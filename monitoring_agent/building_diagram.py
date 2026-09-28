"""Zeichnet die Übersicht 'Gebäude -> Heizkreise' als eigenständiges SVG (siehe buildings.py)."""

from __future__ import annotations

import html

from .buildings import GEBAEUDE

BOX_W, BOX_H, GAP, PAD = 148, 64, 12, 16
HEADER_H = 36
TOP = 54
BG = "#f4f6f8"
INK = "#1c2733"
MUTED = "#5b6b7b"


def _wrap(text: str, max_chars: int = 15) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if len(trial) > max_chars and cur:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines[:2] if len(lines) <= 2 else [lines[0], lines[1][:max_chars - 1] + "…"]


def svg_overview(selected_zone: str | None = None) -> str:
    """SVG-Übersicht aller Gebäude und ihrer Heizkreise; der ausgewählte Kreis wird hervorgehoben."""
    widths = [len(g.kreise) * BOX_W + (len(g.kreise) - 1) * GAP + 2 * PAD for g in GEBAEUDE]
    # Kopfzeile (Gebäudename) kann breiter sein als die Kreis-Boxen darunter -> pro Gebäude umbrechen und die
    # größte benötigte Zeilenzahl fürs ganze Diagramm übernehmen, damit alle Boxen auf gleicher Höhe beginnen.
    name_lines = [_wrap(g.name, max(10, round(w / 7.4))) for g, w in zip(GEBAEUDE, widths)]
    header_h = HEADER_H + max(len(lines) for lines in name_lines) * 15

    building_gap = 28
    total_w = sum(widths) + building_gap * (len(GEBAEUDE) - 1) + 40
    total_h = TOP + header_h + BOX_H + PAD + 30

    parts = [f'<svg viewBox="0 0 {total_w} {total_h}" xmlns="http://www.w3.org/2000/svg" '
             f'role="img" aria-label="Übersicht der Gebäude und ihrer Heizkreise" style="width:100%;height:auto;font-family:Arial,sans-serif">',
             f'<rect x="0" y="0" width="{total_w}" height="{total_h}" fill="{BG}" rx="10"/>']

    x = 20
    for g, w, lines in zip(GEBAEUDE, widths, name_lines):
        parts.append(f'<rect x="{x}" y="{TOP}" width="{w}" height="{header_h + BOX_H + PAD}" rx="10" '
                     f'fill="none" stroke="{g.farbe}" stroke-width="2.5"/>')
        ty = TOP + 21 - (len(lines) - 1) * 7
        for line in lines:
            parts.append(f'<text x="{x + w / 2}" y="{ty}" text-anchor="middle" font-size="13.5" '
                         f'font-weight="700" fill="{g.farbe}">{html.escape(line)}</text>')
            ty += 16
        bx = x + PAD
        by = TOP + header_h
        for k in g.kreise:
            active = k.zone == selected_zone
            fill = g.farbe if active else "#ffffff"
            text_color = "#ffffff" if active else INK
            stroke = g.farbe
            parts.append(f'<rect x="{bx}" y="{by}" width="{BOX_W}" height="{BOX_H}" rx="7" '
                         f'fill="{fill}" stroke="{stroke}" stroke-width="{2.5 if active else 1.3}"/>')
            parts.append(f'<text x="{bx + 10}" y="{by + 17}" font-size="11" font-weight="700" fill="{text_color}">'
                         f'{k.nr}</text>')
            lines = _wrap(k.short)
            ly = by + BOX_H / 2 - (len(lines) - 1) * 7
            for line in lines:
                parts.append(f'<text x="{bx + BOX_W / 2 + 6}" y="{ly + 4}" text-anchor="middle" font-size="11.5" '
                             f'fill="{text_color}">{html.escape(line)}</text>')
                ly += 15
            bx += BOX_W + GAP
        x += w + building_gap

    parts.append(f'<text x="{total_w / 2}" y="{total_h - 8}" text-anchor="middle" font-size="11.5" fill="{MUTED}">'
                 f'7 eigenständige Heizkreise in 4 Gebäuden · Kreis anklicken für die eigene Auswertung</text>')
    parts.append("</svg>")
    return "".join(parts)
