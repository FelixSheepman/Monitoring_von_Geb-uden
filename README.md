# KI-Agent: Technisches Monitoring

Automatisierte Datenprüfung und grafische Aufbereitung von Monitoring-Messdaten –
Ersatz für die manuelle Excel-Auswertung aus Kapitel 6 der Hausarbeit
*"Verwendung von KI-Agenten im Monitoring"*.

## Setup

```bash
# einmalig
.venv/Scripts/python.exe -m venv .venv          # falls .venv fehlt
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

## Nutzung

**CLI (Skript-Variante):**
```bash
.venv/Scripts/python.exe cli.py --input "source_docs/Messdaten 2024-2026.xlsx" --output report.xlsx
```

**Web-App (interaktiv):**
```bash
.venv/Scripts/streamlit.exe run app.py
```

## Projektstruktur

```
monitoring_agent/      Kernlogik (von CLI und Web-App gemeinsam genutzt)
  config.py             Spaltenschema: welche Excel-Spalte ist welcher Messpunkt
  data_loader.py         Einlesen der Messdaten-.xlsx
  quality.py              Automatisierte Datenprüfung (Tabelle 1)
  metrics.py               Delta-T, Tagesverbrauch aus Zählerständen
  figures.py                 Die 11 Plotly-Abbildungen aus Kap. 6.3
  report.py                   Orchestriert Prüfung + Abbildungen zu einem Report
  excel_export.py              Export als native Excel-Arbeitsmappe
cli.py                  Kommandozeilen-Variante
app.py                  Streamlit-Web-App
source_docs/            Rohdaten + Textauszug der Hausarbeit (Referenz)
output/                 Generierte Reports (lokal, nicht Teil der Abgabe)
```

## Stand

- Datenprüfung (Tabelle 1) automatisiert nachgebaut, reproduziert die manuell
  gefundenen Auffälligkeiten (Aussetzer, RL>VL, zu niedriger Sollwert) und
  findet zusätzlich rückläufige Zählerstände.
- Alle 11 Abbildungen aus Kap. 6.3 (Liniendiagramme, Heizkurve mit Regression,
  2 Carpetplots, Zonenvergleich, Delta-T, Tageswerte) als interaktive
  Plotly-Charts sowie als native Excel-Charts.
- Getestet gegen den vollständigen Datensatz (58.125 Zeitschritte, 23 Spalten).

## Offene Punkte / mögliche nächste Schritte

- Automatisch generierter Auswertungstext (Kap. 6.4-Stil) als Ergänzung zu den Grafiken.
- Vergleichsansicht konventionell vs. KI-Agent (Kap. 8 der Hausarbeit).
- Export der Abbildungen als Word-/PDF-Bericht.
