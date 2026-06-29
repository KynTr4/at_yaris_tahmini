"""Central, reversible country/track scope for production race processing."""
from __future__ import annotations

import os
import re
import sqlite3
import unicodedata
from typing import Any

SUPPORTED_COUNTRIES = tuple(
    value.strip().upper() for value in os.environ.get("SUPPORTED_COUNTRIES", "TR,ALL").split(",") if value.strip()
)
ENABLE_FOREIGN_RACES = os.environ.get("ENABLE_FOREIGN_RACES", "true").lower() in {"1", "true", "yes", "on"}

DOMESTIC_TRACKS = {
    "ISTANBUL", "IZMIR", "ANKARA", "ADANA", "ANTALYA", "BURSA",
    "DIYARBAKIR", "ELAZIG", "KOCAELI", "SANLIURFA",
}
TRACK_ALIASES = {
    "VELIEFENDI": "İstanbul", "SIRINYER": "İzmir", "YESILOBA": "Adana",
    "OSMANGAZI": "Bursa", "KARTEPE": "Kocaeli", "75. YIL": "Ankara",
}


def fold(value: Any) -> str:
    text = str(value or "")
    if any(marker in text for marker in ("Ã", "Ä", "Å")):
        try:
            text = text.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch)).upper().strip()


def clean_track(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "Bilinmiyor")).strip()
    text = re.sub(r"\s*[(]\s*\d+[.]?\s*Y[.]?G[.]?\s*[)]\s*$", "", text, flags=re.I)
    text = re.sub(r"\s*[(][^)]*Yar[ıi]ş\s+G[üu]n[üu][^)]*[)]\s*$", "", text, flags=re.I)
    text = re.sub(r"\s*[(][^)]*[)]\s*$", "", text).strip()
    normalized = fold(text)
    for alias, canonical in TRACK_ALIASES.items():
        if normalized.startswith(alias):
            return canonical
    return text or "Bilinmiyor"


def is_turkey_track(value: Any) -> bool:
    normalized = fold(clean_track(value))
    base = normalized.split()[0] if normalized else ""
    return base in DOMESTIC_TRACKS


def track_key(value: Any) -> str:
    return fold(clean_track(value))


def normalize_country(value: str | None = None) -> str:
    country = (value or "ALL").upper()
    if country == "ALL":
        return country
    if country not in SUPPORTED_COUNTRIES:
        raise ValueError(f"country must be one of: {', '.join(SUPPORTED_COUNTRIES)}")
    return country


def track_in_country(track: Any, country: str = "ALL") -> bool:
    country = normalize_country(country)
    return True if country == "ALL" else is_turkey_track(track)


def configure_sqlite(connection: sqlite3.Connection) -> None:
    connection.create_function("is_turkey_track", 1, lambda value: int(is_turkey_track(value)), deterministic=True)
    connection.create_function("track_key", 1, track_key, deterministic=True)
