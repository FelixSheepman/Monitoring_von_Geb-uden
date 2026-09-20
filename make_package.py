"""Baut das Versandpaket fuer den Betreuer: output/Monitoring-KI-Agent.zip (Programm + Beispielbericht als HTML)."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
NAME = "Monitoring-KI-Agent"
DATA = ROOT / "source_docs" / "Messdaten 2024-2026.xlsx"

FILES = ["App-starten.bat", "LIESMICH.txt", "app.py", "cli.py", "requirements.txt", "requirements-dev.txt", ".streamlit/config.toml"]
TREES = ["monitoring_agent", "reference", "docs", "tests"]


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from monitoring_agent.data_loader import load_measurements
    from monitoring_agent.html_export import export_html
    from monitoring_agent.report import build_report
    from monitoring_agent.comparison import compare_table1

    OUT.mkdir(exist_ok=True)
    print("Erzeuge Beispielbericht (HTML) ...")
    report = build_report(load_measurements(DATA), display_resample="h", show_anomalies=True)
    html_path = OUT / "Beispielbericht.html"
    export_html(report, html_path, comparison=compare_table1(report.quality_df))

    zip_path = OUT / f"{NAME}.zip"
    print(f"Packe {zip_path.name} ...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        def add(src: Path, arc: str) -> None:
            if src.suffix == ".bat":  # Batch-Dateien brauchen Windows-Zeilenenden, sonst funktionieren Sprungmarken nicht
                data = src.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
                z.writestr(f"{NAME}/{arc}", data)
            else:
                z.write(src, f"{NAME}/{arc}")

        for f in FILES:
            add(ROOT / f, f)
        for tree in TREES:
            for p in sorted((ROOT / tree).rglob("*")):
                if p.is_file() and "__pycache__" not in p.parts and p.suffix not in {".pyc"}:
                    add(p, p.relative_to(ROOT).as_posix())
        add(DATA, "source_docs/" + DATA.name)
        add(html_path, "Beispielbericht.html")
    print(f"Fertig: {zip_path} ({zip_path.stat().st_size / 1e6:.1f} MB), Beispielbericht: {html_path.stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
