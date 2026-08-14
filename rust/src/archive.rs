//! Merkle roots, manifests, snapshots and extraction — sections 5 and 6.
//!
//! The Merkle construction is the part of this format most easily got subtly wrong,
//! so the three choices that matter are implemented here with their reasons rather
//! than copied: domain separation so a leaf hash and a node hash can never collide,
//! odd nodes **promoted and never duplicated** so that `[a,b,c]` and `[a,b,c,c]`
//! cannot share a root (CVE-2012-2459), and a defined root for the empty tree.

use crate::cbor::{encode, decode, Value};
use crate::container::{
    self, check_capabilities, find_latest_footer, hash_bytes, parse_record, walk_footers, Footer,
};
use crate::error::{Error, Kind, Result};

const LEAF_PREFIX: u8 = 0x00;
const NODE_PREFIX: u8 = 0x01;
const EMPTY_PREFIX: u8 = 0x02;
const PRESERVATION_PREFIX: u8 = 0x03;
const OBJECT_ID_PREFIX: u8 = 0x10;

const CODEC_STORE: u64 = 0;
const CODEC_ZSTD: u64 = 1;

fn leaf_hash(data: &[u8], algorithm: &str) -> Result<Vec<u8>> {
    let mut buffer = Vec::with_capacity(data.len() + 1);
    buffer.push(LEAF_PREFIX);
    buffer.extend_from_slice(data);
    Ok(hash_bytes(&buffer, algorithm)?.to_vec())
}

fn node_hash(left: &[u8], right: &[u8], algorithm: &str) -> Result<Vec<u8>> {
    let mut buffer = Vec::with_capacity(left.len() + right.len() + 1);
    buffer.push(NODE_PREFIX);
    buffer.extend_from_slice(left);
    buffer.extend_from_slice(right);
    Ok(hash_bytes(&buffer, algorithm)?.to_vec())
}

pub fn merkle_root(leaves: &[Vec<u8>], algorithm: &str) -> Result<Vec<u8>> {
    if leaves.is_empty() {
        return Ok(hash_bytes(&[EMPTY_PREFIX], algorithm)?.to_vec());
    }
    let mut level: Vec<Vec<u8>> = leaves
        .iter()
        .map(|leaf| leaf_hash(leaf, algorithm))
        .collect::<Result<_>>()?;
    while level.len() > 1 {
        let mut next = Vec::with_capacity(level.len().div_ceil(2));
        let mut index = 0;
        while index + 1 < level.len() {
            next.push(node_hash(&level[index], &level[index + 1], algorithm)?);
            index += 2;
        }
        if level.len() % 2 == 1 {
            // Promoted, not duplicated. Duplicating the odd node makes [a,b,c] and
            // [a,b,c,c] share a root, which is CVE-2012-2459.
            next.push(level[level.len() - 1].clone());
        }
        level = next;
    }
    Ok(level.remove(0))
}

// ---------------------------------------------------------------------------
// manifest
// ---------------------------------------------------------------------------

pub struct Snapshot {
    pub sequence: u64,
    pub snapshot_id: Vec<u8>,
    pub manifest: Value,
    pub footer: Footer,
    pub hash_algorithm: String,
}

impl Snapshot {
    pub fn objects(&self) -> Result<&[Value]> {
        self.manifest
            .need("objects")
            .and_then(|v| v.as_array())
            .map_err(|e| Error::new(Kind::ManifestInvalid, e.to_string()))
    }
    pub fn chunks(&self) -> Result<&[(Value, Value)]> {
        self.manifest
            .need("chunks")
            .and_then(|v| v.as_map())
            .map_err(|e| Error::new(Kind::ManifestInvalid, e.to_string()))
    }
}

fn invalid(message: impl Into<String>) -> Error {
    Error::new(Kind::ManifestInvalid, message)
}

/// Recompute every root from the manifest's own contents and compare.
///
/// Trusting the declared root because the footer's hash covered the manifest bytes
/// would mean a root that says nothing: it would prove only that the manifest had
/// not been edited, not that it describes what it claims to.
pub fn verify_manifest(manifest: &Value, algorithm: &str) -> Result<()> {
    for member in [
        "anla_version",
        "archive_id",
        "snapshot_sequence",
        "created_unix_ns",
        "hash_algorithms",
        "required_capabilities",
        "optional_capabilities",
        "objects",
        "chunks",
        "metadata",
        "auxiliary",
        "objects_root",
        "chunks_root",
        "metadata_root",
        "preservation_root",
        "auxiliary_root",
    ] {
        if manifest.get(member).is_none() {
            return Err(invalid(format!("manifest is missing required member: {member}")));
        }
    }

    let objects = manifest.need("objects").and_then(|v| v.as_array()).map_err(|e| invalid(e.to_string()))?;
    let mut seen_paths: Vec<&str> = Vec::new();
    let mut object_leaves: Vec<(Vec<u8>, Vec<u8>)> = Vec::new();
    for entry in objects {
        let path = entry
            .need("path")
            .and_then(|v| v.as_text())
            .map_err(|e| invalid(e.to_string()))?;
        check_object_path(path)?;
        if let Some(name) = entry.get("name") {
            check_native_name(name, path)?;
        }
        let kind = entry
            .need("kind")
            .and_then(|v| v.as_text())
            .map_err(|e| invalid(e.to_string()))?;
        if !["regular-file", "directory", "symbolic-link"].contains(&kind) {
            return Err(invalid(format!("unsupported object kind: {kind}")));
        }
        if kind == "symbolic-link" && entry.get("target").and_then(|v| v.as_bytes().ok()).is_none() {
            return Err(invalid("a symbolic link needs a byte-string target"));
        }
        if seen_paths.contains(&path) {
            return Err(Error::new(Kind::UnsafeObject, format!("duplicate object path: {path}")));
        }
        seen_paths.push(path);

        let declared = entry
            .need("object_id")
            .and_then(|v| v.as_bytes())
            .map_err(|e| invalid(e.to_string()))?;
        // The identity is every member but the id, re-encoded canonically.
        let identity = Value::Map(
            entry
                .as_map()
                .map_err(|e| invalid(e.to_string()))?
                .iter()
                .filter(|(k, _)| !matches!(k, Value::Text(name) if name == "object_id"))
                .cloned()
                .collect(),
        );
        let mut buffer = vec![OBJECT_ID_PREFIX];
        buffer.extend_from_slice(&encode(&identity));
        if hash_bytes(&buffer, algorithm)?.as_slice() != declared {
            return Err(Error::new(
                Kind::IntegrityFailure,
                format!("object_id does not match the object it identifies: {path}"),
            ));
        }
        object_leaves.push((declared.to_vec(), encode(entry)));
    }
    // Leaf order is part of the definition: objects sort by object_id.
    object_leaves.sort_by(|a, b| a.0.cmp(&b.0));
    let objects_root = merkle_root(
        &object_leaves.into_iter().map(|(_, leaf)| leaf).collect::<Vec<_>>(),
        algorithm,
    )?;

    let chunks = manifest.need("chunks").and_then(|v| v.as_map()).map_err(|e| invalid(e.to_string()))?;
    let mut chunk_leaves: Vec<Vec<u8>> = Vec::new();
    for (id, descriptor) in chunks {
        chunk_leaves.push(encode(&Value::Array(vec![id.clone(), descriptor.clone()])));
    }
    let chunks_root = merkle_root(&chunk_leaves, algorithm)?;

    let metadata = manifest.need("metadata").and_then(|v| v.as_array()).map_err(|e| invalid(e.to_string()))?;
    let mut metadata_leaves: Vec<Vec<u8>> = metadata.iter().map(encode).collect();
    metadata_leaves.sort();
    let metadata_root = merkle_root(&metadata_leaves, algorithm)?;

    let auxiliary = manifest.need("auxiliary").and_then(|v| v.as_array()).map_err(|e| invalid(e.to_string()))?;
    let auxiliary_root = merkle_root(&auxiliary.iter().map(encode).collect::<Vec<_>>(), algorithm)?;

    let mut buffer = vec![PRESERVATION_PREFIX];
    buffer.extend_from_slice(&objects_root);
    buffer.extend_from_slice(&chunks_root);
    buffer.extend_from_slice(&metadata_root);
    let preservation_root = hash_bytes(&buffer, algorithm)?.to_vec();

    for (name, computed) in [
        ("objects_root", &objects_root),
        ("chunks_root", &chunks_root),
        ("metadata_root", &metadata_root),
        ("preservation_root", &preservation_root),
        ("auxiliary_root", &auxiliary_root),
    ] {
        let declared = manifest
            .need(name)
            .and_then(|v| v.as_bytes())
            .map_err(|e| invalid(e.to_string()))?;
        if declared != computed.as_slice() {
            return Err(Error::new(
                Kind::IntegrityFailure,
                format!("{name} disagrees with the manifest contents"),
            ));
        }
    }
    Ok(())
}

/// SPEC-1.0-DRAFT.md section 5.2.1: relative, no NUL, no drive letter, no `.` or
/// The portable rendering of a name that may not be UTF-8 — SPEC §5.2.1.
///
/// Decode as UTF-8; write each byte that will not decode as `%XX`, uppercase. The
/// Python implementation reaches the same answer through `surrogateescape`, which
/// puts an undecodable byte at `U+DC00 + byte`; this one walks the bytes directly
/// because Rust has no such decoding mode. Two routes to one definition is exactly
/// the situation the byte comparison exists to check, and the reason this rule is
/// written out in the specification rather than left as "what the writer does".
pub fn derive_path(name: &[u8]) -> String {
    let mut out = String::with_capacity(name.len());
    let mut i = 0;
    while i < name.len() {
        // The longest valid UTF-8 sequence starting here, if any. `from_utf8` on a
        // shrinking window is O(1) amortised for the 1–4 byte cases that exist.
        let mut taken = 0;
        for width in (1..=4.min(name.len() - i)).rev() {
            if let Ok(text) = core::str::from_utf8(&name[i..i + width]) {
                out.push_str(text);
                taken = width;
                break;
            }
        }
        if taken == 0 {
            out.push_str(&format!("%{:02X}", name[i]));
            taken = 1;
        }
        i += taken;
    }
    out
}

/// A native name is legal only if `path` is what it derives — SPEC §5.2.1.
///
/// That relation is the safety argument. Without it an archive could carry a
/// harmless `path` and a traversing `name`, and a reader that prefers the name
/// would write outside the destination while one that falls back would not — two
/// conforming readers disagreeing about where a file goes, with every hash
/// verifying. This reader accepted all of that until the Python side was built and
/// the two were compared.
fn check_native_name(name: &Value, path: &str) -> Result<()> {
    let bytes = name
        .as_bytes()
        .map_err(|_| invalid(format!("a native name must be a byte string: {path}")))?;
    if bytes.is_empty() {
        return Err(Error::new(
            Kind::UnsafeObject,
            format!("a native name must not be empty: {path}"),
        ));
    }
    if bytes == path.as_bytes() {
        return Err(invalid(format!(
            "a native name equal to the path carries nothing and is omitted: {path}"
        )));
    }
    let derived = derive_path(bytes);
    if derived != path {
        return Err(invalid(format!(
            "the path is not this name's derivation: {path} vs {derived}"
        )));
    }
    Ok(())
}

/// `..` component, `/` the only separator — and a path that would have to be
/// *changed* to satisfy that is refused rather than changed.
pub fn check_object_path(path: &str) -> Result<()> {
    let unsafe_object = |message: &str| Error::new(Kind::UnsafeObject, format!("{message}: {path}"));
    if path.is_empty() {
        return Err(unsafe_object("object path is empty"));
    }
    if path.contains('\0') {
        return Err(unsafe_object("object path contains NUL"));
    }
    if path.starts_with('/') || path.starts_with('\\') {
        return Err(unsafe_object("object path is absolute"));
    }
    let bytes = path.as_bytes();
    if bytes.len() >= 2 && bytes[1] == b':' && bytes[0].is_ascii_alphabetic() {
        return Err(unsafe_object("object path carries a drive letter"));
    }
    if path.contains('\\') {
        // Not rewritten into a separator: a POSIX file genuinely named `a\b` would
        // become `a/b` and restore as a file inside a directory.
        return Err(unsafe_object("object path is not stored in normalized form"));
    }
    for component in path.split('/') {
        if component.is_empty() || component == "." || component == ".." {
            return Err(unsafe_object("unsafe object path component"));
        }
    }
    Ok(())
}

pub fn read_snapshot(data: &[u8], footer: Footer) -> Result<Snapshot> {
    let record = parse_record(data, footer.manifest_offset)?;
    if record.kind != "MANF" {
        return Err(invalid("footer does not point at a MANF record"));
    }
    if record.total_length() != footer.manifest_length {
        return Err(invalid("footer disagrees with the manifest record's length"));
    }
    let algorithm = record
        .header
        .need("hash_algorithm")
        .and_then(|v| v.as_text())
        .map_err(|e| invalid(e.to_string()))?
        .to_owned();
    let declared = record
        .header
        .need("payload_hash")
        .and_then(|v| v.as_bytes())
        .map_err(|e| invalid(e.to_string()))?
        .to_vec();
    let payload = record.payload(data);
    if hash_bytes(payload, &algorithm)?.as_slice() != declared.as_slice() {
        return Err(Error::new(Kind::IntegrityFailure, "manifest payload hash mismatch"));
    }
    let manifest = decode(payload).map_err(|e| invalid(format!("manifest: {e}")))?;

    // Named in two places, so the two must agree — or a reader could verify with
    // one algorithm and interpret with the other.
    let declared_algorithms = manifest
        .need("hash_algorithms")
        .and_then(|v| v.as_array())
        .map_err(|e| invalid(e.to_string()))?;
    if declared_algorithms.len() != 1
        || declared_algorithms[0].as_text().ok() != Some(algorithm.as_str())
    {
        return Err(Error::new(
            Kind::IntegrityFailure,
            "the manifest and its record disagree about the hash",
        ));
    }

    verify_manifest(&manifest, &algorithm)?;
    check_capabilities(&manifest)?;

    let declared_root = manifest
        .need("preservation_root")
        .and_then(|v| v.as_bytes())
        .map_err(|e| invalid(e.to_string()))?;
    if declared_root != footer.preservation_root.as_slice() {
        return Err(Error::new(
            Kind::IntegrityFailure,
            "footer and manifest disagree about preservation_root",
        ));
    }
    // The header and the manifest both name the archive, so the two must agree.
    // Neither reader checked it until a writer produced an archive where they
    // disagreed and both said `ok`.
    let header = container::parse_header(data)?;
    let declared_id = manifest
        .need("archive_id")
        .and_then(|v| v.as_bytes())
        .map_err(|e| invalid(e.to_string()))?;
    if declared_id != header.archive_uuid.as_slice() {
        return Err(Error::new(
            Kind::IntegrityFailure,
            "the manifest and the header disagree about archive_id",
        ));
    }
    let sequence = manifest
        .need("snapshot_sequence")
        .and_then(|v| v.as_u64())
        .map_err(|e| invalid(e.to_string()))?;
    if sequence != footer.snapshot_sequence {
        return Err(Error::new(
            Kind::IntegrityFailure,
            "footer and manifest disagree about the sequence",
        ));
    }
    // snapshot_id is the hash of the *stored* bytes, so re-encoding the decoded
    // manifest must reproduce them. A consequence of the strict decoder, and worth
    // asserting: if it ever stopped holding, every lineage link would stop matching.
    if encode(&manifest) != payload {
        return Err(invalid("manifest bytes are not the canonical encoding"));
    }

    Ok(Snapshot {
        sequence,
        snapshot_id: hash_bytes(payload, &algorithm)?.to_vec(),
        manifest,
        footer,
        hash_algorithm: algorithm,
    })
}

/// Every snapshot, oldest first, with the lineage rules enforced.
pub fn list_snapshots(data: &[u8]) -> Result<Vec<Snapshot>> {
    let mut footers = walk_footers(data)?;
    footers.reverse();
    let mut snapshots = Vec::new();
    for footer in footers {
        snapshots.push(read_snapshot(data, footer)?);
    }
    check_lineage(&snapshots)?;
    check_chunk_placement(&snapshots)?;
    check_record_sequences(data, &snapshots)?;
    Ok(snapshots)
}

/// SPEC-1.0-DRAFT.md section 4.3: within one snapshot, sequences are contiguous and
/// unique; the `FOOT` has the highest; across snapshots they never restart.
///
/// **This was missing, and the differential fuzzer found it on its first run** —
/// two divergences where Python refused and this reader accepted. Worth recording
/// why, because the same rule went unchecked by *both* implementations of MVP until
/// a fuzzer found it there too, and it has now been missed three times by three
/// separate attempts to implement a document that states it plainly.
///
/// The reason is structural rather than careless. Everything else a reader does is
/// seek-based: find the footer, jump to the manifest, jump to each chunk. This is
/// the only rule that requires walking every record from the start, so it is the
/// only one that costs something no other check has already paid for — and an
/// expensive rule with no other caller is exactly the rule an implementer skips.
fn check_record_sequences(data: &[u8], snapshots: &[Snapshot]) -> Result<()> {
    let header = container::parse_header(data)?;
    let mut start = header.first_record_offset;
    let mut highest = 0u64;
    for snapshot in snapshots {
        let end = snapshot.footer.record.end();
        let mut sequences = Vec::new();
        let mut at = start;
        while at + container::RECORD_FRAME_SIZE <= end {
            let record = container::parse_record(data, at)?;
            if record.end() > end {
                return Err(invalid("a record crosses its snapshot's footer"));
            }
            sequences.push(record.sequence);
            at = record.end();
        }
        if at != end {
            return Err(invalid("records do not tile the snapshot exactly"));
        }
        if sequences.is_empty() {
            return Err(invalid("a snapshot contains no records"));
        }
        let lowest = *sequences.iter().min().unwrap();
        let top = *sequences.iter().max().unwrap();
        let mut sorted = sequences.clone();
        sorted.sort_unstable();
        sorted.dedup();
        if sorted.len() != sequences.len() || top - lowest + 1 != sequences.len() as u64 {
            return Err(invalid("record sequences are not contiguous and unique"));
        }
        if lowest <= highest {
            return Err(invalid("record sequences restart across snapshots"));
        }
        if snapshot.footer.record.sequence != top {
            return Err(invalid(
                "the footer is not the highest sequence in its snapshot",
            ));
        }
        highest = top;
        start = end;
    }
    Ok(())
}

pub fn latest_snapshot(data: &[u8]) -> Result<Snapshot> {
    read_snapshot(data, find_latest_footer(data)?)
}

fn check_lineage(snapshots: &[Snapshot]) -> Result<()> {
    let first = snapshots
        .first()
        .ok_or_else(|| invalid("archive holds no snapshots"))?;
    if first.sequence != 1 {
        return Err(invalid("the oldest snapshot in the chain is not sequence 1"));
    }
    if first.manifest.get("parent_snapshot").is_some() {
        return Err(invalid("the first snapshot declares a parent"));
    }
    for pair in snapshots.windows(2) {
        let (previous, current) = (&pair[0], &pair[1]);
        if current.sequence != previous.sequence + 1 {
            return Err(invalid("snapshot sequence is not contiguous"));
        }
        let parent = current
            .manifest
            .get("parent_snapshot")
            .ok_or_else(|| invalid("a snapshot after the first declares no parent"))?
            .as_bytes()
            .map_err(|e| invalid(e.to_string()))?;
        if parent != previous.snapshot_id.as_slice() {
            return Err(Error::new(
                Kind::IntegrityFailure,
                "parent_snapshot does not match the chain",
            ));
        }
        if current.hash_algorithm != previous.hash_algorithm {
            return Err(invalid("snapshots use different hash algorithms"));
        }
    }
    Ok(())
}

fn check_chunk_placement(snapshots: &[Snapshot]) -> Result<()> {
    let mut seen: Vec<(Vec<u8>, Value)> = Vec::new();
    for snapshot in snapshots {
        let limit = snapshot.footer.manifest_offset;
        for (id, descriptor) in snapshot.chunks()? {
            let chunk_id = id.as_bytes().map_err(|e| invalid(e.to_string()))?.to_vec();
            let offset = descriptor
                .need("record_offset")
                .and_then(|v| v.as_usize())
                .map_err(|e| invalid(e.to_string()))?;
            let length = descriptor
                .need("record_length")
                .and_then(|v| v.as_usize())
                .map_err(|e| invalid(e.to_string()))?;
            // In an append-only file every byte a snapshot depends on was written
            // before it, so this is arithmetic rather than a plausibility judgement.
            if offset >= limit || offset + length > limit {
                return Err(invalid(
                    "chunk record is not before the manifest that references it",
                ));
            }
            match seen.iter().find(|(known, _)| *known == chunk_id) {
                Some((_, known)) if known != descriptor => {
                    return Err(Error::new(
                        Kind::IntegrityFailure,
                        "one chunk id with two different descriptors",
                    ))
                }
                Some(_) => {}
                None => seen.push((chunk_id, descriptor.clone())),
            }
        }
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// extraction
// ---------------------------------------------------------------------------

fn decompress(payload: &[u8], codec: u64, raw_size: usize) -> Result<Vec<u8>> {
    match codec {
        CODEC_STORE => {
            if payload.len() != raw_size {
                return Err(Error::new(
                    Kind::ResourceLimitExceeded,
                    "stored chunk is not its declared size",
                ));
            }
            Ok(payload.to_vec())
        }
        CODEC_ZSTD => {
            // Bounded by the *declared* size, before allocating. A frame that says
            // it decodes to fifty megabytes must be refused on the strength of the
            // header, not measured afterwards.
            let raw = zstd::bulk::decompress(payload, raw_size).map_err(|e| {
                Error::new(Kind::ResourceLimitExceeded, format!("zstd: {e}"))
            })?;
            if raw.len() != raw_size {
                return Err(Error::new(
                    Kind::ResourceLimitExceeded,
                    "zstd decoded to the wrong size",
                ));
            }
            Ok(raw)
        }
        other => Err(Error::new(
            Kind::UnsupportedCapability,
            format!("unknown codec id: {other}"),
        )),
    }
}

fn chunk_bytes(data: &[u8], descriptor: &Value, chunk_id: &[u8], algorithm: &str) -> Result<Vec<u8>> {
    let payload_offset = descriptor
        .need("payload_offset")
        .and_then(|v| v.as_usize())
        .map_err(|e| invalid(e.to_string()))?;
    let payload_length = descriptor
        .need("payload_length")
        .and_then(|v| v.as_usize())
        .map_err(|e| invalid(e.to_string()))?;
    let raw_size = descriptor
        .need("raw_size")
        .and_then(|v| v.as_usize())
        .map_err(|e| invalid(e.to_string()))?;
    let codec = descriptor
        .need("codec_id")
        .and_then(|v| v.as_u64())
        .map_err(|e| invalid(e.to_string()))?;
    let record_offset = descriptor
        .need("record_offset")
        .and_then(|v| v.as_usize())
        .map_err(|e| invalid(e.to_string()))?;

    let record = parse_record(data, record_offset)?;
    if record.kind != "CHNK" {
        return Err(invalid("chunk descriptor points at a non-CHNK record"));
    }
    let end = payload_offset
        .checked_add(payload_length)
        .filter(|end| *end <= data.len())
        .ok_or_else(|| invalid("chunk payload lies outside the archive"))?;
    let stored = &data[payload_offset..end];

    let declared_payload_hash = descriptor
        .need("payload_hash")
        .and_then(|v| v.as_bytes())
        .map_err(|e| invalid(e.to_string()))?;
    if hash_bytes(stored, algorithm)?.as_slice() != declared_payload_hash {
        return Err(Error::new(
            Kind::IntegrityFailure,
            "stored chunk does not match its payload hash",
        ));
    }
    let raw = decompress(stored, codec, raw_size)?;
    if hash_bytes(&raw, algorithm)?.as_slice() != chunk_id {
        return Err(Error::new(
            Kind::IntegrityFailure,
            "chunk content does not match its id",
        ));
    }
    Ok(raw)
}

pub fn extract_snapshot(data: &[u8], snapshot: &Snapshot) -> Result<Vec<(String, Vec<u8>)>> {
    let chunks = snapshot.chunks()?;
    let mut restored = Vec::new();
    for entry in snapshot.objects()? {
        let kind = entry.need("kind").and_then(|v| v.as_text()).map_err(|e| invalid(e.to_string()))?;
        if kind != "regular-file" {
            continue;
        }
        let path = entry.need("path").and_then(|v| v.as_text()).map_err(|e| invalid(e.to_string()))?;
        let mut content = Vec::new();
        for chunk_id in entry.need("chunks").and_then(|v| v.as_array()).map_err(|e| invalid(e.to_string()))? {
            let id = chunk_id.as_bytes().map_err(|e| invalid(e.to_string()))?;
            let descriptor = chunks
                .iter()
                .find(|(key, _)| key.as_bytes().ok() == Some(id))
                .map(|(_, value)| value)
                .ok_or_else(|| invalid("a file references a chunk the manifest does not list"))?;
            content.extend_from_slice(&chunk_bytes(data, descriptor, id, &snapshot.hash_algorithm)?);
        }
        let declared = entry
            .need("content_hash")
            .and_then(|v| v.as_bytes())
            .map_err(|e| invalid(e.to_string()))?;
        if hash_bytes(&content, &snapshot.hash_algorithm)?.as_slice() != declared {
            return Err(Error::new(
                Kind::IntegrityFailure,
                format!("file content hash mismatch: {path}"),
            ));
        }
        restored.push((path.to_owned(), content));
    }
    Ok(restored)
}

pub struct ArchiveReport {
    pub snapshots: usize,
    pub unique_chunks: usize,
    pub chunk_bytes: usize,
    pub archive_bytes: usize,
}

pub fn verify_archive(data: &[u8]) -> Result<ArchiveReport> {
    let snapshots = list_snapshots(data)?;
    let mut seen: Vec<Vec<u8>> = Vec::new();
    let mut chunk_bytes = 0usize;
    for snapshot in &snapshots {
        for (id, descriptor) in snapshot.chunks()? {
            let chunk_id = id.as_bytes().map_err(|e| invalid(e.to_string()))?.to_vec();
            if seen.contains(&chunk_id) {
                continue;
            }
            chunk_bytes += chunk_bytes_length(descriptor)?;
            chunk_bytes_verify(data, descriptor, &chunk_id, &snapshot.hash_algorithm)?;
            seen.push(chunk_id);
        }
        // Every file's content hash, not only every chunk's: a manifest can list
        // correct chunks in the wrong order and every chunk-level check will pass.
        extract_snapshot(data, snapshot)?;
    }
    Ok(ArchiveReport {
        snapshots: snapshots.len(),
        unique_chunks: seen.len(),
        chunk_bytes,
        archive_bytes: data.len(),
    })
}

fn chunk_bytes_length(descriptor: &Value) -> Result<usize> {
    descriptor
        .need("payload_length")
        .and_then(|v| v.as_usize())
        .map_err(|e| invalid(e.to_string()))
}

fn chunk_bytes_verify(data: &[u8], descriptor: &Value, id: &[u8], algorithm: &str) -> Result<()> {
    chunk_bytes(data, descriptor, id, algorithm).map(|_| ())
}

pub fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

