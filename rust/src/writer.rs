//! A writer — the other half of the freeze rule.
//!
//! Reading an archive proves two implementations agree about what is *valid*.
//! Writing one proves they agree about what is *canonical*, and that is the clause
//! byte-identity is stated over: same tree in, same bytes out, from two programs
//! that share no code.
//!
//! Everything with a choice in it is here, and every choice is one the
//! specification made rather than one this file is making:
//!
//! * **`anla-cdc-1`** — the gear table is *derived*, `SHA-256("anla-gear-1" ‖ 0x00
//!   ‖ i)[0..4]`, so there is no table of constants to copy wrongly. The boundary is
//!   the *top* k bits being zero, because gear hashing accumulates history there.
//! * **Ordering** — files by UTF-8 path bytes, objects by `object_id`, map keys by
//!   encoded CBOR bytes. Every one of those decides an offset, so a writer that
//!   disagreed about any of them would produce a valid archive with different bytes.
//! * **A chunk that grew is stored**, and the archive then does not require
//!   `anla:codec:zstd:1` of its readers.
//!
//! What it does not do, stated rather than discovered: no symbolic links, no
//! recorded metadata, no appending to an existing archive. It writes one snapshot of
//! regular files and directories. That is exactly the surface the byte-identity
//! comparison needs, and everything beyond it would be surface the comparison does
//! not yet cover.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use crate::archive::{check_object_path, merkle_root};
use crate::cbor::{encode, Value};
use crate::container::{crc32, hash_bytes, ALIGNMENT, ARCHIVE_MAGIC, HEADER_SIZE,
                       RECORD_FRAME_SIZE, RECORD_MAGIC};
use crate::error::{Error, Kind, Result};

const FLAG_REQUIRED_FOR_EXTRACTION: u16 = 1;
const RECORD_VERSION: u16 = 1;
const OBJECT_ID_PREFIX: u8 = 0x10;
const PRESERVATION_PREFIX: u8 = 0x03;
const CODEC_STORE: u64 = 0;
const CODEC_ZSTD: u64 = 1;

// ---------------------------------------------------------------------------
// anla-cdc-1
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Copy)]
pub struct CdcProfile {
    pub min_size: usize,
    pub avg_size: usize,
    pub max_size: usize,
    pub normalization: u32,
}

impl Default for CdcProfile {
    fn default() -> Self {
        CdcProfile {
            min_size: 64 * 1024,
            avg_size: 256 * 1024,
            max_size: 1024 * 1024,
            normalization: 2,
        }
    }
}

impl CdcProfile {
    fn bits(&self) -> u32 {
        self.avg_size.trailing_zeros()
    }

    pub fn as_manifest_member(&self) -> Value {
        Value::Map(vec![
            (Value::Text("algorithm".into()), Value::Text("fastcdc".into())),
            (Value::Text("version".into()), Value::Text("anla-cdc-1".into())),
            (Value::Text("gear_table_id".into()), Value::Text("anla-gear-1".into())),
            (Value::Text("gear_table_sha256".into()),
             Value::Text(gear_table_digest())),
            (Value::Text("min".into()), Value::Uint(self.min_size as u64)),
            (Value::Text("avg".into()), Value::Uint(self.avg_size as u64)),
            (Value::Text("max".into()), Value::Uint(self.max_size as u64)),
            (Value::Text("normalization".into()), Value::Uint(u64::from(self.normalization))),
            (Value::Text("fingerprint".into()), Value::Text("gear32".into())),
            (Value::Text("boundary".into()), Value::Text("top-bits-zero".into())),
        ])
    }
}

/// Derived, never copied. Three lines and no constants means a third implementation
/// can check it rather than trust a transcription.
fn gear_table() -> [u32; 256] {
    let mut table = [0u32; 256];
    for (index, slot) in table.iter_mut().enumerate() {
        let mut seed = b"anla-gear-1".to_vec();
        seed.push(0x00);
        seed.push(index as u8);
        let digest = hash_bytes(&seed, "sha256").expect("sha256 is built in");
        *slot = u32::from_be_bytes([digest[0], digest[1], digest[2], digest[3]]);
    }
    table
}

fn gear_table_digest() -> String {
    let mut buffer = Vec::with_capacity(1024);
    for word in gear_table() {
        buffer.extend_from_slice(&word.to_be_bytes());
    }
    hash_bytes(&buffer, "sha256")
        .expect("sha256 is built in")
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

/// One past the end of the chunk beginning at `start`.
///
/// Written as the plainest possible loop, for the reason the Python says out loud:
/// this function's output is part of the format's identity, so it is the last place
/// to be clever.
fn next_cut(data: &[u8], start: usize, profile: &CdcProfile, gear: &[u32; 256]) -> usize {
    let remaining = data.len() - start;
    if remaining <= profile.min_size {
        return data.len();
    }
    let limit = start + remaining.min(profile.max_size);
    let normal_end = start + remaining.min(profile.avg_size);
    let bits = profile.bits();
    let strict_shift = 32 - (bits + profile.normalization);
    let loose_shift = 32 - (bits - profile.normalization);

    let mut fingerprint: u32 = 0;
    let mut index = start + profile.min_size;
    while index < normal_end {
        fingerprint = (fingerprint >> 1).wrapping_add(gear[data[index] as usize]);
        if fingerprint >> strict_shift == 0 {
            return index + 1;
        }
        index += 1;
    }
    while index < limit {
        fingerprint = (fingerprint >> 1).wrapping_add(gear[data[index] as usize]);
        if fingerprint >> loose_shift == 0 {
            return index + 1;
        }
        index += 1;
    }
    limit
}

pub fn cut_points(data: &[u8], profile: &CdcProfile) -> Vec<(usize, usize)> {
    let gear = gear_table();
    let mut ranges = Vec::new();
    let mut at = 0;
    while at < data.len() {
        let end = next_cut(data, at, profile, &gear);
        ranges.push((at, end));
        at = end;
    }
    ranges
}

// ---------------------------------------------------------------------------
// records
// ---------------------------------------------------------------------------

fn padding_for(length: usize) -> usize {
    (ALIGNMENT - (length % ALIGNMENT)) % ALIGNMENT
}

fn build_header(uuid: &[u8; 16], hint: u64) -> Vec<u8> {
    let mut buffer = vec![0u8; HEADER_SIZE];
    buffer[0..8].copy_from_slice(&ARCHIVE_MAGIC);
    buffer[8..10].copy_from_slice(&1u16.to_le_bytes());
    buffer[10..12].copy_from_slice(&0u16.to_le_bytes());
    buffer[12..16].copy_from_slice(&(HEADER_SIZE as u32).to_le_bytes());
    buffer[16..24].copy_from_slice(&0u64.to_le_bytes());
    buffer[24..32].copy_from_slice(&(HEADER_SIZE as u64).to_le_bytes());
    buffer[32..40].copy_from_slice(&hint.to_le_bytes());
    buffer[40..56].copy_from_slice(uuid);
    let checksum = crc32(&buffer[0..56]);
    buffer[56..60].copy_from_slice(&checksum.to_le_bytes());
    buffer
}

fn build_record(kind: &str, header: &Value, payload: &[u8], sequence: u64) -> Vec<u8> {
    let header_bytes = encode(header);
    let mut frame = vec![0u8; RECORD_FRAME_SIZE];
    frame[0..4].copy_from_slice(&RECORD_MAGIC);
    frame[4..8].copy_from_slice(kind.as_bytes());
    frame[8..10].copy_from_slice(&RECORD_VERSION.to_le_bytes());
    frame[10..12].copy_from_slice(&FLAG_REQUIRED_FOR_EXTRACTION.to_le_bytes());
    frame[12..16].copy_from_slice(&(header_bytes.len() as u32).to_le_bytes());
    frame[16..24].copy_from_slice(&(payload.len() as u64).to_le_bytes());
    frame[24..32].copy_from_slice(&sequence.to_le_bytes());
    frame[32..36].copy_from_slice(&crc32(&header_bytes).to_le_bytes());
    // bytes 36..40 stay zero: reserved, and a reader refuses a non-zero value.

    let mut out = frame;
    out.extend_from_slice(&header_bytes);
    out.extend_from_slice(payload);
    out.extend(std::iter::repeat_n(0u8, padding_for(out.len())));
    out
}

// ---------------------------------------------------------------------------
// the pack
// ---------------------------------------------------------------------------

pub struct PackOptions {
    pub archive_id: [u8; 16],
    pub created_unix_ns: u64,
    pub profile: Option<CdcProfile>,
    pub codec: u64,
    pub level: i32,
    pub hash_algorithm: String,
}

struct SourceFile {
    path: String,
    disk: PathBuf,
}

/// Walk a directory into the objects a snapshot describes.
///
/// Symbolic links and special files are refused rather than skipped: an archive
/// that silently omitted one would still be claiming `Extract(Pack(F, P)) = F`, and
/// this writer has no fidelity report to record the omission in.
fn scan(root: &Path, exclude: &[String]) -> Result<(Vec<SourceFile>, Vec<String>)> {
    let mut files = Vec::new();
    let mut directories = Vec::new();
    let mut stack = vec![root.to_path_buf()];
    while let Some(current) = stack.pop() {
        let entries = std::fs::read_dir(&current)
            .map_err(|e| Error::new(Kind::InvalidInput, format!("{}: {e}", current.display())))?;
        for entry in entries {
            let entry = entry
                .map_err(|e| Error::new(Kind::InvalidInput, e.to_string()))?;
            let disk = entry.path();
            let relative = disk
                .strip_prefix(root)
                .map_err(|_| Error::new(Kind::InvalidInput, "path escaped the root"))?;
            let archive_path = relative
                .components()
                .map(|c| c.as_os_str().to_string_lossy().into_owned())
                .collect::<Vec<_>>()
                .join("/");
            check_object_path(&archive_path)?;
            if exclude.iter().any(|prefix| archive_path == *prefix
                || archive_path.starts_with(&format!("{prefix}/"))) {
                continue;
            }
            let meta = std::fs::symlink_metadata(&disk)
                .map_err(|e| Error::new(Kind::InvalidInput, e.to_string()))?;
            if meta.file_type().is_symlink() {
                return Err(Error::new(
                    Kind::UnsafeObject,
                    format!("this writer cannot represent a symbolic link: {archive_path}"),
                ));
            }
            if meta.is_dir() {
                directories.push(archive_path);
                stack.push(disk);
            } else if meta.is_file() {
                files.push(SourceFile { path: archive_path, disk });
            } else {
                return Err(Error::new(
                    Kind::UnsafeObject,
                    format!("this writer cannot represent this entry: {archive_path}"),
                ));
            }
        }
    }
    // By UTF-8 path bytes. Not by locale collation, which is the defect that made the
    // original browser writer's byte layout depend on the machine that ran it.
    files.sort_by(|a, b| a.path.as_bytes().cmp(b.path.as_bytes()));
    directories.sort_by(|a, b| a.as_bytes().cmp(b.as_bytes()));
    Ok((files, directories))
}

fn compress(raw: &[u8], codec: u64, level: i32) -> Result<(u64, Vec<u8>)> {
    if codec == CODEC_STORE || raw.is_empty() {
        return Ok((CODEC_STORE, raw.to_vec()));
    }
    let packed = zstd::bulk::compress(raw, level)
        .map_err(|e| Error::new(Kind::InvalidInput, format!("zstd: {e}")))?;
    // A chunk that grew is stored. Random bytes come back longer, and paying a
    // decompression step for a larger file is a bad trade in both directions.
    if packed.len() >= raw.len() {
        Ok((CODEC_STORE, raw.to_vec()))
    } else {
        Ok((CODEC_ZSTD, packed))
    }
}

pub fn pack(root: &Path, exclude: &[String], options: &PackOptions) -> Result<Vec<u8>> {
    let (files, directories) = scan(root, exclude)?;
    let algorithm = options.hash_algorithm.as_str();
    let hash = |data: &[u8]| -> Result<Vec<u8>> { Ok(hash_bytes(data, algorithm)?.to_vec()) };

    let mut out = build_header(&options.archive_id, 0);
    let mut sequence = 1u64;
    let mut chunk_map: BTreeMap<Vec<u8>, Value> = BTreeMap::new();
    let mut objects: Vec<(Vec<u8>, Value)> = Vec::new();
    let mut used_zstd = false;

    for path in &directories {
        let identity = Value::Map(vec![
            (Value::Text("kind".into()), Value::Text("directory".into())),
            (Value::Text("path".into()), Value::Text(path.clone())),
        ]);
        objects.push(object_entry(identity, algorithm)?);
    }

    for file in &files {
        let payload = std::fs::read(&file.disk)
            .map_err(|e| Error::new(Kind::InvalidInput, format!("{}: {e}", file.disk.display())))?;
        let pieces: Vec<(usize, usize)> = match &options.profile {
            Some(profile) => cut_points(&payload, profile),
            None if payload.is_empty() => Vec::new(),
            None => vec![(0, payload.len())],
        };

        let mut ids = Vec::new();
        for (start, end) in pieces {
            let raw = &payload[start..end];
            // The chunk id is the hash of the *raw* chunk, before any codec touches
            // it, which is what keeps compression out of objects_root.
            let chunk_id = hash(raw)?;
            ids.push(Value::Bytes(chunk_id.clone()));
            if chunk_map.contains_key(&chunk_id) {
                continue;
            }
            let (codec, stored) = compress(raw, options.codec, options.level)?;
            if codec == CODEC_ZSTD {
                used_zstd = true;
            }
            let payload_hash = hash(&stored)?;
            let offset = out.len();
            let header = Value::Map(vec![
                (Value::Text("chunk_id".into()), Value::Bytes(chunk_id.clone())),
                (Value::Text("codec_id".into()), Value::Uint(codec)),
                (Value::Text("raw_size".into()), Value::Uint(raw.len() as u64)),
                (Value::Text("payload_hash".into()), Value::Bytes(payload_hash.clone())),
            ]);
            let record = build_record("CHNK", &header, &stored, sequence);
            let header_length = encode(&header).len();
            chunk_map.insert(
                chunk_id,
                Value::Map(vec![
                    (Value::Text("record_offset".into()), Value::Uint(offset as u64)),
                    (Value::Text("record_length".into()), Value::Uint(record.len() as u64)),
                    (Value::Text("payload_offset".into()),
                     Value::Uint((offset + RECORD_FRAME_SIZE + header_length) as u64)),
                    (Value::Text("payload_length".into()), Value::Uint(stored.len() as u64)),
                    (Value::Text("raw_size".into()), Value::Uint(raw.len() as u64)),
                    (Value::Text("codec_id".into()), Value::Uint(codec)),
                    (Value::Text("payload_hash".into()), Value::Bytes(payload_hash)),
                ]),
            );
            out.extend_from_slice(&record);
            sequence += 1;
        }

        let identity = Value::Map(vec![
            (Value::Text("kind".into()), Value::Text("regular-file".into())),
            (Value::Text("path".into()), Value::Text(file.path.clone())),
            (Value::Text("size".into()), Value::Uint(payload.len() as u64)),
            (Value::Text("content_hash".into()), Value::Bytes(hash(&payload)?)),
            (Value::Text("chunks".into()), Value::Array(ids)),
        ]);
        objects.push(object_entry(identity, algorithm)?);
    }

    // Objects sort by object_id — the order is part of the definition of
    // objects_root, not the caller's choice.
    objects.sort_by(|a, b| a.0.cmp(&b.0));
    let object_values: Vec<Value> = objects.iter().map(|(_, entry)| entry.clone()).collect();

    let objects_root = merkle_root(
        &object_values.iter().map(encode).collect::<Vec<_>>(),
        algorithm,
    )?;
    let chunk_leaves: Vec<Vec<u8>> = chunk_map
        .iter()
        .map(|(id, descriptor)| {
            encode(&Value::Array(vec![Value::Bytes(id.clone()), descriptor.clone()]))
        })
        .collect();
    let chunks_root = merkle_root(&chunk_leaves, algorithm)?;
    let metadata_root = merkle_root(&[], algorithm)?;
    let auxiliary_root = merkle_root(&[], algorithm)?;
    let mut buffer = vec![PRESERVATION_PREFIX];
    buffer.extend_from_slice(&objects_root);
    buffer.extend_from_slice(&chunks_root);
    buffer.extend_from_slice(&metadata_root);
    let preservation_root = hash(&buffer)?;

    let mut required = vec![
        "anla:core:objects:1".to_string(),
        "anla:core:chunks:1".to_string(),
        "anla:core:snapshots:1".to_string(),
        format!("anla:hash:{algorithm}:1"),
        "anla:codec:store:1".to_string(),
    ];
    if used_zstd {
        required.push("anla:codec:zstd:1".to_string());
    }
    required.sort();

    let mut manifest_entries = vec![
        (Value::Text("anla_version".into()),
         Value::Array(vec![Value::Uint(1), Value::Uint(0)])),
        (Value::Text("archive_id".into()), Value::Bytes(options.archive_id.to_vec())),
        (Value::Text("snapshot_sequence".into()), Value::Uint(1)),
        (Value::Text("created_unix_ns".into()), Value::Uint(options.created_unix_ns)),
        (Value::Text("hash_algorithms".into()),
         Value::Array(vec![Value::Text(algorithm.to_string())])),
        (Value::Text("required_capabilities".into()),
         Value::Array(required.into_iter().map(Value::Text).collect())),
        (Value::Text("optional_capabilities".into()), Value::Array(vec![])),
        (Value::Text("objects".into()), Value::Array(object_values)),
        (Value::Text("chunks".into()),
         Value::Map(chunk_map.iter().map(|(k, v)| (Value::Bytes(k.clone()), v.clone())).collect())),
        (Value::Text("metadata".into()), Value::Array(vec![])),
        (Value::Text("auxiliary".into()), Value::Array(vec![])),
        (Value::Text("objects_root".into()), Value::Bytes(objects_root)),
        (Value::Text("chunks_root".into()), Value::Bytes(chunks_root)),
        (Value::Text("metadata_root".into()), Value::Bytes(metadata_root)),
        (Value::Text("preservation_root".into()), Value::Bytes(preservation_root.clone())),
        (Value::Text("auxiliary_root".into()), Value::Bytes(auxiliary_root.clone())),
    ];

    if let Some(profile) = &options.profile {
        let mut plan = match profile.as_manifest_member() {
            Value::Map(entries) => entries,
            _ => unreachable!("as_manifest_member returns a map"),
        };
        plan.push((Value::Text("codec".into()), codec_plan(options)?));
        let plan = Value::Map(plan);
        manifest_entries.push((Value::Text("packing_plan_digest".into()),
                               Value::Bytes(hash(&encode(&plan))?)));
        manifest_entries.push((Value::Text("packing_plan".into()), plan));
    }

    let manifest = Value::Map(manifest_entries);
    let payload = encode(&manifest);
    let manifest_offset = out.len();
    let manifest_record = build_record(
        "MANF",
        &Value::Map(vec![
            (Value::Text("hash_algorithm".into()), Value::Text(algorithm.to_string())),
            (Value::Text("payload_hash".into()), Value::Bytes(hash(&payload)?)),
        ]),
        &payload,
        sequence,
    );
    out.extend_from_slice(&manifest_record);
    sequence += 1;

    let footer_payload = encode(&Value::Map(vec![
        (Value::Text("snapshot_sequence".into()), Value::Uint(1)),
        (Value::Text("manifest_offset".into()), Value::Uint(manifest_offset as u64)),
        (Value::Text("manifest_length".into()), Value::Uint(manifest_record.len() as u64)),
        (Value::Text("preservation_root".into()), Value::Bytes(preservation_root)),
        (Value::Text("auxiliary_root".into()), Value::Bytes(auxiliary_root)),
    ]));
    let footer_offset = out.len();
    out.extend_from_slice(&build_record(
        "FOOT",
        &Value::Map(vec![
            (Value::Text("hash_algorithm".into()), Value::Text(algorithm.to_string())),
            (Value::Text("payload_hash".into()), Value::Bytes(hash(&footer_payload)?)),
        ]),
        &footer_payload,
        sequence,
    ));

    // The hint is written last and believed by nobody.
    let header = build_header(&options.archive_id, footer_offset as u64);
    out[..HEADER_SIZE].copy_from_slice(&header);
    Ok(out)
}

fn codec_plan(options: &PackOptions) -> Result<Value> {
    if options.codec == CODEC_STORE {
        return Ok(Value::Map(vec![
            (Value::Text("id".into()), Value::Uint(CODEC_STORE)),
            (Value::Text("name".into()), Value::Text("store".into())),
        ]));
    }
    let version = zstd::zstd_safe::VERSION_NUMBER;
    let (major, minor, patch) = (version / 10000, (version / 100) % 100, version % 100);
    Ok(Value::Map(vec![
        (Value::Text("id".into()), Value::Uint(CODEC_ZSTD)),
        (Value::Text("name".into()), Value::Text("zstd".into())),
        (Value::Text("level".into()), Value::Uint(options.level as u64)),
        (Value::Text("library".into()),
         Value::Text(format!("libzstd {major}.{minor}.{patch}"))),
    ]))
}

fn object_entry(identity: Value, algorithm: &str) -> Result<(Vec<u8>, Value)> {
    let mut buffer = vec![OBJECT_ID_PREFIX];
    buffer.extend_from_slice(&encode(&identity));
    let object_id = hash_bytes(&buffer, algorithm)?.to_vec();
    let mut entries = vec![(Value::Text("object_id".into()), Value::Bytes(object_id.clone()))];
    match identity {
        Value::Map(members) => entries.extend(members),
        _ => unreachable!("an identity is a map"),
    }
    Ok((object_id, Value::Map(entries)))
}
