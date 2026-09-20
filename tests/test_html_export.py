"""Tests fuer den eigenstaendigen HTML-Bericht und das Versandpaket."""

import re
import zipfile
from pathlib import Path

import pytest

from monitoring_agent.comparison import compare_table1
from monitoring_agent.data_loader import load_measurements
from monitoring_agent.html_export import export_html
from monitoring_agent.report import build_report
from monitoring_agent.structure import REPORT_SECTIONS

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "source_docs" / "Messdaten 2024-2026.xlsx"
needs_data = pytest.mark.skipif(not DATA.exists(), reason="Messdaten-Datei fehlt")


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    report = build_report(load_measurements(DATA), display_resample="h", excluded=frozenset({("Stat. Heizung Geb.06 VL (Soll)", "nullwert")}))
    path = tmp_path_factory.mktemp("html") / "b.html"
    export_html(report, path, comparison=compare_table1(report.quality_df))
    return path.read_text(encoding="utf-8"), report


@needs_data
def test_html_report_is_complete(page):
    text, report = page
    for i, name in enumerate(REPORT_SECTIONS, start=1):
        assert f"{i} {name}" in text
    assert text.count("<figure>") == len(report.figures) == 13
    assert "Abbildung 4: Heizkurve" in text
    assert "Nicht berücksichtigte Messwerte" in text and "16 fehlerhafte Messwerte" in text
    assert "Vergleich manuelle Auswertung / Agent" in text


@needs_data
def test_html_report_works_offline(page):
    text, _ = page
    assert not re.search(r"<script[^>]+src=", text) and not re.search(r"<link[^>]+href=", text)  # nichts wird nachgeladen
    assert "plotly" in text and len(text) < 20_000_000            # plotly.js eingebettet, Datei bleibt versandfaehig


@needs_data
def test_html_export_does_not_modify_the_figures_of_the_report(tmp_path):
    report = build_report(load_measurements(DATA), display_resample="h")
    before = [e.figure.layout.width for e in report.figures]
    export_html(report, tmp_path / "x.html")
    assert [e.figure.layout.width for e in report.figures] == before


@needs_data
def test_package_layout_is_complete():
    """Das Paket braucht alles, was App und Kommandozeile zur Laufzeit lesen."""
    import make_package
    for f in make_package.FILES:
        assert (ROOT / f).exists(), f
    assert (ROOT / "App-starten.bat").read_bytes().count(b"\r\n") > 20   # Windows-Zeilenenden, sonst laufen Sprungmarken nicht
    assert make_package.DATA.exists()
    names = {p.name for p in (ROOT / "reference").iterdir()}
    assert {"kontrollkriterien.csv", "manual_tabelle1.csv", "forschungsfragen.csv"} <= names
