# ACCR：自主上下文編譯運行時

## Autonomous Context Compilation Runtime

**Technical Whitepaper v0.1**  
**EveMissLab / TDCD Engineering Layer**  
**Date:** 2026-08-15

## 摘要

ACCR（Autonomous Context Compilation Runtime）是一個長程 AI / Agent 上下文治理運行時。它不把「記憶」視為一個單一向量資料庫，也不把「壓縮」視為上下文管理的最終答案，而是把完整歷史、低成本投影與當下工作上下文分離，建立一個持續執行的：

$$
\boxed{
\text{Ingest}
\rightarrow
\text{Canonicalize}
\rightarrow
\text{Compile}
\rightarrow
\text{Project}
\rightarrow
\text{Govern}
\rightarrow
\text{Expand}
\rightarrow
\text{Converge}
\rightarrow
\text{Commit}
}
$$

循環。

ACCR 是 Three-Domain Context Dynamics（TDCD）Series I 的工程落地層。TDCD 將記憶系統區分為：

$$
\mathcal D_t
=
\text{Canonical Domain},
$$

$$
\mathcal P_t
=
\text{Projection Domain},
$$

$$
\mathcal W_t
=
\text{Working Context Domain}.
$$

ACCR 的核心目標不是讓模型「永遠看到更多」，而是讓完整歷史可以安全離開當下，並在真正需要時以可驗證地址重新展開。

本文定義 ACCR 的系統邊界、核心模組、資料流、canonical authority、Context Governor、ANLA adapter、MCP bus、雲端資料庫層、maintenance scheduler、observability 與 MVP 實作路線。

核心設計原則為：

$$
\boxed{
\text{Store the past exactly; project it cheaply; govern the present selectively.}
}
$$

---

# 1. ACCR 解決的不是「記憶容量」而是「上下文生命週期」

傳統長程記憶系統常被描述成：

$$
\text{history}
\rightarrow
\text{embedding}
\rightarrow
\text{vector search}
\rightarrow
\text{prompt}.
$$

這條鏈只能回答部分問題。

它不能天然解決：

- 哪些舊資訊已被新版本取代；
- 哪些資訊只在另一個 branch 有效；
- 哪些摘要省略了未來可能再次重要的細節；
- 哪些候選雖然語義相似，但現在不應進入工作域；
- 哪些記憶被清掉後應如何 byte-exact 恢復；
- 哪些維護任務已經落後；
- governor 是否正在形成 stale bias；
- active context 是否因歷史累積而污染。

ACCR 因此把問題重新定義為：

$$
\boxed{
\text{Context Lifecycle Governance}.
}
$$

---

# 2. 與 TDCD Series I 的對應

## 2.1 Paper 01：三域

$$
\mathcal D
\leftrightarrow
\mathcal P
\leftrightarrow
\mathcal W.
$$

ACCR 對應：

- Canonical Store；
- Projection Store；
- Working Context Assembler。

## 2.2 Paper 02：Context Governor

ACCR 實作：

$$
\{
\operatorname{admit},
\operatorname{retain},
\operatorname{evict},
\operatorname{recall},
\operatorname{supersede},
\operatorname{fork},
\operatorname{recheck}
\}.
$$

## 2.3 Paper 03：尋址與相位

ACCR 分離：

$$
\text{Canonical Address}
\neq
\text{Semantic Candidate Address}
\neq
\text{Typed Search Phase}
\neq
\Psi_\tau.
$$

## 2.4 Paper 04：治理器學習

ACCR 保存：

- hard validity gate；
- calibration；
- verifier feedback；
- drift state；
- self-overturn；
- governor checkpoint。

## 2.5 Paper 05：全域穩定

ACCR 顯式維護：

$$
Q_t
$$

作為 maintenance backlog，並要求 active footprint、maintenance throughput、retrieval latency 與 canonical consistency 分別被監控。

---

# 3. 系統邊界

ACCR 不是：

1. LLM provider；
2. 單一向量資料庫；
3. 單純摘要服務；
4. MCP Server 的 session state；
5. ANLA 的別名；
6. 一個把所有聊天永久塞回 prompt 的工具。

ACCR 是：

$$
\boxed{
\text{an explicit stateful runtime above stateless tool transport}.
}
$$

MCP 負責能力暴露與 transport。

ACCR 負責：

- context lifecycle；
- explicit handles；
- governor state；
- maintenance；
- canonical lineage；
- active-context assembly。

---

# 4. 高階架構

```text
                         +----------------------+
                         |      LLM / Agent     |
                         +----------+-----------+
                                    |
                                    v
                         +----------------------+
                         |   ACCR Runtime Core  |
                         | context_run_id       |
                         +--+----+----+----+----+
                            |    |    |    |
                  +---------+    |    |    +----------+
                  v              v    v               v
          +---------------+ +---------+---------+ +---------+
          | Context       | | Context Governor  | | Metrics |
          | Assembler     | | Gate / Score /    | | Audit   |
          | W_t           | | Hysteresis        | | Trace   |
          +-------+-------+ +---------+---------+ +---------+
                  |                   |
                  +---------+---------+
                            |
                            v
                  +--------------------+
                  | Projection Compiler|
                  | P_t / candidates   |
                  +---------+----------+
                            |
          +-----------------+------------------+
          |                                    |
          v                                    v
 +------------------+                 +---------------------+
 | ANLA Adapter     |                 | Cloud Memory Layer  |
 | exact archive   |                 | metadata / lineage  |
 | project/expand  |                 | index / events      |
 +--------+---------+                 +----------+----------+
          |                                      |
          v                                      v
 +------------------+                 +---------------------+
 | Canonical Bytes  |<--------------->| Object Store / DB  |
 | digest-addressed | replicas        | canonical replicas  |
 +------------------+                 +---------------------+

          MCP = transport / capability bus around these services
```

---

# 5. Canonical authority

ACCR 不把「某個資料庫」本身當成真理來源。

Canonical authority 定義在：

$$
O
=
(
id,
bytes,
digest,
provenance,
version,
lineage
).
$$

只要不同 backend 保存的：

$$
bytes
$$

具有相同 canonical digest，則可以被視為同一 canonical object 的 replica。

因此：

$$
\boxed{
\text{Canonical identity is content-and-lineage based, not backend based}.
}
$$

例如同一 object 可以存在於：

- ANLA archive；
- local filesystem；
- S3-compatible object storage；
- cloud blob store；
- backup archive。

其 canonical record 仍只有一個。

---

# 6. Canonical object

最小 canonical object：

```json
{
  "object_id": "obj_...",
  "digest": "sha256:...",
  "object_type": "conversation_turn",
  "created_at": "...",
  "source": {
    "kind": "chat",
    "locator": "..."
  },
  "branch_id": "branch_main",
  "persistence_class": "active",
  "version_key": "project.deadline",
  "supersedes": null,
  "status": "valid",
  "replicas": [
    {
      "backend": "anla",
      "locator": "turns/000123-user.md"
    }
  ]
}
```

其中：

$$
digest
$$

驗證 bytes；

$$
object\_id
$$

提供穩定邏輯身份；

$$
version\_key
$$

允許 supersession；

$$
replicas
$$

允許多 backend。

---

# 7. Canonical Store

Canonical Store 負責：

1. 原始 bytes；
2. digest；
3. canonical metadata；
4. version lineage；
5. branch provenance；
6. exact address；
7. replica registry。

MVP 參考配置：

```text
PostgreSQL-compatible DB
    canonical metadata
    version lineage
    branches
    governance events
    maintenance jobs

S3-compatible object store
    canonical raw bytes
    large files
    attachments

ANLA
    snapshot archive
    exact projection/expansion path
    archive verification
```

此配置只是 reference profile。

ACCR API 必須保持 backend-agnostic。

---

# 8. Projection Store

投影域：

$$
\mathcal P_t
$$

只保存 derivative representation。

包括：

- summary；
- embedding；
- semantic segment；
- tags；
- dependency edges；
- typed search-phase features；
- persistence；
- version head cache；
- branch state；
- importance statistics；
- canonical pointer。

投影物件永遠必須能回答：

> 我從哪個 canonical object 來？

因此：

$$
projection.canonical\_id\neq null.
$$

---

# 9. ANLA 在 ACCR 中的位置

目前 ANLA MCP surface 已提供：

- archive survey；
- verify；
- snapshots；
- list；
- diff；
- manifest；
- writer comparison；
- `context_project`；
- `context_expand`；
- `context_find`；
- `context_address`；
- `context_status`。

其中對 ACCR 最重要的是：

$$
\boxed{
\text{project}
\rightarrow
\text{find/address}
\rightarrow
\text{expand exactly}.
}
$$

因此 ANLA 很適合作為：

$$
\boxed{
\text{Exact Archive + Recoverable Projection Substrate}.
}
$$

但目前這個已連接的 MCP surface 沒有暴露完整的 `pack/ingest` writer lifecycle。

因此 MVP 需要：

```text
ArchiveWriterAdapter
```

其實作可以是：

- 本地 ANLA CLI；
- ANLA local service；
- future MCP writer tool；
- queue worker。

ACCR 不應假裝目前 MCP surface 已經完成 ingest 閉環。

---

# 10. MCP 在 ACCR 中的位置

MCP 的角色：

$$
\boxed{
\text{transport}
+
\text{capability discovery}
+
\text{tool invocation}.
}
$$

ACCR 的 state 不依賴隱藏 MCP session。

所有狀態型操作應使用顯式 handle，例如：

```json
{
  "context_run_id": "ctx_01...",
  "governor_checkpoint_id": "gov_08...",
  "branch_id": "branch_main"
}
```

因此即使請求被送到不同 server instance，只要它們可以訪問 ACCR state store，即可繼續執行。

---

# 11. Context Run

一次 active reasoning lifecycle 定義為：

$$
R_t
=
(
context\_run\_id,
agent,
task,
branch,
budget,
regime,
governor
).
$$

Context Run 不是永續 session。

它是一個可以：

- 建立；
- checkpoint；
- commit；
- close；
- reopen from canonical state

的顯式 runtime object。

---

# 12. Context Prepare

一次 query 進來後：

$$
q_t
$$

ACCR 執行：

$$
q_t
\rightarrow
\tau_t
\rightarrow
C_t
\rightarrow
\phi_t
\rightarrow
\chi_t
\rightarrow
\Psi_t
\rightarrow
E_t
\rightarrow
\mathcal W_t.
$$

具體步驟：

1. Build contextual moment；
2. semantic candidate retrieval；
3. typed relational qualification；
4. hard validity gate；
5. governor scoring；
6. hysteresis；
7. dependency closure；
8. canonical exact expansion；
9. token-budget convergence；
10. emit ContextPlan。

---

# 13. ContextPlan

ContextPlan 是 ACCR 和 Agent 之間最重要的契約。

```json
{
  "context_run_id": "ctx_...",
  "plan_id": "plan_...",
  "query_digest": "sha256:...",
  "branch_id": "branch_main",
  "budget": {
    "max_input_tokens": 64000
  },
  "items": [
    {
      "canonical_id": "obj_...",
      "role": "active_constraint",
      "reason": "current version head",
      "score": 0.91,
      "confidence": 0.84,
      "restoration": {
        "backend": "anla",
        "locator": "turns/..."
      }
    }
  ],
  "omitted": [
    {
      "canonical_id": "obj_...",
      "reason": "cold",
      "restorable": true
    }
  ]
}
```

Plan 是可 audit 的。

它不能只有「最後 prompt」。

---

# 14. Hard validity gate

對候選 $O$：

$$
\chi_\tau(O)
=
\chi_{id}
\chi_{ver}
\chi_{branch}
\chi_{prov}
\chi_{access}.
$$

若：

$$
\chi_\tau(O)=0,
$$

則：

$$
\Psi_\tau(O)=-\infty.
$$

MVP 第一版 hard gate 必須是 deterministic。

不得讓 LLM judge 靜默覆寫：

- canonical digest failure；
- revoked access；
- invalid branch；
- superseded current fact；
- missing required provenance。

---

# 15. Governor

MVP governor 使用 hybrid policy：

$$
\Psi_\tau
=
\Psi_{rule}
+
\omega_t\Psi_{learned}.
$$

v0.1 可先令：

$$
\omega_t=0
$$

或只在 shadow mode 啟用 learned score。

第一版 rule features：

- semantic relevance；
- branch match；
- version freshness；
- persistence class；
- dependency necessity；
- recency conditioned by persistence；
- provenance；
- context cost；
- recent usage；
- conflict state。

目標不是一開始就訓練最強 governor。

目標是建立：

$$
\boxed{
\text{a measurable governor lifecycle}.
}
$$

---

# 16. Hysteresis

ACCR 使用：

$$
\theta_{in}>\theta_{out}.
$$

當 object 不在 active set：

$$
\Psi(O)\geq\theta_{in}
$$

才 admit。

已在 active set：

$$
\Psi(O)>\theta_{out}
$$

則 retain。

這避免邊界 candidate 每輪反覆：

$$
\operatorname{admit}
\leftrightarrow
\operatorname{evict}.
$$

---

# 17. Working Context Assembler

Assembler 接收：

- ContextPlan；
- canonical expansions；
- current query；
- system constraints；
- token budget。

它輸出：

$$
\mathcal W_t.
$$

排序不是單純 score descending。

至少按 role 區分：

1. hard constraints；
2. active task state；
3. current version facts；
4. dependencies；
5. procedural memory；
6. relevant historical evidence；
7. optional context。

當 budget 不足，從低優先層開始收斂。

---

# 18. Commit Turn

模型完成一次 reasoning / action 後，ACCR 執行：

```text
Agent output
  -> canonical event
  -> provenance
  -> new / updated objects
  -> version analysis
  -> maintenance jobs
  -> governor feedback
  -> context_run checkpoint
```

commit 不等於「把整個模型輸出當成事實」。

輸出應分類為：

- user-provided fact；
- tool evidence；
- model inference；
- proposal；
- decision；
- generated artifact；
- temporary scratch state。

不同 object type 使用不同 canonical policy。

---

# 19. 版本更新

若：

$$
O_{old}\prec_v O_{new},
$$

ACCR：

1. 保留 $O_{old}$；
2. 將 active head 指向 $O_{new}$；
3. 產生 supersession event；
4. 把 $O_{old}$ 移出普通 active candidates；
5. 產生 dependency recheck jobs。

因此：

$$
\boxed{
\text{supersede}
\neq
\text{delete}.
}
$$

---

# 20. Dependency invalidation

若：

$$
O_i\rightarrow O_j
$$

表示 $O_j$ 依賴 $O_i$，而 $O_i$ 失效，則：

$$
O_j
$$

進入：

```text
needs_revalidation
```

而不是自動刪除。

Maintenance Scheduler 產生：

$$
\operatorname{recheck}(O_j).
$$

---

# 21. Maintenance Scheduler

所有非即時必要工作放入：

$$
Q_t.
$$

job types：

- compile projection；
- compute embedding；
- verify digest；
- rebuild version head；
- propagate invalidation；
- refresh summary；
- archive snapshot；
- counterfactual audit；
- compact index；
- governor evaluation。

每個 job 具有：

```json
{
  "job_id": "job_...",
  "kind": "projection_compile",
  "priority": 50,
  "canonical_id": "obj_...",
  "created_at": "...",
  "deadline": null,
  "attempts": 0
}
```

---

# 22. Backpressure

ACCR 必須監控：

$$
Q_t.
$$

設定：

$$
Q_{soft}<Q_{hard}.
$$

當：

$$
Q_t>Q_{soft},
$$

降低非必要 projection / audit。

當：

$$
Q_t>Q_{hard},
$$

只保證：

- canonical durable ingest；
- critical invalidation；
- current version head；
- active task maintenance。

其餘 deferred。

---

# 23. 三種儲存溫度

## Hot

直接支援當下工作。

包含：

- active projection；
- current branch；
- current version heads；
- recent dependency neighborhood。

## Warm

可低延遲搜尋。

包含：

- embeddings；
- topic/phase index；
- recent archive metadata。

## Cold

canonical history。

包含：

- old versions；
- inactive branches；
- historical raw events；
- large artifact archives。

Cold 不等於 stale。

---

# 24. Semantic Channel 與 Phase Channel

v0.1 不允許把 embedding 叫 phase。

Semantic channel：

$$
E(O),E(q).
$$

Phase layer：

$$
\Theta_{\mathrm{mem},T}(O,\tau)
$$

必須是明確 typed relational representation。

MVP 可以先：

```text
L1 semantic candidates
L2 typed contextual qualification
```

而不假裝已經完成完整 PH-6 transport dynamics。

這與 Phase Canon 保持一致。

---

# 25. Exact Expansion

任何被選入工作域、且需要 authoritative source 的 object，最終透過：

$$
a_D(O)
$$

解析。

若 ANLA backend：

```text
context_address
  -> canonical path / byte range
  -> context_expand
```

若 object store：

```text
object_id
  -> replica locator
  -> bytes
  -> digest verify
```

返回成功條件：

$$
H(bytes_{returned})
=
digest_{canonical}.
$$

---

# 26. Context Cleaner

Context Cleaner 不修改 canonical history。

它只操作：

$$
\mathcal W_t
$$

與：

$$
\mathcal P_t^{hot}.
$$

最小清理規則：

- exact duplicate -> collapse；
- superseded -> evict from normal active set；
- wrong branch -> isolate；
- expired temporary state -> evict；
- low-relevance cold -> demote；
- unresolved conflict -> mark, not silently merge；
- persistent method -> protected from recency-only eviction。

---

# 27. Governor Checkpoint

每次 policy/config 變更建立：

$$
\Gamma_t.
$$

包含：

```json
{
  "checkpoint_id": "gov_...",
  "policy_version": "rule-v0.1",
  "threshold_in": 0.72,
  "threshold_out": 0.58,
  "weights": {},
  "calibration_revision": "none",
  "created_at": "...",
  "digest": "sha256:..."
}
```

ACCR 可以：

$$
\Gamma_{t+1}\rightarrow\Gamma_t
$$

rollback。

---

# 28. Audit log

每個重大治理動作記錄：

```json
{
  "event_id": "gev_...",
  "context_run_id": "ctx_...",
  "canonical_id": "obj_...",
  "action": "evict",
  "reason_codes": [
    "superseded"
  ],
  "score_before": 0.81,
  "score_after": null,
  "gate": {
    "version": false
  },
  "governor_checkpoint_id": "gov_...",
  "timestamp": "..."
}
```

audit log 本身也是 canonical event stream。

---

# 29. Counterfactual Audit

ACCR 定期抽樣已被 evict 的 object：

$$
O\notin\mathcal W_t
$$

進行 shadow evaluation。

目的：

$$
\boxed{
\text{estimate false eviction}.
}
$$

MVP 不必讓 audit 直接改 production context。

可以先 shadow mode：

```text
evicted object
 -> shadow expand
 -> alternate context plan
 -> offline evaluator
 -> audit metric
```

---

# 30. 多 Agent

共享：

$$
\mathcal D^{shared}.
$$

但各 Agent 具有：

$$
\mathcal W_t^{(i)},
$$

$$
\Gamma_t^{(i)},
$$

以及：

$$
\Psi_t^{(i)}.
$$

因此：

$$
\boxed{
\text{shared memory}
\neq
\text{shared present}.
}
$$

ACCR 可另外建立 group branch / shared context plan，但不能默認所有 Agent 的 active context 完全一致。

---

# 31. 雲端資料庫責任

Cloud DB 保存：

- canonical metadata；
- object registry；
- branch graph；
- version graph；
- projection metadata；
- relation graph；
- governance events；
- context runs；
- governor checkpoints；
- maintenance jobs；
- metrics。

不建議把大型 canonical bytes 全塞 relational row。

大型 bytes 放 object storage / archive backend。

---

# 32. Reference Database Tables

核心表：

```text
canonical_objects
canonical_replicas
branches
versions
relations
projections
semantic_segments
context_runs
context_plans
context_plan_items
governor_checkpoints
governance_events
maintenance_jobs
audit_results
metrics_timeseries
```

詳細 schema 見 Data Model 文件。

---

# 33. MCP Tool Surface

第一版 ACCR 可暴露：

```text
accr.status
accr.ingest
accr.prepare_context
accr.expand
accr.commit
accr.recheck
accr.get_object
accr.get_plan
accr.run_maintenance
accr.metrics
```

其中每次 stateful 呼叫都顯式攜帶：

```text
context_run_id
branch_id
checkpoint_id
```

而不依賴 protocol 隱藏 session。

---

# 34. ANLA Adapter Contract

ACCR 對 ANLA 使用：

```text
status
project
find
address
expand
verify
snapshots
diff
manifest
```

並另外定義抽象 writer：

```text
ArchiveWriterAdapter.append(...)
ArchiveWriterAdapter.snapshot(...)
```

目前若 MCP 沒有 writer tool，就由 local worker 實作。

因此 archive read plane 與 write plane 可以先分開。

---

# 35. MVP 不做什麼

v0.1 不做：

1. 全自動 reinforcement-learning governor；
2. 自動修改 hard validity schema；
3. universal phase holonomy；
4. 跨所有資料庫自動 migration；
5. 無限規模保證；
6. autonomous permanent deletion；
7. 全自動 fact truth adjudication；
8. 把 LLM confidence 當 truth probability。

---

# 36. MVP 必須做到什麼

v0.1 必須做到：

1. canonical bytes 可驗證；
2. projection 可指回 canonical object；
3. explicit context run；
4. prepare context；
5. exact expansion；
6. hard gate；
7. branch isolation；
8. supersession；
9. active eviction 不刪 canonical；
10. maintenance queue；
11. audit events；
12. metrics；
13. governor rollback；
14. ANLA read integration；
15. cloud metadata persistence。

---

# 37. 最小生命週期

```text
1. ingest raw turn
2. write canonical bytes
3. create canonical metadata
4. enqueue projection job
5. compile projection
6. receive new query
7. create context_run
8. retrieve candidates
9. gate candidates
10. score candidates
11. exact expand selected objects
12. build working context
13. model executes
14. commit output/events
15. update version/branch state
16. enqueue maintenance
17. record metrics
```

如果這條鏈完整跑通，ACCR 才算真正形成 MVP 閉環。

---

# 38. 狀態機

```text
RAW
 |
 v
DURABLE
 |
 v
CANONICALIZED
 |
 +----------+
 |          |
 v          v
PROJECTED   MAINTENANCE_PENDING
 |
 v
CANDIDATE
 |
 v
VALID
 |
 v
ADMITTED
 |
 v
ACTIVE
 |
 +----------------+
 |                |
 v                v
EVICTED         SUPERSEDED
 |                |
 +--------+-------+
          |
          v
       CANONICAL
```

這裡：

```text
EVICTED
```

只是 active-state transition。

不是 deletion。

---

# 39. Benchmark

MVP benchmark 至少包含：

## B1 Exact Restore

驗證：

$$
RF=1.
$$

## B2 Supersession

舊值不應進普通 active context。

## B3 Branch Isolation

不同 branch 不應無證據混入。

## B4 Cold Recall

長期不活躍但仍有效的 persistent memory 能重新取得。

## B5 Irrelevant Archive Growth

archive 增大時 active footprint 不應等比例增大。

## B6 Memory Storm

大量 ingest 時 backlog 可恢復。

## B7 Context Thrashing

邊界候選不應每輪 admit / evict。

## B8 False-Eviction Shadow Audit

估計被清掉的必要資訊比例。

---

# 40. Acceptance Metrics

核心：

$$
RF
=
\text{Restoration Fidelity}.
$$

$$
ACP
=
\text{Active Context Precision}.
$$

$$
ACR
=
\text{Active Context Recall}.
$$

$$
SAR
=
\text{Stale Activation Rate}.
$$

$$
BLR
=
\text{Branch Leakage Rate}.
$$

$$
CTR
=
\text{Context Thrashing Rate}.
$$

$$
FER_G
=
\text{False Eviction Rate}.
$$

$$
MB
=
\text{Maintenance Backlog}.
$$

$$
RLS
=
\text{Retrieval Latency Stability}.
$$

v0.1 最優先：

$$
RF=1
$$

對所有通過 canonical exact-expansion 測試的 fixture。

---

# 41. Reference Deployment Profile

```text
ACCR Runtime Core
    Python or Rust service

Cloud metadata
    PostgreSQL-compatible database

Canonical large objects
    S3-compatible object storage

Semantic index
    PostgreSQL vector extension or pluggable vector backend

Exact local/archive memory
    ANLA

Transport
    MCP 2026-07-28 compatible tool servers

Workers
    maintenance queue workers

Observability
    OpenTelemetry-compatible traces + metrics
```

此配置不是協議要求。

它只是 MVP 的低複雜度 reference profile。

---

# 42. 為什麼 MCP 不應持有 ACCR 核心狀態

MCP 2026-07-28 的核心 wire model 已轉向 stateless request/response，移除舊 initialize handshake 與 MCP session header，並讓 request 自帶 protocol/client capability metadata。

因此 ACCR state 應：

$$
\boxed{
\text{live in ACCR-managed storage and explicit handles}.
}
$$

而不是：

$$
\boxed{
\text{hide inside an MCP transport session}.
}
$$

這使 runtime 更容易：

- scale-out；
- resume；
- replay；
- audit；
- crash recovery。

---

# 43. 為什麼要分離 storage / retrieval / maintenance

近期 agent-memory systems research 已把 memory architecture 拆成 representation/storage、extraction、retrieval/routing 與 maintenance，並觀察到不同架構存在不同成本與品質 trade-off。

ACCR 因此拒絕：

```text
one database = entire memory theory
```

而採用：

$$
\boxed{
\text{canonical store}
+
\text{projection/index}
+
\text{governor}
+
\text{maintenance}.
}
$$

---

# 44. Security boundary

ACCR 至少必須處理：

- tenant / user scope；
- branch scope；
- agent scope；
- canonical access control；
- provenance；
- tool output trust class；
- prompt injection contamination；
- destructive deletion authorization。

MVP 中 permanent delete 預設禁用。

如果需要刪除：

```text
request_delete
 -> authorization
 -> retention policy
 -> tombstone
 -> background erase
 -> audit
```

不得由普通 Context Governor 直接完成。

---

# 45. Failure recovery

## Runtime crash

重新載入：

$$
context\_run\_id
$$

與最近 checkpoint。

## Projection corruption

從 canonical object 重建。

## Index loss

從 canonical metadata / archive 重建。

## Governor regression

rollback：

$$
\Gamma_{t+1}
\rightarrow
\Gamma_t.
$$

## ANLA replica unavailable

resolve alternative canonical replica。

## Cloud unavailable

允許 local degraded mode，但標記未同步 canonical events。

---

# 46. MVP 成功定義

ACCR v0.1 成功不等於：

> 它比所有 memory framework 都準。

成功定義是：

$$
\boxed{
\text{the lifecycle closes without destroying provenance or canonical recoverability}.
}
$$

具體而言：

1. 一段歷史能被 canonical ingest；
2. 可以離開 active context；
3. projection 仍能找到它；
4. governor 可以決定它是否適合現在；
5. exact source 可以重新展開；
6. 新版本可以 supersede 舊版本；
7. branch 可以隔離；
8. maintenance queue 可以清空；
9. 所有決策可以 audit；
10. context budget 可被穩定維持。

---

# 47. 後續版本

## v0.2

- learned shadow governor；
- calibration；
- counterfactual audit；
- version propagation；
- richer phase features。

## v0.3

- multi-Agent shared canonical domain；
- governor disagreement；
- adaptive maintenance scheduling；
- drift detection。

## v0.4

- automatic policy learning；
- dynamic fixed-point benchmark；
- long-horizon stability suite。

## v1.0

要求：

$$
\boxed{
\text{canonical correctness}
+
\text{stable context governance}
+
\text{measured long-horizon maintenance}.
}
$$

---

# 48. 結論

ACCR 的基本思想不是替 AI 製造一個更大的 prompt。

它是把：

$$
\boxed{
\text{現在}
}
$$

變成一個可被編譯、治理、重建與驗證的 runtime object。

完整歷史存在於：

$$
\mathcal D.
$$

低成本搜尋與編譯表示存在於：

$$
\mathcal P.
$$

真正進入推理的有限集合存在於：

$$
\mathcal W.
$$

治理器決定：

$$
\mathcal D
\rightarrow
\mathcal P
\rightarrow
\mathcal W
$$

的動態投影，而不是篡改：

$$
\mathcal D
$$

本身。

因此 ACCR 的最短定義為：

$$
\boxed{
\text{ACCR is a runtime that continuously compiles an unbounded history into a bounded, auditable, recoverable present.}
}
$$

或者：

$$
\boxed{
\text{ACCR does not compress memory into the prompt;}
}
$$

$$
\boxed{
\text{it compiles memory into the present.}
}
$$

---

# 參考資料

[1] Model Context Protocol Core Maintainers. *The 2026-07-28 Specification*. Model Context Protocol, 2026.

[2] Omri, Y., Gan, Z., Broveak, Z., et al. *Agent Memory: Characterization and System Implications of Stateful Long-Horizon Workloads*. arXiv:2606.06448, 2026.

[3] Zhou, W., Zhou, X., Han, S., et al. *Are We Ready For An Agent-Native Memory System?* arXiv:2606.24775, 2026.

[4] Alake, R., Bernardis, C., Cayet, P., et al. *Oracle Agent Memory as an Enterprise Memory Substrate for Long-Horizon AI Agents*. arXiv:2607.13157, 2026.

[5] EveMissLab. *TDCD Series I / Papers 01-05*. 2026.

[6] EveMissLab. *EveMissLab Phase Canon v1.2 - IPFC Integration Edition*. 2026.

---

# Canonical-source status

This Markdown file is the canonical UTF-8 source artifact for the ACCR Technical Whitepaper v0.1.

Mathematical source uses only `$...$` and `$$...$$`.

No Unicode escape-codec round-trip is used.

No conversion of LaTeX source into Unicode mathematical glyphs is intended.

The architecture is an engineering proposal. The reference deployment profile is not a requirement of TDCD or MCP.
