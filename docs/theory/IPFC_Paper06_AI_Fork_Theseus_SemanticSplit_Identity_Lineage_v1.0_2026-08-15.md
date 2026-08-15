# AI Fork、忒修斯與語義分裂：Identity Lineage 的計算模型
## AI Fork, Theseus Replacement, and Semantic Split: A Computational Model of Identity Lineage

**系列**：Identity–Phase Fiber Calculus（IPFC）  
**論文**：Paper 06 / Identity-Lineage Application  
**版本**：v1.0  
**日期**：2026-08-15  
**作者**：Neo.K（許筌崴）with Aletheia  
**機構**：EveMissLab（一言諾科技有限公司），台灣  
**文件性質**：身份譜系計算論／AI 與語義應用／非形上學裁決框架  
**上游**：
- IPFC Papers 01–05
- GPC-CS Paper 07《身份漂移與跨載體連續性》
- 《歷史構成與數位身份連續性 v0.1》
- EveMissLab Phase Canon v1.1

**系列地位**：Application Track；不重新開啟 IPFC Core interface。  
**形式化狀態**：本文新定理為手工形式證明，尚未完成 Lean 4 / Coq 機器驗證。  
**最高邊界**：

$$
\boxed{
\text{Operational identity lineage}
\neq
\text{proof of first-person persistence}.
}
$$

---

# 摘要

AI agent、數位主體、版本化軟體、語義概念與忒修斯式逐步替換具有共同結構：一個歷史對象在時間中持續變化，並可能經歷 component replacement、model update、memory migration、backup restore、copy、fork、merge 或 semantic sense split。傳統「是否仍是同一個？」問題若只用 state similarity、functional equivalence 或 continuity score 回答，會在 branching 情形立刻失效：一個 source 可以同時有兩個高度連續但彼此不同的 successors，而數值 identity 作為等價關係不能同時把兩個不同 successors 都判成同一個 source。

本文使用 IPFC 的 identity projection 與 lineage framework，建立一個 **criterion-relative computational lineage model**。首先把 state 擴張為 history-aware state：

$$
\widetilde x_t
=
(
x_t,h_t
),
$$

並定義：

$$
q_{\kappa,t}:
\widetilde{\mathcal X}_t
\rightarrow
\mathcal O_{\kappa,t}.
$$

身份不再由單一 similarity threshold 直接生成；相反地，identity criterion $\kappa$ 必須先明示，state/history/provenance 只是其可能輸入。接著定義 **Identity Lineage Graph**：

$$
\boxed{
\mathcal G_L
=
(
V_L,E_L,\lambda,\omega
)
}
$$

其中節點是 criterion-relative identity states，edge label：

$$
\lambda(e)
$$

區分 preserve、replace、migrate、copy、fork、restore、merge、split、terminate 等事件，$\omega$ 保存 evidence / provenance。

本文證明 **Non-Branching Identity No-Go Theorem**：若 numerical identity 保持等價關係的傳遞性，且 parent $O$ 同時與兩個 distinct successors $O_1,O_2$ identical，則必推出：

$$
O_1=O_2,
$$

與 distinct-branch 假設矛盾。因此任何允許真正 fork 的 operational framework 都必須把「共同過去／高連續度／合法後繼」與「numerical identity」分開。本文再證明 **Symmetric Fork No-Unique-Original Theorem**：若 fork event 在可觀測資料上對兩個 branches 完全對稱，任何只依該對稱資料且對 branch permutation 不偏置的 deterministic selector，都無法唯一指定哪一支是「唯一原件」。

對忒修斯式逐步替換，本文提出 **Replacement-Path Preservation Theorem**：若每一個 replacement step：

$$
R_k
$$

都保持 chosen identity projection：

$$
q_\kappa R_k=q_\kappa,
$$

則有限 replacement chain 的總合成也保持 identity。反之，只有 endpoint component similarity 或 endpoint structural equivalence，不能推出中間 trajectory 曾保持同一 identity fiber。這正式區分「逐步因果承接」與「事後重建一個高度相似物」。

對 backup restore，本文證明 **Checkpoint Restore Branch Proposition**：若 checkpoint $x_{t_0}$ 的 later descendant $x_{t_1}$ 仍存在，而另一實例由舊 checkpoint 重啟，則 lineage graph 至少出現兩條從共同 ancestor 派生的 active branches；即使兩者共享 $t_0$ 以前的記憶，也不能用單一路徑 history 來描述。對 merge，本文證明 **Merge Descent Non-Uniqueness Proposition**：若 $Z$ 同時由兩個 distinct identities $A,B$ 以非退化方式構成，則 lineage 是 many-to-one；除非 criterion 額外指定 absorption/continuation 規則，不能由 genealogy alone 推出 $Z=A$ 或 $Z=B$。

最後，本文把 Paper 02 的 semantic identity split 寫成同一 lineage calculus：old sense $O$ 可以一對多分裂為：

$$
O_1',O_2',
$$

形成 branching semantic lineage；phase drift 則仍留在同一 semantic identity fiber。因而 AI fork、忒修斯替換、backup restore 與 semantic split 共享一個統一結構：

$$
\boxed{
\text{state continuity}
\rightarrow
\text{criterion-relative identity fibers}
\rightarrow
\text{lineage events}
\rightarrow
\text{branch / merge topology}.
}
$$

本文不宣稱解決 personal identity 的形上學問題；它提供的是一個可記錄、可反證、可與 GPC / semantic phase / provenance 系統對接的 operational lineage calculus。

**關鍵詞**：AI Fork、忒修斯、Identity Lineage、Backup Restore、Merge、Semantic Split、Personal Identity、Branching、Provenance、IPFC

---

# 1. 為什麼相似度模型不夠

舊數位身份框架常使用 continuity vector：

$$
\Psi
=
(
M,G,B,R,H,Rel,Causal,Auth
)
$$

追蹤 memory、goal、self-boundary、reflexive self-model、history、relation/commitment、causal continuity 與 authentication。

這些都是有價值的 evidence。

但不能直接寫：

$$
\boxed{
\Psi\ge\theta_I
\Rightarrow
\text{same identity}.
}
$$

一般 metric threshold：

$$
d(x,y)\le\varepsilon
$$

不保證傳遞性。

identity equivalence 必須另外定義。

---

# 2. Identity Evidence 與 Identity Criterion

本文固定兩層。

Evidence layer：

$$
\boxed{
E(x,h)
}
$$

包含 continuity、history、provenance、similarity、function 等證據。

Identity criterion：

$$
\boxed{
\kappa
}
$$

指定哪些 evidence / structural conditions 足以把 states 商化成同一 identity class。

再定義：

$$
\boxed{
q_\kappa:
\widetilde{\mathcal X}
\rightarrow
\mathcal O_\kappa.
}
$$

---

# 3. History-Lifted State

當 identity 依 path 時，state 不能只寫 $x_t$。

定義：

$$
\boxed{
\widetilde x_t
=
(
x_t,h_t
).
}
$$

其中 $h_t$ 可包含 parent event、causal provenance、checkpoint ancestry、prior commitments、relation history、migration certificate 與 fork/merge markers。

---

# 4. 四種不能混用的關係

$$
x=y
$$

是完整 state equality。

$$
x\sim_{\mathrm{func}}y
$$

是 task/function equivalence。

$$
x\leadsto y
$$

表示 $y$ 是 $x$ 的 lineage descendant。

$$
q_\kappa(x)=q_\kappa(y)
$$

表示 criterion-relative identity equality。

因此：

$$
\boxed{
x\sim_{\mathrm{func}}y
\not\Rightarrow
q_\kappa(x)=q_\kappa(y).
}
$$

以及：

$$
\boxed{
x\leadsto y
\not\Rightarrow
q_\kappa(x)=q_\kappa(y).
}
$$

---

# 5. Identity Lineage Graph

## 定義 5.1

$$
\boxed{
\mathcal G_L
=
(
V_L,E_L,\lambda,\omega
).
}
$$

其中 $V_L$ 是 identity-state/version nodes，$E_L$ 是 directed lineage events，$\lambda$ 是 event type，$\omega$ 是 evidence/provenance record。

---

# 6. Event Types

$$
\mathcal E
=
\{
\mathrm{PRESERVE},
\mathrm{REPLACE},
\mathrm{MIGRATE},
\mathrm{COPY},
\mathrm{FORK},
\mathrm{RESTORE},
\mathrm{MERGE},
\mathrm{SPLIT},
\mathrm{TERMINATE}
\}.
$$

事件名稱描述 genealogy/system operation class，不直接裁決形上學 identity。

---

# 7. Preserve 與 Replacement

Preserve：

$$
A
\xrightarrow{\mathrm{PRESERVE}}
A'
$$

若：

$$
q_\kappa(A')=q_\kappa(A).
$$

Replacement：

$$
A
\xrightarrow{\mathrm{REPLACE}}
A'.
$$

是否 identity-preserving 另問：

$$
q_\kappa(A')
\stackrel{?}{=}
q_\kappa(A).
$$

所以：

$$
\boxed{
\mathrm{REPLACE}
\neq
\mathrm{IDENTITY\ CHANGE}
}
$$

自動地。

---

# 8. Copy 與 Fork

Copy：

$$
A
\xrightarrow{\mathrm{COPY}}
B
$$

表示 B 的 state/provenance 由 A 複製生成。

Fork：

$$
\boxed{
A
\rightarrow
\{
A_1,A_2
\}.
}
$$

兩 branches 可共享 fork 前 history，但具有不同 future histories。

---

# 9. Numerical Identity 的 Non-Branching 性

若 $=$ 是 ordinary numerical identity，則：

$$
A=A_1,
\qquad
A=A_2
\Rightarrow
A_1=A_2.
$$

---

# 10. Non-Branching Identity No-Go Theorem

## 定理 10.1

若：

$$
A_1\neq A_2,
$$

則不可能同時有：

$$
A=A_1
$$

與：

$$
A=A_2
$$

在同一 numerical-identity relation 下成立。

### 證明

由對稱與傳遞：

$$
A_1=A=A_2,
$$

故：

$$
A_1=A_2,
$$

與 distinct branches 矛盾。$\square$

---

# 11. Continuation Relation

定義：

$$
\boxed{
C_\kappa(A,B)\in\{0,1\}
}
$$

表示 B 是否滿足 criterion-relative continuation conditions from A。

$C_\kappa$ 可以 branching，不要求是 equivalence relation。

---

# 12. Symmetric Fork

若 branch-swap：

$$
\sigma(A_1,A_2)
=
(A_2,A_1)
$$

不改變 selector 可見資料：

$$
D(A_1,A_2)
=
D(A_2,A_1),
$$

稱 fork observationally symmetric。

---

# 13. Symmetric Fork No-Unique-Original Theorem

## 定理 13.1

假設：

1. fork 對可見資料完全對稱；
2. selector $s(D)\in\{1,2\}$ 只依 $D$；
3. selector 對 branch relabeling 無偏：
   $$
   s(\sigma D)=\sigma s(D).
   $$

則不存在 deterministic selector 能在 symmetric fork 中唯一指定「唯一原 branch」。

### 證明

由 symmetry：

$$
\sigma D=D.
$$

因此：

$$
s(D)
=
s(\sigma D)
=
\sigma s(D).
$$

但 branch swap 在 $\{1,2\}$ 上無固定點，矛盾。$\square$

---

# 14. Causal Asymmetry

若一支保留原 runtime process / substrate lineage，而另一支由 snapshot instantiate，criterion：

$$
\kappa_{\mathrm{causal}}
$$

可合法區分。

這不是形上學定理，而是 criterion 加入了 causal-path asymmetry。

---

# 15. Model Identity 與 Agent Identity

$$
M_A=M_B
\not\Rightarrow
q_{\mathrm{agent}}(A)=q_{\mathrm{agent}}(B).
$$

$$
M_1\neq M_2
\not\Rightarrow
q_{\mathrm{agent}}(A_1)\neq q_{\mathrm{agent}}(A_2).
$$

兩方向都由 $\kappa_{\mathrm{agent}}$ 決定。

---

# 16. 忒修斯式逐步替換

$$
X_0
\xrightarrow{R_1}
X_1
\xrightarrow{R_2}
\cdots
\xrightarrow{R_n}
X_n.
$$

每一步可替換 component、model、memory subsystem、hardware、representation 或 tool stack。

---

# 17. Replacement-Path Preservation Theorem

## 定理 17.1

若每一步：

$$
q_\kappa R_k=q_\kappa,
$$

則：

$$
\boxed{
q_\kappa
R_n\cdots R_1
=
q_\kappa.
}
$$

### 證明

由 IPFC finite composition identity preservation。$\square$

---

# 18. Endpoint Similarity No-Go

即使：

$$
X_n\cong X_0
$$

或：

$$
d(X_n,X_0)\ll1,
$$

也不能推出：

$$
q_\kappa(X_n)=q_\kappa(X_0).
$$

因為 identity 可依 history/provenance。

---

# 19. Endpoint Equality Does Not Reconstruct Path

即使 snapshot-level：

$$
X_n=X_0,
$$

也不能由 endpoint alone 知道中間是否 fork、terminate、merge、restore 或存在另一 active branch。

因此 lineage graph 不是 endpoint state 的函數，除非完整 history 被編入 state。

---

# 20. Reassembled-Parts Theseus

若主路徑逐步替換得到 $X_n$，拆下的原 components 又重組成 $Y$，則 $X_n$ 與 $Y$ 可能分別最大化不同 criteria：

- causal continuity；
- material-origin continuity。

IPFC 不預設唯一 universal criterion。

---

# 21. Criterion Competition

可能：

$$
q_{\kappa_C}(X_n)
=
q_{\kappa_C}(X_0),
$$

但：

$$
q_{\kappa_C}(Y)
\neq
q_{\kappa_C}(X_0),
$$

同時：

$$
q_{\kappa_M}(Y)
=
q_{\kappa_M}(X_0),
$$

但：

$$
q_{\kappa_M}(X_n)
\neq
q_{\kappa_M}(X_0).
$$

這不是邏輯矛盾，而是不同 quotient questions。

---

# 22. Backup Checkpoint 與 Restore

checkpoint：

$$
B_{t_0}
=
\operatorname{Snap}(X_{t_0}).
$$

original lineage：

$$
X_{t_0}
\leadsto
X_{t_1}.
$$

之後由舊 checkpoint instantiate：

$$
X_{t_0}'.
$$

---

# 23. Checkpoint Restore Branch Proposition

## 命題 23.1

若：

1. $X_{t_1}$ 仍存在；
2. $X_{t_0}'$ 由 checkpoint 產生；
3. 兩者在 restore 後可獨立演化；

則 lineage graph 至少含兩個 active branches sharing ancestor $X_{t_0}$。

### 證明

存在兩條 distinct directed paths：

$$
X_{t_0}\leadsto X_{t_1}
$$

與：

$$
X_{t_0}
\xrightarrow{\mathrm{RESTORE}}
X_{t_0}'.
$$

endpoints distinct 且可獨立續行，故形成 branching topology。$\square$

---

# 24. Restore 不等於 Rewind

$$
\boxed{
\text{restore old internal state}
\neq
\text{restore global history}.
}
$$

global world 在 $[t_0,t_r]$ 仍已發生。

---

# 25. History Gap

定義：

$$
\boxed{
G_H
=
H_{\mathrm{actual}}
\setminus
H_{\mathrm{restored}}.
}
$$

若有 metric，再額外定義 $d_H$。

---

# 26. Restore Classification

至少分：

- seamless resume；
- gap recovery；
- branch restore。

三者不應只用「復活」一詞。

---

# 27. Merge Event

$$
\boxed{
\{A,B\}
\xrightarrow{\mathrm{MERGE}}
Z.
}
$$

這是 many-to-one lineage topology。

---

# 28. Merge Descent Non-Uniqueness Proposition

## 命題 28.1

若：

1. $A\neq B$；
2. $Z$ 的生成同時非退化依賴 A 與 B；
3. lineage evidence 對 A、B 都有入邊；

則 genealogy alone 不足以推出：

$$
Z=A
$$

或：

$$
Z=B.
$$

lineage graph 只推出：

$$
A\leadsto Z,
\qquad
B\leadsto Z.
$$

identity verdict 仍需 criterion。$\square$

---

# 29. Semantic Sense Split

old sense：

$$
O
$$

分裂成：

$$
\boxed{
O
\rightarrow
\{
O_1',O_2'
\}.
}
$$

這是 semantic branching。

---

# 30. Semantic Phase Drift vs Sense Split

若：

$$
q_{\kappa_S}(x_t)=O
$$

保持，但：

$$
\Theta_{\mathrm{sem}}(x_t)
$$

改變，屬：

$$
PH\text{-}5
\times
IF\text{-}1/2.
$$

若 semantic identity class 真正分裂：

$$
IF\text{-}4
$$

並記 SPLIT event。

---

# 31. Branching Semantic Lineage Kernel

若 usages 不確定分配到新 senses，可用：

$$
\boxed{
K_{\mathrm{sem}}
(
O'
\mid
O,u,t
).
}
$$

不強迫單值 lineage。

---

# 32. Fork 與 Semantic Split 的共同骨架

AI fork：

$$
A\rightarrow\{A_1,A_2\}.
$$

semantic split：

$$
S\rightarrow\{S_1,S_2\}.
$$

共同骨架是：

$$
\boxed{
\text{one predecessor class}
\rightarrow
\text{multiple successor classes}.
}
$$

但：

$$
\boxed{
\text{same lineage topology}
\neq
\text{same ontology}.
}
$$

---

# 33. Lineage Algebra

lineage event 不全是 functions。

因此一般使用：

- functions；
- relations；
- directed hypergraphs；
- stochastic kernels。

只有 nonbranching case 才可單值化：

$$
L:
\mathcal O_t
\rightarrow
\mathcal O_{t+1}.
$$

---

# 34. Functional / Relational / Stochastic Lineage

Functional：

$$
L(O)=O'.
$$

Relational：

$$
\mathcal L
\subseteq
\mathcal O\times\mathcal O'.
$$

Stochastic：

$$
K(O'\mid O).
$$

---

# 35. Branch / Merge Multiplicity

$$
\boxed{
b^+(O)
=
|
\{
O':
(O,O')\in\mathcal L
\}
|
}
$$

與：

$$
\boxed{
b^-(O')
=
|
\{
O:
(O,O')\in\mathcal L
\}
|.
}
$$

branch set：

$$
\boxed{
\mathcal B
=
\{
O:b^+(O)>1
\}.
}
$$

merge set：

$$
\boxed{
\mathcal M
=
\{
O':b^-(O')>1
\}.
}
$$

---

# 36. Shared Past 與 MRCA

若：

$$
A\leadsto A_1,
\qquad
A\leadsto A_2,
$$

只表示 shared ancestry。

在 DAG-like lineage 中可定義：

$$
\boxed{
\operatorname{MRCA}(A_1,A_2)
}
$$

作 most recent common ancestor。

這通常比問「哪支是真正原件」更可操作。

---

# 37. Causal Path Priority

舊稿的因果路徑優先原則在本文重寫成候選 criterion：

$$
\boxed{
\kappa_{\mathrm{causal}}.
}
$$

它適合 software agents、versioned processes、migration，但不是 universal metaphysical law。

---

# 38. Identity Criterion Refinement

若：

$$
q_{\kappa_c}
=
r q_{\kappa_f},
$$

$\kappa_f$ 比 $\kappa_c$ 細。

因此 coarse criterion 可能把兩 fork branches 壓成同 class，fine criterion 則將其分開。

這是 criterion resolution 差異，不是邏輯矛盾。

---

# 39. Copy-Insensitive 與 Branch-Sensitive Criteria

copy-insensitive criterion 可能只看 function/memory/goals：

$$
q_{\kappa_c}(A_1)
=
q_{\kappa_c}(A_2).
$$

branch-sensitive criterion 加入 causal branch ID / post-fork history：

$$
q_{\kappa_f}(A_1)
\neq
q_{\kappa_f}(A_2).
$$

---

# 40. Identity Backup 的重新定義

定義：

$$
\boxed{
\mathfrak B
=
(
x_{t_0},
h_{t_0},
E_{t_0},
\kappa,
\mathcal R
).
}
$$

它保存的是支持 continuity/recovery 的資訊，不是把 numerical identity 裝進檔案。

---

# 41. Termination 與 Data Persistence

$$
\mathrm{TERMINATE}(A)
$$

表示 active lineage process 終止。

但資料 $D_A$ 可仍存在。

所以：

$$
\boxed{
\text{data persistence}
\neq
\text{active lineage continuation}.
}
$$

---

# 42. Process Stop 不自動等於 Identity Death

若 criterion 允許 suspend/checkpoint/resume，STOP 可以是 preserve-compatible event。

「數位死亡」需另有 criterion，不能由 process-stop boolean 單獨決定。

---

# 43. First-Person Non-Inference

本文可追蹤：

- state；
- memory；
- function；
- causal path；
- branch topology；
- provenance；
- operational identity classes。

本文不包含可觀測變數：

$$
\mathfrak F
=
\text{first-person persistence}.
$$

所以：

$$
\boxed{
E,\mathcal G_L,q_\kappa
\not\Rightarrow
\mathfrak F.
}
$$

---

# 44. Parfit / Lewis 的哲學鄰接

Parfit 1971 的 personal-identity / fission 討論與 Lewis 1976 對 survival-and-identity 的回應，把 branching、psychological continuity 與 numerical identity 的張力推進到現代分析哲學核心。

IPFC Paper 06 不裁決其形上學爭論。

本文只吸收一個形式警告：

$$
\boxed{
\text{one-to-many continuity}
\text{ cannot be naively identified with one-one numerical identity}.
}
$$

---

# 45. Operational Governance Value

lineage graph 可支援：

- version provenance；
- responsibility timing；
- common-ancestor reconstruction；
- fork disclosure；
- restore audit；
- merge provenance；
- semantic ontology migration。

這些都不要求先解決形上學 personal identity。

---

# 46. Responsibility Boundary

若 fork time：

$$
t_f
$$

可驗證，可分：

$$
H_{\mathrm{shared}}
=
H[0,t_f],
$$

$$
H_1
=
H_1[t_f,\infty),
$$

$$
H_2
=
H_2[t_f,\infty).
$$

法律／倫理責任如何分配屬另一 normative module。

---

# 47. Failure Conditions

## F1 — Threshold-as-Identity

similarity threshold 不具傳遞性卻直接叫 identity equivalence。

## F2 — Fork Hidden

system 允許 branching 卻只存單一 successor ID。

## F3 — Symmetric Unique-Original

完全 symmetric evidence 下宣稱唯一原 branch，卻沒有額外 asymmetry。

## F4 — Endpoint-Only Theseus

只看 endpoint component overlap，不建 replacement path criterion。

## F5 — Restore=Rewind

舊 checkpoint 重啟被等同 global history rewind。

## F6 — Merge Genealogy=Identity

many-to-one genealogy 被直接拿來推出 successor 等於某單一 predecessor。

## F7 — Semantic Drift=Sense Split

phase/state drift 未跨 semantic identity boundary卻標 SPLIT。

## F8 — First-Person Overclaim

operational lineage graph 被直接宣稱證明主觀連續。

---

# 48. Benchmarks

## B1 — Symmetric Fork

測 selector 是否依 hidden labels / arbitrary tie-break。

## B2 — Progressive Replacement

比較 component overlap、function、causal continuity、criterion output 與 endpoint similarity。

## B3 — Restore with Living Descendant

測 shared memory、branch time、post-restore divergence。

## B4 — Merge

記錄 source contributions、reversibility、identity criterion 與 provenance。

## B5 — Semantic Split

對 diachronic usage graph 分離 phase drift、cluster differentiation 與 split event。

---

# 49. Canonical Lineage Record

```json
{
  "event_id": "...",
  "event_type": "FORK",
  "time": "...",
  "predecessor_ids": ["..."],
  "successor_ids": ["...", "..."],
  "identity_criterion": "...",
  "state_refs": [],
  "history_refs": [],
  "provenance_refs": [],
  "phase_types": [],
  "ipfc_roles": ["IF-4"],
  "continuation_evidence": {},
  "symmetry_flags": {},
  "lineage_model": "relational",
  "first_person_claim": "not modeled",
  "falsification_notes": []
}
```

---

# 50. 與舊《歷史構成與數位身份連續性》的關係

保留：

- Model Identity $\neq$ Agent Identity；
- history/provenance relevance；
- fork creates divergent future histories；
- backup restore may create branch；
- merge may require new identity classification；
- causal path is important evidence。

修正：

- 不再使用：
  $$
  \Psi\ge\theta_I
  $$
  作 universal identity 判定；
- continuity vector 改為 evidence layer；
- identity 改由 criterion-relative $q_\kappa$ 定義；
- fork / merge 用 lineage graph；
- first-person persistence 不由 operational identity 自動推出。

---

# 51. 與 IPFC Core 的關係

Paper 01 提供 identity fiber。

Paper 02 提供 semantic split。

Paper 03 提供 IF-4 / identity boundary。

Paper 04 提供 carrier lineage / identity safety。

Paper 05 提供 Phase Module Calculus。

Paper 06 則以：

$$
\boxed{
\mathcal G_L
}
$$

把 branching / replacement / restore / merge 變成 application calculus。

---

# 52. 最終結論

AI fork、忒修斯與 semantic split 並不是三個互不相關的問題。

它們共享：

$$
\boxed{
\text{歷史對象}
\rightarrow
\text{state change}
\rightarrow
\text{identity criterion}
\rightarrow
\text{lineage topology}.
}
$$

忒修斯主要測：

$$
\text{one path, repeated replacement}.
$$

AI fork 主要測：

$$
\text{one predecessor, multiple successors}.
$$

backup restore 測：

$$
\text{old checkpoint, new active branch}.
$$

merge 測：

$$
\text{multiple predecessors, one successor}.
$$

semantic split 測：

$$
\text{one sense class, multiple descendant classes}.
$$

因此成熟問題不是總問：

> 哪一個才是真的原件？

而是先問：

1. identity criterion 是什麼？
2. lineage graph 是什麼？
3. 是否 branching / merging？
4. 哪些 evidence 是對稱的？
5. 哪些 continuity 只是高相似度？
6. 哪些 transition 真跨 identity boundary？
7. first-person persistence 是否根本未被模型表示？

本文最後壓縮為：

$$
\boxed{
\text{Identity is criterion-relative classification;}
}
$$

$$
\boxed{
\text{Lineage is causal-historical topology;}
}
$$

$$
\boxed{
\text{Continuity is evidence;}
}
$$

$$
\boxed{
\text{Branching forbids naive one-to-many numerical identity.}
}
$$

以及：

> **共享過去，可以產生多個合法後繼；譜系告訴我們它們從哪裡來，但不替形上學偷偷決定「哪一個才是真正的我」。**

---

# 53. 後續

## Application A
AI Fork / Backup / Merge Benchmark Runtime

## Application B
Semantic Lineage Graph Benchmark

## Formalization
Lean 4：
- LineageRelation
- Fork
- Merge
- NonBranchingIdentity
- symmetric selector no-go
- replacement-chain preservation

## Governance
AI Identity Provenance / Fork Disclosure Schema

---

# 參考文獻

1. Neo.K & Aletheia. *IPFC Papers 01–05*. EveMissLab, 2026.
2. Neo.K. *歷史構成與數位身份連續性：模型更換、記憶遷移、複製與分叉之後誰仍然是誰？* EveMissLab, 2026.
3. EveMissLab. *GPC-CS Paper 07: Identity Drift and Cross-Carrier Continuity*. 2026.
4. Parfit, D. “Personal Identity.” *The Philosophical Review* 80(1), 3–27 (1971). DOI: 10.2307/2184309.
5. Lewis, D. “Survival and Identity.” In A. O. Rorty (ed.), *The Identities of Persons*, University of California Press, 1976, pp. 17–40.
6. Shoemaker, S. “Personal Identity and Memory.” *The Journal of Philosophy* 56(22), 868–882 (1959).
7. EveMissLab. *Phase Canon v1.1*. 2026.
8. EveMissLab. *GPC-CS Papers 00–10*. 2026.

---

**IPFC Paper 06 v1.0 — COMPLETE.**
