"""
Automatisierte Auswertungstexte - Ersatz fuer die manuelle Interpretation in
Kapitel 6.4 der Hausarbeit ("Auswertung der Ergebnisse").

Anders als die Datenpruefung (quality.py), die einzelne Spalten prueft,
verknuepfen diese Funktionen mehrere Groessen zu einer fachlichen Aussage -
z.B. "Heizkurve zu flach/ohne Heizgrenze" aus Aussentemperatur + Vorlauf.
Alle Zahlen im Text werden live aus den Daten berechnet (keine Textbausteine
mit festen Werten), damit der Text bei neuen Messdaten automatisch mitzieht.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .metrics import daily_consumption
from .settings import Thresholds

HEIZGRENZE_AUL = 15.0  # °C - ueblicher Schwellenwert, ab dem Heizbetrieb einstellbar waere
AKTIV_SCHWELLE_VL = 25.0  # °C - Vorlauftemperatur, ab der von aktivem Heizbetrieb ausgegangen wird
NIEDRIGTEMP_FBH_GRENZE = 40.0  # °C - typische Auslegungsgrenze fuer Fussbodenheizungen


@dataclass
class NarrativeBlock:
    figure_keys: list[str]
    heading: str
    text: str


def _heizkurve_text(df: pd.DataFrame, aul_col: str, vl_col: str, th: Thresholds) -> NarrativeBlock:
    sub = df[[aul_col, vl_col]].dropna()
    slope, intercept = np.polyfit(sub[aul_col], sub[vl_col], 1)

    above = sub[sub[aul_col] > th.heizgrenze_aul]
    frac_still_heating = (above[vl_col] > th.aktiv_schwelle_vl).mean() if len(above) else float("nan")
    mean_vl_above = above[vl_col].mean() if len(above) else float("nan")

    text = (
        f"Die Regressionsgerade der Heizkurve fällt mit einer Steigung von {slope:.2f} K "
        f"Vorlauftemperatur je K Außentemperatur ({intercept:.1f} °C bei 0 °C Außentemperatur). "
        f"Oberhalb von {th.heizgrenze_aul:.0f} °C Außentemperatur – ab der ein Heizbetrieb energetisch "
        f"i. d. R. nicht mehr erforderlich ist – liegt die Vorlauftemperatur in "
        f"{frac_still_heating*100:.0f} % der Zeitschritte weiterhin über {th.aktiv_schwelle_vl:.0f} °C "
        f"(Mittelwert {mean_vl_above:.1f} °C). Das deutet auf eine fehlende oder zu hoch angesetzte "
        f"Heizgrenztemperatur in der Regelung hin."
    )
    return NarrativeBlock(["heizkurve"], "Heizkurve ohne erkennbare Heizgrenze", text)


def _rlt_betrieb_text(df: pd.DataFrame, vl_col: str, meter_ab: str, meter_zu: str) -> NarrativeBlock:
    series = df[vl_col].dropna()
    hourly_profile = series.groupby(series.index.hour).mean()
    day_night_spread = hourly_profile.max() - hourly_profile.min()

    daily_ab = daily_consumption(df, meter_ab)
    is_weekend = daily_ab.index.dayofweek >= 5
    weekday_mean = daily_ab[~is_weekend].mean()
    weekend_mean = daily_ab[is_weekend].mean()
    weekend_diff_pct = (weekend_mean - weekday_mean) / weekday_mean * 100 if weekday_mean else float("nan")

    text = (
        f"Der mittlere Tagesgang der primären RLT-Vorlauftemperatur schwankt über 24 Stunden nur um "
        f"{day_night_spread:.1f} K (Minimum {hourly_profile.min():.1f} °C, Maximum {hourly_profile.max():.1f} °C) "
        f"– eine ausgeprägte Nachtabsenkung ist nicht erkennbar. Der tägliche Stromverbrauch des "
        f"Abluftventilators unterscheidet sich am Wochenende mit {weekend_mean:.1f} kWh/Tag nur um "
        f"{weekend_diff_pct:+.1f} % vom Werktagsmittel ({weekday_mean:.1f} kWh/Tag), was auf einen "
        f"durchgehenden Dauerbetrieb der RLT-Anlage auch außerhalb der Kernnutzungszeiten schließen lässt."
    )
    return NarrativeBlock(
        ["carpet_rlt_vl", "carpet_rlt_rl", "strom_rlt_taeglich"],
        "RLT-Anlage im Dauerbetrieb ohne erkennbare Nachtabsenkung", text,
    )


def _zonenvergleich_text(df: pd.DataFrame, fbh_cols: list[tuple[str, str]],
                          ref_col: str, ref_label: str, th: Thresholds) -> NarrativeBlock:
    lines = []
    worst_label, worst_p95 = None, -1
    for label, col in fbh_cols:
        p95 = df[col].quantile(0.95)
        if p95 > worst_p95:
            worst_p95, worst_label = p95, label
    ref_p95 = df[ref_col].quantile(0.95)

    text = (
        f"Für Niedertemperatursysteme wie Fußbodenheizungen gilt eine Auslegungsgrenze von rund "
        f"{th.fbh_limit:.0f} °C Vorlauftemperatur. Die Zone „{worst_label}“ überschreitet "
        f"dieses Niveau im 95. Perzentil mit {worst_p95:.1f} °C deutlich und nähert sich damit dem "
        f"Temperaturniveau der {ref_label} ({ref_p95:.1f} °C im 95. Perzentil). Dies deutet auf einen "
        f"fehlerhaften hydraulischen Abgleich oder eine übersteuerte Mischerregelung in dieser Zone hin."
    )
    return NarrativeBlock(["zonenvergleich"], "Hydraulischer Abgleich: Auffällig hohe FBH-Vorlauftemperatur", text)


def _delta_t_text(df: pd.DataFrame, pairs: list[tuple[str, str, str]], th: Thresholds) -> NarrativeBlock:
    parts = []
    for label, vl_col, rl_col in pairs:
        dt = df[vl_col] - df[rl_col]
        active = df[vl_col] > th.aktiv_schwelle_vl
        frac_low = (dt[active] < th.delta_t_min).mean() if active.any() else float("nan")
        parts.append(f"{label} in {frac_low*100:.0f} % der aktiven Betriebszeit")

    text = (
        "Bei effizientem Betrieb sollte die Temperaturspreizung zwischen Vor- und Rücklauf während "
        f"aktiver Heizphasen deutlich über {th.delta_t_min:.0f} Kelvin liegen. In den vorliegenden Daten liegt sie bei "
        f"{' bzw. '.join(parts)} unterhalb dieses Werts. Wiederkehrende Phasen mit sehr geringer "
        "Spreizung sprechen für ungeregelt weiterlaufende Umwälzpumpen ohne Differenzdruckregelung "
        "und damit für vermeidbaren Pumpenstromverbrauch bei gleichzeitig ineffizienter Wärmeübergabe."
    )
    return NarrativeBlock(["delta_t"], "Geringe Temperaturspreizung deutet auf ungeregelte Pumpen hin", text)


def _sommerbetrieb_text(df: pd.DataFrame, meter_col: str) -> NarrativeBlock:
    daily = daily_consumption(df, meter_col)
    summer = daily[daily.index.month.isin([6, 7, 8])]
    winter = daily[daily.index.month.isin([12, 1, 2])]
    ratio_pct = summer.mean() / winter.mean() * 100 if winter.mean() else float("nan")

    text = (
        f"Der mittlere tägliche Wärmeverbrauch sinkt in den Sommermonaten (Juni–August) auf "
        f"{summer.mean():.1f} kWh/Tag gegenüber {winter.mean():.1f} kWh/Tag im Winter "
        f"(Dezember–Februar), also auf rund {ratio_pct:.1f} % des winterlichen Niveaus. Der Verbrauch "
        "fällt jedoch nicht auf null, was auf fortlaufende Zirkulations- bzw. Leitungsverluste oder "
        "unnötigen Restbetrieb außerhalb der eigentlichen Heizperiode hindeutet."
    )
    return NarrativeBlock(["waerme_taeglich"], "Restwärmeverbrauch außerhalb der Heizperiode", text)


def _pumpen_text(df: pd.DataFrame, pump_cols: list[tuple[str, str]], meter_col: str) -> NarrativeBlock:
    parts, summer_shares, winter_shares = [], [], []
    for label, col in pump_cols:
        on = df[col].dropna()
        summer = on[on.index.month.isin([6, 7, 8])].mean()
        winter = on[on.index.month.isin([12, 1, 2])].mean()
        summer_shares.append(summer)
        winter_shares.append(winter)
        parts.append(f"{label} im Winter {winter*100:.0f} %, im Sommer {summer*100:.0f} %")
    summer_avg = sum(summer_shares) / len(summer_shares)
    daily = daily_consumption(df, meter_col)
    summer_heat = daily[daily.index.month.isin([6, 7, 8])].mean()

    if summer_avg > 0.8:
        heading = "Heizkreispumpen laufen ganzjährig durch"
        judgement = ("Eine witterungs- oder bedarfsabhängige Pumpenabschaltung (Sommerabschaltung) ist nicht "
                     "erkennbar; sie würde Pumpenstrom und Zirkulationsverluste vermeiden.")
    else:
        heading = "Heizkreispumpen mit Sommerabschaltung, aber Restlaufzeiten"
        judgement = (f"Eine Sommerabschaltung ist erkennbar; im Sommermittel laufen die Pumpen jedoch noch zu "
                     f"{summer_avg*100:.0f} % der Zeit. Jede weitere Verkürzung dieser Restlaufzeiten spart Pumpenstrom "
                     "und Zirkulationsverluste.")

    jun = {}
    for label, col in pump_cols:
        on = df[col].dropna()
        for year in sorted(set(on.index.year)):
            m = on[(on.index.year == year) & (on.index.month == 6)]
            if len(m) > 96 * 20:
                jun.setdefault(label, {})[year] = m.mean() * 100
    changes = [f"{lbl}: Juni {y0} {v[y0]:.0f} % gegenüber Juni {y1} {v[y1]:.0f} %"
               for lbl, v in jun.items() if len(v) >= 2 for y0, y1 in [(min(v), max(v))] if abs(v[y1] - v[y0]) > 15]
    change_text = (" Auffällig ist der Vergleich derselben Jahreszeit: " + "; ".join(changes) +
                   " – die Pumpenregelung verhält sich in den beiden Jahren unterschiedlich.") if changes else ""

    text = ("Anteil der Betriebszeit der Heizkreispumpen: " + "; ".join(parts) +
            f". Der mittlere Wärmeverbrauch im Sommer beträgt {summer_heat:.1f} kWh/Tag. " + judgement + change_text)
    return NarrativeBlock(["pumpenlaufzeit"], heading, text)


def build_narrative(df: pd.DataFrame, th: Thresholds | None = None) -> list[NarrativeBlock]:
    """Erzeugt alle Auswertungstexte fuer den vorliegenden (vollaufgeloesten) Datensatz."""
    th = th or Thresholds()
    return [
        _heizkurve_text(df, "RLT KL01 Außenluft", "Stat. Heizung Geb.06 VL (Ist)", th),
        _rlt_betrieb_text(df, "RLT primär VL", "Zähler 021 – Strom Abluft", "Zähler 022 – Strom Zuluft"),
        _zonenvergleich_text(df, [
            ("FBH Geb.08 KI-Räume", "FBH Geb.08 KI-Räume VL"),
            ("FBH Geb.08 Intensivpflege", "FBH Geb.08 Intensivpflege VL"),
            ("FBH Geb.06", "FBH Geb.06 VL (Ist)"),
        ], "Stat. Heizung Geb.06 VL (Ist)", "statischen Heizung Geb.06", th),
        _delta_t_text(df, [
            ("Stat. Heizung Geb.06", "Stat. Heizung Geb.06 VL (Ist)", "Stat. Heizung Geb.06 RL"),
            ("FBH Geb.06", "FBH Geb.06 VL (Ist)", "FBH Geb.06 RL"),
        ], th),
        _sommerbetrieb_text(df, "Zähler 019 – WMZ"),
        _pumpen_text(df, [("Stat. Heizung Geb.06", "Stat. Heizung Geb.06 Pumpe"), ("FBH Geb.06", "FBH Geb.06 Pumpe")],
                     "Zähler 019 – WMZ"),
    ]
