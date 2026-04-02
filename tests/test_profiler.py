import io
import textwrap

import pandas as pd
import pytest

from src.audit.profiler import profile_dataframe
from src.audit.type_detector import infer_type


# ── Helpers ────────────────────────────────────────────────────────────────

def df_from_csv(text: str) -> pd.DataFrame:
    return pd.read_csv(io.StringIO(textwrap.dedent(text).strip()))


# ── Type detector ──────────────────────────────────────────────────────────

def test_infer_numeric():
    s = pd.Series([1.0, 2.5, 3.0, None], name="amount")
    assert infer_type(s) == "numeric"


def test_infer_category():
    s = pd.Series(["Paris", "Lyon", "Paris", "Lyon"], name="city")
    assert infer_type(s) == "category"


def test_infer_boolean():
    s = pd.Series(["true", "false", "true"], name="active")
    assert infer_type(s) == "boolean"


def test_infer_all_null():
    s = pd.Series([None, None, None], name="empty")
    assert infer_type(s) == "text"


# ── Profiler — basic ───────────────────────────────────────────────────────

def test_profile_basic_structure():
    df = df_from_csv("""
        name,age,city
        Alice,30,Paris
        Bob,25,Lyon
        Alice,30,Paris
    """)
    profile = profile_dataframe(df)
    assert "score" not in profile  # scorer not called here
    assert profile["file_info"]["rows"] == 3
    assert profile["file_info"]["columns"] == 3
    assert profile["overview"]["duplicate_rows"] == 1
    assert len(profile["columns"]) == 3


def test_profile_duplicate_rows():
    df = pd.DataFrame({"a": [1, 1, 2], "b": ["x", "x", "y"]})
    profile = profile_dataframe(df)
    assert profile["overview"]["duplicate_rows"] == 1
    assert profile["overview"]["duplicate_rows_pct"] == pytest.approx(33.33, abs=0.1)


def test_profile_all_null_column():
    df = pd.DataFrame({"a": [1, 2, 3], "b": [None, None, None]})
    profile = profile_dataframe(df)
    col_b = next(c for c in profile["columns"] if c["name"] == "b")
    assert col_b["null_pct"] == 100.0
    assert col_b["unique_count"] == 0


def test_profile_constant_column():
    df = pd.DataFrame({"id": [1, 1, 1], "val": [10, 20, 30]})
    profile = profile_dataframe(df)
    assert "id" in profile["overview"]["constant_columns"]


def test_profile_numeric_stats():
    df = pd.DataFrame({"price": [10.0, 20.0, 30.0, 40.0, 1000.0]})
    profile = profile_dataframe(df)
    col = profile["columns"][0]
    assert col["type"] == "numeric"
    assert col["stats"]["min"] == 10.0
    assert col["stats"]["max"] == 1000.0
    assert col["stats"]["outliers_count"] >= 1


def test_profile_zero_numeric_columns():
    df = pd.DataFrame({"city": ["Paris", "Lyon"], "name": ["Alice", "Bob"]})
    profile = profile_dataframe(df)
    numeric_cols = [c for c in profile["columns"] if c["type"] == "numeric"]
    assert len(numeric_cols) == 0


def test_profile_single_column():
    df = pd.DataFrame({"val": [1, 2, 3, 4, 5]})
    profile = profile_dataframe(df)
    assert profile["file_info"]["columns"] == 1
    assert len(profile["columns"]) == 1


def test_profile_semicolon_csv_via_pandas():
    """Simulate a file already parsed with semicolons by file_handler."""
    df = pd.DataFrame({"nom": ["Alice", "Bob"], "age": [30, 25]})
    profile = profile_dataframe(df)
    assert profile["file_info"]["rows"] == 2


def test_profile_category_case_inconsistency():
    df = pd.DataFrame({"city": ["Paris", "paris", "PARIS", "Lyon"]})
    profile = profile_dataframe(df)
    col = profile["columns"][0]
    issue_text = " ".join(col["issues"])
    assert "casse" in issue_text.lower() or "incoh" in issue_text.lower()


def test_profile_category_leading_spaces():
    df = pd.DataFrame({"tag": [" sport", "sport", " sport"]})
    profile = profile_dataframe(df)
    col = profile["columns"][0]
    issue_text = " ".join(col["issues"])
    assert "espaces" in issue_text.lower() or "whitespace" in issue_text.lower() or "superflus" in issue_text.lower()


def test_profile_date_future():
    df = pd.DataFrame({"date": ["2099-01-01", "2020-06-15", "2030-12-31"]})
    profile = profile_dataframe(df)
    col = profile["columns"][0]
    if col["type"] == "datetime":
        assert col["date_stats"]["future_count"] >= 1


def test_profile_latin1_data():
    """Simulate data that would come from a Latin-1 decoded file."""
    df = pd.DataFrame({"prénom": ["André", "Ève", "Chloé"], "age": [30, 25, 28]})
    profile = profile_dataframe(df)
    assert profile["file_info"]["rows"] == 3
