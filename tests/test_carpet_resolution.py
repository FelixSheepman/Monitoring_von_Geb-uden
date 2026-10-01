"""Tests fuer die waehlbare Carpetplot-Aufloesung (Jahr/Monat/Woche/Tag) und die
Aussentemperatur-Beschriftung der Zellen (Abbildung 5)."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from monitoring_agent import figures as fx
from monitoring_agent.buildings import HEIZKREISE
from monitoring_agent.circuit_analysis import circuit_figures
from monitoring_agent.data_loader import load_measurements
from monitoring_agent.process import figure_kind
from monitoring_agent.report import build_report

DATA = Path(__file__).resolve().parent.parent / "source_docs" / "Messdaten 2024-2026.xlsx"
needs_data = pytest.mark.skipif(not DATA.exists(), reason="Messdaten-Datei fehlt")


@pytest.fixture(scope="module")
def df():
    return load_measurements(DATA)


# ----------------------------------------------------------------------------- carpet_window / Label

def test_carpet_window_bounds_per_granularity():
    anchor = pd.Timestamp("2025-02-13 10:00")  # ein Donnerstag
    jahr = fx.carpet_window(anchor, "Jahr")
    assert jahr == (pd.Timestamp("2025-01-01"), pd.Timestamp("2026-01-01"))
    monat = fx.carpet_window(anchor, "Monat")
    assert monat == (pd.Timestamp("2025-02-01"), pd.Timestamp("2025-03-01"))
    woche = fx.carpet_window(anchor, "Woche")
    assert woche == (pd.Timestamp("2025-02-10"), pd.Timestamp("2025-02-17"))  # Montag bis naechsten Montag
    assert woche[0].day_name() == "Monday"
    tag = fx.carpet_window(anchor, "Tag")
    assert tag == (pd.Timestamp("2025-02-13"), pd.Timestamp("2025-02-14"))


def test_carpet_period_label_formats():
    anchor = pd.Timestamp("2025-02-13")
    assert fx.carpet_period_label("Jahr", anchor) == "2025"
    assert fx.carpet_period_label("Monat", anchor) == "02/2025"
    assert fx.carpet_period_label("Tag", anchor) == "13.02.2025"
    assert fx.carpet_period_label("Woche", anchor).startswith("KW ") and "10.02.2025" in fx.carpet_period_label("Woche", anchor)


# ----------------------------------------------------------------------------- fig_carpet_window

@needs_data
def test_every_granularity_shows_every_raw_value_at_least_once(df):
    """Kernanforderung: keine Glaettung - jede Zelle ist genau ein 15-Min-Messwert."""
    counts = {}
    for gran, anchor in [("Jahr", pd.Timestamp("2025-06-01")), ("Monat", pd.Timestamp("2025-02-01")),
                         ("Woche", pd.Timestamp("2025-02-13")), ("Tag", pd.Timestamp("2025-02-13"))]:
        fig = fx.fig_carpet_window(df, "RLT primär VL", gran, anchor, "t", zmin=20, zmax=65)
        z = np.asarray(fig.data[0].z, dtype=float)
        counts[gran] = int(np.sum(~np.isnan(z)))
        start, end = fx.carpet_window(anchor, gran)
        raw = df.loc[start:end - pd.Timedelta(minutes=1), "RLT primär VL"].dropna()
        assert counts[gran] == len(raw)  # jeder tatsaechlich gemessene Wert erscheint als eigene Zelle
    assert counts["Tag"] < counts["Woche"] < counts["Monat"] < counts["Jahr"]


@needs_data
def test_annotation_present_except_for_jahr(df):
    for gran, expect_text in [("Jahr", False), ("Monat", True), ("Woche", True), ("Tag", True)]:
        fig = fx.fig_carpet_window(df, "RLT primär VL", gran, pd.Timestamp("2025-02-13"), "t",
                                   annotate_col="RLT KL01 Außenluft", annotate_label="Außentemp.")
        assert (fig.data[0].text is not None) == expect_text


@needs_data
def test_annotation_skipped_when_annotate_col_equals_value_col(df):
    fig = fx.fig_carpet_window(df, "RLT KL01 Außenluft", "Woche", pd.Timestamp("2025-02-13"), "t",
                               annotate_col="RLT KL01 Außenluft")
    assert fig.data[0].text is None


@needs_data
def test_tag_orientation_is_a_horizontal_strip_across_the_day(df):
    fig = fx.fig_carpet_window(df, "RLT primär VL", "Tag", pd.Timestamp("2025-02-13"), "t")
    z = fig.data[0]
    assert len(z.x) == 96 and len(z.y) == 1  # Uhrzeit von links nach rechts, eine einzelne Zeile
    assert list(z.x)[:2] == ["00:00", "00:15"]


def test_empty_window_does_not_crash():
    idx = pd.date_range("2025-01-01", periods=10, freq="15min")
    df = pd.DataFrame({"RLT primär VL": range(10)}, index=idx)
    fig = fx.fig_carpet_window(df, "RLT primär VL", "Tag", pd.Timestamp("2030-01-01"), "t")
    assert fig.data[0].type == "heatmap"
    assert "keine Messwerte" in fig.layout.title.text


# ----------------------------------------------------------------------------- Einbindung in build_report

@needs_data
def test_build_report_default_matches_the_previous_fixed_month_behaviour(df):
    """Ohne explizite Angabe (wie bisher ueberall aufgerufen) bleibt Titel und Verhalten identisch."""
    rep = build_report(df)
    vl = next(f for f in rep.figures if f.key == "carpet_rlt_vl")
    rl = next(f for f in rep.figures if f.key == "carpet_rlt_rl")
    assert vl.title == "RLT primär VL-Temp. 02/2025" and rl.title == "RLT primär RL-Temp. 02/2025"
    assert "Außentemperatur" in vl.caption and "Außentemperatur" not in rl.caption
    assert figure_kind(vl.figure) == "Carpetplot" and figure_kind(rl.figure) == "Carpetplot"
    assert vl.figure.data[0].zmin == 20 and vl.figure.data[0].zmax == 65  # feste Farbskala (GR3) bleibt erhalten


@needs_data
def test_build_report_honours_a_different_granularity_and_anchor(df):
    rep = build_report(df, carpet_granularity="Woche", carpet_year=2025, carpet_month=2, carpet_day=13)
    vl = next(f for f in rep.figures if f.key == "carpet_rlt_vl")
    assert "KW " in vl.title and len(vl.figure.data[0].x) == 7
    assert rep.carpet_granularity == "Woche" and rep.carpet_day == 13


@needs_data
def test_no_secondary_axis_introduced_by_the_new_figures(df):
    rep = build_report(df, carpet_granularity="Tag", carpet_year=2025, carpet_month=2, carpet_day=13)
    assert all("yaxis2" not in f.figure.layout.to_plotly_json() for f in rep.figures)  # GR3-Regel


# ----------------------------------------------------------------------------- Einbindung in circuit_analysis

@needs_data
def test_circuit_carpet_uses_the_chosen_granularity_and_annotates_with_site_outdoor_temperature(df):
    rep = build_report(df)
    kreis = HEIZKREISE["stat_heizung_geb06"]
    figs = circuit_figures(rep.df, kreis, "Tag", pd.Timestamp("2025-02-13"))
    carp = next(f for f in figs if f.title == "Carpetplot Vorlauf")
    assert carp.figure.data[0].text is not None
    assert len(carp.figure.data[0].x) == 96


# ----------------------------------------------------------------------------- Tag/Nacht- und Betriebszustaende-Overlay

@needs_data
@pytest.mark.parametrize("granularity", ["Jahr", "Monat", "Woche", "Tag"])
def test_carpet_has_toggleable_night_and_operating_state_overlays(df, granularity):
    fig = fx.fig_carpet_window(df, "RLT primär VL", granularity, pd.Timestamp("2025-02-13"), "t",
                               zmin=20, zmax=65, annotate_col="RLT KL01 Außenluft")
    # 4 Nacht-Shapes (2 Flaechen + 2 Grenzlinien) + 4 echte farbige Kaestchen fuer die Betriebszustaende
    assert len(fig.layout.shapes) == 8 and all(s.visible for s in fig.layout.shapes)
    assert sum(s.type == "rect" and s.fillcolor and s.fillcolor.startswith("rgb(") for s in fig.layout.shapes) == 4
    # 1 Nacht-Beschriftung + 4 Betriebszustands-Beschriftungen (je Kaestchen eine eigene, nicht ein Textblock)
    assert len(fig.layout.annotations) == 5 and all(a.visible for a in fig.layout.annotations)
    assert "Nachtzeit" in fig.layout.annotations[0].text
    labels = {"Aus", "Nachtabsenkung", "Normalbetrieb", "Volllast"}
    found = {lbl for lbl in labels for a in fig.layout.annotations[1:] if lbl in a.text}
    assert found == labels
    assert len(fig.layout.updatemenus) == 2  # ein Button-Paar je Overlay, unabhaengig voneinander ein-/ausblendbar
    # jeder Button steuert nur seine eigene Gruppe (kein Button schaltet beide Overlays gleichzeitig)
    night_args = fig.layout.updatemenus[0].buttons[0].args[0]
    assert all(k.startswith("shapes[0]") or k.startswith("shapes[1]") or k.startswith("shapes[2]")
              or k.startswith("shapes[3]") or k.startswith("annotations[0]") for k in night_args)
    legend_args = fig.layout.updatemenus[1].buttons[0].args[0]
    assert all(k.startswith("shapes[4]") or k.startswith("shapes[5]") or k.startswith("shapes[6]")
              or k.startswith("shapes[7]") or k.startswith("annotations[1]") or k.startswith("annotations[2]")
              or k.startswith("annotations[3]") or k.startswith("annotations[4]") for k in legend_args)


def test_night_shapes_wrap_around_midnight_in_the_expected_orientation():
    for granularity, axis_attr in (("Monat", "yref"), ("Woche", "yref"), ("Jahr", "yref"), ("Tag", "xref")):
        shapes = fx._night_shapes(granularity)
        assert len(shapes) == 4  # 2 Flaechen (rect) + 2 kraeftige Grenzlinien (line), je einmal pro Uebergang
        assert sum(s["type"] == "rect" for s in shapes) == 2
        assert sum(s["type"] == "line" for s in shapes) == 2
        bounds = [(s["x0"], s["x1"]) if axis_attr == "xref" else (s["y0"], s["y1"])
                 for s in shapes if s["type"] == "rect"]
        assert ("00:00", fx.NIGHT_END) in bounds and (fx.NIGHT_START, "23:45") in bounds


def test_operating_bands_cover_the_full_range_without_gaps():
    bands = fx._operating_band_colors_and_bounds(20.0, 65.0, "°C")
    assert [label for _, label, _ in bands] == ["Aus", "Nachtabsenkung", "Normalbetrieb", "Volllast"]
    bounds = [b for _, _, b in bands]
    assert bounds[0] == "< 27 °C" and bounds[-1] == "> 58 °C"  # erste/letzte Stufe offen, dazwischen lueckenlos
    assert bounds[1] == "27–38 °C" and bounds[2] == "38–58 °C"
    assert len({color for color, _, _ in bands}) == 4  # jede Stufe eine eigene Farbe


@needs_data
def test_overlays_are_skipped_for_the_empty_window_fallback(df):
    fig = fx.fig_carpet_window(df, "RLT primär VL", "Tag", pd.Timestamp("2030-01-01"), "t", zmin=20, zmax=65)
    assert len(fig.layout.shapes) == 0 and len(fig.layout.annotations) == 0


# ----------------------------------------------------------------------------- Zulaessige Vorlauftemperatur (Grenzlinie)

def test_add_component_limit_draws_a_visible_dashed_line_with_label():
    import plotly.graph_objects as go
    fig = go.Figure(go.Scatter(x=[1, 2, 3], y=[10, 20, 30]))
    fx.add_component_limit(fig, 70.0, "Zulässig Heizkörper")
    assert len(fig.layout.shapes) == 1
    shape = fig.layout.shapes[0]
    assert shape.y0 == shape.y1 == 70.0 and shape.line.dash == "dash" and shape.line.width >= 2
    assert len(fig.layout.annotations) == 1 and "Zulässig Heizkörper: 70 °C" in fig.layout.annotations[0].text


@needs_data
def test_circuit_figures_mark_the_component_limit_by_kind(df):
    from monitoring_agent.circuit_analysis import circuit_figures
    from monitoring_agent.settings import Thresholds
    th = Thresholds(fbh_limit=40.0, heizkoerper_limit=70.0)
    rep = build_report(df)

    fbh = circuit_figures(rep.df, HEIZKREISE["fbh_geb06"], "Monat", pd.Timestamp("2025-02-01"), th)
    vr = next(f for f in fbh if f.title == "Vorlauf und Rücklauf")
    assert vr.figure.layout.shapes[0].y0 == 40.0
    assert "40 °C" in vr.caption

    hk = circuit_figures(rep.df, HEIZKREISE["stat_heizung_geb06"], "Monat", pd.Timestamp("2025-02-01"), th)
    vr_hk = next(f for f in hk if f.title == "Vorlauf und Rücklauf")
    assert vr_hk.figure.layout.shapes[0].y0 == 70.0

    rlt = circuit_figures(rep.df, HEIZKREISE["rlt_primaer"], "Monat", pd.Timestamp("2025-02-01"), th)
    vr_rlt = next(f for f in rlt if f.title == "Vorlauf und Rücklauf")
    assert len(vr_rlt.figure.layout.shapes) == 0  # RLT ist weder Heizkoerper noch Fussbodenheizung


@needs_data
def test_zonenvergleich_compares_only_same_type_components(df):
    """Hydraulischer Abgleich vergleicht parallele Kreise DESSELBEN Systemtyps - FBH und Heizkoerper sind
    absichtlich auf unterschiedliche Vorlauftemperaturen ausgelegt und gehoeren daher auf getrennte Diagramme."""
    rep = build_report(df)
    fbh = next(f for f in rep.figures if f.key == "zonenvergleich")
    hk = next(f for f in rep.figures if f.key == "zonenvergleich_heizkoerper")

    fbh_names = {t.name for t in fbh.figure.data}
    assert fbh_names == {"FBH Geb.06", "FBH Geb.08 KI-Räume", "FBH Geb.08 Intensivpflege"}
    assert [s.y0 for s in fbh.figure.layout.shapes] == [40.0]  # nur die FBH-Grenze

    hk_names = {t.name for t in hk.figure.data}
    assert hk_names == {"Stat. Heizung Geb.06", "Heizung Geb.1/3", "Heizung Lager Geb.2"}
    assert [s.y0 for s in hk.figure.layout.shapes] == [70.0]  # nur die Heizkoerper-Grenze
    assert fbh_names.isdisjoint(hk_names)  # keine Komponente taucht in beiden Vergleichen auf
