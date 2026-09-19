"""Schaltbare Funktionen der App (im Einstellungsmenue an-/abschaltbar)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Thresholds:
    heizgrenze_aul: float = 15.0
    aktiv_schwelle_vl: float = 25.0
    delta_t_min: float = 2.0
    fbh_limit: float = 40.0
    heat_avoid_share: float = 0.5
    rlt_night_hours: float = 8.0
    rlt_night_reduction: float = 0.5
    heat_price: float = 0.09
    power_price: float = 0.30


@dataclass(frozen=True)
class Settings:
    show_timings: bool = True
    show_anomalies: bool = True
    show_comparison: bool = True
    use_llm: bool = False
    enable_word_export: bool = True
    strict_rules: bool = False
    show_savings: bool = True
    show_explorer: bool = True
    show_assessment: bool = True
    show_process: bool = True
    show_research: bool = True
    llm_model: str = "claude-opus-5"


FEATURE_LABELS = {
    "show_timings": ("Laufzeitmessung", "Zeigt, wie lange Prüfung, Grafiken und Auswertung dauern (Zeitvergleich manuell vs. Agent)."),
    "show_anomalies": ("Anomalien in Diagrammen markieren", "Rote Marker bei Nullwert-Aussetzern, Zählerrücksprüngen und Delta T < 2 K."),
    "show_comparison": ("Vergleichsansicht (Kap. 8)", "Stellt eure manuelle Auswertung der Agent-Auswertung gegenüber."),
    "use_llm": ("LLM-Auswertung (Claude)", "Ein Sprachmodell formuliert die Auswertung; benötigt einen Anthropic-API-Key."),
    "strict_rules": ("Erweiterte Prüfregeln (v2)", "Zusätzliche Regeln: hohe Zuluft-Maxima, FBH-Grenzwerte, Vor-/Rücklauf-Widersprüche an beiden Spalten. Zum Vergleich v1 gegen v2 in Kap. 8.2.3."),
    "show_savings": ("Energieeinsparpotenzial", "Schätzt das Einsparpotenzial (Heizgrenze, RLT-Nachtabsenkung) gegenüber dem 10-%-Ziel."),
    "show_assessment": ("Bewertung (Kap. 6.5)", "Stuft die Befunde nach Schweregrad ein und gibt Empfehlungen; erscheint auch im Word-Bericht."),
    "show_process": ("Vorgehen und Kontrollkriterien (Kap. 4/5)", "Zwischenschritte, Kontrollkriterien mit automatischer Prüfung, Agent-Steckbrief, Sensorik-Übersicht."),
    "show_research": ("Forschungsfragen (Kap. 9/10)", "Antwortentwürfe mit Belegen, Theorie-Praxis-Abgleich, Empfehlungen und Ausblick."),
    "show_explorer": ("Explorer (freie Diagramme)", "Eigene Spalten, Zeitraum und Carpetplots frei auswählen."),
    "enable_word_export": ("Word-Berichtsexport", "Erzeugt einen formatierten Bericht (.docx) mit Abbildungen."),
}
