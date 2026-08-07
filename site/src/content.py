# -*- coding: utf-8 -*-
"""Site copy, in both languages, plus the two hand-built page templates.

English at the root, Traditional Chinese under /zh/. The specification and the
conformance report are maintained in English only and linked from both trees —
marked as such rather than duplicated, because a format specification with two
normative language versions has two normative language versions, which is a
problem, not a feature.
"""

from __future__ import annotations

LANGS = ("en", "zh")

HOST = "anla.evemisslab.com"
REPO = "https://github.com/kakon77777-commits/anla"
FAMILY = "https://evemisslab.com"

# --------------------------------------------------------------------------
# strings
# --------------------------------------------------------------------------

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "html_lang": "en",
        "site_name": "ANLA",
        "site_tagline": "Agent-Native Lossless Archive",
        "nav_home": "Overview",
        "nav_workbench": "Workbench",
        "nav_spec": "Specification",
        "nav_papers": "Papers",
        "nav_conformance": "Conformance",
        "nav_bench": "Numbers",
        "nav_repo": "Source",
        "bench_kicker": "Measured, not claimed",
        "bench_h1": "What ANLA does to real bytes",
        "bench_desc": "Five scenarios, run against this repository's own git history "
                      "and against the alternatives a person would actually reach for. "
                      "Every figure is produced by bench/run_bench.py and written to a "
                      "JSON file this page is generated from, so the page cannot say "
                      "anything the harness did not measure — including the rows where "
                      "ANLA loses.",
        "bench_warning_h": "ANLA 1.0 does not compress.",
        "bench_warning": "Its only codec is store. Every ratio below is deduplication. "
                         "One snapshot of unique files is therefore larger than the "
                         "tree it holds, and a general-purpose compressor beats it "
                         "comfortably. That case is the first row rather than an "
                         "omitted one, because a benchmark you cannot lose is not a "
                         "benchmark.",
        "bench_measured": "Measured at",
        "bench_stack": "Profile",
        "bench_input": "Input",
        "bench_smaller": "smaller is better",
        "bench_of_input": "of the input",
        "bench_composition_h": "Where the bytes went, per snapshot",
        "bench_composition": "New content against the cost of describing it. A "
                             "manifest describes its whole snapshot rather than a "
                             "delta, and this is what that costs.",
        "bench_col_snapshot": "Snapshot",
        "bench_col_content": "New content",
        "bench_col_metadata": "Metadata",
        "bench_reading_h": "What the table says to build next",
        "bench_read_codec": "One snapshot of a source tree costs {ratio}× a tar.gz "
                            "of the same tree. That gap is a missing codec, not a "
                            "missing design, and it is the entire case for Zstandard.",
        "bench_read_history": "Eight versions of that tree cost {ratio}× a single "
                              "tar.gz of all eight — with no compression at all. "
                              "Unlike the tar.gz, any one version extracts on its own "
                              "and a ninth appends without rewriting a byte.",
        "bench_read_metadata": "Describing a snapshot cost {first} on the first and "
                               "{last} on the eighth, and {share} of everything the "
                               "later snapshots added. A manifest describes its whole "
                               "snapshot rather than a delta; FLAG_COMPRESSED_METADATA "
                               "is what stops that share from growing without bound.",
        "bench_read_cdc": "Inserting 64 bytes at the front of a 3 MB file costs {cdc} "
                          "with content-defined boundaries and {fixed} with fixed ones "
                          "— {factor}× more. That is what anla-cdc-1 is for.",
        "bench_rerun": "Reproduce this",
        "lang_switch": "中文",
        "en_only": "EN",
        "footer_left": "ANLA · Agent-Native Lossless Archive · EVEMISS Technology × EveMissLab",
        "footer_right": "Local-first · Lossless · Model-independent",
        "footer_license": "Apache-2.0",
        "footer_family": "EveMissLab",

        # landing
        "meta_home": "ANLA is a lossless archive format an AI can plan and a "
                     "deterministic, model-independent decoder must restore exactly. "
                     "Two reference implementations, cross-verified byte for byte.",
        "hero_eyebrow": "Research preview · Open format · Apache-2.0",
        "hero_h1_a": "Let an AI plan the packing.",
        "hero_h1_b": "Do not let an AI rewrite the truth.",
        "hero_lead": "ANLA is an archive format for agents. A model may choose the "
                     "chunking, the codec, the indexes and the order of work. A public, "
                     "deterministic decoder still has to return every byte that was "
                     "declared into the archive — with no model in the loop.",
        "hero_cta_1": "Open the workbench",
        "hero_cta_2": "Read the specification",
        "card_label": "Core invariant",
        "fact_lossless": "Lossless preservation",
        "fact_lossless_v": "Required",
        "fact_ai": "Decoder requires AI",
        "fact_ai_v": "No",
        "fact_impl": "Reference implementations",
        "fact_impl_v": "2, cross-verified",
        "fact_tests": "Conformance tests",
        "fact_tests_v": "634 + fuzzing",
        "strip_1_t": "Local-first",
        "strip_1_d": "The workbench runs entirely in your tab: your files are read "
                     "into memory and never sent anywhere. The page makes no requests "
                     "of its own, and its content policy forbids outbound connections.",
        "strip_2_t": "Deterministic",
        "strip_2_d": "Same input, same archive bytes — proven by two implementations "
                     "in two languages producing identical output.",
        "strip_3_t": "Inspectable",
        "strip_3_d": "Manifest, chunk map, codec choices and the planner's decision "
                     "log are all readable JSON.",
        "strip_4_t": "Experimental",
        "strip_4_d": "A research profile, frozen and tested — not yet somewhere to "
                     "keep the only copy of anything.",

        "why_kicker": "Control-plane transition",
        "why_h2": "Not another interface over ZIP.",
        "why_desc": "Traditional formats assume a human picks the files and a level, "
                    "and a fixed algorithm does the rest. ANLA turns the packing plan "
                    "into a structured control surface an agent can produce, a "
                    "validator can check and a writer can replay — while the format's "
                    "invariants refuse information loss.",
        "why_1_h": "An AI planner, never an AI decoder",
        "why_1_p": "A model may analyse the tree and emit a packing plan. The writer "
                   "validates that plan; the decoder restores without a model, ever.",
        "why_1_c": "Planner → Policy validator → Deterministic writer",
        "why_2_h": "Content addressing and deduplication",
        "why_2_p": "Every raw chunk is identified by the SHA-256 of its content, so "
                   "identical content is stored once no matter how many files "
                   "reference it, or which codec stored it.",
        "why_2_c": "chunk_id = SHA-256(raw bytes)",
        "why_3_h": "The intelligence layer is disposable",
        "why_3_p": "Search indexes, decision logs and model annotations live in a "
                   "plane you can empty completely. What a decoder extracts does not "
                   "change by one byte.",
        "why_3_c": "Decode(P, I) = Decode(P, ∅)",

        "arch_kicker": "Two planes",
        "arch_h2": "Intelligence can be rebuilt. Original data cannot.",
        "arch_desc": "ANLA separates the preservation truth that must not be "
                     "compromised from the AI-assisted data that may change freely. "
                     "This is not a visual grouping; it is the format's trust boundary.",
        "arch_p_tag": "Preservation plane",
        "arch_p_h": "Deterministic, required",
        "arch_p_p": "Raw payload chunks, the chunk map, paths, metadata, content "
                    "hashes and the snapshot root. Every conforming decoder must "
                    "reach the same result from these bytes.",
        "arch_i_tag": "Intelligence plane",
        "arch_i_h": "Disposable, rebuildable",
        "arch_i_p": "The packing plan a model produced, its decision log, full-text "
                    "and semantic indexes, agent history. Replaceable, deletable, "
                    "and never a precondition for extraction.",

        "proof_kicker": "What is actually true today",
        "proof_h2": "The claims, and what backs each one.",
        "proof_desc": "A format's promises are worth what its tests are worth. These "
                      "are the ones that run on every commit, on Linux, macOS and "
                      "Windows.",
        "proof_1_h": "Two implementations agree byte for byte",
        "proof_1_p": "A Python writer and a JavaScript writer, written separately "
                     "against the specification, produce identical archives for every "
                     "reproducible fixture — not merely archives each other can read.",
        "proof_2_h": "The first release's archive still verifies",
        "proof_2_p": "The .anla file shipped with the original v0.1 browser build is "
                     "checked into the repository as a compatibility vector, and both "
                     "implementations still restore it exactly.",
        "proof_3_h": "Corruption is refused, not tolerated",
        "proof_3_p": "Wrong hash, wrong length, unknown codec, unsafe path, duplicate "
                     "path, a compression bomb, an offset past the end of the file: "
                     "each has a test asserting the decoder fails instead of guessing.",
        "proof_4_h": "A filesystem that cannot restore an archive says so",
        "proof_4_p": "Two paths differing only by case, or by Unicode normalization, "
                     "are distinct here. Extracting onto a filesystem that folds them "
                     "fails with both names — it never silently drops one.",

        "state_kicker": "Honest scope",
        "state_h2": "What this profile does not do.",
        "state_desc": "The whitepaper describes a larger format: BLAKE3, Zstandard, "
                      "CBOR manifests, append-only snapshots, cross-platform "
                      "metadata, encryption, signatures, parity. ANLA-MVP v0.1 "
                      "implements the smallest subset that can be finished and "
                      "verified end to end, and claims nothing else.",
        "state_yes_h": "Implemented and tested",
        "state_yes_p": "Single snapshot · ordinary files and directories · fixed-size "
                       "and content-defined chunking · Store and DEFLATE · SHA-256 chunk identity · "
                       "canonical JSON manifest · cross-file deduplication · full "
                       "round-trip verification · reproducible output · safe paths · "
                       "resource limits · ZIP export.",
        "state_no_h": "Not implemented, not claimed",
        "state_no_p": "Symlinks · hard links · permissions and ACLs · extended "
                      "attributes · alternate data streams · sparse files · "
                      "Zstandard · BLAKE3 · encryption · signatures · parity · "
                      "append-only snapshots · partial materialization.",
        "state_warn": "This is a research profile. Do not make an ANLA archive the "
                      "only copy of anything you cannot lose.",

        "get_kicker": "Get it",
        "get_h2": "Read it, run it, or check it yourself.",
        "cta_demo_t": "Live test",
        "cta_demo_d": "Run the conformance suite in your own browser and watch every "
                      "assertion resolve. It starts on load.",
        "cta_workbench_t": "Live workbench",
        "cta_workbench_d": "Build and verify a real .anla in your browser. No backend.",
        "cta_standalone_t": "Standalone page",
        "cta_standalone_d": "One self-contained HTML file. Save it, open it offline, "
                            "it still works.",
        "cta_spec_t": "Specification",
        "cta_spec_d": "The normative definition of ANLA-MVP v0.1, byte layout included.",
        "cta_vectors_t": "Conformance vectors",
        "cta_vectors_d": "Frozen archives and their hashes, for a third implementation "
                         "to test against.",
        "cta_repo_t": "Source",
        "cta_repo_d": "Both reference implementations, the test suite and the papers.",
        "cta_papers_t": "Papers",
        "cta_papers_d": "The concept paper and the technical whitepaper behind the "
                        "format.",

        # workbench page
        "meta_workbench": "Build and verify a real ANLA-MVP v0.1 archive in your "
                          "browser. Nothing is uploaded.",
        "wb_kicker": "Standalone live workbench",
        "wb_h2": "Build a real .anla, right now.",
        "wb_desc": "This is not a simulator. The page runs web/anla-core.js — the same "
                   "reference implementation the conformance suite runs under Node — "
                   "using Web Crypto for SHA-256 and the platform's compression "
                   "streams for DEFLATE. Your files are read in this tab and are never "
                   "sent anywhere.",
        "wb_shell_title": "ANLA Standalone Workbench · Browser runtime",
        "wb_no_backend": "No backend required",
        "wb_tab_1": "01 · Build",
        "wb_tab_2": "02 · Open and verify",
        "wb_tab_3": "03 · Profile",
        "wb_side_note": "Browser mode covers ordinary files and directories, fixed "
                        "chunking, Store and DEFLATE. It does not preserve links, "
                        "permissions or extended attributes — and does not pretend to.",
        "wb_pick_h": "Choose a workspace",
        "wb_pick_p": "Use the folder field, or the native directory picker in "
                     "Chromium-based browsers. A plain file field cannot see empty "
                     "directories.",
        "wb_clear": "Clear",
        "wb_drop_strong": "Choose a folder, or drop files here",
        "wb_drop_small": "Everything is read inside this tab only.",
        "wb_native": "Native folder picker",
        "s_files": "Files",
        "s_dirs": "Directories",
        "s_logical": "Logical size",
        "s_root": "Root name",
        "f_compression": "Compression",
        "f_comp_auto": "Auto · keep DEFLATE only when it is smaller",
        "f_comp_deflate": "DEFLATE · always compress",
        "f_comp_store": "Store · never compress",
        "f_chunk": "Chunk size",
        "f_name": "Output filename",
        "f_level": "DEFLATE level (the browser may ignore it)",
        "f_exclude": "Exclusion globs, one per line",
        "chk_mtime": "Preserve modification times",
        "chk_verify": "Full verification after building",
        "chk_ai": "Decoder requires AI: false",
        "wb_build": "Build and verify",
        "wb_plan": "Preview the packing plan",
        "wb_result_ok": "Packed and fully verified",
        "wb_download": "Download .anla",
        "wb_restore": "Restore as ZIP",
        "wb_open_h": "Open an ANLA archive",
        "wb_open_p": "Verifies the bootstrap header, the footer, the manifest hash, "
                     "every chunk and every file — before offering you anything.",
        "wb_open_strong": "Choose or drop a .anla file",
        "wb_open_small": "Archives from this page, from the Python CLI, or from the "
                         "original v0.1 release.",
        "wb_open_ok": "Archive fully verified",
        "wb_extract": "Restore as ZIP",
        "wb_redownload": "Download the archive",
        "wb_search": "Search packed paths…",
        "wb_copy_manifest": "Copy manifest",
        "wb_profile_h": "Standalone profile v0.1",
        "wb_profile_p": "This page deliberately keeps to the smallest verifiable "
                        "scope. It does not claim the whitepaper's full cross-platform "
                        "metadata model.",
        "wb_prof_1_h": "Implemented",
        "wb_prof_1_p": "Single snapshot, ordinary files and directories, fixed and "
                       "content-defined chunking, Store and DEFLATE, SHA-256, canonical JSON "
                       "manifest, cross-file deduplication, full round trip, "
                       "reproducible output.",
        "wb_prof_2_h": "Not implemented",
        "wb_prof_2_p": "Symlinks, hard links, ACLs, alternate data streams, sparse "
                       "files, Zstandard, BLAKE3, encryption, signatures, "
                       "append-only snapshots.",
        "wb_prof_3_h": "Safety boundary",
        "wb_prof_3_p": "Declared lengths are bounded before allocation, unsafe and "
                       "duplicate paths are refused, unknown codecs and record types "
                       "fail rather than being skipped.",
        "wb_prof_4_h": "Self-test",
        "wb_prof_4_p": "Append ?selftest=1 to this URL and the page packs, verifies, "
                       "re-packs and compares a fixture against itself, then reports "
                       "PASS or FAIL in the corner.",
        "wb_selftest_link": "Run the self-test",

        # workbench runtime strings (consumed by app.js)
        "runtime_ready": "Browser runtime ready",
        "runtime_store_only": "Runtime ready · Store only",
        "cap_crypto": "SHA-256",
        "cap_deflate": "DEFLATE",
        "native": "native",
        "fallback": "software fallback",
        "available": "available",
        "store_only": "unavailable",
        "waiting_for_selection": "Waiting for a selection",
        "ready_to_build": "Ready to build",
        "more_files": "more files",
        "busy_build_title": "Building the archive",
        "busy_build_detail": "Hashing, chunking, deduplicating, compressing, then "
                             "verifying the whole round trip…",
        "busy_open_title": "Verifying the archive",
        "busy_open_detail": "Header, footer, manifest, every chunk, every file…",
        "busy_zip_title": "Restoring",
        "busy_zip_detail": "Reassembling verified content into a ZIP…",
        "build_done": "Built and verified",
        "build_failed": "Build failed",
        "build_ok": "Packed and verified",
        "open_ok": "Archive verified",
        "zip_ok": "Restored",
        "plan_preview": "Packing plan preview",
        "plan_note": "A plan is a proposal. The writer validates it before any byte "
                     "is written.",
        "manifest_copied": "Manifest copied as canonical JSON",
        "clipboard_failed": "The clipboard is unavailable in this context",
        "picker_unsupported": "This browser has no native directory picker",
        "no_matches": "No matching path",
        "dir_label": "directory",
        "m_files": "Files",
        "m_dirs": "Directories",
        "m_logical": "Logical",
        "m_archive": "Archive",
        "m_chunks": "Chunks unique/refs",
        "m_stored": "Stored payload",
        "m_ratio": "Ratio",
        "m_verified": "Verified files",
        "m_format": "Format",
        "m_uuid": "Archive UUID",
        "m_needs_ai": "Decoder needs AI",

        # papers index
        "meta_papers": "The concept paper and the technical whitepaper behind ANLA.",
        "papers_kicker": "Research",
        "papers_h2": "The papers behind the format.",
        "papers_desc": "Two documents, both written before the implementation existed. "
                       "The Traditional Chinese versions are canonical; the English "
                       "versions are faithful renditions.",
        "paper_1_t": "From Path Containers to Intelligent Packaging",
        "paper_1_s": "The control-plane transition thesis for AI-native lossless "
                     "archive formats",
        "paper_1_d": "Why the next step in archive formats may be the control plane "
                     "rather than the codec — and the boundary that keeps AI-native "
                     "from meaning generative. Includes the conditions that would "
                     "refute the thesis.",
        "paper_2_t": "ANLA v0.1 Technical Whitepaper",
        "paper_2_s": "Agent-Native Lossless Archive Format",
        "paper_2_d": "The target format: object model, binary container, manifests and "
                     "snapshots, chunking and codecs, the agent planning interface, "
                     "security, conformance profiles and the milestone roadmap.",
        "paper_read": "Read",
        "paper_original": "Traditional Chinese original",
        "paper_translation": "English translation",
        "spec_card_t": "ANLA-MVP v0.1 — Normative specification",
        "spec_card_d": "What is actually implemented, frozen and cross-verified. The "
                       "whitepaper is the target; this is the part that is done.",

        # doc pages
        "doc_toc": "On this page",
        "doc_source": "Source file",
        "doc_meta_author": "Author",
        "doc_meta_date": "Date",
        "doc_meta_status": "Status",
        "doc_meta_version": "Version",
        "doc_meta_lang": "Language",
        "doc_translation_note": "This is an English rendition. The Traditional Chinese "
                                "original remains the canonical text.",
        "doc_spec_note": "The specification is maintained in English only. A format "
                         "specification with two normative language versions has two "
                         "normative versions, which is a defect rather than a feature.",
        "doc_read_zh": "Read the Traditional Chinese original",
        "doc_read_en": "Read the English translation",
    },
    "zh": {
        "html_lang": "zh-Hant",
        "site_name": "ANLA",
        "site_tagline": "代理原生無損封裝格式",
        "nav_home": "總覽",
        "nav_workbench": "工作台",
        "nav_spec": "規格",
        "nav_papers": "論文",
        "nav_conformance": "一致性",
        "nav_bench": "實測數據",
        "nav_repo": "原始碼",
        "bench_kicker": "量出來的，不是宣稱的",
        "bench_h1": "ANLA 對真實位元組做了什麼",
        "bench_desc": "五個情境，跑在這個儲存庫自己的 git 歷史上，並且跟一般人真的會拿來用的"
                      "替代方案對比。每一個數字都由 bench/run_bench.py 產生並寫進一份 JSON，"
                      "這個頁面是從那份 JSON 生成的——所以頁面說不出任何量測程式沒有量到的東西，"
                      "包含 ANLA 輸掉的那幾列。",
        "bench_warning_h": "ANLA 1.0 不做壓縮。",
        "bench_warning": "它唯一的 codec 是 store。以下每一個比值都是「去重」。因此單一 snapshot "
                         "若檔案彼此不重複，封裝會比原樹更大，而一般用途的壓縮器會贏得很輕鬆。"
                         "那個情境放在第一列而不是被省略掉——一個你不可能輸的基準，不是基準。",
        "bench_measured": "量測於",
        "bench_stack": "組態",
        "bench_input": "輸入",
        "bench_smaller": "越小越好",
        "bench_of_input": "為輸入的",
        "bench_composition_h": "每個 snapshot 的位元組去了哪裡",
        "bench_composition": "新內容，對比「描述它」的代價。manifest 描述的是它整個 snapshot "
                             "而不是差異，這一欄就是那個決定的價格。",
        "bench_col_snapshot": "第幾個",
        "bench_col_content": "新內容",
        "bench_col_metadata": "描述資料",
        "bench_reading_h": "這張表指出接下來該做什麼",
        "bench_read_codec": "一棵原始碼樹的單一 snapshot，是同一棵樹 tar.gz 的 {ratio} 倍。"
                            "這個差距是「少了一個 codec」，不是「設計不對」——"
                            "而這就是該做 Zstandard 的全部理由。",
        "bench_read_history": "同一棵樹的八個版本，是「八個版本包成一個 tar.gz」的 "
                              "{ratio} 倍——而且完全沒有壓縮。跟 tar.gz 不同的是，"
                              "任何一個版本都能單獨取出，而且第九個可以附加上去而不重寫任何一個位元組。",
        "bench_read_metadata": "描述一個 snapshot 的成本，第一個是 {first}、第八個是 {last}，"
                               "並且佔了後續 snapshot 所新增內容的 {share}。manifest 描述的是"
                               "它整個 snapshot 而不是差異；FLAG_COMPRESSED_METADATA 就是用來阻止"
                               "那個比例無限地成長下去。",
        "bench_read_cdc": "在一個 3 MB 檔案最前面插入 64 個位元組，內容定義邊界的成本是 {cdc}，"
                          "固定切塊是 {fixed}——多了 {factor} 倍。這就是 anla-cdc-1 存在的理由。",
        "bench_rerun": "自己重跑一次",
        "lang_switch": "English",
        "en_only": "英文",
        "footer_left": "ANLA · 代理原生無損封裝格式 · 一言諾科技 × EveMissLab",
        "footer_right": "本機優先 · 無損 · 不依賴模型",
        "footer_license": "Apache-2.0",
        "footer_family": "EveMissLab",

        "meta_home": "ANLA 是一種可由 AI 規劃、但必須由確定性且不依賴模型的解碼器"
                     "精確還原的無損封裝格式。兩套參考實作，逐位元互相驗證。",
        "hero_eyebrow": "研究預覽 · 開放格式 · Apache-2.0",
        "hero_h1_a": "讓 AI 規劃封裝，",
        "hero_h1_b": "不讓 AI 改寫真相。",
        "hero_lead": "ANLA 是面向 Agent 的封裝格式。模型可以選擇分塊、Codec、索引與"
                     "工作順序；公開且確定性的解碼器仍然必須把所有已納入封裝的位元"
                     "原封不動交回來——過程中沒有任何模型參與。",
        "hero_cta_1": "打開工作台",
        "hero_cta_2": "閱讀規格",
        "card_label": "核心不變量",
        "fact_lossless": "無損保存",
        "fact_lossless_v": "必要",
        "fact_ai": "解碼需要 AI",
        "fact_ai_v": "否",
        "fact_impl": "參考實作",
        "fact_impl_v": "2 套，互相驗證",
        "fact_tests": "一致性測試",
        "fact_tests_v": "634 項 + 模糊測試",
        "strip_1_t": "本機優先",
        "strip_1_d": "工作台完全在你的分頁裡執行：檔案只讀進記憶體，不會被送到任何"
                     "地方。頁面本身不發出任何請求，其內容安全政策也禁止對外連線。",
        "strip_2_t": "確定性",
        "strip_2_d": "相同輸入產生相同的封裝位元——由兩種語言的兩套實作產生完全一致"
                     "的輸出來證明。",
        "strip_3_t": "可檢視",
        "strip_3_d": "Manifest、Chunk Map、Codec 選擇與規劃器的決策紀錄，全部是可讀"
                     "的 JSON。",
        "strip_4_t": "實驗性",
        "strip_4_d": "已凍結並測試過的研究 Profile——但還不是拿來存放唯一副本的地方。",

        "why_kicker": "控制平面轉移",
        "why_h2": "不是再做一個 ZIP 介面。",
        "why_desc": "傳統格式預設人類選檔案、選壓縮等級，其餘交給固定演算法。ANLA 把"
                    "封裝計畫變成可由 Agent 產生、可由驗證器檢查、可由寫入器重放的"
                    "結構化控制面；同時用格式的不變量拒絕資訊失真。",
        "why_1_h": "AI 是規劃器，永遠不是解碼器",
        "why_1_p": "模型可以分析檔案樹並產生封裝計畫；寫入器負責驗證計畫，解碼器則"
                   "在完全沒有模型的情況下還原。",
        "why_1_c": "Planner → Policy Validator → 確定性 Writer",
        "why_2_h": "內容定址與去重",
        "why_2_p": "每個原始 Chunk 以內容的 SHA-256 作為身分，因此相同內容只保存一"
                   "次——不論被幾個檔案引用，也不論當初用哪個 Codec 儲存。",
        "why_2_c": "chunk_id = SHA-256(raw bytes)",
        "why_3_h": "智能層可以整層丟棄",
        "why_3_p": "搜尋索引、決策紀錄與模型標註都住在一個可以被清空的平面裡。清空"
                   "之後，解碼器取出的內容一個位元都不會改變。",
        "why_3_c": "Decode(P, I) = Decode(P, ∅)",

        "arch_kicker": "兩個平面",
        "arch_h2": "智能可以重建，原始資料不行。",
        "arch_desc": "ANLA 把不可妥協的保存真相，跟可以自由變動的 AI 輔助資料分開。"
                     "這不是視覺分類，而是格式的信任邊界。",
        "arch_p_tag": "保存平面",
        "arch_p_h": "確定性、必要",
        "arch_p_p": "原始 Payload Chunk、Chunk Map、路徑、Metadata、內容雜湊與 "
                    "Snapshot Root。任何符合規格的解碼器都必須從這些位元得到相同"
                    "結果。",
        "arch_i_tag": "智能平面",
        "arch_i_h": "可拋棄、可重建",
        "arch_i_p": "模型產生的封裝計畫、決策紀錄、全文與語義索引、Agent 操作歷史。"
                    "可替換、可刪除，而且永遠不是解壓的前提。",

        "proof_kicker": "今天真正成立的部分",
        "proof_h2": "每一個宣稱，各自由什麼支撐。",
        "proof_desc": "一個格式的承諾值多少，取決於它的測試值多少。以下這些在每次"
                      "commit 都會在 Linux、macOS 與 Windows 上跑一遍。",
        "proof_1_h": "兩套實作逐位元一致",
        "proof_1_p": "Python 寫入器與 JavaScript 寫入器各自依規格獨立實作，對每個可"
                     "重現的 fixture 產生完全相同的封裝——不只是彼此讀得懂而已。",
        "proof_2_h": "第一版發布的封裝檔仍然驗證通過",
        "proof_2_p": "原始 v0.1 瀏覽器版所附的 .anla 檔以相容性測試向量的身分留在"
                     "repo 裡，兩套實作至今都能精確還原它。",
        "proof_3_h": "遇到損壞就拒絕，不將就",
        "proof_3_p": "雜湊不符、長度不符、未知 Codec、不安全路徑、重複路徑、壓縮"
                     "炸彈、超出檔尾的位移：每一種都有測試斷言解碼器必須失敗而不是"
                     "猜測。",
        "proof_4_h": "還原不了的檔案系統會說出來",
        "proof_4_p": "只差大小寫、或只差 Unicode 正規化形式的兩個路徑在這裡是不同"
                     "路徑。在會把它們折疊成同一個檔案的系統上解壓會失敗，並同時"
                     "報出兩個路徑——絕不默默丟掉其中一個。",

        "state_kicker": "誠實的範圍",
        "state_h2": "這個 Profile 沒有做到什麼。",
        "state_desc": "白皮書描述的是更大的格式：BLAKE3、Zstandard、CBOR Manifest、"
                      "追加式 Snapshot、跨平台 Metadata、加密、簽章、Parity。"
                      "ANLA-MVP v0.1 只實作能夠端到端完成並驗證的最小子集，並且不"
                      "宣稱其他任何事。",
        "state_yes_h": "已實作並測試",
        "state_yes_p": "單一 Snapshot · 普通檔案與目錄 · 固定分塊與內容定義分塊 · Store 與 DEFLATE "
                       "· SHA-256 Chunk 身分 · Canonical JSON Manifest · 跨檔去重 · "
                       "完整 Round Trip 驗證 · 可重現輸出 · 安全路徑 · 資源限制 · "
                       "ZIP 匯出。",
        "state_no_h": "未實作，也不宣稱",
        "state_no_p": "Symlink · Hard Link · 權限與 ACL · Extended Attributes · "
                      "Alternate Data Streams · 稀疏檔 · Zstandard · "
                      "BLAKE3 · 加密 · 簽章 · Parity · 追加式 Snapshot · 局部物化。",
        "state_warn": "這是研究用 Profile。不要讓 ANLA 封裝成為任何不能遺失的資料的"
                      "唯一副本。",

        "get_kicker": "取用",
        "get_h2": "讀它、跑它，或者自己驗它。",
        "cta_demo_t": "即時測試",
        "cta_demo_d": "在你自己的瀏覽器裡執行一致性測試，看每一項斷言逐一定案。"
                      "開頁即自動開始。",
        "cta_workbench_t": "線上工作台",
        "cta_workbench_d": "在瀏覽器裡建立並驗證一個真正的 .anla，不需要後端。",
        "cta_standalone_t": "獨立單檔頁面",
        "cta_standalone_d": "一個自帶所有內容的 HTML 檔。存下來、離線打開，照樣可用。",
        "cta_spec_t": "規格",
        "cta_spec_d": "ANLA-MVP v0.1 的規範定義，含完整位元布局。",
        "cta_vectors_t": "一致性測試向量",
        "cta_vectors_d": "凍結的封裝檔與其雜湊，供第三套實作對照測試。",
        "cta_repo_t": "原始碼",
        "cta_repo_d": "兩套參考實作、測試套件與論文。",
        "cta_papers_t": "論文",
        "cta_papers_d": "格式背後的概念論文與技術白皮書。",

        "meta_workbench": "在瀏覽器裡建立並驗證真正的 ANLA-MVP v0.1 封裝，不上傳任何"
                          "資料。",
        "wb_kicker": "獨立線上工作台",
        "wb_h2": "現在就建立一個真正的 .anla。",
        "wb_desc": "這不是模擬器。這個頁面執行的是 web/anla-core.js——與一致性測試在 "
                   "Node 下執行的同一份參考實作——用 Web Crypto 算 SHA-256，用平台的"
                   "壓縮串流做 DEFLATE。你的檔案不會離開這個分頁。",
        "wb_shell_title": "ANLA 獨立工作台 · 瀏覽器執行環境",
        "wb_no_backend": "不需要後端",
        "wb_tab_1": "01 · 建立封裝",
        "wb_tab_2": "02 · 開啟與驗證",
        "wb_tab_3": "03 · Profile 狀態",
        "wb_side_note": "瀏覽器模式涵蓋普通檔案與目錄、固定分塊、Store 與 DEFLATE。"
                        "它不保存連結、權限或 Extended Attributes——而且不假裝有。",
        "wb_pick_h": "選擇工作空間",
        "wb_pick_p": "使用資料夾欄位，或 Chromium 系瀏覽器的原生目錄選擇器。一般的"
                     "檔案欄位看不到空目錄。",
        "wb_clear": "清除",
        "wb_drop_strong": "選擇資料夾，或把檔案拖進來",
        "wb_drop_small": "所有檔案只在這個分頁裡讀取。",
        "wb_native": "原生資料夾選擇器",
        "s_files": "檔案",
        "s_dirs": "目錄",
        "s_logical": "邏輯大小",
        "s_root": "根名稱",
        "f_compression": "壓縮策略",
        "f_comp_auto": "Auto · 只有變小才保留 DEFLATE",
        "f_comp_deflate": "DEFLATE · 一律壓縮",
        "f_comp_store": "Store · 一律不壓縮",
        "f_chunk": "Chunk 大小",
        "f_name": "輸出檔名",
        "f_level": "DEFLATE 等級（瀏覽器可能忽略）",
        "f_exclude": "排除規則（Glob，每行一個）",
        "chk_mtime": "保存修改時間",
        "chk_verify": "建立後完整驗證",
        "chk_ai": "解碼需要 AI：false",
        "wb_build": "建立並驗證",
        "wb_plan": "預覽封裝計畫",
        "wb_result_ok": "封裝完成且完整驗證通過",
        "wb_download": "下載 .anla",
        "wb_restore": "還原為 ZIP",
        "wb_open_h": "開啟 ANLA 封裝",
        "wb_open_p": "在把任何東西交給你之前，先驗證 Bootstrap Header、Footer、"
                     "Manifest 雜湊、每一個 Chunk 與每一個檔案。",
        "wb_open_strong": "選擇或拖入 .anla",
        "wb_open_small": "可以是這個頁面、Python CLI，或原始 v0.1 發布版建立的封裝。",
        "wb_open_ok": "封裝完整驗證通過",
        "wb_extract": "還原為 ZIP",
        "wb_redownload": "下載原封裝",
        "wb_search": "搜尋封裝內路徑…",
        "wb_copy_manifest": "複製 Manifest",
        "wb_profile_h": "獨立頁面 Profile v0.1",
        "wb_profile_p": "這個頁面刻意維持在最小可驗證範圍，不宣稱完成白皮書的完整"
                        "跨平台 Metadata 模型。",
        "wb_prof_1_h": "已實作",
        "wb_prof_1_p": "單 Snapshot、普通檔案與目錄、固定分塊與內容定義分塊、Store 與 DEFLATE、"
                       "SHA-256、Canonical JSON Manifest、跨檔去重、完整 Round Trip、"
                       "可重現輸出。",
        "wb_prof_2_h": "未實作",
        "wb_prof_2_p": "Symlink、Hard Link、ACL、Alternate Data Streams、稀疏檔、"
                       "Zstandard、BLAKE3、加密、簽章、追加式 Snapshot。",
        "wb_prof_3_h": "安全邊界",
        "wb_prof_3_p": "所有宣告長度在配置記憶體前先設界，不安全與重複路徑一律拒絕，"
                       "未知 Codec 與未知 Record 類型會失敗而不是被跳過。",
        "wb_prof_4_h": "自我測試",
        "wb_prof_4_p": "在網址後面加上 ?selftest=1，頁面會自己封裝、驗證、再封裝一次"
                       "並比對位元，然後在角落顯示 PASS 或 FAIL。",
        "wb_selftest_link": "執行自我測試",

        "runtime_ready": "瀏覽器環境就緒",
        "runtime_store_only": "環境就緒 · 僅 Store",
        "cap_crypto": "SHA-256",
        "cap_deflate": "DEFLATE",
        "native": "原生",
        "fallback": "軟體實作",
        "available": "可用",
        "store_only": "不可用",
        "waiting_for_selection": "等待選擇資料",
        "ready_to_build": "可以建立",
        "more_files": "個檔案未列出",
        "busy_build_title": "正在建立封裝",
        "busy_build_detail": "計算雜湊、分塊、去重、壓縮，並執行完整 Round Trip "
                             "驗證…",
        "busy_open_title": "正在驗證封裝",
        "busy_open_detail": "Header、Footer、Manifest、每個 Chunk、每個檔案…",
        "busy_zip_title": "正在還原",
        "busy_zip_detail": "把已驗證的內容重新組成 ZIP…",
        "build_done": "已建立並驗證",
        "build_failed": "建立失敗",
        "build_ok": "封裝並驗證完成",
        "open_ok": "封裝驗證通過",
        "zip_ok": "已還原",
        "plan_preview": "封裝計畫預覽",
        "plan_note": "計畫只是提案。在寫下任何一個位元之前，寫入器會先驗證它。",
        "manifest_copied": "已以 Canonical JSON 複製 Manifest",
        "clipboard_failed": "此環境無法使用剪貼簿",
        "picker_unsupported": "這個瀏覽器沒有原生目錄選擇器",
        "no_matches": "沒有符合的路徑",
        "dir_label": "目錄",
        "m_files": "檔案",
        "m_dirs": "目錄",
        "m_logical": "邏輯大小",
        "m_archive": "封裝大小",
        "m_chunks": "Chunk 唯一/引用",
        "m_stored": "儲存 Payload",
        "m_ratio": "比率",
        "m_verified": "已驗證檔案",
        "m_format": "格式",
        "m_uuid": "封裝 UUID",
        "m_needs_ai": "解碼需要 AI",

        "meta_papers": "ANLA 背後的概念論文與技術白皮書。",
        "papers_kicker": "研究",
        "papers_h2": "格式背後的兩篇論文。",
        "papers_desc": "兩份文件都寫在實作存在之前。繁體中文版為正本，英文版是忠實"
                       "轉譯。",
        "paper_1_t": "從路徑容器到智能封裝",
        "paper_1_s": "AI 原生無損壓縮格式的控制平面轉移命題",
        "paper_1_d": "為什麼封裝格式的下一步可能出現在控制平面而不是 Codec，以及那"
                     "條讓「AI 原生」不等於「生成式」的邊界。文中也列出可以反駁這個"
                     "命題的條件。",
        "paper_2_t": "ANLA v0.1 技術白皮書",
        "paper_2_s": "Agent-Native Lossless Archive Format",
        "paper_2_d": "目標格式的全貌：物件模型、二進位容器、Manifest 與 Snapshot、"
                     "分塊與 Codec、Agent 規劃介面、安全、Conformance Profile 與"
                     "里程碑路線。",
        "paper_read": "閱讀",
        "paper_original": "繁體中文正本",
        "paper_translation": "英文轉譯",
        "spec_card_t": "ANLA-MVP v0.1 — 規範規格",
        "spec_card_d": "真正已實作、已凍結、已互相驗證的部分。白皮書是目標，這份是"
                       "做完的那一段。",

        "doc_toc": "本頁目錄",
        "doc_source": "原始檔",
        "doc_meta_author": "作者",
        "doc_meta_date": "日期",
        "doc_meta_status": "狀態",
        "doc_meta_version": "版本",
        "doc_meta_lang": "語言",
        "doc_translation_note": "這是英文轉譯版。繁體中文正本仍為權威文本。",
        "doc_spec_note": "規格僅以英文維護。一份規格若有兩個規範語言版本，就等於有"
                         "兩份規範——那是缺陷，不是功能。",
        "doc_read_zh": "閱讀繁體中文正本",
        "doc_read_en": "閱讀英文轉譯版",
    },
}

# Keys app.js reads at runtime; the build injects exactly these into the page.
WORKBENCH_KEYS = (
    "runtime_ready", "runtime_store_only", "cap_crypto", "cap_deflate", "native",
    "fallback", "available", "store_only", "waiting_for_selection", "ready_to_build",
    "more_files", "busy_build_title", "busy_build_detail", "busy_open_title",
    "busy_open_detail", "busy_zip_title", "busy_zip_detail", "build_done",
    "build_failed", "build_ok", "open_ok", "zip_ok", "plan_preview", "plan_note",
    "manifest_copied", "clipboard_failed", "picker_unsupported", "no_matches",
    "dir_label", "m_files", "m_dirs", "m_logical", "m_archive", "m_chunks",
    "m_stored", "m_ratio", "m_verified", "m_format", "m_uuid", "m_needs_ai",
)

from demo_content import DEMO_STRINGS, demo_keys  # noqa: E402

for _lang, _extra in DEMO_STRINGS.items():
    STRINGS[_lang].update(_extra)

# One i18n asset per language serves both the workbench and the live test page.
RUNTIME_KEYS = WORKBENCH_KEYS + demo_keys(WORKBENCH_KEYS)


# ---------------------------------------------------------------------------
# benchmark scenarios
# ---------------------------------------------------------------------------

#: Traditional Chinese copy for each benchmark scenario, keyed by the id the
#: harness emits. The English lives in `bench/results.json`, written by
#: `bench/run_bench.py`, so each language has exactly one home and neither can
#: drift from the other. A scenario the harness produces and this table does not
#: cover is a build error, not an English fallback — a page that silently switches
#: language is a page nobody notices is incomplete.
BENCH_ZH: dict[str, dict[str, str]] = {
    "metadata-cost": {
        "headline": "500 個檔案：命名空間化的 metadata 跟 500 個 symlink 多花了多少",
        "note": "Milestone 2 不會移動任何一個壓縮數字，因為它本來就不是在談壓縮"
                "——它是「讓工具能打包以前直接拒絕的樹」。"
                "這就是它在 manifest 裡、每個物件的帳單。",
    },
    "source-tree": {
        "headline": "這個儲存庫的 python/ 目錄，單一 snapshot",
        "note": "ANLA 1.0 只儲存，不壓縮。所以單一 snapshot 會比原樹更大，兩種壓縮器都贏它。"
                "這一列就是「該做 Zstandard」這個主張，寫成一次量測。",
    },
    "git-history": {
        "headline": "python/ 連續 8 個 commit，每個一個 snapshot",
        "note": "每一個版本都逐位元可還原。對照組是「每個版本各存一個 ZIP」——沒有 snapshot 的人"
                "就是這樣做的——以及「全部版本一個 tar.gz」。gzip 的視窗只有 32 KB，看不到"
                "從這一份原始碼樹到下一份，這正是為什麼去重是另一套機制，而不是比較差的壓縮。",
    },
    "duplicate-tree": {
        "headline": "同一個目錄連續 snapshot 五次，內容完全沒變",
        "note": "去重的上限。第 2 到第 5 個 snapshot 只多了一份 manifest 跟一個 footer，"
                "所以它們的成本就是 snapshot 設計裡第一個決定的價格：manifest 描述的是"
                "它整個 snapshot，而不是差異。",
    },
    "incompressible": {
        "headline": "2 MB 隨機位元組，然後同一個檔案再來一次",
        "note": "這種資料沒有東西壓得動，也不該壓得動。第一個 snapshot 比原檔略大；"
                "第二個幾乎不用錢——去重不在乎位元組壓不壓得動。",
    },
    "shifted-insert": {
        "headline": "3 MB 檔案，然後在最前面插入 64 個位元組",
        "note": "固定切塊撐不過的情境：每一個邊界都位移了，所以沒有任何一個 chunk 對得上，"
                "整個檔案被存第二次。內容定義的邊界跟著內容走，所以只有真正改變的 chunk 是新的。",
    },
}
