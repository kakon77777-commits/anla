# 相位語義：語義身份、關係座標、Context Transport 與 Semantic Holonomy
## Phase Semantics: Semantic Identity, Relational Coordinates, Context Transport, and Semantic Holonomy

**系列**：Identity–Phase Fiber Calculus（IPFC）  
**論文**：Paper 02 / Semantic Domain Module  
**版本**：v1.0  
**日期**：2026-08-15  
**作者**：Neo.K（許筌崴）with Aletheia  
**機構**：EveMissLab（一言諾科技有限公司），台灣  
**文件性質**：形式語義／計算語義／橋接理論／可驗證研究框架  
**上游**：
- IPFC Paper 01《同一性–相位纖維微積分》
- EveMissLab Phase Canon v1.1
- GPC-CS Papers 00–10
- 《相位交流：語言之後的意義傳遞》
- 《語義核、展開層與橋接層 v2.0》
- 《歷史的認知符號相位場論》之經 audit 後有效部分

**形式化狀態**：本文定理目前為手工形式證明，尚未完成 Lean 4 / Coq 機器驗證。  
**Canonical Type**：預設為：

$$
\boxed{
PH\text{-}5
}
$$

並依 identity role 分成：

$$
IF\text{-}1,\ IF\text{-}2,\ IF\text{-}3,\ IF\text{-}4.
$$

---

# 摘要

「相位語義」在早期 EveMissLab 理論中曾被用來表示語義對齊、跨載體傳遞、歷史語境共鳴與 AI 原生交流，但其核心困難始終存在：**語義身份、語義狀態、語義差異、語境效應與語義相位經常被同一個 phase 詞彙混在一起。** 在 Phase Canon v1.1 與 IPFC Paper 01 完成後，本文重新建立相位語義，使其不再等同於「語義本身」，也不再預設語義具有物理 $S^1$ 相位。

本文首先引入 criterion-relative semantic identity。對 semantic state space：

$$
\mathcal X_{\mathrm{sem}},
$$

給定 identity criterion：

$$
\kappa,
$$

定義：

$$
q_{\mathrm{sem},\kappa}
:
\mathcal X_{\mathrm{sem}}
\twoheadrightarrow
\mathcal O_{\mathrm{sem},\kappa}.
$$

不同 $\kappa$ 可以分別追蹤 lexeme、sense、concept、proposition、referent 與 communicative intent。再定義 relational semantic phase extractor：

$$
\Theta_{\mathrm{sem},T}
:
\mathcal X_{\mathrm{sem}}
\times
\mathcal C
\rightarrow
\Phi_{\mathrm{sem},T},
$$

其中 context bundle：

$$
\mathcal C
=
(
c,b,r,T
)
$$

包含語境、接收者背景、參照基底與任務。由此「相位語義」被定義為：

> **同一語義身份或不同語義身份，在明示的 context/reference/receiver/task 下，於 typed semantic relation space 中的位置、差異與可傳輸結構。**

本文證明三個核心 factorization theorem。第一，**Semantic Identity Recoverability Theorem**：semantic identity 可由 phase 唯一恢復：

$$
q_{\mathrm{sem}}
=
R\Theta_{\mathrm{sem}}
$$

當且僅當 semantic identity 在每個 phase fiber 上為常數。第二，**Semantic Task Sufficiency Theorem**：task observable：

$$
H_T
$$

可由 phase 單獨決定：

$$
H_T
=
\widehat H_T\Theta_{\mathrm{sem}}
$$

當且僅當 $H_T$ 在 phase fibers 上為常數。第三，**Joint Identity–Phase Sufficiency Theorem**：若單獨 identity 或 phase 都不充分，則聯合表示：

$$
J(x)
=
(
q_{\mathrm{sem}}(x),
\Theta_{\mathrm{sem}}(x)
)
$$

對 task 充分的條件是 $H_T$ 在 joint fibers 上為常數。

本文再建立 Context Transport 與 Semantic Holonomy。若一條閉合 context path：

$$
\gamma:
c_0
\rightarrow
c_1
\rightarrow
\cdots
\rightarrow
c_n=c_0
$$

滿足：

$$
q_{\mathrm{sem}}
T_\gamma(x)
=
q_{\mathrm{sem}}(x)
$$

但：

$$
T_\gamma(x)
\neq
x,
$$

則定義 **Semantic Holonomy**。此概念不被等同於量子 geometric phase，而是 IPFC 的 PH-5 × IF-2 一般 transport structure。本文同時證明：如果不同 contexts 都可由一個全域共享 semantic trivialization 精確連接，且 transport 完全由該 trivialization 的座標變換生成，則所有 closed loops 的 holonomy 必為恆等；故可重現的非零 semantic holonomy 表示至少有 path dependence、不可逆 context rewriting、非一致 decoder、噪聲、模型差異或不存在該全域精確 trivialization。

最後，本文提出三層 semantic communication success：identity success、phase alignment 與 functional success，並給出 translation round-trip、multi-agent loop、diachronic sense drift、ontology migration 與 paraphrase-preservation 五類 benchmark。本文主張：相位語義真正有用的地方不是把 meaning 改名為 phase，而是**明確區分「還是不是同一意思」與「同一意思目前處於什麼關係位置」以及「沿一條語境路徑後留下多少不可消去的殘差」。**

**關鍵詞**：相位語義、語義身份、語義相位、Semantic Holonomy、Context Transport、詞義變化、語義漂移、GPC、語義通訊、IPFC、語義同一性

---

# 1. 問題重述：Semantic Identity 不是 Semantic Phase

## 1.1 「語義變了」至少可能表示四件不同的事

一句：

> 語義變了。

至少可能指：

1. surface expression 改了；
2. semantic state 在 context 下移動；
3. relational phase 改了；
4. semantic identity 真正改變或分裂。

以前這四件事很容易被壓進：

$$
\Delta\phi_{\mathrm{sem}}.
$$

IPFC 要求拆開。

---

## 1.2 四層基本區分

本文固定：

$$
\boxed{
\text{Expression}
\neq
\text{Semantic State}
\neq
\text{Semantic Identity}
\neq
\text{Semantic Phase}.
}
$$

其中：

- Expression 是符號／句子／訊息；
- Semantic State 是可變的結構化語義狀態；
- Semantic Identity 是依 criterion $\kappa$ 所屬的 identity class；
- Semantic Phase 是相對 context/reference/receiver/task 的 typed relational coordinate。

---

# 2. Expression 與 Semantic State

令：

$$
\mathcal E
$$

為 expression space。

一個 expression：

$$
e\in\mathcal E.
$$

在 context：

$$
c
$$

與 receiver/background：

$$
b
$$

下，由 interpretation map：

$$
\boxed{
S:
\mathcal E
\times
\mathcal C_{\mathrm{int}}
\rightarrow
\mathcal X_{\mathrm{sem}}
}
$$

生成 semantic state：

$$
x
=
S(e;c,b).
$$

因此同一 expression 可以：

$$
S(e;c_1,b_1)
\neq
S(e;c_2,b_2).
$$

反之，不同 expressions 也可以產生 task-equivalent semantic states。

---

# 3. Semantic State 的 typed decomposition

本文不把 semantic state 預設為單一 embedding。

定義一個可選 typed product：

$$
\boxed{
\mathcal X_{\mathrm{sem}}
=
X_{\mathrm{den}}
\times
X_{\mathrm{inf}}
\times
X_{\mathrm{prag}}
\times
X_{\mathrm{aff}}
\times
X_{\mathrm{act}}
\times
X_{\mathrm{hist}}
\times
X_{\mathrm{unc}}.
}
$$

其中：

- $X_{\mathrm{den}}$：denotational / referential content；
- $X_{\mathrm{inf}}$：inferential relations；
- $X_{\mathrm{prag}}$：pragmatic force / discourse role；
- $X_{\mathrm{aff}}$：affective / connotative state；
- $X_{\mathrm{act}}$：action / decision implication；
- $X_{\mathrm{hist}}$：historical / provenance state；
- $X_{\mathrm{unc}}$：uncertainty / ambiguity。

具體模型可以只選其子集。

---

# 4. 六種 Semantic Identity Criterion

Semantic identity 不是單一概念。

---

## 4.1 Lexeme Identity

$$
\kappa_L.
$$

問：

> 是否為同一 lexeme / symbol identity？

---

## 4.2 Sense Identity

$$
\kappa_S.
$$

問：

> 是否屬於同一 lexical sense？

---

## 4.3 Concept Identity

$$
\kappa_C.
$$

問：

> 是否為同一概念／ontology concept？

---

## 4.4 Propositional Identity

$$
\kappa_P.
$$

問：

> 是否表達同一 proposition / claim content？

---

## 4.5 Referent Identity

$$
\kappa_R.
$$

問：

> 是否指向同一 referent/entity？

---

## 4.6 Communicative-Intent Identity

$$
\kappa_I.
$$

問：

> speaker 是否試圖完成同一 communicative intent？

---

# 5. Semantic Identity Projection

對任何 criterion：

$$
\kappa,
$$

定義：

$$
\boxed{
q_{\mathrm{sem},\kappa}
:
\mathcal X_{\mathrm{sem}}
\twoheadrightarrow
\mathcal O_{\mathrm{sem},\kappa}.
}
$$

identity fiber：

$$
\boxed{
F_O^{\mathrm{sem},\kappa}
=
q_{\mathrm{sem},\kappa}^{-1}(O).
}
$$

同一 identity fiber 中的 states 可以有不同：

- context；
- tone；
- uncertainty；
- pragmatic force；
- historical loading；
- receiver effect。

---

# 6. 第一個核心例子：翻譯

中文：

> 我受夠了。

英文：

> I've had enough.

在：

$$
\kappa_L
$$

下：

$$
q_{\kappa_L}(x_{\mathrm{ZH}})
\neq
q_{\kappa_L}(x_{\mathrm{EN}}).
$$

但在某些：

$$
\kappa_P
$$

或：

$$
\kappa_I
$$

下，可以：

$$
\boxed{
F_Oq_{\kappa_P}(x_{\mathrm{ZH}})
=
q_{\kappa_P}(x_{\mathrm{EN}}).
}
$$

所以「翻譯保持語義」永遠必須問：

> 保持哪一種 identity？

---

# 7. Relational Semantic Phase

## 定義 7.1

令：

$$
\mathcal C
=
C
\times
B
\times
R
\times
T
$$

分別代表：

- context；
- receiver/background；
- reference/base；
- task。

定義：

$$
\boxed{
\Theta_{\mathrm{sem},T}
:
\mathcal X_{\mathrm{sem}}
\times
\mathcal C
\rightarrow
\Phi_{\mathrm{sem},T}.
}
$$

semantic phase：

$$
\phi_{\mathrm{sem}}
=
\Theta_{\mathrm{sem},T}
(
x;c,b,r,T
).
$$

Canonical classification：

$$
\boxed{
PH\text{-}5.
}
$$

---

# 8. Semantic Phase 不是單一角度

預設：

$$
\Phi_{\mathrm{sem},T}
$$

不是：

$$
S^1.
$$

更自然的是 typed product：

$$
\boxed{
\Phi_{\mathrm{sem},T}
=
\Phi_{\mathrm{den}}
\times
\Phi_{\mathrm{inf}}
\times
\Phi_{\mathrm{prag}}
\times
\Phi_{\mathrm{aff}}
\times
\Phi_{\mathrm{act}}
\times
\Phi_{\mathrm{unc}}.
}
$$

對兩個 semantic states：

$$
x,y,
$$

定義：

$$
\boxed{
\Delta\Phi_{\mathrm{sem},T}(x,y)
=
(
d_{\mathrm{den}},
d_{\mathrm{inf}},
d_{\mathrm{prag}},
d_{\mathrm{aff}},
d_{\mathrm{act}},
d_{\mathrm{unc}}
).
}
$$

---

# 9. Scalarization 是後續 task choice

若 task $T$ 需要單一 score：

$$
\boxed{
D_T(x,y)
=
f_T
\left(
\Delta\Phi_{\mathrm{sem},T}(x,y)
\right).
}
$$

線性簡化可寫：

$$
D_T
=
w_T^\top
\Delta\Phi_{\mathrm{sem},T}.
$$

但：

$$
\boxed{
D_T
\neq
\Delta\Phi_{\mathrm{sem},T}.
}
$$

scalar ranking 不等於完整 semantic phase state。

---

# 10. Same Identity, Different Semantic Phase

## 命題 10.1

一般不存在：

$$
q_{\mathrm{sem}}(x_1)
=
q_{\mathrm{sem}}(x_2)
\Rightarrow
\Theta_{\mathrm{sem}}(x_1)
=
\Theta_{\mathrm{sem}}(x_2).
$$

### 解釋

同一 proposition 可以：

- 用不同禮貌強度說；
- 帶不同 sarcasm；
- 在不同 receiver 身上具有不同 implication；
- 在不同時代具有不同 connotation。

所以：

$$
\boxed{
\text{same semantic identity}
\not\Rightarrow
\text{same semantic phase}.
}
$$

這是：

$$
PH\text{-}5
\times
IF\text{-}1.
$$

---

# 11. Similar Phase, Different Identity

反之：

$$
\Theta(x_A)
\approx
\Theta(x_B)
$$

不推出：

$$
q(x_A)=q(x_B).
$$

例如：

> 自由

與：

> 自主

在某 task 下可能 relationally close，但不必是同一 concept identity。

這是：

$$
PH\text{-}5
\times
IF\text{-}3.
$$

---

# 12. Semantic Identity Recoverability Theorem

## 定理 12.1

給定：

$$
q:
\mathcal X_{\mathrm{sem}}
\rightarrow
\mathcal O_{\mathrm{sem}}
$$

與：

$$
\Theta:
\mathcal X_{\mathrm{sem}}
\rightarrow
\Phi_{\mathrm{sem}}.
$$

存在：

$$
\boxed{
R:
\Phi_{\mathrm{sem}}
\rightarrow
\mathcal O_{\mathrm{sem}}
}
$$

使：

$$
\boxed{
q
=
R\circ\Theta
}
$$

當且僅當：

$$
\boxed{
\Theta(x_1)=\Theta(x_2)
\Rightarrow
q(x_1)=q(x_2).
}
$$

即 semantic identity 在每個 phase fiber 上為常數。

### 證明

必要性：

若：

$$
q=R\Theta,
$$

且：

$$
\Theta(x_1)=\Theta(x_2),
$$

則：

$$
q(x_1)
=
R\Theta(x_1)
=
R\Theta(x_2)
=
q(x_2).
$$

充分性：

對：

$$
\phi
\in
\operatorname{im}\Theta,
$$

選：

$$
x
$$

使：

$$
\Theta(x)=\phi.
$$

定義：

$$
R(\phi)=q(x).
$$

由 phase-fiber constancy，此定義與代表元無關，故良定義。

在 $\Phi$ 的其餘部分可任意延拓，或限制 $R$ 定義域為 $\operatorname{im}\Theta$。

因此：

$$
q=R\Theta.
\qquad\square
$$

---

# 13. 意義：Phase 不自動包含 Identity

若存在：

$$
x_1,x_2
$$

使：

$$
\Theta(x_1)=\Theta(x_2)
$$

但：

$$
q(x_1)\neq q(x_2),
$$

則：

$$
\boxed{
\text{semantic phase cannot uniquely determine semantic identity}.
}
$$

所以 phase coordinate 不是完整 semantic ontology。

---

# 14. Semantic Task Sufficiency Theorem

令：

$$
H_T:
\mathcal X_{\mathrm{sem}}
\rightarrow
\mathcal Y_T
$$

為 task observable。

## 定理 14.1

存在：

$$
\widehat H_T:
\Phi_{\mathrm{sem},T}
\rightarrow
\mathcal Y_T
$$

使：

$$
\boxed{
H_T
=
\widehat H_T
\circ
\Theta_{\mathrm{sem},T}
}
$$

當且僅當：

$$
\boxed{
\Theta_{\mathrm{sem},T}(x_1)
=
\Theta_{\mathrm{sem},T}(x_2)
\Rightarrow
H_T(x_1)
=
H_T(x_2).
}
$$

### 證明

與定理 12.1 同型，將 $q$ 換成 $H_T$。$\square$

---

# 15. Phase 可以 task-sufficient 但 identity-insufficient

可能存在：

$$
H_T
=
\widehat H_T\Theta
$$

但不存在：

$$
q
=
R\Theta.
$$

也就是：

> semantic phase 足夠完成某 task，但不足以唯一恢復語義身份。

例如粗分類任務只需要知道：

- positive / negative stance；
- urgency；
- action recommendation；

並不需要完整 concept identity。

因此：

$$
\boxed{
\text{task sufficiency}
\neq
\text{identity recoverability}.
}
$$

---

# 16. Semantic Identity 可以 recoverable 但 task-insufficient

反之，也可能 phase 足以辨認：

$$
O_{\mathrm{sem}},
$$

但 task 還需要：

- provenance；
- uncertainty；
- temporal context；
- receiver-specific constraints。

所以：

$$
q
=
R\Theta
$$

不推出：

$$
H_T
=
\widehat H_T\Theta.
$$

---

# 17. Joint Identity–Phase Representation

定義：

$$
\boxed{
J:
\mathcal X_{\mathrm{sem}}
\rightarrow
\mathcal O_{\mathrm{sem}}
\times
\Phi_{\mathrm{sem}},
}
$$

$$
J(x)
=
(
q(x),
\Theta(x)
).
$$

---

## 定理 17.1 — Joint Identity–Phase Sufficiency Theorem

存在：

$$
\widehat H_T:
\mathcal O_{\mathrm{sem}}
\times
\Phi_{\mathrm{sem}}
\rightarrow
\mathcal Y_T
$$

使：

$$
\boxed{
H_T
=
\widehat H_T
\circ
J
}
$$

當且僅當：

$$
\boxed{
J(x_1)=J(x_2)
\Rightarrow
H_T(x_1)=H_T(x_2).
}
$$

證明仍為 fiber factorization。$\square$

---

# 18. 為什麼 Joint Representation 重要

這給出三種模型層級：

### Identity-only

$$
O.
$$

### Phase-only

$$
\phi.
$$

### Identity + Phase

$$
(O,\phi).
$$

可以直接做 ablation：

$$
M_O,
\quad
M_\Phi,
\quad
M_{O,\Phi}.
$$

若：

$$
M_{O,\Phi}
$$

明顯優於兩個單獨模型，代表 identity 與 phase 確實攜帶互補資訊。

---

# 19. Semantic Phase Reparameterization

phase coordinate 本身可以換表示。

令：

$$
g:
\Phi
\rightarrow
\Phi'
$$

為雙射。

定義：

$$
\Theta'
=
g\circ\Theta.
$$

---

## 定理 19.1 — Reparameterization Invariance

若 $g$ 為雙射，則：

1. semantic identity recoverability 對 $\Theta$ 與 $\Theta'$ 等價；
2. task sufficiency 對 $\Theta$ 與 $\Theta'$ 等價。

### 證明

因：

$$
\Theta'(x_1)=\Theta'(x_2)
$$

當且僅當：

$$
g\Theta(x_1)=g\Theta(x_2),
$$

由 $g$ injective：

$$
\Theta(x_1)=\Theta(x_2).
$$

故兩者 phase fibers 完全相同，只是座標重新命名。$\square$

---

# 20. 意義：Semantic Phase 的價值不應依賴座標名稱

如果只是：

$$
\phi
\mapsto
g(\phi)
$$

的 bijective reparameterization，

它不改變：

- identity recoverability；
- task sufficiency；
- phase-fiber structure。

因此：

$$
\boxed{
\text{phase mechanics}
\neq
\text{coordinate naming}.
}
$$

---

# 21. Context Transport

令 context/index base：

$$
I_{\mathrm{sem}}.
$$

每個 context：

$$
i\in I_{\mathrm{sem}}
$$

有 semantic state space：

$$
\mathcal X_i.
$$

一條 context path：

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

定義 semantic transport：

$$
\boxed{
T^\mathrm{sem}_\gamma:
\mathcal X_{i_0}
\rightarrow
\mathcal X_{i_n}.
}
$$

---

# 22. Context Transport 的三個實例

## 22.1 Translation Transport

$$
\mathrm{ZH}
\rightarrow
\mathrm{EN}
\rightarrow
\mathrm{JA}.
$$

## 22.2 Agent Transport

$$
A
\rightarrow
B
\rightarrow
C.
$$

## 22.3 Historical Context Transport

$$
t_0
\rightarrow
t_1
\rightarrow
t_2.
$$

三者數學接口相似，但 transport operator 不必相同。

---

# 23. Semantic Identity-Preserving Transport

如果：

$$
\boxed{
q_{\mathrm{sem}}
T^\mathrm{sem}_\gamma
=
q_{\mathrm{sem}},
}
$$

則 transport 保持 chosen semantic identity。

注意：

$$
\kappa
$$

必須固定或經明示 map 跨 criteria 對齊。

---

# 24. Semantic Phase Transport

定義 phase transport：

$$
\boxed{
T^\Phi_\gamma:
\Phi_{i_0}
\rightarrow
\Phi_{i_n}.
}
$$

理想：

$$
\boxed{
\Theta_{i_n}
T^\mathrm{sem}_\gamma
=
T^\Phi_\gamma
\Theta_{i_0}.
}
$$

若只近似：

$$
\boxed{
\varepsilon_{\Phi,\gamma}(x)
=
d_\Phi
\left(
\Theta_{i_n}T^\mathrm{sem}_\gamma(x),
T^\Phi_\gamma\Theta_{i_0}(x)
\right).
}
$$

---

# 25. Semantic Holonomy

令：

$$
\gamma
$$

為 closed context path：

$$
i_n=i_0.
$$

定義：

$$
\boxed{
\operatorname{Hol}^{\mathrm{sem}}_\gamma
=
T^\mathrm{sem}_\gamma.
}
$$

若：

$$
q_{\mathrm{sem}}
\operatorname{Hol}^{\mathrm{sem}}_\gamma(x)
=
q_{\mathrm{sem}}(x),
$$

但：

$$
\operatorname{Hol}^{\mathrm{sem}}_\gamma(x)
\neq
x,
$$

則存在：

$$
\boxed{
\text{Semantic Holonomy}.
}
$$

分類：

$$
\boxed{
PH\text{-}5
\times
IF\text{-}2.
}
$$

---

# 26. Semantic Holonomy Defect

定義：

$$
\boxed{
\mathfrak C_\gamma^{\mathrm{sem}}(x)
=
\Delta_{\mathrm{sem}}
\left(
x,
\operatorname{Hol}_\gamma^{\mathrm{sem}}(x)
\right).
}
$$

typed form：

$$
\boxed{
\mathbf C_\gamma
=
(
C_{\mathrm{den}},
C_{\mathrm{inf}},
C_{\mathrm{prag}},
C_{\mathrm{aff}},
C_{\mathrm{act}},
C_{\mathrm{unc}}
).
}
$$

所以 round-trip「大致還是同一句意思」不代表 holonomy 為零。

---

# 27. Translation Round-Trip Example

$$
\gamma:
\mathrm{ZH}
\rightarrow
\mathrm{EN}
\rightarrow
\mathrm{JA}
\rightarrow
\mathrm{ZH}.
$$

可能：

$$
q_{\kappa_P}
(
T_\gamma x
)
=
q_{\kappa_P}(x),
$$

但：

$$
C_{\mathrm{prag}}>0,
$$

$$
C_{\mathrm{aff}}>0.
$$

即 proposition identity 保留，但 pragmatic / affective phase 沒回原點。

---

# 28. Zero-Holonomy Theorem under Global Semantic Trivialization

## 定理 28.1

假設每個 context $i$ 的 semantic state space $\mathcal X_i$ 都存在到共同 global semantic space $\mathcal S$ 的雙射：

$$
\psi_i:
\mathcal X_i
\rightarrow
\mathcal S,
$$

且 transport 定義為：

$$
\boxed{
T_{i\rightarrow j}
=
\psi_j^{-1}
\circ
\psi_i.
}
$$

則任意 closed path：

$$
\gamma:
i_0
\rightarrow
i_1
\rightarrow
\cdots
\rightarrow
i_n=i_0
$$

皆有：

$$
\boxed{
T_\gamma
=
\operatorname{id}_{\mathcal X_{i_0}}.
}
$$

### 證明

展開：

$$
T_\gamma
=
\psi_{i_0}^{-1}
\psi_{i_{n-1}}
\cdots
\psi_{i_2}^{-1}
\psi_{i_1}
\psi_{i_1}^{-1}
\psi_{i_0}.
$$

所有中間 maps 成對消去，得到：

$$
T_\gamma
=
\psi_{i_0}^{-1}\psi_{i_0}
=
\operatorname{id}.
\qquad\square
$$

---

# 29. Nonzero Semantic Holonomy 的意義

若實驗中穩定觀察到：

$$
\mathfrak C_\gamma^{\mathrm{sem}}>0,
$$

至少表示下列一項成立：

1. 不存在上述 global exact trivialization；
2. transport 不是單純 path-independent coordinate change；
3. decoder / translator / agent maps 非互逆；
4. transport 帶噪聲；
5. context 會真正改寫 semantic state；
6. system 具有 memory / path dependence；
7. chosen identity criterion 太粗，使 phase residual 被留在同一 fiber 中。

所以：

$$
\boxed{
\text{nonzero semantic holonomy}
\neq
\text{proof of mysterious semantic field}.
}
$$

它首先是 transport nontriviality 的診斷量。

---

# 30. Holonomy 與單次 Endpoint Difference 不同

如果只比較：

$$
x_0,
x_1,
$$

只能得到：

$$
\Delta(x_0,x_1).
$$

要談 holonomy，必須有：

$$
\boxed{
\text{closed path}
+
\text{composable transport}
+
\text{same base endpoint}.
}
$$

因此：

$$
\boxed{
\text{semantic drift}
\not\Rightarrow
\text{semantic holonomy}.
}
$$

---

# 31. Semantic Identity Split

如果：

$$
q_{\mathrm{sem},\kappa'}
(
T_\gamma x
)
\neq
q_{\mathrm{sem},\kappa}(x),
$$

不能稱 same-identity semantic holonomy。

應引入 semantic lineage：

$$
\boxed{
q_{\mathrm{sem},\kappa'}
T_\gamma
=
L_{\mathrm{sem}}
q_{\mathrm{sem},\kappa}
}
$$

若 factorization 成立。

這是：

$$
\boxed{
PH\text{-}5
\times
IF\text{-}4.
}
$$

---

# 32. Semantic Lineage Factorization

由 IPFC Paper 01 的 Lineage Factorization Theorem：

semantic lineage：

$$
L_{\mathrm{sem}}
$$

存在且唯一，當且僅當：

$$
q_{\mathrm{old}}(x_1)
=
q_{\mathrm{old}}(x_2)
$$

推出：

$$
q_{\mathrm{new}}
(
\Gamma x_1
)
=
q_{\mathrm{new}}
(
\Gamma x_2
).
$$

若同一舊 sense fiber 中不同 usages 會分裂成不同 downstream senses，則單值：

$$
L_{\mathrm{sem}}
:
O_{\mathrm{old}}
\rightarrow
O_{\mathrm{new}}
$$

不存在。

此時需要：

- relation-valued lineage；
- branching lineage graph；
- stochastic transition kernel。

---

# 33. Branching Semantic Lineage

若一個舊 sense：

$$
O
$$

分裂成：

$$
O_1',
O_2',
$$

更自然寫：

$$
\boxed{
L_{\mathrm{sem}}(O)
=
\{
O_1',
O_2'
\}
}
$$

或 probabilistic：

$$
\boxed{
K(
O'
\mid
O
).
}
$$

這比強迫單值 lineage 更適合 diachronic semantic change。

---

# 34. 與現代 Lexical Semantic Change 的接口

現代 LSCD 常把問題拆成：

1. usage-level similarity / Word-in-Context；
2. sense induction；
3. sense distribution / cluster comparison across time。

這與本文三層：

$$
\boxed{
\text{semantic state}
\rightarrow
\text{semantic identity}
\rightarrow
\text{phase / lineage dynamics}
}
$$

可以自然對接。

但本文不主張現有 LSCD 已經等同 IPFC。

IPFC 另外要求：

- identity criterion 明示；
- phase role 明示；
- transport 若存在則可組合；
- identity split 與 phase drift 分開。

---

# 35. Contextual Embedding Guard

contextual embeddings：

$$
z(e,c)
$$

可以是 semantic state representation 的一部分。

但：

$$
\boxed{
\Delta z
\neq
\text{semantic identity change}.
}
$$

因為 representation 可能對：

- syntax；
- topic；
- register；
- local context variance；

敏感。

所以：

$$
\boxed{
\text{embedding drift}
\rightarrow
\text{candidate state drift},
}
$$

不是：

$$
\boxed{
\text{automatic sense split}.
}
$$

---

# 36. GPC Semantic Communication

Sender intended semantic state：

$$
x_A.
$$

Receiver reconstruction：

$$
\hat x_B.
$$

GPC：

$$
\boxed{
\hat x_B
=
D_B
\left(
T_{AB}
(
E_A(x_A)
),
b_B,c
\right).
}
$$

---

# 37. Communication Success Level S0 — Identity Success

跨語言／跨 agent identity map：

$$
F_O:
\mathcal O_A
\rightarrow
\mathcal O_B.
$$

成功條件：

$$
\boxed{
F_Oq_A(x_A)
=
q_B(\hat x_B).
}
$$

這表示：

> receiver reconstructed 的是同一 chosen semantic identity。

---

# 38. Communication Success Level S1 — Phase Alignment

phase map：

$$
F_\Phi:
\Phi_A
\rightarrow
\Phi_B.
$$

定義：

$$
\boxed{
D_{\Phi,T}
=
d_\Phi
\left(
F_\Phi\Theta_A(x_A),
\Theta_B(\hat x_B)
\right).
}
$$

若：

$$
D_{\Phi,T}
\le
\varepsilon_T,
$$

則 phase-aligned。

---

# 39. Communication Success Level S2 — Functional Success

task observable：

$$
H_T.
$$

要求：

$$
\boxed{
d_Y
\left(
H_T^A(x_A),
H_T^B(\hat x_B)
\right)
\le
\delta_T.
}
$$

所以：

$$
\boxed{
\text{semantic communication success}
=
\text{identity}
+
\text{phase}
+
\text{function}.
}
$$

---

# 40. 三層成功彼此不等價

可能：

### Identity 成功，Phase 失敗

proposition 對，但 sarcasm / urgency / social force 失真。

### Phase 近似，Identity 失敗

兩個相關概念很接近，但 receiver 抓錯 sense。

### Identity + Phase 成功，Function 失敗

receiver 理解對了，但因外部 knowledge / capability 不足執行錯。

因此：

$$
\boxed{
S0
\not\Rightarrow
S1
\not\Rightarrow
S2.
}
$$

它們是不同驗證層。

---

# 41. Semantic Communication 與 Semantic Communication Engineering

現代 semantic communication 已經把：

- bit/symbol fidelity；
- semantic reconstruction；
- receiver task performance；

分開處理。

IPFC Paper 02 的補充是：

> semantic reconstruction 本身仍應拆成 identity、phase 與 function。

所以 DeepSC 類系統可作工程先例，但不等於已實現本文的 semantic identity fibers 或 holonomy。

---

# 42. Semantic Holonomy Benchmark 1 — Translation Loop

路徑：

$$
L_0
\rightarrow
L_1
\rightarrow
\cdots
\rightarrow
L_0.
$$

記錄：

- S0 identity preservation；
- phase residual vector；
- task success；
- path order。

比較：

$$
\gamma_1,
\gamma_2
$$

若：

$$
\mathbf C_{\gamma_1}
\neq
\mathbf C_{\gamma_2},
$$

則有 path-order dependence 候選。

---

# 43. Benchmark 2 — Multi-Agent Loop

$$
A
\rightarrow
B
\rightarrow
C
\rightarrow
A.
$$

每個 agent 使用：

- 相同／不同模型；
- 相同／不同 memory；
- 相同／不同 ontology；
- 相同／不同 system prompt。

測：

$$
\boxed{
\mathfrak C_{A\to B\to C\to A}^{\mathrm{sem}}.
}
$$

這是 Semantic Holonomy 最直接的 AI 實驗之一。

---

# 44. Benchmark 3 — Diachronic Phase Drift vs Identity Split

對 word/sense：

$$
w
$$

與時間：

$$
t_0<t_1<t_2,
$$

先做 usage-level semantic states：

$$
x_{w,u,t}.
$$

再建立 sense identity classes：

$$
q_{\kappa_S}.
$$

若 sense identity 保留但 distribution / connotation / pragmatic relation 改變：

$$
\boxed{
IF\text{-}1 / IF\text{-}2.
}
$$

若 sense class 真正分裂／新生：

$$
\boxed{
IF\text{-}4.
}
$$

---

# 45. Benchmark 4 — Ontology Migration Round Trip

ontology versions：

$$
V_1
\rightarrow
V_2
\rightarrow
V_3
\rightarrow
V_1.
$$

如果 entity identity 保留但 relations 改變：

$$
\text{semantic holonomy}.
$$

如果 entity 被 split / merge：

$$
\text{lineage transition}.
$$

這對 knowledge graph / schema evolution 很重要。

---

# 46. Benchmark 5 — Paraphrase Identity / Phase

兩個 expressions：

$$
e_1,e_2
$$

若：

$$
q_{\kappa_P}
(
S(e_1)
)
=
q_{\kappa_P}
(
S(e_2)
),
$$

但：

$$
\Delta\Phi_{\mathrm{prag}}
\neq0,
$$

代表：

> proposition paraphrase 成功，但 pragmatic phase 不同。

這可把傳統 paraphrase binary label 擴成 typed semantic relation evaluation。

---

# 47. Path Order 與 Noncommutativity

若兩種 context transformations：

$$
T_A,
T_B
$$

滿足：

$$
\boxed{
T_AT_B
\neq
T_BT_A,
}
$$

則 semantic transport 具有 order effect。

例如：

- 先 legal framing 再 emotional framing；
- 先 machine translation 再 summarization；
- 先 ontology normalization 再 compression；

可能和反向順序不同。

這是 generalized noncommutative transport。

但除非另有 group/connection structure，不應直接稱 non-Abelian gauge phase。

---

# 48. Semantic Curvature Interface

若有大量 closed context loops：

$$
\gamma,
$$

可把：

$$
\mathfrak C_\gamma^{\mathrm{sem}}
$$

視為 semantic transport curvature 的候選 observables。

但本文只建立接口，不定義唯一 semantic curvature tensor。

未來至少可研究：

1. loop residual norm；
2. path-order defect；
3. local small-loop scaling；
4. context graph cycle inconsistency；
5. projection-resolution-dependent residual。

---

# 49. 相位語義的 PAC

本文 phase module：

$$
\boxed{
\mathfrak M_{\mathrm{SemPhase}}
}
$$

填入 IPFC Phase Attachment Contract：

| 欄位 | 本文定義 |
|---|---|
| Domain | semantics / communication / NLP |
| Identity criterion | $\kappa_L,\kappa_S,\kappa_C,\kappa_P,\kappa_R,\kappa_I$ |
| State space | $\mathcal X_{\mathrm{sem}}$ |
| Identity projection | $q_{\mathrm{sem},\kappa}$ |
| Context/index | $I_{\mathrm{sem}}$ |
| Phase Canon type | PH-5 |
| IPFC role | IF-1/2/3/4 |
| Phase space | typed relational $\Phi_{\mathrm{sem},T}$ |
| Phase extractor | $\Theta_{\mathrm{sem},T}$ |
| Transport | $T_\gamma^{\mathrm{sem}}$ |
| Observable | $H_T$ |
| Lineage | $L_{\mathrm{sem}}$ 或 branching kernel |
| Physical realization | 不預設 |
| Falsification | identity/phase/transport/benchmark failures |

---

# 50. 相位語義的拒絕條件

## F1 — Renaming Only

如果：

$$
\Theta(x)
$$

只是普通 embedding 改名字，沒有 typed relational effect：

撤回 phase-mechanics claim。

## F2 — Identity Criterion Missing

如果不知道是在追蹤 sense、concept、proposition 還是 intent：

semantic identity claim 不成立。

## F3 — Holonomy Without Transport

沒有 composable context transport：

不得稱 Semantic Holonomy。

## F4 — Embedding Drift = Sense Split

若只看到：

$$
\Delta z>0
$$

就宣布新 sense：

拒絕。

## F5 — Phase Sufficiency Fails

若：

$$
\Theta(x_1)=\Theta(x_2)
$$

但 task output 常不同：

phase 對該 task 不充分。

## F6 — Identity Recoverability Fails

若 phase fiber 包含多個 identity classes：

不能宣稱 phase 等於完整 meaning identity。

---

# 51. 外部實證錨點：Lexical Semantic Change

Hamilton–Leskovec–Jurafsky 2016 以 diachronic embeddings 研究詞義隨時間變化，證明 distributional representation 可以捕捉大量 diachronic semantic structure。

Giulianelli–Del Tredici–Fernández 2020 使用 contextualized word representations 與 usage clustering 分析 lexical semantic change，將 word usages 分群並與 human judgments 比較。

DWUG 2021 建立大規模 diachronic word usage graph，使用十萬級 human semantic proximity judgments。

SemEval-2020 Task 1 與 2026 LSCD Benchmark 則把 lexical semantic change 拆成 usage-level、sense induction 與 diachronic comparison 的模組化評估。

本文將這些視為：

> semantic state / semantic identity / diachronic change 可被操作化

的證據基礎。

它們不證明 Semantic Holonomy 已存在。

---

# 52. Contextual Embedding 的限制正好支持 IPFC 分型

後續研究指出 contextualized embedding-based semantic change detector 可能把：

- lexicographic sense change；
- contextual variance；
- syntax/context distribution shift；

混在一起。

所以：

$$
\boxed{
\text{representation drift}
\neq
\text{identity-lineage transition}.
}
$$

這正是本文 insist on：

$$
q_{\mathrm{sem}}
$$

與：

$$
\Theta_{\mathrm{sem}}
$$

分離的理由之一。

---

# 53. Translation / Round-Trip 的實證接口

現代 machine translation research 已重新使用 round-trip translation 作：

- quality estimation；
- semantic preservation checks；
- adversarial verification。

而 semantic-level embedding metrics 通常比純表面 BLEU 更適合 round-trip semantic comparison。

本文將 round-trip translation 提升成：

$$
\boxed{
\text{closed context transport benchmark}
}
$$

但不宣稱所有 RTT residual 都是 intrinsic semantic holonomy。

它可能來自：

- translator error；
- noninvertible paraphrase；
- model asymmetry；
- representation noise；
- identity split；
- path dependence。

---

# 54. Semantic Phase 與一般 Semantic Similarity 的差異

普通 semantic similarity：

$$
s(x,y)
$$

通常只回答：

> 兩者多接近？

IPFC Semantic Phase 額外要求：

1. identity criterion；
2. typed phase dimensions；
3. context/reference/receiver/task；
4. transport；
5. optional path/holonomy；
6. lineage when identity changes；
7. task sufficiency tests。

所以：

$$
\boxed{
\text{semantic phase}
\supsetneq
\text{one-shot similarity score}
}
$$

在設計目標上成立。

但是否工程上真的提供增益，仍需 benchmark。

---

# 55. Phase Necessity Ablation

建立四個模型：

### $M_0$ — surface / token baseline

### $M_1$ — embedding similarity baseline

### $M_2$ — typed semantic state baseline

使用相同：

- denotational；
- pragmatic；
- affective；
- uncertainty；

features，但不建 transport/holonomy。

### $M_\phi$ — full semantic phase model

加入：

- phase extractor；
- context transport；
- loop residual；
- lineage classification。

真正 semantic-phase algorithmic gain：

$$
\boxed{
\Delta S_\phi
=
S(M_\phi)
-
S(M_2).
}
$$

若：

$$
\Delta S_\phi\approx0,
$$

相位語義仍可作解釋框架，但不能宣稱 phase mechanics 有額外計算價值。

---

# 56. 最小可實驗原型

Paper 02 最小 MVP 不需要訓練新 LLM。

可以直接使用：

1. 多語翻譯模型或多個 LLM；
2. semantic identity evaluator；
3. typed phase scorer；
4. context path generator；
5. round-trip loop；
6. human / model-assisted annotation。

輸出：

$$
\boxed{
(
S0,
\mathbf C_\gamma,
S2,
\text{lineage flag}
).
}
$$

---

# 57. 資料格式建議

每個 semantic transport event：

```json
{
  "source_identity_criterion": "proposition",
  "source_expression": "...",
  "source_context": "...",
  "path": ["zh", "en", "ja", "zh"],
  "identity_preserved": true,
  "phase_residual": {
    "denotational": 0.03,
    "inferential": 0.07,
    "pragmatic": 0.31,
    "affective": 0.26,
    "action": 0.04,
    "uncertainty": 0.11
  },
  "functional_success": true,
  "lineage_transition": false
}
```

數字必須由實際 metric / annotator/model output 產生，不能人工杜撰。

---

# 58. 對「相位語義」舊說法的正式修正

撤回：

$$
\boxed{
\text{Meaning}
=
\text{Phase}.
}
$$

改成：

$$
\boxed{
\text{Meaning state}
\xrightarrow{
q_{\mathrm{sem}}
}
\text{Semantic identity}
}
$$

以及：

$$
\boxed{
\text{Meaning state}
\xrightarrow{
\Theta_{\mathrm{sem}}
}
\text{Relational semantic phase}.
}
$$

所以相位語義不是 meaning ontology。

它是：

$$
\boxed{
\text{identity-aware relational semantics}.
}
$$

---

# 59. 與「相位交流」舊系列的關係

早期相位交流的重要直覺是：

> surface symbol equality 並不足以保證 sender / receiver meaning equality。

這保留。

但 direct concept address = concept identity 已被 GPC / Phase Canon audit 修正。

Paper 02 的現行結構：

$$
\boxed{
\text{stable semantic identity}
+
\text{typed semantic phase}
+
\text{receiver reconstruction}
+
\text{functional validation}.
}
$$

---

# 60. 與未來其他「XX 相位」的模板關係

相位語義是 IPFC 第一個 domain stress test。

若此模組成立，以後：

- 認知相位；
- 法律相位；
- 經濟相位；
- 科學認識論相位；
- AI phase；

都不能只定義：

$$
x\mapsto\phi_x.
$$

而必須回答：

1. identity criterion？
2. state space？
3. PH type？
4. IF role？
5. phase space？
6. transport？
7. observable？
8. lineage？
9. physical map？
10. falsification？

---

# 61. 理論地位

本文中：

## 已證明的形式結果

- Semantic Identity Recoverability Theorem；
- Semantic Task Sufficiency Theorem；
- Joint Identity–Phase Sufficiency Theorem；
- Reparameterization Invariance；
- Zero-Holonomy Theorem under Global Semantic Trivialization。

## 由上游 IPFC 繼承

- Lineage Factorization；
- identity-preserving transport；
- holonomy / lineage distinction；
- Phase Module Morphism。

## 外部研究支持的是可操作性

- diachronic semantic change 可量測；
- usage/sense structure可標註；
- translation semantic preservation可評估；
- semantic communication可工程化。

## 尚未被外部文獻直接證明

- Semantic Holonomy 作為統一理論量；
- PH-5 semantic phase 的 algorithmic necessity；
- semantic curvature；
- universal semantic transport geometry。

---

# 62. 結論

本文將「相位語義」從一個容易過度延展的跨域概念，重建為 IPFC 中的一個 typed domain module。

核心不再是：

$$
\boxed{
\text{語義就是相位}.
}
$$

而是：

$$
\boxed{
\text{Semantic Identity}
\neq
\text{Semantic State}
\neq
\text{Semantic Phase}.
}
$$

semantic identity 由：

$$
q_{\mathrm{sem},\kappa}
$$

判定。

semantic phase 由：

$$
\Theta_{\mathrm{sem},T}
$$

提供 relational coordinate。

context path 由：

$$
T_\gamma^{\mathrm{sem}}
$$

傳輸。

closed loop 中若：

$$
q_{\mathrm{sem}}T_\gamma(x)
=
q_{\mathrm{sem}}(x)
$$

但：

$$
T_\gamma(x)\neq x,
$$

才有資格談：

$$
\boxed{
\text{Semantic Holonomy}.
}
$$

若 identity 真正改變，則進：

$$
\boxed{
\text{Semantic Lineage}.
}
$$

因此相位語義的成熟版本可濃縮為：

> **語義身份回答「還是不是同一意思」；語義相位回答「這個意思在目前語境、接收者、參照與任務下處於什麼關係位置」；Semantic Holonomy 回答「沿一圈語境傳輸後，同一意思留下了多少不可消去的關係殘差」；Semantic Lineage 則回答「何時它已經不再只是同一意思的變化」。**

這使相位語義可以同時接入：

- NLP；
- translation；
- diachronic semantics；
- ontology alignment；
- multi-agent communication；
- GPC-CS；
- AI semantic memory；

而不需要把任何 generalized semantic structure 誤稱為 physical phase。

---

# 63. 後續

## IPFC Paper 03
**《相變與同一性分岔：Identity-Preserving Regime Change 與 Lineage Transition》**

## Semantic Phase Experiment 01
**Translation / Multi-Agent Semantic Holonomy Benchmark**

## Semantic Phase Experiment 02
**Diachronic Phase Drift vs Sense Identity Split**

## Semantic Phase Experiment 03
**Ontology Migration Round-Trip Defect**

---

# 參考文獻

1. Neo.K & Aletheia. *同一性–相位纖維微積分：從身份投影、索引 Holonomy 到相位動力學的統一接口*. IPFC Paper 01, EveMissLab, 2026.
2. Hamilton, W. L., Leskovec, J., & Jurafsky, D. “Diachronic Word Embeddings Reveal Statistical Laws of Semantic Change.” ACL 2016. DOI: 10.18653/v1/P16-1141.
3. Giulianelli, M., Del Tredici, M., & Fernández, R. “Analysing Lexical Semantic Change with Contextualised Word Representations.” ACL 2020. DOI: 10.18653/v1/2020.acl-main.365.
4. Schlechtweg, D., McGillivray, B., Hengchen, S., Dubossarsky, H., & Tahmasebi, N. “SemEval-2020 Task 1: Unsupervised Lexical Semantic Change Detection.” SemEval 2020. DOI: 10.18653/v1/2020.semeval-1.1.
5. Schlechtweg, D., Tahmasebi, N., Hengchen, S., Dubossarsky, H., & McGillivray, B. “DWUG: A large Resource of Diachronic Word Usage Graphs in Four Languages.” EMNLP 2021. DOI: 10.18653/v1/2021.emnlp-main.567.
6. Kutuzov, A., Velldal, E., & Øvrelid, L. “Contextualized embeddings for semantic change detection: Lessons learned.” Northern European Journal of Language Technology 8, 2022. DOI: 10.3384/nejlt.2000-1533.2022.3478.
7. Schlechtweg, D., Yadav, S., Kuhn, J., & Arefyev, N. “The LSCD Benchmark: a Testbed for Diachronic Word Meaning Tasks.” *SEM 2026. DOI: 10.18653/v1/2026.starsem-conference.10.
8. Moon, J., Cho, H., & Park, E. L. “Revisiting Round-trip Translation for Quality Estimation.” EAMT 2020.
9. Zhuo, T. Y., Xu, Q., He, X., & Cohn, T. “Rethinking Round-Trip Translation for Machine Translation Evaluation.” Findings of ACL 2023. DOI: 10.18653/v1/2023.findings-acl.22.
10. Song, Y., Zhao, J., & Specia, L. “SentSim: Crosslingual Semantic Evaluation of Machine Translation.” NAACL 2021. DOI: 10.18653/v1/2021.naacl-main.252.
11. Xie, H., Qin, Z., Li, G. Y., & Juang, B.-H. “Deep Learning Enabled Semantic Communication Systems.” arXiv:2006.10685, 2020.
12. EveMissLab. *Phase Canon v1.1*. 2026.
13. EveMissLab. *GPC-CS Papers 00–10*. 2026.

---

**IPFC Paper 02 v1.0 — COMPLETE.**
