# Descargador asistido de facturas DIAN (por CUFE)

Automatiza la descarga de facturas electronicas desde el portal de la DIAN
(`certificate-vpfe.dian.gov.co`) a partir de una lista de CUFEs en Excel/CSV.

## Que hace (y que NO)

La pagina de la DIAN muestra **un captcha en cada documento**. Por eso **no existe
descarga 100% desatendida honesta**: el captcha lo resuelve una persona. Esta
herramienta automatiza *todo lo demas*, reduciendo el trabajo por factura de ~7
pasos manuales a **1** (resolver el captcha):

| Paso | Antes (manual) | Con la herramienta |
|------|----------------|--------------------|
| Tomar el CUFE | copiar/pegar uno por uno | lee la lista Excel/CSV |
| Entrar al documento | escribir URL / escanear QR | navega solo |
| Poner el NIT | a mano | autollenado (best-effort) |
| Resolver captcha | a mano | **a mano (unico paso humano)** |
| Descargar | clic | clic automatico (o asistido) |
| Quitar contrasena (NIT) al PDF/ZIP | a mano, dos veces | automatico |
| Renombrar / organizar / imprimir | a mano | automatico |
| Saber que ya se hizo | memoria | estado idempotente |

**Estado de verificacion:** la logica de lectura, descifrado (PDF y ZIP con NIT) e
idempotencia esta cubierta por tests (`pytest`, 15/15). La navegacion concreta en
DIAN (selectores del boton de descarga y del campo NIT) **debe confirmarse en tu
primera corrida** con `--inspect`, porque el DOM del portal no se pudo inspeccionar
al construir la herramienta. Mientras tanto funciona en **modo asistido**: si el
script no encuentra un boton, cede el control y tu haces ese clic; el archivo se
captura, descifra, organiza e imprime igual.

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

Flujo por documento: se abre el navegador, se autollena el NIT, **resuelves el
captcha** y presionas ENTER en la consola; la herramienta descarga, quita la
contrasena, guarda el PDF en `descargas/<proveedor>/<nombre>.pdf`, opcionalmente
imprime, y marca el CUFE como hecho. Si vuelves a ejecutar, los ya hechos se saltan.

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
