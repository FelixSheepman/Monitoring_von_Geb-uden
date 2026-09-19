"""
Orchestriert Datenpruefung, Kennwerte und die 12 Abbildungen aus Kapitel 6 der
Hausarbeit zu einem einzigen Report-Objekt. Wird sowohl vom CLI-Skript als auch
von der Streamlit-App genutzt, damit beide exakt dieselbe Auswertungslogik
verwenden.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import pandas as pd

from . import anomalies as an
from .assessment import build_assessment, data_coverage, measurement_head
from . import figures as fx
from .metrics import daily_consumption
from .extras import availability_daily, pump_runtime_monthly, savings_potential
from .narrative import NarrativeBlock, build_narrative
from .quality import quality_to_dataframe, run_data_quality
from .settings import Thresholds


@dataclass
class FigureEntry:
    key: str
    title: str
    figure: object  # plotly.graph_objects.Figure
    caption: str


@dataclass
class Report:
    df: pd.DataFrame
    quality_df: pd.DataFrame
    figures: list[FigureEntry] = field(default_factory=list)
    narrative: list[NarrativeBlock] = field(default_factory=list)
    savings: pd.DataFrame | None = None
    thresholds: Thresholds | None = None
    head_table: pd.DataFrame | None = None
    coverage: pd.DataFrame | None = None
    assessment: pd.DataFrame | None = None
    timings: dict[str, float] = field(default_factory=dict)
    anomaly_counts: dict[str, int] = field(default_factory=dict)
    carpet_year: int = 2025
    carpet_month: int = 2


def build_report(df: pd.DataFrame, carpet_year: int = 2025, carpet_month: int = 2,
                  display_resample: str | None = None, show_anomalies: bool = False,
                  thresholds: Thresholds | None = None, strict_rules: bool = False) -> Report:
    """`df` ist immer die volle Rohauflösung und wird für Datenprüfung, Carpetplots
    und Tagesverbrauchsberechnungen verwendet (Glätten würde dort Aussetzer/Resets
    verdecken bzw. die Tagesdifferenz-Logik verfälschen). `display_resample`
    (z.B. "h" oder "D") glättet ausschließlich die reinen Zeitverlaufs-Liniendiagramme
    für eine ruhigere Darstellung."""
    th = thresholds or Thresholds()
    timings: dict[str, float] = {}
    t0 = time.perf_counter()
    quality_results = run_data_quality(df, strict=strict_rules, fbh_limit=th.fbh_limit)
    quality_df = quality_to_dataframe(quality_results)
    timings["Datenprüfung"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    df_disp = df.resample(display_resample).mean() if display_resample else df

    figs: list[FigureEntry] = []

    figs.append(FigureEntry(
        "wmz_kumuliert", "Zähler 019 – WMZ (kumuliert)",
        fx.fig_meter_cumulative(df_disp, "Zähler 019 – WMZ", "Zähler 019 – WMZ (kumuliert)"),
        "Kumulierter Zählerstand des Wärmemengenzählers über den gesamten Erfassungszeitraum.",
    ))

    figs.append(FigureEntry(
        "regelguete_stat_heizung", "Regelgüte Stat. Heizung Geb.06: Soll- vs. Ist-Vorlauf",
        fx.fig_soll_ist(df_disp, "Stat. Heizung Geb.06 VL (Soll)", "Stat. Heizung Geb.06 VL (Ist)",
                         "Regelgüte Stat. Heizung Geb.06: Soll- vs. Ist-Vorlauf"),
        "Vergleich der systemseitig berechneten Soll-Vorlauftemperatur mit der gemessenen Ist-Vorlauftemperatur.",
    ))

    figs.append(FigureEntry(
        "heizkurve", "Heizkurve: Außentemp. vs. Vorlauftemp. Geb.06",
        fx.fig_heating_curve(df, "RLT KL01 Außenluft", "Stat. Heizung Geb.06 VL (Ist)",
                              "Heizkurve: Außentemp. vs. Vorlauftemp. Geb.06"),
        "Streudiagramm der Ist-Vorlauftemperatur in Abhängigkeit von der Außentemperatur mit Regressionslinie.",
    ))

    figs.append(FigureEntry(
        "carpet_rlt_vl", f"RLT primär VL-Temp. {carpet_month:02d}/{carpet_year}",
        fx.fig_carpet(df, "RLT primär VL", carpet_year, carpet_month,
                       f"RLT primär VL-Temp. {carpet_month:02d}/{carpet_year}", zmin=20, zmax=65),
        "Carpetplot der primären Vorlauftemperatur der RLT-Anlage, Farbskala fix auf 20–65 °C.",
    ))

    figs.append(FigureEntry(
        "carpet_rlt_rl", f"RLT primär RL-Temp. {carpet_month:02d}/{carpet_year}",
        fx.fig_carpet(df, "RLT primär RL", carpet_year, carpet_month,
                       f"RLT primär RL-Temp. {carpet_month:02d}/{carpet_year}", zmin=20, zmax=65),
        "Carpetplot der primären Rücklauftemperatur der RLT-Anlage, Farbskala fix auf 20–65 °C.",
    ))

    figs.append(FigureEntry(
        "regelguete_fbh", "Regelgüte FBH Geb.06: Soll- vs. Ist-Vorlauf",
        fx.fig_soll_ist(df_disp, "FBH Geb.06 VL (Soll)", "FBH Geb.06 VL (Ist)",
                         "Regelgüte FBH Geb.06: Soll- vs. Ist-Vorlauf"),
        "Vergleich der Soll- mit der Ist-Vorlauftemperatur der Fußbodenheizung Gebäude 06.",
    ))

    figs.append(FigureEntry(
        "zonenvergleich", "Hydraulischer Abgleich: Zonenvergleich Vorlauftemperaturen",
        fx.fig_zone_comparison(df_disp, [
            ("Stat. Heizung Geb.06", "Stat. Heizung Geb.06 VL (Ist)"),
            ("FBH Geb.06", "FBH Geb.06 VL (Ist)"),
            ("FBH Geb.08 KI-Räume", "FBH Geb.08 KI-Räume VL"),
            ("FBH Geb.08 Intensivpflege", "FBH Geb.08 Intensivpflege VL"),
        ], "Hydraulischer Abgleich: Zonenvergleich Vorlauftemperaturen"),
        "Vergleich der Ist-Vorlauftemperaturen von vier Heizkreisen zur Prüfung des hydraulischen Abgleichs.",
    ))

    figs.append(FigureEntry(
        "delta_t", "Effizienz: Temperaturspreizung (Delta T)",
        fx.fig_delta_t(df_disp, [
            ("Stat. Heizung Geb.06", "Stat. Heizung Geb.06 VL (Ist)", "Stat. Heizung Geb.06 RL"),
            ("FBH Geb.06", "FBH Geb.06 VL (Ist)", "FBH Geb.06 RL"),
        ], "Effizienz: Temperaturspreizung (Delta T)"),
        "Temperaturdifferenz zwischen Vor- und Rücklauf als Effizienzindikator der Wärmeübergabe.",
    ))

    figs.append(FigureEntry(
        "rlt_aul_zul", "RLT-Anlage: Außenluft vs. Zuluft",
        fx.fig_two_series(df_disp, "RLT KL01 Außenluft", "Außenluft", "RLT KL01 Zuluft", "Zuluft",
                           "RLT-Anlage: Außenluft vs. Zuluft"),
        "Zeitlicher Verlauf von Außenluft- und Zulufttemperatur der RLT-Anlage.",
    ))

    daily_strom_ab = daily_consumption(df, "Zähler 021 – Strom Abluft")
    daily_strom_zu = daily_consumption(df, "Zähler 022 – Strom Zuluft")
    figs.append(FigureEntry(
        "strom_rlt_taeglich", "Stromverbrauch RLT-Ventilatoren (Tageswerte)",
        fx.fig_daily_lines({
            "Abluftventilator": daily_strom_ab,
            "Zuluftventilator": daily_strom_zu,
        }, "Stromverbrauch RLT-Ventilatoren (Tageswerte)"),
        "Täglicher elektrischer Energieverbrauch der Ab- und Zuluftventilatoren.",
    ))

    daily_waerme = daily_consumption(df, "Zähler 019 – WMZ")
    figs.append(FigureEntry(
        "waerme_taeglich", "Täglicher Wärmeverbrauch",
        fx.fig_daily_bar(daily_waerme, "Täglicher Wärmeverbrauch"),
        "Absoluter, täglich aufsummierter Wärmeverbrauch der gesamten Anlage.",
    ))

    figs.append(FigureEntry(
        "pumpenlaufzeit", "Laufzeit der Heizkreispumpen (Monatswerte)",
        fx.fig_pump_runtime(pump_runtime_monthly(df), "Laufzeit der Heizkreispumpen (Monatswerte)"),
        "Monatliche Betriebsstunden der Heizkreispumpen; 720 h entsprechen Dauerbetrieb.",
    ))
    figs.append(FigureEntry(
        "verfuegbarkeit", "Datenverfügbarkeit je Sensor und Tag",
        fx.fig_availability(availability_daily(df), "Datenverfügbarkeit je Sensor und Tag"),
        "Anzahl fehlender oder auf 0 stehender Zeitschritte (von 96 je Tag) je Spalte und Kalendertag.",
    ))

    anomaly_counts = _apply_anomalies(df, figs, th) if show_anomalies else {}
    timings["Grafiken"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    narrative = build_narrative(df, th)
    savings = savings_potential(df, th)
    t1 = time.perf_counter()
    head_table, coverage = measurement_head(df), data_coverage(df)
    assessment = build_assessment(df, quality_df, savings, th)
    timings["Bewertung"] = time.perf_counter() - t1
    timings["Auswertungstext"] = time.perf_counter() - t0

    return Report(df=df, quality_df=quality_df, figures=figs, narrative=narrative,
                  timings=timings, anomaly_counts=anomaly_counts, savings=savings, thresholds=th,
                  head_table=head_table, coverage=coverage, assessment=assessment,
                  carpet_year=carpet_year, carpet_month=carpet_month)


def _apply_anomalies(df: pd.DataFrame, figs: list[FigureEntry], th: Thresholds) -> dict[str, int]:
    by_key = {f.key: f.figure for f in figs}
    counts: dict[str, int] = {}

    def zeros(key: str, cols: list[str], label: str) -> None:
        idx = an.zero_dropouts(df, cols)
        counts[f"{label} (Nullwert-Aussetzer)"] = len(idx)
        fx.add_anomaly_markers(by_key[key], idx.index, [0] * len(idx), "Aussetzer (Wert 0)")

    zeros("regelguete_stat_heizung", ["Stat. Heizung Geb.06 VL (Ist)", "Stat. Heizung Geb.06 VL (Soll)"],
          "Regelgüte Stat. Heizung")
    zeros("regelguete_fbh", ["FBH Geb.06 VL (Ist)", "FBH Geb.06 VL (Soll)"], "Regelgüte FBH")
    zeros("zonenvergleich", ["Stat. Heizung Geb.06 VL (Ist)", "FBH Geb.06 VL (Ist)",
                              "FBH Geb.08 KI-Räume VL", "FBH Geb.08 Intensivpflege VL"], "Zonenvergleich")

    resets = an.meter_resets(df, "Zähler 019 – WMZ")
    counts["WMZ (Zählerrücksprung)"] = len(resets)
    fx.add_anomaly_markers(by_key["wmz_kumuliert"], resets.index, df.loc[resets.index, "Zähler 019 – WMZ"],
                            "Zählerrücksprung")

    n_low = 0
    for vl, rl, label in [("Stat. Heizung Geb.06 VL (Ist)", "Stat. Heizung Geb.06 RL", "Stat. Heizung"),
                          ("FBH Geb.06 VL (Ist)", "FBH Geb.06 RL", "FBH")]:
        idx = an.low_delta_t(df, vl, rl, th.aktiv_schwelle_vl, th.delta_t_min)
        n_low += len(idx)
        fx.add_anomaly_markers(by_key["delta_t"], idx.index, (df[vl] - df[rl]).loc[idx.index],
                                f"Delta T < {th.delta_t_min:g} K ({label})", color="#7F0000")
    counts[f"Delta T < {th.delta_t_min:g} K bei aktivem Betrieb"] = n_low
    return counts
