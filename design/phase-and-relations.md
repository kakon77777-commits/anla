# Relations and phase: what the theory permits ANLA to build

Two pieces of the context layer have been reserved and empty since they were
written: `SegmentIndex.edges`, and the phase channel that `context_find` reports as
`ABSENT`. Neo named 相位 as the mechanism months ago; I declined to implement it,
on the grounds that 相變 and 相位 are different words and I was not going to treat
one as the other.

The IPFC series now says precisely what would have to hold. Read against it, the
useful result is **negative first**: most of what ANLA could easily do here would be
forbidden, and the reason it would be forbidden is worth more than the feature.

Sources in [`docs/theory/`](../docs/theory/). Section numbers below are Paper 02's
unless stated.

---

## 1. The distinction the whole thing rests on

$$\text{Expression} \neq \text{Semantic State} \neq \text{Semantic Identity} \neq \text{Semantic Phase}$$

Mapped onto what ANLA already has:

| IPFC | ANLA today |
|---|---|
| Expression | the turn's raw bytes in the preservation plane |
| Semantic State | the projected view `π_σ(m)` — text, after unescaping |
| Semantic Identity | **not represented.** `source_digest` is byte identity, which is closest to lexeme identity $\kappa_L$ and answers a different question |
| Semantic Phase | **not represented, and must not be claimed** — see §3 |

That table is the finding. ANLA has an expression layer and a state layer, one
identity criterion that is not a semantic one, and no phase.

---

## 2. What ANLA is allowed to build: relations

Relation edges are not phase. Under the Canon they are the **context/index base**
$I_{\mathrm{sem}}$ — the graph a transport would later be defined *over*. Building
them claims nothing about phase, so the reserved list stands:

    same-turn · adjacency · tool-call/result · quote/reference · same-file
    supersedes/supports/contradicts

Two constraints the papers impose on how they are built:

**Typed, not scalar.** Paper 02 §8 refuses a single angle: the phase space is a
typed product $\Phi_{\mathrm{den}} \times \Phi_{\mathrm{inf}} \times
\Phi_{\mathrm{prag}} \times \Phi_{\mathrm{aff}} \times \Phi_{\mathrm{act}} \times
\Phi_{\mathrm{unc}}$, and §9 is explicit that a scalarization is a task choice made
*after*, never the thing itself:

$$D_T \neq \Delta\Phi_{\mathrm{sem},T}$$

ANLA's cosine score is exactly such a scalarization. An edge carrying one number
would repeat the same collapse one level up. Edges should carry a *kind*, and a
kind is not a weight.

**Composable, or the word transport is unavailable.** §30: a closed path, a
composable transport and the same base endpoint are all three required before
anything may be called holonomy. `supersedes` between two turns is an edge; it is
not transport until there is a composition law saying what two of them do.

---

## 3. What ANLA is forbidden to claim: phase

Paper 02 §50 lists six rejection conditions. Four of them would fire on the obvious
implementation — the one where we call the existing vectors "phase" and ship it.

**F1 — Renaming Only.** If $\Theta(x)$ is an ordinary embedding with no typed
relational effect, the phase-mechanics claim is withdrawn. ANLA's vectors are
`nomic-embed-text` over a projected view. Labelling them phase would be renaming and
nothing else.

**F2 — Identity Criterion Missing.** Without saying whether we track sense, concept,
proposition or intent, there is no semantic identity claim to make. ANLA currently
tracks *byte* identity, deliberately, and has never claimed a semantic one.

**F4 — Embedding Drift = Sense Split.** §35 is the sharpest sentence for us:

> $\Delta z \neq$ semantic identity change … embedding drift → **candidate** state
> drift, not automatic sense split.

ANLA already refuses to compare vectors across models with `INCOMPARABLE` rather
than returning a confident number. That refusal is the same instinct, and this is
the argument for it in general form.

**F3 — Holonomy Without Transport.** No composable context transport, no holonomy.
ANLA has none.

The remaining two (F5 task-sufficiency, F6 identity-recoverability) are the
*measurements* that would decide whether a real phase channel earned anything —
Theorems 12.1, 14.1 and 17.1 give them as fiber-constancy tests, and §55 gives the
ablation: $\Delta S_\phi = S(M_\phi) - S(M_2)$. If that is about zero, phase remains
an explanatory frame and may not be sold as computational gain.

**Also excluded, and easy to get wrong:** Canon v1.2 §3.1 rules out linear process
stages — a snapshot sequence, an append chain, a version history. ANLA has all
three and none of them is phase.

---

## 4. The checklist, if it is ever built

Paper 02 §49 fills the Phase Attachment Contract for its own module. Any ANLA phase
channel would have to fill the same thirteen fields, and the interesting thing is
how many are currently blank:

| field | what ANLA would have to say |
|---|---|
| Domain | conversational memory / retrieval |
| Identity criterion | **blank** — byte identity is not one of $\kappa_{L,S,C,P,R,I}$ |
| State space | the projected view |
| Identity projection | **blank** |
| Context/index | the relation graph of §2, once it exists |
| Phase Canon type | PH-5 if anything — relational, and explicitly *not* $S^1$ |
| IPFC role | IF-1…IF-4 depending on what is being asked |
| Phase space | typed, per §8 |
| Phase extractor | **blank** |
| Transport | **blank** — and this is the one that gates the word holonomy |
| Observable | retrieval quality, which we already measure |
| Lineage | branching, per §33: re-segmentation splits one view into many |
| Physical realization | none, and none should be asserted |
| Falsification | F1–F6 above |

Six of thirteen are blank. That is the honest state of the phase channel, and it is
why `ABSENT` is the correct value rather than a placeholder.

---

## 5. What this changes about work already done

**It does not retract anything.** The `INCOMPARABLE` rule, the `ABSENT` channels and
the refusal to call segmentation a phase transition all turn out to be what the
canon requires. That is a check passing, not a discovery.

**It renames one thing.** `edges` is a context/index base, not a relation *phase*.
The docstring calls them relations, which is right; nothing there should acquire the
word phase.

**It supplies one measurement we do not have.** §55's ablation is the honest test of
whether any of this earns its complexity: build $M_2$ (typed features, no transport)
and $M_\phi$ (transport, loop residual, lineage) and subtract. ANLA's benchmark
already has the shape for this — labelled queries, one pinned corpus, a control row
— so the harness exists.

**It gives the read contract a second author.** `ACCR_MCP_ANLA_Contracts_v0.1.md`
specifies a governed runtime above ANLA and names the tools it needs:
`context_status`, `context_project`, `context_find`, `context_address`,
`context_expand`, `anla_verify`, `anla_snapshots`, `anla_diff`, `anla_manifest` —
all of which exist. It also states a rule ANLA already enforces and should keep
enforcing under someone else's name:

> Returned bytes are accepted as authoritative only after expected digest
> verification when a digest is available … If no verified replica is available, do
> not silently regenerate authoritative source; return `source_unavailable`.

And it names the gap accurately: there is no MCP *writer* lifecycle. ANLA's writing
tools exist but are withdrawn under `--share`, which is the same observation from
the other side.

---

## 6. The order this implies

1. ~~**Relation edges, typed, no phase vocabulary.**~~ **Built** —
   `python/anla1/relations.py`, 9,050 edges over the pinned corpus, three derivable
   kinds and six named-but-not-stored with the reason each is absent.
2. ~~**Measure whether they help.**~~ **Measured, and the answer is mostly no** —
   [`relation-edges-measured.md`](relation-edges-measured.md).

   90.6% of `replies-to` edges connect turns that are already adjacent, and the tenth
   that do not score **+0.089 against adjacency's +0.185** — half of what conversation
   order gives for free. `tool-result-of` has the same shape. Only `mentions-path` is
   a real relation: 76% long-range, reaching 5,103 turns, and still 2.42× adjacency
   when its adjacent edges are excluded.

   On retrieval the graph moves three of twelve queries — two up, one down, net +1 at
   R@1, MRR +0.056 where one query is 0.083. Smaller than the instrument resolves.

   So the claim above that edges are "independently useful for retrieval" was written
   before there was a measurement, and the measurement does not support it in general.
   It supports it for one kind of the three. The consequence for the layer is that
   `mentions-path` is the semantic relation and the other two are navigation, which is
   a distinction the index base should carry rather than a reason to delete them.
3. **Transport only if a composition law is written down** — and then holonomy is
   available as a word, and Theorem 28.1 says a zero result is the *expected* one
   under a global trivialization, so a non-zero result needs the seven-way
   disambiguation of §29 before it means anything.
4. **Phase last, or never.** It needs six blank fields filled and an ablation that
   beats the typed-features baseline. Until then `ABSENT` is not a placeholder, it is
   the measurement.
