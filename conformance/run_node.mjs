// Conformance driver for the JavaScript reference implementation.
//
//   node conformance/run_node.mjs pack   <outdir>            write one archive per fixture case
//   node conformance/run_node.mjs verify <archive> [...]     verify archives written elsewhere
//   node conformance/run_node.mjs extract <archive> <outdir> verify, then restore
//   node conformance/run_node.mjs selftest                   internal round trip
//
// Every mode prints a single JSON object on stdout, so the pytest suite can
// drive it without parsing prose.

import { readFile, writeFile, mkdir, stat } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

import {
  FORMAT_NAME, FORMAT_VERSION, VERSION,
  pack, openArchive, exportZip, canonical, toHex, sha256Hex,
  hasNativeCrypto, hasNativeCompression,
} from '../web/anla-core.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURES = path.join(HERE, 'fixtures.json');

const encoder = new TextEncoder();

function fromBase64(text) {
  return Uint8Array.from(Buffer.from(text, 'base64'));
}

function repeatPattern(spec) {
  const pattern = fromBase64(spec.pattern_base64);
  const out = new Uint8Array(spec.length);
  for (let i = 0; i < out.length; i += 1) out[i] = pattern[i % pattern.length];
  return out;
}

function fixturePath(entry) {
  if (entry.path_codepoints) return String.fromCodePoint(...entry.path_codepoints);
  return entry.path;
}

/**
 * The pinned LCG from fixtures.json.
 *
 * Math.imul is required: 1103515245 * 4294967295 exceeds 2**53, so a plain
 * multiply would lose precision and diverge from the Python loader silently —
 * which is the one failure mode a shared fixture cannot tolerate.
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
  if (entry.concat) return concatParts(entry.concat.map(fixtureData));
  if (entry.lcg) return lcgBytes(entry.lcg);
  if (typeof entry.text === 'string') return encoder.encode(entry.text);
  if (entry.base64 !== undefined) return fromBase64(entry.base64);
  if (entry.repeat) return repeatPattern(entry.repeat);
  throw new Error(`fixture ${fixturePath(entry)} has no content`);
}

function concatParts(parts) {
  const total = parts.reduce((sum, part) => sum + part.length, 0);
  const out = new Uint8Array(total);
  let at = 0;
  for (const part of parts) { out.set(part, at); at += part.length; }
  return out;
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

async function loadFixtures() {
  return JSON.parse(await readFile(FIXTURES, 'utf8'));
}

function uuidBytes(hex) {
  const out = new Uint8Array(16);
  for (let i = 0; i < 16; i += 1) out[i] = parseInt(hex.substr(i * 2, 2), 16);
  return out;
}

async function cmdPack(outdir) {
  const fixtures = await loadFixtures();
  await mkdir(outdir, { recursive: true });
  const cases = [];
  for (const testCase of fixtures.cases) {
    const tree = buildTree(fixtures.trees[testCase.tree]);
    const { bytes, manifest } = await pack(tree, testCase.plan, {
      archiveUuid: uuidBytes(testCase.uuid),
      createdNs: testCase.created_ns,
    });
    const target = path.join(outdir, `${testCase.id}.js.anla`);
    await writeFile(target, bytes);

    // Reproducibility inside this implementation: the same call twice.
    const again = await pack(tree, testCase.plan, {
      archiveUuid: uuidBytes(testCase.uuid),
      createdNs: testCase.created_ns,
    });
    const selfReproducible = Buffer.compare(Buffer.from(bytes), Buffer.from(again.bytes)) === 0;

    const opened = await openArchive(bytes, { full: true });
    cases.push({
      id: testCase.id,
      file: target,
      bytes: bytes.length,
      sha256: await sha256Hex(bytes),
      self_reproducible: selfReproducible,
      statistics: manifest.statistics,
      verification: opened.verification,
      manifest_sha256: await sha256Hex(encoder.encode(canonical(manifest))),
    });
  }
  return { mode: 'pack', outdir, implementation: 'javascript', cases };
}

async function cmdVerify(files) {
  const results = [];
  for (const file of files) {
    const bytes = new Uint8Array(await readFile(file));
    try {
      const opened = await openArchive(bytes, { full: true });
      const zip = await exportZip(opened);
      const withoutAux = opened.withoutAuxiliary();
      results.push({
        file,
        ok: true,
        summary: opened.summary,
        verification: opened.verification,
        zip_bytes: zip.length,
        auxiliary_stripped_differs: canonical(withoutAux) !== canonical(opened.manifest),
        paths: opened.manifest.objects.map((o) => o.path),
        file_hashes: Object.fromEntries(
          opened.manifest.objects.filter((o) => o.type === 'file').map((o) => [o.path, o.sha256]),
        ),
      });
    } catch (error) {
      results.push({
        file, ok: false, code: error.code ?? 'ERROR', message: error.message,
        details: error.details ?? {},
      });
    }
  }
  return { mode: 'verify', implementation: 'javascript', results };
}

async function cmdExtract(archive, outdir) {
  const bytes = new Uint8Array(await readFile(archive));
  const opened = await openArchive(bytes, { full: true });
  await mkdir(outdir, { recursive: true });
  const written = [];
  // Identity of what this run has already written, so a filesystem that cannot
  // tell two archive paths apart (case folding on Windows, NFC against NFD on
  // macOS) is reported rather than allowed to drop one of the two files.
  const identities = new Map();
  for (const object of opened.manifest.objects) {
    const target = path.join(outdir, object.path);
    if (object.type === 'directory') {
      await mkdir(target, { recursive: true });
      continue;
    }
    await mkdir(path.dirname(target), { recursive: true });
    const existing = await stat(target).catch(() => null);
    if (existing) {
      const collided = identities.get(`${existing.dev}:${existing.ino}`);
      if (collided !== undefined) {
        const error = new Error('two distinct archive paths collide on the target filesystem');
        error.code = 'ANLA_EXTRACTION_FIDELITY_DEGRADED';
        error.details = { paths: [collided, object.path], target };
        throw error;
      }
    }
    const content = opened.read(object.path);
    await writeFile(target, content);
    const after = await stat(target);
    identities.set(`${after.dev}:${after.ino}`, object.path);
    written.push({ path: object.path, bytes: content.length });
  }
  return { mode: 'extract', implementation: 'javascript', destination: outdir, written };
}

async function cmdSelftest() {
  const tree = {
    name: 'selftest',
    directories: ['docs'],
    files: [
      { path: 'docs/readme.txt', data: encoder.encode('ANLA self test\n'), mtimeNs: '1700000000000000000' },
      { path: 'data.bin', data: new Uint8Array([1, 2, 3, 4, 1, 2, 3, 4]) },
      { path: 'empty.txt', data: new Uint8Array(0) },
    ],
  };
  const { bytes, manifest } = await pack(tree, { chunk_size: 4, compression: 'auto' }, {
    archiveUuid: uuidBytes('000102030405060708090a0b0c0d0e0f'),
    createdNs: '1752732000000000000',
  });
  const opened = await openArchive(bytes, { full: true });
  const zip = await exportZip(opened);
  return {
    mode: 'selftest',
    implementation: 'javascript',
    runtime: {
      node: process.version,
      native_crypto: hasNativeCrypto(),
      native_compression: hasNativeCompression(),
      core_version: VERSION,
      format: `${FORMAT_NAME} ${FORMAT_VERSION}`,
    },
    archive_bytes: bytes.length,
    archive_sha256: await sha256Hex(bytes),
    statistics: manifest.statistics,
    verification: opened.verification,
    zip_bytes: zip.length,
    readme: new TextDecoder().decode(opened.read('docs/readme.txt')),
  };
}

async function main() {
  const [mode, ...rest] = process.argv.slice(2);
  let result;
  switch (mode) {
    case 'pack': result = await cmdPack(rest[0] ?? path.join(HERE, 'out')); break;
    case 'verify': result = await cmdVerify(rest); break;
    case 'extract': result = await cmdExtract(rest[0], rest[1]); break;
    case 'selftest': result = await cmdSelftest(); break;
    default:
      process.stderr.write('usage: run_node.mjs pack|verify|extract|selftest …\n');
      process.exit(2);
  }
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}

main().catch((error) => {
  process.stdout.write(`${JSON.stringify({
    ok: false, code: error.code ?? 'ERROR', message: error.message, details: error.details ?? {},
    stack: error.stack,
  }, null, 2)}\n`);
  process.exit(1);
});
