---
title: "AI 原生無損封裝格式技術白皮書"
subtitle: "Agent-Native Lossless Archive Format（ANLA）v0.1"
author: "Neo.K"
organization: "EVEMISSLAB／一言諾科技有限公司"
date: "2026-07-16"
version: "v0.1"
status: "技術白皮書／規格前草案"
language: "zh-TW"
scope: "本版本只定義無損保存、確定性解碼與 Agent 控制面；不納入任何生成式或語義近似重建。"
---

# AI 原生無損封裝格式技術白皮書

## Agent-Native Lossless Archive Format（ANLA）v0.1

**作者：** Neo.K  
**日期：** 2026 年 7 月 16 日  
**狀態：** 規格前草案  
**暫定副檔名：** `.anla`  
**暫定 MIME：** `application/vnd.evemiss.anla`

---

# 執行摘要

ANLA 是一套面向 AI Agent、人類使用者與一般程式的通用無損封裝格式。它不是新的單一壓縮演算法，而是建立在多 Codec、內容定址、可驗證 Manifest、跨平台物件模型、增量 Snapshot 與結構化控制面的封裝協議。

ANLA v0.1 的首要原則是：

> **AI 可以自主選擇如何壓縮，但不能以任何形式替代、摘要、推測或重新生成已納入封裝的原始資料。**

格式必須滿足：

$$
\operatorname{Extract}(\operatorname{Pack}(F,P))=F
$$

其中：

- $F$ 是已批准納入封裝的物件集合。
- $P$ 是由 AI 或傳統規劃器產生的無損封裝計畫。
- `Pack` 是受規範約束的確定性寫入流程。
- `Extract` 是不需要 AI 的標準解碼流程。

ANLA 將系統分成兩個平面：

1. **保存平面：** 原始 Payload、Chunk、物件拓撲、路徑、Metadata、Hash、Snapshot、簽章與復原資料。
2. **智能平面：** AI 決策紀錄、內容索引、語言標註、搜尋資料、存取提示與 Agent 操作歷史。

智能平面是可選且可重建的。刪除全部智能資料後，保存平面仍必須完整解碼。

本白皮書定義：

- 核心不變量。
- 檔案與 Metadata 物件模型。
- 二進位容器布局。
- Manifest 與 Snapshot。
- Chunk 與 Codec。
- 路徑及歷史編碼保存。
- 隨機存取與串流。
- 增量版本。
- Agent 規劃介面。
- CLI／JSON／MCP。
- 安全、加密、簽章與復原。
- Conformance Profile。
- Rust 參考實作路線。

---

# 第一部　目標與邊界

## 第一章　設計目標

### 1.1 核心目標

ANLA v0.1 必須：

1. 對納入封裝的檔案內容提供位元級無損恢復。
2. 保存足夠的路徑與平台 Metadata。
3. 支援 x86、x64、ARM 與不同作業系統上的獨立 Decoder。
4. 允許不同檔案或 Chunk 使用不同無損 Codec。
5. 支援固定分塊與內容定義分塊。
6. 支援跨檔案與跨 Snapshot 去重。
7. 支援串流寫入。
8. 支援完成封裝後的隨機存取。
9. 支援追加式增量更新。
10. 支援 Agent 以結構化方式規劃和操作。
11. 確保解壓完全不依賴 Agent 或模型。
12. 提供完整性、簽章與安全限制。
13. 允許匯出為 ZIP、TAR 或一般資料夾。
14. 允許未來擴充，但未知必要能力必須安全失敗。

---

### 1.2 明確非目標

ANLA v0.1 不包含：

- 生成式圖片、文字、音訊或影片重建。
- 以提示詞取代原始檔案。
- 以摘要取代原始內容。
- 語義有損壓縮。
- 自動刪除「可重新下載」依賴。
- 自動省略建置產物。
- 模型權重壓縮研究。
- 自行發明新的底層熵編碼器。
- 任意執行封裝內程式。
- 反作弊、DRM 或存取控制繞過。
- 強制要求向量資料庫或知識圖。
- 強制要求任何未公開或私有理論。

---

### 1.3 AI 原生的操作性定義

ANLA 的 AI 原生性由以下能力構成：

#### 自描述

Codec、版本、Chunk Map、路徑表示與必要能力均由格式明確聲明。

#### 可規劃

Agent 能輸出完整 Packing Plan，而不是只傳入「最高壓縮」。

#### 可審計

每次規劃可保存輸入證據、選擇理由、工具版本與 Benchmark 結果。

#### 可重放

同一計畫可以由確定性 Writer 再次執行。

#### 可查詢

Agent 可以列出物件、Chunk、Snapshot、差異與 Metadata。

#### 可局部物化

只解壓任務需要的物件，而不必掃描全部 Payload。

#### 模型獨立

更換或移除模型不影響既有 Archive 的解壓。

---

## 第二章　核心不變量

### 2.1 內容完整性

對所有普通檔案 $f_i$：

$$
H(B_i)=H(\widehat{B_i})
$$

其中：

- $B_i$：原始內容位元組。
- $\widehat{B_i}$：解壓後內容位元組。
- $H$：Manifest 指定的雜湊函數。

---

### 2.2 Chunk 完整覆蓋

令檔案 $f$ 的內容為 $B$，其 Chunk Slice 序列為：

$$
S_f=(s_1,s_2,\ldots,s_k)
$$

必須滿足：

$$
B=s_1\Vert s_2\Vert\cdots\Vert s_k
$$

且：

- Slice 不得缺口。
- Slice 不得重疊，除非規格明確聲明重複引用相同 Chunk。
- 每個 Slice 的未壓縮長度總和必須等於檔案大小。
- 每個 Slice 引用的 Chunk 必須存在或可由同一 Snapshot 的外部 Descriptor 解析。

---

### 2.3 確定性解碼

對相同 Archive 位元組與相同能力集合，Decoder 必須得到相同輸出。

$$
D_1(A)=D_2(A)
$$

只要 $D_1$ 與 $D_2$ 都符合相同 Conformance Profile。

---

### 2.4 智能平面可拋棄

令 Archive 為：

$$
A=(P,I)
$$

其中：

- $P$：Preservation Plane。
- $I$：Intelligence Plane。

必須滿足：

$$
D(P,I)=D(P,\varnothing)
$$

---

### 2.5 模型不可成為 Decoder

標準 Decoder 的依賴集合不得包含：

- 特定 LLM。
- 遠端推理 API。
- Embedding 模型。
- 生成模型。
- 自然語言判定。
- 供應商私有服務。

---

### 2.6 明確失敗

遇到未知必要能力時，Decoder 必須拒絕，而不是猜測：

```text
required capability unknown → fail
optional auxiliary record unknown → skip
```

---

# 第二部　邏輯物件模型

## 第三章　Archive 結構

ANLA 邏輯模型為：

$$
\mathcal{A}
=
(S,O,C,M,X,R,Q)
$$

其中：

- $S$：Snapshot 集合。
- $O$：Filesystem Object 集合。
- $C$：Chunk 集合。
- $M$：Manifest 與 Descriptor。
- $X$：可選索引及智能擴充。
- $R$：Recovery 與簽章資料。
- $Q$：Policy 與能力聲明。

---

## 第四章　Filesystem Object

### 4.1 物件種類

v0.1 定義：

```text
regular-file
directory
symbolic-link
hard-link-reference
sparse-file
windows-reparse-point
platform-special
```

`platform-special` 用於保存 Decoder 不應自動建立的特殊物件，例如：

- Device Node。
- Named Pipe。
- Socket。
- 未知 Reparse Point。

Decoder 預設只保存其 Metadata，不自動具現化，除非使用者明確授權且平台支援。

---

### 4.2 物件識別

每個物件具有穩定 `object_id`，不以路徑作為唯一識別。

```json
{
  "object_id": "b3:...",
  "kind": "regular-file",
  "parent_id": "b3:...",
  "name": { "...": "..." }
}
```

這可避免：

- 同一路徑在不同 Snapshot 指向不同物件。
- Rename 被誤判為刪除後新增。
- Hard Link 關係無法表達。
- 路徑正規化碰撞。

---

## 第五章　路徑模型

### 5.1 路徑不是單一 UTF-8 字串

為避免重現 ZIP 的歷史問題，ANLA 將路徑拆成物件父子關係與名稱元件。

每個名稱元件可包含：

```json
{
  "portable_utf8": "會話01.txt",
  "unicode_normalization": "unmodified",
  "native": {
    "platform": "windows-nt",
    "representation": "utf16le-code-units",
    "data_base64": "..."
  },
  "legacy": {
    "encoding": "cp932",
    "raw_bytes_base64": "...",
    "confidence": "confirmed"
  }
}
```

---

### 5.2 `portable_utf8`

`portable_utf8` 用於：

- UI 顯示。
- 跨平台匯出。
- 查詢。
- 一般 CLI。

它必須是合法 UTF-8，但不作為原始名稱的唯一證據。

---

### 5.3 原生名稱

`native` 保存來源平台實際名稱表示：

- Windows NT：UTF-16LE Code Unit。
- POSIX：原始 Byte Sequence。
- macOS：UTF-8／檔案系統原生表示與必要擴充。

Decoder 在同平台恢復時，優先使用原生表示；跨平台時依映射政策處理。

---

### 5.4 Legacy Archive Import

從舊 ZIP 或其他封裝匯入時，可保存：

- 原始檔名位元組。
- 假定 Code Page。
- 解碼後 Unicode。
- 判定方式。
- 人工確認狀態。

這些資料屬保存 Metadata，不要求未來重新猜測。

---

### 5.5 路徑安全

解壓器必須拒絕或重新映射：

- `..` 路徑穿越。
- 絕對路徑。
- Windows Drive Prefix。
- UNC 路徑。
- NUL。
- 目標平台保留名稱。
- 正規化後碰撞。
- 大小寫不敏感碰撞。
- Symlink 逃逸。

所有映射必須輸出 Extraction Report。

---

## 第六章　Metadata Namespace

### 6.1 通用 Metadata

```json
{
  "size": 12345,
  "modified_time": "...",
  "created_time": "...",
  "accessed_time": "...",
  "read_only": false,
  "executable_hint": true
}
```

時間採：

- UTC 數值。
- 原始精度。
- 原始時區或「未知」。
- 明確 Calendar 與 Epoch。

---

### 6.2 POSIX Namespace

可保存：

- Mode。
- UID／GID。
- User／Group Name。
- Extended Attributes。
- ACL。
- Device Major／Minor。
- Link Count。

---

### 6.3 Windows Namespace

可保存：

- File Attributes。
- Security Descriptor。
- Alternate Data Streams。
- Reparse Data。
- Creation Time。
- Object ID。
- Sparse Range。
- Compression Attribute。

---

### 6.4 macOS Namespace

可保存：

- Extended Attributes。
- ACL。
- Resource Fork。
- Finder Info。
- Quarantine Attribute。
- Clone／Sparse 提示。

---

### 6.5 Extraction Capability Report

Decoder 必須回報：

```json
{
  "object_id": "b3:...",
  "content": "restored",
  "path": "mapped",
  "metadata": {
    "posix.mode": "restored",
    "windows.acl": "preserved-in-sidecar",
    "macos.resource_fork": "unsupported"
  }
}
```

不能因目標平台無法套用 Metadata 而默默丟失。

---

# 第三部　二進位容器

## 第七章　檔案總體布局

ANLA v0.1 採：

```text
┌──────────────────────┐
│ Bootstrap Header      │
├──────────────────────┤
│ Record Stream         │
│  MANF / CHNK / INDX   │
│  META / SIGN / PARI   │
├──────────────────────┤
│ Latest Footer         │
└──────────────────────┘
```

支援：

- 從頭串流讀取。
- 從尾部快速取得最新 Snapshot。
- 追加新 Snapshot。
- Footer 損壞時掃描 Record Stream。

---

## 第八章　Bootstrap Header

### 8.1 Magic

暫定 8 Bytes：

```text
41 4E 4C 41 0D 0A 1A 0A
A  N  L  A \r \n SUB \n
```

---

### 8.2 Header 欄位

固定長度 64 Bytes：

| Offset | Size | Field |
|---:|---:|---|
| 0 | 8 | Magic |
| 8 | 2 | Major Version, little-endian |
| 10 | 2 | Minor Version |
| 12 | 4 | Header Size |
| 16 | 8 | Global Flags |
| 24 | 8 | First Record Offset |
| 32 | 8 | Latest Footer Offset Hint |
| 40 | 16 | Archive UUID |
| 56 | 4 | Header CRC32C |
| 60 | 4 | Reserved |

`Latest Footer Offset Hint` 只作提示。權威 Footer 仍應由檔尾掃描與 Hash 驗證確認。

---

## 第九章　Record Frame

每個 Record：

| Field | Size |
|---|---:|
| Record Magic | 4 |
| Record Type | 4 |
| Record Version | 2 |
| Record Flags | 2 |
| Header Length | 4 |
| Payload Length | 8 |
| Record Sequence | 8 |
| Header CRC32C | 4 |
| Reserved | 4 |
| Extended Header | variable |
| Payload | variable |
| Padding | 0–7 |

Record Magic 暫定：

```text
ANLR
```

---

### 9.1 Record Types

| Type | Meaning |
|---|---|
| `CHNK` | 壓縮或未壓縮 Chunk |
| `MANF` | Snapshot Manifest |
| `INDX` | Random Access Index |
| `AUXI` | 可選智能資料 |
| `META` | 大型或平台 Metadata |
| `SIGN` | 簽章 |
| `PARI` | Recovery／Parity |
| `FOOT` | Snapshot Footer |

---

### 9.2 Required Flag

Record Flags 包含：

```text
bit 0: REQUIRED_FOR_EXTRACTION
bit 1: REQUIRED_FOR_VERIFICATION
bit 2: ENCRYPTED
bit 3: COMPRESSED_METADATA
bit 4: AUXILIARY_DISPOSABLE
```

未知 Record：

- 若 `REQUIRED_FOR_EXTRACTION=1`，Decoder 必須失敗。
- 若 `AUXILIARY_DISPOSABLE=1`，Decoder 可以跳過。

---

## 第十章　Footer

Footer 固定包含：

- Footer Version。
- Snapshot Sequence。
- Manifest Offset／Length。
- Primary Index Offset／Length。
- Previous Footer Offset。
- Preservation Root Digest。
- Auxiliary Root Digest。
- Footer Digest。
- Footer CRC32C。

Footer 在每次更新時追加，不覆寫舊 Footer。

---

# 第四部　Manifest 與 Snapshot

## 第十一章　Manifest 編碼

### 11.1 Deterministic CBOR

ANLA v0.1 建議使用 RFC 8949 Deterministic CBOR，原因：

- 二進位友善。
- 支援 Map、Array、Byte String。
- 適合簽章。
- 可用 CDDL 定義 Schema。
- 可建立相同邏輯資料的穩定位元表示。

Manifest 不使用浮點數作必要結構欄位。

---

### 11.2 Root Manifest

概念示例：

```json
{
  "anla_version": [0, 1],
  "archive_id": "...",
  "snapshot_id": "b3:...",
  "parent_snapshot": "b3:...",
  "created_at": "...",
  "hash_algorithms": ["blake3-256"],
  "required_capabilities": [
    "core.objects.v1",
    "core.chunks.v1",
    "codec.zstd.v1"
  ],
  "objects_root": "b3:...",
  "chunks_root": "b3:...",
  "metadata_root": "b3:...",
  "preservation_root": "b3:...",
  "auxiliary_root": "b3:...",
  "packing_plan_digest": "b3:..."
}
```

---

## 第十二章　Snapshot

### 12.1 Append-only

每次更新建立新 Snapshot：

$$
S_{t+1}=(S_t,\Delta O,\Delta C,\Delta M)
$$

舊 Snapshot 保持可讀。

---

### 12.2 Snapshot ID

Snapshot ID 是規範化 Manifest 的內容 Hash：

$$
\operatorname{snapshot\_id}
=
H(\operatorname{CanonicalEncode}(M))
$$

簽章欄位本身不得造成循環依賴；簽章以獨立 `SIGN` Record 引用 Snapshot ID。

---

### 12.3 Snapshot Completeness

Snapshot 必須列出：

- Root Directory Objects。
- 所有可達物件。
- 所有 Chunk Reference。
- 外部 Chunk Descriptor。
- 必要 Metadata。
- Required Capabilities。

Snapshot 不得依賴未聲明的全域狀態。

---

# 第五部　Chunk 與壓縮

## 第十三章　Chunk Identity

### 13.1 Digest

v0.1 預設：

```text
BLAKE3-256
```

Chunk ID 以未壓縮內容計算：

$$
\operatorname{chunk\_id}=H(B_{\mathrm{raw}})
$$

如此，同一內容即使使用不同 Codec，仍具有相同內容身分。

---

### 13.2 Compressed Representation ID

可另計算：

$$
\operatorname{repr\_id}=H(C(B_{\mathrm{raw}},p))
$$

用於驗證實際壓縮 Payload。

---

## 第十四章　Chunking

### 14.1 支援模式

```text
fixed-size
fastcdc
whole-object
small-object-pack
external-chunk-map
```

---

### 14.2 Fixed-size

適合：

- 已知隨機存取。
- 大型不可變二進位檔。
- 簡單實作。
- GPU／並行處理。

參數必須保存：

```json
{
  "algorithm": "fixed",
  "size": 4194304
}
```

---

### 14.3 Content-Defined Chunking

適合：

- 多版本資料。
- 內容插入／刪除頻繁。
- 備份。
- 原始碼與文件。

v0.1 可採 FastCDC Profile，參數必須完整保存：

```json
{
  "algorithm": "fastcdc",
  "version": "anla-profile-1",
  "min": 65536,
  "avg": 262144,
  "max": 1048576,
  "normalization": 2,
  "gear_table_id": "anla-standard-1"
}
```

不能只寫 `fastcdc`，否則不同實作可能產生不同 Chunk Boundary。

---

### 14.4 小檔案聚合

大量小檔案可聚合成 Pack Chunk，但 Manifest 必須保留每個檔案的：

- Byte Offset。
- Length。
- Content Hash。
- Metadata。
- Object ID。

聚合不能破壞單檔驗證與局部提取。

---

## 第十五章　Codec

### 15.1 Codec Registry

v0.1 Core Profile：

| Codec ID | Codec |
|---:|---|
| 0 | Store |
| 1 | Zstandard |
| 2 | Deflate |
| 3 | LZMA2 |
| 4 | Brotli |
| 5 | LZ4 Frame |

Core Decoder 最低要求：

```text
Store + Zstandard
```

其他 Codec 可由 Capability 聲明。

---

### 15.2 Codec Descriptor

```json
{
  "codec_id": 1,
  "codec_name": "zstd",
  "format_profile": "rfc8878",
  "level": 9,
  "dictionary": null,
  "window_log": null,
  "uncompressed_size": 1048576
}
```

Codec 參數必須足以由獨立 Decoder 重現解碼。

---

### 15.3 Codec 選擇

AI Planner 可根據：

- MIME。
- Magic Bytes。
- Entropy Sample。
- 試壓縮結果。
- 解壓延遲目標。
- 記憶體上限。
- 存取頻率。
- 目標平台。

選擇 Codec。

但 Writer 必須確認該 Codec：

- 在 Required Capability 中聲明。
- 是無損。
- 已成功 Round Trip。
- 不超過資源政策。

---

### 15.4 已壓縮格式

JPEG、MP4、ZIP、7z、PDF 等不一定適合再次壓縮。Planner 可以選 `Store`，但仍可以：

- 分塊。
- Hash。
- 去重。
- 建立索引。
- 加密。

---

## 第十六章　Dictionary

壓縮字典本身是保存平面物件，具有：

- Dictionary ID。
- 原始位元組。
- Hash。
- Codec Namespace。
- 訓練來源說明，可選。
- 必要能力。

Decoder 不得依賴封裝外部未聲明字典。

---

# 第六部　內容定址與去重

## 第十七章　去重範圍

支持：

```text
within-object
within-snapshot
within-archive
across-archive-store
remote-content-store
```

---

### 17.1 封裝內去重

若兩個 Slice 引用相同 `chunk_id`，只需保存一個 Payload Representation。

---

### 17.2 外部 Chunk

可引用外部內容庫：

```json
{
  "chunk_id": "b3:...",
  "locations": [
    {
      "scheme": "https",
      "uri": "...",
      "expected_size": 1234
    }
  ],
  "embedded_fallback": false
}
```

但若沒有 Embedded Fallback，該 Archive 不得標示為 `self-contained`。

---

### 17.3 去重與隱私

跨使用者去重可能洩露內容存在性。ANLA 定義：

- `private`：不做跨信任域去重。
- `archive-local`：只在單一 Archive。
- `trusted-store`：在同一信任域。
- `convergent`：高風險實驗模式，v0.1 禁止預設啟用。

---

# 第七部　隨機存取與串流

## 第十八章　串流建立

Writer 可以：

1. 寫 Bootstrap Header。
2. 依序寫 Chunk。
3. 寫 Manifest。
4. 寫 Index。
5. 寫 Footer。

接收端可在 Footer 到達前：

- 驗證 Record Header。
- 暫存 Chunk。
- 建立臨時索引。
- 不宣告 Snapshot Complete。

---

## 第十九章　隨機存取

Primary Index 至少映射：

```text
chunk_id → record_offset, payload_offset, compressed_length
object_id → manifest_entry
snapshot_id → footer_offset
```

Index 可被重建，因此其損壞不應摧毀 Payload。

---

## 第二十章　局部物化

Agent 可要求：

```json
{
  "snapshot": "b3:...",
  "objects": ["b3:...", "b3:..."],
  "destination": "...",
  "metadata_policy": "best-effort-report"
}
```

Resolver 計算最小 Chunk 集合：

$$
C_Q
=
\bigcup_{o\in Q}\operatorname{Chunks}(o)
$$

只讀取 $C_Q$。

---

# 第八部　智能平面

## 第二十一章　Packing Plan

### 21.1 Plan Schema

```json
{
  "plan_version": "0.1",
  "source_snapshot": "...",
  "selection": {
    "included_roots": ["..."],
    "excluded": []
  },
  "chunking_rules": [
    {
      "match": {"mime": "text/*"},
      "strategy": "fastcdc-text"
    }
  ],
  "codec_rules": [
    {
      "match": {"already_compressed": true},
      "codec": "store"
    }
  ],
  "metadata_policy": "full-supported",
  "verification": "full-round-trip",
  "resource_limits": {
    "memory_bytes": 4294967296,
    "threads": 8
  }
}
```

---

### 21.2 Plan 與 Writer 分離

```text
AI Planner
   ↓ JSON Plan
Policy Validator
   ↓ Approved Plan
Deterministic Writer
   ↓
ANLA Archive
```

Planner 不直接寫入任意二進位格式。

---

### 21.3 Decision Log

可選保存：

```json
{
  "decision_id": "...",
  "target": "object-id",
  "choice": "zstd-level-9",
  "alternatives": [
    {"codec": "store", "size": 1000000},
    {"codec": "zstd-3", "size": 410000},
    {"codec": "zstd-9", "size": 360000}
  ],
  "reason_codes": [
    "cold-data",
    "high-text-redundancy",
    "decompression-budget-satisfied"
  ],
  "planner": {
    "type": "model",
    "name": "...",
    "version": "..."
  }
}
```

Decision Log 屬 `AUXI`，不影響解壓。

---

## 第二十二章　可選索引

可選：

- Full-text。
- MIME。
- Language。
- Symbol／AST。
- Image Perceptual Hash。
- Audio Fingerprint。
- Vector Embedding。
- Relationship Graph。
- Access Heat。

每個索引必須標示：

- Schema。
- Generator。
- Version。
- Source Snapshot。
- 可否重建。
- 是否包含私人資訊。
- 是否加密。

---

## 第二十三章　AI 不得執行的決策

沒有使用者或 Policy 明確批准時，Planner 不得：

- 排除檔案。
- 改寫原始檔案。
- 將無損改為有損。
- 只保存 Recipe。
- 下載外部內容取代本地內容。
- 覆蓋既有 Snapshot。
- 解除加密。
- 上傳私人索引。
- 執行封裝內程式。
- 變更檔案權限語義。

---

# 第九部　安全

## 第二十四章　解壓威脅模型

ANLA Decoder 必須防止：

- 路徑穿越。
- 絕對路徑覆寫。
- Symlink／Hard Link 逃逸。
- Unicode 正規化碰撞。
- 大小寫碰撞。
- Compression Bomb。
- Chunk Bomb。
- 深度遞迴。
- Manifest Billion Laughs 類攻擊。
- 超大宣告長度。
- 整數溢位。
- Codec 記憶體耗盡。
- 惡意 Sparse File。
- 特殊檔案建立。
- 未授權 ACL 套用。
- 外部 Chunk SSRF。
- 簽章繞過。
- Parser 差異攻擊。

---

## 第二十五章　資源限制

解壓請求必須支援：

```json
{
  "max_output_bytes": 100000000000,
  "max_objects": 1000000,
  "max_path_depth": 256,
  "max_name_bytes": 4096,
  "max_chunk_uncompressed": 67108864,
  "max_ratio_per_chunk": 1000,
  "max_total_ratio": 100,
  "max_memory_bytes": 4294967296,
  "max_external_fetches": 0
}
```

超出限制必須停止並回報，而不是自動放寬。

---

## 第二十六章　安全提取模式

### Inspect Only

不建立檔案。

### Quarantine Extract

- 不套用可執行權限。
- 不建立 Symlink。
- 不建立特殊檔案。
- 不套用 ACL。
- 改寫危險名稱。
- 生成報告。

### Exact Restore

只在受信任 Archive、相容平台與使用者明確授權下使用。

---

# 第十部　加密與簽章

## 第二十七章　壓縮與加密順序

必須：

```text
Raw Chunk
→ Compress
→ Encrypt
```

不能先加密再期望一般壓縮。

---

## 第二十八章　Chunk 加密

v0.1 建議採 AEAD Profile，完整演算法另由 Security Profile 定義。

每個加密 Chunk 必須有：

- Algorithm ID。
- Nonce。
- Key Slot ID。
- Associated Data。
- Ciphertext Length。
- Authentication Tag。

Associated Data 至少綁定：

- Archive ID。
- Snapshot ID 或 Security Context。
- Chunk ID。
- Codec Descriptor。

---

## 第二十九章　Metadata 加密

可分級：

```text
payload-only
payload-and-paths
full-manifest
opaque-archive
```

若 Manifest 加密，Bootstrap 仍需保留最低能力聲明，以便 Decoder 知道需要何種解密模組。

---

## 第三十章　簽章

可使用 COSE_Sign1 或等價公開 Profile 對以下內容簽章：

$$
\operatorname{Sign}(
\operatorname{archive\_id}
\Vert
\operatorname{snapshot\_id}
\Vert
\operatorname{preservation\_root}
)
$$

簽章不替代 Chunk Hash。

---

# 第十一部　損壞復原

## 第三十一章　檢測與復原分離

Hash 可以偵測損壞：

$$
H(B)\neq H(\widehat{B})
$$

但無法自行修復。

---

## 第三十二章　最低復原能力

v0.1 必須：

- Footer 可重複。
- Manifest 可選重複。
- Record 有同步 Magic。
- Index 可重建。
- Chunk 可獨立驗證。
- 單一 Chunk 損壞不阻止其他 Chunk 提取。
- 掃描器能列出可恢復物件。

---

## 第三十三章　Parity Extension

`PARI` Record 可在後續 Profile 中使用 Reed–Solomon 或其他 Erasure Code。

v0.1 Core Decoder 可以跳過 Parity，但不能把存在 Parity 誤認為 Payload。

---

# 第十二部　版本與擴充

## 第三十四章　版本策略

### Major

破壞核心解析或語義。

### Minor

新增可選能力，不破壞既有 Core Decoder。

---

## 第三十五章　Capability URI

```text
anla:core:objects:1
anla:core:chunks:1
anla:codec:zstd:rfc8878
anla:index:fulltext:1
anla:security:cose-sign1:1
```

Required 與 Optional 必須分開。

---

## 第三十六章　Registry

正式標準化前，以公開 Git Repository 維護：

- Record Type。
- Codec ID。
- Metadata Namespace。
- Capability。
- Error Code。
- Test Vector。

不得由單一私有服務作為唯一註冊來源。

---

# 第十三部　CLI 與 Agent API

## 第三十七章　CLI

```bash
anla plan <source> --policy policy.json --json
anla pack <source> --plan plan.json --output project.anla
anla inspect project.anla --json
anla list project.anla --snapshot latest --json
anla verify project.anla --mode full --json
anla extract project.anla --to output --safe
anla extract project.anla --object <id> --to output
anla update project.anla <source> --append
anla snapshots project.anla --json
anla diff project.anla <snapshot-a> <snapshot-b>
anla recover project.anla --scan
anla export project.anla --format zip --output project.zip
```

---

## 第三十八章　Exit Code

```text
0  success
1  generic failure
2  invalid input
3  unsupported required capability
4  manifest invalid
5  integrity failure
6  signature failure
7  decryption failure
8  resource limit exceeded
9  unsafe path or object
10 incomplete external content
11 extraction fidelity degraded
12 recovery partially successful
```

---

## 第三十九章　Structured Error

```json
{
  "error": {
    "code": "ANLA_UNSUPPORTED_REQUIRED_CAPABILITY",
    "message": "The archive requires codec.example.v2.",
    "retryable": false,
    "archive_safe": true,
    "details": {
      "capability": "anla:codec:example:2"
    }
  }
}
```

---

## 第四十章　MCP／Agent Tools

```text
archive_plan
archive_pack
archive_inspect
archive_list_objects
archive_verify
archive_extract_objects
archive_append_snapshot
archive_diff_snapshots
archive_get_extraction_report
archive_export_view
```

不提供：

```text
archive_run_embedded_program
archive_load_arbitrary_decoder
```

---

# 第十四部　參考實作

## 第四十一章　技術棧

### Core

- Rust Stable。
- `serde`。
- Deterministic CBOR library。
- `blake3`。
- `zstd`。
- `crc32c`。
- `fastcdc` 或自行鎖定的規範實作。

### Optional C ABI

提供最小 Decoder API，便於其他語言整合。

### Planner

獨立程序，透過 JSON 或 Named Pipe 連接，不進入核心 Parser。

---

## 第四十二章　Repository

```text
anla/
├─ README.md
├─ LICENSE
├─ SECURITY.md
├─ SPEC.md
├─ schemas/
│  ├─ manifest.cddl
│  ├─ plan.schema.json
│  └─ extraction-report.schema.json
├─ crates/
│  ├─ anla-core/
│  ├─ anla-format/
│  ├─ anla-codec/
│  ├─ anla-chunk/
│  ├─ anla-fsmodel/
│  ├─ anla-security/
│  ├─ anla-cli/
│  └─ anla-planner-sdk/
├─ tools/
│  ├─ anla-inspect/
│  ├─ anla-recover/
│  └─ anla-fuzz/
├─ fixtures/
│  ├─ paths/
│  ├─ metadata/
│  ├─ corrupt/
│  ├─ bombs/
│  └─ cross-platform/
└─ conformance/
```

---

## 第四十三章　Parser 原則

- Bounds Check 在配置前。
- 不信任宣告長度。
- 迭代解析，限制遞迴。
- 整數運算使用 Checked Arithmetic。
- 未知 Required Record 拒絕。
- Codec 解壓置於資源限制內。
- Fuzz 所有 Record 與 Manifest。
- 建立差異測試，確保多實作一致。

---

# 第十五部　Conformance

## 第四十四章　Profile

### ANLA-Core-Reader

- 讀取 Header、Record、Footer。
- 解析 Deterministic CBOR Manifest。
- Store。
- Zstandard。
- 普通檔案與資料夾。
- BLAKE3 驗證。
- 安全路徑。
- Extraction Report。

### ANLA-Core-Writer

包含 Core Reader，另支援：

- 建立單 Snapshot。
- Fixed Chunk。
- Whole Object。
- Store／Zstandard。
- 完整 Manifest。
- Footer。

### ANLA-Advanced-Writer

- FastCDC。
- 去重。
- 多 Snapshot。
- 小檔案聚合。
- 索引。
- Agent Plan。

### ANLA-Preservation

- POSIX／Windows／macOS Metadata。
- Link 與 Sparse。
- 完整 Fidelity Report。
- Recovery。

---

## 第四十五章　測試向量

必須包含：

1. 空 Archive。
2. 空檔案。
3. 單一小檔案。
4. 大檔案多 Chunk。
5. 重複 Chunk。
6. UTF-8 多語路徑。
7. POSIX 非 UTF-8 路徑位元組。
8. Windows UTF-16 特殊名稱。
9. NFC／NFD 衝突。
10. 大小寫衝突。
11. Symlink。
12. Hard Link。
13. Sparse File。
14. Alternate Data Stream。
15. 損壞 Chunk。
16. 損壞 Footer。
17. 未知 Optional Record。
18. 未知 Required Record。
19. Compression Bomb。
20. Append Snapshot。
21. 加密 Archive。
22. 簽章錯誤。
23. Legacy ZIP Import Metadata。

---

# 第十六部　Benchmark

## 第四十六章　基線

- ZIP Deflate。
- 7z LZMA2。
- TAR + Zstandard。
- 固定 1 MiB + Zstandard。
- FastCDC + Zstandard。
- ANLA Planner。

---

## 第四十七章　資料集

- Linux Kernel Source。
- 多版本 Git Working Tree。
- Node／Rust／Python 專案。
- 模型權重。
- 圖片、音訊、影片。
- Office／PDF。
- 遊戲資源。
- 備份快照。
- 多語與舊編碼檔名。
- Windows Metadata Fixture。

---

## 第四十八章　指標

### 壓縮比

$$
R_c
=
\frac{B_{\mathrm{archive}}}{B_{\mathrm{source}}}
$$

### Pack Throughput

$$
T_p
=
\frac{B_{\mathrm{source}}}{t_{\mathrm{pack}}}
$$

### Extract Throughput

$$
T_e
=
\frac{B_{\mathrm{restored}}}{t_{\mathrm{extract}}}
$$

### Dedup Ratio

$$
R_d
=
1-
\frac{B_{\mathrm{unique\ chunks}}}{B_{\mathrm{chunk\ references}}}
$$

### 增量放大

$$
A_{\Delta}
=
\frac{B_{\mathrm{new\ records}}}{B_{\mathrm{changed\ source}}}
$$

### Planner Return

$$
G_p
=
B_{\mathrm{fixed\ baseline}}
-
B_{\mathrm{planned}}
-
C_{\mathrm{planning}}
$$

需將規劃 CPU、能源和延遲折算後再宣稱收益。

---

# 第十七部　開發路線

## 第四十九章　Milestone 0：規格固定

- Magic。
- Header。
- Record Frame。
- Footer。
- CDDL。
- BLAKE3。
- Store／Zstandard。
- 安全限制。
- Test Vector。

---

## 第五十章　Milestone 1：Core Reader／Writer

- 單 Snapshot。
- 普通檔案與資料夾。
- Fixed Chunk。
- Verify。
- Extract。
- Cross-platform CI。

---

## 第五十一章　Milestone 2：完整 Filesystem Model

- Symlink。
- Hard Link。
- Sparse。
- POSIX Metadata。
- Windows Metadata。
- macOS Metadata。
- Fidelity Report。

---

## 第五十二章　Milestone 3：增量與去重

- FastCDC。
- 跨檔去重。
- Append Snapshot。
- Diff。
- Recovery Scan。

---

## 第五十三章　Milestone 4：Agent Planner

- Plan Schema。
- Rule-based Planner。
- Benchmark Planner。
- AI Planner Adapter。
- Decision Log。
- Policy Validator。

先建立規則式 Planner 作為可重現基線，再評估模型是否真正提高效果。

---

## 第五十四章　Milestone 5：UI 與掛載

- 人類 GUI。
- Agent Observatory。
- Read-only Mount。
- Partial Materialization。
- ZIP／TAR Export。

---

# 第十八部　開放問題

1. BLAKE3 是否作為唯一 Core Hash，或同時要求 SHA-256？
2. Deterministic CBOR Profile 應採 RFC 8949 Core Requirements，還是另鎖定更嚴格 CDE？
3. FastCDC 參數如何形成永久穩定 Profile？
4. Windows NT 名稱與 POSIX Byte Name 如何建立最小跨平台模型？
5. Metadata Sidecar 是否應有獨立標準？
6. Snapshot Manifest 應採單一 Merkle Root 還是多 Root？
7. 加密 Archive 如何兼顧局部存取與 Metadata 隱私？
8. Parity 是否進入 Core Preservation Profile？
9. 多 Volume Archive 如何保持 Snapshot 原子性？
10. 遠端 Chunk Store 如何避免 SSRF、內容替換與可用性依賴？
11. Agent Planner 如何證明沒有漏封裝？
12. 如何對 Packing Plan 做形式化 Coverage Verification？
13. 如何避免 AI Planner 為壓縮率犧牲解壓延遲？
14. 如何建立跨實作 Parser 差異測試？
15. `.anla` 是否應保持單檔，或同時定義 Directory Layout？

---

# 結論

ANLA v0.1 不試圖一次重建整個資訊理論，也不把生成模型當作解碼器。

它只建立一個嚴格且可實作的地基：

- 原始內容必須完整保存。
- 路徑與平台 Metadata 必須明確表示。
- Codec 必須自描述。
- Chunk 必須可獨立驗證。
- Snapshot 必須可追加和回滾。
- Agent 可以規劃，但不能繞過 Writer 的無損驗證。
- 智能索引可以消失，Archive 仍然可讀。
- 解壓不需要 AI。
- 未知必要能力必須安全失敗。
- 所有失真型擴充均不屬於 v0.1。

一句話定義：

> **ANLA 是一種由 AI 可自主規劃、由確定性 Writer 建立、由模型獨立 Decoder 精確還原的無損、內容定址、版本化封裝格式。**

---

# 參考規格與工程資料

1. PKWARE, *APPNOTE.TXT — ZIP File Format Specification*.  
   https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT

2. IETF, *RFC 8878: Zstandard Compression and the application/zstd Media Type*.  
   https://www.rfc-editor.org/rfc/rfc8878

3. IETF, *RFC 8949: Concise Binary Object Representation (CBOR)*.  
   https://www.rfc-editor.org/rfc/rfc8949

4. IETF, *RFC 9052: CBOR Object Signing and Encryption (COSE)*.  
   https://www.rfc-editor.org/rfc/rfc9052

5. IETF, *RFC 8493: The BagIt File Packaging Format*.  
   https://www.rfc-editor.org/rfc/rfc8493

6. BLAKE3 Team, *BLAKE3*.  
   https://github.com/BLAKE3-team/BLAKE3  
   https://github.com/BLAKE3-team/BLAKE3-specs

7. W. Xia et al., *FastCDC*, USENIX ATC 2016.  
   https://www.usenix.org/conference/atc16/technical-sessions/presentation/xia

8. IPLD, *Content Addressable aRchives*.  
   https://ipld.io/specs/transport/car/

9. Open Container Initiative, *Image Specification*.  
   https://github.com/opencontainers/image-spec

10. Unicode Consortium, *Unicode Standard Annex #15: Unicode Normalization Forms*.  
    https://unicode.org/reports/tr15/
