# Descargador asistido de facturas DIAN (por CUFE)

Automatiza la descarga de facturas electronicas desde el portal de la DIAN
(`certificate-vpfe.dian.gov.co`) a partir de una lista de CUFEs en Excel/CSV.

## Importante: dos vias segun Cloudflare

El portal DIAN protege la busqueda con **Cloudflare Turnstile**, que **bloquea la
automatizacion externa** (Playwright/Selenium): al driver lo redirige al endpoint
que exige certificado o le niega el token ("La verificacion fallo"). Por eso:

- **Via recomendada (userscript):** corre dentro de TU navegador real, donde
  Turnstile pasa como humano. Ver [`userscript/README.md`](userscript/README.md).
  La descarga la hace el userscript; el descifrado en lote lo hace
  `procesar_descargas.py`.
- **Via Playwright (`run.py`):** queda como referencia y funciona en portales sin
  Turnstile, pero contra DIAN hoy la bloquea Cloudflare.

## Que hace (via Playwright, de referencia)

Secuencia real del portal (confirmada con capturas): abrir
`SearchDocument?DocumentKey=<CUFE>` (el CUFE queda prellenado) -> escribir el NIT
-> pasar la verificacion **Cloudflare Turnstile** -> **Buscar** -> modal
*"Este archivo contiene contrasena..."* -> **Aceptar** -> **Descargar PDF**. El PDF
que baja esta cifrado con el NIT; al abrirlo pide contrasena. La herramienta hace
toda esa cadena y ademas **quita la contrasena** para dejar el PDF listo para imprimir.

| Paso | Antes (manual) | Con la herramienta |
|------|----------------|--------------------|
| Tomar el CUFE | copiar/pegar uno por uno | lee la lista Excel/CSV |
| Entrar al documento | escribir URL | navega solo |
| Poner el NIT | a mano | autollenado |
| Verificacion Cloudflare | a veces un clic | pasa sola; pausa solo si desafia |
| Buscar / Aceptar / Descargar PDF | 3 clics | automatico |
| Quitar la contrasena (NIT) al PDF | a mano | automatico |
| Renombrar / organizar / imprimir | a mano | automatico |
| Saber que ya se hizo | memoria | estado idempotente |

**Sobre el "captcha":** es **Cloudflare Turnstile**, no reCAPTCHA. En navegador
visible suele pasar solo (invisible). Por eso el objetivo real es **desatendido**:
solo pausa para pedir tu intervencion si Turnstile presenta un desafio explicito.
No se puede garantizar 100%: Cloudflare puede endurecer la verificacion ante
automatizacion; el perfil persistente y el modo visible maximizan la tasa de exito.

**Estado de verificacion:** la lectura de la lista, el **descifrado del PDF cifrado
con el NIT** y la idempotencia estan cubiertos por tests (`pytest`, 15/15). La
navegacion usa selectores basados en las capturas reales, pero **no se ejecuto
contra DIAN** al construir (la red del entorno bloquea `*.dian.gov.co`): confirma
los selectores en tu primera corrida con `--inspect`. Si algun boton cambia de
nombre, la herramienta cede el control y tu haces ese clic; la descarga, el
descifrado y la impresion siguen funcionando igual.

## Requisitos

- Windows (tambien corre en Mac/Linux para pruebas).
- Python 3.11+.

## Instalacion (Windows)

```powershell
cd dian-facturas
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
copy .env.example .env
notepad .env          # pon tu DIAN_NIT y la ruta de tu Excel/CSV
```

## Archivo de entrada

Un `.xlsx` o `.csv` con al menos la columna **cufe**. Columnas opcionales:
`nit` (contrasena por fila, si difiere del global), `nombre` (nombre del PDF),
`proveedor` (subcarpeta). Los encabezados se detectan sin importar
mayusculas/acentos. Ver `facturas.ejemplo.csv`.

```csv
cufe,nombre,proveedor
a1b2...ff00,factura_energia_enero,EPM
```

## Uso

```powershell
python run.py                     # procesa todo lo pendiente
python run.py --input mis.xlsx    # otro archivo de entrada
python run.py --only <CUFE>       # un solo documento
python run.py --retry-failed      # reintenta los fallidos
python run.py --no-print          # descarga sin imprimir
python run.py --inspect <CUFE>    # diagnostico: vuelca el DOM real
```

Flujo por documento: se abre el navegador, se autollena el NIT, se espera a que
Cloudflare pase (si desafia, te pide un ENTER en consola), se hace Buscar ->
Aceptar -> Descargar PDF, se quita la contrasena y se guarda el PDF en
`descargas/<proveedor>/<nombre>.pdf`, opcionalmente se imprime y se marca el CUFE
como hecho. Si vuelves a ejecutar, los ya hechos se saltan.

## Afinar los selectores (primera corrida)

```powershell
python run.py --inspect <un-CUFE-real>
```

Genera `descargas/inspect/pagina.html` y `pagina.png`. Con eso se fijan los
selectores exactos del campo NIT y del boton de descarga en `src/dian_client.py`
(constantes `NIT_SELECTORS` y `DOWNLOAD_SELECTORS`).

## Impresion

`AUTO_PRINT=true` en `.env` imprime cada PDF al terminar. Para elegir una impresora
concreta en Windows instala [SumatraPDF](https://www.sumatrapdfreader.org/) y pon
`PRINTER_NAME=` con su nombre exacto; sin SumatraPDF se usa la impresora
predeterminada.

## Seguridad y privacidad

- El NIT vive solo en `.env` (ignorado por git). Nunca en el codigo ni en el repo.
- Los PDFs, el perfil del navegador y la lista real estan en `.gitignore`.
- La herramienta solo accede a documentos que ya recibiste; usa una pausa entre
  descargas (`PACING_SECONDS`) para no saturar el portal.

## Observabilidad

- `descargas/logs/dian.log`: log rotado con ID de ejecucion.
- `descargas/estado.json`: estado por CUFE (done/failed, salida, error).
- `descargas/logs/error_<cufe>.png`: captura cuando un documento falla.

## Tests

```powershell
pip install pytest
pytest -q
```

## Costos

Cero servicios de pago. Todo local (Python + Playwright + Chromium). Sin APIs
externas ni tokens.
