//! `anla1-rs` — an independent reader and writer for ANLA 1.0 (draft).
//!
//! This exists for one reason: the freeze rule at the top of `SPEC-1.0-DRAFT.md`
//! says nothing is frozen until two independent implementations produce
//! byte-identical archives *and* a differential fuzzer finds no verdict divergence.
//! Until 2026-08-14 there was one implementation. This is the other, and it does
//! both halves — it reads, so the fuzzer has two verdicts to compare, and it writes,
//! so there are two sets of bytes to diff.
//!
//! **Those two instruments catch different things, which is why the rule has two
//! clauses.** The fuzzer asks "do you both accept this?", and two implementations
//! that are wrong in the *same* way answer yes together. That happened: an append
//! wrote a manifest whose `archive_id` disagreed with the header's, both readers
//! verified it, and sixteen thousand mutants said nothing. The byte comparison found
//! it immediately, because writing the same archive twice has no shared blind spot
//! to hide in.
//!
//! **An honest limitation, since the point of the exercise is honesty about
//! verification.** Two implementations by one author are weaker evidence than two by
//! two authors: I have read the Python, and a shared misreading of the
//! specification reproduces here rather than being caught. The incident above is
//! that weakness showing up in practice rather than in theory.

// A reader's surface is wider than any one command uses: a caller embedding this
// wants the header's fields and `latest_snapshot` even though `verify` does not.
// Kept and marked rather than deleted, so the crate stays a reader rather than a
// verify subcommand with a library-shaped hole in it.
#![allow(dead_code)]

mod archive;
mod cbor;
mod container;
mod error;
mod writer;

#[cfg(test)]
mod tests;

use std::io::Read;
use std::process::ExitCode;

use archive::{extract_snapshot, hex, list_snapshots, verify_archive};
use error::{Error, Kind};

fn json_escape(text: &str) -> String {
    let mut out = String::with_capacity(text.len() + 2);
    for ch in text.chars() {
        match ch {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out
}

fn next_arg(
    rest: &mut std::slice::Iter<'_, String>,
    flag: &str,
) -> std::result::Result<String, Error> {
    rest.next()
        .cloned()
        .ok_or_else(|| Error::new(Kind::InvalidInput, format!("{flag} needs a value")))
}

fn rest_value(_flag: &str) {}

fn parse_uuid(text: &str) -> std::result::Result<[u8; 16], Error> {
    let clean: String = text.chars().filter(|c| *c != '-').collect();
    if clean.len() != 32 {
        return Err(Error::new(Kind::InvalidInput, "--uuid must be 16 bytes of hex"));
    }
    let mut out = [0u8; 16];
    for (index, slot) in out.iter_mut().enumerate() {
        *slot = u8::from_str_radix(&clean[index * 2..index * 2 + 2], 16)
            .map_err(|_| Error::new(Kind::InvalidInput, "--uuid must be hex"))?;
    }
    Ok(out)
}

fn read_input(path: &str) -> std::result::Result<Vec<u8>, Error> {
    if path == "-" {
        let mut buffer = Vec::new();
        std::io::stdin()
            .read_to_end(&mut buffer)
            .map_err(|e| Error::new(Kind::InvalidInput, e.to_string()))?;
        return Ok(buffer);
    }
    std::fs::read(path).map_err(|e| Error::new(Kind::InvalidInput, format!("{path}: {e}")))
}

fn pack_command(command: &str, path: &str, args: &[String])
    -> std::result::Result<String, Error>
{
        // The other half of the freeze rule: same tree in, same bytes out, from
        // a program that shares no code with the Python writer.
        let mut options = writer::PackOptions {
            archive_id: [0u8; 16],
            created_unix_ns: 0,
            profile: None,
            codec: 1,
            level: 10,
            hash_algorithm: "blake3-256".to_string(),
            preserve_metadata: true,
            allow_unsupported: false,
        };
        let mut output = String::new();
        let mut exclude: Vec<String> = Vec::new();
        let mut rest = args.iter();
        while let Some(flag) = rest.next() {
            let value = || {
                rest_value(flag)
            };
            match flag.as_str() {
                "-o" | "--output" => output = next_arg(&mut rest, flag)?,
                "--uuid" => options.archive_id = parse_uuid(&next_arg(&mut rest, flag)?)?,
                "--created-ns" => {
                    options.created_unix_ns = next_arg(&mut rest, flag)?
                        .parse()
                        .map_err(|_| Error::new(Kind::InvalidInput, "--created-ns"))?
                }
                "--chunk-avg" => {
                    let average: usize = next_arg(&mut rest, flag)?
                        .parse()
                        .map_err(|_| Error::new(Kind::InvalidInput, "--chunk-avg"))?;
                    if !average.is_power_of_two() {
                        return Err(Error::new(
                            Kind::InvalidInput,
                            "--chunk-avg must be a power of two",
                        ));
                    }
                    options.profile = Some(writer::CdcProfile {
                        min_size: (average / 4).max(1),
                        avg_size: average,
                        max_size: average * 4,
                        normalization: 2,
                    });
                }
                "--chunking" => {
                    if next_arg(&mut rest, flag)? == "cdc" {
                        options.profile = Some(writer::CdcProfile::default());
                    }
                }
                "--codec" => {
                    options.codec = if next_arg(&mut rest, flag)? == "zstd" { 1 } else { 0 }
                }
                "--level" => {
                    options.level = next_arg(&mut rest, flag)?
                        .parse()
                        .map_err(|_| Error::new(Kind::InvalidInput, "--level"))?
                }
                "--exclude" => exclude.push(next_arg(&mut rest, flag)?),
                "--no-metadata" => options.preserve_metadata = false,
                "--skip-unsupported" => options.allow_unsupported = true,
                "--json" => {}
                other => {
                    let _ = value;
                    return Err(Error::new(
                        Kind::InvalidInput,
                        format!("unknown option: {other}"),
                    ));
                }
            }
        }
        // `pack <dir> -o <archive>` and `append <archive> <dir>` name their operands
        // in opposite orders, matching the Python CLI. Resolved here explicitly
        // rather than cleverly, because a writer that appended to the tree it was
        // reading would be a memorable afternoon.
        let (existing, tree, destination) = if command == "append" {
            let archive = std::fs::read(path)
                .map_err(|e| Error::new(Kind::InvalidInput, format!("{path}: {e}")))?;
            if output.is_empty() {
                return Err(Error::new(Kind::InvalidInput, "append needs -o <directory>"));
            }
            (archive, output.clone(), path.to_string())
        } else {
            if output.is_empty() {
                return Err(Error::new(Kind::InvalidInput, "-o is required"));
            }
            (Vec::new(), path.to_string(), output.clone())
        };
        // Streamed to the destination rather than assembled and then written. The
        // archive never exists as one object, so a tree larger than memory is
        // packable — which the Python writer could already do and this one could
        // not, the two implementations' capabilities inverted exactly where it
        // mattered. An append writes after the newest complete footer and patches
        // the 64-byte header instead of rebuilding the file.
        let bytes = writer::pack_to_file(
            std::path::Path::new(&destination), &existing,
            std::path::Path::new(&tree), &exclude, &options)?;
        Ok(format!(
            "{{\"archive\":\"{}\",\"bytes\":{}}}",
            json_escape(&destination),
            bytes
        ))
}

fn run(args: &[String]) -> std::result::Result<String, Error> {
    let command = args
        .first()
        .map(String::as_str)
        .ok_or_else(|| Error::new(Kind::InvalidInput, "usage: anla1-rs <verify|list|snapshots|extract|selftest> <archive>"))?;

    if command == "selftest" {
        return Ok(selftest());
    }

    let path = args
        .get(1)
        .ok_or_else(|| Error::new(Kind::InvalidInput, "a path is required"))?;

    // `pack` takes a *directory*; every other command takes an archive. Reading the
    // path before dispatching tried to `fs::read` a folder, which on Windows is an
    // access-denied rather than the is-a-directory you would expect to see.
    if command == "pack" || command == "append" {
        return pack_command(command, path, &args[2..]);
    }
    let data = read_input(path)?;

    match command {
        "verify" => {
            let report = verify_archive(&data)?;
            Ok(format!(
                "{{\"ok\":true,\"snapshots\":{},\"unique_chunks\":{},\"chunk_bytes\":{},\"archive_bytes\":{}}}",
                report.snapshots, report.unique_chunks, report.chunk_bytes, report.archive_bytes
            ))
        }
        "snapshots" => {
            let snapshots = list_snapshots(&data)?;
            let rows: Vec<String> = snapshots
                .iter()
                .map(|s| {
                    format!(
                        "{{\"sequence\":{},\"snapshot_id\":\"{}\",\"objects\":{},\"chunks\":{}}}",
                        s.sequence,
                        hex(&s.snapshot_id),
                        s.objects().map(<[cbor::Value]>::len).unwrap_or(0),
                        s.chunks().map(<[(cbor::Value, cbor::Value)]>::len).unwrap_or(0),
                    )
                })
                .collect();
            Ok(format!("{{\"snapshots\":[{}]}}", rows.join(",")))
        }
        "list" => {
            let snapshots = list_snapshots(&data)?;
            let latest = snapshots.last().unwrap();
            let mut rows = Vec::new();
            for entry in latest.objects()? {
                let path = entry.need("path").and_then(|v| v.as_text()).unwrap_or("?");
                let kind = entry.need("kind").and_then(|v| v.as_text()).unwrap_or("?");
                let size = entry.get("size").and_then(|v| v.as_u64().ok()).unwrap_or(0);
                rows.push(format!(
                    "{{\"path\":\"{}\",\"kind\":\"{}\",\"size\":{}}}",
                    json_escape(path),
                    kind,
                    size
                ));
            }
            Ok(format!("{{\"objects\":[{}]}}", rows.join(",")))
        }
        "extract" => {
            // Digests rather than bytes: the fuzzer and the cross-check compare
            // this against the Python, and a hash per path is the comparison that
            // does not depend on how either side happens to serialise content.
            let snapshots = list_snapshots(&data)?;
            let latest = snapshots.last().unwrap();
            let restored = extract_snapshot(&data, latest)?;
            let rows: Vec<String> = restored
                .iter()
                .map(|(path, content)| {
                    format!(
                        "{{\"path\":\"{}\",\"bytes\":{},\"blake3\":\"{}\"}}",
                        json_escape(path),
                        content.len(),
                        hex(blake3::hash(content).as_bytes())
                    )
                })
                .collect();
            Ok(format!("{{\"files\":[{}]}}", rows.join(",")))
        }
        other => Err(Error::new(
            Kind::InvalidInput,
            format!("unknown command: {other}"),
        )),
    }
}

/// Pinned values, so a build that links a different BLAKE3 or miscompiles the
/// canonical encoder says so before anyone trusts a verdict from it.
fn selftest() -> String {
    let mut checks = Vec::new();
    let mut ok = true;

    let empty = hex(&container::hash_bytes(b"", "blake3-256").unwrap());
    let expected = "af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262";
    ok &= empty == expected;
    checks.push(format!("{{\"check\":\"blake3-empty\",\"ok\":{}}}", empty == expected));

    let abc = hex(&container::hash_bytes(b"abc", "sha256").unwrap());
    let want = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";
    ok &= abc == want;
    checks.push(format!("{{\"check\":\"sha256-abc\",\"ok\":{}}}", abc == want));

    // RFC 8949 appendix A, and the ordering rule that is this profile's own:
    // keys sort by encoded bytes, so "z" comes before "aa".
    let map = cbor::Value::Map(vec![
        (cbor::Value::Text("aa".into()), cbor::Value::Uint(2)),
        (cbor::Value::Text("z".into()), cbor::Value::Uint(1)),
    ]);
    let encoded = hex(&cbor::encode(&map));
    let want_map = "a2617a01626161 02".replace(' ', "");
    ok &= encoded == want_map;
    checks.push(format!("{{\"check\":\"cbor-key-order\",\"ok\":{}}}", encoded == want_map));

    let empty_root = hex(&archive::merkle_root(&[], "blake3-256").unwrap());
    let has_root = empty_root.len() == 64;
    ok &= has_root;
    checks.push(format!("{{\"check\":\"merkle-empty\",\"ok\":{has_root}}}"));

    format!("{{\"ok\":{},\"checks\":[{}]}}", ok, checks.join(","))
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match run(&args) {
        Ok(output) => {
            println!("{output}");
            ExitCode::SUCCESS
        }
        Err(error) => {
            eprintln!(
                "{{\"ok\":false,\"code\":\"{}\",\"message\":\"{}\"}}",
                error.kind.name(),
                json_escape(&error.message)
            );
            ExitCode::from(error.kind.exit_code() as u8)
        }
    }
}
