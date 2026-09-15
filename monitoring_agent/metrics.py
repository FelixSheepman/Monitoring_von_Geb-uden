"""Abgeleitete Kennwerte: Temperaturspreizung (Delta T) und Tageswerte aus Zaehlerstaenden."""

from __future__ import annotations

import pandas as pd


def delta_t(df: pd.DataFrame, vl_col: str, rl_col: str) -> pd.Series:
    return df[vl_col] - df[rl_col]


def daily_consumption(df: pd.DataFrame, meter_col: str) -> pd.Series:
    """Taeglicher Verbrauch aus einem kumulierten Zaehlerstand: letzter minus
    erster gueltiger Wert je Kalendertag."""
    daily = df[meter_col].resample("D").agg(["first", "last"])
    return (daily["last"] - daily["first"]).rename(meter_col)
