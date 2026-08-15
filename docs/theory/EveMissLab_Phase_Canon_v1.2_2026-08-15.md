# EveMissLab Phase Canon v1.2
## IPFC-Integrated Canon of Typed Phase Structures, Identity Roles, and Module Composition

**版本：** v1.2  
**日期：** 2026-08-15  
**狀態：** CURRENT CANON — supersedes v1.1  
**Audit basis：** 5 batches / 238 claim-level judgments  
**Canonical architecture：** Phase Canon v1.2 → IPFC Core Papers 01–05 → Phase Modules；GPC-CS / PCPRT 為主要 realized/safety branches；IPFC Paper 06 為 application track  
**核心規則：** `No type jump without a map.`

---

# v1.2 IPFC Integration Amendment

Phase Canon v1.2 為 **IPFC integration release**。它不撤銷 v1.1 的五批 audit，也不改寫既有 PH-0…PH-6 的 primary type taxonomy；它新增第二型別軸、identity/lineage 接口與 Phase Module governance，使未來「X 相位／相位 X」不再各自重造底層。

v1.2 的最高新增結構是：

$$
\boxed{
\mathrm{PhaseClaim}
=
(
PH\text{-}k,
IF\text{-}j,
\mathfrak M,
\mathsf E
).
}
$$

其中：

- $PH\text{-}k$：phase 是什麼結構型；
- $IF\text{-}j$：phase 相對 identity 扮演什麼角色；
- $\mathfrak M$：Phase Module；
- $\mathsf E$：evidence / validation status。

因此：

$$
\boxed{
PH\text{-type}
\neq
IF\text{-role}.
}
$$

同一 PH type 可在不同 identity criterion 下具有不同 IF role。

---

## v1.2-A1 — Identity Criterion

任何 IPFC / Phase Module claim 必先明示：

$$
\boxed{
\kappa
}
$$

表示 identity criterion。

它回答：

> 哪些 states 被視為同一個研究對象／載體／語義身份／系統？

沒有 $\kappa$ 時，不得無條件使用「same identity」「identity transition」「identity preservation」。

---

## v1.2-A2 — Identity Projection

定義：

$$
\boxed{
q_\kappa:
\mathcal X
\twoheadrightarrow
\mathcal O_\kappa.
}
$$

identity fiber：

$$
\boxed{
F_O^\kappa
=
q_\kappa^{-1}(O).
}
$$

它與 phase extractor：

$$
\Theta:
\mathcal X\times\mathcal C
\rightarrow
\Phi
$$

是兩個不同投影。

因此：

$$
\boxed{
\text{same identity}
\not\Rightarrow
\text{same phase},
}
$$

且：

$$
\boxed{
\text{same/similar phase}
\not\Rightarrow
\text{same identity}.
}
$$

---

## v1.2-A3 — IF-0…IF-4 Identity-Role Types

v1.2 新增與 PH-0…PH-6 **正交**的第二型別軸。

### IF-0 — Presentation / Gauge Role

phase/change 只作用於 presentation/index/gauge；resolved state 不變。

典型條件：

$$
\rho T^{\mathcal V}
=
\rho.
$$

### IF-1 — Intra-Identity State Role

state 真正改變，但 identity 保持：

$$
\boxed{
q_\kappa T(x)
=
q_\kappa(x).
}
$$

### IF-2 — Holonomic / Path Role

closed path 後 state/phase 不回原點，但 identity 保持：

$$
\boxed{
T_\gamma x\neq x,
\qquad
q_\kappa(T_\gamma x)=q_\kappa(x).
}
$$

### IF-3 — Inter-Identity Relational Role

phase 描述不同 identities / carriers / candidates 間的 relation：

$$
\boxed{
\Delta_\Phi
(
x_A,x_B
\mid
T,C
).
}
$$

### IF-4 — Identity-Lineage Transition Role

dynamics 跨 identity fiber：

$$
\boxed{
q_{\kappa'}\Gamma
=
Lq_\kappa
}
$$

或在 branching case 使用 relation / graph / stochastic kernel。

---

## v1.2-A4 — Double-Typing Rule

任何進入現行 Canon 的新 phase module，原則上應標：

$$
\boxed{
PH\text{-}k
\times
IF\text{-}j.
}
$$

若 IF role 與研究問題無關，可明示：

> `IF role not claimed / not analyzed`

而不是默認某個 identity 結論。

因此：

$$
\boxed{
\text{PH-5}
}
$$

只說「generalized relational phase」的結構型；

它不能單獨告訴我們該 relation 是：

- same-identity drift；
- holonomy；
- cross-identity alignment；
- identity split。

---

## v1.2-A5 — Identity-Preserving Dynamics

若：

$$
\boxed{
q_\kappa\Gamma
=
q_\kappa,
}
$$

則 dynamics 保持每個 identity fiber：

$$
\boxed{
\Gamma(F_O^\kappa)
\subseteq
F_O^\kappa.
}
$$

反之亦然。

這是 IPFC 的 **Fiber Invariance Theorem**，成為 v1.2 identity preservation 的 canonical test。

---

## v1.2-A6 — Lineage Factorization Gate

若 identity 可改變，不再用「phase drift」含糊處理。

對：

$$
\Gamma:
\mathcal X
\rightarrow
\mathcal X',
$$

deterministic lineage：

$$
L:
\mathcal O_\kappa
\rightarrow
\mathcal O_{\kappa'}
$$

存在且可下推，要求：

$$
\boxed{
q_\kappa(x_1)=q_\kappa(x_2)
\Rightarrow
q_{\kappa'}(\Gamma x_1)
=
q_{\kappa'}(\Gamma x_2).
}
$$

若此條件失敗，單值 lineage 不存在；改用：

- relation-valued lineage；
- branching lineage graph；
- stochastic kernel。

---

## v1.2-A7 — Holonomy Gate

v1.2 禁止把一般 endpoint difference 稱為 holonomy。

要使用：

$$
\operatorname{Hol}_\gamma
$$

至少需：

1. context/index/path space；
2. composable transport family：
   $$
   T_{\gamma_2\circ\gamma_1}
   =
   T_{\gamma_2}T_{\gamma_1};
   $$
3. closed path：
   $$
   \gamma:i_0\rightarrow\cdots\rightarrow i_0.
   $$

若聲稱 **same-identity holonomy**，另需：

$$
\boxed{
q_\kappa T_\gamma
=
q_\kappa.
}
$$

若 identity 改變，應進 IF-4 lineage，而不是 IF-2 holonomy。

---

## v1.2-A8 — Phase Module

現行通用 phase module：

$$
\boxed{
\mathfrak M
=
(
D,
\kappa,
\mathcal X,
\mathcal O,
q,
\mathcal C,
\tau,
\Phi,
\Theta,
\mathcal T,
\Gamma,
H,
L,
\Pi,
\mathsf A,
\mathsf G,
\mathsf R
).
}
$$

其中：

$$
\tau
=
(
PH,
IF
).
$$

v1.1 的 Realization Record：

$$
\mathfrak R
$$

不被撤銷；它現在成為 $\mathfrak M$ 中 physical realization / validation 的專門子紀錄。

---

## v1.2-A9 — Canon-Admissible Module

新的「X 相位／相位 X」若要進 current Canon，至少回答：

1. Domain $D$？
2. Identity criterion $\kappa$？
3. State space $\mathcal X$？
4. Identity projection $q$？
5. PH type？
6. IF role？
7. Phase space $\Phi$？
8. Extractor $\Theta$？
9. Dynamics / transport？
10. Observable / task $H$？
11. Identity transition 時 lineage？
12. Physical claim 時 realization $\Pi$？
13. Falsification $\mathsf R$？

只改名：

$$
x\mapsto\phi_x
$$

不構成新 phase mechanics。

---

## v1.2-A10 — Phase Module Morphism

兩 modules：

$$
\mathfrak M_A,
\qquad
\mathfrak M_B
$$

若要合法跨域搬運 claim，至少要求相應 diagrams 交換。

identity：

$$
\boxed{
q_BF_X
=
F_Oq_A.
}
$$

phase：

$$
\boxed{
\Theta_BF_X
=
F_\Phi\Theta_A.
}
$$

dynamics：

$$
\boxed{
F_X\Gamma_A
=
\Gamma_BF_X.
}
$$

observable：

$$
\boxed{
H_BF_X
=
F_YH_A.
}
$$

若聲稱 physical realization，再加 physical square。

因此：

$$
\boxed{
\text{similar notation}
\neq
\text{module morphism}.
}
$$

---

## v1.2-A11 — Defect Ledger

approximate module mapping 不得只寫「大致對齊」。

至少分列：

$$
\boxed{
\boldsymbol\varepsilon
=
(
\varepsilon_q,
\varepsilon_\Phi,
\varepsilon_\Gamma,
\varepsilon_H,
\varepsilon_L,
\varepsilon_\Pi
).
}
$$

在 Lipschitz 條件下，composition 需有 defect bound，例如：

$$
\boxed{
\varepsilon_q(G\circ F)
\le
\varepsilon_q(G)
+
\operatorname{Lip}(G_O)\varepsilon_q(F).
}
$$

---

## v1.2-A12 — Universal Fiber-Factorization Principle

v1.2 將多條既有定理統一為：

> **若某高層量要在 quotient / coarse-graining / observation / phase coordinate 上良定義，它必須在被壓掉的 fibers 上保持常數或具有相應 consistency。**

形式：

給：

$$
C:
\mathcal X
\twoheadrightarrow
\bar{\mathcal X},
$$

高層量：

$$
P:
\mathcal X
\rightarrow
\mathcal Y
$$

可寫成：

$$
P
=
\bar P C
$$

當且僅當：

$$
\boxed{
C(x_1)=C(x_2)
\Rightarrow
P(x_1)=P(x_2).
}
$$

此原理統一：

- PCPRT closure；
- phase factorization；
- identity lineage factorization；
- semantic identity recoverability；
- task sufficiency；
- identity observability；
- Phase Module quotient。

---

## v1.2-A13 — Contract / Replacement Rule

Phase Module 可以帶：

$$
\mathsf C_{\mathfrak M}
=
(
\mathsf A,
\mathsf G
).
$$

sequential composition 只有在 upstream guarantee 足以滿足 downstream assumption 時才可直接繼承 guarantee。

若上層 proof 依賴 identity preservation、zero holonomy、lineage correctness 或 realization margin，這些必須明寫於 guarantee，而不能只寫 output correctness。

---

## v1.2-A14 — Type-Elevation Gate v2

v1.1：

$$
\boxed{
\text{No type jump without a map.}
}
$$

在 v1.2 保持最高禁則，並升級為：

$$
\boxed{
\text{phase morphism}
\neq
\text{physical realization}.
}
$$

PH-5 / PH-6 若要升格 PH-0，仍需：

$$
\Pi,
\quad
\Phi_{\mathrm{phys}},
\quad
H,
\quad
\varepsilon_\Pi,
\quad
\text{falsification/evidence}.
$$

IPFC / PMC 的存在不降低 physical-elevation 門檻。

---

## v1.2-A15 — Continuity Is Evidence, Not Identity

對 AI / carrier / semantic lineage：

$$
\boxed{
\text{similarity}
\neq
\text{continuity}
\neq
\text{lineage}
\neq
\text{identity}.
}
$$

特別是 threshold relation：

$$
d(x,y)\le\varepsilon
$$

一般不具傳遞性，因此不得無條件作 identity equivalence。

---

## v1.2-A16 — Branching Identity Rule

真正 fork / split：

$$
O
\rightarrow
\{
O_1',O_2'
\}
$$

不得強迫寫成單值 lineage。

普通 numerical identity 若保有傳遞性，也不能同時把 distinct branches 都當成同一個 predecessor 的 numerical identity。

因此 branch / merge topology 應留在 lineage layer。

---

## v1.2-A17 — First-Person Non-Inference Boundary

IPFC 可以建立：

- operational identity；
- carrier identity；
- semantic identity；
- lineage；
- continuity evidence；
- provenance。

但這些不自動建立：

$$
\mathfrak F
=
\text{first-person persistence}.
$$

因此：

$$
\boxed{
q_\kappa,
\mathcal G_L,
E
\not\Rightarrow
\mathfrak F
}
$$

除非未來另有獨立 theory / observability bridge。

此規則只限制過度推論，不否定任何特定 personal-identity 哲學理論。

---

# v1.2 Canonical Publication Rules — Superseding Rule 1 and Extending Rules 2–5

## Rule 1 — Double type declaration

新 phase module 第一次出現「相位」時，標：

$$
\boxed{
PH\text{-}k
\times
IF\text{-}j
}
$$

或明示 IF role 不在 claim scope。

## Rule 2 — Identity declaration

若文件使用：

- same identity；
- identity-preserving；
- identity transition；
- lineage；

必給：

$$
\kappa,
\qquad
q_\kappa.
$$

## Rule 3 — Holonomy declaration

使用 holonomy 時必給：

$$
\mathcal C,
\quad
T_\gamma,
\quad
\gamma\text{ closed}.
$$

## Rule 4 — Physical elevation

沿用 v1.1，PH-5 / PH-6 升 PH-0 需 explicit realization record。

## Rule 5 — Module record

跨域 phase claim 優先附：

$$
\mathfrak M.
$$

## Rule 6 — Defect accounting

approximate mapping / realization / composition 必分列 relevant defects。

## Rule 7 — Lineage declaration

identity-changing dynamics 必給 functional / relational / stochastic lineage model。

## Rule 8 — Evidence and formalization status

至少分：

- definition；
- hand-proved theorem；
- machine-verified theorem；
- empirical result；
- effective model；
- benchmark proposal；
- engineering hypothesis；
- ontology/conjecture。

## Rule 9 — Falsification

每個強 claim 仍必寫 downgrade / refutation condition。

## Rule 10 — Provenance preservation

沿用 v1.1：retired / superseded claim 不刪除，但不得當 current Canon 引用。

---

# v1.2 Canonical Minimal Test Suite

對任一新 phase module，至少問：

### Test A — PH Type

它是 PH-0…PH-6 哪一型？

### Test B — Identity / IF Role

identity criterion 是什麼？IF-0…IF-4 哪一型？

### Test C — Fiber

被 quotient / coarse-grain / observe 掉的 fiber 是否藏有不同 target property？

### Test D — Closure

phase/state/identity-level dynamics 是否真正閉合？

### Test E — Transport / Holonomy

若使用 path language，transport 是否可組合？closed loop 是否真的存在？

### Test F — Observability

phase / identity / safety claim 是否可由 observation map 判定？

### Test G — Necessity / Ablation

移除 phase mechanics 後 prediction / control / explanation 是否真的變差？

### Test H — Specificity

效果是否其實由 amplitude、rate、common drive、material state、task stage 或 hidden variable 解釋？

### Test I — Lineage

identity 變化是否具有合法 functional / relational / stochastic lineage？

### Test J — Realization

physical claim 是否有 $\Pi$、physical dynamics 與 realization defect？

### Test K — Composition

跨 module claim 是否有 morphism / contract / defect ledger？

### Test L — Falsification

什麼結果會讓 claim 降級、改型或撤回？

---

# v1.2 Canonical Research Architecture

現行總結構更新為：

$$
\boxed{
\text{Phase Canon}
\supset
\text{IPFC Core}
\supset
\text{Phase Modules}.
}
$$

其中：

### Phase Canon

治理：

- PH types；
- evidence；
- realization；
- type jumps；
- publication rules。

### IPFC Core Papers 01–05

治理：

- identity fiber；
- PH × IF；
- semantic/domain phase；
- transition / lineage；
- carrier identity safety；
- Phase Module Calculus。

### IPFC Paper 06 and later applications

屬 application track。

它們可以新增 domain results / benchmarks / governance schemas，但不自動改動 Core definitions。

---

# v1.2 Updated Open Problems

## O1 — A∩B Welding Theorem

保留。

## O2 — Phase Coherence Persistent Homology

保留。

## O3 — Generalized-Phase Geometry

由單純「找一個 metric」升級為：

> 針對不同 PH-5 / PH-6 modules，何時存在 task-invariant metric、connection、transport 或 manifold structure？

## O4 — Cross-Substrate Benchmark

保留，並要求以 Phase Module / Defect Ledger 格式報告。

## O5 — IPFC / PMC Machine Formalization

形式化：

- Fiber Invariance；
- Lineage Factorization；
- Phase Module Morphism；
- Module Quotient；
- Approximate Composition；
- Fork No-Go。

## O6 — Semantic Holonomy Benchmark

translation / multi-agent / ontology round-trip 是否存在可重現 nonzero loop residual？

## O7 — Carrier Identity Benchmark

semantic success、functional success、carrier identity preservation 是否實際可分離？

## O8 — Identity Lineage Benchmark

fork / restore / merge / progressive replacement 的 criterion-relative lineage record。

## O9 — Neural–Semantic Module Bridge

是否能建立：

$$
\mathfrak M_{\mathrm{neural}}
\rightarrow
\mathfrak M_{\mathrm{semantic}}
$$

而不把 neural phase 直接等同 meaning？

## O10 — Contracted Phase Modules

研究 assume–guarantee / open-system composition 如何完整納入 identity、lineage、phase defects 與 physical realization。

---

# v1.2 Closure Amendment

v1.1 的：

$$
\text{Phase}
=
\text{typed structure}
+
\text{relation}
+
\text{dynamics}
+
\text{realization}
+
\text{evidence boundary}
$$

仍有效，但 v1.2 的現行最高形式擴張為：

$$
\boxed{
\text{Phase Canon v1.2}
=
\text{Typed Phase}
+
\text{Identity Role}
+
\text{Fiber / Factorization}
+
\text{Dynamics / Transport}
+
\text{Lineage}
+
\text{Realization}
+
\text{Module Composition}
+
\text{Evidence / Falsification}.
}
$$

最重要的三條禁則：

$$
\boxed{
\text{No type jump without a map.}
}
$$

$$
\boxed{
\text{No holonomy without transport.}
}
$$

$$
\boxed{
\text{No identity transition without an explicit identity criterion and lineage model.}
}
$$

中文：

> **沒有映射，不得跳型；沒有傳輸，不得談 Holonomy；沒有身份準則與譜系，不得把狀態變化直接叫身份轉換。**

---

# v1.1 Audit Amendment

Phase Canon v1.1 保留 v1.0 的 PH-0…PH-6 分型、realization map、fiber principle、phase fate、GPC / PCPRT bridge。

五批 audit 新增以下 mandatory constraints。

## A1 — Renaming Rule

$$
\boxed{
\text{renaming a state as phase does not create phase mechanics}.
}
$$

## A2 — Algorithmic Phase Necessity Rule

對 PH-5 / PH-6：

$$
\boxed{
\Delta S_\phi
=
S(M_\phi)-S(M_{\mathrm{typed}}).
}
$$

若：

$$
\Delta S_\phi\approx0,
$$

phase 可保留作 nomenclature，但不得宣稱為必要 computational primitive。

## A3 — Frequency-Coincidence Guard

$$
\boxed{
f_A\approx f_B
\not\Rightarrow
A\leftrightarrow B.
}
$$

## A4 — Biological Evidence Ladder

$$
\boxed{
B0\ \text{periodicity}
\not\Rightarrow
B1\ \text{oscillator phase}
\not\Rightarrow
B2\ \text{functional coupling}
\not\Rightarrow
B3\ \text{clinical relevance}.
}
$$

## A5 — Medical Boundary

$$
\boxed{
\text{biological phase}
\neq
\text{medical efficacy}.
}
$$

## A6 — Engineering Phase Boundary

$$
\boxed{
\text{switching / resonance / PLL phase}
\neq
\text{quantum phase}.
}
$$

## A7 — Grounding Rule

$$
\boxed{
\text{semantic alignment}
\neq
\text{grounded validity}.
}
$$

## A8 — Language Qualification Rule

$$
\boxed{
\text{high-dimensional representation}
\not\Rightarrow
\text{language}.
}
$$

## A9 — Topology Boundary

$$
\boxed{
\text{persistent topology}
=
\text{stable informative descriptor}
\neq
\text{complete identity invariant}.
}
$$

topology → phase 的 canonical bridge 優先採：

$$
H^1_{\mathrm{persistent}}
\rightarrow
S^1.
$$

## A10 — Provenance Rule

$$
\boxed{
\text{retired claim}
\neq
\text{deleted historical source}.
}
$$

---

# Audit Statistics

總計：

$$
\boxed{238}
$$

claim-level judgments。

| Canonical category | Count |
|---|---:|
| KEEP | 80 |
| REPAIR / REFRAME | 29 |
| CONJECTURE / BENCHMARK | 33 |
| RETIRE | 91 |
| HISTORICAL / OPEN | 5 |

---

# Canonical Evidence Status

## C0 — HISTORICAL

歷史來源／哲學 provenance。

## C1 — CONJECTURE

已明確定義，但尚缺驗證。

## C2 — RESEARCH-READY

具有 well-defined objects、measurable/computable observables 與 falsification condition。

## C3 — EFFECTIVE-VALIDATED

在指定 domain / task / dataset 上經 benchmark 或實驗支持。

## C4 — CAUSAL / REALIZED

具有 causal intervention 或 explicit physical realization：

$$
\Pi\Phi_{\mathrm{phys}}
\approx
\Gamma\Pi.
$$

## C5 — CANONICAL

表示：在現行 Phase Canon 中可作為其他文件的預設上游結構，且適用域與 evidence boundary 已明示。

---

# Canonical Research Stacks After Audit

1. Physical Phase Realization
2. Phase-Coherence TDA
3. Weighted Infinite Oscillators
4. Persistent-Cohomology Circular Coordinates
5. Typed Relational Difference
6. GPC Cross-Carrier Safety
7. GIPSS Open-World Discovery
8. GIPE Active Epistemic Control
9. Cross-Carrier Semantic Transduction
10. Biological Oscillator / Entrainment Science
11. Multiscale Physiological Monitoring
12. Classical Power-Phase Engineering

---

# v1.1 Closure Statement

EveMissLab 相位體系在 audit 後的最高正典不再是：

$$
\boxed{
\text{萬物都是相位}.
}
$$

也不是：

$$
\boxed{
\text{相位只是比喻}.
}
$$

而是：

$$
\boxed{
\text{Phase}
=
\text{typed structure}
+
\text{relation}
+
\text{dynamics}
+
\text{realization}
+
\text{evidence boundary}.
}
$$

---

# Inherited v1.0 Canon

以下為 v1.0 canonical body，除與上述 v1.1 Amendment 衝突處外全部繼承。

---


# 0. Canonical Statement

EveMissLab 對「相位」的現行最高層敘述是：

$$
\boxed{
\text{Phase is a privileged cross-domain structural language of cyclicity, relation, alignment, regime, transition, routing, and multiscale realization.}
}
$$

中文：

> **相位之所以具有核心地位，不是因為所有存在都已被證明是同一種相位實體，而是因為相位型結構反覆出現在週期、差分、同步、相界、拓樸、路由、轉導、記憶與跨尺度有效關係中。**

本 Canon 不接受下列無條件等式：

$$
\boxed{
\text{physical phase}
=
\text{semantic phase}
=
\text{material phase}
=
\text{algorithmic phase}.
}
$$

也不接受：

$$
\boxed{
\text{同名 phase}
\Rightarrow
\text{同一數學物件}
\Rightarrow
\text{同一物理實體}.
}
$$

---

# 1. Canon Scope

本 Canon 解決六件事：

1. 「相位」在不同文件中究竟是哪一種數學結構；
2. 什麼時候可以跨領域搬運 phase；
3. 什麼時候 generalized phase 可以聲稱有 physical realization；
4. 什麼時候 physical phase 在 coarse-graining 後被保留、關係化、潛伏或消去；
5. 舊相位本體論與現行 GPC-CS／PCPRT 的版本關係；
6. 新論文、實驗與工程文件應如何命名、引用與反證。

---

# 2. Canonical Phase Types

## PH-0 — Physical Oscillator Phase

若 physical system 存在合法 oscillatory structure，可定義：

$$
\boxed{
\Theta:
\mathcal Z
\rightarrow
S^1.
}
$$

典型：

- limit-cycle phase；
- wave phase；
- optical phase；
- Josephson phase；
- quantum relative/geometric phase（需依具體結構定義）。

PH-0 的核心問題是：

$$
\boxed{
\text{phase coordinate 是否由真實 physical dynamics 支持？}
}
$$

---

## PH-1 — Relative / Coherence Phase

由 PH-0 形成：

$$
\boxed{
\Delta\theta_{ij}
=
\theta_j-\theta_i
}
$$

或：

$$
\boxed{
re^{i\psi}
=
\frac1N
\sum_j
e^{i\theta_j}.
}
$$

典型用途：

- synchronization；
- interference；
- coherence；
- phase locking；
- collective order parameter；
- routing gain。

PH-1 比絕對 phase 更常直接進入 observable relation。

---

## PH-2 — Regime / Material Phase

此處「phase」不是圓上的角度，而是：

$$
\boxed{
\text{state/parameter space region}
}
$$

由：

- order parameter；
- symmetry；
- topology；
- bifurcation；
- material structure；

分類。

典型：

- thermodynamic phase；
- magnetic phase；
- superconducting phase；
- topological phase；
- amorphous / crystalline material phase。

PH-2 不得與 PH-0 混用。

---

## PH-3 — Carrier Phase State

若 phase-only 不足，載體狀態擴張：

$$
\boxed{
q
=
(
\theta,
a,
\lambda,
\mu
).
}
$$

其中：

- $\theta$：phase；
- $a$：amplitude / transverse state；
- $\lambda$：coupling / carrier parameters；
- $\mu$：plasticity-rule / metaplastic state。

PH-3 表示：

> phase 是 carrier state 的一部分，而不是整個 carrier。

---

## PH-4 — Neural / Artificial Functional Phase

PH-4 是 phase 在功能層的角色，而不是新的微觀 phase 種類。

神經系統可寫：

$$
\boxed{
\mathcal P_{\mathrm{neural}}
=
(
P_{\mathrm{gate}},
P_{\mathrm{route}},
P_{\mathrm{code}},
P_{\mathrm{plastic}}
).
}
$$

人工系統可寫：

$$
\boxed{
\mathcal P_{\mathrm{art}}
=
(
P_{\mathrm{time}},
P_{\mathrm{state}},
P_{\mathrm{route}},
P_{\mathrm{plastic}}
).
}
$$

PH-4 的關鍵是：

$$
\boxed{
\text{phase 有什麼可觀測功能？}
}
$$

---

## PH-5 — Generalized Relational Phase

這是 GPC／語義／跨載體／認知對齊中使用的高層 phase。

它可以是：

- task-relative relation；
- state alignment；
- reconstruction relation；
- semantic compatibility；
- carrier receptivity；
- multidimensional typed difference。

PH-5 不要求：

$$
\theta\in S^1.
$$

因此：

$$
\boxed{
\text{PH-5}
\not\Rightarrow
\text{PH-0}.
}
$$

---

## PH-6 — Epistemic / Search Phase

用於 GIPE / GIPSS 等認識論與搜尋方法論。

其 phase 是：

$$
\boxed{
\Phi_{\mathrm{task}}
(
x;
\mathcal W
)
}
$$

型類型化判定向量。

例如：

- 數學：命題強度、證明深度、反例距離；
- 材料：結構、穩定性、成本、製程；
- 科學：證據、模型誤差、可觀測性。

PH-6 是方法論座標，不是 physical oscillator。

---

# 3. Canonical Exclusions

## 3.1 Linear Process Stage

例如：

- clinical Phase I / II / III；
- project phase；
- compilation phase；
- training phase / inference phase。

若只是：

$$
\boxed{
\text{poset / irreversible process stage},
}
$$

不進本 Canon 核心 phase ontology。

---

## 3.2 Phase Space

phase space：

$$
\boxed{
\Gamma_{\mathrm{state}}
}
$$

是 dynamical state manifold / position-momentum space。

它不是：

$$
\boxed{
\theta\in S^1.
}
$$

---

## 3.3 Phase-Change Material

amorphous / crystalline：

$$
\boxed{
\text{material phase}
}
$$

屬 PH-2。

不等於 oscillator phase。

---

# 4. Canonical Realization Map

所有高層相位 physical claim 的第一個方程是：

$$
\boxed{
x
=
\Pi(z).
}
$$

其中：

$$
z
\in
\mathcal Z_{\mathrm{phys}},
\qquad
x
\in
\mathcal X_{\mathrm{eff}}.
$$

physical dynamics：

$$
\boxed{
z^+
=
\Phi_{\mathrm{phys}}(z).
}
$$

effective dynamics：

$$
\boxed{
x^+
=
\Gamma(x).
}
$$

realization criterion：

$$
\boxed{
\Pi
\circ
\Phi_{\mathrm{phys}}
\approx
\Gamma
\circ
\Pi.
}
$$

realization defect：

$$
\boxed{
\varepsilon_{\Pi,\Gamma}(z)
=
d
\left(
\Pi\Phi_{\mathrm{phys}}(z),
\Gamma\Pi(z)
\right).
}
$$

---

# 5. Canonical Fiber Principle

若兩個 lower-level states：

$$
z_1,z_2
$$

被 coarse-grain 成：

$$
\Pi(z_1)
=
\Pi(z_2)
=
x,
$$

但 target property：

$$
P(z_1)
\neq
P(z_2),
$$

則：

$$
\boxed{
x
\text{ 對 }P\text{ 不充分}.
}
$$

因此：

$$
\boxed{
P
=
\widetilde P
\circ
\Pi
}
$$

只有在 $P$ 對每個 $\Pi$-fiber 為常數時才可能成立。

這是本 Canon 的 universal audit tool。

---

# 6. Canonical Phase-Only Closure Rule

受輸入 $u$ 的 physical dynamics：

$$
\dot z
=
F_u(z).
$$

physical phase：

$$
\theta
=
\Theta(z).
$$

phase velocity：

$$
\boxed{
v_\Theta(z,u)
=
D\Theta(z)F_u(z).
}
$$

若存在：

$$
\Theta(z_1)=\Theta(z_2)
$$

但：

$$
v_\Theta(z_1,u)
\neq
v_\Theta(z_2,u),
$$

則精確：

$$
\boxed{
\dot\theta
=
f(\theta,u)
}
$$

不存在。

因此 phase-only model 必須通過 phase-fiber closure。

---

# 7. Canonical Phase Fate

physical phase 在向上 coarse-grain 時只有五種 canonical fate：

## F0 — Preserved

$$
\boxed{
\Theta
=
\theta_{\mathrm{eff}}
\circ
\Pi.
}
$$

## F1 — Relationalized

只保留：

$$
\Delta\theta,
\quad
r,
\quad
\psi.
$$

## F2 — Latent

phase 仍影響 effective dynamics，但沒有顯式進入上層 state。

## F3 — Eliminated

phase-blind closure 對 target task 成立。

## F4 — Replaced

上層重新建立 generalized phase：

$$
\varphi_{\mathrm{GPC}},
$$

但：

$$
\varphi_{\mathrm{GPC}}
\neq
\Theta
$$

一般成立。

---

# 8. Canonical Carrier Principle

communication / interaction 的終點不是單純 decoding。

現行 GPC carrier equation：

$$
\boxed{
x_B'
=
F_B
\left(
x_B,
D_B
\left(
T_{A\to B}
(
E_A(x_A)
),
x_B
\right)
\right).
}
$$

真正問題是：

$$
\boxed{
x_B
\rightarrow
x_B'.
}
$$

因此 Canon 保留：

> **交流是一個 carrier-state transformation problem。**

---

# 9. Canonical Plastic Carrier

interaction 可以改：

$$
z,
\lambda,
\mu.
$$

最小：

$$
\boxed{
\dot z
=
F(z;\lambda,u),
}
$$

$$
\boxed{
\dot\lambda
=
\varepsilon_\lambda
G(z,\lambda,u;\mu),
}
$$

$$
\boxed{
\dot\mu
=
\varepsilon_\mu
M(z,\lambda,\mu,u).
}
$$

所以：

$$
\boxed{
\text{same present state}
\not\Rightarrow
\text{same future response law}.
}
$$

---

# 10. Canonical Dynamical Safety

static safe set：

$$
\mathcal S
$$

對動態生物／人工載體往往不足。

Canon 使用：

$$
\boxed{
\mathfrak R_{\mathrm{adm}}
=
(
\mathfrak A_{\mathrm{adm}},
\mathfrak M_{\mathrm{adm}},
E_{\mathrm{adm}},
\Lambda_{\mathrm{adm}}
).
}
$$

安全的現行定義是：

> trajectory 保持於允許的 attractor / metastable regime / transition graph / parameter region，且具有足夠的 resilience margin。

---

# 11. Canonical Neural Rule

神經 phase 可以扮演：

- gating；
- routing；
- coding；
- plasticity。

但：

$$
\boxed{
\theta_{\mathrm{neural}}
\neq
\text{semantic meaning}.
}
$$

更合理：

$$
\boxed{
\text{neural phase}
\rightarrow
\text{excitability / gain}
\rightarrow
\text{routing of meaning-bearing activity}.
}
$$

任何「phase = thought / meaning」強等式都不是 Canon。

---

# 12. Canonical Artificial-Phase Rule

人工系統分：

$$
\boxed{
\text{physical phase present}
}
$$

$$
\boxed{
\text{computationally relevant}
}
$$

$$
\boxed{
\text{semantically exposed}.
}
$$

三者不同。

普通 clocked digital AI：

$$
\boxed{
\text{physically instantiated}
\not\Rightarrow
\text{phase-native}.
}
$$

oscillator Ising / coherent photonic / ONN 等才可能真正把 phase 作 computational state。

---

# 13. Canonical Substrate Independence

substrate：

$$
s
\in
\mathfrak S
$$

各自有：

$$
\Pi_s:
\mathcal Z_s
\rightarrow
\mathcal X.
$$

若：

$$
\boxed{
\Pi_s
\circ
\Phi_s
=
\Gamma
\circ
\Pi_s
\qquad
\forall s\in\mathfrak S,
}
$$

才稱 $\Gamma$ 在該 substrate family 上具有 exact substrate-independent realization。

所以：

$$
\boxed{
\text{same effective dynamics}
\not\Rightarrow
\text{same microscopic physics}.
}
$$

---

# 14. Canonical Two-Branch Architecture

不可再用：

$$
\text{Physics}
\rightarrow
\text{Biology}
\rightarrow
\text{Cognition}
\rightarrow
\text{Computation}
$$

這種單線。

Canonical architecture：

$$
\boxed{
\text{Physics}
\rightarrow
\text{Biophysics}
\rightarrow
\text{Neural Dynamics}
\rightarrow
\text{Cognition}
\rightarrow
\text{GPC}
}
$$

與：

$$
\boxed{
\text{Physics}
\rightarrow
\text{Device Physics}
\rightarrow
\text{Computation}
\rightarrow
\text{GPC}.
}
$$

GPC 是高層匯合語言，不是 microscopic common substance。

---

# 15. Canonical Scale-Stopping Principle

給定 target property：

$$
P.
$$

若下一層 coarse map：

$$
\Pi
$$

仍允許：

$$
P
=
P'\circ\Pi,
$$

可以繼續 coarse-grain。

若無法 factor：

$$
\boxed{
P
\neq
P'\circ\Pi,
}
$$

則：

$$
\boxed{
\text{next scale is too coarse for this question}.
}
$$

研究尺度的目標不是「最微觀」或「最宏觀」，

而是：

$$
\boxed{
\text{minimum complexity subject to dynamical closure and property preservation}.
}
$$

---

# 16. Canonical Status of Historical Theories

## 16.1 保留但降格為歷史強猜想

包括：

- 《相位場本體論》
- 《h-相位元本體論》
- 《相位編織論》中強物理本體段落

Canon 不刪除它們。

它們屬：

$$
\boxed{
\text{provenance / hypothesis history}.
}
$$

但不直接作為：

$$
\boxed{
\text{verified physical conclusion}.
}
$$

---

## 16.2 重構保留

包括：

- C₀-相位統一論
- 相位時間
- 歷史認知符號相位場
- CCTC
- 全域相位化世界模型

核心結構可保留，

但要重新標：

- PH type；
- realization status；
- evidence level；
- effective vs physical claim。

---

## 16.3 現行 Canonical Successors

### GPC-CS

負責：

$$
\boxed{
\text{generalized carrier-state safety and interaction}.
}
$$

### PCPRT

負責：

$$
\boxed{
\text{physical realization and multiscale grounding}.
}
$$

兩者共同取代「單一終極相位本體論」作為現行總主幹。

---

# 17. Canonical Publication Rules

所有新的相位文件：

## Rule 1 — Type declaration

第一次使用「相位」時標：

$$
PH\!-\!0
\ldots
PH\!-\!6.
$$

## Rule 2 — Physical-elevation rule

若 PH-5 / PH-6 要聲稱 PH-0 realization，

必給：

$$
\Pi,
\quad
\Theta,
\quad
H,
\quad
\varepsilon,
\quad
\text{experimental evidence}.
$$

## Rule 3 — Scope

每個 theorem / experiment 明示：

- state domain；
- timescale；
- substrate；
- observable；
- assumptions。

## Rule 4 — Evidence label

至少區分：

- theorem；
- empirical result；
- effective model；
- engineering hypothesis；
- ontology/conjecture。

## Rule 5 — Falsification

每個強 claim 必寫：

$$
\boxed{
\text{what observation would make us retract or downgrade it?}
}
$$

---

# 18. Canonical Realization Record

任何「X 實現 Y 相位理論」的正式主張，建議附：

$$
\boxed{
\mathfrak R
=
(
S,
\mathcal Z,
\Pi,
\mathcal X,
\Phi,
\Gamma,
H,
K,
T,
\varepsilon,
P
).
}
$$

其中：

- $S$：substrate；
- $\mathcal Z$：lower-level state；
- $\Pi$：realization map；
- $\mathcal X$：effective state；
- $\Phi$：lower-level dynamics；
- $\Gamma$：effective dynamics；
- $H$：observation map；
- $K$：valid state domain；
- $T$：validity horizon；
- $\varepsilon$：realization defect；
- $P$：preserved properties。

---

# 19. Canonical Minimal Test Suite

對任一新 phase theory，至少問：

### Test A — Type

它是 PH-0…PH-6 哪一型？

### Test B — Fiber

同一 coarse state 是否藏有不同 target future / property？

### Test C — Closure

phase-only / state-only model 是否真正閉合？

### Test D — Observability

所聲稱的 phase 能不能被量測或可靠估計？

### Test E — Necessity

移除 phase 後 prediction / control / explanation 是否真的變差？

### Test F — Specificity

效果是否其實由 amplitude、rate、common drive、material state 或 task stage 解釋？

### Test G — Realization

generalized phase 是否有明確 physical realization map？

### Test H — Falsification

什麼結果會讓 claim 降級？

---

# 20. Canonical Open Problems

## O1 — A∩B 焊接定理

形式化：

$$
\boxed{
\text{order-parameter phase}
\rightarrow
\text{regime / topological classification}
}
$$

的最一般條件。

## O2 — Phase Coherence Persistent Homology

定義哪些 phase-coherence structures 具有真正穩定拓樸不變量。

## O3 — Generalized-Phase Metric

PH-5 / PH-6 的 phase difference：

$$
\Delta\Phi
$$

需要 typed metric / manifold，而不能永遠停在語義直覺。

## O4 — Cross-Substrate Benchmark

以：

- oscillator hardware；
- neural public data；
- simulated coupled systems；

測：

$$
\Pi\Phi
\approx
\Gamma\Pi.
$$

## O5 — Canonical Ontology Audit

逐篇重審 G1 強本體論：

- 哪些只是哲學假說；
- 哪些可重述成 effective theory；
- 哪些與已知 physics 衝突；
- 哪些可以形成可證偽新猜想。

---

# 21. Canonical References / External Anchors

本 Canon 的外部物理錨點包括：

1. Wilson & Moehlis, *Isostable reduction of periodic orbits*, Physical Review E 94, 052213 (2016).
2. Kurebayashi et al., *Phase reduction of strongly coupled limit-cycle oscillators*, Physical Review Research 4, 043176 (2022).
3. Wilson, *The renormalization group: Critical phenomena and the Kondo problem*, Reviews of Modern Physics 47, 773 (1975).
4. Simon, *Holonomy, the Quantum Adiabatic Theorem, and Berry's Phase*, Physical Review Letters 51, 2167 (1983).
5. Drebitz, Rausch & Kreiter, *Gamma-band synchronization between neurons in the visual cortex is causal for effective information processing and behavior*, Nature Communications 16, 7380 (2025).
6. Kragel et al., *Closed-loop control of theta oscillations enhances human hippocampal network connectivity*, Nature Communications 16, 4061 (2025).

這些文獻不是「證明 EveMissLab Phase Canon」。

它們只是對 Canon 中以下邊界提供外部錨點：

- phase reduction 有適用域；
- phase-only 可能不足；
- holonomy 是合法 physical/geometric phase 結構；
- universality 需要明確 coarse-graining；
- neural phase 可以具有局部 causal functional role；
- local evidence 不等於 semantic/ontological universality。

---

# 22. Final Canon — v1.2 Superseding Closure

相位體系的現行最高收斂式：

$$
\boxed{
\text{Phase Canon v1.2}
=
\text{Typed Phase Structures}
+
\text{Identity Roles}
+
\text{Fiber / Factorization Tests}
+
\text{Dynamics / Transport}
+
\text{Lineage}
+
\text{Realization Maps}
+
\text{Module Morphisms / Contracts}
+
\text{Defect Ledgers}
+
\text{Evidence / Falsification}.
}
$$

現行最高治理禁則：

$$
\boxed{
\text{No type jump without a map.}
}
$$

$$
\boxed{
\text{No holonomy without transport.}
}
$$

$$
\boxed{
\text{No identity transition without a criterion and lineage model.}
}
$$

中文：

> **沒有映射，不得跳型；沒有傳輸，不得談 Holonomy；沒有身份準則與譜系，不得把狀態變化直接叫身份轉換。**

沒有：

$$
\Pi
$$

就不能把 generalized phase 稱成 physical phase。

沒有 fiber constancy / consistency：

$$
C(x_1)=C(x_2)
\Rightarrow
P(x_1)=P(x_2),
$$

就不能說 quotient / coarse-graining / observation 保留了 $P$。

沒有：

$$
q_\kappa,
$$

就不能無條件宣稱 same identity / identity preservation。

沒有：

$$
T_\gamma
$$

與 closed path，就不能叫 holonomy。

沒有合法 module morphism / contract / defect ledger，就不能把跨領域相似直接當成可組合理論。

因此 EveMissLab 相位體系目前不以：

$$
\boxed{
\text{「萬物都是相位」}
}
$$

作最高正典，也不以：

$$
\boxed{
\text{「所有 X 相位都共享同一數學物件」}
}
$$

作預設。

現行最高正典是：

$$
\boxed{
\text{「相位是一組必須分型、相對身份定位、可映射、可組合、可驗證、可反證的跨域結構語言。」}
}
$$

---

## v1.2 Additional External Anchors

v1.2 新增的外部結構性錨點包括：

1. Brendan Fong, *Decorated Cospans* (2015)：open systems 的 compositional categorical language。
2. Baez, Courser & Vasilakopoulou, *Structured versus Decorated Cospans* (2022)：structured/decorated cospan 的比較與 double-category 結構。
3. assume–guarantee contract literature：component assumptions / guarantees / refinement / composition 的模組化驗證傳統。
4. Barry Simon (1983) 與 Wilczek–Zee (1984)：holonomy / geometric phase / non-Abelian transport 的成熟物理數學先例。

這些文獻不證明 IPFC/PMC；它們只界定：

- compositionality；
- contract reasoning；
- holonomy；

在既有數學／工程中的合法結構鄰域。

---

**Phase Canon v1.2 — CURRENT CANON.**
**IPFC INTEGRATION — COMPLETE.**
