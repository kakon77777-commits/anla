# -*- coding: utf-8 -*-
"""Builds anla.evemisslab.com into site/dist/.

    python site/build.py

English at the root, Traditional Chinese under /zh/. The workbench ships the same
web/anla-core.js file the conformance suite runs under Node — it is copied, not
reimplemented, so the deployed page and the tested implementation cannot drift
apart. The build fails if a page is missing from a language that should have it.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import content as C  # noqa: E402
from markdown import render_markdown, split_front_matter  # noqa: E402

DIST = ROOT / "dist"
ASSETS = ROOT / "src" / "assets"
CORE = REPO / "web" / "anla-core.js"
VECTORS = REPO / "conformance" / "vectors"

BUILD_ID_FILE = DIST / "build.json"


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def strings(lang: str) -> dict:
    return C.STRINGS[lang]


def base(lang: str) -> str:
    return "/" if lang == "en" else "/zh/"


def other(lang: str) -> str:
    return "zh" if lang == "en" else "en"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def esc(value: str) -> str:
    return html.escape(str(value), quote=True)


NAV = (
    ("nav_home", "", True),
    ("nav_workbench", "workbench/", True),
    ("nav_demo", "demo/", True),
    ("nav_spec", "/spec/", False),
    ("nav_papers", "papers/", True),
    ("nav_conformance", "/conformance/", False),
)


def layout(lang: str, *, slug: str, title: str, description: str, body: str,
           runtime: bool = False, alternate: str | None = None,
           wide: bool = False) -> str:
    s = strings(lang)
    url = f"https://{C.HOST}{base(lang)}{slug}"
    nav_items = []
    for key, href, localized in NAV:
        target = f"{base(lang)}{href}" if localized else href
        current = ' aria-current="page"' if target.rstrip("/") == f"{base(lang)}{slug}".rstrip("/") \
            else ""
        label = esc(s[key])
        marker = "" if localized else f' <small style="opacity:.6">{esc(s["en_only"])}</small>'
        nav_items.append(f'<a href="{target}"{current}>{label}{marker}</a>')
    nav_items.append(f'<a href="{C.REPO}" rel="noreferrer">{esc(s["nav_repo"])} ↗</a>')

    switch = ""
    if alternate is not None:
        switch = (f'<a class="langswitch" href="{alternate}" '
                  f'hreflang="{"zh-Hant" if other(lang) == "zh" else "en"}">'
                  f'{esc(s["lang_switch"])}</a>')

    alternates = ""
    if alternate is not None:
        this_url = url
        other_url = f"https://{C.HOST}{alternate}"
        pairs = {("zh-Hant" if lang == "zh" else "en"): this_url,
                 ("en" if lang == "zh" else "zh-Hant"): other_url}
        alternates = "\n".join(
            f'<link rel="alternate" hreflang="{code}" href="{href}">'
            for code, href in sorted(pairs.items())
        ) + f'\n<link rel="alternate" hreflang="x-default" href="https://{C.HOST}/">'

    # The workbench's translations load as an asset rather than an inline
    # script: it lets the site keep script-src 'self' with no inline exception,
    # and an exception is the one thing a content policy should not have.
    runtime_json = (f'<script src="/assets/i18n.{lang}.js"></script>' if runtime else "")

    return f"""<!doctype html>
<html lang="{s['html_lang']}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<meta name="color-scheme" content="light dark">
<link rel="canonical" href="{url}">
{alternates}
<meta property="og:type" content="website">
<meta property="og:site_name" content="ANLA — {esc(s['site_tagline'])}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{url}">
<meta name="twitter:card" content="summary">
<link rel="icon" href="/assets/icon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/assets/styles.css">
{runtime_json}
</head>
<body>
<header class="topbar"><div class="wrap inner">
  <a class="brand" href="{base(lang)}"><span class="mark">A</span>
    <span>{esc(s['site_name'])}<small>{esc(s['site_tagline'])}</small></span></a>
  <nav class="nav">{''.join(nav_items)}</nav>
  {switch}
</div></header>
{body}
<footer class="footer"><div class="wrap inner">
  <span>{esc(s['footer_left'])}</span>
  <span><a href="{C.REPO}/blob/main/LICENSE" rel="noreferrer">{esc(s['footer_license'])}</a>
    · <a href="{C.FAMILY}" rel="noreferrer">{esc(s['footer_family'])}</a></span>
</div></footer>
</body>
</html>
"""


# --------------------------------------------------------------------------
# landing
# --------------------------------------------------------------------------

def page_home(lang: str) -> str:
    s = strings(lang)
    b = base(lang)
    body = f"""<main>
<div class="wrap"><section class="hero"><div class="hero-grid">
  <div>
    <div class="eyebrow">{esc(s['hero_eyebrow'])}</div>
    <h1>{esc(s['hero_h1_a'])}<br><em>{esc(s['hero_h1_b'])}</em></h1>
    <p class="lead">{esc(s['hero_lead'])}</p>
    <div class="actions">
      <a class="btn primary" href="{b}workbench/">{esc(s['hero_cta_1'])}</a>
      <a class="btn" href="{b}demo/">{esc(s['cta_demo_t'])}</a>
      <a class="btn" href="/spec/">{esc(s['hero_cta_2'])}</a>
    </div>
  </div>
  <aside class="card">
    <span class="tag">ANLA-MVP v0.1</span>
    <div class="label">{esc(s['card_label'])}</div>
    <div class="invariant">Extract(Pack(F, P)) = F</div>
    <div class="facts">
      <div><span>{esc(s['fact_lossless'])}</span><strong>{esc(s['fact_lossless_v'])}</strong></div>
      <div><span>{esc(s['fact_ai'])}</span><strong>{esc(s['fact_ai_v'])}</strong></div>
      <div><span>{esc(s['fact_impl'])}</span><strong>{esc(s['fact_impl_v'])}</strong></div>
      <div><span>{esc(s['fact_tests'])}</span><strong>{esc(s['fact_tests_v'])}</strong></div>
    </div>
  </aside>
</div>
<div class="strip">
  <div><strong>{esc(s['strip_1_t'])}</strong><span>{esc(s['strip_1_d'])}</span></div>
  <div><strong>{esc(s['strip_2_t'])}</strong><span>{esc(s['strip_2_d'])}</span></div>
  <div><strong>{esc(s['strip_3_t'])}</strong><span>{esc(s['strip_3_d'])}</span></div>
  <div><strong>{esc(s['strip_4_t'])}</strong><span>{esc(s['strip_4_d'])}</span></div>
</div></section></div>

<section class="section"><div class="wrap">
  <div class="section-head"><span class="kicker">{esc(s['why_kicker'])}</span>
    <h2>{esc(s['why_h2'])}</h2><p class="section-desc">{esc(s['why_desc'])}</p></div>
  <div class="grid-3">
    <article class="feature"><span class="num">01</span><h3>{esc(s['why_1_h'])}</h3>
      <p>{esc(s['why_1_p'])}</p><code>{esc(s['why_1_c'])}</code></article>
    <article class="feature"><span class="num">02</span><h3>{esc(s['why_2_h'])}</h3>
      <p>{esc(s['why_2_p'])}</p><code>{esc(s['why_2_c'])}</code></article>
    <article class="feature"><span class="num">03</span><h3>{esc(s['why_3_h'])}</h3>
      <p>{esc(s['why_3_p'])}</p><code>{esc(s['why_3_c'])}</code></article>
  </div>
</div></section>

<section class="section"><div class="wrap">
  <div class="section-head"><span class="kicker">{esc(s['arch_kicker'])}</span>
    <h2>{esc(s['arch_h2'])}</h2><p class="section-desc">{esc(s['arch_desc'])}</p></div>
  <div class="grid-2">
    <article class="plane preserve"><span class="plane-tag">{esc(s['arch_p_tag'])}</span>
      <h3>{esc(s['arch_p_h'])}</h3><p>{esc(s['arch_p_p'])}</p>
      <ul><li>Raw content chunks</li><li>Canonical JSON manifest</li>
        <li>SHA-256 integrity digests</li><li>Filesystem object model</li></ul></article>
    <article class="plane intel"><span class="plane-tag">{esc(s['arch_i_tag'])}</span>
      <h3>{esc(s['arch_i_h'])}</h3><p>{esc(s['arch_i_p'])}</p>
      <ul><li>Packing plan</li><li>Planner decision log</li>
        <li>Search and semantic indexes</li><li>Agent operation history</li></ul></article>
  </div>
</div></section>

<section class="section"><div class="wrap">
  <div class="section-head"><span class="kicker">{esc(s['proof_kicker'])}</span>
    <h2>{esc(s['proof_h2'])}</h2><p class="section-desc">{esc(s['proof_desc'])}</p></div>
  <div class="grid-2">
    <article class="feature"><span class="num">T-XIM-3</span><h3>{esc(s['proof_1_h'])}</h3>
      <p>{esc(s['proof_1_p'])}</p></article>
    <article class="feature"><span class="num">T-ORG-1</span><h3>{esc(s['proof_2_h'])}</h3>
      <p>{esc(s['proof_2_p'])}</p></article>
    <article class="feature"><span class="num">T-CHK · T-PTH · T-BMB</span>
      <h3>{esc(s['proof_3_h'])}</h3><p>{esc(s['proof_3_p'])}</p></article>
    <article class="feature"><span class="num">T-EXT-1</span><h3>{esc(s['proof_4_h'])}</h3>
      <p>{esc(s['proof_4_p'])}</p></article>
  </div>
</div></section>

<section class="section"><div class="wrap">
  <div class="section-head"><span class="kicker">{esc(s['state_kicker'])}</span>
    <h2>{esc(s['state_h2'])}</h2><p class="section-desc">{esc(s['state_desc'])}</p></div>
  <div class="grid-2">
    <article class="plane preserve"><h3>{esc(s['state_yes_h'])}</h3>
      <p>{esc(s['state_yes_p'])}</p></article>
    <article class="plane intel"><h3>{esc(s['state_no_h'])}</h3>
      <p>{esc(s['state_no_p'])}</p></article>
  </div>
  <div class="callout"><strong>⚠</strong> {esc(s['state_warn'])}</div>
</div></section>

<section class="section"><div class="wrap">
  <div class="section-head"><span class="kicker">{esc(s['get_kicker'])}</span>
    <h2>{esc(s['get_h2'])}</h2></div>
  <div class="filecards">
    {_filecard(f"{b}workbench/", s['cta_workbench_t'], s['cta_workbench_d'], 'HTML · no backend')}
    {_filecard(f"{b}demo/", s['cta_demo_t'], s['cta_demo_d'], '67 assertions')}
    {_filecard("/standalone.html" if lang == "en" else "/standalone.zh.html",
               s['cta_standalone_t'], s['cta_standalone_d'], 'single file')}
    {_filecard("/spec/", s['cta_spec_t'], s['cta_spec_d'], 'EN')}
    {_filecard(f"{b}papers/", s['cta_papers_t'], s['cta_papers_d'], 'EN · 中文')}
    {_filecard("/conformance/", s['cta_vectors_t'], s['cta_vectors_d'], '.anla + SHA256SUMS')}
    {_filecard(C.REPO, s['cta_repo_t'], s['cta_repo_d'], 'Apache-2.0')}
  </div>
</div></section>
</main>"""
    return layout(lang, slug="", title=f"ANLA — {s['site_tagline']}",
                  description=s["meta_home"], body=body,
                  alternate=base(other(lang)))


def _filecard(href: str, title: str, description: str, meta: str) -> str:
    rel = ' rel="noreferrer"' if href.startswith("http") else ""
    return (f'<a class="filecard" href="{esc(href)}"{rel}><span><span class="t">'
            f'{esc(title)}</span><span class="d">{esc(description)}</span></span>'
            f'<span class="m">{esc(meta)}</span></a>')


# --------------------------------------------------------------------------
# workbench
# --------------------------------------------------------------------------

def workbench_markup(lang: str) -> str:
    s = strings(lang)
    return f"""<section class="section"><div class="wrap">
  <div class="section-head"><span class="kicker">{esc(s['wb_kicker'])}</span>
    <h1>{esc(s['wb_h2'])}</h1><p class="section-desc">{esc(s['wb_desc'])}</p>
    <p style="margin-top:10px"><span class="badge" id="capabilityBadge">…</span>
      <span class="badge" id="runtimeStatus">…</span></p></div>

  <div class="shell">
    <div class="shell-top"><div class="dots"><i></i><i></i><i></i></div>
      <span class="shell-title">{esc(s['wb_shell_title'])}</span>
      <span class="badge">{esc(s['wb_no_backend'])}</span></div>
    <div class="shell-body">
      <aside class="tabs">
        <button class="tab active" data-panel="build">{esc(s['wb_tab_1'])}</button>
        <button class="tab" data-panel="inspect">{esc(s['wb_tab_2'])}</button>
        <button class="tab" data-panel="status">{esc(s['wb_tab_3'])}</button>
        <p class="note">{esc(s['wb_side_note'])}</p>
      </aside>
      <div>
        <section class="panel active" id="wb-build">
          <div class="panel-title"><div><h3>{esc(s['wb_pick_h'])}</h3>
            <p>{esc(s['wb_pick_p'])}</p></div>
            <button class="btn small" id="clearSource">{esc(s['wb_clear'])}</button></div>
          <label class="drop" id="sourceDrop">
            <input type="file" id="sourceInput" webkitdirectory multiple>
            <span class="icon">⌁</span>
            <strong>{esc(s['wb_drop_strong'])}</strong>
            <small>{esc(s['wb_drop_small'])}</small>
            <span class="mini"><button class="btn small" type="button" id="nativePicker">
              {esc(s['wb_native'])}</button></span>
          </label>
          <div class="summaries">
            <div class="summary"><span>{esc(s['s_files'])}</span><strong id="srcFiles">0</strong></div>
            <div class="summary"><span>{esc(s['s_dirs'])}</span><strong id="srcDirs">0</strong></div>
            <div class="summary"><span>{esc(s['s_logical'])}</span><strong id="srcSize">0 B</strong></div>
            <div class="summary"><span>{esc(s['s_root'])}</span><strong id="srcRoot">—</strong></div>
          </div>
          <div class="filelist" id="sourceList" hidden></div>
          <div class="form">
            <label class="field"><span>{esc(s['f_compression'])}</span>
              <select id="compression">
                <option value="auto">{esc(s['f_comp_auto'])}</option>
                <option value="deflate">{esc(s['f_comp_deflate'])}</option>
                <option value="store">{esc(s['f_comp_store'])}</option>
              </select></label>
            <label class="field"><span>{esc(s['f_chunk'])}</span>
              <select id="chunkSize">
                <option value="262144">256 KiB</option>
                <option value="1048576" selected>1 MiB</option>
                <option value="4194304">4 MiB</option>
                <option value="16777216">16 MiB</option>
              </select></label>
            <label class="field"><span>{esc(s['f_name'])}</span>
              <input id="archiveName" type="text" value="workspace.anla" spellcheck="false"></label>
            <label class="field"><span>{esc(s['f_level'])}</span>
              <input id="deflateLevel" type="range" min="0" max="9" value="6"></label>
            <label class="field wide"><span>{esc(s['f_exclude'])}</span>
              <textarea id="excludeGlobs" spellcheck="false"
                placeholder=".git&#10;.git/**&#10;node_modules/**"></textarea></label>
          </div>
          <div class="checks">
            <label><input type="checkbox" id="preserveMtime" checked>{esc(s['chk_mtime'])}</label>
            <label><input type="checkbox" checked disabled>{esc(s['chk_verify'])}</label>
            <label><input type="checkbox" checked disabled>{esc(s['chk_ai'])}</label>
          </div>
          <div class="action-row">
            <button class="btn primary" id="buildButton" disabled>{esc(s['wb_build'])}</button>
            <button class="btn" id="showPlan">{esc(s['wb_plan'])}</button>
            <span class="status" id="buildStatus">…</span>
          </div>
          <div class="result" id="buildResult" hidden>
            <div class="result-head"><div class="ok"><i></i><strong>{esc(s['wb_result_ok'])}</strong></div>
              <div class="action-row">
                <a class="btn primary small" id="downloadAnla" href="#">{esc(s['wb_download'])}</a>
                <button class="btn small" id="downloadRoundtrip">{esc(s['wb_restore'])}</button>
              </div></div>
            <div class="summaries" id="buildMetrics"></div>
            <pre class="report" id="buildReport"></pre>
          </div>
        </section>

        <section class="panel" id="wb-inspect">
          <div class="panel-title"><div><h3>{esc(s['wb_open_h'])}</h3>
            <p>{esc(s['wb_open_p'])}</p></div></div>
          <label class="drop" id="archiveDrop">
            <input type="file" id="archiveInput" accept=".anla,application/octet-stream">
            <span class="icon">⇩</span>
            <strong>{esc(s['wb_open_strong'])}</strong>
            <small>{esc(s['wb_open_small'])}</small>
          </label>
          <div class="result" id="inspectResult" hidden>
            <div class="result-head"><div class="ok"><i></i><strong>{esc(s['wb_open_ok'])}</strong></div>
              <div class="action-row">
                <button class="btn primary small" id="extractZip">{esc(s['wb_extract'])}</button>
                <a class="btn small" id="redownloadAnla" href="#">{esc(s['wb_redownload'])}</a>
              </div></div>
            <div class="summaries" id="inspectMetrics"></div>
            <div class="searchbar">
              <input type="search" id="objectSearch" placeholder="{esc(s['wb_search'])}">
              <button class="btn small" id="copyManifest">{esc(s['wb_copy_manifest'])}</button>
            </div>
            <div class="objects" id="objectList"></div>
            <pre class="report" id="inspectReport"></pre>
          </div>
        </section>

        <section class="panel" id="wb-status">
          <div class="panel-title"><div><h3>{esc(s['wb_profile_h'])}</h3>
            <p>{esc(s['wb_profile_p'])}</p></div></div>
          <div class="grid-2">
            <article class="feature"><h3>{esc(s['wb_prof_1_h'])}</h3>
              <p>{esc(s['wb_prof_1_p'])}</p></article>
            <article class="feature"><h3>{esc(s['wb_prof_2_h'])}</h3>
              <p>{esc(s['wb_prof_2_p'])}</p></article>
            <article class="feature"><h3>{esc(s['wb_prof_3_h'])}</h3>
              <p>{esc(s['wb_prof_3_p'])}</p></article>
            <article class="feature"><h3>{esc(s['wb_prof_4_h'])}</h3>
              <p>{esc(s['wb_prof_4_p'])}</p>
              <code><a href="?selftest=1">{esc(s['wb_selftest_link'])}</a></code></article>
          </div>
        </section>
      </div>
    </div>
  </div>
</div></section>
<div class="toast" id="toast" hidden></div>
<div class="busy" id="busy" hidden><div class="box"><div class="spinner"></div>
  <strong id="busyTitle">…</strong><span id="busyDetail">…</span></div></div>"""


def page_workbench(lang: str) -> str:
    s = strings(lang)
    body = ('<main>' + workbench_markup(lang)
            + '<script type="module" src="/assets/app.js"></script></main>')
    return layout(lang, slug="workbench/",
                  title=f"{s['wb_h2']} — ANLA",
                  description=s["meta_workbench"], body=body, runtime=True,
                  alternate=f"{base(other(lang))}workbench/")


def page_demo(lang: str) -> str:
    s = strings(lang)
    body = f"""<main><div class="wrap"><section class="section">
  <div class="section-head"><span class="kicker">{esc(s['demo_kicker'])}</span>
    <h1>{esc(s['demo_h1'])}</h1>
    <p class="section-desc">{esc(s['demo_desc'])}</p></div>

  <div class="runbar">
    <button class="btn primary" id="runButton">{esc(s['demo_run'])}</button>
    <span class="badge" id="tally">—</span>
    <span class="badge" id="env">…</span>
    <span class="runmeta">{esc(s['demo_counts'])}: <b id="counts">…</b>
      <small>{esc(s['demo_counts_note'])}</small></span>
  </div>

  <div class="callout"><strong>▸</strong> {esc(s['demo_headline'])}</div>
  <div class="callout" id="verdict" hidden></div>

  <div id="results" class="suites"></div>

  <p class="section-desc" style="margin-top:26px">{esc(s['demo_source'])}
    <a href="/conformance/">{esc(s['nav_conformance'])} ↗</a></p>
</section></div>
<script type="module" src="/assets/demo.js"></script></main>"""
    return layout(lang, slug="demo/", title=f"{s['demo_h1']} — ANLA",
                  description=s["meta_demo"], body=body, runtime=True,
                  alternate=f"{base(other(lang))}demo/")


def build_standalone(lang: str) -> tuple[str, str]:
    """One file, no requests: the css, the core and the app inlined.

    The core and the app are the same sources the hosted page and the test suite
    use; only their delivery differs.
    """
    s = strings(lang)
    css = (ASSETS / "styles.css").read_text(encoding="utf-8")
    core = CORE.read_text(encoding="utf-8")
    app = (ASSETS / "app.js").read_text(encoding="utf-8")

    # Splice the two modules into one inline module: drop the core's export
    # keywords and the app's import statement, keeping every definition.
    core_inline = re.sub(r"^export\s+(?=(const|function|async function|class|let))", "",
                         core, flags=re.MULTILINE)
    core_inline = re.sub(r"^export\s+\{[^}]*\};?\s*$", "", core_inline, flags=re.MULTILINE)
    app_inline = re.sub(r"import\s*\{[^}]*\}\s*from\s*'\./anla-core\.js';", "", app)

    runtime = json.dumps({key: s[key] for key in C.RUNTIME_KEYS},
                         ensure_ascii=False, sort_keys=True)

    # One inline module, hashed, so the served copy needs no 'unsafe-inline' for
    # scripts. The translations go inside it rather than in a second script tag:
    # two inline scripts would mean two hashes to keep in step. Opened from a
    # file:// URL there is no CSP at all, which is the point of this build.
    script_body = f"\nwindow.ANLA_I18N={runtime};\n{core_inline}\n{app_inline}\n"
    script_hash = "sha256-" + base64.b64encode(
        hashlib.sha256(script_body.encode("utf-8")).digest()).decode("ascii")

    document = f"""<!doctype html>
<html lang="{s['html_lang']}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>ANLA Standalone Workbench — {esc(s['site_tagline'])}</title>
<meta name="description" content="{esc(s['meta_workbench'])}">
<meta name="color-scheme" content="light dark">
<meta name="robots" content="noindex">
<style>{css}</style>
</head>
<body>
<header class="topbar"><div class="wrap inner">
  <a class="brand" href="https://{C.HOST}/"><span class="mark">A</span>
    <span>{esc(s['site_name'])}<small>{esc(s['site_tagline'])} · standalone</small></span></a>
  <nav class="nav"><a href="https://{C.HOST}{base(lang)}" rel="noreferrer">
    {esc(s['nav_home'])} ↗</a></nav>
</div></header>
<main>{workbench_markup(lang)}</main>
<footer class="footer"><div class="wrap inner">
  <span>{esc(s['footer_left'])}</span><span>{esc(s['footer_right'])}</span>
</div></footer>
<script type="module">{script_body}</script>
</body>
</html>
"""
    return document, script_hash


# --------------------------------------------------------------------------
# documents
# --------------------------------------------------------------------------

def page_doc(lang: str, *, slug: str, source: Path, title: str, description: str,
             notes: list[str], alternate: str | None, link_line: str = "",
             heading_offset: int = 0) -> str:
    s = strings(lang)
    text = source.read_text(encoding="utf-8")
    meta, markdown_body = split_front_matter(text)
    headings: list[dict] = []
    rendered = render_markdown(markdown_body, heading_offset=heading_offset,
                              collect_headings=headings)

    meta_rows = []
    for key, label in (("author", "doc_meta_author"), ("date", "doc_meta_date"),
                       ("version", "doc_meta_version"), ("status", "doc_meta_status"),
                       ("language", "doc_meta_lang")):
        if meta.get(key):
            meta_rows.append(f"<dt>{esc(s[label])}</dt><dd>{esc(meta[key])}</dd>")
    rel = source.relative_to(REPO).as_posix()
    meta_rows.append(f'<dt>{esc(s["doc_source"])}</dt><dd><a href="{C.REPO}/blob/main/{rel}"'
                     f' rel="noreferrer"><code>{esc(rel)}</code></a></dd>')
    docmeta = f'<div class="docmeta"><dl>{"".join(meta_rows)}</dl></div>'

    callouts = "".join(f'<div class="callout">{esc(note)}</div>' for note in notes)
    # A hundred-entry table of contents is a wall, not a map: on a long
    # document keep only the top level.
    deep = [h for h in headings if h["level"] in (2, 3)]
    wanted = deep if len(deep) <= 40 else [h for h in deep if h["level"] == 2]
    toc_links = "".join(
        f'<a href="#{h["slug"]}" class="l{h["level"]}">{esc(h["text"])}</a>'
        for h in wanted
    )
    toc = (f'<nav class="toc"><strong>{esc(s["doc_toc"])}</strong>{toc_links}</nav>'
           if toc_links else "")

    body = f"""<main><div class="wrap"><div class="section">
<div class="doclayout">
  <article class="prose wide">
    {docmeta}
    {callouts}
    {link_line}
    {rendered}
  </article>
  {toc}
</div>
</div></div></main>"""
    return layout(lang, slug=slug, title=title, description=description, body=body,
                  alternate=alternate, wide=True)


def page_papers(lang: str) -> str:
    s = strings(lang)
    b = base(lang)
    cards = [
        _papercard(f"{b}papers/control-plane-transition/", s["paper_1_t"], s["paper_1_s"],
                   s["paper_1_d"], s["paper_read"],
                   s["paper_original"] if lang == "zh" else s["paper_translation"]),
        _papercard(f"{b}papers/anla-whitepaper/", s["paper_2_t"], s["paper_2_s"],
                   s["paper_2_d"], s["paper_read"],
                   s["paper_original"] if lang == "zh" else s["paper_translation"]),
        _papercard("/spec/", s["spec_card_t"], "ANLA-MVP v0.1",
                   s["spec_card_d"], s["paper_read"], s["en_only"]),
    ]
    body = f"""<main><div class="wrap"><section class="section">
  <div class="section-head"><span class="kicker">{esc(s['papers_kicker'])}</span>
    <h1>{esc(s['papers_h2'])}</h1><p class="section-desc">{esc(s['papers_desc'])}</p></div>
  <div class="grid-2">{''.join(cards)}</div>
</section></div></main>"""
    return layout(lang, slug="papers/", title=f"{s['papers_h2']} — ANLA",
                  description=s["meta_papers"], body=body,
                  alternate=f"{base(other(lang))}papers/")


def _papercard(href: str, title: str, subtitle: str, description: str,
               read: str, badge: str) -> str:
    return (f'<article class="feature"><span class="num">{esc(badge)}</span>'
            f'<h3>{esc(title)}</h3>'
            f'<p style="color:var(--ink-3);margin:0 0 8px">{esc(subtitle)}</p>'
            f'<p>{esc(description)}</p>'
            f'<a class="btn small" href="{esc(href)}">{esc(read)} →</a></article>')


# --------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------

PAPERS = {
    "control-plane-transition": {
        "en": REPO / "papers" / "01-control-plane-transition.en.md",
        "zh": REPO / "papers" / "01-control-plane-transition.zh-Hant.md",
        "title": "paper_1_t",
    },
    "anla-whitepaper": {
        "en": REPO / "papers" / "02-anla-whitepaper.en.md",
        "zh": REPO / "papers" / "02-anla-whitepaper.zh-Hant.md",
        "title": "paper_2_t",
    },
}


def fixtures_module() -> str:
    """conformance/fixtures.json, verbatim, as an ES module.

    Verbatim matters: the live test page compares what it packs against hashes
    the Python writer produced, so if this file were massaged on the way in, the
    comparison would be measuring the massaging.
    """
    raw = (REPO / "conformance" / "fixtures.json").read_text(encoding="utf-8")
    json.loads(raw)  # fail the build rather than ship a broken module
    return ("// Generated from conformance/fixtures.json — do not edit.\n"
            "export const FIXTURES = " + raw.rstrip() + ";\n")


#: Vectors larger than this are not inlined into the live test page. Every hash
#: still is, so the byte-exactness suite still checks them: it packs the case here
#: and compares against the committed hash, which exercises the same bytes through
#: the writer instead of the reader. The page says how many it bundled, because a
#: silently truncated test set reads as full coverage when it is not.
VECTOR_BUNDLE_LIMIT = 24 * 1024


def vectors_module() -> str:
    """The frozen vectors as base64, plus the committed SHA256SUMS.

    The hashes are what make the page's headline claim checkable in front of the
    reader: they were produced by the Python writer, and the browser has to
    arrive at the same ones from the same fixtures.
    """
    import base64 as b64

    entries = {}
    omitted = {}
    for vector in sorted(VECTORS.glob("*.anla")):
        raw = vector.read_bytes()
        if len(raw) > VECTOR_BUNDLE_LIMIT:
            omitted[vector.name] = len(raw)
            continue
        entries[vector.name] = b64.b64encode(raw).decode("ascii")
    sums = {}
    for line in (VECTORS / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            digest, name = line.split("  ", 1)
            sums[name] = digest
    missing = set(entries) - set(sums)
    if missing:
        raise SystemExit(f"vectors without a committed hash: {sorted(missing)}")
    if omitted:
        listing = ", ".join(f"{name} ({size // 1024} KiB)"
                            for name, size in sorted(omitted.items()))
        print(f"  not inlined into the live test page, hashes still checked: {listing}")
    return ("// Generated from conformance/vectors/ — do not edit.\n"
            "export const VECTOR_BYTES_BASE64 = "
            + json.dumps(entries, indent=0, sort_keys=True) + ";\n"
            "export const VECTOR_SHA256 = "
            + json.dumps(sums, indent=1, sort_keys=True) + ";\n"
            "export const VECTOR_NOT_BUNDLED = "
            + json.dumps(omitted, indent=1, sort_keys=True) + ";\n")


def git_revision() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(REPO),
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or "unversioned"
    except Exception:
        return "unversioned"


def main() -> int:
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    written: list[str] = []

    def emit(relative: str, text: str) -> None:
        write(DIST / relative, text)
        written.append(relative)

    # pages present in both languages
    for lang in C.LANGS:
        prefix = "" if lang == "en" else "zh/"
        emit(f"{prefix}index.html", page_home(lang))
        emit(f"{prefix}workbench/index.html", page_workbench(lang))
        emit(f"{prefix}demo/index.html", page_demo(lang))
        emit(f"{prefix}papers/index.html", page_papers(lang))
        for slug, spec in PAPERS.items():
            s = strings(lang)
            source = spec[lang]
            notes = [s["doc_translation_note"]] if lang == "en" else []
            partner = f"{base(other(lang))}papers/{slug}/"
            link = (f'<p><a class="btn small" href="{partner}">'
                    f'{esc(s["doc_read_zh"] if lang == "en" else s["doc_read_en"])} →</a></p>')
            emit(f"{prefix}papers/{slug}/index.html",
                 page_doc(lang, slug=f"papers/{slug}/", source=source,
                          title=f"{s[spec['title']]} — ANLA",
                          description=s["meta_papers"], notes=notes,
                          alternate=partner, link_line=link))

    # English-only documents, linked from both trees
    emit("spec/index.html", page_doc(
        "en", slug="spec/", source=REPO / "SPEC.md",
        title="ANLA-MVP v0.1 — Normative Specification",
        description="The normative byte-level specification of ANLA-MVP v0.1: header, "
                    "record frame, footer, canonical JSON, codecs, manifest, paths, "
                    "reproducibility, decoder safety and conformance.",
        notes=[strings("en")["doc_spec_note"]], alternate=None))
    emit("conformance/index.html", page_doc(
        "en", slug="conformance/", source=REPO / "conformance" / "README.md",
        title="Conformance — ANLA-MVP v0.1",
        description="The conformance suite, the frozen test vectors and their hashes, "
                    "for anyone implementing ANLA-MVP v0.1 independently.",
        notes=[], alternate=None))

    # standalone single-file builds
    standalone_hashes = {}
    for lang, name in (("en", "standalone.html"), ("zh", "standalone.zh.html")):
        document, script_hash = build_standalone(lang)
        emit(name, document)
        standalone_hashes[name] = script_hash

    # assets: the core is copied, never rewritten
    (DIST / "assets").mkdir(parents=True, exist_ok=True)
    shutil.copy2(ASSETS / "styles.css", DIST / "assets" / "styles.css")
    shutil.copy2(ASSETS / "app.js", DIST / "assets" / "app.js")
    shutil.copy2(CORE, DIST / "assets" / "anla-core.js")
    write(DIST / "assets" / "icon.svg", ICON)
    written += ["assets/styles.css", "assets/app.js", "assets/anla-core.js",
                "assets/icon.svg"]
    for lang in C.LANGS:
        payload = {key: strings(lang)[key] for key in C.RUNTIME_KEYS}
        write(DIST / "assets" / f"i18n.{lang}.js",
              "window.ANLA_I18N="
              + json.dumps(payload, ensure_ascii=False, sort_keys=True) + ";\n")
        written.append(f"assets/i18n.{lang}.js")

    # The live test page's inputs travel with the page instead of being fetched.
    # That is not an optimisation: connect-src is 'none', so a page that fetched
    # its own fixtures would need that promise loosened to run its own tests.
    shutil.copy2(ASSETS / "demo.js", DIST / "assets" / "demo.js")
    write(DIST / "assets" / "fixtures.js", fixtures_module())
    write(DIST / "assets" / "vectors.js", vectors_module())
    written += ["assets/demo.js", "assets/fixtures.js", "assets/vectors.js"]

    # downloadable conformance vectors
    vectors_out = DIST / "downloads" / "vectors"
    vectors_out.mkdir(parents=True, exist_ok=True)
    vector_names = []
    for vector in sorted(VECTORS.iterdir()):
        if vector.is_file():
            shutil.copy2(vector, vectors_out / vector.name)
            vector_names.append(vector.name)

    # robots, sitemap, headers
    write(DIST / "robots.txt",
          f"User-agent: *\nAllow: /\nSitemap: https://{C.HOST}/sitemap.xml\n")
    urls = [u for u in written if u.endswith("index.html")]
    entries = "".join(
        f"  <url><loc>https://{C.HOST}/{u[:-10]}</loc></url>\n" for u in sorted(urls))
    write(DIST / "sitemap.xml",
          '<?xml version="1.0" encoding="UTF-8"?>\n'
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
          f"{entries}</urlset>\n")
    write(DIST / "_headers", headers_file(standalone_hashes))

    revision = git_revision()
    write(BUILD_ID_FILE, json.dumps({
        "site": C.HOST,
        "format": "ANLA-MVP 0.1",
        "revision": revision,
        "pages": sorted(urls),
        "vectors": vector_names,
    }, indent=2, sort_keys=True) + "\n")

    # A page that silently lost its script tag is worse than a build failure.
    checks = [
        ("workbench/index.html", '<script type="module" src="/assets/app.js">'),
        ("zh/workbench/index.html", '/assets/i18n.zh.js'),
        ("assets/i18n.zh.js", "window.ANLA_I18N"),
        ("standalone.html", "async function pack("),
        ("standalone.zh.html", "window.ANLA_I18N"),
        ("workbench/index.html", '/assets/i18n.en.js'),
        ("demo/index.html", '<script type="module" src="/assets/demo.js">'),
        ("zh/demo/index.html", 'suite_rej'.replace('suite_rej', 'runButton')),
        ("assets/fixtures.js", "export const FIXTURES"),
        ("assets/vectors.js", "export const VECTOR_SHA256"),
        ("spec/index.html", "Bootstrap Header"),
        ("papers/anla-whitepaper/index.html", "Extract(Pack(F,P))=F"),
        ("zh/papers/anla-whitepaper/index.html", "保存平面"),
    ]
    problems = []
    for relative, needle in checks:
        target = DIST / relative
        if not target.exists():
            problems.append(f"missing page: {relative}")
        elif needle not in target.read_text(encoding="utf-8"):
            problems.append(f"{relative} is missing {needle!r}")
    for name in ("standalone.html", "standalone.zh.html"):
        if "from './anla-core.js'" in (DIST / name).read_text(encoding="utf-8"):
            problems.append(f"{name} still imports an external module")
    if problems:
        for problem in problems:
            print(f"build check failed: {problem}", file=sys.stderr)
        return 1

    total = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file())
    print(f"built {len(written)} files into {DIST}  ({total / 1024:.0f} KiB, rev {revision})")
    print(f"  pages: {len(urls)}   vectors: {len(vector_names)}")
    return 0


ICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
<rect width="32" height="32" rx="7" fill="#12557d"/>
<path d="M8 22.5 15.1 9h1.9l7.1 13.5h-3.3l-1.5-3H12.7l-1.5 3H8Zm5.8-5.6h4.5L16 12.4Z"
 fill="#f6f4f0"/></svg>
"""

def base_csp(script_hashes: list[str]) -> str:
    """The site-wide policy.

    The hashes are the standalone builds' single inline module. They are in the
    global policy rather than only in a per-path rule because path matching for
    an extension-stripped URL is host behaviour, and a security header that
    depends on host behaviour is a security header that will one day not apply.
    Adding a hash does not loosen 'self' for anything else: an injected script
    would have to hash to exactly one of these.

    Inline styles are allowed because the standalone build inlines its
    stylesheet; a style is a far smaller surface than a script, and a hash for it
    is not reliably supported everywhere.
    """
    sources = " ".join(f"'{h}'" for h in sorted(script_hashes))
    return (f"default-src 'self'; script-src 'self' {sources}; "
            f"style-src 'self' 'unsafe-inline'; connect-src 'none'; "
            f"img-src 'self' data:; object-src 'none'; base-uri 'none'; "
            f"form-action 'none'; frame-ancestors 'none'")


def headers_file(standalone_hashes: dict[str, str]) -> str:
    """Build `_headers`.

    `connect-src 'none'` is the load-bearing line: neither page has any reason to
    send your files anywhere, so it is denied at the policy level rather than left
    to the code's good behaviour.

    One policy for every path. Per-path rules were tried and removed: the host
    serves `/standalone.html` from `/standalone`, so a path-keyed rule produced a
    second CSP header for the browser to intersect with the first, which is a
    confusing way to say what one header already said.
    """
    blocks = [f"/*\n  Referrer-Policy: no-referrer\n  X-Content-Type-Options: nosniff\n"
              f"  Permissions-Policy: camera=(), microphone=(), geolocation=()\n"
              f"  Cross-Origin-Opener-Policy: same-origin\n"
              f"  Content-Security-Policy: "
              f"{base_csp(list(standalone_hashes.values()))}\n"]
    blocks.append("/assets/*\n  Cache-Control: public, max-age=3600\n")
    blocks.append("/downloads/*\n  Cache-Control: public, max-age=86400\n")
    return "\n".join(blocks)


if __name__ == "__main__":
    raise SystemExit(main())
