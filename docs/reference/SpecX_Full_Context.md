# SpecX — Complete Project Context

**Verified Website-to-WebMCP Conversion, Sandboxed Agent Testing and Safety-Preserving Optimisation**

Compiled: 17 August 2026 · AI Course Project · VIT (SCOPE) · Guide: Dr. Yoganand S (CFAIR)

This document consolidates everything from the working session: the original submitted brief, the reviewer's provisional acceptance and eight suggested enhancements, the deep prior-art/novelty analysis used to select four of them, the full content of the generated project draft PDF, and the build notes for reproducing that PDF.

---

## Table of Contents

1. [Original Project Submission](#1-original-project-submission)
2. [Reviewer Feedback & The Eight Suggestions](#2-reviewer-feedback--the-eight-suggestions)
3. [Deep Novelty & Prior-Art Analysis](#3-deep-novelty--prior-art-analysis)
4. [Project Draft — Full Content](#4-project-draft--full-content)
5. [PDF Build Notes](#5-pdf-build-notes)
6. [Open Action Items](#6-open-action-items)

---

# 1. Original Project Submission

## Brief Abstract

WebMCP lets web applications expose structured, machine-readable tools to AI agents, but generated tools may invoke the wrong action, cause unapproved side effects, or be difficult for agents to select. SpecX is a developer platform that converts developer-authorised websites into WebMCP-ready interfaces, verifies them in controlled environments, and improves them through measured agent testing.

It combines repository and UI analysis with controlled browser execution to identify candidate actions, generate atomic WebMCP tool wrappers, and test each tool using either a disposable sandbox or MCP-B Chrome integration with an external evaluation agent. For every tool, the system checks observable preconditions, postconditions, network effects, and optional backend audit events. Unsafe, unverifiable, or incorrect tools are quarantined.

A closed-loop optimiser evaluates realistic held-out tasks and rewrites tool names, descriptions, and approved schemas only when repeated trials show improvement without weakening safety contracts. SpecX outputs verified WebMCP definitions, workflow manifests, tests, diagnostics, and an agent-readiness report for each application version.

## 4 Major Functionalities [Tentative]

**F1 (Completely New) — Contract-Grounded Tool Verification:** Derives executable preconditions and postconditions from code, DOM, accessibility, network traces, and audit events. Runs each candidate tool in a controlled browser and quarantines tools with incorrect or unapproved effects.

**F2 (Completely New) — Safety-Preserving Closed-Loop Optimisation:** An external agent tests verified tools through a sandbox or MCP-B Chrome integration. Failure traces guide LLM revisions; a statistical regression gate accepts only changes that improve performance while preserving safety invariants.

**F3 (Upgrade) — Evidence-Based Website-to-WebMCP Generation:** Extends form/action generators using repository parsing, semantic DOM/ARIA signals, API traces, and existing end-to-end tests to produce implementation-ready, atomic WebMCP tool definitions.

**F4 (Upgrade) — Comparative Agent-Readiness Evaluation and Workflow Graphs:** Extends web-agent benchmarks with raw DOM, generated, verified, and optimised WebMCP conditions. Builds typed workflow graphs capturing valid tool order, state transitions, data dependencies, and risk levels.

## Project Outcome

Standalone CLI, CI integration, and web dashboard that convert authorised websites into verified, performance-optimised WebMCP interfaces with tests, diagnostics, workflow manifests, and reports.

## Additional Outcome

Research Paper: Controlled evaluation of whether contract-verified WebMCP interfaces improve agent success, efficiency, and safety compared with raw DOM interaction and unverified tools.

---

# 2. Reviewer Feedback & The Eight Suggestions

> The project idea you submitted for the Artificial Intelligence Course has been **provisionally accepted**. Include at least four more additional functionalities from the list below, besides those mentioned in your uploaded document, and then start working on the project requirement analysis and further development.

### The eight suggested enhanced functionalities

**S1.** Instead of relying solely on standard evaluation agents for closed-loop optimization, implement a specialized DRL agent trained via adversarial rewards to actively discover edge cases, race conditions, and hidden side effects within the controlled browser execution. This upgrades the verification engine by identifying complex state-transition failures that standard LLM-driven testing trails might overlook.

**S2.** Transform the current structural workflow graphs into typed embedding spaces using GNNs, such as Graph Convolutional Networks (GCNs). This will allow the system to predict unmapped data dependencies, forecast high-risk tool execution paths, and automatically detect non-obvious violations of safety invariants across long-sequence agent interactions.

**S3.** Introduce a self-supervised contrastive learning framework (similar to CLIP but tailored for software) that co-embeds repository source code, DOM trees, and network traces. This will significantly upgrade the generation component by ensuring that the generated atomic WebMCP tool definitions maintain deep semantic alignment between the developer's underlying code logic and the visual UI layer.

**S4.** Upgrade the LLM revision loop by integrating a fine-tuned, multi-modal transformer architecture capable of processing serialized DOM diffs, network trace logs, and visual screenshots simultaneously. The model can then output structured, actionable code patches and schema corrections rather than relying on unstructured textual failure traces.

**S5.** Implement a Meta-Learning framework (such as Model-Agnostic Meta-Learning) to optimize tool names, descriptions, and JSON schemas. This modification ensures that the closed-loop optimizer does not overfit to specific local held-out tasks, enabling the system to generalize its agent-readiness adjustments instantly across entirely different web application domains.

**S6.** Integrate deep isolation forests or LSTM-autoencoders to analyze browser network traces and DOM mutation observers in real-time. This provides an AI-driven safety layer that catches subtle, slow-leaking unapproved side effects or unauthorized background API calls during sandboxed testing.

**S7.** Upgrade the generator by deploying a specialized RAG framework that indexes existing end-to-end testing scripts (e.g., Cypress, Playwright). When encountering complex DOM interactions, the system can retrieve similar verified architectural patterns to generate highly robust, production-ready WebMCP tool wrappers.

**S8.** Incorporate feature attribution methods (such as SHAP or Integrated Gradients) into the evaluation module. This modification transforms the raw agent-readiness reports and risk levels into clear, transparent diagnostic scorecards, explaining precisely why a specific tool is quarantined or flagged as low-readiness.

**Requirement:** Incorporate the best 4 out of the given suggestions. Target: journal publication with at least 4 novel approaches.

---

# 3. Deep Novelty & Prior-Art Analysis

## 3.1 Decision Summary

**Adopt S1, S2, S4, S6. Drop S3, S5, S7, S8.**

These four maximize defensible novelty *in the WebMCP context*, slot cleanly into the existing F1–F4 pipeline, are feasible for a small team in one semester, and each supports a clean ablation.

**Critical finding:** SpecX's core (F1 contract verification, F2 closed-loop optimization) is **not novel on its own**. ContractSkill (arXiv 2603.20340) and CoEvoSkills (arXiv 2604.01687) already do contract-based verification and co-evolutionary verification for web-agent skills. SpecX's novelty must rest on the *WebMCP generation target*, *multi-surface contract grounding*, and the *four added contributions*.

## 3.2 WebMCP Ecosystem Status (verified context)

- WebMCP lets web apps expose JavaScript-based tools to AI agents; a page using WebMCP acts as a client-side MCP server.
- Roots trace to **MCP-B**, built by Alex Nahas at Amazon in early 2025 to handle auth challenges of running internal services as MCP servers; now unified into WebMCP with Nahas involved in the W3C working group.
- Timeline: MCP-B built Jan 2025 → Google/Microsoft unified proposal Aug 2025 → W3C Web Machine Learning Community Group formally accepted Sep 2025 → Chrome 146 shipped Early Preview Feb 2026 behind a `chrome://flags` "WebMCP for testing" flag → native Chrome/Edge support targeted H2 2026.
- Spec authored by Microsoft's Brandon Walderman, Leo Lee, Andrew Nolan and Google's David Bokan, Khushal Sagar, Hannah Van Opstal; published as Draft Community Group Report Feb 2026.
- **Date caveat:** sources cite 12 February 2026, but some MCP spec artifacts carry a later 2026-07-28 stateless-spec date that is easy to conflate. Verify against `github.com/webmachinelearning/webmcp`.
- Adjacent MCP security work: MCP-Scan, MCP-Scanner, Proximity, Cisco `mcp-scanner` — all analyse *declared* tools **statically**. SpecX must differentiate as runtime-effect verification of *generated* tools.

## 3.3 Closest Neighbours to the SpecX Core (must-cite)

| Work | What it does | How SpecX differs |
|---|---|---|
| **ContractSkill** (arXiv 2603.20340, Lu et al., 2026) | Compiles a draft web-agent skill into a "contracted executable artifact with explicit preconditions, step specifications, postconditions, recovery rules, and termination checks"; enables deterministic verification, step-level fault localization, minimal patch-based repair. Lifts VisualWebArena self-generated-skill success from ~9–11% to ~28–38%. | Verifies hand-drafted *skills* against page state only. SpecX targets *generated WebMCP tools*, grounds contracts in five surfaces (code, DOM, ARIA, network, audit events), and adds a generation stage ContractSkill lacks. |
| **CoEvoSkills** (arXiv 2604.01687, 2026) | Skill Generator and information-isolated Surrogate Verifier "co-evolve through iterative generate–verify–refine cycles"; ground-truth oracle "returns only an opaque pass/fail signal". | Optimises skill *code* via LLM surrogate. SpecX optimises agent-facing *metadata* (names, descriptions, schemas) behind a statistical regression gate with hard safety invariants. |
| **Methods for Formal Verification of Agent Skills** (arXiv 2605.23951, 2026) | Verifies across "three verification surfaces"; checks that "every world-state change has a matching audit-log envelope"; explicitly contrasts with plain MCP/OpenAI JSON-Schema validation. | Verifies existing skills formally. SpecX unifies generation + multi-surface runtime verification + adversarial fuzzing + closed-loop optimisation in one system, and evaluates agent readiness comparatively. |

**Implication:** the paper's related-work section must lead with these three and argue the distinction explicitly. If SpecX cannot be distinguished from ContractSkill on verification, the core contribution collapses.

## 3.4 Full Comparison Table — All Eight Suggestions

| # | Suggestion | Novelty (1–5) | Closest prior art | Feasibility (1 sem) | Fit to F1–F4 | Verdict |
|---|---|:---:|---|:---:|---|:---:|
| **S1** | Adversarial DRL fuzzing to find edge cases/race conditions/side effects in sandbox | **4** | WebRLED (arXiv 2504.19237, curiosity-driven DRL web GUI testing); GENESIS-RL (edge-case RL); ARLAS (arXiv 2510.05442, adversarial RL for agent safety); RL-XSS grey-box fuzzing | **High** (Gym env + PPO/DQN over existing sandbox; reward = contract violations) | **F1 (strong)** — feeds the verifier | ✅ **PICK** |
| **S2** | GNNs on typed workflow graphs to predict data deps, high-risk paths, safety-invariant violations | **4** | FLORA/FLORA-Bench (arXiv 2503.11301, GNNs predict *performance* of agentic workflows); AFGNN (API misuse); provenance-graph GNNs (security) | **Med-High** (PyG; GCN/GAT/Graph Transformer; labels from sandbox verdicts) | **F4 (native)** + F1 | ✅ **PICK** |
| **S4** | Fine-tuned multimodal transformer → structured patches/schema corrections | **4** | SVRepair (arXiv 2602.06090); GALA (arXiv 2604.08089); VisualRepair (arXiv 2607.14075) — all multimodal APR but NOT WebMCP schema/tool-description repair | **Med** (VLM API + LoRA; structured JSON output; no full pretrain) | **F2 (native)** | ✅ **PICK** |
| **S6** | Isolation Forest / LSTM-AE on network traces + DOM mutation streams as runtime safety layer | **3.5** | Hybrid LSTM-AE + Isolation Forest for network anomaly (many); TRACE/JANUS (trajectory-level agent safety) | **Very High** (sklearn IsolationForest + small LSTM-AE; off-the-shelf) | **F1 (strong)** — second safety net | ✅ **PICK** |
| **S3** | CLIP-style contrastive co-embedding of code + DOM + network traces | **2.5** | GNN-Coder (arXiv 2502.15202, CLIP-style code↔text); Pix2Struct; Screen2Vec; CodeBERT/GraphCodeBERT | **Low** (needs large aligned tri-modal corpus + contrastive pretrain compute) | F3 | ❌ drop |
| **S5** | MAML meta-learning to optimize tool names/desc/schemas across domains | **2.5** | System Prompt Optimization with Meta-Learning (arXiv 2505.09666); DSPy/MIPROv2; OPRO; PLAY2PROMPT (arXiv 2503.14432) | **Low** (MAML bilevel optim unstable; needs many web-app "tasks") | F2 | ❌ drop |
| **S7** | RAG over Cypress/Playwright test scripts | **2** | Autonomous QA Agent (arXiv 2601.06034, RAG for Selenium gen); cypress-generator; Playwright MCP/codegen | **Very High** (but too incremental) | F3 | ❌ drop |
| **S8** | SHAP / Integrated Gradients → diagnostic readiness scorecards | **2** | AgentSHAP (arXiv 2512.12597, "first framework for explaining tool importance in LLM agents") | **High** (but pre-empted) | F4 | ❌ drop |

## 3.5 The Recommended Four — Defensible Claims & Experiment Design

### S1 — Adversarial DRL fuzzing of WebMCP tool contracts (→ F1)

**Defensible novelty claim:** "The first application of adversarial reinforcement-learning fuzzing to WebMCP/MCP tool *contract* verification, where the reward is defined over executable pre/postcondition violations, unapproved side effects, and race conditions observed in a disposable browser sandbox."

Closest prior art WebRLED (curiosity-driven DRL for web GUI *coverage/failure* testing) and GENESIS-RL (RL edge-case generation) target crashes/coverage, not *contract violations of machine-readable agent tools*; ARLAS does adversarial RL for prompt-injection defense, not tool-effect fuzzing. **The gap is real.**

**Implementation:** Wrap the existing sandbox as a Gym-style environment. Actions = parameter mutations / call orderings / concurrent invocations. State = DOM + network + audit deltas. Reward = +1 per newly triggered contract violation or unapproved effect, shaped by a novelty/curiosity bonus (à la WebRLED). Use PPO or DQN (Stable-Baselines3). Compare against random fuzzing and coverage-guided baselines.

**Ablation:** verified-tool quarantine rate and mean-time-to-first-violation with (a) random fuzz, (b) coverage-guided, (c) adversarial DRL. Hypothesis: DRL finds more high-severity violations per sandbox-hour.

### S2 — GNNs over typed workflow graphs (→ F4, feeds F1)

**Defensible novelty claim:** "The first use of GNNs to predict *unmapped data dependencies and safety-invariant violations* over typed WebMCP workflow graphs, as opposed to predicting workflow *task performance*."

FLORA/FLORA-Bench — the closest work — formulates agentic workflows as computational graphs and trains GNNs to predict workflow *success rates*, "achieving up to a 125× speedup with minimal performance loss" over LLM evaluation; FLORA-Bench comprises ~600,000 workflow-task pairs, and GNN baselines average 0.78 accuracy / 0.72 utility across six domains (GAT reaches ~84% on coding). FLORA does *not* predict safety-invariant violations or data-dependency edges. SpecX repurposes graph learning for a *safety/typing* target.

**Implementation:** Build typed graphs (nodes = tools with type signatures/risk level; edges = valid order, state transition, data dependency). Train GCN/GAT/Graph Transformer (PyTorch Geometric) for (a) edge prediction (missing data deps) and (b) node/subgraph classification (invariant-violation risk). Labels come from sandbox verdicts (S1/F1) — **synergy: S1 generates positive violation examples for S2's training set.**

**Ablation:** precision/recall of predicted risky paths vs. a rule-based dependency checker and an MLP-on-features baseline; measure how many real violations the GNN flags *before* sandbox execution.

### S4 — Multimodal transformer emitting structured patches (→ F2)

**Defensible novelty claim:** "The first multimodal (DOM-diff + network-trace + screenshot) model that outputs *structured tool-schema corrections and code patches* for WebMCP tool revision, replacing unstructured textual failure traces in the closed loop."

Multimodal APR systems SVRepair, GALA, and VisualRepair (2026) repair *general program bugs* from bug screenshots; none target WebMCP tool descriptions/JSON schemas or consume network traces as a modality.

**Implementation:** Do not pretrain from scratch — use an off-the-shelf VLM (Qwen-VL/LLaVA-class) with LoRA fine-tuning on (failure-trace bundle → structured patch) pairs harvested from SpecX's own optimization runs; enforce JSON-schema-constrained decoding. Serialize DOM diffs and network logs as text, feed screenshots as image tokens.

**Ablation:** revision loop with (a) unstructured textual traces (baseline = current F2), (b) text-only structured patches, (c) full multimodal structured patches. Metric: agent-task success improvement per revision iteration and iterations-to-convergence, gated by the statistical regression/safety gate.

### S6 — Streaming anomaly detection safety layer (→ F1)

**Defensible novelty claim:** "A real-time AI anomaly-detection safety layer over browser network traces and DOM MutationObserver streams that catches slow-leaking unapproved side effects and unauthorized background API calls during sandboxed WebMCP tool testing — complementary to deterministic contract checks."

Hybrid LSTM-AE + Isolation Forest is well established for *network intrusion* detection, but not applied to *DOM-mutation + network streams during agent-tool sandbox verification*. Novel application, clean second safety net distinct from S1's active fuzzing.

**Implementation:** sklearn `IsolationForest` on windowed network/DOM features + a small LSTM-autoencoder (Keras/PyTorch) trained on "approved" traces; reconstruction error / isolation score above threshold → flag. Fully off-the-shelf, negligible compute — **lowest-risk of the four.**

**Ablation:** detection rate of injected slow side effects (delayed background POSTs, silent localStorage writes) for (a) contract checks only, (b) + Isolation Forest, (c) + LSTM-AE; report false-positive rate on benign tools.

## 3.6 Why the Other Four Were Dropped

- **S3 (contrastive code↔DOM↔trace):** Most compute/data-hungry option; needs a large *aligned tri-modal* corpus a student team cannot easily assemble, and GNN-Coder already demonstrates CLIP-style code↔text alignment. High risk of a weak, under-trained embedding reviewers dismiss.
- **S5 (MAML for tool descriptions):** "System Prompt Optimization with Meta-Learning" (arXiv 2505.09666) already brings MAML to prompt optimization; MAML's bilevel optimization is notoriously unstable and needs a large distribution of web-app "tasks". DSPy/MIPROv2/OPRO are simpler, stronger baselines a reviewer will demand — and would likely beat a hastily-trained MAML. Cross-domain generalization is better claimed as an *evaluation* of S4's optimizer.
- **S7 (RAG over test scripts):** Autonomous QA Agent (arXiv 2601.06034) already shows RAG-grounded Selenium generation reaching 100% syntax validity and 90% execution success (vs. 30% for standard LLM generation); Playwright MCP and codegen make this near-solved. Keep as an internal engineering aid, not a paper claim.
- **S8 (SHAP/IG scorecards):** AgentSHAP (arXiv 2512.12597) is explicitly "the first framework for explaining tool importance in LLM agents" using Monte-Carlo Shapley values — pre-empts the core novelty. Retain as a UI/reporting feature.

## 3.7 Benchmark Anchoring

- **ST-WebAgentBench:** 222 policy-paired tasks scored on six dimensions with the Completion-under-Policy (CuP) metric; evaluated agents' "average CuP is less than two-thirds of their nominal completion rate." → supplies the safety dimension.
- **OSWorld-MCP:** 158 auto-generated MCP tools across 7 applications, tool-vs-GUI ablation. → nearest tool-condition comparator.
- **WebArena / Mind2Web:** standard task pools. (Not separately re-verified in the search; standard and well-documented.)
- **No prior benchmark spans SpecX's four conditions** (raw DOM / generated / verified / optimised) — itself a contribution.

## 3.8 Venue Strategy

| Venue | Profile | Strategy |
|---|---|---|
| **IEEE Access** (primary) | Clarivate 2026 JCR: 2025 JIF 4.2 (5-yr 3.9), Q2, ranked 128/366 in Electrical & Electronic Engineering (~65th percentile); acceptance ~40–45%; median first decision ~30 days; APC $1,995 | Best first target: values applied novelty + solid experiments; fast enough for a student timeline |
| **Empirical Software Engineering** (Springer) | CiteScore ~8.6, Q1; LetPub rates competitiveness "Easy"; review >12 weeks | Choose if the four-condition benchmark study becomes the headline; demands genuine empirical/statistical depth |
| **Journal of Systems and Software** | 2025 JIF ~3.8, Q2 | Prestige upgrade if early results are strong |
| **Automated Software Engineering** (Springer) | Strong scope match to automated tool generation + verification | Plausible reach; scope matches SpecX almost verbatim |
| **TOSEM / TSE** | TOSEM 2024 JIF 6.2; TSE JIF ~5.6–6.5, "the leading journal in software engineering" | Aspirational only; long cycles, expect major revisions |

## 3.9 Paper Contribution List (≥4 novel approaches)

1. **F1+F2 core (reframed):** WebMCP tool generation from developer-authorized websites with *multi-surface* contract-grounded verification (code/DOM/accessibility/network/audit) in a disposable sandbox + safety-preserving closed-loop optimization — novel *as a WebMCP-specific system*, differentiated from ContractSkill (page-state only) and CoEvoSkills (surrogate-LLM verifier, skill code not schemas).
2. **S1:** First adversarial-DRL fuzzer whose reward is WebMCP tool *contract violations*.
3. **S2:** First GNN predicting *data dependencies and safety-invariant violations* on typed WebMCP workflow graphs (vs. FLORA's performance prediction).
4. **S4:** First multimodal (DOM-diff/trace/screenshot) model producing *structured WebMCP schema/tool patches* in a revision loop.
5. **S6:** First streaming LSTM-AE + Isolation-Forest safety layer for DOM-mutation/network side-effect detection during agent-tool sandbox verification.
6. **Benchmark:** A four-condition comparative agent-readiness benchmark with typed workflow graphs.

## 3.10 Implementation Order & Fallback Thresholds

**Order: S6 → S1 → S2 → S4.** S6 first (lowest risk, off-the-shelf, immediate results), then S1 (reuses the sandbox), then S2 (consumes S1's violation labels), then S4 (needs harvested failure/patch pairs). This creates data dependencies that make the pipeline coherent.

**Thresholds that change the plan:**
- If S1's DRL fuzzer does not beat coverage-guided fuzzing on violations-per-hour after ~2 weeks of tuning → fall back to coverage-guided + curiosity heuristics, reclassify S1 as engineering, promote S7 (RAG) as the fourth *ablatable* component.
- If S2's GNN cannot exceed a rule-based dependency checker → reduce to an interpretability/visualization aid, consider promoting S8's scorecard.

## 3.11 Caveats on This Analysis

- **arXiv IDs in the 26xx range are 2026 preprints.** Several (ContractSkill, CoEvoSkills, SkillFoundry, the formal-verification paper) are very recent and may still be under review — verify final versions and exact claims before citing as settled prior art.
- **The WebMCP draft date is contested across sources** (12 Feb 2026 Draft Community Group Report per aggregators vs. a 28 Jul 2026 date tied to a separate stateless-MCP spec artifact). Confirm directly against the W3C repo.
- **Journal impact factors and acceptance rates come partly from third-party aggregators** and can disagree (IEEE Access acceptance cited as ~20% by one IEEE-linked source, ~40–45% by others). Confirm against Clarivate JCR and official journal pages.
- **Novelty framing is fragile for the core.** Because ContractSkill and CoEvoSkills are so close, a reviewer could argue F1/F2 are incremental; acceptance likely hinges on the strength of the four add-ons and the benchmark.
- **"First application" claims are time-sensitive.** Hedge with "to our knowledge" + a stated literature-cutoff date, and re-run a prior-art check immediately before submission.

---

# 4. Project Draft — Full Content

*This is the complete text of the generated 15-page PDF draft (Anthropic-themed: cream/coral/slate palette; Source Serif 4 + Archivo typography approximating Tiempos + Styrene).*

## Cover Metadata

| Field | Value |
|---|---|
| Document type | Full project draft — features, literature review, concepts, implementation, publication plan |
| Existing functionalities | F1 Contract-Grounded Verification · F2 Closed-Loop Optimisation · F3 Evidence-Based Generation · F4 Agent-Readiness Evaluation |
| New functionalities | S1 Adversarial DRL Fuzzing · S2 GNN Workflow-Risk Prediction · S4 Multimodal Structured Patching · S6 Streaming Anomaly Detection |
| Deliverables | CLI · CI integration · web dashboard · verified WebMCP definitions · workflow manifests · agent-readiness reports · research paper |
| Target venues | IEEE Access (primary) · Empirical Software Engineering · Journal of Systems and Software |

## Section 01 — Abstract & Motivation

WebMCP lets web applications expose structured, machine-readable tools to AI agents: a page carrying WebMCP tool definitions effectively behaves as a client-side MCP server that agents can call directly, instead of scraping and clicking through the raw DOM. The proposal, which grew out of the MCP-B project and is now advanced through the W3C Web Machine Learning Community Group by Google and Microsoft, shipped as an early preview behind a flag in Chrome 146 in February 2026, with broader native support expected later in the year. The opportunity is therefore immediate — and so is the risk: auto-generated tools may invoke the wrong action, cause unapproved side effects, silently leak data through background requests, or be so poorly named and described that agents cannot reliably select them.

SpecX addresses this end to end. It (i) analyses a developer-authorised website's repository, DOM, accessibility tree, API traces and existing end-to-end tests to generate atomic WebMCP tool wrappers; (ii) derives executable preconditions and postconditions for every tool and verifies them in a controlled browser sandbox, quarantining anything unsafe, unverifiable or incorrect; (iii) optimises tool names, descriptions and schemas through measured agent testing behind a statistical regression gate that never trades safety for performance; and (iv) evaluates agent readiness across four conditions — raw DOM, generated, verified, and optimised WebMCP — over typed workflow graphs.

Following the review committee's provisional acceptance, this draft incorporates four additional AI functionalities selected from the eight suggested enhancements: **S1** an adversarial deep-reinforcement-learning fuzzer that hunts for contract violations, race conditions and hidden side effects; **S2** graph neural networks that turn typed workflow graphs into embedding spaces for predicting unmapped data dependencies and high-risk execution paths; **S4** a fine-tuned multimodal transformer that converts DOM diffs, network traces and screenshots into structured code patches and schema corrections; and **S6** a streaming anomaly-detection layer (Isolation Forest + LSTM autoencoder) that catches slow-leaking unapproved effects during sandboxed testing. The selection was made after a prior-art study to maximise defensible novelty, architectural coherence, one-semester feasibility, and clean ablation design.

> **Thesis of the paper.** Contract-verified, adversarially tested and learning-optimised WebMCP interfaces measurably improve agent success, efficiency and safety compared with raw DOM interaction and unverified generated tools — and each added subsystem contributes an independently measurable share of that improvement.

## Section 02 — Existing Functionalities (F1–F4)

The four functionalities below form the accepted core of SpecX. F1 and F2 were proposed as completely new; F3 and F4 as upgrades of existing generator and benchmark work. Together they define the pipeline into which the new S-features plug.

### F1 · NEW — Contract-Grounded Tool Verification

Derives *executable* preconditions and postconditions for every candidate tool from five evidence surfaces: repository code, rendered DOM, accessibility (ARIA) tree, network traces, and optional backend audit events. Each tool is executed in a controlled browser — a disposable sandbox or an MCP-B Chrome integration — and its observable effects are checked against the contract. Tools with incorrect, unapproved or unverifiable effects are quarantined rather than shipped.

*Output:* pass/fail verdicts per contract clause, effect diffs, quarantine list with machine-readable reasons.

### F2 · NEW — Safety-Preserving Closed-Loop Optimisation

An external evaluation agent exercises the verified tools on realistic held-out tasks. Failure traces guide LLM-driven revisions of tool *names, descriptions and approved JSON schemas* — the agent-facing metadata that governs tool selection — never the underlying action. A statistical regression gate accepts a revision only when repeated trials show improvement *and* all safety invariants still hold.

*Output:* optimised tool metadata, per-revision trial statistics, accepted/rejected revision log.

### F3 · UPGRADE — Evidence-Based Website-to-WebMCP Generation

Extends form/action generators with repository parsing, semantic DOM/ARIA signals, API traces and existing end-to-end tests to identify candidate actions and emit implementation-ready, *atomic* WebMCP tool definitions (one verifiable action per tool). Atomicity is what makes F1's contracts checkable.

*Output:* WebMCP tool definitions with parameter schemas, provenance links back to the evidence that justified each tool.

### F4 · UPGRADE — Comparative Agent-Readiness Evaluation & Workflow Graphs

Extends web-agent benchmarks with four conditions — raw DOM, generated, verified, and optimised WebMCP — so every pipeline stage is measurable. Builds *typed workflow graphs* whose nodes are tools (with type signatures and risk levels) and whose edges encode valid ordering, state transitions and data dependencies.

*Output:* agent-readiness report per application version, workflow manifests, benchmark scores per condition.

**Project outcome.** A standalone CLI, CI integration and web dashboard that convert authorised websites into verified, performance-optimised WebMCP interfaces with tests, diagnostics, workflow manifests and reports — plus a controlled research study of whether contract-verified WebMCP interfaces improve agent success, efficiency and safety.

## Section 03 — Literature Review & Prior-Art Positioning

*(Full content in Part 3 above: WebMCP ecosystem status §3.2, closest-neighbour differentiation table §3.3, per-enhancement prior art §3.4, benchmark anchoring §3.7.)*

## Section 04 — New Functionalities (S1, S2, S4, S6)

Four of the eight reviewer suggestions are adopted. Selection criteria: publishable novelty surviving the prior art, coherence with F1–F4, one-semester feasibility for a small team, and a clean per-feature ablation.

### S1 · NEW — Adversarial DRL Contract Fuzzer → plugs into F1

A deep-reinforcement-learning agent (PPO/DQN) treats the F1 sandbox as a Gym-style environment. Its *actions* mutate tool parameters, reorder calls, and fire concurrent invocations; its *state* is the observed DOM + network + audit delta; its *reward* is +1 for each newly triggered contract violation, unapproved side effect or race condition, shaped by a curiosity bonus for novel states. Standard LLM-driven test trails explore the happy path; the adversarial agent is paid to break it.

*Novelty claim:* to our knowledge, the first adversarial-RL fuzzer whose reward is defined over executable pre/postcondition violations of WebMCP/MCP agent tools (vs. coverage/crash rewards in WebRLED & GUI-testing RL).

### S2 · NEW — GNN Workflow-Risk & Dependency Prediction → plugs into F4 (feeds F1)

F4's typed workflow graphs are embedded with graph neural networks (GCN/GAT via PyTorch Geometric). Two heads: (i) *edge prediction* recovers unmapped data dependencies between tools; (ii) *node/subgraph classification* forecasts high-risk execution paths and non-obvious safety-invariant violations across long tool sequences — before any sandbox run. Training labels come from F1/S1 sandbox verdicts, so the fuzzer literally generates the GNN's training data.

*Novelty claim:* first GNN predicting safety-invariant violations and data dependencies on typed WebMCP workflow graphs — FLORA-style graph learning repurposed from performance prediction to safety.

### S4 · NEW — Multimodal Structured Patch Generator → plugs into F2

Replaces unstructured textual failure traces in the F2 revision loop with a fine-tuned vision-language model (Qwen-VL/LLaVA-class, LoRA-adapted) that ingests serialised DOM diffs, network trace logs and screenshots *simultaneously* and emits schema-constrained JSON: concrete code patches and tool-schema corrections. Structured output makes revisions machine-applicable and auditable by the regression gate.

*Novelty claim:* first multimodal (DOM-diff + trace + screenshot) model producing structured WebMCP schema/tool patches — adjacent multimodal APR (SVRepair, GALA, VisualRepair) repairs general program bugs, not agent-tool metadata.

### S6 · NEW — Streaming Anomaly-Detection Safety Layer → plugs into F1

During every sandboxed run, windowed features from browser network traces and DOM MutationObserver streams feed two detectors: an Isolation Forest (scikit-learn) for point anomalies and a small LSTM autoencoder trained on approved traces, whose reconstruction error flags sequence anomalies. This catches what deterministic contracts miss: slow-leaking side effects, delayed background POSTs, silent storage writes, unauthorised third-party calls.

*Novelty claim:* a real-time learned safety layer over DOM-mutation + network streams during agent-tool sandbox verification — a novel application of a well-proven hybrid detector, positioned as complementary to (not replacing) contract checks.

**Why not S3, S5, S7, S8.** S3 needs a large aligned code–DOM–trace corpus and contrastive pre-training compute a student team cannot marshal, and GNN-Coder weakens its claim. S5 is pre-empted by meta-learned prompt optimisation and is unstable to train; DSPy/OPRO-style baselines would likely win. S7 is an excellent engineering aid (and will be used internally in F3) but is too incremental to claim. S8 is pre-empted by AgentSHAP; it survives as a dashboard reporting feature, not a contribution.

## Section 05 — Concepts Explained

Every technical concept the system relies on, in pipeline order. Doubles as the paper's background section and as onboarding material.

**MCP & WebMCP.** The Model Context Protocol (MCP) is a JSON-RPC-based standard through which AI applications discover and invoke external tools with typed parameter schemas. **WebMCP** moves the tool surface into the web page itself: a site declares JavaScript-backed tools (name, description, input schema, handler), and a browsing agent calls them directly instead of parsing the DOM. MCP-B is the Chrome-extension lineage of the same idea and serves as one of SpecX's two execution targets.

**Atomic tool wrappers.** A tool is *atomic* when it performs exactly one verifiable action (e.g., "add item to cart", never "add item and checkout"). Atomicity is what makes contracts decidable: each tool has a small, checkable effect footprint, and workflows are recovered as graphs over atomic tools rather than baked into monoliths.

**Preconditions & postconditions (design by contract).** A *precondition* states what must hold before a tool may run (user logged in, form field present, cart non-empty); a *postcondition* states what must hold after (order row created, exactly one POST to /api/orders, confirmation dialog visible). SpecX derives both as *executable* checks from code, DOM, ARIA, network traces and audit events — the "contract-grounded" part of F1. A tool that cannot be given a checkable contract is quarantined as unverifiable.

**Sandboxed execution & quarantine.** Every candidate tool runs inside a disposable browser environment (seeded database, network interception, no external effects) so that misbehaviour is observable but harmless. Quarantine means the tool is excluded from the shipped WebMCP manifest and reported with the exact contract clause it violated.

**Closed-loop optimisation & regression gates.** An evaluation agent attempts held-out tasks with the current tool set; failures produce traces; an LLM (later, S4's model) proposes metadata revisions; the revised set is re-trialled. A *statistical regression gate* (paired trials, significance test, effect size) accepts a revision only if performance improves and no safety invariant regresses — preventing the optimiser from "improving" success by weakening safeguards.

**Deep reinforcement learning & adversarial rewards (S1).** RL trains an agent to maximise cumulative reward through trial and error; *deep* RL uses neural networks (here PPO/DQN) over rich state. An *adversarial reward* pays the agent for making the system under test fail — each new contract violation, race condition or unapproved effect is a point. A curiosity bonus (reward for novel states) prevents the fuzzer from replaying the same crash.

**Race conditions & hidden side effects.** A race condition is behaviour that depends on the timing/interleaving of concurrent operations (double-submit creating two orders). A hidden side effect is any state change outside the declared contract (an analytics beacon, a background write). S1 searches for both actively; S6 watches for them passively.

**Graph neural networks & typed embeddings (S2).** GNNs learn vector representations of nodes and edges by iteratively aggregating information from neighbours (GCN: spectral convolutions; GAT: learned attention weights). Embedding SpecX's typed workflow graphs lets the system *predict* missing data-dependency edges (link prediction) and classify paths by violation risk (node/subgraph classification) before spending sandbox time — a learned prioritiser in front of the verifier.

**Multimodal transformers & structured decoding (S4).** A vision-language transformer jointly attends over text tokens (serialised DOM diffs, network logs) and image patches (screenshots). LoRA fine-tuning adapts a pre-trained model cheaply by training small low-rank adapter matrices. *Schema-constrained decoding* forces the output to be valid JSON matching a patch schema, so every revision is machine-applicable.

**Isolation Forests & LSTM autoencoders (S6).** An Isolation Forest isolates anomalies with random splits — anomalous points need fewer splits, giving an anomaly score without labelled attacks. An LSTM autoencoder learns to compress-and-reconstruct *normal* sequences; abnormal sequences reconstruct poorly, and the reconstruction error is the alarm. Together they cover point anomalies and temporal anomalies over network/DOM streams.

**Typed workflow graphs & agent readiness (F4).** Nodes are tools annotated with type signatures and risk levels; edges encode valid ordering, state transitions and data flow. *Agent readiness* is the measured ability of a standard agent to complete tasks against an interface, reported across the four benchmark conditions with success, efficiency (steps/tokens) and safety (policy-violation) metrics.

## Section 06 — Implementation Plan

The plan follows a strict dependency order — **S6 → S1 → S2 → S4** — chosen so that each stage produces the data the next one trains on: S6 needs only approved traces; S1 reuses the sandbox and generates violation examples; S2 trains on S1/F1's verdict labels; S4 trains on failure–patch pairs harvested from F2 runs.

### 6.1 Architecture & Stack

| Layer | Components | Technology |
|---|---|---|
| Generation (F3) | Repo parser, DOM/ARIA analyser, API-trace miner, atomic tool emitter; internal RAG over Cypress/Playwright scripts (S7 as engineering aid) | Node.js/TypeScript, Playwright, tree-sitter, LLM API |
| Verification (F1) | Contract deriver, disposable sandbox, effect differ, quarantine manager | Playwright + CDP, Docker sandboxes, network interception (mitmproxy), seeded Postgres |
| S6 safety layer | Feature windower over network + MutationObserver streams; Isolation Forest; LSTM-AE | scikit-learn, PyTorch (small LSTM), streaming via CDP events |
| S1 fuzzer | Gym wrapper around sandbox; parameter/ordering/concurrency action space; violation+curiosity reward | Gymnasium, Stable-Baselines3 (PPO/DQN) |
| S2 graph model | Typed graph builder; GCN/GAT with edge-prediction + risk-classification heads | PyTorch Geometric, NetworkX |
| Optimisation (F2 + S4) | Evaluation agent harness, regression gate, VLM patch generator with JSON-constrained decoding | LLM/VLM APIs, LoRA (PEFT), outlines/jsonschema decoding, SciPy stats |
| Evaluation (F4) | Four-condition benchmark runner, workflow-manifest exporter, readiness reports | WebArena/Mind2Web task pools, ST-WebAgentBench-style safety scoring, OSWorld-MCP comparator |
| Delivery | CLI, CI integration, dashboard | Node CLI, GitHub Actions, React dashboard |

### 6.2 Semester Timeline (14 weeks)

| Weeks | Milestone | Exit criterion |
|---|---|---|
| 1–2 | F3 generator + F1 sandbox skeleton on 2 seed apps (one e-commerce, one CRUD/admin) | Atomic tools generated with provenance; sandbox replays a tool run deterministically |
| 3–4 | F1 contracts on all five surfaces; quarantine flow; **S6** detectors trained on approved traces | Injected slow side effects detected; false-positive rate on benign tools measured |
| 5–7 | **S1** Gym environment + PPO fuzzer; baseline random & coverage-guided fuzzers | DRL beats baselines on violations found per sandbox-hour (else invoke fallback, §6.4) |
| 8–9 | **S2** graph builder + GNN heads trained on F1/S1 verdicts | GNN beats rule-based dependency checker on held-out precision/recall |
| 10–11 | F2 loop + regression gate; harvest failure–patch pairs; **S4** LoRA fine-tune + constrained decoding | Structured patches apply cleanly; loop converges in fewer iterations than text-trace baseline |
| 12–13 | F4 four-condition benchmark across ≥3 applications; full ablation matrix; statistics | Every S-feature has an isolated effect size with significance test |
| 14 | Paper draft, artifact packaging (code, seeds, manifests), dashboard polish | Reproducibility package runs end-to-end from a clean clone |

### 6.3 Experiment & Ablation Design

- **Conditions:** raw DOM → generated (F3) → verified (F1+S1+S6) → optimised (F2+S4), each evaluated by the same frozen agent on the same held-out task pool.
- **Per-feature ablations:** S1 vs random/coverage fuzzing (violations per sandbox-hour, severity mix); S2 vs rule-based checker and MLP-on-features (dependency P/R, pre-sandbox risk ranking quality); S4 vs unstructured text traces and text-only structured patches (success gain per revision, iterations-to-convergence); S6 on/off with injected slow leaks (detection rate, FPR).
- **Metrics:** task success, steps and tokens to completion, policy-violation rate (Completion-under-Policy style), quarantine precision, time-to-first-violation.
- **Statistics:** ≥10 paired trials per condition; paired tests with Holm–Bonferroni correction; report effect sizes and confidence intervals — the F2 regression gate already provides this machinery.

### 6.4 Risk Register & Fallbacks

- **S1 underperforms** after ~2 weeks of tuning → fall back to coverage-guided fuzzing with curiosity heuristics, reclassify S1 as engineering, and promote S7 (RAG generation) to the fourth ablatable contribution.
- **S2 cannot beat the rule-based checker** → demote to interpretability/visualisation aid; consider promoting an S8-style scorecard with explicit AgentSHAP differentiation.
- **Sparse S4 training pairs** → bootstrap with synthetic failure injection (mutate schemas, break selectors) before harvesting real loop data.
- **WebMCP spec drift** (Chrome preview evolving) → pin to the February 2026 draft; keep the MCP-B extension path as the stable fallback target.

## Section 07 — Path to a Successful Journal Publication

Acceptance will not hinge on the ML methods themselves — all four are established primitives — but on *honest novelty framing, airtight empirical design, and reproducibility*.

### 7.1 Contribution List (≥4 novel approaches)

- **C1 — System.** First end-to-end pipeline generating WebMCP tools from developer-authorised live websites with *multi-surface* contract grounding (code + DOM + ARIA + network + audit events) and sandbox quarantine — explicitly differentiated from ContractSkill, CoEvoSkills and formal skill verification.
- **C2 — S1.** First adversarial-RL fuzzer rewarded on executable contract violations of agent tools.
- **C3 — S2.** First GNN predicting data dependencies and safety-invariant violations on typed WebMCP workflow graphs (vs. FLORA's performance prediction).
- **C4 — S4.** First multimodal (DOM-diff + trace + screenshot) model emitting structured WebMCP schema/tool patches inside a safety-gated revision loop.
- **C5 — S6.** A streaming learned safety layer over DOM-mutation + network streams during tool verification — a novel application, framed as complementary to contracts.
- **C6 — Benchmark.** The first four-condition agent-readiness benchmark (raw DOM / generated / verified / optimised WebMCP) with typed workflow manifests, released as an artifact.

Every "first" must be hedged as *"to our knowledge"* with a stated literature-cutoff date, and the prior-art search re-run immediately before submission — the field moved fast enough in 2026 that a six-week-old novelty claim can expire.

### 7.2 What Determines Acceptance

| Determinant | What reviewers expect | SpecX answer |
|---|---|---|
| Novelty defense | Related work engages the *closest* neighbours head-on, not a survey of distant ones | Dedicated subsection on ContractSkill / CoEvoSkills / arXiv 2605.23951 with a differentiation table; per-feature closest-work citations (WebRLED, FLORA, SVRepair-family, AgentSHAP) |
| Empirical rigour | Controlled conditions, paired trials, significance tests, effect sizes, multiple applications | Four-condition design over ≥3 apps, ≥10 paired trials, Holm–Bonferroni, CIs; the regression gate doubles as the stats engine |
| Ablatability | Each claimed contribution isolated and measured | One ablation arm per S-feature (§6.3); no bundled claims |
| Threats to validity | Explicit internal/external/construct threats | Seed-app selection bias, agent-model dependence, WebMCP spec drift, synthetic-injection realism for S6, fuzzer reward hacking for S1 |
| Reproducibility | Public code, data, seeds, exact model versions, one-command replication | Artifact: CLI + seed apps + manifests + trained checkpoints + benchmark harness; pinned Chrome/spec versions |
| Writing & scope | One coherent story, not eight features | Narrative: *generate → verify (S6, S1) → predict (S2) → repair (S4) → measure (benchmark)* — every feature advances the same safety thesis |

### 7.3 Venue Strategy

*(See §3.8 above for the full table with impact factors, acceptance rates, and strategy notes.)*

### 7.4 Pre-Submission Checklist

- Re-run the prior-art search (arXiv, Semantic Scholar alerts on "WebMCP", "agent tool verification", "skill contracts") and update every novelty hedge.
- Verify the exact WebMCP draft date against the W3C repository (`github.com/webmachinelearning/webmcp`) — sources conflict, and a wrong spec date in paragraph one destroys credibility.
- Confirm venue metrics (JIF, APC, acceptance rate) against Clarivate JCR and official journal pages — aggregator numbers disagree.
- Freeze the evaluation agent model and Chrome version; record all seeds; package a one-command replication script.
- Internal red-team review: have a teammate attack each novelty claim with the cited prior work before a reviewer does.
- Secure faculty guidance sign-off (Dr. Yoganand S / CFAIR) on authorship order, ethics of testing only developer-authorised sites, and data release.

> **Bottom line.** SpecX ships six defensible contributions wrapped in one safety thesis. The core pipeline alone would be judged incremental against 2026 skill-verification work — the four selected S-features and the four-condition benchmark are what make this publishable. Execute in the stated order, keep every claim ablated and hedged, and target IEEE Access first with EMSE as the empirical-track alternative.

## Appendix — Key References

1. Lu et al., "ContractSkill: Repairable Contract-Based Skills for Multimodal Web Agents," arXiv:2603.20340, 2026.
2. "CoEvoSkills: Co-Evolving Skill Generation and Surrogate Verification for Web Agents," arXiv:2604.01687, 2026.
3. "Methods for Formal Verification of Agent Skills: Three Layers Toward a Mechanically Checkable Capability-Containment Proof," arXiv:2605.23951, 2026.
4. "WebRLED: Curiosity-Driven Deep Reinforcement Learning for Web GUI Testing," arXiv:2504.19237, 2025.
5. "Adversarial Reinforcement Learning for Large Language Model Agent Safety (ARLAS)," arXiv:2510.05442, 2025.
6. "FLORA: GNN-Based Performance Prediction for Agentic Workflows / FLORA-Bench," arXiv:2503.11301, 2025.
7. "SVRepair," arXiv:2602.06090; "GALA," arXiv:2604.08089; "VisualRepair," arXiv:2607.14075 — multimodal automated program repair, 2026.
8. "AgentSHAP: Interpreting LLM Agent Tool Importance with Monte Carlo Shapley Value Estimation," arXiv:2512.12597, 2025.
9. "GNN-Coder: Boosting Semantic Code Retrieval with Combined GNNs and Transformer," arXiv:2502.15202, 2025.
10. "System Prompt Optimization with Meta-Learning," arXiv:2505.09666, 2025.
11. "Autonomous QA Agent: RAG-Grounded Test Script Generation," arXiv:2601.06034, 2026.
12. "ST-WebAgentBench: Evaluating Safety and Trustworthiness of Web Agents (Completion-under-Policy)," arXiv, 2024/2025.
13. "OSWorld-MCP: Tool-vs-GUI Evaluation with Auto-Generated MCP Tools," 2025/2026.
14. W3C Web Machine Learning CG, "WebMCP," Draft Community Group Report, Feb 2026 (verify date). `github.com/webmachinelearning/webmcp`.
15. Combination of Isolation Forest and LSTM Autoencoder for Anomaly Detection — hybrid detector literature (network intrusion detection).
16. PLAY2PROMPT, arXiv:2503.14432 — tool-description optimization (cited in S5 prior art).
17. AFGNN — GNN-based API misuse detection (cited in S2 prior art).

*Note: several 2026 arXiv preprints above may still be under review; confirm final versions, authors and claims before citing them as settled prior art in the submitted manuscript.*

---

# 5. PDF Build Notes

The draft was generated as a 15-page A4 PDF with ReportLab (Platypus + BaseDocTemplate).

## Theme (Anthropic-inspired)

| Token | Hex | Use |
|---|---|---|
| CREAM | `#FAF7F0` | page background |
| CREAM_DEEP | `#F2EDE3` | panel / alternating table rows |
| CORAL | `#D97757` | accent bands, table headers, tags |
| CORAL_DARK | `#BC5A38` | kickers, bullets, page numbers |
| INK | `#29261B` | body text (warm near-black) |
| SLATE | `#57534A` | secondary text |
| LINE | `#DDD5C6` | hairlines, table grid |

## Typography

Anthropic's actual typefaces (Tiempos, Styrene) are proprietary, so the closest open equivalents were embedded:

- **Source Serif 4** → Tiempos substitute; headings + body. Static instances cut from the variable font with fontTools: Regular (wght 400, opsz 12), Bold (wght 640, opsz 18), Italic (wght 400, opsz 12), BoldItalic (wght 640, opsz 12).
- **Archivo** → Styrene substitute; kickers, labels, tables. Instances: Regular (wght 400), Medium (wght 500), Bold (wght 650), all wdth 100.

Fonts were downloaded from the Google Fonts GitHub repo, instantiated with `fontTools.varLib.instancer.instantiateVariableFont`, registered via `pdfmetrics.registerFont(TTFont(...))`, and mapped for bold/italic with `addMapping` so inline `<b>`/`<i>` markup resolves correctly.

## Layout Components

- Two page templates: `cover` (full coral top band, 8mm) and `content` (4mm band, running header with "S P E C X" + subtitle, footer with page number in coral).
- Reusable helpers: `section()` (kicker + H1 + coral rule), `feature_card()` (coral tag block + white card with border), `data_table()` (coral header row, alternating cream/white body), `panel()` (cream block with coral left border), `bullets()` (coral square markers).

## Reproduction

```bash
pip install reportlab fonttools pdf2image
# download Source Serif 4 + Archivo variable TTFs from github.com/google/fonts
# instantiate static weights with fontTools
python build_pdf.py   # → SpecX_Project_Draft.pdf
```

Note: ReportLab's built-in fonts lack Unicode subscript/superscript glyphs (they render as black boxes) — use `<sub>`/`<super>` markup in Paragraphs instead. HTML entities (`&mdash;`, `&rarr;`, `&ge;`, `&asymp;`, `&harr;`) were used throughout for typographic characters.

---

# 6. Open Action Items

1. **Verify the WebMCP draft date** against `github.com/webmachinelearning/webmcp` before circulating the draft — sources conflict (12 Feb 2026 vs. a 28 Jul 2026 artifact date), and this appears in the abstract's first paragraph.
2. **Confirm the 2026 arXiv preprints** (ContractSkill 2603.20340, CoEvoSkills 2604.01687, formal verification 2605.23951, SVRepair/GALA/VisualRepair) are still the current versions with the claims as characterised.
3. **Re-check venue metrics** (IEEE Access JIF/APC/acceptance, EMSE CiteScore, JSS JIF) against Clarivate JCR and official pages before submission.
4. **Get Dr. Yoganand S's sign-off** on the four-feature selection, authorship order, and the ethics framing (testing only developer-authorised sites).
5. **Confirm the reviewer accepts S1/S2/S4/S6** as satisfying the "at least four additional functionalities" requirement, and whether S7/S8 as non-claimed engineering features count toward or against the count.
6. **Start Week 1–2 work:** pick the two seed applications (one e-commerce, one CRUD/admin) and stand up the F3 generator + F1 sandbox skeleton.
