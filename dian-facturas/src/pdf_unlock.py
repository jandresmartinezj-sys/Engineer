"""Procesa el archivo descargado de DIAN y devuelve un PDF sin contrasena.

DIAN entrega el documento protegido con el NIT. El archivo descargado puede ser:
  - un PDF cifrado con contrasena = NIT, o
  - un ZIP protegido con contrasena = NIT que contiene el PDF (y a veces el XML),
    y el PDF interior puede estar tambien cifrado.

Este modulo detecta el tipo por 'magic bytes' (no confia en la extension) y
produce un unico PDF descifrado, listo para imprimir.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pikepdf
import pyzipper


class UnlockError(Exception):
    """Falla al descifrar/extraer con la contrasena dada."""


def _sniff(data: bytes) -> str:
    if data[:4] == b"%PDF":
        return "pdf"
    if data[:2] == b"PK":
        return "zip"
    return "unknown"


def _decrypt_pdf_bytes(data: bytes, password: str) -> bytes:
    """Devuelve los bytes de un PDF sin cifrar. Si ya venia sin cifrar, lo re-guarda."""
    try:
        pdf = pikepdf.open(io.BytesIO(data))  # no cifrado
    except pikepdf.PasswordError:
        try:
            pdf = pikepdf.open(io.BytesIO(data), password=password)
        except pikepdf.PasswordError as exc:
            raise UnlockError(
                "La contrasena (NIT) no abrio el PDF. Verifica el valor de DIAN_NIT."
            ) from exc
    out = io.BytesIO()
    with pdf:
        pdf.save(out)  # guarda sin cifrado
    return out.getvalue()


def _extract_pdf_from_zip(data: bytes, password: str) -> bytes:
    """Extrae el primer PDF de un ZIP protegido (AES via pyzipper o ZipCrypto)."""
    pwd = password.encode("utf-8")
    last_err: Exception | None = None

    for opener in (pyzipper.AESZipFile, zipfile.ZipFile):
        try:
            with opener(io.BytesIO(data)) as zf:  # type: ignore[arg-type]
                zf.setpassword(pwd)
                pdf_names = [n for n in zf.namelist() if n.lower().endswith(".pdf")]
                names = pdf_names or [n for n in zf.namelist() if not n.endswith("/")]
                if not names:
                    raise UnlockError("El ZIP no contiene archivos.")
                for name in names:
                    inner = zf.read(name)  # aqui valida la contrasena
                    if _sniff(inner) == "pdf" or name.lower().endswith(".pdf"):
                        return inner
                # ningun pdf: devuelve el primero para diagnostico aguas arriba
                return zf.read(names[0])
        except (RuntimeError, zipfile.BadZipFile, NotImplementedError) as exc:
            last_err = exc  # intenta el siguiente opener
            continue

    raise UnlockError(
        f"No pude abrir el ZIP con la contrasena (NIT). Detalle: {last_err}"
    )


def process_download(src_path: str | Path, password: str, out_path: str | Path) -> Path:
    """Convierte el archivo descargado en un PDF descifrado en out_path.

    Devuelve la ruta del PDF final. Lanza UnlockError si la contrasena no sirve.
    """
    src_path = Path(src_path)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    data = src_path.read_bytes()
    kind = _sniff(data)

    if kind == "zip":
        data = _extract_pdf_from_zip(data, password)
        kind = _sniff(data)

    if kind != "pdf":
        raise UnlockError(
            f"El contenido descargado no es un PDF reconocible (magic={data[:4]!r}). "
            "Puede que la pagina haya devuelto HTML/error en vez del documento."
        )

    pdf_bytes = _decrypt_pdf_bytes(data, password)
    out_path.write_bytes(pdf_bytes)
    return out_path
