"""
PDF-Export: derselbe Bericht wie im HTML-/Word-Export (html_export.py), als PDF gedruckt.

Die Diagramme werden dazu als PNG eingebettet (static_figures) und die Seite mit einem headless Chrome/Chromium
gedruckt - derselbe Browser, den auch das Bildrendering des Word-Exports braucht (kaleido). Auf Streamlit Cloud
steht er ueber packages.txt zur Verfuegung.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .html_export import export_html

_CANDIDATES = ("chrome", "google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "msedge")
_WINDOWS_PATHS = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
)


def find_chrome() -> str | None:
    """Pfad zu Chrome/Chromium/Edge; Umgebungsvariable BROWSER_PATH hat Vorrang. None, wenn keiner gefunden wird."""
    env = os.environ.get("BROWSER_PATH")
    if env and Path(env).exists():
        return env
    for name in _CANDIDATES:
        found = shutil.which(name)
        if found:
            return found
    for p in _WINDOWS_PATHS:
        if Path(p).exists():
            return p
    return None


def export_pdf(report, path_or_buffer, narrative=None, comparison=None, include_savings: bool = True,
               include_assessment: bool = True, title: str = "Monitoringbericht", timeout: int = 240) -> list[str]:
    """Schreibt den Bericht als PDF (Dateipfad oder Puffer mit write()). Gibt Warnungen zurueck (z.B. fehlende
    Bilder). Wirft RuntimeError, wenn kein Chrome/Chromium gefunden wird oder der Druck fehlschlaegt."""
    chrome = find_chrome()
    if chrome is None:
        raise RuntimeError("Für den PDF-Export wird Google Chrome, Chromium oder Edge benötigt (kein Browser gefunden). "
                           "Alternativ den HTML-Bericht im Browser öffnen und mit Strg+P als PDF speichern.")
    with tempfile.TemporaryDirectory() as tmp:
        html_path, pdf_path = Path(tmp) / "bericht.html", Path(tmp) / "bericht.pdf"
        warnings = export_html(report, html_path, narrative=narrative, comparison=comparison,
                               include_savings=include_savings, include_assessment=include_assessment,
                               title=title, static_figures=True)
        cmd = [chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer",
               f"--user-data-dir={Path(tmp) / 'profile'}", f"--print-to-pdf={pdf_path}", html_path.as_uri()]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"Der PDF-Druck dauerte länger als {timeout} s und wurde abgebrochen.") from e
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Der PDF-Druck mit {Path(chrome).name} ist fehlgeschlagen: "
                               f"{e.stderr.decode(errors='replace')[-300:]}") from e
        if not pdf_path.exists() or pdf_path.stat().st_size == 0:
            raise RuntimeError("Der Browser hat keine PDF-Datei erzeugt.")
        data = pdf_path.read_bytes()
    if hasattr(path_or_buffer, "write"):
        path_or_buffer.write(data)
    else:
        Path(path_or_buffer).write_bytes(data)
    return warnings
