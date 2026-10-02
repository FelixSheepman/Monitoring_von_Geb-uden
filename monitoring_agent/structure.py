"""Gemeinsame Struktur-Konstanten (Zwischenschritte, Berichtsgliederung); vermeidet zyklische Importe."""

# Ampel-Farben (Rot/Gelb/Gruen) fuer Schweregrad- und Status-Spalten - eine gemeinsame Quelle fuer
# App-UI (ui.py), HTML- und Word-Export, damit dieselben Befunde in jedem Format gleich eingefaerbt
# sind statt unabhaengig (und potenziell abweichend) als Hex-Literale gepflegt zu werden. Word-Export
# braucht die Werte ohne "#" (python-docx-Formatierung) und leitet sie per .lstrip("#") davon ab.
GREEN, RED, AMBER, INFO_BLUE = "#C6EFCE", "#FFC7CE", "#FFE699", "#DDEBF7"
SEVERITY_COLORS = {"hoch": RED, "mittel": AMBER, "gering": GREEN}

STEPS = ["Datenprüfung", "Grafikerstellung", "Auswertung", "Bewertung", "Berichtserstellung"]

STEP_CHAPTERS = {
    "Datenprüfung": "Kap. 6.2 / 7.2 / 8.2",
    "Grafikerstellung": "Kap. 6.3 / 7.3 / 8.3",
    "Auswertung": "Kap. 6.4 / 7.4 / 8.4",
    "Bewertung": "Kap. 6.5 / 7.5 / 8.5",
    "Berichtserstellung": "Kap. 6.7 / 7.6 / 8.6",
}

# Gliederung des Monitoringberichts in Anlehnung an Kap. 6 der Hausarbeit (6.1 bis 6.6)
REPORT_SECTIONS = [
    "Einleitung und Datengrundlage",
    "Datenprüfung",
    "Grafische Aufbereitung und Auswertung",
    "Energieeinsparpotenzial",
    "Bewertung der Ergebnisse",
    "Zusammenfassung und Empfehlungen",
]
REQUIRED_SECTION_KEYWORDS = ["Einleitung", "Datenprüfung", "Grafische Aufbereitung", "Auswertung", "Bewertung", "Zusammenfassung"]
