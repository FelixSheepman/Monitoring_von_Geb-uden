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

## Funktionen (im Einstellungsmenü der App einzeln an-/abschaltbar)

| Funktion | Beschreibung |
|---|---|
| Datenprüfung (Tabelle 1) | Regelbasiert, generisch, immer auf den Rohdaten |
| 11 Abbildungen | Interaktive Plotly-Charts, Glättung nur für die Anzeige |
| Laufzeitmessung | Zeiten je Schritt, Faktor gegenüber manuellem Aufwand |
| Anomalie-Marker | Nullwert-Aussetzer, Zählerrücksprünge, Delta T < 2 K |
| Regelbasierte Auswertung | Datengestützte Texte im Stil Kap. 6.4 |
| Vergleichsansicht | Manuelle Auswertung (`reference/*.csv`) vs. Agent |
| LLM-Auswertung | Claude formuliert die Auswertung aus den berechneten Kennzahlen |
| Erweiterte Prüfregeln (v2) | Zusatzregeln, im Vergleich gegen v1 mit Trefferquote/Genauigkeit |
| Pumpenlaufzeiten, Datenverfügbarkeit | Zwei zusätzliche Abbildungen (13, 14) und ein Auswertungstext |
| Energieeinsparpotenzial | Abschätzung mit einstellbaren Annahmen gegenüber dem 10-%-Ziel |
| Explorer | Freie Diagramme (Linie, Streu, Carpetplot) mit Zeitraumfilter |
| Schwellenwerte | Heizgrenze, Delta T, FBH-Grenze, Preise u. a. per Regler |
| Word-/Excel-Export | Formatierter Bericht bzw. Arbeitsmappe |

## LLM-Auswertung einrichten

API-Key nie ins Repo committen. Lokal: Umgebungsvariable `ANTHROPIC_API_KEY` setzen oder den Key im
Einstellungsmenü eintragen. Streamlit Cloud: App → Settings → Secrets → `ANTHROPIC_API_KEY = "sk-ant-..."`.

## Tests

```bash
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe -m pytest tests -q
```

Die Tests prüfen u. a., dass Min/Max aller 23 Spalten mit eurer manuellen Tabelle 1 übereinstimmen
und dass alle manuell gefundenen Befunde vom Agenten reproduziert werden.
