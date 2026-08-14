//! Tests for the parts a differential fuzzer reaches slowly or not at all.
//!
//! The fuzzer is the main instrument: it mutates real archives and compares
//! verdicts, which finds disagreements no hand-written test would think of. What it
//! is bad at is producing a *specific* malformed encoding on purpose — a
//! non-shortest integer, a map with keys one byte out of order — because those are
//! narrow targets in a very large space.
//!
//! So this file covers the canonical CBOR rules directly. That is also where two
//! implementations diverge most easily, since "canonical" is a set of refusals
//! rather than a behaviour, and a decoder that quietly accepts is indistinguishable
//! from one that is correct until something depends on the difference.

use crate::archive::merkle_root;
use crate::cbor::{decode, encode, Value};
use crate::container::{crc32, hash_bytes};

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

// ---------------------------------------------------------------------------
// canonical CBOR: the refusals
// ---------------------------------------------------------------------------

#[test]
fn shortest_form_is_required() {
    // 0x00 is the canonical encoding of 0. 0x18 0x00 says the same thing longer.
    assert!(decode(&[0x00]).is_ok());
    for longer in [
        vec![0x18, 0x00],                                     // 1-byte for a tiny int
        vec![0x19, 0x00, 0x17],                               // 2-byte for 23
        vec![0x1a, 0x00, 0x00, 0x00, 0xff],                   // 4-byte for 255
        vec![0x1b, 0, 0, 0, 0, 0, 0, 0xff, 0xff],             // 8-byte for 65535
    ] {
        assert!(decode(&longer).is_err(), "accepted {}", hex(&longer));
    }
}

#[test]
fn indefinite_lengths_are_refused() {
    // 0x9f is an indefinite-length array. Legal CBOR, not in this profile: it
    // gives one logical value two encodings, and then two archives one meaning.
    for indefinite in [vec![0x9f, 0x01, 0xff], vec![0xbf, 0x61, 0x61, 0x01, 0xff],
                       vec![0x5f, 0x41, 0x61, 0xff]] {
        assert!(decode(&indefinite).is_err(), "accepted {}", hex(&indefinite));
    }
}

#[test]
fn map_keys_must_be_sorted_by_encoded_bytes() {
    // {"z": 1, "aa": 2}. Sorted by *encoded bytes*, "z" (61 7a) precedes "aa"
    // (62 61 61) — the opposite of what sorting the strings would give.
    let canonical = [0xa2, 0x61, 0x7a, 0x01, 0x62, 0x61, 0x61, 0x02];
    assert!(decode(&canonical).is_ok());

    let swapped = [0xa2, 0x62, 0x61, 0x61, 0x02, 0x61, 0x7a, 0x01];
    assert!(decode(&swapped).is_err(), "accepted a map sorted by value");

    let duplicated = [0xa2, 0x61, 0x7a, 0x01, 0x61, 0x7a, 0x02];
    assert!(decode(&duplicated).is_err(), "accepted a duplicate key");
}

#[test]
fn the_encoder_agrees_with_the_rule_the_decoder_enforces() {
    let map = Value::Map(vec![
        (Value::Text("aa".into()), Value::Uint(2)),
        (Value::Text("z".into()), Value::Uint(1)),
    ]);
    let bytes = encode(&map);
    assert_eq!(hex(&bytes), "a2617a01626161 02".replace(' ', ""));
    // And round-trips: the decoder accepts what the encoder produced, which is the
    // property `snapshot_id` depends on — it hashes the *stored* bytes.
    assert_eq!(encode(&decode(&bytes).unwrap()), bytes);
}

#[test]
fn null_and_floats_are_not_in_the_profile() {
    assert!(decode(&[0xf6]).is_err(), "accepted null");
    assert!(decode(&[0xfa, 0x00, 0x00, 0x00, 0x00]).is_err(), "accepted a float");
    assert!(decode(&[0xf4]).is_ok());
    assert!(decode(&[0xf5]).is_ok());
}

#[test]
fn trailing_bytes_are_refused() {
    assert!(decode(&[0x00, 0x00]).is_err(), "accepted a second top-level value");
}

#[test]
fn a_declared_length_longer_than_the_input_is_refused_not_panicked() {
    // A four-gigabyte byte string in a three-byte file. The commonest thing a
    // fuzzer produces, and the one that must not become an allocation.
    assert!(decode(&[0x5a, 0xff, 0xff, 0xff, 0xff]).is_err());
    assert!(decode(&[0x9a, 0xff, 0xff, 0xff, 0xff]).is_err());
}

#[test]
fn nesting_is_bounded() {
    // 20_000 nested arrays used to be a stack overflow in the Python decoder, where
    // a refusal was owed. Depth is capped here rather than recursed into.
    let deep: Vec<u8> = std::iter::repeat_n(0x81u8, 20_000).chain([0x00]).collect();
    assert!(decode(&deep).is_err());
}

// ---------------------------------------------------------------------------
// the pinned primitives
// ---------------------------------------------------------------------------

#[test]
fn published_hash_vectors() {
    assert_eq!(
        hex(&hash_bytes(b"", "blake3-256").unwrap()),
        "af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262"
    );
    assert_eq!(
        hex(&hash_bytes(b"abc", "blake3-256").unwrap()),
        "6437b3ac38465133ffb63b75273a8db548c558465d79db03fd359c6cd5bd9d85"
    );
    // SHA-256 is written out in this crate rather than imported, so its vectors
    // matter more than usual.
    assert_eq!(
        hex(&hash_bytes(b"", "sha256").unwrap()),
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    );
    assert_eq!(
        hex(&hash_bytes(b"abc", "sha256").unwrap()),
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    );
    let long = b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq";
    assert_eq!(
        hex(&hash_bytes(long, "sha256").unwrap()),
        "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"
    );
    assert!(hash_bytes(b"", "md5").is_err());
}

#[test]
fn crc32_matches_the_published_vector() {
    assert_eq!(crc32(b"123456789"), 0xCBF4_3926);
    assert_eq!(crc32(b""), 0);
}

#[test]
fn an_odd_merkle_node_is_promoted_and_never_duplicated() {
    // Duplicating the odd node makes [a,b,c] and [a,b,c,c] share a root, which is
    // CVE-2012-2459. Asserted as an *absence*, and with the colliding construction
    // written out beside it so the test says what it is guarding against.
    let three: Vec<Vec<u8>> = vec![b"a".to_vec(), b"b".to_vec(), b"c".to_vec()];
    let four: Vec<Vec<u8>> = vec![b"a".to_vec(), b"b".to_vec(), b"c".to_vec(), b"c".to_vec()];
    assert_ne!(
        merkle_root(&three, "blake3-256").unwrap(),
        merkle_root(&four, "blake3-256").unwrap()
    );
    // Domain separation: an empty tree has a root, and it is not the hash of nothing.
    let empty = merkle_root(&[], "blake3-256").unwrap();
    assert_eq!(empty.len(), 32);
    assert_ne!(empty, hash_bytes(b"", "blake3-256").unwrap().to_vec());
    // A single leaf is leaf-hashed, not passed through.
    let one = merkle_root(&[b"a".to_vec()], "blake3-256").unwrap();
    assert_ne!(one, hash_bytes(b"a", "blake3-256").unwrap().to_vec());
}

#[test]
fn object_paths_that_would_have_to_be_rewritten_are_refused() {
    use crate::archive::check_object_path;

    for good in ["a", "a/b", "docs/guide.md", "resumé.txt", "深/路徑.txt"] {
        assert!(check_object_path(good).is_ok(), "refused {good}");
    }
    // `a\b` is the one that matters: normalising it into `a/b` would store a
    // different tree than the one that went in, with every hash still verifying.
    for bad in ["", "/absolute", "../escape", "a/./b", "a//b", "C:/drive", "a\\b"] {
        assert!(check_object_path(bad).is_err(), "accepted {bad}");
    }
}


#[test]
fn a_native_name_derives_the_path_the_specification_says() {
    use crate::archive::derive_path;

    // The same table as `python/tests/test_native_names_1_0.py`, deliberately
    // duplicated rather than shared: two implementations agreeing because they read
    // one file is not two implementations agreeing. `tools/compare_names.py` then
    // checks the pair over four hundred names neither table thought of.
    let cases: &[(&[u8], &str)] = &[
        (b"hello.txt", "hello.txt"),
        ("café.txt".as_bytes(), "café.txt"),
        ("中文.txt".as_bytes(), "中文.txt"),
        (b"caf\xe9.txt", "caf%E9.txt"),
        (b"\xff\xfe.bin", "%FF%FE.bin"),
        (b"a\x80b\x81c", "a%80b%81c"),
        (b"dir/caf\xe9.txt", "dir/caf%E9.txt"),
        // A lead byte with nothing following it: the window search must not run off
        // the end, and must escape the lead byte alone rather than consuming what
        // is not there.
        (b"\xc3", "%C3"),
        (b"\xc3\x28", "%C3("),
        // A surrogate encoded as UTF-8, which `from_utf8` rejects byte by byte.
        (b"\xed\xa0\x80", "%ED%A0%80"),
        // An overlong NUL: two bytes, neither valid, both escaped.
        (b"\xc0\x80", "%C0%80"),
    ];
    for (native, expected) in cases {
        assert_eq!(&derive_path(native), expected, "for {native:?}");
    }
}

#[test]
fn the_derivation_never_loses_a_valid_prefix() {
    use crate::archive::derive_path;

    // The failure mode a byte-walking implementation has and a decoding one does
    // not: consuming one byte at a time would turn a perfectly good multi-byte
    // character into three escapes. Every valid character here must survive whole,
    // with only the trailing rubbish escaped.
    let mut name = "中文-漢字".as_bytes().to_vec();
    name.extend_from_slice(b"\xe9\xff");
    name.extend_from_slice("🌏".as_bytes());
    assert_eq!(derive_path(&name), "中文-漢字%E9%FF🌏");
}


/// A scratch directory that removes itself. No dev-dependency for two tests.
struct Scratch(std::path::PathBuf);

impl Scratch {
    fn new(name: &str) -> Self {
        let path = std::env::temp_dir().join(format!("anla1-rs-{name}"));
        let _ = std::fs::remove_dir_all(&path);
        std::fs::create_dir_all(&path).expect("scratch directory");
        Self(path)
    }

    fn join(&self, name: &str) -> std::path::PathBuf {
        self.0.join(name)
    }
}

impl Drop for Scratch {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

fn pack_options(created_unix_ns: u64) -> crate::writer::PackOptions {
    crate::writer::PackOptions {
        archive_id: [7u8; 16],
        created_unix_ns,
        profile: None,
        codec: 0,   // store; the codec is not what these tests are about
        level: 3,
        hash_algorithm: "blake3-256".to_string(),
        // No recorded metadata: mtimes differ between the two packs otherwise, and
        // the equality below would fail for a reason that is not the sink.
        preserve_metadata: false,
        allow_unsupported: false,
    }
}

#[test]
fn streaming_to_a_file_produces_what_packing_into_memory_produces() {
    // The only property a streaming refactor is allowed to have. `pack` and
    // `pack_to_file` are the same code behind two sinks, and this is what says the
    // sink is not part of the output — the cross-implementation byte comparison
    // then says the same thing against a completely separate writer.
    let scratch = Scratch::new("stream-identity");
    let tree = scratch.join("tree");
    std::fs::create_dir_all(tree.join("sub")).unwrap();
    std::fs::write(tree.join("a.txt"), vec![b'a'; 5000]).unwrap();
    std::fs::write(tree.join("sub/b.bin"), vec![0xA5u8; 70_000]).unwrap();

    let options = pack_options(1);
    let in_memory = crate::writer::pack(&[], &tree, &[], &options).unwrap();

    let target = scratch.join("streamed.anla");
    let size = crate::writer::pack_to_file(&target, &[], &tree, &[], &options).unwrap();
    let streamed = std::fs::read(&target).unwrap();

    assert_eq!(size as usize, streamed.len());
    assert_eq!(in_memory.len(), streamed.len(), "streamed archive is a different size");
    assert_eq!(in_memory, streamed, "streamed archive differs from the in-memory one");
}

#[test]
fn an_append_reclaims_what_a_torn_write_left_behind() {
    // SPEC §4.4. A write that did not finish leaves the file at an arbitrary length,
    // and resuming at the end of the *file* rather than the end of the newest
    // complete footer puts every later record off its alignment — after which
    // `find_latest_footer` scans past the new footer and the archive keeps reading
    // as the older snapshot, with every hash correct and nothing erroring.
    //
    // The Python writer had a real bug here that the clean-append case could not
    // show, because truncating to a file's existing length is a no-op that
    // succeeds. Only a torn archive actually shrinks.
    use std::io::Write;

    let scratch = Scratch::new("torn-append");
    let tree = scratch.join("tree");
    std::fs::create_dir_all(&tree).unwrap();
    std::fs::write(tree.join("a.txt"), vec![b'a'; 5000]).unwrap();

    let options = pack_options(1);
    let target = scratch.join("torn.anla");
    crate::writer::pack_to_file(&target, &[], &tree, &[], &options).unwrap();
    let clean_len = std::fs::metadata(&target).unwrap().len();

    std::fs::OpenOptions::new()
        .append(true)
        .open(&target)
        .unwrap()
        .write_all(&[0xDE; 1200])
        .unwrap();
    assert_eq!(std::fs::metadata(&target).unwrap().len(), clean_len + 1200);

    let second = scratch.join("second");
    std::fs::create_dir_all(&second).unwrap();
    std::fs::write(second.join("b.txt"), b"second snapshot").unwrap();

    // A clean copy of the same archive, to append to as well. Comparing the two
    // results is the only unambiguous test: the first version of this asserted the
    // torn archive ended up smaller than `clean + garbage`, which the new
    // snapshot's own records make false whether the tail was reclaimed or not. The
    // assertion was wrong, not the code — and it could only fail, never mislead,
    // which is the good kind of broken test.
    let control = scratch.join("control.anla");
    crate::writer::pack_to_file(&control, &[], &tree, &[], &options).unwrap();

    let appending = pack_options(2);
    let after = {
        let existing = std::fs::read(&target).unwrap();
        crate::writer::pack_to_file(&target, &existing, &second, &[], &appending).unwrap()
    };
    let expected = {
        let existing = std::fs::read(&control).unwrap();
        crate::writer::pack_to_file(&control, &existing, &second, &[], &appending).unwrap()
    };

    let archive = std::fs::read(&target).unwrap();
    assert_eq!(after as usize, archive.len());
    assert_eq!(after, expected,
               "appending onto a torn archive gave {after} where a clean one gave                 {expected} — the {} bytes of torn tail were kept", 1200);
    assert_eq!(archive, std::fs::read(&control).unwrap(),
               "the two archives differ despite being the same size");
    assert_eq!(crate::archive::list_snapshots(&archive).unwrap().len(), 2,
               "both snapshots must be readable");
    let _ = clean_len;
}
