#!/usr/bin/env python3
"""Descargador asistido de facturas electronicas DIAN por CUFE.

Uso tipico:
    python run.py                      # procesa todo lo pendiente de INPUT_FILE
    python run.py --input mis.xlsx     # usa otro archivo de entrada
    python run.py --only <CUFE>        # un solo documento
    python run.py --retry-failed       # reintenta los que fallaron
    python run.py --no-print           # descarga sin imprimir
    python run.py --inspect <CUFE>     # modo diagnostico (vuelca DOM para afinar)
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from src.config import Config
from src.dian_client import DianClient
from src.input_reader import Job, read_jobs
from src.logging_setup import setup_logging
from src.pdf_unlock import UnlockError, process_download
from src.printer import print_file
from src.tracker import Tracker


def _select_jobs(jobs: list[Job], tracker: Tracker, args) -> list[Job]:
    if args.only:
        return [j for j in jobs if j.cufe == args.only] or [Job(cufe=args.only, row=0)]
    if args.retry_failed:
        return [j for j in jobs if tracker.get(j.cufe).get("status") == "failed"]
    return [j for j in jobs if not tracker.is_done(j.cufe)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Descarga asistida de facturas DIAN por CUFE")
    parser.add_argument("--input", help="Ruta al Excel/CSV de CUFEs (sobrescribe .env)")
    parser.add_argument("--only", help="Procesar un unico CUFE")
    parser.add_argument("--retry-failed", action="store_true", help="Reintentar los fallidos")
    parser.add_argument("--no-print", action="store_true", help="No imprimir")
    parser.add_argument("--limit", type=int, default=0, help="Maximo de documentos a procesar")
    parser.add_argument("--inspect", metavar="CUFE", help="Modo diagnostico: vuelca el DOM")
    args = parser.parse_args()

    base = Path(__file__).resolve().parent
    cfg = Config.load(env_path=base / ".env")
    if args.input:
        cfg.input_file = Path(args.input).expanduser()

    log, run_id = setup_logging(cfg.download_dir / "logs")
    if cfg.errors:
        for e in cfg.errors:
            log.error("CONFIG: %s", e)
        return 2
    cfg.ensure_dirs()

    # Modo diagnostico: no requiere lista de entrada.
    if args.inspect:
        with DianClient(cfg) as client:
            client.inspect(args.inspect, cfg.download_dir / "inspect")
        return 0

    try:
        all_jobs = read_jobs(cfg.input_file)
    except (FileNotFoundError, ValueError) as exc:
        log.error("ENTRADA: %s", exc)
        return 2

    tracker = Tracker(cfg.download_dir / "estado.json")
    jobs = _select_jobs(all_jobs, tracker, args)
    if args.limit:
        jobs = jobs[: args.limit]

    if not jobs:
        log.info("No hay documentos pendientes. (done/failed: %s)", tracker.summary())
        return 0

    log.info("Pendientes: %d de %d totales.", len(jobs), len(all_jobs))
    ok = fail = 0

    with DianClient(cfg) as client:
        for i, job in enumerate(jobs, 1):
            for w in job.warnings:
                log.warning(w)
            password = job.nit or cfg.nit
            tag = job.cufe[-12:]
            log.info("[%d/%d] Procesando CUFE ...%s", i, len(jobs), tag)
            try:
                raw = client.fetch_document(job, password, cfg.download_dir / "_crudo")

                subdir = cfg.download_dir / (job.proveedor or "")
                out_pdf = subdir / f"{job.safe_name()}.pdf"
                process_download(raw, password, out_pdf)
                log.info("PDF listo: %s", out_pdf)

                if cfg.auto_print and not args.no_print:
                    if print_file(out_pdf, cfg.printer_name):
                        log.info("Enviado a imprimir: %s", out_pdf.name)

                tracker.mark_done(job.cufe, str(out_pdf), run_id)
                ok += 1
            except (UnlockError, RuntimeError, Exception) as exc:  # aislar por documento
                fail += 1
                log.error("FALLO CUFE ...%s: %s", tag, exc)
                tracker.mark_failed(job.cufe, str(exc), run_id)
                try:
                    shot = cfg.download_dir / "logs" / f"error_{tag}.png"
                    client.page.screenshot(path=str(shot))
                    log.error("Captura de error: %s", shot)
                except Exception:
                    pass

            if i < len(jobs):
                time.sleep(cfg.pacing_seconds)  # ritmo respetuoso

    log.info("FIN. OK=%d FALLIDOS=%d | estado acumulado: %s", ok, fail, tracker.summary())
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
