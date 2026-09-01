"""Carga y valida la configuracion desde variables de entorno / .env.

Todos los secretos (NIT) viven en .env, nunca en el codigo ni en el repo.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Pagina real de descarga de documentos (confirmada por el usuario).
# El parametro DocumentKey es el CUFE (o CUDE en documentos equivalentes).
DIAN_SEARCH_URL = "https://certificate-vpfe.dian.gov.co/User/SearchDocument?DocumentKey="


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "si", "sí", "on"}


@dataclass
class Config:
    nit: str
    input_file: Path
    download_dir: Path
    user_data_dir: Path
    headless: bool = False           # DEBE ser False: el captcha necesita navegador visible
    auto_print: bool = False
    printer_name: str | None = None
    pacing_seconds: float = 3.0      # pausa respetuosa entre documentos
    captcha_timeout: int = 300       # segundos que esperamos al humano por doc
    nav_timeout_ms: int = 45000
    search_url: str = DIAN_SEARCH_URL
    errors: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, env_path: str | os.PathLike | None = None) -> "Config":
        # load_dotenv no sobrescribe variables ya presentes en el entorno real.
        load_dotenv(dotenv_path=env_path, override=False)

        base = Path(__file__).resolve().parent.parent

        nit = (os.getenv("DIAN_NIT") or "").strip()
        input_file = Path(os.getenv("INPUT_FILE", str(base / "facturas.csv"))).expanduser()
        download_dir = Path(os.getenv("DOWNLOAD_DIR", str(base / "descargas"))).expanduser()
        user_data_dir = Path(
            os.getenv("BROWSER_PROFILE_DIR", str(base / ".browser-profile"))
        ).expanduser()

        cfg = cls(
            nit=nit,
            input_file=input_file,
            download_dir=download_dir,
            user_data_dir=user_data_dir,
            headless=_as_bool(os.getenv("HEADLESS"), False),
            auto_print=_as_bool(os.getenv("AUTO_PRINT"), False),
            printer_name=(os.getenv("PRINTER_NAME") or "").strip() or None,
            pacing_seconds=float(os.getenv("PACING_SECONDS", "3")),
            captcha_timeout=int(os.getenv("CAPTCHA_TIMEOUT", "300")),
            nav_timeout_ms=int(os.getenv("NAV_TIMEOUT_MS", "45000")),
        )
        cfg._validate()
        return cfg

    def _validate(self) -> None:
        if not self.nit:
            self.errors.append(
                "DIAN_NIT vacio. Define tu NIT (sin digito de verificacion salvo que "
                "DIAN lo pida) en el archivo .env. Es la contrasena de los documentos."
            )
        if self.headless:
            self.errors.append(
                "HEADLESS=true no es compatible: el captcha de DIAN requiere navegador "
                "visible. Usa HEADLESS=false."
            )

    def ensure_dirs(self) -> None:
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.user_data_dir.mkdir(parents=True, exist_ok=True)
