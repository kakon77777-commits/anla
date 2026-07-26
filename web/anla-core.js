// ANLA-MVP v0.1 — JavaScript reference implementation.
//
// Runs unchanged in a browser tab and in Node. It is written against SPEC.md at
// the repository root, not against the Python implementation; the conformance
// suite is what holds the two together.
//
// Everything here is platform primitives only: SubtleCrypto for SHA-256,
// CompressionStream for DEFLATE, TextEncoder for UTF-8. No dependencies, no
// build step, no network. A decoder that needed any of those would defeat the
// point of the format.
//
// Copyright 2026 EVEMISS Technology Co., Ltd. Apache-2.0.

'use strict';

export const FORMAT_NAME = 'ANLA-MVP';
export const FORMAT_VERSION = '0.1';
export const VERSION_MAJOR = 0;
export const VERSION_MINOR = 1;
export const RECORD_VERSION = 1;

export const HEADER_SIZE = 64;
export const RECORD_FRAME_SIZE = 40;
export const FOOTER_SIZE = 96;
export const MAX_RECORD_HEADER = 16 * 1024 * 1024;

export const ARCHIVE_MAGIC = new Uint8Array([0x41, 0x4e, 0x4c, 0x41, 0x0d, 0x0a, 0x1a, 0x0a]);
export const RECORD_MAGIC = new Uint8Array([0x41, 0x4e, 0x4c, 0x52]); // ANLR
export const FOOTER_MAGIC = new Uint8Array([0x41, 0x4e, 0x4c, 0x41, 0x46, 0x54, 0x52, 0x00]);

export const CODEC_STORE = 'store';
export const CODEC_DEFLATE = 'deflate';
export const CODECS = [CODEC_STORE, CODEC_DEFLATE];

export const DEFAULT_LIMITS = Object.freeze({
  maxOutputBytes: 100 * 1024 ** 3,
  maxObjects: 1_000_000,
  maxPathDepth: 256,
  maxNameBytes: 4096,
  maxChunkUncompressed: 64 * 1024 * 1024,
});

const encoder = new TextEncoder();
const decoder = new TextDecoder('utf-8', { fatal: true });

// ---------------------------------------------------------------------------
// errors — codes match anla/errors.py so both CLIs classify failures the same
// ---------------------------------------------------------------------------

export class AnlaError extends Error {
  constructor(code, message, details = {}) {
    super(message);
    this.name = 'AnlaError';
    this.code = code;
    this.details = details;
  }
}

const invalidInput = (m, d) => new AnlaError('ANLA_INVALID_INPUT', m, d);
const manifestInvalid = (m, d) => new AnlaError('ANLA_MANIFEST_INVALID', m, d);
const integrityFailure = (m, d) => new AnlaError('ANLA_INTEGRITY_FAILURE', m, d);
const unsupported = (m, d) => new AnlaError('ANLA_UNSUPPORTED_REQUIRED_CAPABILITY', m, d);
const limitExceeded = (m, d) => new AnlaError('ANLA_RESOURCE_LIMIT_EXCEEDED', m, d);
const unsafeObject = (m, d) => new AnlaError('ANLA_UNSAFE_PATH_OR_OBJECT', m, d);

// ---------------------------------------------------------------------------
// bytes
// ---------------------------------------------------------------------------

export function concatBytes(...parts) {
  let total = 0;
  for (const part of parts) total += part.length;
  const out = new Uint8Array(total);
  let at = 0;
  for (const part of parts) { out.set(part, at); at += part.length; }
  return out;
}

function bytesEqual(a, b) {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i += 1) if (a[i] !== b[i]) return false;
  return true;
}

export function toHex(bytes) {
  let out = '';
  for (const b of bytes) out += b.toString(16).padStart(2, '0');
  return out;
}

export function fromHex(text) {
  if (typeof text !== 'string' || text.length % 2 !== 0 || /[^0-9a-fA-F]/.test(text)) {
    throw invalidInput('not a hex string', { value: String(text).slice(0, 64) });
  }
  const out = new Uint8Array(text.length / 2);
  for (let i = 0; i < out.length; i += 1) out[i] = parseInt(text.substr(i * 2, 2), 16);
  return out;
}

// CRC-32 (ISO-HDLC) — the polynomial zlib and PNG use, not CRC32C.
const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n += 1) {
    let c = n;
    for (let k = 0; k < 8; k += 1) c = (c & 1) ? (0xedb88320 ^ (c >>> 1)) : (c >>> 1);
    table[n] = c >>> 0;
  }
  return table;
})();

export function crc32(bytes) {
  let c = 0xffffffff;
  for (const b of bytes) c = CRC_TABLE[(c ^ b) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function writeU64(view, offset, value) {
  view.setBigUint64(offset, BigInt(value), true);
}

function readU64(view, offset) {
  const value = view.getBigUint64(offset, true);
  // A JavaScript decoder must refuse a 64-bit field it cannot represent
  // exactly rather than round it into a plausible-looking offset.
  if (value > BigInt(Number.MAX_SAFE_INTEGER)) {
    throw limitExceeded('archive field exceeds the safe integer range', { offset });
  }
  return Number(value);
}

// ---------------------------------------------------------------------------
// SHA-256
// ---------------------------------------------------------------------------

const K = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]);

const rotr = (x, n) => (x >>> n) | (x << (32 - n));

// Used when SubtleCrypto is unavailable — an insecure context, for instance a
// page served over plain http on a LAN address. The archive must be readable
// there too, so the format cannot depend on a browser API being present.
export function sha256Software(bytes) {
  const length = bytes.length;
  const padded = Math.ceil((length + 9) / 64) * 64;
  const msg = new Uint8Array(padded);
  msg.set(bytes);
  msg[length] = 0x80;
  const view = new DataView(msg.buffer);
  view.setUint32(padded - 4, (length << 3) >>> 0, false);
  view.setUint32(padded - 8, Math.floor(length / 0x20000000), false);
  const h = new Uint32Array([
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
  ]);
  const w = new Uint32Array(64);
  for (let block = 0; block < padded; block += 64) {
    for (let i = 0; i < 16; i += 1) w[i] = view.getUint32(block + i * 4, false);
    for (let i = 16; i < 64; i += 1) {
      const s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >>> 3);
      const s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >>> 10);
      w[i] = (w[i - 16] + s0 + w[i - 7] + s1) >>> 0;
    }
    let [a, b, c, d, e, f, g, hh] = h;
    for (let i = 0; i < 64; i += 1) {
      const S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
      const ch = (e & f) ^ (~e & g);
      const t1 = (hh + S1 + ch + K[i] + w[i]) >>> 0;
      const S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
      const maj = (a & b) ^ (a & c) ^ (b & c);
      const t2 = (S0 + maj) >>> 0;
      hh = g; g = f; f = e; e = (d + t1) >>> 0;
      d = c; c = b; b = a; a = (t1 + t2) >>> 0;
    }
    h[0] = (h[0] + a) >>> 0; h[1] = (h[1] + b) >>> 0; h[2] = (h[2] + c) >>> 0;
    h[3] = (h[3] + d) >>> 0; h[4] = (h[4] + e) >>> 0; h[5] = (h[5] + f) >>> 0;
    h[6] = (h[6] + g) >>> 0; h[7] = (h[7] + hh) >>> 0;
  }
  const out = new Uint8Array(32);
  const outView = new DataView(out.buffer);
  for (let i = 0; i < 8; i += 1) outView.setUint32(i * 4, h[i], false);
  return out;
}

export async function sha256(bytes) {
  if (globalThis.crypto?.subtle) {
    return new Uint8Array(await globalThis.crypto.subtle.digest('SHA-256', bytes));
  }
  return sha256Software(bytes);
}

export async function sha256Hex(bytes) {
  return toHex(await sha256(bytes));
}

export function hasNativeCrypto() {
  return Boolean(globalThis.crypto?.subtle);
}

export function hasNativeCompression() {
  return typeof CompressionStream !== 'undefined' && typeof DecompressionStream !== 'undefined';
}

// ---------------------------------------------------------------------------
// canonical JSON — SPEC.md section 6
// ---------------------------------------------------------------------------

/** Compare two strings by their UTF-8 bytes, which is also code point order. */
export function compareUtf8(a, b) {
  const x = encoder.encode(a);
  const y = encoder.encode(b);
  const n = Math.min(x.length, y.length);
  for (let i = 0; i < n; i += 1) {
    if (x[i] !== y[i]) return x[i] < y[i] ? -1 : 1;
  }
  return x.length === y.length ? 0 : (x.length < y.length ? -1 : 1);
}

function canonicalString(value) {
  // Reject lone surrogates rather than emit an escape the Python side would
  // refuse to produce: the two writers must agree byte for byte.
  if (/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?:[^\uD800-\uDBFF]|^)[\uDC00-\uDFFF]/.test(value)) {
    throw invalidInput('string contains an unpaired surrogate and cannot be canonicalized');
  }
  return JSON.stringify(value);
}

export function canonical(value) {
  if (value === true) return 'true';
  if (value === false) return 'false';
  if (value === null || value === undefined) {
    throw invalidInput('null is not used by ANLA-MVP v0.1');
  }
  if (typeof value === 'string') return canonicalString(value);
  if (typeof value === 'number') {
    if (!Number.isInteger(value) || !Number.isSafeInteger(value)) {
      throw invalidInput('only safe integers may appear in an archive', { value });
    }
    return String(value);
  }
  if (typeof value === 'bigint') {
    throw invalidInput('carry values beyond 2^53 as decimal strings, not BigInt');
  }
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (typeof value === 'object') {
    const keys = Object.keys(value).sort(compareUtf8);
    return `{${keys.map((k) => `${canonicalString(k)}:${canonical(value[k])}`).join(',')}}`;
  }
  throw invalidInput(`type ${typeof value} has no canonical JSON form`);
}

export function canonicalBytes(value) {
  return encoder.encode(canonical(value));
}

// ---------------------------------------------------------------------------
// exclusion globs — SPEC.md section 8.3
// ---------------------------------------------------------------------------

const GLOB_SPECIAL = new Set('.+^$(){}[]|\\');

export function globToRegExp(glob) {
  let out = '^';
  for (let i = 0; i < glob.length; i += 1) {
    const ch = glob[i];
    if (ch === '*') {
      if (glob[i + 1] === '*') { out += '[\\s\\S]*'; i += 1; } else { out += '[^/]*'; }
    } else if (ch === '?') {
      out += '[^/]';
    } else if (GLOB_SPECIAL.has(ch)) {
      out += `\\${ch}`;
    } else {
      out += ch;
    }
  }
  return new RegExp(`${out}$`);
}

export function matchesAny(path, globs) {
  return (globs || []).some((g) => globToRegExp(g).test(path));
}

// ---------------------------------------------------------------------------
// header, record frame, footer
// ---------------------------------------------------------------------------

export function uuidText(raw) {
  if (raw.length !== 16) throw invalidInput('archive UUID must be 16 bytes', { got: raw.length });
  const h = toHex(raw);
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20, 32)}`;
}

export function randomUuidBytes() {
  const raw = new Uint8Array(16);
  if (globalThis.crypto?.getRandomValues) {
    globalThis.crypto.getRandomValues(raw);
  } else {
    for (let i = 0; i < 16; i += 1) raw[i] = Math.floor(Math.random() * 256);
  }
  raw[6] = (raw[6] & 0x0f) | 0x40;
  raw[8] = (raw[8] & 0x3f) | 0x80;
  return raw;
}

export function buildHeader(archiveUuid) {
  if (archiveUuid.length !== 16) {
    throw invalidInput('archive UUID must be 16 bytes', { got: archiveUuid.length });
  }
  const buf = new Uint8Array(HEADER_SIZE);
  const view = new DataView(buf.buffer);
  buf.set(ARCHIVE_MAGIC, 0);
  view.setUint16(8, VERSION_MAJOR, true);
  view.setUint16(10, VERSION_MINOR, true);
  view.setUint32(12, 0, true);
  buf.set(archiveUuid, 16);
  view.setUint32(60, crc32(buf.subarray(0, 60)), true);
  return buf;
}

export function parseHeader(bytes) {
  if (bytes.length < HEADER_SIZE + FOOTER_SIZE) {
    throw manifestInvalid('archive is smaller than a header plus a footer', { size: bytes.length });
  }
  const head = bytes.subarray(0, HEADER_SIZE);
  const view = new DataView(head.buffer, head.byteOffset, head.byteLength);
  if (!bytesEqual(head.subarray(0, 8), ARCHIVE_MAGIC)) {
    throw manifestInvalid('invalid ANLA bootstrap magic');
  }
  const major = view.getUint16(8, true);
  const minor = view.getUint16(10, true);
  if (major !== VERSION_MAJOR || minor !== VERSION_MINOR) {
    throw manifestInvalid('unsupported ANLA version', { found: `${major}.${minor}` });
  }
  if (crc32(head.subarray(0, 60)) !== view.getUint32(60, true)) {
    throw integrityFailure('bootstrap header CRC mismatch');
  }
  const archiveUuid = head.slice(16, 32);
  return { versionMajor: major, versionMinor: minor, archiveUuid, uuidText: uuidText(archiveUuid) };
}

export function buildRecord(type, header, payload, sequence) {
  if (type.length !== 4) throw invalidInput('record type must be four ASCII bytes', { type });
  const headerBytes = canonicalBytes(header);
  if (headerBytes.length > MAX_RECORD_HEADER) {
    throw invalidInput('record header exceeds 16 MiB', { size: headerBytes.length });
  }
  const frame = new Uint8Array(RECORD_FRAME_SIZE);
  const view = new DataView(frame.buffer);
  frame.set(RECORD_MAGIC, 0);
  frame.set(encoder.encode(type), 4);
  view.setUint16(8, RECORD_VERSION, true);
  view.setUint16(10, 0, true);
  view.setUint32(12, headerBytes.length, true);
  writeU64(view, 16, payload.length);
  writeU64(view, 24, sequence);
  view.setUint32(32, crc32(headerBytes), true);
  view.setUint32(36, 0, true);
  return {
    bytes: concatBytes(frame, headerBytes, payload),
    payloadRelativeOffset: RECORD_FRAME_SIZE + headerBytes.length,
    totalLength: RECORD_FRAME_SIZE + headerBytes.length + payload.length,
  };
}

export function parseRecord(bytes, offset) {
  if (!Number.isSafeInteger(offset) || offset < 0 || offset + RECORD_FRAME_SIZE > bytes.length) {
    throw manifestInvalid('record frame lies outside the archive', { offset });
  }
  const frame = bytes.subarray(offset, offset + RECORD_FRAME_SIZE);
  if (!bytesEqual(frame.subarray(0, 4), RECORD_MAGIC)) {
    throw manifestInvalid('invalid record magic', { offset });
  }
  const view = new DataView(frame.buffer, frame.byteOffset, frame.byteLength);
  const type = String.fromCharCode(...frame.subarray(4, 8));
  const version = view.getUint16(8, true);
  const flags = view.getUint16(10, true);
  const headerLength = view.getUint32(12, true);
  const payloadLength = readU64(view, 16);
  const sequence = readU64(view, 24);
  const expectedCrc = view.getUint32(32, true);
  if (headerLength > MAX_RECORD_HEADER) {
    throw manifestInvalid('record header exceeds 16 MiB', { offset, size: headerLength });
  }
  const end = offset + RECORD_FRAME_SIZE + headerLength + payloadLength;
  if (end > bytes.length) {
    throw manifestInvalid('record extent lies outside the archive',
      { offset, declaredEnd: end, archiveSize: bytes.length });
  }
  const headerBytes = bytes.subarray(offset + RECORD_FRAME_SIZE,
    offset + RECORD_FRAME_SIZE + headerLength);
  if (crc32(headerBytes) !== expectedCrc) {
    throw integrityFailure('record header CRC mismatch', { offset });
  }
  let header;
  try {
    header = JSON.parse(decoder.decode(headerBytes));
  } catch (error) {
    throw manifestInvalid(`record header is not valid UTF-8 JSON: ${error.message}`, { offset });
  }
  if (header === null || typeof header !== 'object' || Array.isArray(header)) {
    throw manifestInvalid('record header is not a JSON object', { offset });
  }
  return {
    offset,
    type,
    version,
    flags,
    header,
    payloadOffset: offset + RECORD_FRAME_SIZE + headerLength,
    payloadLength,
    sequence,
    totalLength: RECORD_FRAME_SIZE + headerLength + payloadLength,
  };
}

export function buildFooter(manifestOffset, manifestLength, archiveUuid, manifestHash) {
  if (manifestHash.length !== 32) {
    throw invalidInput('manifest hash must be 32 bytes', { got: manifestHash.length });
  }
  const buf = new Uint8Array(FOOTER_SIZE);
  const view = new DataView(buf.buffer);
  buf.set(FOOTER_MAGIC, 0);
  view.setUint16(8, VERSION_MAJOR, true);
  view.setUint16(10, VERSION_MINOR, true);
  view.setUint32(12, 0, true);
  writeU64(view, 16, manifestOffset);
  writeU64(view, 24, manifestLength);
  buf.set(archiveUuid, 32);
  buf.set(manifestHash, 48);
  view.setUint32(92, crc32(buf.subarray(0, 92)), true);
  return buf;
}

export function parseFooter(bytes, header) {
  const foot = bytes.subarray(bytes.length - FOOTER_SIZE);
  const view = new DataView(foot.buffer, foot.byteOffset, foot.byteLength);
  if (!bytesEqual(foot.subarray(0, 8), FOOTER_MAGIC)) {
    throw manifestInvalid('invalid ANLA footer magic');
  }
  const major = view.getUint16(8, true);
  const minor = view.getUint16(10, true);
  if (major !== VERSION_MAJOR || minor !== VERSION_MINOR) {
    throw manifestInvalid('unsupported footer version', { found: `${major}.${minor}` });
  }
  if (crc32(foot.subarray(0, 92)) !== view.getUint32(92, true)) {
    throw integrityFailure('footer CRC mismatch');
  }
  if (!bytesEqual(foot.subarray(32, 48), header.archiveUuid)) {
    throw integrityFailure('header and footer disagree about the archive UUID');
  }
  return {
    manifestRecordOffset: readU64(view, 16),
    manifestRecordLength: readU64(view, 24),
    manifestPayloadSha256: foot.slice(48, 80),
  };
}

// ---------------------------------------------------------------------------
// codecs
// ---------------------------------------------------------------------------

async function deflate(raw) {
  const stream = new CompressionStream('deflate');
  const writer = stream.writable.getWriter();
  writer.write(raw);
  writer.close();
  return new Uint8Array(await new Response(stream.readable).arrayBuffer());
}

async function inflate(payload) {
  const stream = new DecompressionStream('deflate');
  const writer = stream.writable.getWriter();
  writer.write(payload);
  writer.close();
  return new Uint8Array(await new Response(stream.readable).arrayBuffer());
}

export async function encodeChunk(raw, compression) {
  if (compression === CODEC_STORE || !hasNativeCompression()) {
    return { codec: CODEC_STORE, payload: raw };
  }
  const compressed = await deflate(raw);
  if (compression === CODEC_DEFLATE) return { codec: CODEC_DEFLATE, payload: compressed };
  if (compression === 'auto') {
    return compressed.length + 8 < raw.length
      ? { codec: CODEC_DEFLATE, payload: compressed }
      : { codec: CODEC_STORE, payload: raw };
  }
  throw invalidInput('unknown compression mode', { mode: compression });
}

export async function decodeChunk(payload, codec, rawSize, maxChunkOutput = null) {
  if (maxChunkOutput !== null && rawSize > maxChunkOutput) {
    throw limitExceeded('chunk declares more raw bytes than the limit allows',
      { declaredRawSize: rawSize, limit: maxChunkOutput });
  }
  if (codec === CODEC_STORE) {
    if (payload.length !== rawSize) {
      throw integrityFailure('stored chunk length mismatch',
        { declared: rawSize, actual: payload.length });
    }
    return payload;
  }
  if (codec !== CODEC_DEFLATE) throw unsupported('unsupported codec', { codec });
  if (!hasNativeCompression()) {
    throw unsupported('this runtime cannot decode DEFLATE streams', { codec });
  }
  const raw = await inflate(payload);
  if (raw.length !== rawSize) {
    throw integrityFailure('decompressed chunk length mismatch',
      { declared: rawSize, actual: raw.length });
  }
  return raw;
}

// ---------------------------------------------------------------------------
// paths — SPEC.md section 9
// ---------------------------------------------------------------------------

export function safePath(path) {
  if (typeof path !== 'string' || path.length === 0) {
    throw unsafeObject('object path must be a non-empty string', { path: String(path) });
  }
  if (path.includes('\0')) throw unsafeObject('object path contains NUL');
  if (path.startsWith('/') || path.startsWith('\\')) {
    throw unsafeObject('object path is absolute or a UNC path', { path });
  }
  if (/^[A-Za-z]:/.test(path)) throw unsafeObject('object path carries a drive letter', { path });
  const parts = path.replaceAll('\\', '/').split('/');
  for (const part of parts) {
    if (part === '' || part === '.' || part === '..') {
      throw unsafeObject('unsafe object path component', { path, component: part });
    }
  }
  return parts.join('/');
}

// ---------------------------------------------------------------------------
// the writer
// ---------------------------------------------------------------------------

export const DEFAULT_PLAN = Object.freeze({
  plan_version: '0.1',
  chunk_size: 1024 * 1024,
  compression: 'auto',
  deflate_level: 6,
  exclude_globs: [],
  preserve_mode: false,
  preserve_mtime: true,
  verification: 'full',
});

export function normalizePlan(plan = {}) {
  const merged = { ...DEFAULT_PLAN, ...plan };
  if (!Number.isSafeInteger(merged.chunk_size) || merged.chunk_size < 1) {
    throw invalidInput('chunk_size must be a positive integer', { chunk_size: merged.chunk_size });
  }
  if (!['auto', CODEC_DEFLATE, CODEC_STORE].includes(merged.compression)) {
    throw invalidInput('unknown compression mode', { mode: merged.compression });
  }
  if (!Number.isInteger(merged.deflate_level) || merged.deflate_level < 0
      || merged.deflate_level > 9) {
    throw invalidInput('deflate_level must be 0..9', { level: merged.deflate_level });
  }
  if (merged.preserve_mode) {
    throw invalidInput('preserve_mode is not implemented by ANLA-MVP v0.1');
  }
  return {
    plan_version: merged.plan_version,
    chunk_size: merged.chunk_size,
    compression: merged.compression,
    deflate_level: merged.deflate_level,
    exclude_globs: [...merged.exclude_globs],
    preserve_mode: false,
    preserve_mtime: Boolean(merged.preserve_mtime),
    verification: merged.verification,
  };
}

function reasonFor(mode, codec) {
  if (mode !== 'auto') return 'forced-by-plan';
  return codec === CODEC_DEFLATE ? 'smaller-representation' : 'compression-not-beneficial';
}

/**
 * Build an archive.
 *
 * @param {{name?: string, files: Array<{path: string, data: Uint8Array, mtimeNs?: (number|bigint|string)}>, directories?: string[]}} tree
 * @param {object} [planInput]
 * @param {{archiveUuid?: Uint8Array, createdNs?: (number|bigint|string), onProgress?: Function}} [options]
 *
 * Passing both archiveUuid and createdNs makes the output byte-exact and
 * reproducible (SPEC.md section 10).
 */
export async function pack(tree, planInput = {}, options = {}) {
  const plan = normalizePlan(planInput);
  const archiveUuid = options.archiveUuid ?? randomUuidBytes();
  const createdNs = options.createdNs ?? (BigInt(Date.now()) * 1000000n);
  const onProgress = options.onProgress;

  const pieces = [buildHeader(archiveUuid)];
  let offset = HEADER_SIZE;
  let sequence = 1;
  let logicalBytes = 0;
  let storedPayloadBytes = 0;
  let chunkReferences = 0;

  const chunks = {};
  const objects = [];
  const decisionLog = [];

  const seenDirs = new Set();
  for (const rawDir of (tree.directories ?? [])) {
    const path = safePath(rawDir);
    if (seenDirs.has(path) || matchesAny(path, plan.exclude_globs)) continue;
    seenDirs.add(path);
    objects.push({ type: 'directory', path, metadata: {} });
  }

  const files = [...(tree.files ?? [])].sort((a, b) => compareUtf8(a.path, b.path));
  let done = 0;
  for (const entry of files) {
    const path = safePath(entry.path);
    if (matchesAny(path, plan.exclude_globs)) continue;
    const data = entry.data;
    logicalBytes += data.length;
    const fileChunks = [];
    for (let start = 0; start < data.length; start += plan.chunk_size) {
      const raw = data.subarray(start, Math.min(data.length, start + plan.chunk_size));
      const chunkId = await sha256Hex(raw);
      chunkReferences += 1;
      if (!Object.prototype.hasOwnProperty.call(chunks, chunkId)) {
        const { codec, payload } = await encodeChunk(raw, plan.compression);
        const payloadSha256 = await sha256Hex(payload);
        const record = buildRecord('CHNK', {
          chunk_id: chunkId,
          raw_size: raw.length,
          codec,
          payload_sha256: payloadSha256,
        }, payload, sequence);
        sequence += 1;
        pieces.push(record.bytes);
        chunks[chunkId] = {
          record_offset: offset,
          record_length: record.totalLength,
          payload_offset: offset + record.payloadRelativeOffset,
          payload_length: payload.length,
          raw_size: raw.length,
          codec,
          payload_sha256: payloadSha256,
        };
        decisionLog.push({
          chunk_id: chunkId,
          raw_size: raw.length,
          stored_size: payload.length,
          codec,
          reason: reasonFor(plan.compression, codec),
        });
        offset += record.totalLength;
        storedPayloadBytes += payload.length;
      }
      fileChunks.push({ id: chunkId, length: raw.length });
    }

    const metadata = {};
    if (plan.preserve_mtime && entry.mtimeNs !== undefined && entry.mtimeNs !== null) {
      metadata.mtime_ns = BigInt(entry.mtimeNs).toString();
    }
    objects.push({
      type: 'file',
      path,
      size: data.length,
      sha256: await sha256Hex(data),
      chunks: fileChunks,
      metadata,
    });
    done += 1;
    if (onProgress) onProgress({ done, total: files.length, path });
  }

  objects.sort((a, b) => compareUtf8(a.path, b.path) || compareUtf8(a.type, b.type));

  const manifest = {
    format: FORMAT_NAME,
    format_version: FORMAT_VERSION,
    archive_uuid: uuidText(archiveUuid),
    created_unix_ns: BigInt(createdNs).toString(),
    hash_algorithm: 'sha256',
    manifest_encoding: 'canonical-json',
    snapshot_sequence: 1,
    source_name: tree.name ?? 'workspace',
    plan,
    preservation: {
      lossless: true,
      decoder_requires_ai: false,
      object_coverage: 'all-selected-objects',
    },
    objects,
    chunks,
    statistics: {
      objects: objects.length,
      files: objects.filter((o) => o.type === 'file').length,
      directories: objects.filter((o) => o.type === 'directory').length,
      unique_chunks: Object.keys(chunks).length,
      chunk_references: chunkReferences,
      logical_bytes: logicalBytes,
      stored_payload_bytes: storedPayloadBytes,
    },
    auxiliary: { decision_log: decisionLog, disposable: true },
  };

  const manifestPayload = canonicalBytes(manifest);
  const manifestHash = await sha256(manifestPayload);
  const manifestRecord = buildRecord('MANF', {
    encoding: 'canonical-json',
    payload_sha256: toHex(manifestHash),
    preservation_required: true,
  }, manifestPayload, sequence);
  const manifestOffset = offset;
  pieces.push(manifestRecord.bytes);
  offset += manifestRecord.totalLength;
  pieces.push(buildFooter(manifestOffset, manifestRecord.totalLength, archiveUuid, manifestHash));

  const bytes = concatBytes(...pieces);
  return { bytes, manifest, statistics: manifest.statistics };
}

// ---------------------------------------------------------------------------
// the reader
// ---------------------------------------------------------------------------

const HEX64 = /^[0-9a-f]{64}$/;

function asInt(value, field) {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0) {
    throw manifestInvalid(`${field} must be a non-negative safe integer`,
      { got: String(value).slice(0, 64) });
  }
  return value;
}

/**
 * Open and verify an archive.
 *
 * @param {Uint8Array} input
 * @param {{full?: boolean, limits?: object}} [options]
 */
export async function openArchive(input, options = {}) {
  const full = options.full ?? true;
  const limits = { ...DEFAULT_LIMITS, ...(options.limits ?? {}) };
  const bytes = input instanceof Uint8Array ? input : new Uint8Array(input);

  const header = parseHeader(bytes);
  const footer = parseFooter(bytes, header);

  const manifestRecord = parseRecord(bytes, footer.manifestRecordOffset);
  if (manifestRecord.type !== 'MANF') {
    throw manifestInvalid('footer does not point at a MANF record', { found: manifestRecord.type });
  }
  if (manifestRecord.totalLength !== footer.manifestRecordLength) {
    throw manifestInvalid('manifest record length disagrees with the footer');
  }
  const manifestPayload = bytes.subarray(manifestRecord.payloadOffset,
    manifestRecord.payloadOffset + manifestRecord.payloadLength);
  if (!bytesEqual(await sha256(manifestPayload), footer.manifestPayloadSha256)) {
    throw integrityFailure('manifest SHA-256 does not match the footer');
  }
  let manifest;
  try {
    manifest = JSON.parse(decoder.decode(manifestPayload));
  } catch (error) {
    throw manifestInvalid(`manifest is not valid UTF-8 JSON: ${error.message}`);
  }
  if (manifest === null || typeof manifest !== 'object' || Array.isArray(manifest)) {
    throw manifestInvalid('manifest is not a JSON object');
  }
  if (manifest.format !== FORMAT_NAME || manifest.format_version !== FORMAT_VERSION) {
    throw unsupported('archive declares a different format profile',
      { format: manifest.format, format_version: manifest.format_version });
  }
  if (manifest.archive_uuid !== header.uuidText) {
    throw integrityFailure('manifest UUID does not match the bootstrap header');
  }
  for (const member of ['objects', 'chunks', 'statistics', 'preservation', 'plan']) {
    if (!(member in manifest)) {
      throw manifestInvalid(`manifest is missing required member: ${member}`);
    }
  }
  if (!Array.isArray(manifest.objects) || typeof manifest.chunks !== 'object'
      || manifest.chunks === null || Array.isArray(manifest.chunks)) {
    throw manifestInvalid('manifest objects must be an array and chunks an object');
  }
  if (manifest.objects.length > limits.maxObjects) {
    throw limitExceeded('archive declares more objects than the limit allows',
      { objects: manifest.objects.length, limit: limits.maxObjects });
  }

  const chunkCache = new Map();
  let verifiedChunks = 0;
  let verifiedFiles = 0;
  let declaredRaw = 0;

  for (const [chunkId, descriptor] of Object.entries(manifest.chunks)) {
    if (!HEX64.test(chunkId)) {
      throw manifestInvalid('chunk id is not lowercase 64-hex', { chunkId: chunkId.slice(0, 80) });
    }
    if (descriptor === null || typeof descriptor !== 'object' || Array.isArray(descriptor)) {
      throw manifestInvalid('chunk descriptor is not an object', { chunkId });
    }
    for (const key of ['record_offset', 'record_length', 'payload_offset', 'payload_length',
      'raw_size', 'codec', 'payload_sha256']) {
      if (!(key in descriptor)) {
        throw manifestInvalid(`chunk descriptor is missing ${key}`, { chunkId });
      }
    }
    if (!CODECS.includes(descriptor.codec)) {
      throw unsupported('unsupported codec', { codec: descriptor.codec, chunkId });
    }
    const rawSize = asInt(descriptor.raw_size, 'raw_size');
    if (rawSize > limits.maxChunkUncompressed) {
      throw limitExceeded('chunk exceeds the per-chunk size limit',
        { chunkId, rawSize, limit: limits.maxChunkUncompressed });
    }
    declaredRaw += rawSize;
    if (declaredRaw > limits.maxOutputBytes) {
      throw limitExceeded('archive declares more raw bytes than the limit allows',
        { declared: declaredRaw, limit: limits.maxOutputBytes });
    }

    const record = parseRecord(bytes, asInt(descriptor.record_offset, 'record_offset'));
    if (record.type !== 'CHNK') {
      throw manifestInvalid('chunk descriptor points at a non-CHNK record',
        { chunkId, found: record.type });
    }
    if (record.totalLength !== asInt(descriptor.record_length, 'record_length')) {
      throw integrityFailure('chunk record length disagrees with the descriptor', { chunkId });
    }
    if (record.header.chunk_id !== chunkId || record.header.codec !== descriptor.codec
        || record.header.raw_size !== rawSize) {
      throw integrityFailure('chunk record header disagrees with the descriptor', { chunkId });
    }
    if (record.payloadOffset !== asInt(descriptor.payload_offset, 'payload_offset')
        || record.payloadLength !== asInt(descriptor.payload_length, 'payload_length')) {
      throw integrityFailure('chunk payload extent disagrees with the descriptor', { chunkId });
    }

    const payload = bytes.subarray(record.payloadOffset,
      record.payloadOffset + record.payloadLength);
    if (await sha256Hex(payload) !== descriptor.payload_sha256) {
      throw integrityFailure('stored chunk payload hash mismatch', { chunkId });
    }
    if (full) {
      const raw = await decodeChunk(payload, descriptor.codec, rawSize,
        limits.maxChunkUncompressed);
      if (await sha256Hex(raw) !== chunkId) {
        throw integrityFailure('raw chunk hash does not match its content id', { chunkId });
      }
      chunkCache.set(chunkId, raw);
      verifiedChunks += 1;
    }
  }

  const seen = new Set();
  let logical = 0;
  for (const object of manifest.objects) {
    if (object === null || typeof object !== 'object' || Array.isArray(object)) {
      throw manifestInvalid('object entry is not an object');
    }
    const path = safePath(object.path);
    if (path !== object.path) {
      throw unsafeObject('object path is not stored in normalized form', { path: object.path });
    }
    if (encoder.encode(path).length > limits.maxNameBytes) {
      throw limitExceeded('object path exceeds the name length limit', { path });
    }
    if (path.split('/').length > limits.maxPathDepth) {
      throw limitExceeded('object path exceeds the depth limit', { path });
    }
    if (seen.has(path)) throw unsafeObject('duplicate object path', { path });
    seen.add(path);

    if (object.type === 'directory') continue;
    if (object.type !== 'file') {
      throw unsupported('unsupported object type', { type: object.type, path });
    }

    const size = asInt(object.size, 'size');
    if (!Array.isArray(object.chunks)) {
      throw manifestInvalid('file object has no chunk reference list', { path });
    }
    let length = 0;
    const parts = [];
    for (const ref of object.chunks) {
      if (ref === null || typeof ref !== 'object' || !('id' in ref) || !('length' in ref)) {
        throw manifestInvalid('malformed chunk reference', { path });
      }
      const descriptor = Object.prototype.hasOwnProperty.call(manifest.chunks, ref.id)
        ? manifest.chunks[ref.id] : undefined;
      if (!descriptor) {
        throw manifestInvalid('chunk reference points at an unknown chunk',
          { path, chunkId: ref.id });
      }
      if (descriptor.raw_size !== asInt(ref.length, 'length')) {
        throw integrityFailure('chunk reference length disagrees with the chunk',
          { path, chunkId: ref.id });
      }
      length += descriptor.raw_size;
      if (full) parts.push(chunkCache.get(ref.id));
    }
    if (length !== size) {
      throw integrityFailure('chunk coverage does not add up to the file size',
        { path, covered: length, size });
    }
    logical += size;
    if (logical > limits.maxOutputBytes) {
      throw limitExceeded('archive restores more bytes than the limit allows',
        { declared: logical, limit: limits.maxOutputBytes });
    }
    if (full) {
      const content = concatBytes(...parts);
      if (await sha256Hex(content) !== object.sha256) {
        throw integrityFailure('file content hash mismatch', { path });
      }
      verifiedFiles += 1;
    }
  }

  const statistics = manifest.statistics ?? {};
  return {
    bytes,
    manifest,
    chunkCache,
    header,
    footer,
    fullVerification: full,
    summary: {
      archive_uuid: header.uuidText,
      archive_bytes: bytes.length,
      format: manifest.format,
      format_version: manifest.format_version,
      source_name: manifest.source_name,
      created_unix_ns: manifest.created_unix_ns,
      hash_algorithm: manifest.hash_algorithm,
      snapshot_sequence: manifest.snapshot_sequence,
      decoder_requires_ai: manifest.preservation?.decoder_requires_ai,
      ...statistics,
    },
    verification: {
      status: 'ok',
      mode: full ? 'full' : 'quick',
      verified_chunks: verifiedChunks,
      verified_files: verifiedFiles,
      logical_bytes: logical,
    },
    /** One file's verified content. */
    read(path) {
      if (!full) throw integrityFailure('archive was opened without full verification');
      const object = manifest.objects.find((o) => o.type === 'file' && o.path === path);
      if (!object) throw manifestInvalid('no such object in the archive', { path });
      return concatBytes(...object.chunks.map((ref) => chunkCache.get(ref.id)));
    },
    /** The manifest with the intelligence plane emptied — see SPEC.md 8.5. */
    withoutAuxiliary() {
      return { ...manifest, auxiliary: { decision_log: [], disposable: true } };
    },
  };
}

// ---------------------------------------------------------------------------
// ZIP export — the interchange format, not the archival one
// ---------------------------------------------------------------------------

function dosDateTime(mtimeNs) {
  let ms = 315532800000; // 1980-01-01T00:00:00Z, the DOS epoch
  if (mtimeNs !== undefined && mtimeNs !== null) {
    const candidate = Number(BigInt(mtimeNs) / 1000000n);
    if (Number.isFinite(candidate) && candidate > ms) ms = candidate;
  }
  const d = new Date(ms);
  return {
    date: (((d.getUTCFullYear() - 1980) & 0x7f) << 9) | ((d.getUTCMonth() + 1) << 5)
      | d.getUTCDate(),
    time: (d.getUTCHours() << 11) | (d.getUTCMinutes() << 5) | Math.floor(d.getUTCSeconds() / 2),
  };
}

/** Export a verified archive as an uncompressed (stored) ZIP. */
export async function exportZip(opened) {
  const locals = [];
  const centrals = [];
  let offset = 0;
  for (const object of opened.manifest.objects) {
    const isDir = object.type === 'directory';
    const name = isDir ? `${object.path}/` : object.path;
    const nameBytes = encoder.encode(name);
    const content = isDir ? new Uint8Array(0) : opened.read(object.path);
    const { date, time } = dosDateTime(object.metadata?.mtime_ns);
    const crc = crc32(content);

    const local = new Uint8Array(30 + nameBytes.length);
    const lv = new DataView(local.buffer);
    lv.setUint32(0, 0x04034b50, true);
    lv.setUint16(4, 20, true);
    lv.setUint16(6, 0x0800, true); // UTF-8 names
    lv.setUint16(8, 0, true); // stored
    lv.setUint16(10, time, true);
    lv.setUint16(12, date, true);
    lv.setUint32(14, crc, true);
    lv.setUint32(18, content.length, true);
    lv.setUint32(22, content.length, true);
    lv.setUint16(26, nameBytes.length, true);
    local.set(nameBytes, 30);
    locals.push(local, content);

    const central = new Uint8Array(46 + nameBytes.length);
    const cv = new DataView(central.buffer);
    cv.setUint32(0, 0x02014b50, true);
    cv.setUint16(4, 20, true);
    cv.setUint16(6, 20, true);
    cv.setUint16(8, 0x0800, true);
    cv.setUint16(10, 0, true);
    cv.setUint16(12, time, true);
    cv.setUint16(14, date, true);
    cv.setUint32(16, crc, true);
    cv.setUint32(20, content.length, true);
    cv.setUint32(24, content.length, true);
    cv.setUint16(28, nameBytes.length, true);
    cv.setUint32(38, isDir ? 0x10 : 0, true);
    cv.setUint32(42, offset, true);
    central.set(nameBytes, 46);
    centrals.push(central);

    offset += local.length + content.length;
  }
  const centralBytes = concatBytes(...centrals);
  const end = new Uint8Array(22);
  const ev = new DataView(end.buffer);
  ev.setUint32(0, 0x06054b50, true);
  ev.setUint16(8, centrals.length, true);
  ev.setUint16(10, centrals.length, true);
  ev.setUint32(12, centralBytes.length, true);
  ev.setUint32(16, offset, true);
  return concatBytes(...locals, centralBytes, end);
}

export const VERSION = '0.1.0';
