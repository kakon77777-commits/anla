# 同一性–相位纖維微積分：從身份投影、索引 Holonomy 到相位動力學的統一接口
## Identity–Phase Fiber Calculus: A Unified Interface from Identity Projection and Index Holonomy to Phase Dynamics

**系列**：Identity–Phase Fiber Calculus（IPFC）  
**論文**：Paper 01 / Foundation Paper  
**版本**：v1.0  
**日期**：2026-08-15  
**作者**：Neo.K（許筌崴）with Aletheia  
**機構**：EveMissLab（一言諾科技有限公司），台灣  
**文件性質**：數學框架／橋接母論文／研究級形式化草案  
**上游**：
- EML-TC-ONT-2026-v0.2《同一性微積分：拓樸微積分的本體論基礎》
- EML-TC-COMP-2026-v0.2《參照語義微積分：拓樸微積分的計算機實現》
- EML-TC-IDXGEO-2026-v0.1《索引幾何學》
- EveMissLab Phase Canon v1.1
- GPC-CS Papers 00–10
- PCPRT Papers 01–08

**形式化狀態**：本文中的新 IPFC 定義與定理尚未完成 Lean 4 形式化。本文僅繼承上游《同一性微積分 v0.2》已報告完成之核心 Lean 4 驗證結果；不得將上游驗證狀態誤標為本文已驗證。

---

# 摘要

同一性微積分與 EveMissLab 相位理論原本處理兩類不同但高度相鄰的問題。前者將「切割」重定義為對同一本體對象生成索引視圖，並以身份積分遺忘索引，因此在其抽象域中具有：

$$
\int_H\circ d_I
=
\operatorname{id}.
$$

後者經 Phase Canon v1.1 正典化後，將 phase 分成 PH-0 至 PH-6，要求 phase claim 必須分型、可映射、可驗證、可反證，並以：

$$
\text{No type jump without a map}
$$

作最高禁則。兩套理論若直接以「同一性 = 相位」合併，會同時破壞同一性微積分的身份不變性與 Phase Canon 的型別紀律；若完全分離，則又無法處理一個普遍問題：**同一個載體、概念或對象在保持身份時，phase、regime、relation、context 或路徑如何變化；反之，何時這些變化已跨出原身份纖維，必須視為 identity-lineage transition？**

本文提出 **同一性–相位纖維微積分**（Identity–Phase Fiber Calculus, IPFC）作為兩者的統一接口。核心結構由三個映射組成：

$$
\mathcal Z_{\mathrm{phys}}
\xrightarrow{\Pi}
\mathcal X
\xrightarrow{q_\kappa}
\mathcal O_\kappa,
$$

以及：

$$
\Theta:
\mathcal X\times\mathcal C
\rightarrow
\Phi.
$$

其中 $\mathcal X$ 為真正發生動力學的 effective/carrier state space；$q_\kappa$ 是依 identity criterion $\kappa$ 定義的身份投影；其 fiber：

$$
F_O^\kappa
=
q_\kappa^{-1}(O)
$$

收集所有仍被判定為同一身份 $O$ 的 states；$\Theta$ 則抽取 typed phase。因而：

$$
\boxed{
\text{Identity defines the fiber; phase describes position, relation, and transport over or between fibers.}
}
$$

本文證明身份保持動力學與 fiber invariance 等價，並建立 **Lineage Factorization Theorem**：對 state dynamics $\Gamma$，存在下推 identity-lineage map $L$ 使：

$$
q_{\kappa'}\Gamma
=
Lq_\kappa
$$

當且僅當 $q_{\kappa'}\Gamma$ 在每個 $q_\kappa$-fiber 上為常數；若 $q_\kappa$ 滿射，$L$ 唯一。本文再引入 index/context transport、phase transport、transport defect 與 identity-preserving holonomy，說明標準 $U(1)$ geometric phase 是此架構的一個嚴格特例，而 generalized semantic/cognitive/AI phase 僅在另行提供合法 phase space、transport 與 observable 時才可使用 holonomy 語言。

最後，本文提出與 Phase Canon PH-0 至 PH-6 正交的第二型別軸 IF-0 至 IF-4，用以區分 presentation/gauge phase、intra-identity state phase、holonomic/path phase、inter-identity relational phase 與 identity-lineage transition phase。此雙分型：

$$
PH\text{-}k
\times
IF\text{-}j
$$

與 Phase Attachment Contract 共同形成未來「相位語義、認知相位、時間相位、工程相位、XX 相位」接入 EveMissLab 相位體系的通用協議。

**關鍵詞**：同一性微積分、相位理論、纖維、身份投影、Holonomy、幾何相位、Lineage、語義相位、GPC、PCPRT、索引幾何、Phase Canon

---

# 1. 問題：同一性與相位不能被直接等同

## 1.1 兩套理論的問題型不同

同一性微積分問：

> 對象經索引、投影、視角、查詢或呈現變換後，什麼仍被判定為同一個對象？

Phase Canon 問：

> 一個 phase claim 究竟是 physical oscillator phase、relative phase、regime phase、carrier phase、functional phase、generalized relational phase 還是 epistemic/search phase？

兩個問題彼此相鄰，但不相同。

如果直接寫：

$$
\boxed{
\text{Identity}
=
\text{Phase},
}
$$

立即產生反例。

同一 oscillator：

$$
O
$$

可在：

$$
\theta_1
\neq
\theta_2
$$

時仍是同一 oscillator。

同一語義概念：

$$
O_{\mathrm{sem}}
$$

可在不同 context 下具有不同 relational semantic phase。

反之，兩個不同 identities 也可以 phase-aligned：

$$
\Theta(x_A)
\approx
\Theta(x_B),
$$

但：

$$
q(x_A)
\neq
q(x_B).
$$

因此：

$$
\boxed{
\text{same identity}
\not\Rightarrow
\text{same phase},
}
$$

以及：

$$
\boxed{
\text{same or similar phase}
\not\Rightarrow
\text{same identity}.
}
$$

---

## 1.2 本文的核心分工

本文採用：

$$
\boxed{
\text{Identity defines admissible sameness;}
}
$$

$$
\boxed{
\text{Phase describes typed position, relation, regime, or transport;}
}
$$

$$
\boxed{
\text{Lineage describes identity change.}
}
$$

這三者構成 IPFC 的最小語法。

---

# 2. 上游：同一性微積分的身份不變性

## 2.1 索引型微分

給定本體對象 $O$ 與索引方案 $I$，上游同一性微積分定義：

$$
d_I(O)
=
\{
(O,i)
:
i\in I
\}.
$$

微分不產生 $O$ 的本體部分，而產生同一 $O$ 的索引視圖。

---

## 2.2 身份積分

身份積分遺忘索引：

$$
\int_H(O,i)
=
O.
$$

因此：

$$
\boxed{
\int_H\circ d_I
=
\operatorname{id}_O.
}
$$

這不是標準微積分的積分，而是 identity/reference calculus 中的 forgetting / resolution operator。

---

## 2.3 反向不對稱

一般：

$$
d_I\circ\int_H
\neq
\operatorname{id}
$$

於原視圖歷史。

原因是：

$$
\int_H
$$

保留 identity，遺忘 index history。

這個不對稱正是 IPFC 引入 holonomy 與 lineage 的入口：**身份可以返回，而路徑／呈現／phase history 可以不返回。**

---

# 3. 三層空間與四個基本映射

## 定義 3.1 — Identity Criterion

identity criterion：

$$
\kappa
$$

是一個明示的 operational / mathematical rule，用來決定哪些 states 被視為同一 identity。

本文不假定所有 domain 存在唯一、絕對的形上學 identity criterion。

例如：

- immutable object identity；
- specimen identity；
- carrier identity；
- semantic sense identity；
- task-relative functional identity；
- versioned entity identity。

---

## 定義 3.2 — Identity Projection

給定 state space：

$$
\mathcal X,
$$

與 identity space：

$$
\mathcal O_\kappa,
$$

定義滿射：

$$
\boxed{
q_\kappa:
\mathcal X
\twoheadrightarrow
\mathcal O_\kappa.
}
$$

$q_\kappa(x)$ 表示依 criterion $\kappa$，state $x$ 被歸入哪個 identity class。

---

## 定義 3.3 — Identity Fiber

對：

$$
O
\in
\mathcal O_\kappa,
$$

定義：

$$
\boxed{
F_O^\kappa
=
q_\kappa^{-1}(O).
}
$$

本文將 $F_O^\kappa$ 稱為 identity fiber。

此處「fiber」只使用一般映射原像意義。

只有當：

$$
q_\kappa:
\mathcal X
\rightarrow
\mathcal O_\kappa
$$

另具局部平凡化等標準條件時，才可進一步稱為 fiber bundle。

---

## 定義 3.4 — Phase Extractor

令：

$$
\mathcal C
$$

為 context / reference / task / receiver condition space。

定義：

$$
\boxed{
\Theta:
\mathcal X
\times
\mathcal C
\rightarrow
\Phi,
}
$$

其中 $\Phi$ 為 typed phase space。

$\Phi$ 可以是：

- $S^1$；
- $U(1)$；
- Lie group / homogeneous space；
- order-parameter space；
- product manifold；
- graph relation space；
- typed discrepancy space。

不能僅因符號寫成 $\phi$ 就稱其為 phase。

---

## 定義 3.5 — Physical Realization Map

若存在 physical state space：

$$
\mathcal Z_{\mathrm{phys}},
$$

則 PCPRT realization map：

$$
\boxed{
\Pi:
\mathcal Z_{\mathrm{phys}}
\rightarrow
\mathcal X.
}
$$

負責把 physical substrate 映到 effective/carrier state。

---

# 4. IPFC 的母圖

完整最小圖：

$$
\boxed{
\begin{array}{ccccc}
\mathcal Z_{\mathrm{phys}}
&
\xrightarrow{\Pi}
&
\mathcal X
&
\xrightarrow{\Theta}
&
\Phi
\\
&&
\downarrow q_\kappa
&&
\\
&&
\mathcal O_\kappa
&&
\end{array}
}
$$

三個映射回答不同問題：

$$
\Pi:
\quad
\text{what physical state realizes }x?
$$

$$
q_\kappa:
\quad
\text{which identity is }x?
$$

$$
\Theta:
\quad
\text{which phase/relation/regime is }x\text{ in?}
$$

因此：

$$
\boxed{
\Pi
\neq
q_\kappa
\neq
\Theta.
}
$$

---

# 5. 呈現層與 Identity–State Square

令：

$$
\mathcal V
$$

為 view / presentation space。

定義：

$$
\rho:
\mathcal V
\rightarrow
\mathcal X
$$

把 view 解析成有效 state。

身份錨：

$$
h:
\mathcal V
\rightarrow
\mathcal O_\kappa.
$$

要求：

$$
\boxed{
q_\kappa\circ\rho
=
h.
}
$$

得到交換圖：

$$
\boxed{
\begin{array}{ccc}
\mathcal V
&
\xrightarrow{\rho}
&
\mathcal X
\\
\downarrow h
&&
\downarrow q_\kappa
\\
\mathcal O_\kappa
&
=
&
\mathcal O_\kappa.
\end{array}
}
$$

這保證：

> view 宣稱指向的 identity，與 view 解析成 state 後由 identity criterion 判定的 identity 相同。

---

# 6. 身份保持動力學

令：

$$
\Gamma:
\mathcal X
\rightarrow
\mathcal X
$$

為 state dynamics。

## 定義 6.1 — Identity-Preserving Dynamics

若：

$$
\boxed{
q_\kappa\circ\Gamma
=
q_\kappa,
}
$$

稱 $\Gamma$ 對 $\kappa$ identity-preserving。

---

## 定理 6.2 — Fiber Invariance Theorem

下列兩條等價：

1. 
$$
q_\kappa\Gamma
=
q_\kappa;
$$

2. 對所有：
$$
O\in\mathcal O_\kappa,
$$
有：
$$
\boxed{
\Gamma(F_O^\kappa)
\subseteq
F_O^\kappa.
}
$$

### 證明

若 1 成立，取：

$$
x\in F_O^\kappa.
$$

則：

$$
q_\kappa(x)=O.
$$

所以：

$$
q_\kappa(\Gamma(x))
=
q_\kappa(x)
=
O,
$$

故：

$$
\Gamma(x)
\in
F_O^\kappa.
$$

反之，若每個 fiber 在 $\Gamma$ 下 invariant，任取 $x$，令：

$$
O=q_\kappa(x).
$$

由：

$$
x\in F_O^\kappa
$$

與 invariant 性得：

$$
\Gamma(x)\in F_O^\kappa.
$$

故：

$$
q_\kappa(\Gamma(x))
=
O
=
q_\kappa(x).
$$

所以：

$$
q_\kappa\Gamma
=
q_\kappa.
\qquad\square
$$

---

## 解釋

「同一個東西在變」的形式意思不是：

$$
x_{t+1}=x_t.
$$

而是：

$$
\boxed{
x_t
\neq
x_{t+1},
\qquad
q_\kappa(x_t)
=
q_\kappa(x_{t+1}).
}
$$

也就是 dynamics 發生在同一 identity fiber 內。

---

# 7. Identity Lineage

某些 dynamics 會跨 fiber。

例如：

- semantic sense split；
- process fork；
- version identity change；
- carrier replacement；
- 某 identity criterion 下的 material phase identity change。

此時不能把：

$$
q_\kappa\Gamma
\neq
q_\kappa
$$

硬稱 identity-preserving phase change。

---

## 定義 7.1 — Lineage Map

給定：

$$
q_\kappa:
\mathcal X
\rightarrow
\mathcal O_\kappa,
$$

$$
q_{\kappa'}:
\mathcal X'
\rightarrow
\mathcal O_{\kappa'},
$$

與：

$$
\Gamma:
\mathcal X
\rightarrow
\mathcal X',
$$

若存在：

$$
\boxed{
L:
\mathcal O_\kappa
\rightarrow
\mathcal O_{\kappa'}
}
$$

使：

$$
\boxed{
q_{\kappa'}\circ\Gamma
=
L\circ q_\kappa,
}
$$

則稱 $L$ 為 $\Gamma$ 的 identity-lineage map。

---

# 8. Lineage Factorization Theorem

## 定理 8.1

假設：

$$
q_\kappa:
\mathcal X
\twoheadrightarrow
\mathcal O_\kappa
$$

為滿射。

存在唯一：

$$
L:
\mathcal O_\kappa
\rightarrow
\mathcal O_{\kappa'}
$$

使：

$$
q_{\kappa'}\Gamma
=
Lq_\kappa
$$

當且僅當：

$$
\boxed{
q_\kappa(x_1)=q_\kappa(x_2)
\Rightarrow
q_{\kappa'}(\Gamma(x_1))
=
q_{\kappa'}(\Gamma(x_2)).
}
$$

也就是：

$$
q_{\kappa'}\Gamma
$$

在每個 identity fiber 上為常數。

### 證明

**必要性。**

若：

$$
q_{\kappa'}\Gamma
=
Lq_\kappa,
$$

且：

$$
q_\kappa(x_1)=q_\kappa(x_2),
$$

則：

$$
q_{\kappa'}\Gamma(x_1)
=
Lq_\kappa(x_1)
=
Lq_\kappa(x_2)
=
q_{\kappa'}\Gamma(x_2).
$$

**充分性。**

對：

$$
O\in\mathcal O_\kappa,
$$

因 $q_\kappa$ 滿射，選任意：

$$
x\in q_\kappa^{-1}(O).
$$

定義：

$$
L(O)
=
q_{\kappa'}(\Gamma(x)).
$$

由 fiber-constancy，此定義與代表元 $x$ 的選擇無關，因此良定義。

且：

$$
L(q_\kappa(x))
=
q_{\kappa'}(\Gamma(x)),
$$

故：

$$
Lq_\kappa
=
q_{\kappa'}\Gamma.
$$

唯一性來自 $q_\kappa$ 滿射：任何滿足交換圖的 $L'$ 對所有 $O=q_\kappa(x)$ 都有：

$$
L'(O)
=
q_{\kappa'}\Gamma(x)
=
L(O).
\qquad\square
$$

---

## 推論 8.2 — Identity Dynamics Exists Only Under Fiber Sufficiency

若同一 identity fiber 中兩個 states：

$$
x_1,x_2
$$

經 $\Gamma$ 後被送到不同 identity classes，則不存在只依舊 identity：

$$
O=q_\kappa(x)
$$

決定的新 identity dynamics。

換句話說：

$$
\boxed{
\text{identity class is dynamically sufficient}
}
$$

當且僅當 downstream identity 對每個 old identity fiber 為常數。

這是 IPFC 與 GPC-CS / PCPRT fiber principle 的直接同型結構。

---

# 9. Identity Preservation 是 Lineage 的特例

若：

$$
\kappa'=\kappa
$$

且：

$$
L
=
\operatorname{id}_{\mathcal O_\kappa},
$$

則：

$$
q_\kappa\Gamma
=
q_\kappa.
$$

因此：

$$
\boxed{
\text{identity preservation}
=
\text{trivial lineage}.
}
$$

---

# 10. Index / Context Transport

phase 不只由 instantaneous state 決定，也可能具有 path dependence。

令 index/context space 為：

$$
I.
$$

一條 path：

$$
\gamma:
i_0
\rightarrow
i_1
\rightarrow
\cdots
\rightarrow
i_n.
$$

---

## 定義 10.1 — State Transport

對每條可合成 path $\gamma$，定義：

$$
\boxed{
T^\mathcal X_\gamma:
\mathcal X_{i_0}
\rightarrow
\mathcal X_{i_n}.
}
$$

要求：

$$
T^\mathcal X_{\operatorname{id}_i}
=
\operatorname{id}_{\mathcal X_i},
$$

以及 path composition：

$$
\boxed{
T^\mathcal X_{\gamma_2\circ\gamma_1}
=
T^\mathcal X_{\gamma_2}
\circ
T^\mathcal X_{\gamma_1},
}
$$

當 composition 有定義時。

---

## 定義 10.2 — View Transport

同理：

$$
\boxed{
T^\mathcal V_\gamma:
\mathcal V_{i_0}
\rightarrow
\mathcal V_{i_n}.
}
$$

---

## 定義 10.3 — Resolution Compatibility

理想情況：

$$
\boxed{
\rho\circ
T^\mathcal V_\gamma
=
T^\mathcal X_\gamma
\circ
\rho.
}
$$

如果只近似成立，可定義：

$$
\boxed{
\varepsilon_{\rho,\gamma}(V)
=
d_\mathcal X
\left(
\rho T^\mathcal V_\gamma(V),
T^\mathcal X_\gamma\rho(V)
\right).
}
$$

---

# 11. Phase Transport

對 phase space：

$$
\Phi_i,
$$

定義：

$$
\boxed{
T^\Phi_\gamma:
\Phi_{i_0}
\rightarrow
\Phi_{i_n}.
}
$$

理想 intertwinement：

$$
\boxed{
\Theta_{i_n}
\circ
T^\mathcal X_\gamma
=
T^\Phi_\gamma
\circ
\Theta_{i_0}.
}
$$

若只近似交換：

$$
\boxed{
\varepsilon_{\Phi,\gamma}(x)
=
d_\Phi
\left(
\Theta_{i_n}T^\mathcal X_\gamma(x),
T^\Phi_\gamma\Theta_{i_0}(x)
\right).
}
$$

---

# 12. Identity-Preserving Transport

## 定義 12.1

若對 path $\gamma$：

$$
\boxed{
q_\kappa
T^\mathcal X_\gamma
=
q_\kappa,
}
$$

稱此 transport identity-preserving。

---

## 命題 12.2

identity-preserving transport 對每個 identity fiber：

$$
F_O^\kappa
$$

定義 endomorphism：

$$
\boxed{
T^\mathcal X_\gamma
:
F_O^\kappa
\rightarrow
F_O^\kappa.
}
$$

證明同定理 6.2。$\square$

---

# 13. Holonomy

令：

$$
\gamma
$$

為閉路：

$$
i_n=i_0.
$$

則：

$$
T^\mathcal X_\gamma
:
\mathcal X_{i_0}
\rightarrow
\mathcal X_{i_0}.
$$

---

## 定義 13.1 — State Holonomy

定義：

$$
\boxed{
\operatorname{Hol}^\mathcal X_\gamma
=
T^\mathcal X_\gamma.
}
$$

若：

$$
\operatorname{Hol}^\mathcal X_\gamma
\neq
\operatorname{id},
$$

存在 nontrivial state holonomy。

---

## 定義 13.2 — Identity-Preserving Holonomy

若：

$$
\boxed{
q_\kappa
\operatorname{Hol}^\mathcal X_\gamma
=
q_\kappa,
}
$$

則稱為 identity-preserving holonomy。

這表示：

$$
\boxed{
\operatorname{Hol}_\gamma(x)
\neq
x
}
$$

可以成立，同時：

$$
\boxed{
q_\kappa(\operatorname{Hol}_\gamma(x))
=
q_\kappa(x).
}
$$

自然語言：

> 走了一圈，還是同一個它，但不是完全同一個 state。

---

## 定義 13.3 — Holonomy Defect

給定 state difference：

$$
\Delta_\mathcal X,
$$

定義：

$$
\boxed{
\mathfrak C_\gamma(x)
=
\Delta_\mathcal X
\left(
x,
\operatorname{Hol}_\gamma(x)
\right).
}
$$

若：

$$
\mathfrak C_\gamma(x)=0,
$$

此 closed transport 對 $x$ 閉合。

若：

$$
\mathfrak C_\gamma(x)>0,
$$

則存在 loop residual。

---

# 14. Identity Holonomy Theorem

## 定理 14.1

若 path transport 的每個基本段：

$$
T^\mathcal X_e
$$

均 identity-preserving，則任意由它們合成的 path transport與 closed-loop holonomy 都 identity-preserving。

### 證明

對兩段：

$$
T_1,T_2
$$

有：

$$
qT_1=q,
$$

$$
qT_2=q.
$$

故：

$$
qT_2T_1
=
(qT_2)T_1
=
qT_1
=
q.
$$

有限合成由歸納成立。

閉路只是此類 path composition 的特例。$\square$

---

# 15. $U(1)$ 特例：Geometric Phase

標準 geometric-phase 數學提供 IPFC 的一個嚴格特例。

若：

1. phase fiber 為一維複線上的 $U(1)$ action；
2. closed transport 可寫為：
   $$
   T^\Phi_\gamma(\psi)
   =
   e^{i\Phi_\gamma}\psi;
   $$
3. physical theory 已建立合法 connection / parallel transport；

則：

$$
\boxed{
e^{i\Phi_\gamma}
}
$$

是 holonomy factor，而：

$$
\boxed{
\Phi_\gamma
}
$$

是 geometric phase。

Simon 1983 將 Berry 的 geometric phase 精確識別為 Hermitian line bundle connection 的 holonomy。本文只採此結果為標準物理／幾何先例。

---

# 16. Cyclic but Nonadiabatic Geometric Phase

Aharonov–Anandan 類結果顯示，geometric phase 的 closed-loop structure 不必只侷限於 adiabatic Berry setting。

對 IPFC 的方法論啟示是：

$$
\boxed{
\text{holonomy/path structure}
}
$$

比「慢速絕熱」更一般。

但本文不因此把任何 generalized semantic/context loop 稱為量子 geometric phase。

generalized domain 必須自己定義：

- phase space；
- transport；
- loop；
- observable；
- defect；
- falsification。

---

# 17. Non-Abelian Holonomy

Wilczek–Zee 類結構表明，在適當退化子空間與 adiabatic transport 中，holonomy 可取值於 non-Abelian group。

抽象地，若 phase/state fiber 有 group action：

$$
G\curvearrowright F,
$$

closed transport 可對應：

$$
\boxed{
g_\gamma
\in
G.
}
$$

若：

$$
g_{\gamma_1}g_{\gamma_2}
\neq
g_{\gamma_2}g_{\gamma_1},
$$

則 path order 重要。

IPFC 只把這當作：

> holonomy 不必等於 scalar angle

的成熟數學先例。

它不授權：

$$
\boxed{
\text{semantic phase}
=
\text{non-Abelian quantum gauge field}.
}
$$

---

# 18. Phase Dynamics

instantaneous state dynamics：

$$
\Gamma_t:
\mathcal X
\rightarrow
\mathcal X.
$$

phase dynamics 可由：

$$
\boxed{
\phi_t
=
\Theta(x_t;c_t)
}
$$

誘導。

若：

$$
q_\kappa(x_t)=O
$$

對整段 trajectory 成立，則 trajectory 完全位於：

$$
F_O^\kappa.
$$

---

## 定義 18.1 — Intra-Identity Phase Dynamics

若：

$$
q_\kappa\Gamma_t
=
q_\kappa
$$

且：

$$
\Theta(\Gamma_t x)
\neq
\Theta(x)
$$

對某些 $x$ 成立，則為：

$$
\boxed{
\text{identity-preserving phase dynamics}.
}
$$

---

# 19. Phase Transition 與 Identity Criterion

「相變後還是不是同一個東西」不是純 phase 問題，而依賴：

$$
\kappa.
$$

同一物理 specimen 從 liquid 變 solid：

若 $\kappa_{\mathrm{specimen}}$ 只追蹤 specimen lineage：

$$
q_{\kappa_{\mathrm{specimen}}}(x_{\mathrm{liq}})
=
q_{\kappa_{\mathrm{specimen}}}(x_{\mathrm{sol}}),
$$

是 intra-identity regime transition。

若 $\kappa_{\mathrm{phase}}$ 把 material phase class 納入 identity：

$$
q_{\kappa_{\mathrm{phase}}}(x_{\mathrm{liq}})
\neq
q_{\kappa_{\mathrm{phase}}}(x_{\mathrm{sol}}),
$$

則是 identity-lineage transition。

因此：

$$
\boxed{
\text{phase transition}
\not\Rightarrow
\text{identity transition}
}
$$

也不推出反向。

必須明示 $\kappa$。

---

# 20. IF-0 至 IF-4：相位相對同一性的角色

Phase Canon PH-0 至 PH-6 回答：

> phase 是哪一型？

IPFC 新增 IF-0 至 IF-4 回答：

> phase 相對 identity 扮演什麼角色？

---

## IF-0 — Presentation / Gauge Phase

view/index 改變，但 resolved state 不變：

$$
\boxed{
\rho T^\mathcal V
=
\rho.
}
$$

identity 自然不變。

---

## IF-1 — Intra-Identity State Phase

state 真變：

$$
T^\mathcal X(x)
\neq
x,
$$

但：

$$
\boxed{
q_\kappa T^\mathcal X(x)
=
q_\kappa(x).
}
$$

---

## IF-2 — Holonomic / Path Phase

closed path 後：

$$
\boxed{
T_\gamma x
\neq
x,
}
$$

但：

$$
\boxed{
q_\kappa(T_\gamma x)
=
q_\kappa(x).
}
$$

---

## IF-3 — Inter-Identity Relational Phase

phase 是不同 identity fibers 間的 relation：

$$
\boxed{
\Delta_\Phi
(
x_A,
x_B
\mid
T,C
).
}
$$

不要求：

$$
q(x_A)=q(x_B).
$$

---

## IF-4 — Identity-Lineage Transition Phase

若：

$$
\boxed{
q_{\kappa'}\Gamma
=
Lq_\kappa,
\qquad
L\neq
\operatorname{id},
}
$$

phase/regime change 伴隨 identity class 遷移。

---

# 21. PH × IF 雙重分型

任一 Phase Module 應標：

$$
\boxed{
PH\text{-}k
\times
IF\text{-}j.
}
$$

例：

| 模組 | Phase Canon | IPFC |
|---|---|---|
| physical oscillator phase | PH-0 | IF-1 |
| relative/geometric phase | PH-1 / PH-0 | IF-2 |
| material regime phase | PH-2 | IF-1 或 IF-4 |
| neural functional phase | PH-4 | IF-1 / IF-2 |
| relational semantic phase | PH-5 | IF-1 / IF-2 / IF-3 / IF-4 |
| GIPSS candidate-target phase | PH-6 | IF-3 |
| classical multiphase converter | PH-0 / PH-1 | IF-1 / IF-2 |

此雙軸禁止再用一個「phase」詞同時包辦數學型別與 identity role。

---

# 22. Pure Presentation Phase 與 Functional Phase

令 task observable：

$$
H_T:
\mathcal X
\rightarrow
\mathcal Y_T.
$$

phase-associated transformation：

$$
g:
\mathcal X
\rightarrow
\mathcal X.
$$

---

## 定義 22.1 — Task-Gauge Transformation

若：

$$
\boxed{
H_T(gx)
=
H_T(x)
}
$$

對所有 $x$ 成立，則 $g$ 對 task $T$ 不可觀測。

若 $g$ 也只改 view 而不改 resolved state，則屬 IF-0。

---

## 定義 22.2 — Functional Phase Effect

若存在 $x$ 使：

$$
\boxed{
H_T(gx)
\neq
H_T(x),
}
$$

則此 phase transformation 對 task $T$ 有 functional effect。

這與 Phase Canon 的 ablation rule 一致：

$$
\boxed{
\text{phase label}
\neq
\text{functional phase evidence}.
}
$$

---

# 23. 相位語義作為壓力測試

本文不在此完整建立相位語義理論，只驗證 IPFC 是否能乾淨承載它。

令：

$$
\mathcal X_{\mathrm{sem}}
$$

為 semantic state space，

$$
q_{\mathrm{sem},\kappa}
:
\mathcal X_{\mathrm{sem}}
\rightarrow
\mathcal O_{\mathrm{sem},\kappa}
$$

為 semantic identity projection。

context / receiver / reference / task：

$$
(c,b,r,T).
$$

定義：

$$
\boxed{
\Theta_{\mathrm{sem},T}
(
x;c,b,r
)
\in
\Phi_{\mathrm{sem},T}.
}
$$

此處 canonical type：

$$
PH\text{-}5.
$$

若同 semantic identity 在不同 context 有不同 phase：

$$
q_{\mathrm{sem}}(x_1)
=
q_{\mathrm{sem}}(x_2),
$$

但：

$$
\Theta_{\mathrm{sem}}(x_1;c_1)
\neq
\Theta_{\mathrm{sem}}(x_2;c_2),
$$

則是：

$$
PH\text{-}5
\times
IF\text{-}1.
$$

---

# 24. Semantic Holonomy Interface

context loop：

$$
\gamma:
c_0
\rightarrow
c_1
\rightarrow
\cdots
\rightarrow
c_n=c_0.
$$

若：

$$
q_{\mathrm{sem}}
T^\mathcal X_\gamma(x)
=
q_{\mathrm{sem}}(x),
$$

但：

$$
T^\mathcal X_\gamma(x)
\neq
x,
$$

則：

$$
\boxed{
\text{Semantic Holonomy}
}
$$

作為：

$$
PH\text{-}5
\times
IF\text{-}2
$$

的候選結構。

這可用於未來研究：

- translation round-trip drift；
- ontology migration loop；
- agent A→B→C→A semantic residual；
- diachronic context loop。

但只有在 transport 被定義後才能使用 holonomy 名稱。

---

# 25. Semantic Identity Split

若：

$$
q_{\mathrm{sem},\kappa'}
(
\Gamma(x)
)
\neq
q_{\mathrm{sem},\kappa}(x),
$$

則不能稱 same-identity semantic holonomy。

而應寫：

$$
\boxed{
q_{\mathrm{sem},\kappa'}
\Gamma
=
L_{\mathrm{sem}}
q_{\mathrm{sem},\kappa}.
}
$$

這是：

$$
PH\text{-}5
\times
IF\text{-}4.
$$

例如：

- word sense split；
- ontology entity split；
- concept fork。

---

# 26. GPC-CS 的 IPFC 接口

GPC receiver update：

$$
x_B'
=
F_B
\left(
x_B,
D_B
\left(
T_{AB}
\left(
E_A(x_A)
\right),
x_B
\right)
\right).
$$

IPFC 另外追蹤：

$$
q_A(x_A)
=
O_A,
$$

$$
q_B(x_B)
=
O_B.
$$

sender–receiver relation：

$$
IF\text{-}3.
$$

receiver state update 後：

若：

$$
q_B(x_B')
=
q_B(x_B),
$$

則 communication 為 carrier-identity-preserving update。

若：

$$
q_B(x_B')
\neq
q_B(x_B),
$$

則需要：

$$
L_B:
O_B
\rightarrow
O_B'
$$

描述 carrier identity lineage。

這給 GPC-CS 原本的 identity/continuity risk 一個明確數學接口。

---

# 27. PCPRT 的 IPFC 接口

PCPRT：

$$
\Pi
:
\mathcal Z_{\mathrm{phys}}
\rightarrow
\mathcal X
$$

負責 physical realization。

IPFC：

$$
q_\kappa:
\mathcal X
\rightarrow
\mathcal O_\kappa
$$

負責 identity classification。

Phase Canon：

$$
\Theta:
\mathcal X
\rightarrow
\Phi
$$

負責 typed phase extraction。

因此：

$$
\boxed{
\mathcal Z_{\mathrm{phys}}
\xrightarrow{\Pi}
\mathcal X
\xrightarrow{q_\kappa}
\mathcal O_\kappa
}
$$

與：

$$
\boxed{
\mathcal X
\xrightarrow{\Theta}
\Phi
}
$$

形成 orthogonal projections。

物理 phase 不得被 identity integral 自動消去。

若：

$$
\Theta
$$

在 task / dynamics 上有 functional role，必須留在 $\mathcal X$ 或其充分 coarse state 中。

---

# 28. Approximate IPFC

實際系統常非精確。

---

## 定義 28.1 — Identity Defect

若 identity space 有距離：

$$
d_\mathcal O,
$$

定義：

$$
\boxed{
\varepsilon_{\mathrm{id}}(x,x')
=
d_\mathcal O
\left(
q_\kappa(x),
q_\kappa(x')
\right).
}
$$

若 identity classes 離散：

$$
\boxed{
\varepsilon_{\mathrm{id}}
=
\mathbf 1
[
q_\kappa(x)
\neq
q_\kappa(x')
].
}
$$

---

## 定義 28.2 — Lineage Factorization Defect

給定候選 lineage：

$$
L,
$$

定義：

$$
\boxed{
\varepsilon_L(x)
=
d_{\mathcal O'}
\left(
q_{\kappa'}\Gamma(x),
Lq_\kappa(x)
\right).
}
$$

---

## 定義 28.3 — Phase Transport Defect

$$
\boxed{
\varepsilon_{\Phi,\gamma}(x)
=
d_\Phi
\left(
\Theta T^\mathcal X_\gamma(x),
T^\Phi_\gamma\Theta(x)
\right).
}
$$

---

## 定義 28.4 — Physical Realization Defect

沿用 PCPRT：

$$
\boxed{
\varepsilon_{\Pi,\Gamma}(z)
=
d_\mathcal X
\left(
\Pi\Phi_{\mathrm{phys}}(z),
\Gamma\Pi(z)
\right).
}
$$

四種 defect 不應混成單一「alignment score」。

---

# 29. Approximate Lineage Bound

## 命題 29.1

若：

$$
L
$$

為候選 lineage，

且：

$$
\varepsilon_L(x)
\le
\epsilon
$$

在 domain $K$ 一致成立，則 identity-level dynamics 可在 $K$ 上以 $L$ 作 $\epsilon$-approximation。

這是定義的直接結果。

真正困難的是：

> 是否存在一個低 defect 的 $L$，而且 defect 不只是因 identity metric 太寬鬆而人為縮小？

因此任何 approximate identity model 必須同時聲明：

- identity criterion；
- identity metric；
- validation set；
- counterexamples。

---

# 30. Phase Attachment Contract

未來任一「X 相位／相位 X」若要接入 IPFC / Phase Canon，至少提供：

$$
\boxed{
\mathfrak M_D
=
(
D,
\kappa,
\mathcal X,
q_\kappa,
I,
PH,
IF,
\Phi,
\Theta,
T,
\Gamma,
H,
L,
\Pi,
\varepsilon,
\mathcal F
).
}
$$

其中：

- $D$：domain；
- $\kappa$：identity criterion；
- $\mathcal X$：state space；
- $q_\kappa$：identity projection；
- $I$：index/context space；
- $PH$：Phase Canon type；
- $IF$：IPFC identity-role type；
- $\Phi$：phase space；
- $\Theta$：phase extractor；
- $T$：transport；
- $\Gamma$：dynamics；
- $H$：observable/task；
- $L$：lineage map；
- $\Pi$：physical realization map，若宣稱 physical；
- $\varepsilon$：defect family；
- $\mathcal F$：falsification rule。

---

# 31. Phase Attachment Rejection Rules

## R1 — No Identity Criterion

不知道「誰／什麼」在變。

拒絕。

## R2 — No Phase Type

沒有 PH-0 至 PH-6 分型。

拒絕。

## R3 — No Identity Role

不知道是 IF-0 至 IF-4 哪一型。

拒絕。

## R4 — Renaming Only

只有：

$$
x
\mapsto
\phi_x
$$

重新命名，沒有新 relation / dynamics / observable。

拒絕 phase-mechanics claim。

## R5 — Physical Type Jump

PH-5 / PH-6 無 $\Pi$ 卻宣稱 PH-0。

拒絕。

## R6 — Holonomy Without Transport

沒有 path transport：

$$
T_\gamma
$$

卻聲稱 holonomy。

拒絕。

## R7 — Identity Change Misnamed Holonomy

若：

$$
q(T_\gamma x)
\neq
q(x),
$$

不得稱 same-identity holonomy。

必須進 lineage。

---

# 32. Phase Module Morphism

令：

$$
\mathfrak M_A,
\qquad
\mathfrak M_B
$$

為兩個 phase modules。

定義 state map：

$$
F_X:
\mathcal X_A
\rightarrow
\mathcal X_B,
$$

identity map：

$$
F_O:
\mathcal O_A
\rightarrow
\mathcal O_B.
$$

若：

$$
\boxed{
q_BF_X
=
F_Oq_A,
}
$$

則 identity diagram 交換。

再令：

$$
F_\Phi:
\Phi_A
\rightarrow
\Phi_B.
$$

若：

$$
\boxed{
\Theta_BF_X
=
F_\Phi\Theta_A,
}
$$

則 phase diagram 交換。

此時稱：

$$
\boxed{
F:
\mathfrak M_A
\rightarrow
\mathfrak M_B
}
$$

為 exact Phase Module Morphism。

若只近似交換，則以 defect 控制。

---

# 33. Phase Module Composition Theorem

## 定理 33.1

若：

$$
\mathfrak M_A
\xrightarrow{F}
\mathfrak M_B
\xrightarrow{G}
\mathfrak M_C
$$

均為 exact Phase Module Morphisms，則：

$$
\boxed{
G\circ F
:
\mathfrak M_A
\rightarrow
\mathfrak M_C
}
$$

亦為 exact Phase Module Morphism。

### 證明

identity side：

$$
q_CG_XF_X
=
G_Oq_BF_X
=
G_OF_Oq_A.
$$

phase side：

$$
\Theta_CG_XF_X
=
G_\Phi\Theta_BF_X
=
G_\Phi F_\Phi\Theta_A.
$$

故 composite maps：

$$
(G_XF_X,G_OF_O,G_\Phi F_\Phi)
$$

同時保持 identity diagram 與 phase diagram。$\square$

---

# 34. 這如何改善未來「相位語義／XX 相位」

以前一個新領域常只寫：

$$
\text{X}
\rightarrow
\phi_X.
$$

問題是：

- X 是 identity 還是 state？
- phase 是 physical 還是 generalized？
- 是否只是相似度？
- 是否有路徑？
- 是否有 observable？
- identity 是否可能分裂？

IPFC 強迫改成：

$$
\boxed{
\text{Identity}
\rightarrow
\text{State}
\rightarrow
\text{Phase}
\rightarrow
\text{Transport}
\rightarrow
\text{Observable}
}
$$

並在 identity 改變時另行加入：

$$
\boxed{
\text{Lineage}.
}
$$

所以「XX phase」不再是一個詞，而是一個可檢驗 module。

---

# 35. 與標準數學／物理的關係

本文使用：

- fiber；
- bundle；
- connection；
- holonomy；
- $U(1)$；
- non-Abelian transport；

時遵守以下界線。

## 35.1 Fiber

對任意 map：

$$
q:X\rightarrow O,
$$

fiber：

$$
q^{-1}(O)
$$

是標準用法。

## 35.2 Fiber Bundle

只有另證 local triviality 等 bundle conditions 時使用。

## 35.3 Holonomy

只有存在明確 transport / connection / loop 才使用。

## 35.4 Geometric Phase

只有相應幾何／物理結構被建立時，才把 holonomy 稱為 geometric phase。

## 35.5 Generalized Semantic / AI Phase

不能因其形式上使用：

$$
\operatorname{Hol}_\gamma
$$

就宣稱為量子 geometric phase。

---

# 36. 可證偽性與失敗條件

IPFC 不是一個「任何東西都能放進來」的無限容器。

以下結果會使具體 module 失敗或降級。

## F1 — Identity Projection 不可操作化

若 $q_\kappa$ 無法定義或無法穩定判定，identity fiber 失去操作意義。

## F2 — Fiber Constancy 失敗

若聲稱存在 identity lineage $L$，但同一 old identity fiber 中 states 被 $\Gamma$ 送往不同 downstream identities，則 identity-level $L$ 不存在。

## F3 — Phase Renaming

若 phase model 相對非 phase typed baseline 無 observable / predictive / structural 增益，phase 不具 algorithmic necessity。

## F4 — Transport 不閉合

若所謂 semantic / cognitive holonomy 沒有可定義 transport，holonomy claim 撤回。

## F5 — Physical Realization 失敗

若 PH-5 / PH-6 無法建立：

$$
\Pi:
\mathcal Z_{\mathrm{phys}}
\rightarrow
\mathcal X,
$$

不得升格為 PH-0。

## F6 — Identity Criterion Sensitivity

若結論完全依賴任意選取 $\kappa$，且沒有任務或理論理由選擇該 criterion，identity conclusion 必須降級為 criterion-relative。

---

# 37. 理論地位

IPFC v1.0 的 claim 分成三層。

## 已由本文證明的形式結果

- Fiber Invariance Theorem；
- Lineage Factorization Theorem；
- identity-preserving transport closure；
- Identity Holonomy Theorem；
- Phase Module Composition Theorem。

這些是定義／集合映射層的形式結果。

## 由外部成熟數學支持的特例

- $U(1)$ geometric-phase holonomy；
- non-Abelian holonomy；
- cyclic geometric phase。

## 尚未實證／形式化的 EveMissLab 下游

- Semantic Holonomy；
- AI identity-lineage dynamics；
- GPC carrier-identity transition benchmarks；
- phase-module cross-domain morphisms；
- physical identity realization across phase transitions。

---

# 38. 形式化路線

上游《同一性微積分 v0.2》已經報告 Lean 4 驗證：

$$
\int_Hd_I
=
\operatorname{id},
$$

切法無關性、迭代不變性、本體守恆與範疇論橋。

本文下一步的 Lean formalization 應獨立建立：

1. `IdentitySystem X O q`
2. `Fiber q O`
3. `IdentityPreserving Γ q`
4. `fiber_invariant_iff`
5. `lineage_factorization_iff`
6. `Transport`
7. `IdentityHolonomy`
8. `PhaseModule`
9. `PhaseModuleMorphism`
10. `phase_module_comp`

本文 v1.0 不聲稱這十項已機器驗證。

---

# 39. 主要外部文獻錨點

## Simon 1983

Barry Simon 證明 Berry geometric phase 是 Hermitian line bundle connection 的 holonomy。

本文由此採用：

> geometric phase 可合法表述為 fiber/connection/holonomy 結構

這個標準先例。

## Wilczek–Zee 1984

Wilczek 與 Zee 展示 non-Abelian gauge structure 可由 adiabatic development 產生。

本文由此採用：

> holonomy 不必壓成單一 scalar angle

這個標準先例。

## Aharonov–Anandan 1987

Aharonov 與 Anandan 對 cyclic quantum evolution 定義 geometric phase，不要求只限 adiabatic Berry setting。

本文由此採用：

> closed-path geometric structure 比單一 adiabatic construction 更一般

這個標準先例。

三者都不證明：

- semantic phase 是 quantum phase；
- identity fiber 是 physical fiber bundle；
- AI state 具有 gauge field；
- GPC communication 是 geometric quantum evolution。

---

# 40. 統一結論

同一性微積分與相位理論真正的統一，不是：

$$
\boxed{
\text{Identity}
=
\text{Phase}.
}
$$

而是：

$$
\boxed{
\text{Identity}
\rightarrow
\text{Fiber};
\qquad
\text{Phase}
\rightarrow
\text{Position / Relation / Transport};
\qquad
\text{Lineage}
\rightarrow
\text{Fiber Change}.
}
$$

在 identity-preserving dynamics 中：

$$
\boxed{
q_\kappa\Gamma
=
q_\kappa.
}
$$

在 identity-changing dynamics 中：

$$
\boxed{
q_{\kappa'}\Gamma
=
Lq_\kappa.
}
$$

在 closed path 中：

$$
\boxed{
q_\kappa\operatorname{Hol}_\gamma
=
q_\kappa
}
$$

允許：

$$
\boxed{
\operatorname{Hol}_\gamma(x)
\neq
x.
}
$$

因此本論文的核心句是：

> **同一性決定「是哪一個」；相位決定「這一個現在在哪裡、和誰相對、沿路如何變」；譜系決定「何時已經不再只是同一個的變化」。**

IPFC 因而不是另一套「萬物相位論」，也不是把同一性微積分物理化；它是一個 typed bridge，使同一性、state、phase、transport、holonomy、physical realization 與 lineage 可以在同一交換圖中被分別追蹤。

---

# 41. 後續系列

## IPFC Paper 02
**《相位語義：同一語義身份上的關係座標、Context Transport 與 Semantic Holonomy》**

## IPFC Paper 03
**《相變與同一性分岔：Identity-Preserving Regime Change 與 Lineage Transition》**

## IPFC Paper 04
**《GPC 中的載體同一性：跨載體交流、Receiver Update 與 Identity Safety》**

## IPFC Paper 05
**《Phase Module Calculus：XX 相位的通用接駁、組合與反證規格》**

## IPFC Paper 06
**《AI Fork、忒修斯與語義分裂：Identity Lineage 的計算模型》**

---

# 參考文獻

1. Neo.K & Theia. *同一性微積分：拓樸微積分的本體論基礎 v0.2*. EveMissLab, 2026.
2. Neo.K & Theia. *參照語義微積分：拓樸微積分的計算機實現 v0.2*. EveMissLab, 2026.
3. Neo.K & Aletheia. *索引幾何學：同一性拓樸微積分中的座標、投影與可計算性 v0.1*. EveMissLab, 2026.
4. EveMissLab. *Phase Canon v1.1*. 2026.
5. EveMissLab. *GPC-CS Papers 00–10*. 2026.
6. EveMissLab. *PCPRT Papers 01–08*. 2026.
7. Simon, B. “Holonomy, the Quantum Adiabatic Theorem, and Berry's Phase.” *Physical Review Letters* 51, 2167 (1983). DOI: 10.1103/PhysRevLett.51.2167.
8. Wilczek, F. & Zee, A. “Appearance of Gauge Structure in Simple Dynamical Systems.” *Physical Review Letters* 52, 2111 (1984). DOI: 10.1103/PhysRevLett.52.2111.
9. Aharonov, Y. & Anandan, J. “Phase Change During a Cyclic Quantum Evolution.” *Physical Review Letters* 58, 1593 (1987). DOI: 10.1103/PhysRevLett.58.1593.

---

**IPFC Paper 01 v1.0 — COMPLETE.**
