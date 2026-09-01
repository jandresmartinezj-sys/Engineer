"""Verifica el descifrado de PDF y la extraccion de ZIP protegido con NIT."""
import io
import sys
from pathlib import Path

import pikepdf
import pyzipper
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.pdf_unlock import UnlockError, process_download  # noqa: E402

NIT = "900123456"


def _make_encrypted_pdf(password: str) -> bytes:
    pdf = pikepdf.Pdf.new()
    pdf.add_blank_page(page_size=(200, 200))
    out = io.BytesIO()
    pdf.save(out, encryption=pikepdf.Encryption(owner=password, user=password, R=6))
    return out.getvalue()


def _make_plain_pdf() -> bytes:
    pdf = pikepdf.Pdf.new()
    pdf.add_blank_page(page_size=(200, 200))
    out = io.BytesIO()
    pdf.save(out)
    return out.getvalue()


def test_encrypted_pdf_is_decrypted(tmp_path):
    src = tmp_path / "in.pdf"
    src.write_bytes(_make_encrypted_pdf(NIT))
    out = process_download(src, NIT, tmp_path / "out.pdf")
    # Debe abrir SIN contrasena tras el proceso.
    with pikepdf.open(out) as pdf:
        assert len(pdf.pages) == 1


def test_plain_pdf_passthrough(tmp_path):
    src = tmp_path / "in.pdf"
    src.write_bytes(_make_plain_pdf())
    out = process_download(src, NIT, tmp_path / "out.pdf")
    assert out.read_bytes()[:4] == b"%PDF"


def test_zip_with_inner_pdf(tmp_path):
    src = tmp_path / "in.zip"
    with pyzipper.AESZipFile(src, "w", encryption=pyzipper.WZ_AES) as zf:
        zf.setpassword(NIT.encode())
        zf.writestr("factura.pdf", _make_encrypted_pdf(NIT))
    out = process_download(src, NIT, tmp_path / "out.pdf")
    with pikepdf.open(out) as pdf:
        assert len(pdf.pages) == 1


def test_wrong_password_raises(tmp_path):
    src = tmp_path / "in.pdf"
    src.write_bytes(_make_encrypted_pdf(NIT))
    with pytest.raises(UnlockError):
        process_download(src, "000000", tmp_path / "out.pdf")


def test_non_document_content_raises(tmp_path):
    src = tmp_path / "in.html"
    src.write_bytes(b"<html>error DIAN</html>")
    with pytest.raises(UnlockError):
        process_download(src, NIT, tmp_path / "out.pdf")
