"""Impresion del PDF final. Multiplataforma, con impresora predeterminada o nombrada.

En Windows la via mas fiable para impresora nombrada es SumatraPDF (si esta
instalado). Si no, se usa el verbo 'print' del visor PDF predeterminado.
Nunca es fatal: un fallo de impresion no pierde el archivo ya descargado.
"""
from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger("dian.printer")

# Rutas tipicas de SumatraPDF en Windows (silencioso, permite impresora nombrada).
_SUMATRA_CANDIDATES = [
    r"C:\Program Files\SumatraPDF\SumatraPDF.exe",
    r"C:\Program Files (x86)\SumatraPDF\SumatraPDF.exe",
]


def _find_sumatra() -> str | None:
    for p in _SUMATRA_CANDIDATES:
        if Path(p).exists():
            return p
    return shutil.which("SumatraPDF") or shutil.which("SumatraPDF.exe")


def print_file(path: str | Path, printer_name: str | None = None) -> bool:
    """Envia el PDF a imprimir. Devuelve True si el comando se lanzo sin error."""
    path = Path(path)
    if not path.exists():
        log.error("No existe el archivo a imprimir: %s", path)
        return False

    system = platform.system()
    try:
        if system == "Windows":
            return _print_windows(path, printer_name)
        # macOS / Linux: CUPS
        if shutil.which("lp"):
            cmd = ["lp"]
            if printer_name:
                cmd += ["-d", printer_name]
            cmd.append(str(path))
            subprocess.run(cmd, check=True)
            return True
        log.warning("No hay 'lp' disponible; se omite la impresion de %s", path.name)
        return False
    except Exception as exc:  # impresion nunca debe tumbar el flujo
        log.error("Fallo al imprimir %s: %s", path.name, exc)
        return False


def _print_windows(path: Path, printer_name: str | None) -> bool:
    sumatra = _find_sumatra()
    if sumatra:
        cmd = [sumatra, "-silent"]
        if printer_name:
            cmd += ["-print-to", printer_name]
        else:
            cmd += ["-print-to-default"]
        cmd.append(str(path))
        subprocess.run(cmd, check=True)
        return True

    if printer_name:
        log.warning(
            "Se pidio impresora '%s' pero SumatraPDF no esta instalado; "
            "se imprimira en la predeterminada. Instala SumatraPDF para elegir impresora.",
            printer_name,
        )
    # Verbo 'print' del visor PDF predeterminado -> impresora predeterminada.
    os.startfile(str(path), "print")  # type: ignore[attr-defined]  # solo Windows
    return True
