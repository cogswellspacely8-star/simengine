# SimEngine Review History & Decision Trail

This directory contains every peer review, critique, and adversarial analysis
performed on the SimEngine system and its accompanying paper. These documents
are the decision trail — they explain WHY things were built the way they were.

Anyone picking up this codebase (human, agent, or future-you) should read
the index below to understand the evolution from v1 thesis to v2 system report.

---

## Review sequence (chronological)

### 1. Sonnet 4.6 Expert Panel Review — Thesis v1
**File:** `01_sonnet_panel_review_v1.html`
**Date:** March 2026
**Format:** 8-panelist simulated review across 7 fields
**Verdict:** 4× Major Revision, 2× Conditional Accept, 2× Fundamental Concern

**Key scores (out of 10):**
- Architectural soundness: 7.5
- Claims ↔ Evidence fit: 3.8  ← this was the problem
- Scope/Ambition: 8.8
- Technical rigor: 4.4
- Empirical validation: 3.3

**Critical findings that drove the v2 rewrite:**
- No convergence diagnostics (Dr. Antonova)
- GA hyperparameters unspecified (Prof. Nakamura)
- Normal returns for investment model (Dr. Lindqvist)
- eval() sandbox security concern (Dr. Vasquez)
- "PhD-level" framing is an overclaim (Dr. Chen)
- Healthspan twin not implemented but presented as current (Dr. Bergström)
- ABM engine not built but treated as core contribution (Prof. Abramowitz)
- "Bayesian-adjacent" is a red flag phrase (Prof. Okafor)

---

### 2. ChatGPT-4o Critique — Thesis v1
**File:** `02_chatgpt4o_critique_v1.md`
**Date:** March 2026
**Format:** Single-reviewer narrative critique
**Verdict:** "Very good working paper / thesis draft, not yet a mature academic paper"

**Key findings (converged with Sonnet panel):**
- Evidence discipline is the main gap
- Validation gap: "validated against what?"
- Internal consistency: 5,000 vs 10,000 run count mismatch
- "PhD-level" and "no general-purpose system exists" are overclaims
- Needs research questions, sensitivity analysis, baseline comparison

**What made this review valuable:**
Converged independently with the Sonnet panel on the same core diagnosis.
Two different models, same conclusion = strong signal.

---

### 3. ChatGPT Deep Research — Adversarial Counterpaper
**File:** `03_chatgpt_deep_research_counterpaper.md`
**Date:** March 2026
**Format:** Full adversarial research analysis with formal problem statement
**Purpose:** "How would a rigorous academic dismantle this and rebuild it better?"

**Key contributions absorbed into v3:**
- Formal problem statement (state/controls/exogenous/observations)
  → became the v3 schema restructuring
- CVaR + chance constraints on the optimizer
  → became v3 safety evaluation layer
- Adversarial framework (4 adversary types, 3 attack scenarios)
  → became the "free lunch" test in the paper
- Two-track dataset strategy (historical + synthetic)
  → became the calibration section recommendations
- Experiment manifests for reproducibility
  → became SHA-256 config hashing in v3

**Key contributions deferred (acknowledged as future work):**
- Full Bayesian posterior inference
- Distributionally robust optimization
- Proper scoring rule evaluation
- Full Sobol sensitivity decomposition

---

### 4. Sonnet 4.6 Expert Panel Review — System Report v2
**File:** `04_sonnet_panel_review_v2.html`
**Date:** March 2026
**Format:** 8-panelist delta assessment (v1 → v2 comparison)
**Verdict:** 5× Accept/Conditional Accept, 2× Minor Revision, 1× Outstanding Item

**Key scores (out of 10, with delta from v1):**
- Architectural soundness: 8.5 (+1.0)
- Claims ↔ Evidence fit: 8.5 (+4.7)  ← biggest single-revision jump
- Technical rigor: 7.4 (+3.0)
- Empirical validation: 6.3 (+3.0)
- Reproducibility: 8.8 (+3.3)

**Resolution status:**
- 16 of 18 major v1 concerns resolved
- 2 partial resolutions with clear roadmaps (eval() security, independence assumption)

**Remaining minor items (copy-edit level):**
- Percentile convergence footnote
- Deterministic baseline attribution clarification
- Inflation haircut estimate on investment model
- 15% ruin threshold justification
- Gen-0 fitness variance report
- AST evaluator elevated to hard requirement
- PRNG quality paragraph
- One French Data Library calibration spot-check

**Recommended submission venues:**
- Primary: INFORMS Analytics Magazine
- Secondary: ACM CHI Workshop, IEEE Software
- Future: Journal of Simulation (after Bayesian updates + historical calibration)

---

## How to use these reviews

**If you're modifying the kernel:** Read reviews 1 and 3. They document the
architectural weaknesses that drove the v3 redesign.

**If you're writing about the system:** Read review 4. It tells you exactly
what claims the evidence supports and where the gaps are.

**If you're building new features:** Check the "deferred" items in review 3.
Those are the prioritized next steps with academic justification for why they matter.

**If you're reviewing someone else's critique:** The full chain (v1 critique →
counterpaper → v2 review) shows how each round of feedback was absorbed. Use
the same pattern: identify specific claims, test them, fix or defer honestly.

---

## The meta-lesson

This review process itself demonstrates the system's core principle:
when uncertain, simulate rather than guess. We "simulated" peer review by
running the paper through multiple independent evaluators, measured the
distribution of critiques, identified the convergent signals, and iterated.
The result: Claims ↔ Evidence fit went from 3.8 to 8.5 in one revision cycle.
