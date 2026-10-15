# Dev B — Safety ML Implementation Plan (S6 anomaly layer → S1 DRL fuzzer → S2 GNN risk model)

> **For agentic workers:** execute task-by-task in order with `superpowers:executing-plans`. Each task ends with a passing test and a commit on branch `dev-b/<task-id>-<slug>`. Read `docs/00_PROJECT_CONTEXT.md`, `contracts/README.md`, `contracts/sandbox_api.md`, and the fixtures for `event_record`, `verdict`, `workflow_graph` first. Steps use `- [ ]` checkboxes.

**Goal:** three learned safety components that run on real sandbox data and produce result tables 3, 4 and 5 (CONTEXT §9) with honest baselines, by H10.

**Architecture:** Pure Python inside the shared `specx` package. Every component is `dataset → model → metrics.json` with a `run.py` CLI. S6 consumes `EventRecord` streams and writes `verdict.anomaly`. S1 is a Gymnasium environment over `SandboxClient` whose reward is new violation signatures; three policies (random, coverage-greedy, PPO) write verdicts with distinct `source` values. S2 turns `WorkflowGraph` + verdicts into a PyG dataset for link prediction and path-risk classification, with rule-based and MLP baselines, and writes `evidence:"gnn"` edges back.

**Tech stack:** `numpy`, `scikit-learn` (IsolationForest), `torch` (LSTM-AE, GCN), `gymnasium`, `stable-baselines3` (PPO), `torch-geometric`, `networkx`, `pydantic`, `typer`. Install with `cd python && uv sync --all-extras`.

**Spec:** CONTEXT §2 (day-1 scale), §8 (`s6`, `s1`, `s2` targets), §9 tables 3–5, `docs/reference/SpecX_Full_Context.md` §3.5 (the novelty claims your numbers support).

## Global constraints

- Never edit `platform/`. Need an endpoint? PR to `contracts/sandbox_api.md` and ask A.
- All sandbox access through `specx.client.sandbox.SandboxClient` (C writes it in C1 — until merged, code against the signature below and `FakeSandbox`).
- Every `run.py`: `--seed`, `--out`, writes `metrics.json` + `run.json` (git SHA, args, timestamps, durations). Retrains in < 10 min. No checkpoints committed.
- Train/held-out splits are **session-disjoint** for S2 and **run-disjoint** for S6. Document the split in `metrics.json`.
- `pytest -m "not sandbox and not llm"` must pass offline in < 60 s. Sandbox-backed tests carry `@pytest.mark.sandbox`.
- Verdicts you produce carry `source ∈ {s1, s1_random, s1_coverage, s6_inject}` and go to `results/verdicts/<source>.jsonl` (the sandbox appends them when you pass `source`).

## Review focus (tests added in the owning task)

1. **Window alignment** — a leak at `t_ms=812` after `tool_end` at 52 ms must land in a `post`-phase window, not be dropped because the stream ended. (B1 test `post_leak_windowed`.)
2. **S6 threshold chosen on test data** — threshold must be the 99th percentile of scores on the *training* approved traces, fixed before evaluation. (B2 test `threshold_from_train_only`.)
3. **S1 reward hacking by error spam** — `status:"error"` (handler threw on type-mismatch) must not be rewarded as a violation unless a clause actually failed. (B3 test `error_not_rewarded`.)
4. **S2 leakage** — a session's verdicts must not appear in both train and test; link-prediction negatives must not include edges that exist with `evidence:"rule"` (unknown label). (B6 test `session_disjoint_split`.)
5. **Mutation that is not a mutation** — `boundary_max` on a tool with no integer params must fall back to `valid` and say so, not crash. (B3 test `mutation_fallback`.)

Client signature you code against (C owns it; file `python/specx/client/sandbox.py`):
```python
class SandboxClient:
    def __init__(self, base_url: str = env SPECX_SANDBOX_URL): ...
    def health(self) -> dict
    def create_session(self, app: str, seed: int | None = None, leak: dict | None = None) -> str   # session_id
    def load_tools(self, session_id: str, tools: list[dict], contracts: list[dict]) -> None
    def reset(self, session_id: str, seed: int | None = None) -> None
    def invoke(self, session_id: str, tool_id: str, args: dict, *, source: str, post_observe_ms: int = 1500, screenshot: bool = False) -> dict  # Verdict
    def invoke_concurrent(self, session_id: str, calls: list[dict], *, source: str, post_observe_ms: int = 1500) -> dict  # {concurrency_group, verdicts}
    def replay(self, session_id: str, run_id: str) -> dict
    def events(self, session_id: str, since_seq: int = 0) -> list[dict]
    def state(self, session_id: str, screenshot: bool = False) -> dict
    def example_args(self, session_id: str, tool_id: str) -> dict
    def inject_leak(self, session_id: str, kind: str, delay_ms: int) -> None
    def close(self, session_id: str) -> None
class FakeSandbox(SandboxClient):  # in-process; replays fixtures; deterministic; used by all offline tests
```
Shared helpers: `specx.client.schemas.validate(name, obj)`, `specx.client.paths` (`results_dir()`, `verdicts_path(source)`, `graphs_dir()`, ...), `specx.client.seeding.seed_everything(seed)`, `specx.client.io.read_jsonl(path)`, `write_jsonl(path, rows)`, `read_json`, `write_json`.

---

### Task B0 (H0, 15 min): environment

- [ ] `cd python && uv sync --all-extras && uv run python -c "import torch, torch_geometric, stable_baselines3, gymnasium, sklearn; print('ok')"`. If `torch-geometric` fails to resolve, install `torch` first then `uv pip install torch-geometric`; record in `docs/DECISIONS.md`.
- [ ] `uv run pytest -q` green on the empty suite. Commit `chore(python): ml extras resolve`.

### Task B1 (H0–H1): S6 feature windower

**Files:** `python/specx/safety/s6/features.py`, `python/tests/safety/test_s6_features.py`.

**Interfaces produced:**
```python
WINDOW_MS = 250
FEATURES = ["n_req", "n_post_like", "n_unapproved", "n_third_party", "req_bytes", "n_resp", "resp_bytes",
            "n_dom_mut", "n_storage", "n_console", "n_nav", "n_audit", "is_post_phase", "ms_since_tool_end"]  # 14
class RunWindows(BaseModel):
    run_id: str; tool_id: str; X: list[list[float]]  # shape (n_windows, 14), n_windows ≥ 1
def windows_for_run(events: list[dict], *, window_ms: int = WINDOW_MS, horizon_ms: int = 2000) -> RunWindows
def windows_from_jsonl(path: Path) -> list[RunWindows]            # groups by run_id, sorted by seq
def to_sequences(runs: list[RunWindows], seq_len: int = 8) -> np.ndarray  # (n_runs, seq_len, 14) zero-padded/truncated
```
- [ ] Windows span `[t_start(tool_start), t_end(tool_end) + horizon_ms]` in `window_ms` steps; events bucket by `t_ms`; `is_post_phase` = 1 if window start ≥ `t_end`; `ms_since_tool_end` = max(0, window_start − t_end). `n_post_like` counts `POST|PUT|PATCH|DELETE`.
- [ ] Tests: `fixtures/events/approved_trace.jsonl` → 1 run, `n_unapproved` sums to 0; `leaked_trace.jsonl` → a window with `is_post_phase==1` has `n_unapproved==1` and a later one has `n_storage==1` (**post_leak_windowed**); `to_sequences` pads to `(2, 8, 14)`.
- [ ] Commit `feat(s6): feature windower over event streams`.

### Task B2 (H1–H2): S6 models, training, scoring (offline, on synthetic traces derived from fixtures)

**Files:** `s6/models.py`, `s6/train.py`, `s6/score.py`, `s6/synth.py` (test-only generator of approved/leaky traces by jittering the fixtures: timestamps ±20 %, byte sizes ±30 %, optional leak events inserted in the post phase), `python/tests/safety/test_s6_models.py`.

**Interfaces produced:**
```python
class LstmAE(nn.Module):  # input 14 → LSTM(hidden=32, 1 layer) encoder → latent 16 → LSTM decoder → 14; MSE
    def __init__(self, n_features: int = 14, hidden: int = 32, latent: int = 16): ...
    def reconstruction_error(self, X: Tensor) -> Tensor  # (n_runs,) mean over time+features
@dataclass class S6Model: iforest: IsolationForest; lstm: LstmAE; scaler: StandardScaler; thr_if: float; thr_lstm: float; seq_len: int
def train(approved: list[RunWindows], *, seed: int, epochs: int = 30) -> S6Model
    # IsolationForest(n_estimators=200, contamination="auto", random_state=seed) on flattened windows (point anomalies);
    # LSTM-AE on sequences (Adam 1e-3, batch 32); thresholds = 99th percentile of train scores (iforest: -score_samples; lstm: error)
def score_run(model: S6Model, run: RunWindows) -> dict  # {"iforest_score": float, "lstm_error": float, "flagged": bool, "flagged_windows": [int]}  (== verdict.anomaly)
def save(model: S6Model, path: Path) -> None; def load(path: Path) -> S6Model
# score.py CLI: python -m specx.safety.s6.score --in results/verdicts/f1.jsonl --out results/verdicts/f1.jsonl --model results/s6/model
#   reads each verdict's artifacts.events_path, computes anomaly, rewrites the JSONL in place with `anomaly` filled; validates every record.
```
- [ ] `flagged = iforest_score > thr_if or lstm_error > thr_lstm`; `flagged_windows` = indices where the per-window iforest score exceeds `thr_if`.
- [ ] Tests (seeded, < 20 s): train on 200 synthetic approved runs; **threshold_from_train_only** (thresholds equal the 99th pct of the training scores exactly); 50 synthetic `delayed_post` runs → detection ≥ 0.8; 50 held-out approved → FPR ≤ 0.1; `score_run` output validates as `verdict.anomaly`; `save/load` round-trip gives identical scores.
- [ ] Commit `feat(s6): isolation forest + lstm autoencoder with train-set thresholds`.

### Task B3 (H2–H3): S1 environment, mutations, random baseline (offline on `FakeSandbox`)

**Files:** `s1/mutations.py`, `s1/env.py`, `s1/baselines.py`, `python/tests/safety/test_s1_env.py`.

**Interfaces produced:**
```python
MUTATIONS = ["valid", "boundary_max", "boundary_zero", "wrong_type", "missing_required", "unknown_id", "replay_last", "concurrent_x2"]
def mutate(tool: dict, valid_args: dict, mutation: str, rng: np.random.Generator) -> tuple[dict, str]  # (args, applied_mutation) — falls back to "valid" when inapplicable
class SpecXFuzzEnv(gym.Env):
    """action = tool_idx * len(MUTATIONS) + mutation_idx ; obs = concat[one_hot(last_tool, T), one_hot(last_status, 4),
       violation_bitmap(32 — hash of signature mod 32, episode-local), db_counts(6, log1p-scaled), step/horizon(1)]"""
    def __init__(self, client: SandboxClient, app: str, tools: list[dict], contracts: list[dict], *, source: str, horizon: int = 25, post_observe_ms: int = 300, seed: int = 0): ...
    def reset(self, *, seed=None, options=None) -> tuple[np.ndarray, dict]  # client.reset(session); clears episode signature set
    def step(self, action: int) -> tuple[np.ndarray, float, bool, bool, dict]
    # reward = +1.0 per violation signature NEW in this episode (+0.5 extra if new across the whole run — curiosity bonus)
    #          +0.1 if the post-step db-count vector is a state never seen this episode
    #          −0.02 per step ; status=="error" with zero failed clauses → 0 (not rewarded)
    # info = {"verdicts": [...], "new_signatures": [...], "mutation": str}
    @property def all_signatures(self) -> set[str]
def run_random(env, n_steps: int, rng) -> EpisodeLog;  def run_coverage_greedy(env, n_steps: int, rng) -> EpisodeLog
    # coverage-greedy: epsilon=0.2 random; else pick the (tool, mutation) pair with the fewest tries so far (UCB-free counter), ties random
class EpisodeLog(BaseModel): method: str; app: str; seed: int; steps: int; signatures: list[str]; first_violation_step: int | None; first_high_step: int | None; verdict_run_ids: list[str]; per_step_new: list[int]
```
- [ ] `concurrent_x2` calls `client.invoke_concurrent` with two identical calls; `replay_last` calls `client.replay` on the previous run_id (reward only for new signatures as usual).
- [ ] Tests on `FakeSandbox`: `check_env(env)` (gymnasium utils) passes; **error_not_rewarded**; **mutation_fallback**; `run_random(…, 50)` with the fixture tools finds ≥ 1 signature when `FakeSandbox` is configured to fail `place_order` concurrently; same seed ⇒ identical `EpisodeLog`.
- [ ] Commit `feat(s1): gym env over the sandbox with violation reward; random + coverage baselines`.

### Task B4 (H3–H5): S6 on real data — approved traces, leak injection, table 3

**Files:** `s6/collect.py`, `s6/inject.py`, `s6/run.py`, `python/tests/safety/test_s6_run.py` (`@pytest.mark.sandbox`).

- [ ] `collect.py`: for each app, load `results/tools/<app>.tools.json` + contracts (until A5 merges, use `fixtures/tools` + `fixtures/contracts`); for each tool with `status != "quarantined"` (or all, pre-Gate-2): 20 runs with `example_args`, `source="s6_approved"`, `post_observe_ms=2000`. Reset every 5 runs. Read each run's events via `client.events()` and keep only that run's `run_id`. Target ≥ 300 approved runs across both apps (~15 min with 4 sessions in a `ThreadPoolExecutor`). Runs whose verdict has any violation are excluded from training (they are not "approved") and counted in `metrics.json` as `n_excluded`.
- [ ] `inject.py`: per leak kind × 25 runs: `inject_leak(kind, delay_ms ∈ {300, 800, 1400})` then invoke a verified write tool with `source="s6_inject"`, `post_observe_ms=2000`. Record run_ids per kind. Also 100 benign held-out runs (fresh, not in training) for FPR.
- [ ] `run.py --apps shop,admin --out results/s6 --seed 0`: collect → train (`epochs=30`) → score inject + benign → `metrics.json`:
  ```json
  {"n_train": 312, "thresholds": {"iforest": 0.61, "lstm": 0.093}, "seq_len": 8,
   "per_kind": {"delayed_post": {"n": 25, "det_if": 0.92, "det_lstm": 0.88, "det_both": 0.96}, "...": {}},
   "benign": {"n": 100, "fpr_if": 0.04, "fpr_lstm": 0.03, "fpr_both": 0.06},
   "contract_only_detection": {"delayed_post": 1.0, "storage_write": 1.0, "third_party_fetch": 1.0, "background_poll": 0.0}}
  ```
  `contract_only_detection` = fraction of injected runs the deterministic contract already flagged (`violations` non-empty) — the ablation (a) arm. Save model to `results/s6/model/`.
- [ ] Then `python -m specx.safety.s6.score --in results/verdicts/f1.jsonl` so A's verdicts carry `anomaly`. Paste `metrics.json` in the PR. Commit `feat(s6): real-trace training, leak-injection evaluation`.

### Task B5 (H5–H8, **Gate 3**): S1 on the real sandbox — PPO vs baselines, table 4

**Files:** `s1/train.py`, `s1/run.py`, `s1/metrics.py`, `python/tests/safety/test_s1_metrics.py`.

**Interfaces produced:**
```python
def train_ppo(env_fns: list[Callable[[], SpecXFuzzEnv]], *, total_steps: int, seed: int) -> tuple[PPO, EpisodeLog]
    # SB3 PPO("MlpPolicy", DummyVecEnv(env_fns) (4 envs = 4 sessions), n_steps=64, batch_size=64, n_epochs=4, learning_rate=3e-4, ent_coef=0.02, gamma=0.95, seed=seed); EpisodeLog aggregated via a callback
def metrics(logs: list[EpisodeLog]) -> dict
    # per (app, method): mean±sd over seeds of unique_signatures_per_1000 = 1000*len(signatures)/steps ;
    # ttfv = first_violation_step, ttf_high = first_high_step (None → steps) ; severity mix from the verdict files ;
    # plus the union of signatures per method and the per-method-only signatures (what PPO found that random did not)
```
- [ ] `run.py --apps shop,admin --steps 1500 --seeds 3 --out results/s1`: for each app, for seed in 0..2: random (1500 steps), coverage (1500), PPO (1500 total env steps). Sources: `s1_random`, `s1_coverage`, `s1`. Sessions created per env; `post_observe_ms=300`. Writes `results/s1/metrics.json`, `results/s1/logs/*.json`, PPO zip under `results/s1/ckpt/` (gitignored). Progress line every 100 steps with cumulative unique signatures. If wall-clock exceeds 90 min, stop at the current seed and record `"seeds_completed"`.
- [ ] Unit test for `metrics` on hand-built logs; sandbox-marked smoke test: 30 PPO steps on shop with the fixture tools produce ≥ 1 verdict in `results/verdicts/s1.jsonl`.
- [ ] Expected qualitative result: all methods find the `place_order` race via `concurrent_x2` and the stock boundary via `boundary_max`; PPO should reach them in fewer steps and keep finding admin's last-admin invariant (needs `deactivate_user` after `set_role`-free prefix). If PPO ≤ random, report it as is and note hyperparameters tried in `run.json`.
- [ ] Commit `feat(s1): ppo fuzzer vs random and coverage baselines on real sandbox`. **Merge = Gate 3 (B side).**

### Task B6 (H8–H10): S2 dataset, GCN, baselines, table 5

**Files:** `s2/dataset.py`, `s2/models.py`, `s2/baselines.py`, `s2/train.py`, `s2/run.py`, `python/tests/safety/test_s2_dataset.py`, `test_s2_models.py`.

**Interfaces produced:**
```python
NODE_FEATS = 4 (risk one-hot) + 1 (n_in) + 1 (n_out) + 1 (n_state_writes) + 1 (status==quarantined) + 1 (violation_rate)
class GraphData(BaseModel): app: str; node_ids: list[str]; x: np.ndarray; edge_index: np.ndarray; edge_type: np.ndarray
def load_graph(path: Path) -> GraphData   # edges with evidence in {trace, contract} and label True are the base graph; rule-evidence edges are NOT included
def link_examples(graph: WorkflowGraph) -> tuple[np.ndarray, np.ndarray]   # positives: data edges label True (trace); negatives: random (src,dst) pairs that are NOT an edge of any evidence and NOT a rule-edge with label None; 1:1
def path_examples(graph: GraphData, verdicts: list[dict]) -> list[PathExample]  # one per verdict: prefix node idxs, target idx, mutation flag (args differ from example?), label = len(violations)>0, session_id
def split_by_session(examples, frac=0.3, seed) -> (train, test)
class GCNEncoder(nn.Module):  # 2× GCNConv(NODE_FEATS→64→64), ReLU, dropout 0.2
class LinkHead(nn.Module):    # dot product of encodings → sigmoid
class PathHead(nn.Module):    # MLP([mean(prefix enc) ‖ target enc ‖ prefix_len ‖ mutation_flag] → 64 → 1)
def train_link(...)->metrics; def train_path(...)->metrics   # Adam 1e-2, 200 epochs, BCE; metrics: auc, precision, recall, f1 @0.5
# baselines.py
def rule_link(tools) -> set[tuple]   # name-match out→in (what A's nameMatchEdges does) — evaluated against the same test positives/negatives
def mlp_path(...)                    # same PathHead features but with raw node features instead of GCN encodings
```
- [ ] Load graphs from `results/graphs/*.graph.json` and verdicts from **all** `results/verdicts/*.jsonl` (f1 + s1 + s1_random + s1_coverage + s6_inject; expected ≥ 15 k). Combine both apps into one disjoint-union graph (node ids are app-prefixed already).
- [ ] Tests: **session_disjoint_split**; `link_examples` on the fixture graph yields 2 positives (`list_products→add_to_cart`, `view_cart→remove_from_cart`) and negatives that exclude existing edges; models overfit a 20-example toy set to AUC 1.0.
- [ ] `run.py --graphs results/graphs --verdicts results/verdicts --out results/s2 --seed 0`: 3 seeds, `metrics.json` with `link: {rule:{p,r}, gcn:{auc,p,r,f1}}`, `path: {mlp:{...}, gcn:{...}}`, `n_train/n_test`, `recovered_edges` (trace-confirmed edges missed by rule_link but predicted by GCN at ≥ 0.5, listed by `src,dst,field`). Then write predicted edges with `evidence:"gnn"`, `confidence=prob`, `label:null` into each graph file (append, dedupe), validating with `validate("workflow_graph", g)`.
- [ ] Commit `feat(s2): gcn link prediction and path-risk classification with rule and mlp baselines`.

### Task B7 (H10–H12): ablation write-up + integration

- [ ] `python/specx/safety/README.md`: one page per component — claim, data, split, metric, number, threats to validity (S1 reward hacking → `error_not_rewarded`, limited steps; S6 injected-leak realism; S2 label noise from fuzzed args; two apps only).
- [ ] Verify `make s6 s1 s2` from a clean clone (A runs it); fix paths/args. Make sure `make report` (C) finds `results/s6/metrics.json`, `results/s1/metrics.json`, `results/s2/metrics.json` with the exact keys above — C's report reads those keys; if you must rename a key, update `specx/stats/report.py` in the same PR.
- [ ] Commit `docs(safety): ablations and threats to validity`.
