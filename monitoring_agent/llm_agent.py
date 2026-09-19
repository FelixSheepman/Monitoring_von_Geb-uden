"""
LLM-gestuetzte Auswertung (Claude) als Gegenstueck zur regelbasierten Auswertung in narrative.py.

Wichtig fuer die Nachvollziehbarkeit: Alle Zahlen werden weiterhin deterministisch im Code
berechnet. Das Sprachmodell erhaelt nur diese Kennzahlen ("Fakten") und formuliert daraus die
fachliche Einordnung. Es darf keine Zahlen erfinden.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

from .narrative import NarrativeBlock

MODELS = {
    "claude-opus-5": "Claude Opus 5 (leistungsstärkster, Standard)",
    "claude-sonnet-5": "Claude Sonnet 5 (günstiger)",
}
FALLBACK_MODELS = {"claude-opus-5"}

FIGURE_KEYS = [
    "wmz_kumuliert", "regelguete_stat_heizung", "heizkurve", "carpet_rlt_vl", "carpet_rlt_rl",
    "regelguete_fbh", "zonenvergleich", "delta_t", "rlt_aul_zul", "strom_rlt_taeglich", "waerme_taeglich",
]

SYSTEM_PROMPT = """Du bist Ingenieur für Technisches Monitoring und Energieoptimierung von Nichtwohngebäuden \
(Heizung, Lüftung, Kälte). Du schreibst die Auswertung eines Monitoringberichts für eine Masterarbeit \
(Bauingenieurwesen, Energieeffiziente Nichtwohngebäude).

Regeln:
- Verwende ausschließlich die Zahlen aus den gelieferten Fakten. Erfinde keine Werte und rechne keine neuen Kennzahlen aus.
- Wenn die Faktenlage für eine Aussage nicht reicht, benenne das ausdrücklich als offen.
- Schreibe sachlich, in vollständigen deutschen Sätzen, im Stil eines technischen Berichts (kein Marketing, keine Aufzählungszeichen im Text).
- Ordne die Befunde ein: mögliche Ursache in der Anlagentechnik/Regelung, Auswirkung auf Energieverbrauch oder Komfort, und eine konkrete Optimierungsempfehlung.
- Verknüpfe zusammenhängende Befunde (z.B. Heizkurve und Sommerverbrauch), statt sie nur aufzuzählen.
- Der Objekttyp ist ein Klinik-/Krankenhauskomplex: Bereiche wie Intensivpflege benötigen ganzjährig sichere Bedingungen, ein Dauerbetrieb kann dort teilweise begründet sein.

Antworte ausschließlich mit einem JSON-Array (ohne Markdown-Codeblock), jedes Element:
{"heading": "<kurze Überschrift>", "figure_keys": ["<Schlüssel>", ...], "text": "<Fließtext, 3-6 Sätze>"}
Erlaubte figure_keys: %s
Erzeuge 5 bis 7 Elemente, das letzte fasst die wichtigsten Optimierungsmaßnahmen zusammen (figure_keys darf dort leer sein).""" % ", ".join(FIGURE_KEYS)


@dataclass
class LLMResult:
    blocks: list[NarrativeBlock]
    seconds: float
    input_tokens: int
    output_tokens: int
    model: str
    fallback_used: bool = False


def build_facts(report) -> str:
    """Verdichtet den Report zu den Fakten, die das Modell sehen darf (JSON)."""
    df = report.df
    q = report.quality_df
    facts = {
        "datensatz": {
            "zeitraum": f"{df.index.min():%d.%m.%Y} bis {df.index.max():%d.%m.%Y}",
            "zeitschritte": int(len(df)),
            "intervall_minuten": 15,
            "spalten": int(df.shape[1]),
        },
        "datenpruefung_auffaellig": [
            {"spalte": int(r["Spalte"]), "bezeichnung": r["Bezeichnung"], "befund": r["Bewertung"]}
            for _, r in q[q["Plausibilität"] == "Auffällig!"].iterrows()
        ],
        "datenpruefung_plausibel_anzahl": int((q["Plausibilität"] == "Plausibel").sum()),
        "regelbasierte_befunde": [
            {"ueberschrift": b.heading, "figure_keys": b.figure_keys, "text": b.text} for b in report.narrative
        ],
    }
    if report.anomaly_counts:
        facts["anomalie_zaehler"] = report.anomaly_counts
    return json.dumps(facts, ensure_ascii=False, indent=1)


def parse_blocks(text: str) -> list[NarrativeBlock]:
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end < start:
        raise ValueError("Die Modellantwort enthält kein JSON-Array.")
    items = json.loads(text[start:end + 1])
    blocks = []
    for it in items:
        keys = [k for k in it.get("figure_keys", []) if k in FIGURE_KEYS]
        blocks.append(NarrativeBlock(keys, str(it["heading"]), str(it["text"])))
    return blocks


def generate_narrative(facts: str, client, model: str = "claude-opus-5") -> LLMResult:
    """`client` ist ein anthropic.Anthropic-Client (in Tests ein Mock)."""
    kwargs = dict(
        model=model,
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": "Fakten des Monitoringberichts:\n\n" + facts}],
    )
    if model in FALLBACK_MODELS:
        kwargs["extra_headers"] = {"anthropic-beta": "server-side-fallback-2026-07-01"}
        kwargs["extra_body"] = {"fallbacks": "default"}

    t0 = time.perf_counter()
    response = client.messages.create(**kwargs)
    seconds = time.perf_counter() - t0

    if response.stop_reason == "refusal":
        raise RuntimeError("Das Modell hat die Anfrage abgelehnt (refusal).")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Die Antwort wurde wegen des Token-Limits abgeschnitten.")

    text = "".join(b.text for b in response.content if b.type == "text")
    fallback_used = any(getattr(b, "type", "") == "fallback" for b in response.content)
    return LLMResult(
        blocks=parse_blocks(text), seconds=seconds,
        input_tokens=response.usage.input_tokens, output_tokens=response.usage.output_tokens,
        model=model, fallback_used=fallback_used,
    )


def make_client(api_key: str):
    import anthropic
    return anthropic.Anthropic(api_key=api_key)
