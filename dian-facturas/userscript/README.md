# Descarga masiva DIAN con userscript (dentro de TU navegador)

Cloudflare Turnstile bloquea la automatizacion externa (Playwright/Selenium). La
via que si funciona es un **userscript** que corre dentro de tu Brave/Chrome real:
Turnstile lo trata como humano y pasa. El userscript hace la navegacion; luego un
script Python descifra los PDF en lote.

## Parte 1 — Instalar y configurar el userscript

1. **Instala Tampermonkey** en Brave:
   https://chromewebstore.google.com/detail/tampermonkey/dhdgffkkebhmkfjojejmpbldmpobfkfo
   (Acepta habilitarlo. Si Brave pide "permitir modo desarrollador de extensiones", actívalo.)

2. **Configura Brave para no preguntar dónde guardar** (clave para que descargue solo):
   Menu → Configuración → Descargas → **desactiva** "Preguntar dónde guardar cada
   archivo antes de descargarlo". Anota la carpeta de descargas (normalmente `Descargas`).

3. **Instala el script:** abre el icono de Tampermonkey → *Crear un nuevo script* →
   borra todo, pega el contenido de `dian-descarga.user.js`, y guarda (Ctrl+S).
   (O abre el archivo `.user.js` en Brave y Tampermonkey ofrece instalarlo.)

## Parte 2 — Descargar

1. Abre cualquier página del portal, por ejemplo:
   `https://catalogo-vpfe.dian.gov.co/User/SearchDocument`
   Aparecerá un **panel azul arriba a la derecha**.
2. En el panel:
   - **NIT**: tu NIT (ya viene `900425099`).
   - **CUFEs**: pega la columna de CUFEs (uno por línea) desde tu Excel.
   - **Pausa**: milisegundos entre facturas (3500 está bien; súbelo si Cloudflare se pone difícil).
3. Clic en **Iniciar**. El script recorre la lista: llena el NIT, espera la
   verificación Cloudflare, hace Buscar → Aceptar → Descargar PDF, y pasa a la siguiente.
   - **Pausar** detiene; **Iniciar** reanuda donde quedó (no repite lo hecho).
   - **Reiniciar** borra el progreso.
   - Si una verificación no pasa sola, resuélvela tú en la ventana; el script continúa.

Los PDF caen en tu carpeta de Descargas, con nombre `<CUFE>.pdf`, **protegidos con tu NIT**.

## Parte 3 — Descifrar e imprimir (Python)

En PowerShell, dentro de `dian-facturas`:
```powershell
python procesar_descargas.py --dir "C:\Users\Admin\Downloads"
```
Descifra todos los `<CUFE>.pdf` con tu NIT y los deja sin contraseña en
`descargas\pdf\`. Para imprimirlos al descifrar, agrega `--print`.

## Notas
- Empieza con **pocos CUFEs** (5-10) para validar el flujo antes del lote completo.
- El panel muestra "Hechos X/Total" y errores. El progreso se guarda en el navegador.
- Si el sitio cambia y algún botón no lo encuentra, avísame con lo que ves y ajusto
  los selectores en el `.user.js`.
