"""Erkennung einzelner Anomalie-Zeitpunkte, die als Marker in die Diagramme eingezeichnet werden."""

from __future__ import annotations

import pandas as pd

AKTIV_SCHWELLE_VL = 25.0
DELTA_T_MIN = 2.0


def zero_dropouts(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    """Zeitpunkte, an denen mindestens eine der Spalten exakt 0 meldet (Sensor-Aussetzer)."""
    mask = (df[cols] == 0).any(axis=1)
    return df.index[mask].to_series()


def meter_resets(df: pd.DataFrame, col: str) -> pd.Series:
    """Zeitpunkte mit rückläufigem Zählerstand."""
    diffs = df[col].dropna().diff()
    return diffs.index[diffs < 0].to_series()


def low_delta_t(df: pd.DataFrame, vl_col: str, rl_col: str) -> pd.Series:
    """Zeitpunkte mit aktivem Heizbetrieb (VL > Schwelle) und Spreizung unter DELTA_T_MIN."""
    dt = df[vl_col] - df[rl_col]
    mask = (df[vl_col] > AKTIV_SCHWELLE_VL) & (dt < DELTA_T_MIN)
    return df.index[mask].to_series()
