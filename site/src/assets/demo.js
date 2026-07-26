// The live test page.
//
// Everything the site claims about ANLA-MVP v0.1 is claimed because a test says
// so. This page runs those tests in the reader's own browser, against the same
// web/anla-core.js the workbench uses and the conformance suite runs under Node,
// and against the same fixtures and frozen vectors that are checked into the
// repository.
//
// The load-bearing comparison is in the first suite. The hashes it checks against
// were produced by the *Python* writer on a different machine. When a row goes
// green, this browser has just reproduced, byte for byte, an archive that a
// different implementation in a different language wrote.
//
// The IDs match the conformance table, so a row here and a row in
// conformance/README.md mean the same thing.

import {
  pack, openArchive, exportZip, canonical, canonicalBytes, safePath,
  buildHeader, buildRecord, buildFooter, crc32, sha256, sha256Hex, toHex,
  concatBytes, compareUtf8, HEADER_SIZE, FOOTER_SIZE,
  GEAR, GEAR_TABLE_DIGEST, CDC_GEAR_TABLE_ID, normalizeCdcProfile, cutPoints,
  hasNativeCrypto, hasNativeCompression, DEFAULT_PLAN, AnlaError,
} from './anla-core.js';
import { FIXTURES } from './fixtures.js';
import { VECTOR_BYTES_BASE64, VECTOR_SHA256, VECTOR_NOT_BUNDLED } from './vectors.js';

const T = globalThis.ANLA_I18N ?? {};
const t = (key, fallback = '') => (T[key] ?? fallback);
const $ = (selector) => document.querySelector(selector);
const encoder = new TextEncoder();

// ---------------------------------------------------------------- fixtures

function fromBase64(text) {
  const binary = atob(text);
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) out[i] = binary.charCodeAt(i);
  return out;
}

function fixturePath(entry) {
  return entry.path_codepoints
    ? String.fromCodePoint(...entry.path_codepoints) : entry.path;
}

/**
 * The pinned LCG from fixtures.json.
 *
 * Math.imul is required: 1103515245 * 4294967295 exceeds 2**53, so a plain
 * multiply would lose precision and diverge from the Python loader silently.
 */
function lcgBytes(spec) {
  let state = Number(spec.seed) >>> 0;
  const out = new Uint8Array(Number(spec.length));
  for (let index = 0; index < out.length; index += 1) {
    state = (Math.imul(1103515245, state) + 12345) >>> 0;
    out[index] = (state >>> 16) & 0xff;
  }
  return out;
}

function fixtureData(entry) {
  if (entry.concat) return concatBytes(...entry.concat.map(fixtureData));
  if (entry.lcg) return lcgBytes(entry.lcg);
  if (typeof entry.text === 'string') return encoder.encode(entry.text);
  if (entry.base64 !== undefined) return fromBase64(entry.base64);
  if (entry.repeat) {
    const pattern = fromBase64(entry.repeat.pattern_base64);
    const out = new Uint8Array(entry.repeat.length);
    for (let i = 0; i < out.length; i += 1) out[i] = pattern[i % pattern.length];
    return out;
  }
  throw new Error(`fixture ${fixturePath(entry)} has no content`);
}

function buildTree(spec) {
  const directories = spec.directories_codepoints
    ? spec.directories_codepoints.map((cps) => String.fromCodePoint(...cps))
    : [...(spec.directories ?? [])];
  return {
    name: spec.name,
    directories,
    files: (spec.files ?? []).map((entry) => ({
      path: fixturePath(entry),
      data: fixtureData(entry),
      mtimeNs: entry.mtime_ns,
    })),
  };
}

function uuidBytes(hex) {
  const out = new Uint8Array(16);
  for (let i = 0; i < 16; i += 1) out[i] = parseInt(hex.substr(i * 2, 2), 16);
  return out;
}

function packCase(testCase) {
  return pack(buildTree(FIXTURES.trees[testCase.tree]), testCase.plan, {
    archiveUuid: uuidBytes(testCase.uuid),
    createdNs: testCase.created_ns,
  });
}

const CASES = FIXTURES.cases;
const BYTE_EXACT = CASES.filter((c) => c.byte_exact_across_implementations);

// ---------------------------------------------------------------- forge

/**
 * Assemble an archive from explicit parts, using only the layout primitives.
 *
 * The rejection suite needs archives that are well formed at the frame level and
 * wrong at exactly one semantic level. Going through the writer could not produce
 * those — it refuses to.
 */
async function forge(chunks, objects, options = {}) {
  const uuid = options.uuid ?? new Uint8Array(16).fill(7);
  const pieces = [buildHeader(uuid)];
  let offset = HEADER_SIZE;
  let sequence = 1;
  const chunkMap = {};
  for (const [chunkId, codec, payload, rawSize] of chunks) {
    let header = {
      chunk_id: chunkId,
      raw_size: rawSize,
      codec,
      payload_sha256: await sha256Hex(payload),
    };
    if (options.patchChunkHeader) header = options.patchChunkHeader({ ...header });
    const record = buildRecord('CHNK', header, payload, sequence);
    sequence += 1;
    pieces.push(record.bytes);
    chunkMap[chunkId] = {
      record_offset: offset,
      record_length: record.totalLength,
      payload_offset: offset + record.payloadRelativeOffset,
      payload_length: payload.length,
      raw_size: rawSize,
      codec,
      payload_sha256: await sha256Hex(payload),
    };
    offset += record.totalLength;
  }

  const uuidHex = toHex(uuid);
  let manifest = {
    format: 'ANLA-MVP',
    format_version: '0.1',
    archive_uuid: `${uuidHex.slice(0, 8)}-${uuidHex.slice(8, 12)}-${uuidHex.slice(12, 16)}`
      + `-${uuidHex.slice(16, 20)}-${uuidHex.slice(20, 32)}`,
    created_unix_ns: '0',
    hash_algorithm: 'sha256',
    manifest_encoding: 'canonical-json',
    snapshot_sequence: 1,
    source_name: 'forged',
    plan: { ...DEFAULT_PLAN },
    preservation: {
      lossless: true, decoder_requires_ai: false,
      object_coverage: 'all-selected-objects',
    },
    objects,
    chunks: chunkMap,
    statistics: {
      objects: objects.length,
      files: objects.filter((o) => o.type === 'file').length,
      directories: objects.filter((o) => o.type === 'directory').length,
      unique_chunks: Object.keys(chunkMap).length,
      chunk_references: 0, logical_bytes: 0, stored_payload_bytes: 0,
    },
    auxiliary: { decision_log: [], disposable: true },
  };
  if (options.patchManifest) manifest = options.patchManifest(manifest);

  const payload = canonicalBytes(manifest);
  const hash = await sha256(payload);
  const record = buildRecord('MANF', {
    encoding: 'canonical-json',
    payload_sha256: toHex(hash),
    preservation_required: true,
  }, payload, sequence);
  const manifestOffset = offset;
  pieces.push(record.bytes);
  pieces.push(buildFooter(options.footerManifestOffset ?? manifestOffset,
    record.totalLength, uuid, hash));
  return concatBytes(...pieces);
}

async function oneFileArchive(content = encoder.encode('hello world')) {
  const chunkId = await sha256Hex(content);
  const objects = [{
    type: 'file', path: 'a.txt', size: content.length,
    sha256: chunkId, chunks: [{ id: chunkId, length: content.length }], metadata: {},
  }];
  return { chunks: [[chunkId, 'store', content, content.length]], objects, chunkId };
}

// ---------------------------------------------------------------- reporting

const state = { total: 0, passed: 0, failed: 0, started: 0 };

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function suiteNode(id, title, description) {
  const section = document.createElement('section');
  section.className = 'suite';
  section.id = `suite-${id}`;
  section.innerHTML = `<div class="suite-head"><h3>${escapeHtml(title)}</h3>`
    + `<span class="suite-count" data-count>—</span></div>`
    + `<p class="suite-desc">${escapeHtml(description)}</p>`
    + '<div class="rows"></div>';
  $('#results').appendChild(section);
  return section;
}

function addRow(section, id, label) {
  const row = document.createElement('div');
  row.className = 'trow running';
  row.innerHTML = `<span class="tid">${escapeHtml(id)}</span>`
    + `<span class="tlabel">${escapeHtml(label)}</span>`
    + `<span class="tdetail"></span><span class="tstatus">…</span>`;
  section.querySelector('.rows').appendChild(row);
  return row;
}

function finishRow(row, ok, detail) {
  row.className = `trow ${ok ? 'pass' : 'fail'}`;
  row.querySelector('.tdetail').textContent = detail ?? '';
  row.querySelector('.tstatus').textContent = ok ? t('pass', 'PASS') : t('fail', 'FAIL');
  state.total += 1;
  state[ok ? 'passed' : 'failed'] += 1;
  renderTally();
}

function renderTally() {
  const elapsed = ((performance.now() - state.started) / 1000).toFixed(2);
  $('#tally').textContent =
    `${state.passed} ${t('passed', 'passed')} · ${state.failed} ${t('failed', 'failed')}`
    + ` · ${elapsed}s`;
  $('#tally').className = `badge ${state.failed ? 'bad' : 'ok'}`;
  for (const section of document.querySelectorAll('.suite')) {
    const rows = [...section.querySelectorAll('.trow')];
    const done = rows.filter((r) => !r.classList.contains('running'));
    const bad = rows.filter((r) => r.classList.contains('fail')).length;
    section.querySelector('[data-count]').textContent =
      `${done.length - bad}/${rows.length}`;
    section.querySelector('[data-count]').className =
      `suite-count ${bad ? 'bad' : (done.length === rows.length ? 'ok' : '')}`;
  }
}

/** Yield to the browser so each row paints as it finishes. */
const breathe = () => new Promise((resolve) => setTimeout(resolve, 0));

async function check(section, id, label, body) {
  const row = addRow(section, id, label);
  await breathe();
  try {
    const detail = await body();
    finishRow(row, true, detail ?? '');
  } catch (error) {
    const code = error instanceof AnlaError ? `${error.code}: ` : '';
    finishRow(row, false, `${code}${error.message}`);
    // Keep it in the console too — a reader who wants the stack should have it.
    console.error(`[${id}] ${label}`, error);
  }
  await breathe();
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function expectRefusal(build, expectedCode) {
  let opened = null;
  try {
    opened = await openArchive(await build(), { full: true });
  } catch (error) {
    const code = error instanceof AnlaError ? error.code : 'ERROR';
    assert(code === expectedCode, `refused with ${code}, expected ${expectedCode}`);
    return `${code}`;
  }
  assert(opened === null, 'the decoder accepted it');
  return '';
}

// ---------------------------------------------------------------- suites

async function suiteCrossImplementation() {
  const section = suiteNode('xim', t('suite_xim_t'), t('suite_xim_d'));
  for (const testCase of BYTE_EXACT) {
    await check(section, 'T-XIM-3', `${testCase.id}`, async () => {
      const { bytes } = await packCase(testCase);
      const digest = await sha256Hex(bytes);
      const expected = VECTOR_SHA256[`${testCase.id}.anla`];
      assert(expected !== undefined, 'no committed hash for this case');
      assert(digest === expected,
        `browser produced ${digest.slice(0, 16)}…, Python committed ${expected.slice(0, 16)}…`);
      return `${bytes.length} B · ${digest.slice(0, 16)}…`;
    });
  }
  await check(section, 'T-REP-1', t('row_reproducible'), async () => {
    const testCase = BYTE_EXACT[0];
    const first = await packCase(testCase);
    const second = await packCase(testCase);
    assert(first.bytes.length === second.bytes.length
      && first.bytes.every((b, i) => b === second.bytes[i]), 'two runs differed');
    return `${testCase.id} · ${first.bytes.length} B`;
  });
  await check(section, 'T-REP-2', t('row_uuid_varies'), async () => {
    // Reproducibility is a promise about fixed inputs, not an accident of the
    // writer being stateless: with no uuid supplied, two archives must differ.
    const tree = buildTree(FIXTURES.trees.basic);
    const a = await pack(tree, { compression: 'store' });
    const b = await pack(tree, { compression: 'store' });
    assert(a.manifest.archive_uuid !== b.manifest.archive_uuid,
      'two archives shared a UUID');
    return `${a.manifest.archive_uuid.slice(0, 13)}… ≠ ${b.manifest.archive_uuid.slice(0, 13)}…`;
  });
}

async function suiteChunking() {
  const section = suiteNode('cdc', t('suite_cdc_t'), t('suite_cdc_d'));

  await check(section, 'T-CDC-1', t('row_gear_derived'), async () => {
    // Derived here, from the documented procedure, and compared with the table
    // the implementation is actually using.
    const expected = new Uint32Array(256);
    for (let index = 0; index < 256; index += 1) {
      const digest = await sha256(concatBytes(
        encoder.encode(CDC_GEAR_TABLE_ID), new Uint8Array([0]), new Uint8Array([index])));
      expected[index] = new DataView(digest.buffer, digest.byteOffset).getUint32(0, false);
    }
    assert(GEAR.every((word, index) => word === expected[index]),
      'the gear table does not match its own derivation');
    assert(new Set(GEAR).size === 256, 'the gear table has a collision');
    assert(GEAR_TABLE_DIGEST
      === 'ecdce4099dbb06b791d1255eb242b2ca9a0454541b6d6c376b5df5d17a7e66c2',
      `digest is ${GEAR_TABLE_DIGEST}`);
    return `256 ${t('words')} · ${GEAR_TABLE_DIGEST.slice(0, 16)}…`;
  });

  const profile = normalizeCdcProfile({ min: 1024, avg: 4096, max: 16384 });
  const sample = lcgBytes({ seed: 7, length: 262144 });

  await check(section, 'T-CDC-2', t('row_tiling'), async () => {
    const ranges = cutPoints(sample, profile);
    assert(ranges[0][0] === 0 && ranges[ranges.length - 1][1] === sample.length,
      'the ranges do not span the input');
    for (let i = 1; i < ranges.length; i += 1) {
      assert(ranges[i - 1][1] === ranges[i][0], `gap or overlap at range ${i}`);
    }
    const sizes = ranges.map(([a, b]) => b - a);
    for (const size of sizes.slice(0, -1)) {
      assert(size >= profile.min && size <= profile.max, `chunk of ${size} is out of bounds`);
    }
    const mean = Math.round(sizes.reduce((a, b) => a + b, 0) / sizes.length);
    assert(mean >= profile.avg / 2 && mean <= profile.avg * 2, `mean ${mean}`);
    return `${sizes.length} ${t('chunks_word')} · ${t('mean_word')} ${mean} B`;
  });

  await check(section, 'T-CDC-3', t('row_shift'), async () => {
    const shifted = concatBytes(encoder.encode('INSERTED..'), sample);
    const key = (data, [a, b]) => toHex(data.subarray(a, Math.min(a + 32, b)))
      + ':' + (b - a);
    const before = new Set(cutPoints(sample, profile).map((r) => key(sample, r)));
    const after = cutPoints(shifted, profile).map((r) => key(shifted, r));
    const shared = after.filter((k) => before.has(k)).length;

    const size = profile.avg;
    const fixedBefore = new Set();
    for (let at = 0; at < sample.length; at += size) {
      fixedBefore.add(key(sample, [at, Math.min(at + size, sample.length)]));
    }
    let fixedShared = 0;
    for (let at = 0; at < shifted.length; at += size) {
      if (fixedBefore.has(key(shifted, [at, Math.min(at + size, shifted.length)]))) {
        fixedShared += 1;
      }
    }
    assert(fixedShared === 0, `fixed-size shared ${fixedShared} chunks, expected none`);
    assert(shared >= after.length - 2,
      `content-defined shared only ${shared}/${after.length}`);
    return `${t('cdc_word')} ${shared}/${after.length} · ${t('fixed_word')} `
      + `${fixedShared}/${Math.ceil(shifted.length / size)}`;
  });

  await check(section, 'T-CDC-4', t('row_cdc_saving'), async () => {
    const cdc = CASES.find((c) => c.id === 'cdc-shifted-pair');
    const fixed = CASES.find((c) => c.id === 'fixed-shifted-pair');
    const a = await packCase(cdc);
    const b = await packCase(fixed);
    assert(b.statistics.unique_chunks === b.statistics.chunk_references,
      'the fixed-size case was supposed to deduplicate nothing');
    assert(a.statistics.unique_chunks < a.statistics.chunk_references,
      'the content-defined case deduplicated nothing');
    assert(a.bytes.length < b.bytes.length * 0.7,
      `${a.bytes.length} vs ${b.bytes.length}`);
    const saved = Math.round((1 - a.bytes.length / b.bytes.length) * 100);
    return `${b.bytes.length} B → ${a.bytes.length} B · ${saved}% ${t('smaller_word')}`;
  });

  await check(section, 'T-CDC-5', t('row_reader_unaware'), async () => {
    const { bytes } = await packCase(CASES.find((c) => c.id === 'cdc-shifted-pair'));
    const archive = await openArchive(bytes, { full: true });
    assert(archive.manifest.format_version === '0.1',
      'a content-defined archive should need no version bump');
    assert(archive.verification.status === 'ok', 'it did not verify');
    return `format_version 0.1 · ${archive.verification.verified_chunks} chunks`;
  });
}

async function suiteVectors() {
  const section = suiteNode('frz', t('suite_frz_t'), t('suite_frz_d'));
  const skipped = Object.keys(VECTOR_NOT_BUNDLED);
  if (skipped.length) {
    // Not a pass or a fail: a statement of what this suite did not carry. The
    // byte-exactness suite above packs these cases and checks the same hashes.
    const note = document.createElement('p');
    note.className = 'suite-desc';
    note.textContent = `${t('vectors_not_bundled')}: ${skipped.join(', ')} — `
      + t('vectors_covered_elsewhere');
    section.querySelector('.rows').before(note);
  }
  for (const name of Object.keys(VECTOR_BYTES_BASE64).sort()) {
    const id = name === 'browser-interop-v0.1.anla' ? 'T-ORG-1' : 'T-FRZ-1';
    await check(section, id, name, async () => {
      const bytes = fromBase64(VECTOR_BYTES_BASE64[name]);
      const digest = await sha256Hex(bytes);
      assert(digest === VECTOR_SHA256[name], 'the shipped bytes do not match SHA256SUMS');
      const archive = await openArchive(bytes, { full: true });
      const v = archive.verification;
      assert(v.status === 'ok', 'verification did not report ok');
      return `${v.verified_files} ${t('files_word')} · ${v.verified_chunks} chunks`
        + ` · ${v.logical_bytes} B`;
    });
  }
}

async function suiteRoundTrip() {
  const section = suiteNode('rt', t('suite_rt_t'), t('suite_rt_d'));
  for (const testCase of CASES) {
    await check(section, 'T-RT', testCase.id, async () => {
      const tree = buildTree(FIXTURES.trees[testCase.tree]);
      const { bytes } = await packCase(testCase);
      const archive = await openArchive(bytes, { full: true });
      const globs = testCase.plan.exclude_globs ?? [];
      const expected = tree.files.filter((f) => !globs.some(
        (g) => new RegExp(`^${g.replace(/[.+^${}()|[\]\\]/g, '\\$&')
          .replace(/\*\*/g, '\u0000').replace(/\*/g, '[^/]*')
          .replace(/\u0000/g, '[\\s\\S]*').replace(/\?/g, '[^/]')}$`).test(f.path)));
      assert(archive.verification.verified_files === expected.length,
        `verified ${archive.verification.verified_files}, expected ${expected.length}`);
      for (const file of expected) {
        const restored = archive.read(file.path);
        assert(restored.length === file.data.length
          && restored.every((b, i) => b === file.data[i]),
          `content differs for ${file.path}`);
      }
      return `${expected.length} ${t('files_word')} · ${bytes.length} B`;
    });
  }

  await check(section, 'T-DUP-1', t('row_dedup'), async () => {
    const testCase = CASES.find((c) => c.id === 'duplicate-content');
    const { manifest } = await packCase(testCase);
    const s = manifest.statistics;
    assert(s.unique_chunks < s.chunk_references,
      `${s.unique_chunks} unique of ${s.chunk_references} references — nothing deduplicated`);
    return `${s.unique_chunks} ${t('unique_word')} / ${s.chunk_references} refs`;
  });

  await check(section, 'T-EMP-1', t('row_empty_file'), async () => {
    const { manifest } = await packCase(CASES.find((c) => c.id === 'empty-file'));
    const empty = manifest.objects.find((o) => o.type === 'file' && o.size === 0);
    assert(empty !== undefined, 'no empty file in the fixture');
    assert(empty.chunks.length === 0, 'an empty file referenced a chunk');
    return `${empty.path} · 0 chunks`;
  });

  await check(section, 'T-EMP-2', t('row_empty_archive'), async () => {
    const { bytes, manifest } = await packCase(
      CASES.find((c) => c.id === 'empty-archive'));
    const archive = await openArchive(bytes, { full: true });
    assert(manifest.objects.length === 0, 'the empty archive had objects');
    assert(archive.verification.status === 'ok', 'it did not verify');
    return `${bytes.length} B`;
  });

  await check(section, 'T-BIG-1', t('row_split'), async () => {
    const testCase = CASES.find((c) => c.id === 'split-file');
    const { manifest } = await packCase(testCase);
    const big = manifest.objects.find((o) => o.type === 'file' && o.chunks.length > 1);
    assert(big !== undefined, 'nothing was split');
    const covered = big.chunks.reduce((sum, ref) => sum + ref.length, 0);
    assert(covered === big.size, 'chunk coverage does not add up to the file size');
    return `${big.path} → ${big.chunks.length} chunks of ${testCase.plan.chunk_size} B`;
  });

  await check(section, 'T-UNI-1', t('row_unicode'), async () => {
    const { bytes } = await packCase(CASES.find((c) => c.id === 'unicode-paths'));
    const archive = await openArchive(bytes, { full: true });
    const paths = archive.manifest.objects.map((o) => o.path);
    const nfc = String.fromCodePoint(99, 97, 102, 233, 45, 110, 102, 99, 46, 116, 120, 116);
    const nfd = String.fromCodePoint(99, 97, 102, 101, 769, 45, 110, 102, 100, 46, 116, 120, 116);
    assert(paths.includes(nfc) && paths.includes(nfd),
      'the precomposed/decomposed pair did not survive');
    assert(paths.includes('Sample.TXT') && paths.includes('sample.txt'),
      'the case-only pair did not survive');
    return `${paths.length} ${t('paths_word')} · NFC ≠ NFD · Sample.TXT ≠ sample.txt`;
  });

  await check(section, 'T-AUX-1', t('row_auxiliary'), async () => {
    const { bytes } = await packCase(
      CASES.find((c) => c.id === 'compressible-deflate'));
    const archive = await openArchive(bytes, { full: true });
    const removed = archive.manifest.auxiliary.decision_log.length;
    assert(removed > 0, 'the decision log was empty, so this would prove nothing');

    // Compared against a rewritten archive, not the same manifest twice: an
    // archive compared with itself passes regardless of what stripping did.
    const stripped = await archive.rewriteWithoutAuxiliary();
    assert(stripped.length < bytes.length, 'stripping did not remove anything');
    const rewritten = await openArchive(stripped, { full: true });
    assert(rewritten.manifest.auxiliary.decision_log.length === 0, 'the log survived');
    assert(JSON.stringify(rewritten.manifest.objects)
      === JSON.stringify(archive.manifest.objects)
      && JSON.stringify(rewritten.manifest.chunks)
      === JSON.stringify(archive.manifest.chunks),
      'stripping the intelligence plane touched the preservation plane');
    for (const object of archive.manifest.objects.filter((o) => o.type === 'file')) {
      const a = archive.read(object.path);
      const b = rewritten.read(object.path);
      assert(a.length === b.length && a.every((byte, i) => byte === b[i]),
        `content changed for ${object.path}`);
    }
    return `${bytes.length} → ${stripped.length} B · ${removed} `
      + `${t('decisions_word')} · ${t('extraction_identical')}`;
  });

  await check(section, 'T-AUX-2', t('row_auxiliary_idempotent'), async () => {
    const { bytes } = await packCase(
      CASES.find((c) => c.id === 'compressible-deflate'));
    const once = await (await openArchive(bytes, { full: true })).rewriteWithoutAuxiliary();
    const twice = await (await openArchive(once, { full: true })).rewriteWithoutAuxiliary();
    assert(once.length === twice.length && once.every((b, i) => b === twice[i]),
      'stripping twice differed from stripping once');
    return `${once.length} B`;
  });

  await check(section, 'T-ZIP-1', t('row_zip'), async () => {
    const { bytes } = await packCase(CASES.find((c) => c.id === 'basic-store'));
    const archive = await openArchive(bytes, { full: true });
    const zip = await exportZip(archive);
    assert(zip.length > 22, 'the zip was empty');
    assert(zip[0] === 0x50 && zip[1] === 0x4b, 'that is not a zip');
    return `${zip.length} B`;
  });
}

async function suiteRejections() {
  const section = suiteNode('rej', t('suite_rej_t'), t('suite_rej_d'));
  const valid = async () => {
    const { chunks, objects } = await oneFileArchive();
    return forge(chunks, objects);
  };

  await check(section, 'T-FORGE', t('row_forge'), async () => {
    const archive = await openArchive(await valid(), { full: true });
    const text = new TextDecoder().decode(archive.read('a.txt'));
    assert(text === 'hello world', 'the forge does not produce a valid archive');
    return `${t('row_forge_ok')}`;
  });

  await check(section, 'T-HDR-1', t('row_bad_magic'), () => expectRefusal(async () => {
    const bytes = await valid();
    bytes[3] = 0x42;
    return bytes;
  }, 'ANLA_MANIFEST_INVALID'));

  await check(section, 'T-HDR-2', t('row_header_crc'), () => expectRefusal(async () => {
    const bytes = await valid();
    bytes[20] ^= 0xff;   // inside the UUID, which the header CRC covers
    return bytes;
  }, 'ANLA_INTEGRITY_FAILURE'));

  await check(section, 'T-HDR-3', t('row_version'), () => expectRefusal(async () => {
    const bytes = await valid();
    new DataView(bytes.buffer).setUint16(10, 2, true);
    new DataView(bytes.buffer).setUint32(60, crc32(bytes.subarray(0, 60)), true);
    return bytes;
  }, 'ANLA_MANIFEST_INVALID'));

  await check(section, 'T-FTR-1', t('row_footer_magic'), () => expectRefusal(async () => {
    const bytes = await valid();
    bytes[bytes.length - FOOTER_SIZE] = 0;
    return bytes;
  }, 'ANLA_MANIFEST_INVALID'));

  await check(section, 'T-FTR-2', t('row_footer_crc'), () => expectRefusal(async () => {
    const bytes = await valid();
    bytes[bytes.length - FOOTER_SIZE + 20] ^= 0xff;
    return bytes;
  }, 'ANLA_INTEGRITY_FAILURE'));

  await check(section, 'T-FTR-3', t('row_footer_uuid'), () => expectRefusal(async () => {
    const bytes = await valid();
    const base = bytes.length - FOOTER_SIZE;
    bytes[base + 32] ^= 0xff;
    new DataView(bytes.buffer).setUint32(base + 92,
      crc32(bytes.subarray(base, base + 92)), true);
    return bytes;
  }, 'ANLA_INTEGRITY_FAILURE'));

  await check(section, 'T-FTR-4', t('row_footer_points_wrong'),
    () => expectRefusal(async () => {
      const { chunks, objects } = await oneFileArchive();
      return forge(chunks, objects, { footerManifestOffset: HEADER_SIZE });
    }, 'ANLA_MANIFEST_INVALID'));

  await check(section, 'T-MAN-1', t('row_manifest_hash'), () => expectRefusal(async () => {
    const bytes = await valid();
    const needle = encoder.encode('"source_name":"forged"');
    const at = findBytes(bytes, needle);
    assert(at >= 0, 'could not find the manifest');
    bytes[at + 16] ^= 0x20;
    return bytes;
  }, 'ANLA_INTEGRITY_FAILURE'));

  await check(section, 'T-MAN-2', t('row_other_profile'), () => expectRefusal(async () => {
    const { chunks, objects } = await oneFileArchive();
    return forge(chunks, objects,
      { patchManifest: (m) => ({ ...m, format_version: '0.2' }) });
  }, 'ANLA_UNSUPPORTED_REQUIRED_CAPABILITY'));

  await check(section, 'T-REC-1', t('row_record_crc'), () => expectRefusal(async () => {
    const bytes = await valid();
    const at = findBytes(bytes, encoder.encode('"chunk_id"'));
    bytes[at + 2] ^= 0x20;
    return bytes;
  }, 'ANLA_INTEGRITY_FAILURE'));

  await check(section, 'T-REC-2', t('row_unknown_record'), () => expectRefusal(async () => {
    const bytes = await valid();
    bytes.set(encoder.encode('WHAT'), HEADER_SIZE + 4);
    return bytes;
  }, 'ANLA_MANIFEST_INVALID'));

  await check(section, 'T-CHK-1', t('row_payload_hash'), () => expectRefusal(async () => {
    const bytes = await valid();
    const at = findBytes(bytes, encoder.encode('hello world'));
    bytes[at] = 'H'.charCodeAt(0);
    return bytes;
  }, 'ANLA_INTEGRITY_FAILURE'));

  await check(section, 'T-CHK-2', t('row_content_id'), () => expectRefusal(async () => {
    // A chunk id is a claim about content, not a label.
    const content = encoder.encode('hello world');
    const wrongId = await sha256Hex(encoder.encode('something else entirely'));
    return forge([[wrongId, 'store', content, content.length]], [{
      type: 'file', path: 'a.txt', size: content.length,
      sha256: await sha256Hex(content),
      chunks: [{ id: wrongId, length: content.length }], metadata: {},
    }]);
  }, 'ANLA_INTEGRITY_FAILURE'));

  await check(section, 'T-CHK-3', t('row_descriptor'), () => expectRefusal(async () => {
    const { chunks, objects } = await oneFileArchive();
    return forge(chunks, objects, {
      patchManifest: (m) => {
        const id = Object.keys(m.chunks)[0];
        m.chunks[id].record_length += 1;
        return m;
      },
    });
  }, 'ANLA_INTEGRITY_FAILURE'));

  await check(section, 'T-CHK-4', t('row_unknown_codec'), () => expectRefusal(async () => {
    const content = encoder.encode('hello world');
    const chunkId = await sha256Hex(content);
    return forge([[chunkId, 'brotli', content, content.length]], [{
      type: 'file', path: 'a.txt', size: content.length, sha256: chunkId,
      chunks: [{ id: chunkId, length: content.length }], metadata: {},
    }]);
  }, 'ANLA_UNSUPPORTED_REQUIRED_CAPABILITY'));

  await check(section, 'T-COV-1', t('row_coverage'), () => expectRefusal(async () => {
    const content = encoder.encode('hello world');
    const chunkId = await sha256Hex(content);
    return forge([[chunkId, 'store', content, content.length]], [{
      type: 'file', path: 'a.txt', size: content.length + 5, sha256: chunkId,
      chunks: [{ id: chunkId, length: content.length }], metadata: {},
    }]);
  }, 'ANLA_INTEGRITY_FAILURE'));

  for (const [label, path] of [
    ['..', '../escape.txt'],
    ['/', '/absolute.txt'],
    ['C:', 'C:/windows.txt'],
    ['//', 'a//b.txt'],
    ['NUL', 'with\u0000nul.txt'],
  ]) {
    await check(section, 'T-PTH-1', `${t('row_unsafe_path')}: ${label}`,
      () => expectRefusal(async () => {
        const content = encoder.encode('x');
        const chunkId = await sha256Hex(content);
        return forge([[chunkId, 'store', content, 1]], [{
          type: 'file', path, size: 1, sha256: chunkId,
          chunks: [{ id: chunkId, length: 1 }], metadata: {},
        }]);
      }, 'ANLA_UNSAFE_PATH_OR_OBJECT'));
  }

  await check(section, 'T-PTH-2', t('row_duplicate_path'), () => expectRefusal(async () => {
    const content = encoder.encode('x');
    const chunkId = await sha256Hex(content);
    const entry = {
      type: 'file', path: 'a.txt', size: 1, sha256: chunkId,
      chunks: [{ id: chunkId, length: 1 }], metadata: {},
    };
    return forge([[chunkId, 'store', content, 1]], [entry, { ...entry }]);
  }, 'ANLA_UNSAFE_PATH_OR_OBJECT'));

  await check(section, 'T-PTH-3', t('row_unknown_object'), () => expectRefusal(
    async () => forge([], [{ type: 'symbolic-link', path: 'link', metadata: {} }]),
    'ANLA_UNSUPPORTED_REQUIRED_CAPABILITY'));

  await check(section, 'T-BMB-1', t('row_absurd_size'), () => expectRefusal(async () => {
    const { chunks, objects, chunkId } = await oneFileArchive();
    return forge(chunks, objects, {
      patchManifest: (m) => {
        m.chunks[chunkId].raw_size = 2 ** 40;
        return m;
      },
    });
  }, 'ANLA_RESOURCE_LIMIT_EXCEEDED'));

  await check(section, 'T-BMB-2', t('row_bomb'), async () => {
    // Four megabytes of zeros, declared as one kilobyte. A decoder that buffers
    // the stream and checks the length afterwards allocates all of it first.
    const zeros = new Uint8Array(4 * 1024 * 1024);
    const stream = new CompressionStream('deflate');
    const writer = stream.writable.getWriter();
    writer.write(zeros);
    writer.close();
    const bomb = new Uint8Array(await new Response(stream.readable).arrayBuffer());
    const declared = 1024;
    const fakeId = await sha256Hex(new Uint8Array(declared));
    const detail = await expectRefusal(async () => forge(
      [[fakeId, 'deflate', bomb, declared]], [{
        type: 'file', path: 'bomb.bin', size: declared, sha256: fakeId,
        chunks: [{ id: fakeId, length: declared }], metadata: {},
      }]), 'ANLA_RESOURCE_LIMIT_EXCEEDED');
    return `${bomb.length} B → ${zeros.length} B, ${t('declared_as')} ${declared} B · ${detail}`;
  });

  await check(section, 'T-LIM-1', t('row_truncated'), () => expectRefusal(
    async () => (await valid()).slice(0, 120), 'ANLA_MANIFEST_INVALID'));
}

function findBytes(haystack, needle) {
  outer: for (let i = 0; i <= haystack.length - needle.length; i += 1) {
    for (let j = 0; j < needle.length; j += 1) {
      if (haystack[i + j] !== needle[j]) continue outer;
    }
    return i;
  }
  return -1;
}

// ---------------------------------------------------------------- run

async function run() {
  $('#results').innerHTML = '';
  Object.assign(state, { total: 0, passed: 0, failed: 0, started: performance.now() });
  $('#runButton').disabled = true;
  $('#runButton').textContent = t('running', 'Running…');
  renderTally();
  try {
    await suiteCrossImplementation();
    await suiteChunking();
    await suiteVectors();
    await suiteRoundTrip();
    await suiteRejections();
  } finally {
    $('#runButton').disabled = false;
    $('#runButton').textContent = t('run_again', 'Run again');
    const elapsed = ((performance.now() - state.started) / 1000).toFixed(2);
    $('#verdict').hidden = false;
    $('#verdict').className = `callout ${state.failed ? 'fail' : 'pass'}`;
    $('#verdict').textContent = state.failed
      ? `${state.failed} ${t('verdict_failed')}`
      : `${state.passed} ${t('verdict_passed')} ${elapsed}s.`;
    document.documentElement.dataset.demo = state.failed ? 'fail' : 'pass';
    document.documentElement.dataset.demoPassed = String(state.passed);
    document.documentElement.dataset.demoFailed = String(state.failed);
  }
}

function boot() {
  const crypto = hasNativeCrypto();
  const compression = hasNativeCompression();
  $('#env').textContent = `SHA-256: ${crypto ? t('native') : t('fallback')}`
    + ` · DEFLATE: ${compression ? t('available') : t('store_only')}`
    + ` · ${navigator.hardwareConcurrency ?? '?'} ${t('cores')}`;
  $('#env').className = `badge ${crypto && compression ? 'ok' : ''}`;
  $('#counts').textContent = `${BYTE_EXACT.length} + ${CASES.length} + `
    + `${Object.keys(VECTOR_BYTES_BASE64).length}`;
  $('#runButton').addEventListener('click', run);
  // A visitor should not have to press anything to see whether it works.
  run();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot);
} else {
  boot();
}
