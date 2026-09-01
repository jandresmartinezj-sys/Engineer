#!/usr/bin/env python3
"""Descifra en lote los PDF que el userscript descargo desde DIAN.

Los PDF que baja DIAN vienen cifrados con el NIT y con nombre <CUFE>.pdf.
Este script los descifra (contrasena = NIT), los guarda sin contrasena en una
carpeta de salida, y opcionalmente los imprime. Es idempotente: si el PDF de
salida ya existe, lo salta.

Uso:
    python procesar_descargas.py                     # Descargas -> ./descargas/pdf
    python procesar_descargas.py --dir "C:\\Users\\Admin\\Downloads"
    python procesar_descargas.py --nit 900425099 --print
    python procesar_descargas.py --todos             # procesa TODOS los .pdf (no solo CUFE)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from src.config import Config
from src.pdf_unlock import UnlockError, process_download
from src.printer import print_file

CUFE_LIKE = re.compile(r"^[0-9a-fA-F]{40,120}$")


def default_downloads() -> Path:
    return Path.home() / "Downloads"


def main() -> int:
    ap = argparse.ArgumentParser(description="Descifra en lote PDFs DIAN descargados")
    ap.add_argument("--dir", help="Carpeta con los PDF descargados (default: Descargas)")
    ap.add_argument("--out", help="Carpeta de salida (default: ./descargas/pdf)")
    ap.add_argument("--nit", help="NIT/contrasena (default: DIAN_NIT del .env)")
    ap.add_argument("--print", dest="do_print", action="store_true", help="Imprimir cada PDF")
    ap.add_argument("--printer", help="Nombre de impresora (Windows, requiere SumatraPDF)")
    ap.add_argument("--todos", action="store_true",
                    help="Procesa todos los .pdf, no solo los que parecen CUFE")
    args = ap.parse_args()

    base = Path(__file__).resolve().parent
    cfg = Config.load(env_path=base / ".env")
    nit = (args.nit or cfg.nit or "").strip()
    if not nit:
        print("ERROR: falta el NIT. Usa --nit 900425099 o define DIAN_NIT en .env")
        return 2

    src_dir = Path(args.dir).expanduser() if args.dir else default_downloads()
    out_dir = Path(args.out).expanduser() if args.out else (base / "descargas" / "pdf")
    out_dir.mkdir(parents=True, exist_ok=True)
    if not src_dir.exists():
        print(f"ERROR: no existe la carpeta {src_dir}")
        return 2

    pdfs = sorted(p for p in src_dir.glob("*.pdf"))
    if not args.todos:
        pdfs = [p for p in pdfs if CUFE_LIKE.match(p.stem)]
    if not pdfs:
        print(f"No hay PDFs para procesar en {src_dir} "
              f"({'todos' if args.todos else 'con nombre tipo CUFE'}).")
        return 0

    ok = skip = fail = 0
    for p in pdfs:
        out = out_dir / p.name
        if out.exists():
            skip += 1
            continue
        try:
            process_download(p, nit, out)
            ok += 1
            print(f"OK   {p.name}")
            if args.do_print:
                print_file(out, args.printer or cfg.printer_name)
        except UnlockError as e:
            fail += 1
            print(f"FALLA {p.name}: {e}")
        except Exception as e:  # noqa: BLE001
            fail += 1
            print(f"ERROR {p.name}: {e}")

    print(f"\nListo. Descifrados={ok}  ya-existian={skip}  fallidos={fail}")
    print(f"Salida: {out_dir}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
