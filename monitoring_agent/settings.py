"""Schaltbare Funktionen der App (im Einstellungsmenue an-/abschaltbar)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    show_timings: bool = True
    show_anomalies: bool = True
    show_comparison: bool = True
    use_llm: bool = False
    enable_word_export: bool = True
    llm_model: str = "claude-opus-5"


FEATURE_LABELS = {
    "show_timings": ("Laufzeitmessung", "Zeigt, wie lange Prüfung, Grafiken und Auswertung dauern (Zeitvergleich manuell vs. Agent)."),
    "show_anomalies": ("Anomalien in Diagrammen markieren", "Rote Marker bei Nullwert-Aussetzern, Zählerrücksprüngen und Delta T < 2 K."),
    "show_comparison": ("Vergleichsansicht (Kap. 8)", "Stellt eure manuelle Auswertung der Agent-Auswertung gegenüber."),
    "use_llm": ("LLM-Auswertung (Claude)", "Ein Sprachmodell formuliert die Auswertung; benötigt einen Anthropic-API-Key."),
    "enable_word_export": ("Word-Berichtsexport", "Erzeugt einen formatierten Bericht (.docx) mit Abbildungen."),
}
