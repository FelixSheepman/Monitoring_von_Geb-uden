"""
Generische Auswertung fuer einen einzelnen Heizkreis (siehe buildings.py).

Ergaenzt die feste Kap.-6-Auswertung (die immer den ganzen Datensatz zeigt) um eine
zweite, unabhaengige Sicht: Datenpruefung, Kennzahlen und Diagramme nur fuer die
Spalten eines ausgewaehlten Heizkreises. Baut auf denselben, bereits fuer den
Gesamtbericht genutzten Grafikfunktionen auf (figures.py), damit Darstellung und
Farbgebung konsistent bleiben.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import figures as fx
from .buildings import Heizkreis
from .extras import STEP_HOURS
from .settings import Thresholds


@dataclass
class CircuitFigure:
    title: str
    figure: object  # plotly.graph_objects.Figure
    caption: str


def circuit_quality(quality_df: pd.DataFrame, kreis: Heizkreis) -> pd.DataFrame:
    """Teilmenge der Tabelle 1 (Datenprüfung) fuer die Spalten dieses Heizkreises.
    "Bezeichnung" in quality_df ist der lange Original-Excel-Name (siehe quality.quality_to_dataframe)."""
    names = {c.excel_name for c in (*kreis.columns, *kreis.extra_columns)}
    return quality_df[quality_df["Bezeichnung"].isin(names)]


def circuit_stats(df: pd.DataFrame, kreis: Heizkreis) -> dict[str, str]:
    """Kurze Kennzahlen fuer die Kachelanzeige (nur fuer tatsaechlich vorhandene Rollen)."""
    stats: dict[str, str] = {}
    vl, rl, soll, pump = kreis.col("vl"), kreis.col("rl"), kreis.col("soll_vl"), kreis.col("pump")
    if vl is not None and df[vl.short].notna().any():
        s = df[vl.short]
        stats["Vorlauf Min/Max"] = f"{s.min():.1f} / {s.max():.1f} °C"
    if rl is not None and df[rl.short].notna().any():
        s = df[rl.short]
        stats["Rücklauf Min/Max"] = f"{s.min():.1f} / {s.max():.1f} °C"
    if vl is not None and rl is not None:
        dt = (df[vl.short] - df[rl.short]).dropna()
        if len(dt):
            stats["Delta T (Median)"] = f"{dt.median():.1f} K"
    if soll is not None and vl is not None:
        diff = (df[vl.short] - df[soll.short]).dropna()
        if len(diff):
            stats["Ist − Soll (Median)"] = f"{diff.median():+.1f} K"
    if pump is not None and df[pump.short].notna().any():
        stats["Pumpe: Laufzeitanteil"] = f"{df[pump.short].mean() * 100:.0f} %"
    return stats


AUL_COLUMN = "RLT KL01 Außenluft"  # einzige Aussentemperatur im Datensatz, gilt fuer die gesamte Anlage


def _component_limit(kreis: Heizkreis, th: Thresholds) -> tuple[float, str] | None:
    """Zulaessige Vorlauftemperatur je Komponenten-Art (Annahme, siehe settings.Thresholds); fuer die
    RLT-Anlage (kein Heizkoerper/keine Fussbodenheizung im eigentlichen Sinn) gibt es keinen Wert."""
    if "Fußbodenheizung" in kreis.art:
        return th.fbh_limit, "Zulässige Vorlauftemp. (Fußbodenheizung)"
    if "RLT" in kreis.art:
        return None
    return th.heizkoerper_limit, "Zulässige Vorlauftemp. (Heizkörper)"


def circuit_figures(df: pd.DataFrame, kreis: Heizkreis, carpet_granularity: str, carpet_anchor: pd.Timestamp,
                    th: Thresholds | None = None) -> list[CircuitFigure]:
    """Diagramme, die sich aus den in diesem Heizkreis tatsächlich vorhandenen Rollen ergeben.
    `carpet_granularity` (Jahr/Monat/Woche/Tag) und `carpet_anchor` legen das Zeitfenster des Carpetplots
    fest (siehe figures.carpet_window). `th` liefert die zulässige Vorlauftemperatur, die als Grenzlinie
    in die Vorlauf-Diagramme eingezeichnet wird (siehe _component_limit)."""
    th = th or Thresholds()
    figs: list[CircuitFigure] = []
    label = kreis.art
    vl, rl = kreis.col("vl"), kreis.col("rl")
    soll, pump = kreis.col("soll_vl"), kreis.col("pump")
    aul, zul = kreis.extra_col("aul"), kreis.extra_col("zul")
    limit = _component_limit(kreis, th)
    limit_note = (f" Die rote gestrichelte Linie ist die zulässige Vorlauftemperatur dieser Komponente "
                 f"({limit[0]:.0f} °C, Annahme – im Einstellungsmenü anpassbar).") if limit else ""

    if soll is not None and vl is not None:
        fig = fx.fig_soll_ist(df, soll.short, vl.short, f"{label}: Soll- vs. Ist-Vorlauf")
        if limit:
            fx.add_component_limit(fig, *limit)
        figs.append(CircuitFigure(
            "Regelgüte", fig,
            "Vergleich der Soll-Vorlauftemperatur mit der gemessenen Ist-Vorlauftemperatur dieses Heizkreises." + limit_note,
        ))
    if vl is not None and rl is not None:
        fig = fx.fig_two_series(df, vl.short, "Vorlauf", rl.short, "Rücklauf", f"{label}: Vorlauf- und Rücklauftemperatur")
        if limit:
            fx.add_component_limit(fig, *limit)
        figs.append(CircuitFigure(
            "Vorlauf und Rücklauf", fig,
            "Zeitlicher Verlauf von Vor- und Rücklauftemperatur dieses Heizkreises." + limit_note,
        ))
        figs.append(CircuitFigure(
            "Temperaturspreizung (Delta T)", fx.fig_delta_t(df, [(label, vl.short, rl.short)],
                                                             f"{label}: Temperaturspreizung (Delta T)"),
            "Differenz zwischen Vor- und Rücklauf als Effizienzindikator der Wärmeübergabe.",
        ))
    if vl is not None:
        series = df[vl.short].dropna()
        if len(series) > 10:
            lo, hi = float(series.quantile(0.01)), float(series.quantile(0.99))
            has_aul = AUL_COLUMN in df.columns and vl.short != AUL_COLUMN
            label_period = fx.carpet_period_label(carpet_granularity, pd.Timestamp(carpet_anchor))
            note = (" Die kleine Zahl in jeder Zelle ist die Außentemperatur (°C) zur selben Uhrzeit."
                    if has_aul and carpet_granularity != "Jahr" else "")
            figs.append(CircuitFigure(
                "Carpetplot Vorlauf", fx.fig_carpet_window(
                    df, vl.short, carpet_granularity, carpet_anchor, f"{label}: Vorlauftemp. {label_period}",
                    zmin=lo, zmax=hi, annotate_col=AUL_COLUMN if has_aul else None, annotate_label="Außentemp."),
                "Farbcodierter Verlauf der Vorlauftemperatur im gewählten Zeitfenster "
                "(Farbskala: 1.–99. Perzentil)." + note,
            ))
    if pump is not None:
        monthly = pd.DataFrame({label: df[pump.short].resample("MS").sum() * STEP_HOURS})
        if monthly[label].sum() > 0:
            figs.append(CircuitFigure(
                "Pumpenlaufzeit", fx.fig_pump_runtime(monthly, f"{label}: Laufzeit der Pumpe (Monatswerte)"),
                "Monatliche Betriebsstunden der Umwälzpumpe; 720 h entsprechen Dauerbetrieb.",
            ))
    if aul is not None and zul is not None:
        figs.append(CircuitFigure(
            "Außenluft und Zuluft", fx.fig_two_series(df, aul.short, "Außenluft", zul.short, "Zuluft",
                                                       f"{label}: Außenluft- und Zulufttemperatur"),
            "Zeitlicher Verlauf von Außenluft- und Zulufttemperatur der zugehörigen RLT-Anlage.",
        ))
    return figs
