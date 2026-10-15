from pathlib import Path

import numpy as np

from specx.safety.s6.features import FEATURES, to_sequences, windows_from_jsonl

REPO_ROOT = Path(__file__).resolve().parents[3]
EVENT_FIXTURES = REPO_ROOT / "fixtures" / "events"


def test_approved_trace_has_no_unapproved_requests() -> None:
    runs = windows_from_jsonl(EVENT_FIXTURES / "approved_trace.jsonl")

    assert len(runs) == 1
    unapproved = FEATURES.index("n_unapproved")
    assert sum(window[unapproved] for window in runs[0].X) == 0


def test_post_leak_windowed_after_tool_end() -> None:
    runs = windows_from_jsonl(EVENT_FIXTURES / "leaked_trace.jsonl")

    assert len(runs) == 1
    post_phase = FEATURES.index("is_post_phase")
    unapproved = FEATURES.index("n_unapproved")
    storage = FEATURES.index("n_storage")
    post_windows = [window for window in runs[0].X if window[post_phase] == 1]

    assert any(window[unapproved] == 1 for window in post_windows)
    assert any(window[storage] == 1 for window in post_windows)


def test_to_sequences_pads_runs_to_fixed_shape() -> None:
    approved = windows_from_jsonl(EVENT_FIXTURES / "approved_trace.jsonl")[0]
    leaked = windows_from_jsonl(EVENT_FIXTURES / "leaked_trace.jsonl")[0]

    sequences = to_sequences([approved, leaked], seq_len=8)

    assert sequences.shape == (2, 8, 14)
    assert sequences.dtype == np.float32
    assert np.count_nonzero(sequences[0, len(approved.X) :]) == 0
