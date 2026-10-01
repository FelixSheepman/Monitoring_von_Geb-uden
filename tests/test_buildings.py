"""Tests fuer die Gliederung nach Gebaeude/Heizkreis und deren generische Auswertung."""

from pathlib import Path

import pandas as pd
import pytest

from monitoring_agent.building_diagram import svg_netzplan, svg_overview
from monitoring_agent.buildings import GEBAEUDE, HEIZKREISE, N_HEIZKREISE, SITE_COLUMNS, find_gebaeude
from monitoring_agent.circuit_analysis import circuit_figures, circuit_quality, circuit_stats
from monitoring_agent.config import COLUMNS
from monitoring_agent.data_loader import load_measurements
from monitoring_agent.report import build_report

DATA = Path(__file__).resolve().parent.parent / "source_docs" / "Messdaten 2024-2026.xlsx"
needs_data = pytest.mark.skipif(not DATA.exists(), reason="Messdaten-Datei fehlt")


def test_seven_heizkreise_in_four_buildings_match_the_sketch():
    assert N_HEIZKREISE == 7 and len(HEIZKREISE) == 7
    assert [g.key for g in GEBAEUDE] == ["geb3", "geb2", "geb6", "geb8"]
    counts = {g.key: len(g.kreise) for g in GEBAEUDE}
    assert counts == {"geb3": 2, "geb2": 1, "geb6": 2, "geb8": 2}
    assert [k.nr for g in GEBAEUDE for k in g.kreise] == list(range(1, 8))  # Nummerierung wie in der Handskizze


def test_every_column_belongs_to_exactly_one_heizkreis_or_the_site_level():
    assigned: list[str] = []
    for k in HEIZKREISE.values():
        assigned += [c.short for c in k.columns] + [c.short for c in k.extra_columns]
    assigned += [c.short for c in SITE_COLUMNS]
    assert sorted(assigned) == sorted(c.short for c in COLUMNS)  # keine Spalte fehlt oder ist doppelt zugeordnet
    assert len(assigned) == len(set(assigned))


def test_find_gebaeude_matches_the_zone_a_kreis_belongs_to():
    for k in HEIZKREISE.values():
        assert find_gebaeude(k.zone).key == k.building
        assert k in find_gebaeude(k.zone).kreise


def test_rlt_anlage_carries_the_shared_ventilation_sensors_as_extras():
    kreis = HEIZKREISE["rlt_primaer"]
    assert {c.role for c in kreis.columns} == {"vl", "rl"}
    assert {c.role for c in kreis.extra_columns} == {"aul", "zul", "meter_electric"}
    assert len(kreis.extra_columns) == 4  # aul, zul, 2x meter_electric (Ab- und Zuluftventilator)
    assert kreis.extra_col("aul") is not None and kreis.extra_col("zul") is not None


def test_heizkreis_without_soll_or_pump_has_no_extra_column_for_it():
    kreis = HEIZKREISE["heizung_geb1_geb3"]
    assert kreis.col("soll_vl") is None and kreis.col("pump") is None and kreis.col("vl") is not None


@needs_data
def test_circuit_quality_matches_the_kreis_columns_by_row_count():
    df = load_measurements(DATA)
    rep = build_report(df)
    for k in HEIZKREISE.values():
        q = circuit_quality(rep.quality_df, k)
        assert len(q) == len(k.columns) + len(k.extra_columns)


@needs_data
def test_circuit_figures_and_stats_cover_every_heizkreis():
    df = load_measurements(DATA)
    rep = build_report(df)
    for k in HEIZKREISE.values():
        figs = circuit_figures(rep.df, k, 2025, 2)
        assert len(figs) >= 3  # jeder der 7 Kreise hat mindestens VL/RL, Delta T und Carpetplot
        assert all(f.figure is not None and f.caption for f in figs)
        stats = circuit_stats(rep.df, k)
        assert "Vorlauf Min/Max" in stats
    fbh = HEIZKREISE["fbh_geb06"]  # hat Soll-Wert und Pumpe -> zusaetzliche Diagramme/Kennzahlen
    titles = {f.title for f in circuit_figures(rep.df, fbh, 2025, 2)}
    assert {"Regelgüte", "Pumpenlaufzeit"} <= titles
    assert "Pumpe: Laufzeitanteil" in circuit_stats(rep.df, fbh)


def test_circuit_figures_handle_a_circuit_with_gaps_gracefully():
    """Kreis mit nur wenigen Rohdaten (z.B. nach starkem Ausschluss) darf nicht abstuerzen."""
    idx = pd.date_range("2025-01-01", periods=5, freq="15min")
    df = pd.DataFrame({c.short: pd.Series([None] * 5, index=idx) for c in COLUMNS})
    kreis = HEIZKREISE["fbh_geb06"]
    df[kreis.col("vl").short] = [20.0, 21.0, None, 22.0, 23.0]
    df[kreis.col("rl").short] = [15.0, 15.5, None, 16.0, 16.5]
    figs = circuit_figures(df, kreis, 2025, 1)
    assert any(f.title == "Vorlauf und Rücklauf" for f in figs)
    assert circuit_stats(df, kreis)["Vorlauf Min/Max"] == "20.0 / 23.0 °C"


def test_svg_overview_contains_all_circuits_and_highlights_the_selection():
    plain = svg_overview()
    assert plain.count("<svg") == 1 and plain.count("</svg>") == 1
    for k in HEIZKREISE.values():
        assert k.short.split()[0] in plain or k.short in plain  # jeder Kreis ist mit seiner Kurzbezeichnung vertreten
    highlighted = svg_overview("fbh_geb06")
    assert highlighted != plain  # die Hervorhebung veraendert das Bild
    assert highlighted.count('stroke-width="2.5"') >= 5  # 4 Gebaeuderahmen + mind. 1 hervorgehobener Kreis


def test_netzplan_is_well_formed_and_labels_every_sensor_column():
    plain = svg_netzplan()
    assert plain.startswith("<svg") and plain.count("<svg") == 1 and plain.endswith("</svg>")
    # jede Spalte eines Heizkreises (VL/RL, Soll, Pumpe) taucht als Beschriftung im Netzplan auf
    for k in HEIZKREISE.values():
        for c in (*k.columns, *k.extra_columns):
            short_or_abbreviated = c.short in plain or c.short.replace("Zähler ", "Z. ") in plain
            assert short_or_abbreviated, c.short  # Zaehler-Spalten werden im Netzplan als "Z. ..." abgekuerzt
        assert k.short in plain
    for g in GEBAEUDE:
        assert g.name in plain


def test_netzplan_card_width_covers_all_buildings_side_by_side():
    """Regressionstest fuer einen Layout-Bug: die Gesamtbreite muss alle Gebaeude-Spalten nebeneinander
    aufnehmen (nicht nur die breiteste einzelne Spalte), sonst liegen Knoten ausserhalb des viewBox."""
    import re
    svg = svg_netzplan()
    w, h = (float(x) for x in re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg).groups())
    xs = [float(x) for x in re.findall(r'<circle cx="([\d.-]+)"', svg)]
    assert xs and max(xs) <= w and min(xs) >= 0
    assert w > 1800  # 7 Kreise in 4 Gebaeuden nebeneinander sind deutlich breiter als ein einzelnes Gebaeude


def test_netzplan_highlights_the_selected_circuit():
    plain = svg_netzplan()
    highlighted = svg_netzplan("stat_heizung_geb06")
    assert highlighted != plain
    assert plain.count('stroke-width="3.4"') == 0
    assert highlighted.count('stroke-width="3.4"') == 1  # genau eine Karte hervorgehoben
