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
