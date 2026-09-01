// ==UserScript==
// @name         DIAN - Descarga masiva de facturas por CUFE
// @namespace    dian-facturas
// @version      0.1.2
// @description  Recorre una lista de CUFEs en el portal publico DIAN (catalogo-vpfe), llena el NIT, espera la verificacion Cloudflare, y hace Buscar -> Aceptar -> Descargar PDF. Corre dentro de TU navegador real, asi Turnstile lo trata como humano.
// @match        https://catalogo-vpfe.dian.gov.co/*
// @run-at       document-idle
// @grant        none
// ==/UserScript==

(function () {
  'use strict';

  // ---------------- Estado persistente ----------------
  const LS = 'dian_bulk_state';
  const defaults = { nit: '900425099', cufes: [], index: 0, running: false,
                     delayMs: 3500, done: [], errors: [] };

  function load() {
    try { return Object.assign({}, defaults, JSON.parse(localStorage.getItem(LS) || '{}')); }
    catch (e) { return Object.assign({}, defaults); }
  }
  function save(s) { localStorage.setItem(LS, JSON.stringify(s)); }
  let state = load();

  // Estado por-documento que sobrevive recargas dentro de la misma pestana.
  function sess() { try { return JSON.parse(sessionStorage.getItem('dian_doc') || '{}'); } catch (e) { return {}; } }
  function setSess(o) { sessionStorage.setItem('dian_doc', JSON.stringify(o)); }

  const BASE = 'https://catalogo-vpfe.dian.gov.co/User/SearchDocument?DocumentKey=';
  const short = (c) => (c || '').slice(-10);

  // ---------------- Utilidades DOM ----------------
  // Escribe en un input de forma que Angular/React detecten el cambio.
  function setNativeValue(el, value) {
    const proto = Object.getPrototypeOf(el);
    const desc = Object.getOwnPropertyDescriptor(proto, 'value');
    if (desc && desc.set) desc.set.call(el, value); else el.value = value;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }
  const inputs = () => [...document.querySelectorAll('input')];
  function findCufeInput() {
    return inputs().find(i => /cufe|uuid/i.test(i.placeholder || '')) ||
           inputs().find(i => (i.type === 'text' || !i.type)) || null;
  }
  function findNitInput() {
    return inputs().find(i => /nit/i.test(i.placeholder || '')) ||
           inputs().filter(i => i.type === 'text' || !i.type)[1] || null;
  }
  function byText(sel, re) {
    return [...document.querySelectorAll(sel)].find(e => re.test((e.textContent || '').trim()));
  }
  const findBuscar   = () => [...document.querySelectorAll('button, input[type=submit]')]
                              .find(b => /^buscar$/i.test((b.textContent || b.value || '').trim()));
  const findAceptar  = () => byText('button', /^aceptar$/i);
  // Busca el elemento visible mas especifico cuyo texto sea "Descargar PDF".
  function findDescargar() {
    const cands = [...document.querySelectorAll('a, button, span, div, p, li, i')]
      .filter(e => e.offsetParent !== null && /descargar\s*pdf/i.test(e.textContent || ''));
    if (!cands.length) return null;
    cands.sort((a, b) => (a.textContent || '').length - (b.textContent || '').length);
    return cands[0];
  }
  // Clic robusto: dispara sobre el elemento y su ancestro <a>/<button>.
  function clickReal(el) {
    const target = el.closest('a, button') || el;
    try { target.click(); } catch (e) {}
    ['mousedown', 'mouseup', 'click'].forEach(t =>
      target.dispatchEvent(new MouseEvent(t, { bubbles: true, cancelable: true, view: window })));
  }
  function turnstileToken() {
    const e = document.querySelector('[name="cf-turnstile-response"]');
    return e && e.value && e.value.length > 20 ? e.value : '';
  }
  const isDocView = () => !!findDescargar() || !!findAceptar();
  const isSearch  = () => !!findBuscar() && !!findNitInput();

  // ---------------- Maquina de estados ----------------
  let busy = false;
  function tick() {
    renderStatus();
    if (!state.running || busy) return;
    busy = true;
    try { step(); } catch (e) { console.error('[DIAN]', e); }
    busy = false;
  }

  function currentCufe() { return state.cufes[state.index]; }

  function step() {
    const cufe = currentCufe();
    if (!cufe) { stop('Lista terminada'); return; }

    let sd = sess();
    if (sd.cufe !== cufe) { sd = { cufe: cufe, startTs: Date.now(), lastBuscar: 0, downloaded: false }; setSess(sd); }

    // Timeout de seguridad por documento.
    if (Date.now() - sd.startTs > 120000) {
      pushError(cufe, 'timeout (120s)'); advance(); return;
    }

    if (isDocView()) {
      const aceptar = findAceptar();
      if (aceptar) { console.log('[DIAN] clic Aceptar'); clickReal(aceptar); return; }
      if (!sd.downloaded) {
        const d = findDescargar();
        if (d) {
          console.log('[DIAN] clic Descargar PDF ->', d.tagName, JSON.stringify((d.textContent || '').trim()));
          clickReal(d);
          sd.downloaded = true; setSess(sd);
          markDone(cufe);
          setStatusMsg('Descargado ' + short(cufe) + '. Siguiente en ' + state.delayMs + ' ms...');
          setTimeout(advance, state.delayMs);
        } else {
          setStatusMsg('No encuentro "Descargar PDF" en ' + short(cufe) + '...');
        }
      }
      return;
    }

    if (isSearch()) {
      // Rellenar SOLO si el campo esta vacio, para no duplicar el valor:
      // el formulario Angular de DIAN antepone en cada 'input', y el CUFE ya
      // viene prellenado por la URL (DocumentKey).
      const ci = findCufeInput();
      if (ci && !(ci.value || '').trim()) setNativeValue(ci, cufe);
      const ni = findNitInput();
      if (ni && !(ni.value || '').trim()) setNativeValue(ni, state.nit);

      const tok = turnstileToken();
      if (!tok) { setStatusMsg('Esperando verificacion Cloudflare... (' + short(cufe) + ')'); return; }

      // Token listo: clic en Buscar (con backoff para no repetir).
      if (Date.now() - (sd.lastBuscar || 0) > 8000) {
        const b = findBuscar();
        if (b) { b.click(); sd.lastBuscar = Date.now(); setSess(sd); setStatusMsg('Buscando ' + short(cufe) + '...'); }
      }
      return;
    }

    setStatusMsg('Cargando pagina... (' + short(cufe) + ')');
  }

  function advance() {
    state.index++; save(state);
    if (state.index >= state.cufes.length) { stop('Completado'); return; }
    location.href = BASE + state.cufes[state.index];   // recarga a la siguiente factura
  }

  function markDone(cufe) { if (!state.done.includes(cufe)) { state.done.push(cufe); save(state); } }
  function pushError(cufe, msg) { state.errors.push({ cufe: cufe, msg: msg, ts: new Date().toISOString() }); save(state); }

  function start() {
    if (!state.cufes.length) { alert('Pega primero la lista de CUFEs.'); return; }
    // Reanuda desde el primer CUFE no hecho.
    while (state.index < state.cufes.length && state.done.includes(state.cufes[state.index])) state.index++;
    if (state.index >= state.cufes.length) { alert('Todos los CUFEs ya estan marcados como hechos. Usa Reiniciar para volver a empezar.'); return; }
    state.running = true; save(state);
    location.href = BASE + state.cufes[state.index];   // arranca limpio con enlace directo
  }
  function stop(msg) { state.running = false; save(state); setStatusMsg(msg || 'Detenido'); }

  // ---------------- Panel de control ----------------
  let statusEl, msgEl;
  function buildPanel() {
    if (document.getElementById('dian-panel')) return;
    const p = document.createElement('div');
    p.id = 'dian-panel';
    p.style.cssText = 'position:fixed;top:10px;right:10px;z-index:2147483647;width:300px;' +
      'background:#0d2b45;color:#fff;font:12px/1.4 system-ui,Arial;padding:12px;border-radius:10px;' +
      'box-shadow:0 6px 24px rgba(0,0,0,.35);';
    p.innerHTML =
      '<div id="dp-head" style="font-weight:700;font-size:13px;margin-bottom:8px;cursor:move;display:flex;justify-content:space-between;align-items:center">' +
        '<span>DIAN · Descarga masiva</span>' +
        '<span id="dp-collapse" style="cursor:pointer;padding:0 6px;user-select:none">▾</span>' +
      '</div>' +
      '<div id="dp-body">' +
      'NIT (contrasena):<br><input id="dp-nit" style="width:100%;margin:2px 0 8px;box-sizing:border-box">' +
      'CUFEs (uno por linea):<br><textarea id="dp-cufes" rows="4" style="width:100%;margin:2px 0 8px;box-sizing:border-box"></textarea>' +
      'Pausa entre facturas (ms):<br><input id="dp-delay" style="width:100%;margin:2px 0 8px;box-sizing:border-box">' +
      '<div style="display:flex;gap:6px;margin-bottom:8px">' +
        '<button id="dp-start" style="flex:1;padding:6px;background:#2ecc71;border:0;border-radius:6px;color:#063;cursor:pointer;font-weight:700">Iniciar</button>' +
        '<button id="dp-pause" style="flex:1;padding:6px;background:#f1c40f;border:0;border-radius:6px;color:#630;cursor:pointer;font-weight:700">Pausar</button>' +
        '<button id="dp-reset" style="flex:1;padding:6px;background:#e74c3c;border:0;border-radius:6px;color:#fff;cursor:pointer">Reiniciar</button>' +
      '</div>' +
      '<div id="dp-status" style="font-weight:700"></div>' +
      '<div id="dp-msg" style="opacity:.85;margin-top:4px;min-height:16px"></div>' +
      '</div>';
    document.body.appendChild(p);

    // Posicion guardada + arrastre por el encabezado.
    try {
      const pos = JSON.parse(localStorage.getItem('dian_panel_pos') || 'null');
      if (pos) { p.style.left = pos.left; p.style.top = pos.top; p.style.right = 'auto'; }
    } catch (e) {}
    (function makeDraggable() {
      const head = p.querySelector('#dp-head');
      let sx, sy, ox, oy, drag = false;
      head.addEventListener('mousedown', (e) => {
        if (e.target.id === 'dp-collapse') return;
        drag = true; sx = e.clientX; sy = e.clientY;
        const r = p.getBoundingClientRect(); ox = r.left; oy = r.top;
        e.preventDefault();
      });
      document.addEventListener('mousemove', (e) => {
        if (!drag) return;
        p.style.left = (ox + e.clientX - sx) + 'px';
        p.style.top = (oy + e.clientY - sy) + 'px';
        p.style.right = 'auto';
      });
      document.addEventListener('mouseup', () => {
        if (!drag) return; drag = false;
        localStorage.setItem('dian_panel_pos', JSON.stringify({ left: p.style.left, top: p.style.top }));
      });
    })();
    // Plegar / desplegar.
    p.querySelector('#dp-collapse').addEventListener('click', () => {
      const body = p.querySelector('#dp-body'), btn = p.querySelector('#dp-collapse');
      const hidden = body.style.display === 'none';
      body.style.display = hidden ? '' : 'none';
      btn.textContent = hidden ? '▾' : '▸';
    });

    const $ = (id) => p.querySelector(id);
    $('#dp-nit').value = state.nit;
    $('#dp-cufes').value = state.cufes.join('\n');
    $('#dp-delay').value = state.delayMs;
    statusEl = $('#dp-status'); msgEl = $('#dp-msg');

    $('#dp-nit').addEventListener('change', e => { state.nit = e.target.value.trim(); save(state); });
    $('#dp-delay').addEventListener('change', e => { state.delayMs = parseInt(e.target.value, 10) || 3500; save(state); });
    $('#dp-cufes').addEventListener('change', e => {
      state.cufes = e.target.value.split(/\s+/).map(s => s.trim()).filter(Boolean);
      save(state);
    });
    $('#dp-start').addEventListener('click', () => {
      // toma lo que este en el textarea aunque no haya disparado 'change'
      const ta = $('#dp-cufes').value; state.cufes = ta.split(/\s+/).map(s => s.trim()).filter(Boolean);
      state.nit = $('#dp-nit').value.trim(); state.delayMs = parseInt($('#dp-delay').value, 10) || 3500;
      save(state); start();
    });
    $('#dp-pause').addEventListener('click', () => stop('Pausado por el usuario'));
    $('#dp-reset').addEventListener('click', () => {
      if (!confirm('Reiniciar progreso? Se borran los marcados como hechos.')) return;
      state.index = 0; state.done = []; state.errors = []; state.running = false; save(state);
      setStatusMsg('Progreso reiniciado');
    });
  }

  function renderStatus() {
    if (!statusEl) return;
    const total = state.cufes.length, done = state.done.length, err = state.errors.length;
    statusEl.textContent = (state.running ? '▶ ' : '⏸ ') +
      'Hechos ' + done + '/' + total + (err ? ('  ·  errores ' + err) : '');
  }
  function setStatusMsg(m) { if (msgEl) msgEl.textContent = m; }

  // ---------------- Arranque ----------------
  function boot() {
    buildPanel();
    setInterval(tick, 1500);
  }
  if (document.body) boot();
  else window.addEventListener('DOMContentLoaded', boot);
})();
