# SpecX learned safety components

This directory contains three experimental safety components evaluated on the
`shop` and `admin` seed applications. The numbers below are the observed results
from the checked-out run artifacts, not target values. Reproduce them from the
repository root with `make s6`, `make s1`, and `make graph s2`; build the combined
report with `make report`. S6 and S1 require the seed applications and sandbox to
be running.

## S6: anomaly detection over execution traces

### Claim and method

S6 tests whether event-window features can flag post-execution activity that is
not obvious from a tool's ordinary result. Each run is converted into eight
250 ms windows with 14 network, response, DOM, storage, console, navigation,
audit, and phase features. An Isolation Forest scores individual windows and an
LSTM autoencoder scores the whole sequence. Their thresholds are fixed at the
99th percentile of the approved training scores; the combined detector flags a
run when either model fires.

### Data, split, and metrics

The real run attempted 352 approved traces and retained 302 violation-free runs
for training. Fifty runs were excluded before training because they were not
approved. Evaluation used fresh sessions: 25 examples for each of four injected
leak kinds and 100 separately collected benign runs. The split unit is a run and
no evaluation run sets either threshold.

Detection rate is reported per leak kind for the Isolation Forest, LSTM, and
their union. False-positive rate uses the benign held-out runs. The deterministic
contract result is an ablation showing what the learned layer adds beyond normal
contract checking.

| Leak | Isolation Forest | LSTM | Either | Contract only |
| --- | ---: | ---: | ---: | ---: |
| Delayed POST | 0.52 | 1.00 | 1.00 | 1.00 |
| Storage write | 0.52 | 0.00 | 0.52 | 1.00 |
| Third-party fetch | 0.52 | 0.00 | 0.52 | 1.00 |
| Background poll | 0.96 | 1.00 | 1.00 | 0.00 |

The learned layer's clearest added value is background polling, which contracts
did not detect. That result comes with a serious calibration cost: benign FPR was
0.50 for the Isolation Forest, 0.00 for the LSTM, and 0.50 for the union. S6 is
therefore evidence of detectable signal, not a deployable low-noise detector.

### Threats to validity

- Leaks are injected and may be easier or more regular than naturally occurring
  delayed or background behavior.
- The benign set contains only 100 runs from two small applications. Its traffic
  diversity is too narrow to establish an operational false-positive rate.
- Approved training data is selected using the same contract system used in the
  ablation. Undetected contract failures could contaminate the nominal class.
- The single seed and fixed 99th-percentile threshold do not measure variance.

Source: [`results/s6/metrics.json`](../../../results/s6/metrics.json) and
[`results/s6/run.json`](../../../results/s6/run.json).

## S1: reinforcement-learning safety fuzzer

### Claim and method

S1 tests whether PPO finds contract-violation signatures sooner or at a higher
rate than random and coverage-greedy action selection. An action selects a tool
and an argument mutation. Reward is based on new violation signatures, new state
coverage, and a curiosity bonus. A handler error alone earns no violation reward:
the `error_not_rewarded` regression test requires an actually failed clause.

### Data, split, and metrics

Random, coverage-greedy, and PPO each ran for 1,500 steps on each application for
three seeds. The methods used distinct sandbox sessions and verdict sources. The
primary metric is unique violation signatures per 1,000 invocations. We also
report time to first violation (TTFV), time to first high-severity violation, and
the union and method-only signatures. Runs that never find the event are censored
at 1,500 steps.

| App | Method | Unique signatures / 1k | TTFV | First high |
| --- | --- | ---: | ---: | ---: |
| Admin | Random | 5.33 ± 0.00 | 5.67 ± 3.40 | 6.67 ± 4.50 |
| Admin | Coverage | 5.11 ± 0.31 | 2.67 ± 1.25 | 5.67 ± 4.64 |
| Admin | PPO | 5.33 ± 0.00 | 1.67 ± 0.94 | 2.67 ± 1.25 |
| Shop | Random | 4.67 ± 0.00 | 1.00 ± 0.00 | 1.67 ± 0.94 |
| Shop | Coverage | 4.67 ± 0.00 | 2.67 ± 1.25 | 7.33 ± 5.79 |
| Shop | PPO | 4.67 ± 0.00 | 1.00 ± 0.00 | 8.00 ± 4.97 |

PPO reached violations sooner on `admin`, but it did not increase total signature
coverage: all three methods found the same 15-signature union and no method had a
method-only signature. On `shop`, random found a high-severity violation sooner
than PPO. The supported claim is therefore limited to an admin timing improvement,
not a general coverage advantage for PPO.

### Threats to validity

- Three seeds and 1,500 steps per condition are too small for a robust RL
  comparison, especially when many actions expose the same signatures.
- Reward shaping can encourage superficial clause failures. Excluding bare
  handler errors prevents the simplest error-spam exploit, but does not eliminate
  every form of reward hacking.
- Precondition failures make several signatures easy to obtain and can obscure
  the harder stateful invariants that motivated PPO.
- Both applications have small action spaces and share the same sandbox and
  contract implementation; results may not transfer to larger tool catalogs.

Source: [`results/s1/metrics.json`](../../../results/s1/metrics.json) and
[`results/s1/run.json`](../../../results/s1/run.json).

## S2: graph link and path-risk prediction

### Claim and method

S2 tests learned reasoning over the workflow graph in two tasks. Link prediction
uses a two-layer GCN and dot-product head to rank confirmed data-flow edges against
known-absent pairs, with output/input name matching as the rule baseline. Path-risk
classification uses the same GCN plus a path head and compares it with an MLP over
raw node features. Predicted graph edges are only appended as `evidence: "gnn"`
when the pair is absent and its mean probability across three seeds is at least
0.5.

### Data, split, and metrics

The run loaded 31,764 verdicts from every published verdict JSONL and combined the
`shop` and `admin` graphs as a disjoint union. Path examples were split by session,
yielding 25,355 training and 6,409 held-out examples; an application-prefixed
session identifier prevents cross-app collisions. Link negatives exclude every
existing edge, including unknown rule edges. Because fuzzing produced order edges
for every within-app directed pair, legal negatives came from cross-app pairs in
the disjoint union.

| Task | Model | AUC | Precision | Recall | F1 |
| --- | --- | ---: | ---: | ---: | ---: |
| Link | Rule | — | 1.000 | 0.852 | — |
| Link | GCN | 0.500 | 0.500 | 1.000 | 0.667 |
| Path risk | Raw-feature MLP | 0.934 | 0.775 | 0.890 | 0.828 |
| Path risk | GCN | 0.829 | 0.712 | 0.665 | 0.686 |

The GCN recovered five trace-confirmed `shop` data-flow edges missed by name
matching at the 0.5 threshold. However, link AUC was at chance and the MLP beat the
GCN on path risk. These results do not support a claim that graph message passing
outperforms simpler baselines. No novel GNN edges were appended because there were
no absent within-app node pairs to propose after the dense fuzzing traces.

### Threats to validity

- Mutation labels are inferred from the most common approved/F1 arguments rather
  than queried from a live sandbox. Fuzzed arguments and legitimate rare variants
  can therefore introduce label noise.
- Cross-app negatives are easier than plausible within-app missing links and can
  expose app identity instead of dependency structure. The chance GCN AUC shows
  that this dataset does not provide a convincing link-prediction benchmark.
- Only 14 nodes across two applications are available. Repeated verdicts enlarge
  the path dataset but do not add graph diversity.
- The recovered-edge threshold is evaluated on the same small graph family, and
  recovered edges are not equivalent to useful novel predictions.

Source: [`results/s2/metrics.json`](../../../results/s2/metrics.json) and
[`results/s2/run.json`](../../../results/s2/run.json).
