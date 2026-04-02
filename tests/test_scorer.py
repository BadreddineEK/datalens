import pandas as pd
import pytest

from src.audit.profiler import profile_dataframe
from src.audit.scorer import compute_score


def make_profile(
    null_pcts: list[float],
    dup_rows_pct: float = 0.0,
    outlier_pcts: list[float] | None = None,
    constant_cols: int = 0,
) -> dict:
    """Build a minimal profile dict for scorer tests."""
    columns = []
    for i, np_ in enumerate(null_pcts):
        col: dict = {"name": f"col{i}", "type": "numeric", "null_pct": np_, "issues": []}
        if outlier_pcts is not None:
            col["stats"] = {"outliers_pct": outlier_pcts[i] if i < len(outlier_pcts) else 0.0, "outliers_count": 0}
        columns.append(col)

    return {
        "overview": {
            "duplicate_rows_pct": dup_rows_pct,
            "constant_columns": [f"const{j}" for j in range(constant_cols)],
        },
        "columns": columns,
    }


# ── Basic scoring ──────────────────────────────────────────────────────────

def test_perfect_score():
    profile = make_profile(null_pcts=[0.0, 0.0], dup_rows_pct=0.0, outlier_pcts=[0.0, 0.0], constant_cols=0)
    score, label = compute_score(profile)
    assert score == 100
    assert label == "Bon"


def test_score_labels():
    cases = [
        (make_profile([0.0], 0.0, [0.0], 0), "Bon"),
        (make_profile([50.0], 0.0, [0.0], 0), "Acceptable"),
        (make_profile([75.0], 50.0, [0.0], 0), "À corriger"),
        (make_profile([100.0], 100.0, [100.0], 10), "Critique"),
    ]
    for profile, expected_label in cases:
        _, label = compute_score(profile)
        assert label == expected_label, f"Expected {expected_label}, got {label}"


def test_null_penalty_max_40():
    """100% nulls on all columns → -40 pts."""
    profile = make_profile([100.0], dup_rows_pct=0.0, outlier_pcts=[0.0])
    score, _ = compute_score(profile)
    assert score == 60


def test_duplicate_penalty_max_20():
    """100% duplicate rows → -20 pts."""
    profile = make_profile([0.0], dup_rows_pct=100.0, outlier_pcts=[0.0])
    score, _ = compute_score(profile)
    assert score == 80


def test_outlier_penalty_max_20():
    """100% outliers → -20 pts."""
    profile = make_profile([0.0], dup_rows_pct=0.0, outlier_pcts=[100.0])
    score, _ = compute_score(profile)
    assert score == 80


def test_constant_col_penalty():
    """1 constant column → -2 pts."""
    profile = make_profile([0.0], dup_rows_pct=0.0, outlier_pcts=[0.0], constant_cols=1)
    score, _ = compute_score(profile)
    assert score == 98


def test_constant_col_penalty_capped_at_20():
    """15 constant columns → max -20 pts."""
    profile = make_profile([0.0], dup_rows_pct=0.0, outlier_pcts=[0.0], constant_cols=15)
    score, _ = compute_score(profile)
    assert score == 80


def test_combined_penalties_floor_zero():
    """All maximum penalties combined must not go below 0."""
    profile = make_profile([100.0], dup_rows_pct=100.0, outlier_pcts=[100.0], constant_cols=15)
    score, _ = compute_score(profile)
    assert score == 0


def test_no_numeric_columns_no_outlier_penalty():
    """No numeric columns → outlier penalty is 0."""
    profile = {
        "overview": {"duplicate_rows_pct": 0.0, "constant_columns": []},
        "columns": [
            {"name": "city", "type": "category", "null_pct": 0.0, "issues": []},
        ],
    }
    score, _ = compute_score(profile)
    assert score == 100


def test_score_from_full_profiler():
    """Smoke test: run scorer on a real profiler output."""
    df = pd.DataFrame({
        "name": ["Alice", "Bob", "Alice"],
        "amount": [100.0, 200.0, 100.0],
        "city": ["Paris", None, "Paris"],
    })
    profile = profile_dataframe(df)
    score, label = compute_score(profile)
    assert 0 <= score <= 100
    assert label in ("Bon", "Acceptable", "À corriger", "Critique")
