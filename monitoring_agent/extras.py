"""Zusaetzliche Auswertungen: Pumpenlaufzeiten, Datenverfuegbarkeit, Energieeinsparpotenzial."""

from __future__ import annotations

import pandas as pd

from .config import COLUMNS
from .metrics import daily_consumption
from .settings import Thresholds

PUMP_COLS = {"Stat. Heizung Geb.06": "Stat. Heizung Geb.06 Pumpe", "FBH Geb.06": "FBH Geb.06 Pumpe"}
STEP_HOURS = 0.25


def pump_runtime_monthly(df: pd.DataFrame) -> pd.DataFrame:
    """Laufzeit der Heizkreispumpen in Stunden je Monat (15-Min-Raster)."""
    out = {label: df[col].resample("MS").sum() * STEP_HOURS for label, col in PUMP_COLS.items()}
    return pd.DataFrame(out)


def availability_daily(df: pd.DataFrame) -> pd.DataFrame:
    """Anzahl fehlerhafter Zeitschritte (fehlend oder exakt 0 bei Temperaturkanaelen) je Spalte und Tag."""
    bad = pd.DataFrame(index=df.index)
    for c in COLUMNS:
        s = df[c.short]
        is_bad = s.isna()
        if c.role in ("vl", "rl", "soll_vl"):
            is_bad |= s == 0
        bad[c.short] = is_bad
    return bad.resample("D").sum()


def savings_potential(df: pd.DataFrame, th: Thresholds) -> pd.DataFrame:
    """Grobe Abschaetzung des Einsparpotenzials mit ausdruecklich genannten Annahmen."""
    days = max((df.index.max() - df.index.min()).days + 1, 1)
    to_year = 365 / days

    heat_daily = daily_consumption(df, "Zähler 019 – WMZ")
    aul_daily = df["RLT KL01 Außenluft"].resample("D").mean()
    warm_days = aul_daily[aul_daily > th.heizgrenze_aul].index
    heat_warm = heat_daily.reindex(warm_days).sum()
    heat_total = heat_daily.sum()

    fans = sum(daily_consumption(df, c).sum() for c in ("Zähler 021 – Strom Abluft", "Zähler 022 – Strom Zuluft"))

    heat_save = heat_warm * th.heat_avoid_share * to_year
    fan_save = fans * (th.rlt_night_hours / 24) * th.rlt_night_reduction * to_year
    total_energy_year = (heat_total + fans) * to_year

    rows = [
        {"Maßnahme": f"Heizgrenze bei {th.heizgrenze_aul:.0f} °C Außentemperatur",
         "Annahme": f"{th.heat_avoid_share*100:.0f} % des Wärmeverbrauchs an Tagen mit Tagesmittel > {th.heizgrenze_aul:.0f} °C sind vermeidbar",
         "Einsparung kWh/a": heat_save, "Kosten €/a": heat_save * th.heat_price},
        {"Maßnahme": "RLT-Ventilatoren: Nachtabsenkung",
         "Annahme": f"{th.rlt_night_hours:.0f} h/Nacht mit {th.rlt_night_reduction*100:.0f} % weniger Ventilatorstrom",
         "Einsparung kWh/a": fan_save, "Kosten €/a": fan_save * th.power_price},
    ]
    out = pd.DataFrame(rows)
    total = {"Maßnahme": "Summe", "Annahme": f"Bezug: gemessener Gesamtverbrauch {total_energy_year:,.0f} kWh/a (Wärme + Ventilatorstrom)".replace(",", "."),
             "Einsparung kWh/a": out["Einsparung kWh/a"].sum(), "Kosten €/a": out["Kosten €/a"].sum()}
    out = pd.concat([out, pd.DataFrame([total])], ignore_index=True)
    out["Anteil %"] = out["Einsparung kWh/a"] / total_energy_year * 100
    return out.round({"Einsparung kWh/a": 0, "Kosten €/a": 0, "Anteil %": 1})
