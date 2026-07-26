// Workbench UI. All archive work happens in web/anla-core.js — the same file the
// conformance suite runs under Node — so what this page produces is what the
// tested reference implementation produces.
//
// Every user-visible string comes from window.ANLA_I18N, which the build injects
// per language. No string literals for humans live in here.

import {
  DEFAULT_PLAN, FORMAT_NAME, FORMAT_VERSION,
  pack, openArchive, exportZip, canonical, matchesAny,
  hasNativeCrypto, hasNativeCompression, safePath,
} from './anla-core.js';

const T = globalThis.ANLA_I18N ?? {};
const t = (key, fallback = '') => (T[key] ?? fallback);
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const state = { files: [], directories: [], name: 'workspace', built: null, opened: null };

// ---------------------------------------------------------------- utilities

function formatBytes(n) {
  if (!Number.isFinite(n)) return '—';
  const units = ['B', 'KiB', 'MiB', 'GiB'];
  let value = n;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) { value /= 1024; index += 1; }
  return `${index === 0 ? value : value.toFixed(value < 10 ? 2 : 1)} ${units[index]}`;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

let toastTimer = null;
function toast(message, isError = false) {
  const node = $('#toast');
  node.textContent = message;
  node.className = `toast${isError ? ' error' : ''}`;
  node.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { node.hidden = true; }, isError ? 6000 : 3200);
}

function busy(on, title = '', detail = '') {
  const node = $('#busy');
  node.hidden = !on;
  if (on) {
    $('#busyTitle').textContent = title;
    $('#busyDetail').textContent = detail;
  }
}

function download(bytes, filename, type = 'application/octet-stream') {
  const url = URL.createObjectURL(new Blob([bytes], { type }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

function metric(label, value) {
  return `<div class="summary"><span>${escapeHtml(label)}</span>`
    + `<strong>${escapeHtml(value)}</strong></div>`;
}

function describeError(error) {
  const detail = error?.details && Object.keys(error.details).length
    ? ` (${Object.entries(error.details).map(([k, v]) => `${k}=${v}`).join(', ')})`
    : '';
  return `${error?.code ? `${error.code}: ` : ''}${error?.message ?? error}${detail}`;
}

// ---------------------------------------------------------------- plan

function currentPlan() {
  return {
    ...DEFAULT_PLAN,
    chunk_size: Number($('#chunkSize').value),
    compression: $('#compression').value,
    deflate_level: Number($('#deflateLevel').value),
    exclude_globs: $('#excludeGlobs').value.split(/\r?\n/).map((s) => s.trim()).filter(Boolean),
    preserve_mtime: $('#preserveMtime').checked,
  };
}

// ---------------------------------------------------------------- sources

function mapFileList(list) {
  const entries = [];
  for (const file of list) {
    const raw = (file.webkitRelativePath || file.name).replaceAll('\\', '/');
    if (!raw || raw.endsWith('/')) continue;
    entries.push({ file, parts: raw.split('/').filter(Boolean) });
  }
  // Paths are stored relative to the selected folder, with its name carried in
  // source_name — the same shape the Python collect_tree produces. Keeping the
  // root in every path would also mean an exclusion glob like `.git/**` matched
  // nothing, which is a trap rather than a feature.
  const roots = new Set(entries.filter((e) => e.parts.length > 1).map((e) => e.parts[0]));
  const root = roots.size === 1 && entries.every((e) => e.parts.length > 1)
    ? [...roots][0] : null;

  const files = [];
  const directories = new Set();
  for (const entry of entries) {
    const parts = root ? entry.parts.slice(1) : entry.parts;
    if (!parts.length) continue;
    for (let i = 1; i < parts.length; i += 1) directories.add(parts.slice(0, i).join('/'));
    files.push({ file: entry.file, path: parts.join('/') });
  }
  state.files = files;
  state.directories = [...directories];
  state.name = root || (files.length === 1 ? files[0].path.replace(/\.[^.]+$/, '') : 'workspace');
  renderSources();
}

async function nativePicker() {
  if (!window.showDirectoryPicker) {
    toast(t('picker_unsupported'), true);
    return;
  }
  try {
    const handle = await window.showDirectoryPicker({ mode: 'read' });
    const files = [];
    const directories = new Set();
    const walk = async (dir, prefix) => {
      for await (const entry of dir.values()) {
        const path = prefix ? `${prefix}/${entry.name}` : entry.name;
        if (entry.kind === 'directory') {
          directories.add(path);
          await walk(entry, path);
        } else {
          files.push({ file: await entry.getFile(), path });
        }
      }
    };
    await walk(handle, '');
    state.files = files;
    state.directories = [...directories];
    state.name = handle.name || 'workspace';
    renderSources();
  } catch (error) {
    if (error?.name !== 'AbortError') toast(describeError(error), true);
  }
}

function renderSources() {
  const plan = currentPlan();
  const kept = state.files.filter((f) => !matchesAny(f.path, plan.exclude_globs));
  const size = kept.reduce((total, f) => total + f.file.size, 0);
  $('#srcFiles').textContent = String(kept.length);
  $('#srcDirs').textContent = String(
    state.directories.filter((d) => !matchesAny(d, plan.exclude_globs)).length);
  $('#srcSize').textContent = formatBytes(size);
  $('#srcRoot').textContent = state.name || '—';
  $('#archiveName').value = `${(state.name || 'workspace').replace(/[^\w.\-]+/g, '-')}.anla`;

  const list = $('#sourceList');
  if (!kept.length) {
    list.hidden = true;
    list.innerHTML = '';
  } else {
    list.hidden = false;
    const shown = kept.slice(0, 400);
    list.innerHTML = shown.map((f) => `<div>${escapeHtml(f.path)} · ${formatBytes(f.file.size)}`
      + '</div>').join('')
      + (kept.length > shown.length
        ? `<div>… ${kept.length - shown.length} ${t('more_files')}</div>` : '');
  }
  $('#buildButton').disabled = kept.length === 0;
  $('#buildStatus').textContent = kept.length
    ? t('ready_to_build') : t('waiting_for_selection');
}

function clearSources() {
  state.files = [];
  state.directories = [];
  state.name = 'workspace';
  $('#sourceInput').value = '';
  $('#buildResult').hidden = true;
  renderSources();
}

// ---------------------------------------------------------------- build

async function doBuild() {
  const plan = currentPlan();
  busy(true, t('busy_build_title'), t('busy_build_detail'));
  try {
    const files = [];
    for (const entry of state.files) {
      files.push({
        path: safePath(entry.path),
        data: new Uint8Array(await entry.file.arrayBuffer()),
        mtimeNs: BigInt(entry.file.lastModified) * 1000000n,
      });
    }
    const tree = { name: state.name, directories: state.directories, files };
    const result = await pack(tree, plan);
    // Verify from the bytes we are about to hand over, not from memory.
    const verified = await openArchive(result.bytes, { full: true });
    state.built = { ...result, verified };

    const stats = result.statistics;
    const ratio = stats.logical_bytes
      ? (result.bytes.length / stats.logical_bytes) : 0;
    $('#buildMetrics').innerHTML = [
      metric(t('m_files'), stats.files),
      metric(t('m_dirs'), stats.directories),
      metric(t('m_logical'), formatBytes(stats.logical_bytes)),
      metric(t('m_archive'), formatBytes(result.bytes.length)),
      metric(t('m_chunks'), `${stats.unique_chunks} / ${stats.chunk_references}`),
      metric(t('m_stored'), formatBytes(stats.stored_payload_bytes)),
      metric(t('m_ratio'), ratio ? ratio.toFixed(3) : '—'),
      metric(t('m_verified'), `${verified.verification.verified_files} ✓`),
    ].join('');
    $('#buildReport').textContent = JSON.stringify({
      summary: verified.summary,
      verification: verified.verification,
      plan: result.manifest.plan,
      preservation: result.manifest.preservation,
      decision_log_entries: result.manifest.auxiliary.decision_log.length,
      codecs: [...new Set(Object.values(result.manifest.chunks).map((c) => c.codec))],
    }, null, 2);
    $('#buildResult').hidden = false;
    $('#buildStatus').textContent = t('build_done');
    toast(t('build_ok'));
  } catch (error) {
    $('#buildStatus').textContent = t('build_failed');
    toast(describeError(error), true);
    console.error(error);
  } finally {
    busy(false);
  }
}

async function showPlan() {
  const plan = currentPlan();
  const preview = {
    plan,
    source_name: state.name,
    candidate_files: state.files.filter((f) => !matchesAny(f.path, plan.exclude_globs)).length,
    candidate_bytes: state.files
      .filter((f) => !matchesAny(f.path, plan.exclude_globs))
      .reduce((total, f) => total + f.file.size, 0),
    writer: `${FORMAT_NAME} ${FORMAT_VERSION}`,
    note: t('plan_note'),
  };
  $('#buildReport').textContent = canonical(preview.plan) + '\n\n'
    + JSON.stringify(preview, null, 2);
  $('#buildMetrics').innerHTML = '';
  $('#buildResult').hidden = false;
  $('#buildResult').querySelector('.ok strong').textContent = t('plan_preview');
}

// ---------------------------------------------------------------- open

async function doOpen(file) {
  busy(true, t('busy_open_title'), t('busy_open_detail'));
  try {
    const bytes = new Uint8Array(await file.arrayBuffer());
    const opened = await openArchive(bytes, { full: true });
    state.opened = { ...opened, filename: file.name };
    renderOpened();
    toast(t('open_ok'));
  } catch (error) {
    $('#inspectResult').hidden = true;
    toast(describeError(error), true);
    console.error(error);
  } finally {
    busy(false);
  }
}

function renderOpened() {
  const opened = state.opened;
  const s = opened.summary;
  $('#inspectMetrics').innerHTML = [
    metric(t('m_files'), s.files),
    metric(t('m_dirs'), s.directories),
    metric(t('m_logical'), formatBytes(s.logical_bytes)),
    metric(t('m_archive'), formatBytes(s.archive_bytes)),
    metric(t('m_chunks'), `${s.unique_chunks} / ${s.chunk_references}`),
    metric(t('m_format'), `${s.format} ${s.format_version}`),
    metric(t('m_uuid'), s.archive_uuid.slice(0, 13) + '…'),
    metric(t('m_needs_ai'), String(s.decoder_requires_ai)),
  ].join('');
  $('#inspectReport').textContent = JSON.stringify({
    verification: opened.verification,
    summary: opened.summary,
    plan: opened.manifest.plan,
    preservation: opened.manifest.preservation,
    auxiliary: {
      disposable: opened.manifest.auxiliary?.disposable,
      decision_log_entries: opened.manifest.auxiliary?.decision_log?.length ?? 0,
    },
  }, null, 2);
  $('#inspectResult').hidden = false;
  renderObjects();
}

function renderObjects() {
  if (!state.opened) return;
  const query = $('#objectSearch').value.trim().toLowerCase();
  const rows = state.opened.manifest.objects
    .filter((o) => !query || o.path.toLowerCase().includes(query))
    .slice(0, 600)
    .map((o) => `<div class="row"><span class="p">${escapeHtml(o.path)}</span>`
      + `<span class="s">${o.type === 'directory' ? t('dir_label') : formatBytes(o.size)}</span>`
      + `<span class="h">${o.sha256 ? escapeHtml(o.sha256.slice(0, 12)) : ''}</span></div>`);
  $('#objectList').innerHTML = rows.join('') || `<div class="row"><span class="p">${
    escapeHtml(t('no_matches'))}</span></div>`;
}

async function downloadZip(source, filename) {
  busy(true, t('busy_zip_title'), t('busy_zip_detail'));
  try {
    const zip = await exportZip(source);
    download(zip, filename, 'application/zip');
    toast(t('zip_ok'));
  } catch (error) {
    toast(describeError(error), true);
  } finally {
    busy(false);
  }
}

// ---------------------------------------------------------------- wiring

function setupDrop(zone, input, handler) {
  ['dragenter', 'dragover'].forEach((type) => zone.addEventListener(type, (event) => {
    event.preventDefault();
    zone.classList.add('over');
  }));
  ['dragleave', 'drop'].forEach((type) => zone.addEventListener(type, (event) => {
    event.preventDefault();
    zone.classList.remove('over');
  }));
  zone.addEventListener('drop', (event) => {
    const files = [...(event.dataTransfer?.files ?? [])];
    if (files.length) handler(files);
  });
  input.addEventListener('change', () => {
    if (input.files?.length) handler([...input.files]);
  });
}

function boot() {
  $$('.tab').forEach((button) => {
    button.addEventListener('click', () => {
      $$('.tab').forEach((other) => other.classList.toggle('active', other === button));
      $$('.panel').forEach((panel) => panel.classList.toggle(
        'active', panel.id === `wb-${button.dataset.panel}`));
    });
  });

  setupDrop($('#sourceDrop'), $('#sourceInput'), mapFileList);
  setupDrop($('#archiveDrop'), $('#archiveInput'), (files) => doOpen(files[0]));

  $('#nativePicker').addEventListener('click', (event) => {
    event.preventDefault();
    event.stopPropagation();
    nativePicker();
  });
  $('#clearSource').addEventListener('click', clearSources);
  $('#buildButton').addEventListener('click', doBuild);
  $('#showPlan').addEventListener('click', showPlan);
  ['#compression', '#chunkSize', '#excludeGlobs', '#preserveMtime'].forEach((selector) => {
    $(selector).addEventListener('change', renderSources);
  });
  $('#excludeGlobs').addEventListener('input', renderSources);

  $('#downloadAnla').addEventListener('click', (event) => {
    event.preventDefault();
    if (!state.built) return;
    download(state.built.bytes, $('#archiveName').value || 'workspace.anla');
  });
  $('#downloadRoundtrip').addEventListener('click', () => {
    if (state.built) {
      downloadZip(state.built.verified,
        ($('#archiveName').value || 'workspace.anla').replace(/\.anla$/, '') + '-restored.zip');
    }
  });
  $('#extractZip').addEventListener('click', () => {
    if (state.opened) {
      downloadZip(state.opened, state.opened.filename.replace(/\.anla$/, '') + '-restored.zip');
    }
  });
  $('#redownloadAnla').addEventListener('click', (event) => {
    event.preventDefault();
    if (state.opened) download(state.opened.bytes, state.opened.filename);
  });
  $('#copyManifest').addEventListener('click', async () => {
    if (!state.opened) return;
    try {
      await navigator.clipboard.writeText(canonical(state.opened.manifest));
      toast(t('manifest_copied'));
    } catch {
      toast(t('clipboard_failed'), true);
    }
  });
  $('#objectSearch').addEventListener('input', renderObjects);

  const crypto = hasNativeCrypto();
  const compression = hasNativeCompression();
  const badge = $('#capabilityBadge');
  badge.textContent = `${t('cap_crypto')}: ${crypto ? t('native') : t('fallback')} · `
    + `${t('cap_deflate')}: ${compression ? t('available') : t('store_only')}`;
  badge.className = `badge ${crypto && compression ? 'ok' : ''}`;
  $('#runtimeStatus').textContent = compression
    ? t('runtime_ready') : t('runtime_store_only');

  renderSources();
  selfTest();
}

// A round trip the page runs on itself when asked, so the deployed page can be
// checked in the deployed environment rather than only in a test harness.
async function selfTest() {
  if (new URLSearchParams(location.search).get('selftest') !== '1') return;
  const mark = document.createElement('div');
  mark.className = 'selftest';
  mark.id = 'selftest-result';
  mark.textContent = 'RUNNING';
  document.body.appendChild(mark);
  try {
    const encoder = new TextEncoder();
    const tree = {
      name: 'selftest',
      directories: ['docs'],
      files: [
        { path: 'docs/readme.txt', data: encoder.encode('ANLA self test\n'), mtimeNs: '1700000000000000000' },
        { path: 'data.bin', data: new Uint8Array([1, 2, 3, 4, 1, 2, 3, 4]) },
        { path: 'empty.txt', data: new Uint8Array(0) },
      ],
    };
    const options = {
      archiveUuid: new Uint8Array([...Array(16).keys()]),
      createdNs: '1752732000000000000',
    };
    const first = await pack(tree, { chunk_size: 4, compression: 'auto' }, options);
    const again = await pack(tree, { chunk_size: 4, compression: 'auto' }, options);
    const reproducible = first.bytes.length === again.bytes.length
      && first.bytes.every((byte, index) => byte === again.bytes[index]);
    const opened = await openArchive(first.bytes, { full: true });
    const zip = await exportZip(opened);
    if (opened.verification.verified_files !== 3 || !zip.length || !reproducible) {
      throw new Error(`unexpected: files=${opened.verification.verified_files} `
        + `zip=${zip.length} reproducible=${reproducible}`);
    }
    // The archive this page builds must be the archive the test suite pinned.
    const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', first.bytes))]
      .map((b) => b.toString(16).padStart(2, '0')).join('');
    mark.textContent = `PASS ${digest.slice(0, 12)}`;
    mark.dataset.status = 'pass';
    document.documentElement.dataset.selftest = 'pass';
    document.documentElement.dataset.selftestDigest = digest;
  } catch (error) {
    mark.textContent = `FAIL: ${error.message}`;
    mark.dataset.status = 'fail';
    document.documentElement.dataset.selftest = 'fail';
    console.error(error);
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot);
} else {
  boot();
}
