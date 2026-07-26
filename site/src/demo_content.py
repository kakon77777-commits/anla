# -*- coding: utf-8 -*-
"""Copy for the live test page, in both languages.

Kept out of content.py because it is a different register: nearly every string
here labels an assertion, and a label that drifts from what its assertion
actually checks is worse than no label at all. When a test changes, its row
label changes with it, in this file.
"""

from __future__ import annotations

__all__ = ["DEMO_STRINGS", "demo_keys"]

DEMO_STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "nav_demo": "Live test",
        "meta_demo": "Run the ANLA-MVP v0.1 conformance suite in your own browser: "
                     "cross-implementation byte equality, frozen vectors, round trips, "
                     "and every rejection a decoder owes you.",
        "demo_kicker": "Live test",
        "demo_h1": "Do not take the tests on faith. Run them here.",
        "demo_desc": "This page runs the conformance suite in your browser, against the "
                     "same web/anla-core.js the workbench uses, the same fixtures.json "
                     "the Python suite reads, and the same frozen vectors that are "
                     "checked into the repository. It starts on load. Nothing is "
                     "uploaded and nothing is fetched — the fixtures and the vectors "
                     "travel with the page.",
        "demo_headline": "The first suite is the one that matters. The hashes it compares "
                         "against were produced by the Python writer, on another machine. "
                         "When a row goes green, this browser has just reproduced one of "
                         "those archives byte for byte.",
        "demo_run": "Run the suite",
        "demo_env": "Environment",
        "demo_counts": "Cases",
        "demo_counts_note": "byte-exact cases + all fixture cases + frozen vectors",
        "demo_source": "Every row corresponds to an assertion in the repository's "
                       "conformance suite; the identifiers match the table in "
                       "conformance/README.md.",
        "running": "Running…",
        "run_again": "Run again",
        "pass": "PASS",
        "fail": "FAIL",
        "passed": "passed",
        "failed": "failed",
        "cores": "cores",
        "files_word": "files",
        "paths_word": "paths",
        "unique_word": "unique",
        "decisions_word": "decisions",
        "extraction_identical": "extraction identical",
        "declared_as": "declared as",
        "verdict_passed": "assertions passed, in",
        "verdict_failed": "assertions failed — please open an issue with your browser and "
                          "platform. A red row here is a real defect, not a quirk.",

        "suite_xim_t": "Two implementations, byte for byte",
        "suite_xim_d": "Each case is packed here and its SHA-256 compared with the hash "
                       "committed in conformance/vectors/SHA256SUMS, which the Python "
                       "writer produced. Equal hashes mean equal archives.",
        "suite_frz_t": "Frozen vectors still verify",
        "suite_frz_d": "Every archive checked into the repository is opened and fully "
                       "verified: header, footer, manifest hash, every chunk against its "
                       "content id, every file against its own hash. T-ORG-1 is the "
                       "archive the original v0.1 browser release shipped.",
        "suite_rt_t": "Round trips and the preservation invariants",
        "suite_rt_d": "Pack, open, and compare every restored byte with what went in — "
                      "then the specific claims: deduplication, empty files, an empty "
                      "archive, chunk splitting, Unicode paths, and the intelligence "
                      "plane being disposable.",
        "suite_rej_t": "Corruption is refused, not tolerated",
        "suite_rej_d": "Each row forges an archive that is well formed at the frame level "
                       "and wrong at exactly one semantic level, then asserts the decoder "
                       "fails with the right error code instead of guessing. This half of "
                       "a preservation format is what makes the other half mean anything.",

        "suite_cdc_t": "Content-defined chunking, pinned",
        "suite_cdc_d": "The whitepaper's open question 3 asked how FastCDC "
                       "parameters could become a permanently stable profile. These "
                       "rows are the answer: the gear table is derived from its own "
                       "name rather than copied as 256 constants, the boundary rule "
                       "is a single predicate, and both implementations cut "
                       "identically. The last row is why any of it matters.",
        "row_gear_derived": "the gear table matches its own derivation",
        "row_tiling": "cut ranges tile the input, inside min and max, near the average",
        "row_shift": "an insertion at the front: how many chunks survive",
        "row_cdc_saving": "the same tree, chunked both ways",
        "row_reader_unaware": "a reader that never heard of the profile still reads it",
        "vectors_not_bundled": "Too large to ship inside this page",
        "vectors_covered_elsewhere": "their hashes are checked by the byte-exactness suite above, which packs the same cases here",
        "words": "words",
        "chunks_word": "chunks",
        "mean_word": "mean",
        "cdc_word": "content-defined",
        "fixed_word": "fixed-size",
        "smaller_word": "smaller",
        "row_reproducible": "the same call twice gives the same bytes",
        "row_uuid_varies": "without a fixed UUID, two archives differ",
        "row_dedup": "identical content is stored once",
        "row_empty_file": "an empty file references no chunk",
        "row_empty_archive": "an archive with no objects round-trips",
        "row_split": "a file larger than the chunk size splits, and the parts add up",
        "row_unicode": "NFC, NFD and case-only pairs stay distinct",
        "row_auxiliary": "emptying the intelligence plane changes no extracted byte",
        "row_zip": "a verified archive exports as a ZIP",
        "row_auxiliary_idempotent": "stripping twice gives the same bytes as stripping once",
        "row_forge": "the forge itself produces a valid archive",
        "row_forge_ok": "valid, so the rows below test what they claim",
        "row_bad_magic": "bad bootstrap magic",
        "row_header_crc": "header CRC mismatch",
        "row_version": "unsupported version",
        "row_footer_magic": "bad footer magic",
        "row_footer_crc": "footer CRC mismatch",
        "row_footer_uuid": "header and footer disagree on the UUID",
        "row_footer_points_wrong": "footer points at a non-MANF record",
        "row_manifest_hash": "manifest hash mismatch",
        "row_other_profile": "a different format profile",
        "row_record_crc": "record header CRC mismatch",
        "row_unknown_record": "unknown record type",
        "row_payload_hash": "stored payload hash mismatch",
        "row_content_id": "chunk id does not match its content",
        "row_descriptor": "descriptor disagrees with its record",
        "row_unknown_codec": "unknown codec",
        "row_coverage": "chunk coverage does not add up",
        "row_unsafe_path": "unsafe path",
        "row_duplicate_path": "duplicate path",
        "row_unknown_object": "an object kind this profile cannot represent",
        "row_absurd_size": "a chunk declaring a terabyte",
        "row_bomb": "a compression bomb, stopped mid-decode",
        "row_truncated": "a truncated archive",
    },
    "zh": {
        "nav_demo": "即時測試",
        "meta_demo": "在你自己的瀏覽器裡跑完 ANLA-MVP v0.1 的一致性測試：跨實作逐位元"
                     "相等、凍結向量、往返還原，以及解碼器該拒絕的每一種情況。",
        "demo_kicker": "即時測試",
        "demo_h1": "測試不必用信任來接受。在這裡跑一遍。",
        "demo_desc": "這個頁面在你的瀏覽器裡執行一致性測試，用的是工作台同一份 "
                     "web/anla-core.js、Python 測試套件同一份 fixtures.json、以及 repo "
                     "裡同一批凍結向量。開頁即自動開始。不上傳任何東西，也不抓取任何"
                     "東西——fixtures 與向量本身就隨頁面一起送來。",
        "demo_headline": "第一組才是重點。它比對的雜湊是 Python 那套實作在另一台機器上"
                         "產生的。當一列變綠，代表這個瀏覽器剛剛逐位元重現了那些封裝"
                         "之一。",
        "demo_run": "執行測試",
        "demo_env": "執行環境",
        "demo_counts": "案例數",
        "demo_counts_note": "逐位元案例 + 全部 fixture 案例 + 凍結向量",
        "demo_source": "每一列都對應 repo 一致性測試裡的一項斷言；識別碼與 "
                       "conformance/README.md 的表格一致。",
        "running": "執行中…",
        "run_again": "再跑一次",
        "pass": "通過",
        "fail": "失敗",
        "passed": "通過",
        "failed": "失敗",
        "cores": "核心",
        "files_word": "個檔案",
        "paths_word": "個路徑",
        "unique_word": "唯一",
        "decisions_word": "筆決策",
        "extraction_identical": "取出內容完全相同",
        "declared_as": "宣告為",
        "verdict_passed": "項斷言全部通過，耗時",
        "verdict_failed": "項斷言失敗——請附上你的瀏覽器與平台開一個 issue。這裡出現"
                          "紅色是真的缺陷，不是小毛病。",

        "suite_xim_t": "兩套實作，逐位元相同",
        "suite_xim_d": "每個案例在這裡封裝一次，再把 SHA-256 與 "
                       "conformance/vectors/SHA256SUMS 裡已提交的雜湊比對——那些是 "
                       "Python 寫入器產生的。雜湊相同就代表封裝完全相同。",
        "suite_frz_t": "凍結向量仍然驗證通過",
        "suite_frz_d": "repo 裡每一個封裝檔都被開啟並完整驗證：Header、Footer、Manifest "
                       "雜湊、每個 Chunk 對照自己的內容身分、每個檔案對照自己的雜湊。"
                       "T-ORG-1 就是原始 v0.1 瀏覽器版所附的那個封裝。",
        "suite_rt_t": "往返還原與保存不變量",
        "suite_rt_d": "封裝、開啟，再把還原出來的每一個位元和放進去的比對——接著是那些"
                      "具體宣稱：去重、空檔案、空封裝、分塊、Unicode 路徑，以及智能平面"
                      "可拋棄。",
        "suite_rej_t": "遇到損壞就拒絕，不將就",
        "suite_rej_d": "每一列都偽造一個「frame 層完全合法、但恰好有一個語義層錯誤」的"
                       "封裝，並斷言解碼器必須以正確的錯誤碼失敗，而不是猜測。保存格式"
                       "的這一半，決定了另一半有沒有意義。",

        "suite_cdc_t": "內容定義分塊，已釘死",
        "suite_cdc_d": "白皮書第 18 部的 open question 3 問的是「FastCDC 參數如何形成"
                       "永久穩定的 Profile」。這幾列就是答案：gear table 由它自己的"
                       "名稱推導出來而不是抄 256 個常數、邊界規則只有一條判準、而且"
                       "兩套實作切在完全相同的位置。最後一列說明這一切為什麼重要。",
        "row_gear_derived": "gear table 與它自己的推導一致",
        "row_tiling": "切出的區間完整鋪滿輸入，落在 min/max 之間、平均接近 avg",
        "row_shift": "在檔案開頭插入位元組：有多少 chunk 存活",
        "row_cdc_saving": "同一棵樹，兩種分塊方式",
        "row_reader_unaware": "從沒聽過這個 Profile 的解碼器照樣讀得懂",
        "vectors_not_bundled": "太大，沒有內嵌進這個頁面",
        "vectors_covered_elsewhere": "它們的雜湊由上面那組逐位元測試檢查——那組會在這裡重新封裝同樣的案例",
        "words": "個字",
        "chunks_word": "個 chunk",
        "mean_word": "平均",
        "cdc_word": "內容定義",
        "fixed_word": "固定大小",
        "smaller_word": "更小",
        "row_reproducible": "同一次呼叫跑兩遍得到相同位元",
        "row_uuid_varies": "沒有固定 UUID 時兩個封裝必須不同",
        "row_dedup": "相同內容只保存一次",
        "row_empty_file": "空檔案不引用任何 Chunk",
        "row_empty_archive": "沒有任何物件的封裝也能往返",
        "row_split": "大於 chunk 大小的檔案會分塊，且各段長度相加正確",
        "row_unicode": "NFC、NFD 與只差大小寫的路徑保持相異",
        "row_auxiliary": "清空智能平面不改變取出的任何一個位元",
        "row_zip": "已驗證的封裝可匯出為 ZIP",
        "row_auxiliary_idempotent": "清空兩次與清空一次得到相同位元",
        "row_forge": "偽造器本身能產生合法封裝",
        "row_forge_ok": "合法，所以下面每一列測的是它們宣稱的東西",
        "row_bad_magic": "Bootstrap magic 錯誤",
        "row_header_crc": "Header CRC 不符",
        "row_version": "不支援的版本",
        "row_footer_magic": "Footer magic 錯誤",
        "row_footer_crc": "Footer CRC 不符",
        "row_footer_uuid": "Header 與 Footer 的 UUID 不一致",
        "row_footer_points_wrong": "Footer 指向非 MANF 的 Record",
        "row_manifest_hash": "Manifest 雜湊不符",
        "row_other_profile": "另一個格式 Profile",
        "row_record_crc": "Record header CRC 不符",
        "row_unknown_record": "未知 Record 類型",
        "row_payload_hash": "儲存 payload 雜湊不符",
        "row_content_id": "Chunk id 與其內容不符",
        "row_descriptor": "Descriptor 與其 Record 不一致",
        "row_unknown_codec": "未知 Codec",
        "row_coverage": "Chunk 覆蓋長度加不起來",
        "row_unsafe_path": "不安全路徑",
        "row_duplicate_path": "重複路徑",
        "row_unknown_object": "此 Profile 無法表示的物件種類",
        "row_absurd_size": "宣告一 TB 的 Chunk",
        "row_bomb": "壓縮炸彈，在解壓中途被攔下",
        "row_truncated": "被截斷的封裝",
    },
}


def demo_keys(runtime_keys: tuple[str, ...]) -> tuple[str, ...]:
    """The keys demo.js reads at runtime, minus what the workbench already ships.

    Page chrome (nav_, meta_, demo_) is rendered server-side and does not need to
    reach the browser as data.
    """
    return tuple(
        key for key in DEMO_STRINGS["en"]
        if key not in runtime_keys and not key.startswith(("nav_", "meta_", "demo_"))
    )
