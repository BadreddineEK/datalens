from statistics import mean


_SCORE_LABELS = [
    (80, "Bon"),
    (60, "Acceptable"),
    (40, "À corriger"),
    (0, "Critique"),
]


def compute_score(profile: dict) -> tuple[int, str]:
    """Return (score 0-100, label)."""
    score = 100.0

    columns = profile.get("columns", [])
    overview = profile.get("overview", {})

    # Penalty: null values — up to -40 pts
    if columns:
        avg_null = mean(col["null_pct"] for col in columns)
        score -= (avg_null / 100) * 40

    # Penalty: duplicate rows — up to -20 pts
    dup_pct = overview.get("duplicate_rows_pct", 0.0)
    score -= (dup_pct / 100) * 20

    # Penalty: outliers on numeric columns — up to -20 pts
    numeric_cols = [
        col for col in columns
        if col.get("type") == "numeric" and col.get("stats")
    ]
    if numeric_cols:
        avg_outlier = mean(col["stats"]["outliers_pct"] for col in numeric_cols)
        score -= (avg_outlier / 100) * 20

    # Penalty: constant columns — -2 pts each, max -20 pts
    constant_penalty = min(len(overview.get("constant_columns", [])) * 2, 20)
    score -= constant_penalty

    final = max(0, round(score))

    label = "Critique"
    for threshold, lbl in _SCORE_LABELS:
        if final >= threshold:
            label = lbl
            break

    return final, label
