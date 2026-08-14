//! The canonical CBOR profile — SPEC-1.0-DRAFT.md section 5.1.
//!
//! Hand-written, not a crate. The whole value of a second implementation is that it
//! disagrees where the specification is ambiguous, and a decoder pulled off the
//! shelf would be enforcing that crate's idea of CBOR rather than this format's.
//! The rules here are the ones section 5.1 states: definite lengths only, integers
//! and lengths in their shortest form, map keys sorted by their *encoded* bytes.
//!
//! The decoder is strict — it refuses non-canonical input rather than normalising
//! it. A decoder that accepts two encodings of one logical manifest lets two
//! archives with different hashes mean the same thing.

use std::fmt;

pub const MAX_DEPTH: usize = 64;

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
pub enum Value {
    Uint(u64),
    /// Encodes -1 - n, as CBOR major type 1 does.
    Nint(u64),
    Bytes(Vec<u8>),
    Text(String),
    Array(Vec<Value>),
    /// A vector rather than a map, so the decoder can *check* the key order
    /// instead of losing it to a hash table and silently accepting bad input.
    Map(Vec<(Value, Value)>),
    Bool(bool),
}

#[derive(Debug)]
pub struct CborError(pub String);

impl fmt::Display for CborError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

type R<T> = Result<T, CborError>;

fn err<T>(message: impl Into<String>) -> R<T> {
    Err(CborError(message.into()))
}

impl Value {
    pub fn as_u64(&self) -> R<u64> {
        match self {
            Value::Uint(n) => Ok(*n),
            other => err(format!("expected an unsigned integer, found {other:?}")),
        }
    }

    pub fn as_usize(&self) -> R<usize> {
        let n = self.as_u64()?;
        usize::try_from(n).or_else(|_| err("value does not fit in a machine word"))
    }

    pub fn as_bytes(&self) -> R<&[u8]> {
        match self {
            Value::Bytes(b) => Ok(b),
            other => err(format!("expected a byte string, found {other:?}")),
        }
    }

    pub fn as_text(&self) -> R<&str> {
        match self {
            Value::Text(s) => Ok(s),
            other => err(format!("expected a text string, found {other:?}")),
        }
    }

    pub fn as_array(&self) -> R<&[Value]> {
        match self {
            Value::Array(items) => Ok(items),
            other => err(format!("expected an array, found {other:?}")),
        }
    }

    pub fn as_map(&self) -> R<&[(Value, Value)]> {
        match self {
            Value::Map(entries) => Ok(entries),
            other => err(format!("expected a map, found {other:?}")),
        }
    }

    /// Look a text key up in a map. Linear because these maps are small, and a hash
    /// map would throw away the ordering the decoder just finished checking.
    pub fn get(&self, key: &str) -> Option<&Value> {
        match self {
            Value::Map(entries) => entries.iter().find_map(|(k, v)| match k {
                Value::Text(name) if name == key => Some(v),
                _ => None,
            }),
            _ => None,
        }
    }

    pub fn need(&self, key: &str) -> R<&Value> {
        self.get(key)
            .ok_or_else(|| CborError(format!("missing member: {key}")))
    }
}

// ---------------------------------------------------------------------------
// encoding
// ---------------------------------------------------------------------------

fn push_head(out: &mut Vec<u8>, major: u8, argument: u64) {
    let high = major << 5;
    match argument {
        0..=23 => out.push(high | argument as u8),
        24..=0xFF => {
            out.push(high | 24);
            out.push(argument as u8);
        }
        0x100..=0xFFFF => {
            out.push(high | 25);
            out.extend_from_slice(&(argument as u16).to_be_bytes());
        }
        0x1_0000..=0xFFFF_FFFF => {
            out.push(high | 26);
            out.extend_from_slice(&(argument as u32).to_be_bytes());
        }
        _ => {
            out.push(high | 27);
            out.extend_from_slice(&argument.to_be_bytes());
        }
    }
}

pub fn encode(value: &Value) -> Vec<u8> {
    let mut out = Vec::new();
    encode_into(value, &mut out);
    out
}

fn encode_into(value: &Value, out: &mut Vec<u8>) {
    match value {
        Value::Uint(n) => push_head(out, 0, *n),
        Value::Nint(n) => push_head(out, 1, *n),
        Value::Bytes(b) => {
            push_head(out, 2, b.len() as u64);
            out.extend_from_slice(b);
        }
        Value::Text(s) => {
            push_head(out, 3, s.len() as u64);
            out.extend_from_slice(s.as_bytes());
        }
        Value::Array(items) => {
            push_head(out, 4, items.len() as u64);
            for item in items {
                encode_into(item, out);
            }
        }
        Value::Map(entries) => {
            // Sorted by *encoded* key bytes, not by value. "z" sorts before "aa",
            // because the encoded forms are 61 7a and 62 61 61.
            let mut pairs: Vec<(Vec<u8>, &Value)> =
                entries.iter().map(|(k, v)| (encode(k), v)).collect();
            pairs.sort_by(|a, b| a.0.cmp(&b.0));
            push_head(out, 5, pairs.len() as u64);
            for (key, value) in pairs {
                out.extend_from_slice(&key);
                encode_into(value, out);
            }
        }
        Value::Bool(b) => out.push(if *b { 0xF5 } else { 0xF4 }),
    }
}

// ---------------------------------------------------------------------------
// decoding
// ---------------------------------------------------------------------------

struct Reader<'a> {
    data: &'a [u8],
    at: usize,
}

impl<'a> Reader<'a> {
    fn take(&mut self, n: usize) -> R<&'a [u8]> {
        match self.at.checked_add(n) {
            Some(end) if end <= self.data.len() => {
                let slice = &self.data[self.at..end];
                self.at = end;
                Ok(slice)
            }
            // A declared length longer than the input is the commonest thing a
            // fuzzer produces, so it is a refusal rather than a panic.
            _ => err("input ended inside a value"),
        }
    }

    fn head(&mut self) -> R<(u8, u64)> {
        let first = self.take(1)?[0];
        let major = first >> 5;
        let extra = first & 0x1F;
        let argument = match extra {
            0..=23 => u64::from(extra),
            24 => {
                let n = u64::from(self.take(1)?[0]);
                if n < 24 {
                    return err("integer is not in its shortest form");
                }
                n
            }
            25 => {
                let b = self.take(2)?;
                let n = u64::from(u16::from_be_bytes([b[0], b[1]]));
                if n <= 0xFF {
                    return err("integer is not in its shortest form");
                }
                n
            }
            26 => {
                let b = self.take(4)?;
                let n = u64::from(u32::from_be_bytes([b[0], b[1], b[2], b[3]]));
                if n <= 0xFFFF {
                    return err("integer is not in its shortest form");
                }
                n
            }
            27 => {
                let b = self.take(8)?;
                let n = u64::from_be_bytes([b[0], b[1], b[2], b[3], b[4], b[5], b[6], b[7]]);
                if n <= 0xFFFF_FFFF {
                    return err("integer is not in its shortest form");
                }
                n
            }
            31 => return err("indefinite lengths are not in this profile"),
            _ => return err(format!("reserved additional information: {extra}")),
        };
        Ok((major, argument))
    }

    fn value(&mut self, depth: usize) -> R<Value> {
        if depth > MAX_DEPTH {
            // Bounded rather than recursed into. Twenty thousand nested arrays used
            // to be a stack overflow in the Python decoder, where a refusal was owed.
            return err("nesting is deeper than the profile allows");
        }
        let (major, argument) = self.head()?;
        match major {
            0 => Ok(Value::Uint(argument)),
            1 => Ok(Value::Nint(argument)),
            2 => {
                let n = usize::try_from(argument)
                    .or_else(|_| err("byte string length does not fit in memory"))?;
                Ok(Value::Bytes(self.take(n)?.to_vec()))
            }
            3 => {
                let n = usize::try_from(argument)
                    .or_else(|_| err("text length does not fit in memory"))?;
                let raw = self.take(n)?;
                match std::str::from_utf8(raw) {
                    Ok(text) => Ok(Value::Text(text.to_owned())),
                    Err(_) => err("text string is not valid UTF-8"),
                }
            }
            4 => {
                // Not pre-allocated from the declared count: a four-byte header can
                // claim four billion items, and reserving for them is the whole
                // allocation attack.
                let mut items = Vec::new();
                for _ in 0..argument {
                    items.push(self.value(depth + 1)?);
                }
                Ok(Value::Array(items))
            }
            5 => {
                let mut entries: Vec<(Value, Value)> = Vec::new();
                let mut previous: Option<Vec<u8>> = None;
                for _ in 0..argument {
                    let start = self.at;
                    let key = self.value(depth + 1)?;
                    let key_bytes = self.data[start..self.at].to_vec();
                    if let Some(before) = &previous {
                        // Checked, never sorted afterwards: sorting would accept a
                        // non-canonical encoding and quietly repair it, which is how
                        // two archives with different hashes come to mean one thing.
                        if *before >= key_bytes {
                            return err("map keys are not sorted by encoded bytes");
                        }
                    }
                    previous = Some(key_bytes);
                    let value = self.value(depth + 1)?;
                    entries.push((key, value));
                }
                Ok(Value::Map(entries))
            }
            7 => match argument {
                20 => Ok(Value::Bool(false)),
                21 => Ok(Value::Bool(true)),
                22 => err("null is not in this profile"),
                other => err(format!("simple value {other} is not in this profile")),
            },
            other => err(format!("major type {other} is not in this profile")),
        }
    }
}

pub fn decode(data: &[u8]) -> R<Value> {
    let mut reader = Reader { data, at: 0 };
    let value = reader.value(0)?;
    if reader.at != data.len() {
        return err(format!(
            "{} trailing bytes after the top-level value",
            data.len() - reader.at
        ));
    }
    Ok(value)
}
