//! The container — SPEC-1.0-DRAFT.md sections 3, 4 and 6.
//!
//! Written from the specification's byte tables rather than from the Python. Where
//! the table did not say something, the answer is in a comment, because that is
//! exactly the kind of gap a second implementation exists to find.
//!
//! Two rules here are the ones the specification learned the hard way and states
//! explicitly, so they are implemented explicitly:
//!
//! * `latest_footer_hint` MUST NOT decide which snapshot is latest. It is a
//!   starting guess. A hint pointing at an older but perfectly valid footer passes
//!   every check, so a reader that believed it would report an old snapshot as
//!   current with every hash in the file correct.
//! * Records begin at multiples of eight. That is not implied by "records are
//!   padded to eight bytes" — padding is what a writer emits, alignment is what
//!   this backwards scan depends on.

use crate::cbor::{decode, Value};
use crate::error::{Error, Kind, Result};

pub const ARCHIVE_MAGIC: [u8; 8] = [0x41, 0x4E, 0x4C, 0x41, 0x31, 0x0D, 0x0A, 0x1A];
pub const RECORD_MAGIC: [u8; 4] = *b"ANLR";
pub const HEADER_SIZE: usize = 64;
pub const RECORD_FRAME_SIZE: usize = 40;
pub const ALIGNMENT: usize = 8;
pub const VERSION_MAJOR: u16 = 1;
pub const MAX_RECORD_HEADER: u64 = 16 * 1024 * 1024;

pub const FLAG_REQUIRED_FOR_EXTRACTION: u16 = 1 << 0;
pub const FLAG_REQUIRED_FOR_VERIFICATION: u16 = 1 << 1;
pub const FLAG_ENCRYPTED: u16 = 1 << 2;
pub const FLAG_COMPRESSED_METADATA: u16 = 1 << 3;
pub const FLAG_AUXILIARY_DISPOSABLE: u16 = 1 << 4;
const FLAGS_DEFINED: u16 = FLAG_REQUIRED_FOR_EXTRACTION
    | FLAG_REQUIRED_FOR_VERIFICATION
    | FLAG_ENCRYPTED
    | FLAG_COMPRESSED_METADATA
    | FLAG_AUXILIARY_DISPOSABLE;

pub const KNOWN_CAPABILITIES: &[&str] = &[
    "anla:core:objects:1",
    "anla:core:chunks:1",
    "anla:core:snapshots:1",
    "anla:hash:blake3-256:1",
    "anla:hash:sha256:1",
    "anla:codec:store:1",
    "anla:codec:zstd:1",
    "anla:chunking:anla-cdc-1",
    "anla:object:symlink:1",
    "anla:metadata:common:1",
    "anla:metadata:posix:1",
];

pub const CORE_HASH: &str = "blake3-256";

/// Hash by *name*. No default: every caller has just read the name out of the
/// archive, and a default would be an invitation to skip that read.
pub fn hash_bytes(data: &[u8], algorithm: &str) -> Result<[u8; 32]> {
    match algorithm {
        "blake3-256" => Ok(*blake3::hash(data).as_bytes()),
        "sha256" => Ok(sha256(data)),
        other => Err(Error::new(
            Kind::UnsupportedCapability,
            format!("unsupported hash algorithm: {other}"),
        )),
    }
}

/// SHA-256, written out rather than pulled in. It is here only so that archives
/// written before BLAKE3 existed still read, and one more crate for that is a
/// dependency the reader would carry forever.
fn sha256(data: &[u8]) -> [u8; 32] {
    const K: [u32; 64] = [
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4,
        0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe,
        0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f,
        0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
        0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc,
        0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
        0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116,
        0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
        0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7,
        0xc67178f2,
    ];
    let mut h: [u32; 8] = [
        0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab,
        0x5be0cd19,
    ];
    let mut message = data.to_vec();
    let bit_length = (data.len() as u64).wrapping_mul(8);
    message.push(0x80);
    while message.len() % 64 != 56 {
        message.push(0);
    }
    message.extend_from_slice(&bit_length.to_be_bytes());

    for block in message.chunks_exact(64) {
        let mut w = [0u32; 64];
        for (i, word) in block.chunks_exact(4).enumerate() {
            w[i] = u32::from_be_bytes([word[0], word[1], word[2], word[3]]);
        }
        for i in 16..64 {
            let s0 = w[i - 15].rotate_right(7) ^ w[i - 15].rotate_right(18) ^ (w[i - 15] >> 3);
            let s1 = w[i - 2].rotate_right(17) ^ w[i - 2].rotate_right(19) ^ (w[i - 2] >> 10);
            w[i] = w[i - 16]
                .wrapping_add(s0)
                .wrapping_add(w[i - 7])
                .wrapping_add(s1);
        }
        let (mut a, mut b, mut c, mut d) = (h[0], h[1], h[2], h[3]);
        let (mut e, mut f, mut g, mut hh) = (h[4], h[5], h[6], h[7]);
        for i in 0..64 {
            let s1 = e.rotate_right(6) ^ e.rotate_right(11) ^ e.rotate_right(25);
            let ch = (e & f) ^ ((!e) & g);
            let t1 = hh
                .wrapping_add(s1)
                .wrapping_add(ch)
                .wrapping_add(K[i])
                .wrapping_add(w[i]);
            let s0 = a.rotate_right(2) ^ a.rotate_right(13) ^ a.rotate_right(22);
            let maj = (a & b) ^ (a & c) ^ (b & c);
            let t2 = s0.wrapping_add(maj);
            hh = g;
            g = f;
            f = e;
            e = d.wrapping_add(t1);
            d = c;
            c = b;
            b = a;
            a = t1.wrapping_add(t2);
        }
        for (slot, value) in h.iter_mut().zip([a, b, c, d, e, f, g, hh]) {
            *slot = slot.wrapping_add(value);
        }
    }
    let mut out = [0u8; 32];
    for (i, word) in h.iter().enumerate() {
        out[i * 4..i * 4 + 4].copy_from_slice(&word.to_be_bytes());
    }
    out
}

pub fn crc32(data: &[u8]) -> u32 {
    let mut crc = 0xFFFF_FFFFu32;
    for byte in data {
        crc ^= u32::from(*byte);
        for _ in 0..8 {
            let mask = (crc & 1).wrapping_neg();
            crc = (crc >> 1) ^ (0xEDB8_8320 & mask);
        }
    }
    !crc
}

fn u16at(data: &[u8], at: usize) -> u16 {
    u16::from_le_bytes([data[at], data[at + 1]])
}

fn u32at(data: &[u8], at: usize) -> u32 {
    u32::from_le_bytes([data[at], data[at + 1], data[at + 2], data[at + 3]])
}

fn u64at(data: &[u8], at: usize) -> u64 {
    let mut buffer = [0u8; 8];
    buffer.copy_from_slice(&data[at..at + 8]);
    u64::from_le_bytes(buffer)
}

// ---------------------------------------------------------------------------
// header
// ---------------------------------------------------------------------------

#[derive(Debug, Clone)]
pub struct Header {
    pub version_major: u16,
    pub version_minor: u16,
    pub header_size: usize,
    pub first_record_offset: usize,
    pub latest_footer_hint: u64,
    pub archive_uuid: [u8; 16],
}

pub fn parse_header(data: &[u8]) -> Result<Header> {
    if data.len() < HEADER_SIZE {
        return Err(Error::new(
            Kind::ManifestInvalid,
            "archive is shorter than a bootstrap header",
        ));
    }
    if data[..8] != ARCHIVE_MAGIC {
        return Err(Error::new(Kind::ManifestInvalid, "invalid ANLA 1.0 magic"));
    }
    let version_major = u16at(data, 8);
    if version_major != VERSION_MAJOR {
        return Err(Error::new(
            Kind::UnsupportedCapability,
            format!("unsupported major version: {version_major}"),
        ));
    }
    if crc32(&data[..56]) != u32at(data, 56) {
        return Err(Error::new(Kind::IntegrityFailure, "bootstrap header CRC mismatch"));
    }
    let global_flags = u64at(data, 16);
    if global_flags != 0 {
        // Reserved means reserved. A reader that ignores an unknown global flag is
        // one that will eventually ignore the flag that mattered.
        return Err(Error::new(
            Kind::UnsupportedCapability,
            "unknown global flags are set",
        ));
    }
    let header_size = u32at(data, 12) as usize;
    let first_record_offset = u64at(data, 24) as usize;
    if header_size < HEADER_SIZE || header_size > data.len() {
        return Err(Error::new(
            Kind::ManifestInvalid,
            "header_size is not inside the archive",
        ));
    }
    if first_record_offset < header_size || first_record_offset > data.len() {
        return Err(Error::new(
            Kind::ManifestInvalid,
            "first record overlaps the header or lies outside the archive",
        ));
    }
    let mut archive_uuid = [0u8; 16];
    archive_uuid.copy_from_slice(&data[40..56]);
    Ok(Header {
        version_major,
        version_minor: u16at(data, 10),
        header_size,
        first_record_offset,
        latest_footer_hint: u64at(data, 32),
        archive_uuid,
    })
}

// ---------------------------------------------------------------------------
// record frame
// ---------------------------------------------------------------------------

#[derive(Debug, Clone)]
pub struct Record {
    pub offset: usize,
    pub kind: String,
    pub flags: u16,
    pub sequence: u64,
    pub header: Value,
    pub header_length: usize,
    pub payload_offset: usize,
    pub payload_length: usize,
}

impl Record {
    pub fn total_length(&self) -> usize {
        let unpadded = RECORD_FRAME_SIZE + self.header_length + self.payload_length;
        unpadded + padding_for(unpadded)
    }
    pub fn end(&self) -> usize {
        self.offset + self.total_length()
    }
    pub fn payload<'a>(&self, data: &'a [u8]) -> &'a [u8] {
        &data[self.payload_offset..self.payload_offset + self.payload_length]
    }
}

pub fn padding_for(length: usize) -> usize {
    (ALIGNMENT - (length % ALIGNMENT)) % ALIGNMENT
}

pub fn parse_record(data: &[u8], offset: usize) -> Result<Record> {
    if !offset.is_multiple_of(ALIGNMENT) {
        return Err(Error::new(
            Kind::ManifestInvalid,
            "record offset is not 8-byte aligned",
        ));
    }
    if offset.checked_add(RECORD_FRAME_SIZE).is_none_or(|e| e > data.len()) {
        return Err(Error::new(
            Kind::ManifestInvalid,
            "record frame lies outside the archive",
        ));
    }
    let frame = &data[offset..offset + RECORD_FRAME_SIZE];
    if frame[..4] != RECORD_MAGIC {
        return Err(Error::new(Kind::ManifestInvalid, "invalid record magic"));
    }
    let kind = match std::str::from_utf8(&frame[4..8]) {
        Ok(text) if text.is_ascii() => text.to_owned(),
        _ => return Err(Error::new(Kind::ManifestInvalid, "record type is not ASCII")),
    };
    let flags = u16at(frame, 10);
    let header_length = u32at(frame, 12) as u64;
    let payload_length = u64at(frame, 16);
    let sequence = u64at(frame, 24);
    let expected_crc = u32at(frame, 32);
    if u32at(frame, 36) != 0 {
        return Err(Error::new(
            Kind::ManifestInvalid,
            "reserved record field is not zero",
        ));
    }
    if flags & !FLAGS_DEFINED != 0 {
        return Err(Error::new(
            Kind::UnsupportedCapability,
            "undefined record flags are set",
        ));
    }
    if flags & FLAG_REQUIRED_FOR_EXTRACTION != 0 && flags & FLAG_AUXILIARY_DISPOSABLE != 0 {
        return Err(Error::new(
            Kind::ManifestInvalid,
            "record claims to be both required and disposable",
        ));
    }
    if sequence < 1 {
        return Err(Error::new(Kind::ManifestInvalid, "record sequence is below 1"));
    }
    if header_length > MAX_RECORD_HEADER {
        return Err(Error::new(
            Kind::ResourceLimitExceeded,
            "record header exceeds 16 MiB",
        ));
    }
    // Every declared length is bounded against the real file before it is used to
    // index into it. A 64-bit payload_length is the cheapest thing to forge.
    let header_start = offset + RECORD_FRAME_SIZE;
    let payload_start = match header_start.checked_add(header_length as usize) {
        Some(start) => start,
        None => return Err(Error::new(Kind::ManifestInvalid, "record header length overflows")),
    };
    let payload_end = match usize::try_from(payload_length)
        .ok()
        .and_then(|n| payload_start.checked_add(n))
    {
        Some(end) if end <= data.len() => end,
        _ => {
            return Err(Error::new(
                Kind::ManifestInvalid,
                "record payload lies outside the archive",
            ))
        }
    };
    let header_bytes = &data[header_start..payload_start];
    if crc32(header_bytes) != expected_crc {
        return Err(Error::new(Kind::IntegrityFailure, "record header CRC mismatch"));
    }
    let header = decode(header_bytes)
        .map_err(|e| Error::new(Kind::ManifestInvalid, format!("record header: {e}")))?;

    let unpadded = RECORD_FRAME_SIZE + header_bytes.len() + (payload_end - payload_start);
    let padding = padding_for(unpadded);
    if offset + unpadded + padding > data.len() {
        return Err(Error::new(
            Kind::ManifestInvalid,
            "record padding lies outside the archive",
        ));
    }
    if data[offset + unpadded..offset + unpadded + padding]
        .iter()
        .any(|b| *b != 0)
    {
        return Err(Error::new(Kind::ManifestInvalid, "record padding is not zero"));
    }

    Ok(Record {
        offset,
        kind,
        flags,
        sequence,
        header,
        header_length: header_bytes.len(),
        payload_offset: payload_start,
        payload_length: payload_end - payload_start,
    })
}

pub fn walk_records(data: &[u8], header: &Header) -> Result<Vec<Record>> {
    let mut records = Vec::new();
    let mut at = header.first_record_offset;
    while at + RECORD_FRAME_SIZE <= data.len() {
        let record = parse_record(data, at)?;
        at = record.end();
        records.push(record);
    }
    Ok(records)
}

// ---------------------------------------------------------------------------
// footers
// ---------------------------------------------------------------------------

#[derive(Debug, Clone)]
pub struct Footer {
    pub record: Record,
    pub snapshot_sequence: u64,
    pub manifest_offset: usize,
    pub manifest_length: usize,
    pub previous_footer_offset: Option<usize>,
    pub preservation_root: Vec<u8>,
    pub auxiliary_root: Option<Vec<u8>>,
    pub hash_algorithm: String,
}

pub fn parse_footer(data: &[u8], offset: usize) -> Result<Footer> {
    let record = parse_record(data, offset)?;
    if record.kind != "FOOT" {
        return Err(Error::new(Kind::ManifestInvalid, "record is not a FOOT"));
    }
    // The footer names its own hash algorithm: it is read *before* the manifest that
    // declares `hash_algorithms`, so it cannot inherit the choice from it.
    let algorithm = record
        .header
        .get("hash_algorithm")
        .ok_or_else(|| Error::new(Kind::ManifestInvalid, "footer names no hash algorithm"))?
        .as_text()
        .map_err(|e| Error::new(Kind::ManifestInvalid, e.to_string()))?
        .to_owned();
    let declared = record
        .header
        .need("payload_hash")
        .and_then(|v| v.as_bytes())
        .map_err(|e| Error::new(Kind::ManifestInvalid, e.to_string()))?
        .to_vec();
    let payload = record.payload(data);
    if hash_bytes(payload, &algorithm)?.as_slice() != declared.as_slice() {
        return Err(Error::new(Kind::IntegrityFailure, "footer payload hash mismatch"));
    }
    let body = decode(payload)
        .map_err(|e| Error::new(Kind::ManifestInvalid, format!("footer payload: {e}")))?;

    let read_index = |key: &str| -> Result<usize> {
        body.need(key)
            .and_then(|v| v.as_usize())
            .map_err(|e| Error::new(Kind::ManifestInvalid, format!("footer {key}: {e}")))
    };

    Ok(Footer {
        snapshot_sequence: body
            .need("snapshot_sequence")
            .and_then(|v| v.as_u64())
            .map_err(|e| Error::new(Kind::ManifestInvalid, e.to_string()))?,
        manifest_offset: read_index("manifest_offset")?,
        manifest_length: read_index("manifest_length")?,
        previous_footer_offset: match body.get("previous_footer_offset") {
            Some(value) => Some(
                value
                    .as_usize()
                    .map_err(|e| Error::new(Kind::ManifestInvalid, e.to_string()))?,
            ),
            None => None,
        },
        preservation_root: body
            .need("preservation_root")
            .and_then(|v| v.as_bytes())
            .map_err(|e| Error::new(Kind::ManifestInvalid, e.to_string()))?
            .to_vec(),
        auxiliary_root: body
            .get("auxiliary_root")
            .and_then(|v| v.as_bytes().ok())
            .map(<[u8]>::to_vec),
        hash_algorithm: algorithm,
        record,
    })
}

/// The newest complete footer, found by scanning backwards.
///
/// Never by trusting `latest_footer_hint`. An interrupted append leaves a hint
/// pointing at a footer that was never finished, and a reader that believes it
/// reports an older snapshot as current with every hash checking out.
pub fn find_latest_footer(data: &[u8]) -> Result<Footer> {
    let header = parse_header(data)?;
    if data.len() < RECORD_FRAME_SIZE {
        return Err(Error::new(Kind::ManifestInvalid, "no complete footer found"));
    }
    let mut at = (data.len() - (data.len() % ALIGNMENT)).saturating_sub(RECORD_FRAME_SIZE);
    at -= at % ALIGNMENT;
    loop {
        if at + 8 <= data.len() && data[at..at + 4] == RECORD_MAGIC && &data[at + 4..at + 8] == b"FOOT"
        {
            if let Ok(footer) = parse_footer(data, at) {
                if footer.record.end() <= data.len() {
                    return Ok(footer);
                }
            }
        }
        if at < header.first_record_offset + ALIGNMENT {
            break;
        }
        at -= ALIGNMENT;
    }
    Err(Error::new(Kind::ManifestInvalid, "no complete footer found"))
}

/// Every snapshot, newest first. Refuses a cycle rather than following one.
pub fn walk_footers(data: &[u8]) -> Result<Vec<Footer>> {
    let mut footers = vec![find_latest_footer(data)?];
    let mut seen = vec![footers[0].record.offset];
    while let Some(previous) = footers.last().unwrap().previous_footer_offset {
        let current_offset = footers.last().unwrap().record.offset;
        if seen.contains(&previous) {
            return Err(Error::new(Kind::ManifestInvalid, "footer chain contains a cycle"));
        }
        if previous >= current_offset {
            return Err(Error::new(Kind::ManifestInvalid, "footer chain does not descend"));
        }
        let footer = parse_footer(data, previous)?;
        if footer.snapshot_sequence >= footers.last().unwrap().snapshot_sequence {
            return Err(Error::new(
                Kind::ManifestInvalid,
                "snapshot sequence does not decrease along the chain",
            ));
        }
        seen.push(previous);
        footers.push(footer);
    }
    Ok(footers)
}

pub fn check_capabilities(manifest: &Value) -> Result<Vec<String>> {
    let required = manifest
        .get("required_capabilities")
        .map(|v| v.as_array())
        .transpose()
        .map_err(|e| Error::new(Kind::ManifestInvalid, e.to_string()))?
        .unwrap_or(&[]);
    let mut missing = Vec::new();
    for entry in required {
        let name = entry
            .as_text()
            .map_err(|e| Error::new(Kind::ManifestInvalid, e.to_string()))?;
        if !KNOWN_CAPABILITIES.contains(&name) {
            missing.push(name.to_owned());
        }
    }
    if !missing.is_empty() {
        return Err(Error::new(
            Kind::UnsupportedCapability,
            format!("archive requires capabilities this reader lacks: {missing:?}"),
        ));
    }
    // Unknown *optional* capabilities are ignored silently and reported, never
    // refused: an unknown metadata namespace is something this reader cannot apply,
    // not something it cannot verify.
    let optional = manifest
        .get("optional_capabilities")
        .map(|v| v.as_array())
        .transpose()
        .map_err(|e| Error::new(Kind::ManifestInvalid, e.to_string()))?
        .unwrap_or(&[]);
    let mut ignored = Vec::new();
    for entry in optional {
        if let Ok(name) = entry.as_text() {
            if !KNOWN_CAPABILITIES.contains(&name) {
                ignored.push(name.to_owned());
            }
        }
    }
    Ok(ignored)
}
