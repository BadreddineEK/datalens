import io
import os

import chardet
import pandas as pd
from fastapi import HTTPException


MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
ALLOWED_MIME_TYPES = {"text/csv", "application/csv", "text/plain", "application/octet-stream"}
ALLOWED_EXTENSIONS = {".csv"}


def validate_file(filename: str, content: bytes) -> None:
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Format invalide. Seuls les fichiers .csv sont acceptés.")
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="Fichier trop volumineux (max 50 MB).")
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Fichier vide.")


def detect_encoding(content: bytes) -> str:
    result = chardet.detect(content)
    encoding = result.get("encoding") or "utf-8"
    # Normalize common aliases
    encoding = encoding.lower().replace("-", "_")
    if encoding in {"ascii", "utf_8_sig"}:
        encoding = "utf-8"
    return encoding


def _try_parse(content: bytes, encoding: str, sep: str) -> pd.DataFrame | None:
    try:
        df = pd.read_csv(io.BytesIO(content), sep=sep, encoding=encoding, on_bad_lines="skip", low_memory=False)
        if df.shape[1] > 1:
            return df
    except Exception:
        pass
    return None


def parse_csv(content: bytes) -> tuple[pd.DataFrame, str]:
    encoding = detect_encoding(content)

    # Try detected encoding first, then fallback
    encodings_to_try = [encoding]
    if encoding != "utf-8":
        encodings_to_try.append("utf-8")
    if "latin" not in encoding and "1252" not in encoding:
        encodings_to_try.append("latin-1")

    separators = [",", ";", "\t", "|"]

    for enc in encodings_to_try:
        for sep in separators:
            df = _try_parse(content, enc, sep)
            if df is not None:
                return df, enc

    # Last resort: single-column CSV
    try:
        df = pd.read_csv(io.BytesIO(content), encoding="utf-8", on_bad_lines="skip", low_memory=False)
        return df, "utf-8"
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Impossible de lire le fichier CSV : {exc}") from exc
