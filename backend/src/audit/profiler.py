from datetime import datetime, timezone

import numpy as np
import pandas as pd

from src.audit.type_detector import infer_type


def _null_pct(series: pd.Series) -> float:
    return round(series.isna().mean() * 100, 2)


def _duplicate_pct(series: pd.Series) -> float:
    non_null = series.dropna()
    if len(non_null) == 0:
        return 0.0
    return round(non_null.duplicated().mean() * 100, 2)


def _profile_numeric(series: pd.Series) -> dict:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if len(clean) == 0:
        return {}

    q1 = clean.quantile(0.25)
    q3 = clean.quantile(0.75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    outliers = clean[(clean < lower) | (clean > upper)]

    counts, bin_edges = np.histogram(clean, bins=10)
    distribution = {
        "bins": [round(float(e), 4) for e in bin_edges[:-1]],
        "counts": [int(c) for c in counts],
    }

    try:
        from scipy.stats import skew as scipy_skew
        skewness = round(float(scipy_skew(clean)), 4)
    except Exception:
        skewness = round(float(clean.skew()), 4)

    return {
        "min": round(float(clean.min()), 4),
        "max": round(float(clean.max()), 4),
        "mean": round(float(clean.mean()), 4),
        "median": round(float(clean.median()), 4),
        "std": round(float(clean.std()), 4),
        "outliers_count": int(len(outliers)),
        "outliers_pct": round(len(outliers) / len(clean) * 100, 2),
        "skewness": skewness,
    }, distribution


def _profile_category(series: pd.Series) -> tuple[list[dict], list[str]]:
    non_null = series.dropna().astype(str)
    issues = []

    # Top 10 values
    top_10 = non_null.value_counts().head(10)
    top_values = [{"value": str(k), "count": int(v)} for k, v in top_10.items()]

    # Case inconsistencies
    lowered = non_null.str.strip().str.lower()
    grouped = non_null.groupby(lowered)
    case_issues = [
        vals.unique().tolist()
        for _, vals in grouped
        if vals.nunique() > 1
    ]
    if case_issues:
        examples = ", ".join(f'"{"/".join(g[:3])}"' for g in case_issues[:3])
        issues.append(f"Incohérences de casse détectées : {examples}")

    # Leading/trailing whitespace
    has_spaces = (non_null != non_null.str.strip()).sum()
    if has_spaces > 0:
        issues.append(f"{has_spaces} valeur(s) avec espaces superflus (leading/trailing)")

    return top_values, issues


def _profile_datetime(series: pd.Series) -> tuple[dict, list[str]]:
    issues = []
    parsed = pd.to_datetime(series, errors="coerce", infer_datetime_format=True)
    non_null = parsed.dropna()

    if len(non_null) == 0:
        return {}, issues

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    future_dates = non_null[non_null > now]
    if len(future_dates) > 0:
        pct = round(len(future_dates) / len(non_null) * 100, 2)
        issues.append(f"{len(future_dates)} date(s) dans le futur ({pct}%)")

    return {
        "min": str(non_null.min()),
        "max": str(non_null.max()),
        "future_count": int(len(future_dates)),
        "future_pct": round(len(future_dates) / len(non_null) * 100, 2),
    }, issues


def _build_column_issues(col_name: str, col_type: str, null_pct: float, duplicate_pct: float, extra_issues: list[str]) -> list[str]:
    issues = []
    if null_pct >= 10:
        issues.append(f"{null_pct}% de valeurs nulles")
    elif null_pct > 0:
        issues.append(f"{null_pct}% de valeurs nulles")
    if duplicate_pct >= 20:
        issues.append(f"{duplicate_pct}% de valeurs dupliquées (hors nulls)")
    issues.extend(extra_issues)
    return issues


def profile_dataframe(df: pd.DataFrame) -> dict:
    n_rows, n_cols = df.shape

    # File-level metrics
    dup_mask = df.duplicated()
    dup_rows = int(dup_mask.sum())
    dup_rows_pct = round(dup_rows / max(n_rows, 1) * 100, 2)

    constant_columns = [
        str(col) for col in df.columns
        if df[col].nunique(dropna=True) <= 1
    ]

    total_null_pct = round(df.isna().mean(axis=None) * 100, 2)

    # Global issues
    overview_issues = []
    if dup_rows > 0:
        overview_issues.append({
            "level": "critical" if dup_rows_pct >= 5 else "warning",
            "message": f"{dup_rows} lignes dupliquées exactes ({dup_rows_pct}%)",
        })
    if total_null_pct >= 15:
        overview_issues.append({
            "level": "critical",
            "message": f"Taux global de nulls élevé : {total_null_pct}%",
        })
    elif total_null_pct > 0:
        overview_issues.append({
            "level": "warning",
            "message": f"Taux global de nulls : {total_null_pct}%",
        })
    for col in constant_columns:
        overview_issues.append({
            "level": "info",
            "message": f"Colonne '{col}' constante — peut être supprimée",
        })

    # Per-column profiling
    columns = []
    for col in df.columns:
        series = df[col]
        col_type = infer_type(series)
        n_null = int(series.isna().sum())
        null_p = _null_pct(series)
        dup_p = _duplicate_pct(series)
        unique_count = int(series.nunique(dropna=True))

        extra_issues = []
        stats = None
        distribution = None
        top_values = None
        date_stats = None

        if col_type == "numeric":
            result = _profile_numeric(series)
            if result:
                stats, distribution = result
                if stats["outliers_count"] > 0:
                    extra_issues.append(
                        f"{stats['outliers_count']} outlier(s) détecté(s) via IQR ({stats['outliers_pct']}%)"
                    )

        elif col_type == "category":
            top_values, cat_issues = _profile_category(series)
            extra_issues.extend(cat_issues)

        elif col_type == "datetime":
            date_stats, dt_issues = _profile_datetime(series)
            extra_issues.extend(dt_issues)

        col_issues = _build_column_issues(str(col), col_type, null_p, dup_p, extra_issues)

        col_entry: dict = {
            "name": str(col),
            "type": col_type,
            "null_pct": null_p,
            "null_count": n_null,
            "unique_count": unique_count,
            "duplicate_pct": dup_p,
            "issues": col_issues,
        }
        if stats is not None:
            col_entry["stats"] = stats
        if distribution is not None:
            col_entry["distribution"] = distribution
        if top_values is not None:
            col_entry["top_values"] = top_values
        if date_stats:
            col_entry["date_stats"] = date_stats

        columns.append(col_entry)

    return {
        "file_info": {
            "filename": "",           # filled by caller
            "rows": n_rows,
            "columns": n_cols,
            "size_kb": 0,             # filled by caller
            "encoding": "",           # filled by caller
            "is_limited": False,      # filled by caller
        },
        "overview": {
            "total_null_pct": total_null_pct,
            "duplicate_rows": dup_rows,
            "duplicate_rows_pct": dup_rows_pct,
            "constant_columns": constant_columns,
            "issues": overview_issues,
        },
        "columns": columns,
    }
