import re

import pandas as pd


_EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z0-9\-.]+$")
_ID_PATTERNS = re.compile(r"\b(id|uuid|key|ref|code|num|no)\b", re.IGNORECASE)


def infer_type(series: pd.Series) -> str:
    """Return one of: numeric, category, datetime, text, boolean, id."""
    non_null = series.dropna()
    if len(non_null) == 0:
        return "text"

    name = str(series.name).lower()

    # Boolean
    unique_vals = set(non_null.astype(str).str.strip().str.lower().unique())
    bool_vals = {"true", "false", "1", "0", "yes", "no", "oui", "non", "y", "n"}
    if unique_vals.issubset(bool_vals) and len(unique_vals) <= 4:
        return "boolean"

    # Already numeric in pandas
    if pd.api.types.is_numeric_dtype(series):
        # ID heuristic: column name suggests ID + high cardinality
        if _ID_PATTERNS.search(name) and series.nunique() / max(len(non_null), 1) > 0.9:
            return "id"
        return "numeric"

    # Try numeric conversion
    converted = pd.to_numeric(non_null, errors="coerce")
    if converted.notna().sum() / len(non_null) >= 0.90:
        return "numeric"

    # Datetime detection
    if any(kw in name for kw in ("date", "time", "created", "updated", "modif", "timestamp")):
        try:
            parsed = pd.to_datetime(non_null, errors="coerce", infer_datetime_format=True)
            if parsed.notna().sum() / len(non_null) >= 0.80:
                return "datetime"
        except Exception:
            pass

    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"

    # Attempt generic datetime parse on string columns
    sample = non_null.head(100)
    try:
        parsed = pd.to_datetime(sample, errors="coerce", infer_datetime_format=True)
        if parsed.notna().sum() / len(sample) >= 0.80:
            return "datetime"
    except Exception:
        pass

    # ID heuristic: column name suggests ID + high cardinality
    if _ID_PATTERNS.search(name) and non_null.nunique() / max(len(non_null), 1) > 0.9:
        return "id"

    # Category vs text: low cardinality relative to count
    cardinality_ratio = non_null.nunique() / max(len(non_null), 1)
    avg_length = non_null.astype(str).str.len().mean()

    if cardinality_ratio < 0.05 or non_null.nunique() <= 20:
        return "category"
    if avg_length > 40:
        return "text"

    return "category"
