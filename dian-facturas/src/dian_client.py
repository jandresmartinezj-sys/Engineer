"""Navegacion asistida al portal publico de DIAN (consulta por CUFE).

IMPORTANTE (limitacion honesta): el DOM exacto del portal DIAN no pudo verificarse
al construir esta herramienta. Por eso el flujo es RESILIENTE:
  1. Intenta autollenar el NIT y hacer clic en Descargar con selectores candidatos.
  2. Si no encuentra algo, CEDE EL CONTROL al humano (que ya debe resolver el
     captcha de todos modos) y captura la descarga la dispare quien la dispare.
Los selectores candidatos estan marcados con TODO-CONFIRMAR: ajustar tras la
primera corrida real usando `python run.py --inspect <CUFE>`.
"""
from __future__ import annotations

import logging
from pathlib import Path

from playwright.sync_api import (
    BrowserContext,
    Download,
    TimeoutError as PWTimeout,
    sync_playwright,
)

from .config import Config
from .input_reader import Job

log = logging.getLogger("dian.client")

# TODO-CONFIRMAR: selectores candidatos. Ajustar con --inspect en la primera corrida.
NIT_SELECTORS = [
    "input[type=password]",
    "input[placeholder*='NIT' i]",
    "input[name*='nit' i]",
    "input[id*='nit' i]",
    "input[name*='password' i]",
]
DOWNLOAD_SELECTORS = [
    "a:has-text('Descargar PDF')",
    "button:has-text('Descargar PDF')",
    "a:has-text('Descargar')",
    "button:has-text('Descargar')",
    "a:has-text('PDF')",
    "[title*='Descargar' i]",
    "[aria-label*='Descargar' i]",
]
CAPTCHA_SELECTORS = [
    "iframe[src*='recaptcha']",
    ".g-recaptcha",
    "iframe[title*='captcha' i]",
]


class DianClient:
    def __init__(self, cfg: Config, interactive: bool = True):
        self.cfg = cfg
        self.interactive = interactive
        self._pw = None
        self._ctx: BrowserContext | None = None

    def __enter__(self) -> "DianClient":
        self._pw = sync_playwright().start()
        self._ctx = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(self.cfg.user_data_dir),
            headless=self.cfg.headless,          # False: el captcha necesita ver el navegador
            accept_downloads=True,
        )
        self._ctx.set_default_timeout(self.cfg.nav_timeout_ms)
        return self

    def __exit__(self, *exc) -> None:
        try:
            if self._ctx:
                self._ctx.close()
        finally:
            if self._pw:
                self._pw.stop()

    @property
    def page(self):
        assert self._ctx is not None
        return self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()

    # ---------- helpers de UI (best-effort) ----------

    def _try_fill_nit(self, page, password: str) -> bool:
        for sel in NIT_SELECTORS:
            try:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=1500):
                    loc.fill(password, timeout=2000)
                    log.info("NIT autollenado (selector: %s)", sel)
                    return True
            except Exception:
                continue
        log.info("No se pudo autollenar el NIT; lo hara el humano si el sitio lo pide.")
        return False

    def _captcha_present(self, page) -> bool:
        for sel in CAPTCHA_SELECTORS:
            try:
                if page.locator(sel).first.is_visible(timeout=800):
                    return True
            except Exception:
                continue
        return False

    def _human_gate(self, page, job: Job) -> None:
        """Cede el control al humano para captcha / pasos que no pudimos automatizar."""
        captcha = self._captcha_present(page)
        tag = job.cufe[-12:]
        print("\n" + "=" * 68)
        print(f"  DOCUMENTO CUFE ...{tag}")
        if captcha:
            print("  * Se detecto un CAPTCHA. Resuelvelo en la ventana del navegador.")
        print("  * Verifica que el documento este visible y listo para descargar.")
        print("  * Si el NIT no quedo puesto, escribelo tu en la pagina.")
        print("=" * 68)
        if self.interactive:
            input("  Cuando este listo, presiona ENTER aqui para continuar... ")

    def _try_click_download(self, page) -> bool:
        for sel in DOWNLOAD_SELECTORS:
            try:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=1200):
                    loc.click(timeout=3000)
                    log.info("Clic en descarga (selector: %s)", sel)
                    return True
            except Exception:
                continue
        return False

    # ---------- API principal ----------

    def fetch_document(self, job: Job, password: str, raw_dir: Path) -> Path:
        """Navega, deja que el humano resuelva el captcha y captura la descarga.

        Devuelve la ruta del archivo crudo descargado (PDF o ZIP, aun con contrasena).
        """
        raw_dir.mkdir(parents=True, exist_ok=True)
        page = self.page
        url = self.cfg.search_url + job.cufe
        log.info("Abriendo CUFE ...%s", job.cufe[-12:])
        page.goto(url, wait_until="domcontentloaded", timeout=self.cfg.nav_timeout_ms)

        self._try_fill_nit(page, password)
        self._human_gate(page, job)

        # expect_download espera el evento aunque el clic lo haga el humano.
        try:
            with page.expect_download(timeout=self.cfg.captcha_timeout * 1000) as dl_info:
                if not self._try_click_download(page):
                    print("  No encontre el boton de descarga automaticamente.")
                    print("  --> Haz clic tu en 'Descargar'. Espero el archivo...")
                download: Download = dl_info.value
        except PWTimeout as exc:
            raise RuntimeError(
                "No se detecto ninguna descarga a tiempo. "
                "Revisa si el documento existe o si falto resolver el captcha."
            ) from exc

        suggested = download.suggested_filename or f"{job.safe_name()}.bin"
        raw_path = raw_dir / f"{job.safe_name()}__{suggested}"
        download.save_as(str(raw_path))
        log.info("Descargado: %s", raw_path.name)
        return raw_path

    def inspect(self, cufe: str, out_dir: Path) -> None:
        """Modo diagnostico: vuelca HTML + captura para afinar selectores."""
        out_dir.mkdir(parents=True, exist_ok=True)
        page = self.page
        page.goto(self.cfg.search_url + cufe, wait_until="domcontentloaded")
        input("Resuelve el captcha si aparece y presiona ENTER para capturar el DOM... ")
        (out_dir / "pagina.html").write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(out_dir / "pagina.png"), full_page=True)
        print(f"Guardado: {out_dir/'pagina.html'} y {out_dir/'pagina.png'}")
        print("Enviame esos dos archivos para fijar los selectores reales.")
