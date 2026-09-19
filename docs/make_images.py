"""Erzeugt die Beispielbilder fuer die Anleitung (docs/img). Aufruf: python docs/make_images.py"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from monitoring_agent import figures as fx  # noqa: E402
from monitoring_agent.data_loader import load_measurements  # noqa: E402

df = load_measurements(ROOT / "source_docs" / "Messdaten 2024-2026.xlsx")
img = ROOT / "docs" / "img"

fx.fig_heating_curve(df, "RLT KL01 Außenluft", "Stat. Heizung Geb.06 VL (Ist)",
                     "Heizkurve: Außentemp. vs. Vorlauftemp. Geb.06").write_image(img / "heizkurve.png", width=900, height=450)
fx.fig_carpet(df, "RLT primär VL", 2025, 2, "RLT primär VL-Temp. 02/2025", 20, 65).write_image(img / "carpet_februar.png", width=900, height=450)
fx.fig_carpet(df, "RLT primär VL", 2025, 7, "RLT primär VL-Temp. 07/2025", 20, 65).write_image(img / "carpet_juli.png", width=900, height=450)
print("ok")
