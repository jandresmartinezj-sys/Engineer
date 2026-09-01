"""Lee la lista de CUFEs desde Excel (.xlsx) o CSV y la normaliza a Jobs.

Detecta columnas sin importar mayusculas/acentos. Columna obligatoria: cufe.
Opcionales: nit (contrasena por fila), nombre (nombre de archivo de salida),
proveedor (subcarpeta para organizar).
"""
from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Job:
    cufe: str
    nit: str | None = None       # sobrescribe el NIT global si viene en la fila
    nombre: str | None = None    # nombre de archivo deseado (sin extension)
    proveedor: str | None = None
    row: int = 0
    warnings: list[str] = field(default_factory=list)

    def safe_name(self) -> str:
        """Nombre de archivo seguro: usa 'nombre' o los ultimos 12 chars del CUFE."""
        base = self.nombre or f"factura_{self.cufe[-12:]}"
        return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", base).strip() or self.cufe[-12:]


def _norm(text: str) -> str:
    """minusculas, sin acentos, sin espacios extremos: para casar encabezados."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.strip().lower()


# alias de encabezados -> campo canonico
_HEADER_ALIASES = {
    "cufe": "cufe", "cude": "cufe", "documentkey": "cufe", "clave": "cufe",
    "codigo": "cufe", "codigo unico": "cufe",
    "nit": "nit", "password": "nit", "contrasena": "nit", "clave documento": "nit",
    "nombre": "nombre", "archivo": "nombre", "nombre archivo": "nombre",
    "proveedor": "proveedor", "emisor": "proveedor", "vendedor": "proveedor",
}

_CUFE_RE = re.compile(r"^[0-9a-fA-F]{40,120}$")


def _map_headers(headers: list[str]) -> dict[int, str]:
    mapping: dict[int, str] = {}
    for i, h in enumerate(headers):
        key = _HEADER_ALIASES.get(_norm(h or ""))
        if key:
            mapping[i] = key
    return mapping


def _rows_from_csv(path: Path) -> list[list[str]]:
    # Detecta delimitador (coma o punto y coma, comun en Excel-ES).
    sample = path.read_text(encoding="utf-8-sig", errors="replace")[:4096]
    delim = ";" if sample.count(";") > sample.count(",") else ","
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return [row for row in csv.reader(fh, delimiter=delim)]


def _rows_from_xlsx(path: Path) -> list[list[str]]:
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows: list[list[str]] = []
    for r in ws.iter_rows(values_only=True):
        rows.append(["" if c is None else str(c) for c in r])
    wb.close()
    return rows


def read_jobs(path: str | Path) -> list[Job]:
    path = Path(path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"No existe el archivo de entrada: {path}")

    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        rows = _rows_from_xlsx(path)
    elif suffix in {".csv", ".txt", ""}:
        rows = _rows_from_csv(path)
    else:
        raise ValueError(f"Formato no soportado: {suffix}. Usa .xlsx o .csv")

    rows = [r for r in rows if any((c or "").strip() for c in r)]  # descarta filas vacias
    if not rows:
        raise ValueError(f"El archivo {path.name} no tiene datos.")

    header_map = _map_headers(rows[0])
    if "cufe" not in header_map.values():
        raise ValueError(
            "No encontre una columna de CUFE. Encabezados aceptados: "
            "cufe, cude, documentkey, clave, codigo. "
            f"Encabezados detectados: {rows[0]}"
        )

    jobs: list[Job] = []
    seen: set[str] = set()
    for idx, row in enumerate(rows[1:], start=2):
        record: dict[str, str] = {}
        for col, field_name in header_map.items():
            if col < len(row):
                record[field_name] = (row[col] or "").strip()

        cufe = record.get("cufe", "")
        if not cufe:
            continue
        if cufe in seen:
            continue  # idempotencia a nivel de entrada: sin duplicados
        seen.add(cufe)

        job = Job(
            cufe=cufe,
            nit=record.get("nit") or None,
            nombre=record.get("nombre") or None,
            proveedor=record.get("proveedor") or None,
            row=idx,
        )
        if not _CUFE_RE.match(cufe):
            job.warnings.append(
                f"El CUFE de la fila {idx} no parece hexadecimal valido "
                f"(len={len(cufe)}). Se intentara igual."
            )
        jobs.append(job)

    if not jobs:
        raise ValueError("No se encontraron CUFEs validos en el archivo.")
    return jobs
