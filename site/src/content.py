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
        "nav_context": "Agent memory",
        "nav_repo": "Source",

        # ---- the context / MCP page -------------------------------------
        "ctx_kicker": "The second thing this turned out to be",
        "ctx_h1": "An agent that remembers its own history, exactly",
        "ctx_desc": "An archive that preserves bytes exactly and expands any part of "
                    "itself on demand is also a description of what a model needs "
                    "from its own context. The same package carries a context layer, "
                    "reachable over MCP: remember losslessly, address semantically, "
                    "and get the record itself back — not a summary of it.",
        "ctx_loop_h": "The loop, and what each step has to hold up",
        "ctx_loop_tool": "Tool",
        "ctx_loop_claim": "The claim it has to hold up",
        "ctx_loop_1": "Every byte of the transcript, or a refusal. A limit that "
                      "would drop the front of a conversation is an error, not a "
                      "quiet truncation.",
        "ctx_loop_2": "An index family over the turns — and the archive is "
                      "byte-identical before and after, which is checked rather "
                      "than asserted.",
        "ctx_loop_3": "The views to embed, with the identity that must come back "
                      "with them, and a sample that names which part of the record "
                      "it covered.",
        "ctx_loop_4": "Vectors into the auxiliary plane: a sidecar beside the "
                      "archive, never a record inside it.",
        "ctx_loop_5": "A question in, (turn, start_byte, end_byte) out, with the "
                      "turn's digest re-checked against what the index was built "
                      "from.",
        "ctx_idx_kicker": "The idea the design rests on",
        "ctx_idx_h": "A segment is an index, never a stored fragment",
        "ctx_idx_p": "From Neo.K's 同一性微積分: 切割 = 索引 — a cut adds a perspective "
                     "and leaves the object whole. So a segment is (turn, "
                     "start_byte, end_byte) in the auxiliary plane, several schemes "
                     "coexist over one record, re-cutting rewrites nothing, and a "
                     "segmenter is allowed to be wrong.",
        "ctx_idx_a_h": "Ontological layer",
        "ctx_idx_a_p": "The turn, stored whole in the preservation plane, untouched "
                       "by any cutting. Its digest is the same before indexing, "
                       "after two different schemes, and after every retrieval.",
        "ctx_idx_b_h": "Presentation layer",
        "ctx_idx_b_p": "Segments as raw byte offsets into that turn. A better "
                       "segmenter later produces a new index family; the record is "
                       "untouched, so choosing between schemes is a measurement "
                       "rather than a migration.",
        "ctx_m_kicker": "Measured on this repository's own development transcript",
        "ctx_m_h": "What it costs and what it returns",
        "ctx_m_desc": "Every figure below was produced by bench/context_bench.py "
                      "into a JSON file this page is generated from, stamped with "
                      "the revision and the corpus digest it was measured against.",
        "ctx_m_record": "The record",
        "ctx_m_index": "The index",
        "ctx_m_vectors": "The vector plane",
        "ctx_m_search": "The search",
        "ctx_m_wire": "Over the wire",
        "ctx_m_turns": "turns",
        "ctx_m_lossless": "lossless — every byte of the transcript is in the archive",
        "ctx_m_partial": "PARTIAL — the front of the transcript was dropped",
        "ctx_m_segments": "segments",
        "ctx_m_median": "median",
        "ctx_m_coverage": "coverage",
        "ctx_m_coverage_note": "no byte of any turn is unreachable through the "
                               "index, and none is covered twice",
        "ctx_m_unchanged": "preservation digest unchanged through indexing",
        "ctx_m_changed": "PRESERVATION DIGEST CHANGED — the invariant is broken",
        "ctx_m_json": "JSON array of decimals",
        "ctx_m_binary": "float32 behind a JSON header",
        "ctx_m_size": "size",
        "ctx_m_load": "load",
        # A whole phrase rather than a suffix: "5.1×" + "smaller" composes in
        # English and doubles the multiplier in Chinese, where × already reads 倍.
        "ctx_m_compare": "{smaller}× smaller · {faster}× faster to load",
        "ctx_m_model": "Model",
        "ctx_m_queries": "labelled queries",
        "ctx_m_numpy": "with NumPy",
        "ctx_m_pure": "pure Python",
        "ctx_m_pure_note": "NumPy is optional and the preservation plane never needs "
                           "it. The pure-Python path refuses only when its own "
                           "projection passes a stated 30-second budget, and it "
                           "quotes the projection so you can disagree with the "
                           "estimate rather than with a constant.",
        "ctx_m_median_query": "median for a whole addressed query",
        "ctx_m_verified": "of them returned digest-verified exact bytes",
        "ctx_m_incomparable": "A 64-wide query against a 768-wide corpus",
        "ctx_r_kicker": "Does segmenting actually help?",
        "ctx_r_h": "Twelve labelled queries, one pinned corpus",
        "ctx_r_desc": "Ground truth is located by exact search for a distinctive "
                      "anchor string — and the question is then written to avoid "
                      "that anchor entirely. So the label comes from a match the "
                      "retriever never sees, and the query is exactly the case "
                      "lexical search cannot answer.",
        "ctx_r_scheme": "Scheme",
        "ctx_r_segments": "Segments",
        "ctx_r_p95": "p95",
        "ctx_r_median_rank": "Median rank",
        "ctx_r_baseline": "baseline",
        "ctx_r_control": "control",
        "ctx_r_find_1_h": "The control beat the scheme it controls for.",
        "ctx_r_find_1_p": "Cutting every ~900 bytes did better than reading the "
                          "document's own headings, paragraph breaks and code "
                          "fences. So that structure was not carrying the "
                          "information, and the scheme that parses it earned nothing "
                          "over arithmetic. What works is cutting where the "
                          "vocabulary changes — the only one of the three that looks "
                          "at content.",
        "ctx_r_find_2_h": "The stated p95 gate failed on every row, including the "
                          "winner.",
        "ctx_r_find_2_p": "It wanted centred random-pair p95 below +0.15, calibrated "
                          "against a baseline of +0.238 measured on a third of this "
                          "corpus — where the baseline is now +0.443. The winning "
                          "scheme halves the crowding, which is what the gate was "
                          "reaching for, and the gate as written still failed. It is "
                          "reported failed here and in the JSON, because a threshold "
                          "re-read after the fact to mean whatever the result "
                          "supports is not a threshold.",
        "ctx_ref_kicker": "Three refusals",
        "ctx_ref_h": "The load-bearing part is what it declines to answer",
        "ctx_ref_1_h": "Identity before similarity",
        "ctx_ref_1_p": "Two 768-wide vectors from different models — or one model "
                       "over two different preprocessings — compare to a confident, "
                       "meaningless number, and nothing downstream can tell. Model, "
                       "revision, dimensions, projection version and segmentation "
                       "scheme must all agree, or the answer is INCOMPARABLE rather "
                       "than a value. Width is not identity.",
        "ctx_ref_2_h": "A capture that would not be lossless",
        "ctx_ref_2_p": "A byte limit that would drop the front of a transcript is "
                       "refused. Taken deliberately, the result is reported as "
                       "partial and names the byte range it dropped — because every "
                       "downstream claim would otherwise be stated over a record the "
                       "caller believes is whole.",
        "ctx_ref_3_h": "A search over part of the record",
        "ctx_ref_3_p": "A vectorised corpus covering a tenth of the index still "
                       "returns its nearest hit, and that answer is indistinguishable "
                       "from a complete search unless the share is stated. It is "
                       "stated, on every call.",
        "ctx_run_h": "Run it",
        "ctx_run_p": "Twenty tools over stdio. Nothing here computes an embedding: "
                     "the vectors come from whatever model the agent already has, "
                     "and the identity travels with them so a local or browser model "
                     "can replace the one used here without anything silently "
                     "comparing across the two.",
        "ctx_run_note": "The retrieval table needs an embedding model; everything "
                        "else on this page runs offline.",
        "ctx_cta_t": "Agent memory",
        "ctx_cta_d": "Remember, index, address, expand — over MCP, measured",

        "bench_kicker": "Measured, not claimed",
        "bench_h1": "What ANLA does to real bytes",
        "bench_desc": "Five scenarios, run against this repository's own git history "
                      "and against the alternatives a person would actually reach for. "
                      "Every figure is produced by bench/run_bench.py and written to a "
                      "JSON file this page is generated from, so the page cannot say "
                      "anything the harness did not measure — including the rows where "
                      "ANLA loses.",
        "bench_warning_h": "Deduplication and compression are different mechanisms.",
        "bench_warning": "Zstandard landed on 2026-08-07; before it, every figure here "
                         "was deduplication alone and a single snapshot was larger "
                         "than the tree it held. The store-only line is kept beside "
                         "the compressed one in the rows where it used to lose, "
                         "because a benchmark that quietly drops the case it lost is "
                         "not reporting, it is marketing.",
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
                            "of the same tree, down from {before}× before "
                            "Zstandard landed. It still loses, and for a structural "
                            "reason rather than a missing feature: tar.gz compresses "
                            "across file boundaries, and ANLA compresses each chunk "
                            "on its own so that any chunk can be read without the "
                            "others.",
        "bench_read_history": "Eight versions of that tree cost {ratio}× a single "
                              "tar.gz of all eight, and {store}× with the codec "
                              "turned off. Deduplication is what wins here and "
                              "compression compounds it. Unlike the tar.gz, any one "
                              "version extracts on its own and a ninth appends "
                              "without rewriting a byte.",
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
        "fact_tests_v": "805 + fuzzing",
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

        "two_kicker": "Two profiles",
        "two_h2": "ANLA 1.0 now has two implementations, and the freeze rule is met.",
        "two_desc": "ANLA-MVP v0.1 is the frozen profile you can verify in a browser "
                    "tab. ANLA 1.0 is the one a preservation system would adopt, and "
                    "in July it set itself a rule: nothing is frozen until two "
                    "independent implementations produce byte-identical archives and "
                    "a differential fuzzer finds no verdict divergence. Both halves "
                    "now hold.",
        "two_a_h": "Byte-identical output",
        "two_a_p": "The same tree packed by a Python writer and a Rust writer, sharing "
                   "no code below BLAKE3 and Zstandard, produces the same bytes — "
                   "with fixed chunking, content-defined chunking, recorded metadata, "
                   "symbolic links, and a two-snapshot archive built by "
                   "create-then-append on both sides. Six comparisons, three "
                   "operating systems.",
        "two_b_h": "No verdict divergence",
        "two_b_p": "Sixteen thousand mutated archives across four seeds, each shown "
                   "to both readers: zero disagreements, and four real defects found "
                   "getting there. Then a measurement of the fuzzer itself showed it "
                   "had never reached the parser at all — a record's hash is checked "
                   "before its payload is read, so every mutation was stopped one "
                   "layer early. A strategy that repairs the hash over what it "
                   "mutates — a lying writer rather than a corrupt disk — found three "
                   "more defects in its first five hundred archives. Then, because "
                   "random sampling found something on Linux that the same seed could "
                   "not reproduce on Windows, we stopped sampling: every member of a "
                   "manifest, deleted, renamed and retyped in turn, asked of both "
                   "readers. Sixty-five disagreements out of a hundred and seventy-nine "
                   "— thirty-three of them one reader crashing where the other answered "
                   "cleanly. All fixed; the enumeration runs in CI.",
        "two_c_h": "Still a draft, and here is why",
        "two_c_p": "Two implementations by one author are weaker evidence than two by "
                   "two: a shared misreading reproduces rather than being caught. "
                   "That is not hypothetical — an archive whose header and manifest "
                   "disagreed passed both readers, and only the byte comparison "
                   "caught it. What having two is good at is the opposite case: the "
                   "object name model landed this month, and the Rust reader accepted "
                   "a filename crafted to restore outside the destination until it "
                   "was taught the rule the Python one already had.",
        "two_cta": "Read the draft specification",
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
        "nav_context": "代理記憶",
        "nav_repo": "原始碼",

        # ---- the context / MCP page -------------------------------------
        "ctx_kicker": "這個專案後來變成的第二件事",
        "ctx_h1": "讓代理精確地記得自己的歷史",
        "ctx_desc": "一個能精確保存位元組、又能隨時把任何一段展開回來的封存格式，同時也就"
                    "描述了一個模型對自己的上下文需要什麼。同一個套件因此帶了一層上下文，"
                    "透過 MCP 使用：無損地記住、以語義定址、而拿回來的是記錄本身 —— "
                    "不是它的摘要。",
        "ctx_loop_h": "這個迴圈，以及每一步必須撐住的主張",
        "ctx_loop_tool": "工具",
        "ctx_loop_claim": "它必須撐住的主張",
        "ctx_loop_1": "逐位元組地存下整份對話記錄，否則就拒絕。一個會砍掉對話前段的上限"
                      "是錯誤，不是安靜的截斷。",
        "ctx_loop_2": "在這些 turn 上建立一族索引 —— 而封存檔在前後是位元組完全相同的，"
                      "這一點是被檢查的，不是被宣稱的。",
        "ctx_loop_3": "要送去做 embedding 的視角，連同必須跟著回來的身分，以及一份會"
                      "說明自己涵蓋了記錄哪一部分的取樣。",
        "ctx_loop_4": "向量進入輔助平面：封存檔「旁邊」的一個附檔，永遠不是它「裡面」"
                      "的一筆記錄。",
        "ctx_loop_5": "問題進去，(turn, start_byte, end_byte) 出來，而且該 turn 的"
                      "digest 會重新對照索引當初建立時的值。",
        "ctx_idx_kicker": "整個設計立足的那個想法",
        "ctx_idx_h": "segment 是索引，永遠不是被保存的新碎片",
        "ctx_idx_p": "出自 Neo.K 的同一性微積分：切割 = 索引 —— 一刀下去只是多了一個"
                     "視角，物件本身完好如初。所以 segment 是輔助平面裡的 "
                     "(turn, start_byte, end_byte)，多個方案可以並存於同一份記錄之上，"
                     "重新切割不改寫任何東西，而且切割器被允許是錯的。",
        "ctx_idx_a_h": "本體層",
        "ctx_idx_a_p": "turn 完整地存在保存平面裡，不被任何切割動到。它的 digest 在建立"
                       "索引之前、兩個不同方案之後、以及每一次檢索之後，都是同一個。",
        "ctx_idx_b_h": "呈現層",
        "ctx_idx_b_p": "segment 是指進那個 turn 的原始位元組偏移量。之後更好的切割器只是"
                       "產生新的一族索引；記錄沒被動過，所以在方案之間做選擇是一次量測，"
                       "而不是一次遷移。",
        "ctx_m_kicker": "在這個儲存庫自己的開發記錄上實測",
        "ctx_m_h": "它的代價，以及它回傳什麼",
        "ctx_m_desc": "下面每一個數字都由 bench/context_bench.py 產生並寫進一份 JSON，"
                      "這個頁面就是從那份 JSON 生成的，並且蓋上了量測時的版本號與語料"
                      "digest。",
        "ctx_m_record": "記錄",
        "ctx_m_index": "索引",
        "ctx_m_vectors": "向量平面",
        "ctx_m_search": "搜尋",
        "ctx_m_wire": "走真正的通訊管道",
        "ctx_m_turns": "個 turn",
        "ctx_m_lossless": "無損 —— 對話記錄的每一個位元組都在封存檔裡",
        "ctx_m_partial": "不完整 —— 對話記錄的前段被丟掉了",
        "ctx_m_segments": "個 segment",
        "ctx_m_median": "中位數",
        "ctx_m_coverage": "覆蓋率",
        "ctx_m_coverage_note": "沒有任何一個 turn 的任何一個位元組是索引不到的，也沒有"
                               "任何一個被涵蓋兩次",
        "ctx_m_unchanged": "建立索引前後，保存平面的 digest 未變",
        "ctx_m_changed": "保存平面的 DIGEST 改變了 —— 這條不變式已經破了",
        "ctx_m_json": "JSON 十進位陣列",
        "ctx_m_binary": "float32 加一行 JSON 標頭",
        "ctx_m_size": "大小",
        "ctx_m_load": "載入",
        "ctx_m_compare": "體積小 {smaller} 倍 · 載入快 {faster} 倍",
        "ctx_m_model": "模型",
        "ctx_m_queries": "個有標準答案的查詢",
        "ctx_m_numpy": "有 NumPy",
        "ctx_m_pure": "純 Python",
        "ctx_m_pure_note": "NumPy 是選用的，保存平面永遠不需要它。純 Python 這條路只有在"
                           "自己的推估超過明列的 30 秒預算時才會拒絕，而且它會把推估值"
                           "寫在拒絕訊息裡 —— 你可以去反對那個估計值，而不是去反對一個"
                           "常數。",
        "ctx_m_median_query": "一次完整定址查詢的中位數",
        "ctx_m_verified": "次回傳了經 digest 驗證的精確位元組",
        "ctx_m_incomparable": "用 64 維的查詢去問 768 維的語料",
        "ctx_r_kicker": "切段到底有沒有用？",
        "ctx_r_h": "十二個有標準答案的查詢，一份釘死的語料",
        "ctx_r_desc": "標準答案是用一個獨特的錨定字串精確搜尋出來的 —— 然後問題本身被"
                      "刻意寫成完全避開那個錨。所以標籤來自一個檢索器永遠看不到的比對，"
                      "而查詢正好就是詞彙比對答不出來的那一類。",
        "ctx_r_scheme": "方案",
        "ctx_r_segments": "segment 數",
        "ctx_r_p95": "p95",
        "ctx_r_median_rank": "排名中位數",
        "ctx_r_baseline": "基線",
        "ctx_r_control": "對照組",
        "ctx_r_find_1_h": "對照組贏過了它本來要對照的那個方案。",
        "ctx_r_find_1_p": "每 900 位元組切一刀，表現比讀取文件自己的標題、段落分隔與"
                          "程式碼圍欄還好。所以那些結構並沒有在承載資訊，而讀取它的方案"
                          "並沒有賺到它比算術多出來的複雜度。真正有效的是在詞彙改變的"
                          "地方切 —— 三者之中唯一會去看內容的那一個。",
        "ctx_r_find_2_h": "當初明訂的 p95 門檻，每一列都沒過，包含冠軍那一列。",
        "ctx_r_find_2_p": "它要求置中後的隨機配對 p95 低於 +0.15，而校準它的基線是在只有"
                          "這份語料三分之一大小時量到的 +0.238 —— 現在那個基線是 +0.443。"
                          "獲勝的方案把擁擠程度砍了一半，那正是這道門檻真正想要的東西，"
                          "而門檻照它寫的樣子仍然沒過。這裡和 JSON 裡都記為失敗，因為一個"
                          "事後被重新解讀成剛好支持結果的門檻，就不是門檻了。",
        "ctx_ref_kicker": "三種拒絕",
        "ctx_ref_h": "真正承重的，是它拒絕回答的那些",
        "ctx_ref_1_h": "先確認身分，再談相似度",
        "ctx_ref_1_p": "兩個都是 768 維、但來自不同模型的向量 —— 或同一個模型但經過兩種"
                       "不同前處理 —— 比對出來會是一個很有自信而毫無意義的數字，而且下游"
                       "沒有任何東西分辨得出來。模型、版本、維度、投影版本與切段方案必須"
                       "全部一致，否則答案是 INCOMPARABLE 而不是一個數值。維度寬度不等於"
                       "身分。",
        "ctx_ref_2_h": "一次不會是無損的擷取",
        "ctx_ref_2_p": "一個會砍掉對話記錄前段的位元組上限會被拒絕。如果是刻意要這麼做，"
                       "結果會被標記為不完整，並且指名它丟掉的位元組範圍 —— 否則下游的"
                       "每一個主張，都是建立在一份呼叫者以為是完整的記錄上。",
        "ctx_ref_3_h": "只涵蓋部分記錄的搜尋",
        "ctx_ref_3_p": "一份只涵蓋索引十分之一的向量語料，一樣會回傳它範圍內最接近的結果，"
                       "而那個答案跟一次完整搜尋是無法區分的 —— 除非把涵蓋比例講出來。"
                       "每一次呼叫都會講。",
        "ctx_run_h": "跑跑看",
        "ctx_run_p": "二十個工具，走 stdio。這裡沒有任何東西會去算 embedding：向量來自"
                     "代理本來就有的模型，而身分會跟著向量一起走，所以本地或瀏覽器端的"
                     "模型可以取代這裡用的那一個，而不會有任何東西在無聲地跨兩個向量空間"
                     "做比較。",
        "ctx_run_note": "檢索那張表需要一個 embedding 模型；這個頁面上其他每一項都可以"
                        "離線跑。",
        "ctx_cta_t": "代理記憶",
        "ctx_cta_d": "記住、索引、定址、展開 —— 走 MCP，有實測",

        "bench_kicker": "量出來的，不是宣稱的",
        "bench_h1": "ANLA 對真實位元組做了什麼",
        "bench_desc": "五個情境，跑在這個儲存庫自己的 git 歷史上，並且跟一般人真的會拿來用的"
                      "替代方案對比。每一個數字都由 bench/run_bench.py 產生並寫進一份 JSON，"
                      "這個頁面是從那份 JSON 生成的——所以頁面說不出任何量測程式沒有量到的東西，"
                      "包含 ANLA 輸掉的那幾列。",
        "bench_warning_h": "去重跟壓縮是兩種不同的機制。",
        "bench_warning": "Zstandard 於 2026-08-07 落地；在那之前，這裡每一個數字都只是去重，而單一 snapshot 比它所包的樹還大。在它曾經輸掉的那幾列，「store 單獨」那一行仍然留在壓縮結果旁邊——一個惄惄把自己輸過的情境拿掉的基準，不是在回報，是在行銷。",
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
        "bench_read_codec": "一棵原始碼樹的單一 snapshot，是同一棵樹 tar.gz 的 {ratio} 倍"
                            "（Zstandard 落地前是 {before} 倍）。它仍然輸，"
                            "而且是結構性的理由而不是少了功能："
                            "tar.gz 跨檔案邊界壓縮，而 ANLA 每一塊各自壓，"
                            "為的是任何一塊都能不靠其他塊讀出來。",
        "bench_read_history": "同一棵樹的八個版本，是「八個版本包成一個 tar.gz」的 "
                              "{ratio} 倍；把 codec 關掉則是 {store} 倍。"
                              "贏的主力是去重，壓縮在上面相乘。"
                              "跟 tar.gz 不同的是，任何一個版本都能單獨取出，"
                              "而且第九個可以附加上去而不重寫任何一個位元組。",
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
        "fact_tests_v": "805 項 + 模糊測試",
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

        "two_kicker": "兩個 profile",
        "two_h2": "ANLA 1.0 現在有兩套實作，而凍結規則已達成。",
        "two_desc": "ANLA-MVP v0.1 是已凍結、可以在瀏覽器分頁裡驗證的 profile。"
                    "ANLA 1.0 則是一個保存系統真的會採用的那一個——"
                    "而它在七月給自己訂下一條規則："
                    "在兩套獨立實作產生逐位元相同的封裝、"
                    "且 differential fuzzer 找不到判決分歧之前，沒有任何部分被凍結。"
                    "兩個半部現在都成立。",
        "two_a_h": "逐位元相同的輸出",
        "two_a_p": "同一棵樹，由一個 Python writer 跟一個 Rust writer 各自打包——"
                   "兩者在 BLAKE3 跟 Zstandard 之上不共用任何程式碼——"
                   "產生相同的 bytes。固定切塊、內容定義切塊、"
                   "記錄 metadata、symbolic link，以及兩邊各自「建立→附加」"
                   "產生的雙 snapshot 封裝。六組比較，三個作業系統。",
        "two_b_h": "找不到判決分歧",
        "two_b_p": "四個 seed、一萬六千個被突變的封裝，"
                   "每一個都給兩套 reader 看：零個不一致，"
                   "走到這裡之前找出了四個真實缺陷。"
                   "然後我們量了 fuzzer 自己——發現它從來沒有真的碰到 parser："
                   "record 的 hash 在 payload 被讀取之前就先檢查，"
                   "所以每一個突變都在前一層就被擋下來了。"
                   "改成「突變之後把 hash 補回去」——"
                   "模擬的不是壞掉的磁碟，而是一個說謊的 writer——"
                   "它在最初的五百個封裝裡就找出三個新缺陷。"
                   "接著，因為隨機抽樣在 Linux 上找到的東西"
                   "在 Windows 用同一個 seed 重現不出來，我們就不再抽樣："
                   "把 manifest 的每一個成員逐一刪除、改名、換型別，"
                   "兩套 reader 各問一次。"
                   "179 個案例裡有 65 個判斷不一致——"
                   "其中 33 個是一邊直接崩潰、另一邊乾淨拒絕。"
                   "全部修好了，而這套列舉現在跑在 CI 裡。",
        "two_c_h": "仍然是草案，而且這是理由",
        "two_c_p": "同一個作者寫的兩套實作，證據力弱於兩個作者寫的："
                   "共同的誤讀會重現而不是被抓到。"
                   "而這不是假設——一個 header 跟 manifest 不一致的封裝"
                   "通過了兩套 reader，只有逐位元比較抓到它。"
                   "但「有兩套」擅長的是反過來的情況："
                   "物件名稱模型這個月完成，而 Rust reader 一直接受"
                   "一個被設計成會還原到目標目錄外面的檔名，"
                   "直到它也學會 Python 那邊早就有的那條規則。",
        "two_cta": "讀草案規格",
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
    "throughput": {
        "headline": "64 MiB 不可壓縮資料，打包與驗證",
        "note": "每秒多少 MiB，在跑這次量測的機器上。"
                "內容定義切塊是預設值——因為固定切塊會讓去重整個垮掉——"
                "而在 Python writer 裡它同時也是慢路徑，慢兩個數量級。"
                "Rust writer 做的是完全一樣的工作，產生逐位元相同的封裝，"
                "速度是 {factor} 倍；所以這是實作的數字，不是格式的數字。"
                "會publish 出來，是因為一個只量自己擅長的項目的專案，等於沒有在量。",
    },
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
