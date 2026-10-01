"""Abgeleitete Kennwerte: Temperaturspreizung (Delta T), Tageswerte aus Zaehlerstaenden und die
geordnete Dauerlinie der thermischen Leistung."""

from __future__ import annotations

import numpy as np
import pandas as pd


def delta_t(df: pd.DataFrame, vl_col: str, rl_col: str) -> pd.Series:
    return df[vl_col] - df[rl_col]


def daily_consumption(df: pd.DataFrame, meter_col: str) -> pd.Series:
    """Taeglicher Verbrauch aus einem kumulierten Zaehlerstand: letzter minus
    erster gueltiger Wert je Kalendertag."""
    daily = df[meter_col].resample("D").agg(["first", "last"])
    return (daily["last"] - daily["first"]).rename(meter_col)


def thermal_power(df: pd.DataFrame, meter_col: str) -> pd.Series:
    """Momentane thermische Leistung (kW) aus dem kumulierten Waermemengenzaehler (kWh): Differenz zweier
    aufeinanderfolgender gueltiger Zaehlerstaende geteilt durch die tatsaechlich verstrichene Zeit (nicht
    einfach 15 Minuten angenommen - bei Luecken im Datensatz waere das falsch). Ruecklaeufige Zaehlerstaende
    (Reset/Uebertragungsfehler, siehe quality.py) wuerden eine negative Leistung ergeben und werden auf 0
    begrenzt."""
    s = df[meter_col].dropna()
    dt_hours = s.index.to_series().diff().dt.total_seconds() / 3600
    power = (s.diff() / dt_hours).clip(lower=0)
    valid = power.notna() & dt_hours.notna() & (dt_hours > 0)
    return power[valid].rename("kW")


def duration_curve(df: pd.DataFrame, meter_col: str) -> pd.DataFrame:
    """Geordnete Dauerlinie: thermische Leistung absteigend sortiert, x-Achse = Betriebsstunden, in
    denen diese Leistung erreicht oder ueberschritten wird. Jeder Messwert zaehlt mit der tatsaechlich
    verstrichenen Zeit bis zum naechsten gueltigen Wert (nicht pauschal 15 Minuten), damit Luecken im
    Datensatz die Kurve nicht verfaelschen."""
    s = df[meter_col].dropna()
    dt_hours = s.index.to_series().diff().dt.total_seconds() / 3600
    power = (s.diff() / dt_hours).clip(lower=0)
    valid = power.notna() & dt_hours.notna() & (dt_hours > 0)
    power, dt_hours = power[valid], dt_hours[valid]
    order = power.sort_values(ascending=False).index
    power_sorted, dt_sorted = power.loc[order], dt_hours.loc[order]
    hours_cum = dt_sorted.cumsum()
    return pd.DataFrame({"Stunden": hours_cum.to_numpy(), "Leistung_kW": power_sorted.to_numpy()})


def duration_curve_percentiles(curve: pd.DataFrame, fractions: tuple[float, ...] = (0.01, 0.05, 0.10, 0.20)) -> dict[float, tuple[float, float]]:
    """Fuer je einen Anteil der Betriebszeit (z.B. 0.05 = 5 %): die Leistung, die in genau diesem
    Anteil der Zeit erreicht oder ueberschritten wird, und die zugehoerige Stundenzahl. Interpoliert
    zwischen den vorhandenen Stuetzstellen der Dauerlinie."""
    if curve.empty:
        return {f: (0.0, 0.0) for f in fractions}
    total_hours = float(curve["Stunden"].iloc[-1])
    out = {}
    for f in fractions:
        hours = f * total_hours
        power = float(np.interp(hours, curve["Stunden"].to_numpy(), curve["Leistung_kW"].to_numpy()))
        out[f] = (hours, power)
    return out
