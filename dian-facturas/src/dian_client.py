"""Navegacion al portal DIAN (certificate-vpfe / catalogo-vpfe) por CUFE.

Secuencia real (confirmada por capturas del usuario):
  1. Abrir SearchDocument?DocumentKey=<CUFE>  -> el CUFE queda prellenado.
  2. Llenar el campo "NIT del Emisor o Receptor del documento".
  3. Cloudflare Turnstile: normalmente pasa solo ("Operacion exitosa"). Si
     realmente desafia, se cede el control al humano (pausa adaptativa).
  4. Clic en "Buscar" -> carga el documento.
  5. Modal "Este archivo contiene contrasena..." -> clic "Aceptar".
  6. Clic en "Descargar PDF" -> Playwright captura la descarga (sin dialogo nativo).
El PDF descargado esta cifrado con el NIT; lo descifra src/pdf_unlock.py.

Diseno resiliente: cada paso intenta selectores concretos y, si falla, cede el
control al humano sin abortar. Afinar con `python run.py --inspect <CUFE>`.
"""
from __future__ import annotations

import logging
import re
import time
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

# Selectores basados en las capturas reales. Ajustar con --inspect si cambian.
CUFE_SELECTORS = [
    "input[placeholder*='CUFE' i]",
    "input[name*='cufe' i]",
    "input[name*='documentkey' i]",
]
NIT_SELECTORS = [
    "input[placeholder*='NIT' i]",
    "input[name*='nit' i]",
    "input[id*='nit' i]",
]
BUSCAR_SELECTORS = [
    "button:has-text('Buscar'):not(:has-text('Documento'))",
    "input[type=submit][value*='Buscar' i]",
    "button:text-is('Buscar')",
]
ACEPTAR_SELECTORS = [
    "button:has-text('Aceptar')",
    ".modal button:has-text('Aceptar')",
    "button:text-is('Aceptar')",
]
DESCARGAR_SELECTORS = [
    "a:has-text('Descargar PDF')",
    "button:has-text('Descargar PDF')",
    "a:has-text('Descargar')",
    "[title*='Descargar' i]",
]
TURNSTILE_PRESENT = "iframe[src*='challenges.cloudflare.com'], .cf-turnstile"


class DianClient:
    def __init__(self, cfg: Config, interactive: bool = True):
        self.cfg = cfg
        self.interactive = interactive
        self._pw = None
        self._ctx: BrowserContext | None = None

    def __enter__(self) -> "DianClient":
        self._pw = sync_playwright().start()
        # Flags para reducir la huella de automatizacion (evita que DIAN/Cloudflare
        # redirija al endpoint que exige certificado).
        base = dict(
            user_data_dir=str(self.cfg.user_data_dir),
            headless=self.cfg.headless,
            accept_downloads=True,
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
            locale="es-CO",
            timezone_id="America/Bogota",
        )
        if self.cfg.client_cert_path:  # mTLS solo si se configura explicitamente
            base["client_certificates"] = [{
                "origin": self.cfg.cert_origin,
                "pfxPath": self.cfg.client_cert_path,
                "passphrase": self.cfg.client_cert_pass or "",
            }]
            log.info("Certificado de cliente configurado para %s", self.cfg.cert_origin)

        self._ctx = self._launch_context(base)
        self._ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        self._ctx.set_default_timeout(self.cfg.nav_timeout_ms)
        return self

    def _launch_context(self, base: dict):
        """Lanza el navegador real elegido; si no esta, cae al Chromium interno."""
        attempts = []
        if self.cfg.browser_executable:
            attempts.append(("ejecutable " + self.cfg.browser_executable,
                             {**base, "executable_path": self.cfg.browser_executable}))
        elif self.cfg.browser_channel:
            attempts.append((f"canal {self.cfg.browser_channel}",
                             {**base, "channel": self.cfg.browser_channel}))
        attempts.append(("chromium interno", base))  # fallback

        last_err = None
        for descr, kwargs in attempts:
            try:
                ctx = self._pw.chromium.launch_persistent_context(**kwargs)
                log.info("Navegador: %s", descr)
                return ctx
            except Exception as exc:
                log.warning("No pude abrir %s: %s", descr, exc)
                last_err = exc
        raise RuntimeError(f"No pude abrir ningun navegador. Ultimo error: {last_err}")

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

    # ---------- helpers ----------

    def _first_visible(self, page, selectors: list[str], timeout: int = 1500):
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=timeout):
                    return loc, sel
            except Exception:
                continue
        return None, None

    def _fill_nit(self, page, job: Job, password: str) -> None:
        # El CUFE suele venir prellenado por la URL; lo aseguramos si esta vacio.
        cufe_loc, _ = self._first_visible(page, CUFE_SELECTORS)
        if cufe_loc is None:
            cufe_loc = page.locator("input[type=text], input:not([type])").first
        try:
            if cufe_loc and not (cufe_loc.input_value() or "").strip():
                cufe_loc.fill(job.cufe)
        except Exception:
            pass

        nit_loc, sel = self._first_visible(page, NIT_SELECTORS)
        if nit_loc is None:
            # Fallback por etiqueta o segundo campo de texto de la pagina.
            try:
                nit_loc = page.get_by_label(re.compile("NIT del Emisor", re.I)).first
                if not nit_loc.is_visible(timeout=1000):
                    nit_loc = None
            except Exception:
                nit_loc = None
        if nit_loc is None:
            inputs = page.locator("input[type=text], input:not([type])")
            if inputs.count() >= 2:
                nit_loc = inputs.nth(1)
        if nit_loc is not None:
            try:
                nit_loc.fill(password)
                log.info("NIT autollenado (%s)", sel or "fallback")
                return
            except Exception:
                pass
        log.warning("No pude autollenar el NIT; el humano debera escribirlo.")

    def _wait_turnstile(self, page) -> None:
        """Espera a que Cloudflare Turnstile pase solo; pausa humana si desafia."""
        if page.locator(TURNSTILE_PRESENT).count() == 0:
            return  # no hay widget
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                token = page.evaluate(
                    "() => { const e = document.querySelector("
                    "'input[name=\"cf-turnstile-response\"]'); return e ? e.value : ''; }"
                )
            except Exception:
                token = ""
            if token:
                log.info("Turnstile resuelto automaticamente.")
                return
            page.wait_for_timeout(1000)
        log.info("Turnstile no paso solo en 20s.")
        if self.interactive:
            print("  * Cloudflare pide verificacion. Resuelvela en el navegador y")
            input("    presiona ENTER aqui para continuar... ")

    def _click_any(self, page, selectors: list[str], label: str, timeout: int = 4000) -> bool:
        loc, sel = self._first_visible(page, selectors, timeout=timeout)
        if loc is None:
            return False
        try:
            loc.click(timeout=timeout)
            log.info("Clic en %s (%s)", label, sel)
            return True
        except Exception as exc:
            log.warning("No pude clicar %s: %s", label, exc)
            return False

    # ---------- API principal ----------

    def fetch_document(self, job: Job, password: str, raw_dir: Path) -> Path:
        raw_dir.mkdir(parents=True, exist_ok=True)
        page = self.page
        log.info("Abriendo CUFE ...%s", job.cufe[-12:])
        page.goto(self.cfg.search_url + job.cufe,
                  wait_until="domcontentloaded", timeout=self.cfg.nav_timeout_ms)

        self._fill_nit(page, job, password)
        self._wait_turnstile(page)

        if not self._click_any(page, BUSCAR_SELECTORS, "Buscar"):
            print("  No encontre 'Buscar'. Haz clic tu en Buscar.")
            if self.interactive:
                input("    Presiona ENTER cuando cargue el documento... ")

        # Modal "Este archivo contiene contrasena..." (best-effort, puede no aparecer).
        self._click_any(page, ACEPTAR_SELECTORS, "Aceptar", timeout=6000)

        # Descarga (Playwright intercepta; no aparece el dialogo nativo del SO).
        try:
            with page.expect_download(timeout=self.cfg.captcha_timeout * 1000) as dl_info:
                if not self._click_any(page, DESCARGAR_SELECTORS, "Descargar PDF"):
                    print("  No encontre 'Descargar PDF'. Haz clic tu; espero el archivo...")
                download: Download = dl_info.value
        except PWTimeout as exc:
            raise RuntimeError(
                "No se detecto la descarga. Verifica que el documento exista y "
                "que se haya pasado la verificacion de Cloudflare."
            ) from exc

        suggested = download.suggested_filename or f"{job.safe_name()}.pdf"
        raw_path = raw_dir / f"{job.safe_name()}__{suggested}"
        download.save_as(str(raw_path))
        log.info("Descargado: %s", raw_path.name)
        return raw_path

    def inspect(self, cufe: str, out_dir: Path) -> None:
        """Modo diagnostico: vuelca HTML + captura para afinar selectores."""
        out_dir.mkdir(parents=True, exist_ok=True)
        page = self.page
        page.goto(self.cfg.search_url + cufe, wait_until="domcontentloaded")
        input("Ajusta lo necesario en el navegador y presiona ENTER para capturar... ")
        (out_dir / "pagina.html").write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(out_dir / "pagina.png"), full_page=True)
        print(f"Guardado: {out_dir/'pagina.html'} y {out_dir/'pagina.png'}")
