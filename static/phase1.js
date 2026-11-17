/* RiceVision HMI - PHASE 1 data layer
 * Loaded AFTER the original UI script. It replaces the localStorage persistence with the SQLite DB
 * (through server.py) and adds the PI / LAPTOP camera switch. The UI markup is not changed
 * except for one extra button (SRC) in the CAMERA VERIFY panel and one hidden <img> for the Pi stream.
 */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);

  /* ------------------------------------------------------------------ helpers */
  const style = document.createElement('style');
  style.textContent = '#p1-toast{position:fixed;left:50%;bottom:10px;transform:translateX(-50%);z-index:2147483000;max-width:90vw;' +
    'padding:6px 12px;border-radius:5px;font:800 9px var(--font-mono,monospace);letter-spacing:.4px;display:none;' +
    'background:#0d1b12;color:#7EE787;border:1px solid #2ea043;box-shadow:0 4px 18px rgba(0,0,0,.6)}' +
    '#p1-toast.bad{background:#2a0d0d;color:#ff7b72;border-color:#da3633}' +
    '#recipe-camera-pi{width:100%;height:100%;object-fit:cover;display:none}';
  document.head.appendChild(style);
  const toastEl = Object.assign(document.createElement('div'), { id: 'p1-toast' });
  document.body.appendChild(toastEl);
  let toastTimer;
  function toast(msg, bad) {
    toastEl.textContent = msg; toastEl.className = bad ? 'bad' : ''; toastEl.style.display = 'block';
    clearTimeout(toastTimer); toastTimer = setTimeout(() => toastEl.style.display = 'none', bad ? 6000 : 3000);
  }
  async function call(path, opt) {
    const r = await fetch(path, opt);
    const t = await r.text(); let j; try { j = JSON.parse(t); } catch (e) { j = { error: t.slice(0, 120) }; }
    if (!r.ok) throw new Error(j.error || ('HTTP ' + r.status));
    return j;
  }
  const get = p => call(p);
  const post = (p, obj) => call(p, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(obj || {}) });
  const ev = (event, detail) => post('/api/event', { event, detail, operator: HMI_STATE.recipe.operator || '', recipe: HMI_STATE.recipe.name || '' }).catch(() => {});
  const setText = (id, t, color) => { const e = $(id); if (e) { e.textContent = t; if (color !== undefined) e.style.color = color; } };

  /* ------------------------------------------------------ stable recipe object
   * The original code replaces HMI_STATE.recipe with a new object in several places, while the
   * calibration form keeps a reference to the FIRST object. Make the property write in-place so
   * both always see the same object. */
  const stable = HMI_STATE.recipe;
  Object.defineProperty(HMI_STATE, 'recipe', {
    configurable: true, enumerable: true, get() { return stable; },
    set(v) { Object.keys(stable).forEach(k => delete stable[k]); Object.assign(stable, v || {}); }
  });

  let opNames = [];
  function setRecipe(ui, operator) {
    const isShivaji = /(?:sh?ivaji|veera)/i.test((ui && ui.name) || '');
    HMI_STATE.recipe = Object.assign({}, ui, {
      operator: operator || '',
      imageDataUrl: (ui && ui.imageUrl) || '',
      frontImageUrl: (ui && ui.frontImageUrl) || (isShivaji ? '/images/veerashivaji_front.jpg' : ''),
      backImageUrl: (ui && ui.backImageUrl) || (isShivaji ? '/images/veerashivaji_back.jpg' : ''),
      operatorImageDataUrl: ''
    });
    setText('active-recipe-name', stable.name);
    if (typeof refreshUI === 'function') refreshUI();
    if (typeof window.syncRecipeCalibrationUI === 'function') window.syncRecipeCalibrationUI();
  }
  async function syncActive() {
    const s = await get('/api/state');
    camSource = s.camera_source || camSource; paintSource();
    if (s.recipe) setRecipe(s.recipe, s.operator);
    return s;
  }
  async function refreshLibrary() {
    const [recs, ops] = await Promise.all([get('/api/recipes'), get('/api/operators')]);
    recipeLibrary = recs; opNames = ops.map(o => o.name);
  }

  /* ------------------------------------------- replace the localStorage library */
  window.loadRecipeLibrary = function () { /* DB-backed: refreshed by refreshLibrary() */ };
  window.saveRecipeLibrary = function () { /* DB-backed */ };
  window.recipeOperators = function () { return opNames.slice(); };
  window.applyRecipeToHmi = function (r) { setRecipe(r, r.operator); };

  window.populateRecipeImages = function () {
    const box = $('recipe-image-scroll'); if (!box) return;
    const imgs = recipeLibrary.filter(r => r.imageUrl);
    setText('recipe-image-count', imgs.length ? '1 / ' + imgs.length : '0 / 0');
    box.innerHTML = ''; recipeSelectedImage = null;
    imgs.forEach(r => {
      const b = document.createElement('div'); b.className = 'recipe-image-thumb'; b.dataset.recipeIndex = String(recipeLibrary.indexOf(r));
      if (r.imageType === 'application/pdf') { const p = document.createElement('div'); p.className = 'pdf'; p.textContent = 'PDF'; b.appendChild(p); }
      else { const i = document.createElement('img'); i.loading = 'lazy'; i.src = r.imageUrl; i.alt = r.name; b.appendChild(i); }
      const n = document.createElement('div'); n.className = 'name'; n.textContent = r.name; b.appendChild(n);
      b.addEventListener('pointerup', () => selectRecipeImage(r, b, imgs.length));
      box.appendChild(b);
    });
    const cur = imgs.findIndex(r => r.name === stable.name), k = cur >= 0 ? cur : 0;
    if (imgs[k]) { const el = box.children[k]; selectRecipeImage(imgs[k], el, imgs.length); el.scrollIntoView({ block: 'nearest', inline: 'center' }); }
    else setText('recipe-image-config', 'No stored recipe images available.');
  };

  /* ------------------------------------------------------- audit: calibration login */
  const origPw = window.handleProtectedPasswordConfirm;
  window.handleProtectedPasswordConfirm = function (target, expected, onSuccess, reopen) {
    const res = origPw(target, expected, function () {
      if (target === 'recipecal_password') ev('CALIBRATION_LOGIN', 'recipe calibration unlocked');
      onSuccess && onSuccess();
    }, reopen);
    if (res === false && target === 'recipecal_password') ev('CALIBRATION_LOGIN_FAILED', 'wrong password');
    return res;
  };

  /* ===================================================== CALIBRATION: SAVE & EXIT */
  let saving = false;
  window.saveRecipeCalibrationAndGoHome = async function () {
    if (saving) return; const st = stable;
    const msg = (t, bad) => setText('recipe-cal-status', t, bad ? 'var(--red-bright)' : '');
    const name = (st.name || '').trim(), operator = (st.operator || '').trim();
    if (!name) return msg('ENTER RECIPE NAME', true);
    if (!operator) return msg('ENTER OPERATOR NAME', true);
    saving = true; msg('SAVING TO DATABASE...');
    const keys = ['repeatLength', 'width', 'material', 'markWindow', 'markOffset', 'sTensionTarget', 'frontSensor', 'frontMark', 'frontBackground', 'backSensor', 'backMark', 'backBackground'];
    const recipe = { name }; keys.forEach(k => recipe[k] = st[k]);
    const newImg = typeof st.imageDataUrl === 'string' && st.imageDataUrl.startsWith('data:');
    try {
      const prevActive = (await get('/api/state')).recipe;
      const hasFrontData = typeof st.frontImageDataUrl === 'string' && st.frontImageDataUrl.startsWith('data:');
      const hasBackData = typeof st.backImageDataUrl === 'string' && st.backImageDataUrl.startsWith('data:');
      const res = await post('/api/recipes', {
        recipe, operator, operatorPhoto: st.operatorImageDataUrl || null,
        image: newImg ? { name: st.imageName, dataUrl: st.imageDataUrl } : null,
        frontImage: hasFrontData ? { name: st.frontImageName || 'front.jpg', dataUrl: st.frontImageDataUrl } : null,
        backImage: hasBackData ? { name: st.backImageName || 'back.jpg', dataUrl: st.backImageDataUrl } : null
      });
      const s = await syncActive();                       // HMI keeps showing the ACTIVE (loaded) recipe
      if (!s.recipe) setRecipe(res.recipe, operator);
      recipeEditSnapshot = recipeClone(stable);
      toast(prevActive && prevActive.recipeId !== res.recipe.recipeId ? 'RECIPE "' + name + '" SAVED TO DB - LOAD IT FROM THE RECIPE SCREEN' : 'RECIPE SAVED TO DB');
      msg('SAVED'); returnToHomeScreen();
    } catch (e) { msg('DB SAVE FAILED: ' + e.message, true); toast('SAVE FAILED: ' + e.message, true); }
    finally { saving = false; }
  };

  /* ---- PDF support for the recipe image (original handler only keeps image data URLs) ---- */
  function bindPdf() {
    const f = $('recipe-image-file-input'); if (!f) return;
    f.addEventListener('change', () => {
      const file = f.files && f.files[0];
      if (file && file.type === 'application/pdf') { const rd = new FileReader(); rd.onload = () => { stable.imageDataUrl = rd.result; }; rd.readAsDataURL(file); }
    });
  }

  /* ============================================================ CAMERA: PI / LAPTOP */
  let camSource = localStorage.getItem('camSource') || 'laptop';
  let piImg = null, srcBtn = null;
  const piOn = () => camSource === 'pi';
  function paintSource() { if (srcBtn) srcBtn.textContent = 'SRC: ' + (piOn() ? 'PI CAM' : 'LAPTOP'); }

  function stopCamera() {
    if (recipeCameraStream) { recipeCameraStream.getTracks().forEach(t => t.stop()); recipeCameraStream = null; }
    if (piImg) { piImg.removeAttribute('src'); piImg.style.display = 'none'; }
    const v = $('recipe-camera-video'); if (v) { v.srcObject = null; v.style.display = 'none'; }
    post('/api/camera/stop').catch(() => {});
  }
  function cameraOffUI() {
    stopCamera(); setText('recipe-camera-status', 'CAMERA OFF');
    const ph = $('recipe-camera-placeholder'); if (ph) ph.style.display = 'flex';
    const cb = $('recipe-camera-compare'); if (cb) cb.disabled = true;
  }
  async function setSource(s) {
    camSource = s; localStorage.setItem('camSource', s); paintSource(); cameraOffUI();
    setText('recipe-compare-result', 'Camera source: ' + (piOn() ? 'RASPBERRY PI CAMERA' : 'LAPTOP / BROWSER CAMERA'));
    try { await post('/api/camera/source', { source: s, operator: stable.operator }); } catch (e) { toast('Could not save camera source: ' + e.message, true); }
  }

  async function openCamera() {
    stopCamera(); recipeCameraCandidate = null;
    const ph = $('recipe-camera-placeholder'), cb = $('recipe-camera-compare');
    try {
      if (piOn()) {
        piImg.onerror = async () => {
          let why = 'unavailable'; try { why = (await get('/api/camera/info')).pi.error || why; } catch (e) {}
          setText('recipe-camera-status', 'PI CAMERA ERROR'); setText('recipe-compare-result', 'Pi camera: ' + why);
          piImg.style.display = 'none'; if (ph) ph.style.display = 'flex'; if (cb) cb.disabled = true;
        };
        piImg.onload = () => { if (ph) ph.style.display = 'none'; };
        piImg.style.display = 'block'; if (ph) ph.style.display = 'none'; piImg.src = '/api/camera/stream?t=' + Date.now();
        if (cb) cb.disabled = false; setText('recipe-camera-status', 'PI CAMERA LIVE'); updateRecipeLoadStatus('PI CAMERA LIVE');
      } else {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia)
          throw new Error(window.isSecureContext ? 'no camera API' : 'laptop camera needs https:// or http://localhost');
        recipeCameraStream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
        const v = $('recipe-camera-video'); v.srcObject = recipeCameraStream; v.style.display = 'block'; if (ph) ph.style.display = 'none';
        if (cb) cb.disabled = false; setText('recipe-camera-status', 'LAPTOP CAMERA LIVE'); updateRecipeLoadStatus('CAMERA LIVE');
      }
    } catch (e) { setText('recipe-camera-status', 'CAMERA ERROR'); setText('recipe-compare-result', 'Camera not available: ' + e.message); }
  }

  function videoJpeg(v, maxW, q) {
    return new Promise((res, rej) => {
      const w = v.videoWidth, h = v.videoHeight; if (!w) return rej(new Error('no video frame'));
      const s = Math.min(1, maxW / w), c = document.createElement('canvas'); c.width = Math.round(w * s); c.height = Math.round(h * s);
      c.getContext('2d').drawImage(v, 0, 0, c.width, c.height); c.toBlob(b => b ? res(b) : rej(new Error('capture failed')), 'image/jpeg', q);
    });
  }

  async function compareCamera() {
    const r = selectedRecipe(), op = $('recipe-select-operator')?.value || '';
    const out = t => setText('recipe-compare-result', t);
    if (!r) return out('Select a recipe first.');
    recipeCameraCandidate = null; out('Reading bag...');
    const q = '?recipe_id=' + r.recipeId + '&operator=' + encodeURIComponent(op) + '&source=' + camSource;
    try {
      let res;
      if (piOn()) res = await post('/api/camera/compare' + q);   // server compares its own full-resolution frame
      else {
        const v = $('recipe-camera-video'); if (!v || v.readyState < 2) return out('Open the camera first.');
        res = await call('/api/camera/compare' + q, { method: 'POST', headers: { 'Content-Type': 'image/jpeg' }, body: await videoJpeg(v, 1280, .88) });
      }
      const cfg = $('recipe-camera-config'), pct = Math.round((res.confidence || 0) * 100);
      if (res.result === 'MATCH' || res.result === 'UNVERIFIED') {
        recipeCameraCandidate = Object.assign({}, r, { operator: op, verifyId: res.verify_id, cameraCapture: res.capture_url });
        out(res.result === 'MATCH' ? 'COMPARISON SUCCESS - ' + r.name + ' (' + pct + '%)' : 'VISION UNAVAILABLE - capture saved, UNVERIFIED');
        cfg.innerHTML = recipeConfigMarkup(recipeCameraCandidate) + '<div style="margin-top:6px;color:var(--green-bright);font-weight:900">' + (res.result === 'MATCH' ? 'CAMERA CAPTURE VERIFIED' : 'UNVERIFIED - OPERATOR CONFIRMS') + '</div>';
        updateRecipeLoadStatus(res.result === 'MATCH' ? 'CAMERA VERIFIED' : 'CAMERA UNVERIFIED', res.result === 'MATCH');
      } else {
        const bad = res.result === 'MISMATCH' ? 'MISMATCH - camera sees "' + res.best + '", selected "' + r.name + '"' : 'NOT RECOGNISED - re-aim camera or add a reference image';
        out(bad); cfg.innerHTML = '<div style="color:var(--red-bright);font-weight:900">' + bad + '</div>'; updateRecipeLoadStatus(res.result);
      }
    } catch (e) { out('Compare failed: ' + e.message); }
  }

  async function grabStill(w, h) {          // operator photo, any source
    let src, stream;
    if (piOn()) { const b = await (await fetch('/api/camera/snapshot')).blob(); src = await createImageBitmap(b); }
    else {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) throw new Error('no camera API');
      stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      const v = document.createElement('video'); v.muted = true; v.playsInline = true; v.srcObject = stream; await v.play();
      await new Promise(r => setTimeout(r, 600)); src = v;
    }
    const sw = src.videoWidth || src.width, sh = src.videoHeight || src.height, k = Math.max(w / sw, h / sh);
    const c = document.createElement('canvas'); c.width = w; c.height = h;
    c.getContext('2d').drawImage(src, (w - sw * k) / 2, (h - sh * k) / 2, sw * k, sh * k);
    if (stream) stream.getTracks().forEach(t => t.stop());
    return c.toDataURL('image/jpeg', .8);
  }
  function openOperatorKeypad() {           // same alpha keypad the original uses
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 -_.';
    window.recipeAlphaKind = 'operator'; window.recipeAlphaBuffer = stable.operator || '';
    setText('recipe-alpha-title', 'OPERATOR NAME'); setText('recipe-alpha-display', window.recipeAlphaBuffer || ' ');
    const g = $('recipe-alpha-grid'); g.innerHTML = '';
    [...chars].forEach(ch => { const b = document.createElement('button'); b.textContent = ch === ' ' ? 'SPACE' : ch;
      b.onclick = () => { if (window.recipeAlphaBuffer.length < 24) window.recipeAlphaBuffer += ch; $('recipe-alpha-display').textContent = window.recipeAlphaBuffer; }; g.appendChild(b); });
    const back = document.createElement('button'); back.textContent = '\u2190';
    back.onclick = () => { window.recipeAlphaBuffer = window.recipeAlphaBuffer.slice(0, -1); $('recipe-alpha-display').textContent = window.recipeAlphaBuffer || ' '; }; g.appendChild(back);
    $('recipe-alpha-modal').classList.add('open');
  }

  /* ============================================================ RECIPE LOAD SCREEN */
  const origShow = window.showRecipeLoadScreen, origClose = window.closeRecipeLoad;
  let loadSource = 'NAME', loading = false;
  window.closeRecipeLoad = function (discard) { origClose(discard); stopCamera(); };
  window.openRecipeCamera = openCamera; window.compareRecipeCamera = compareCamera;

  async function openLoadScreen() {
    try { await refreshLibrary(); } catch (e) { return toast('DATABASE OFFLINE: ' + e.message, true); }
    loadSource = 'NAME'; origShow(); cameraOffUI(); paintSource();
    setText('recipe-compare-result', 'Camera source: ' + (piOn() ? 'RASPBERRY PI CAMERA' : 'LAPTOP / BROWSER CAMERA'));
  }

  async function confirmLoad() {
    if (loading) return;
    const r = recipeLoadDraft || selectedRecipe(), op = $('recipe-select-operator')?.value || '';
    if (!r) return updateRecipeLoadStatus('SELECT A RECIPE');
    if (!op) return updateRecipeLoadStatus('SELECT AN OPERATOR');
    const rid = r.recipeId != null ? r.recipeId : (recipeLibrary.find(x => x.name === r.name) || {}).recipeId;
    loading = true; updateRecipeLoadStatus('SAVING TO DATABASE...');
    try {
      await flushProduction();                                   // close out counts of the previous recipe/operator
      const res = await post('/api/load', { recipe_id: rid, operator: op, source: loadSource,
        verify_id: loadSource === 'CAMERA' && recipeCameraCandidate ? recipeCameraCandidate.verifyId : null });
      setRecipe(res.recipe, res.operator);
      window.closeRecipeLoad(false); toast('RECIPE LOADED - SAVED TO DB');
    } catch (e) { updateRecipeLoadStatus('DB ERROR: ' + e.message); toast('LOAD FAILED: ' + e.message, true); }
    finally { loading = false; }
  }

  /* ================================================== REPORT / PRODUCTION LOG -> DB */
  let reportRows = [];
  window.reportGetRecords = function () { return reportRows; };
  async function refreshReport() { try { reportRows = await get('/api/report'); if ($('report-screen')?.classList.contains('open')) updateReportScreen(); } catch (e) {} }

  let lastCounters = { '0-7': 0, '8-15': 0, '16-25': 0, total: 0 };
  async function flushProduction() {
    const c = HMI_STATE.report.counters; if (!c) return;
    const d = k => Math.max(0, (Number(c[k]) || 0) - lastCounters[k]);
    const body = { c0_7: d('0-7'), c8_15: d('8-15'), c16_25: d('16-25') };
    body.total = d('total') || (body.c0_7 + body.c8_15 + body.c16_25);
    if (!body.total) return;
    await post('/api/production', body);                       // stored against the ACTIVE recipe + operator
    lastCounters = { '0-7': Number(c['0-7']) || 0, '8-15': Number(c['8-15']) || 0, '16-25': Number(c['16-25']) || 0, total: Number(c.total) || 0 };
  }

  /* ================================================================== wire up */
  function init() {
    const view = document.querySelector('.recipe-camera-view');
    if (view) { piImg = document.createElement('img'); piImg.id = 'recipe-camera-pi'; piImg.alt = 'Pi camera'; view.insertBefore(piImg, view.firstChild); }
    const acts = document.querySelector('.recipe-camera-actions');
    if (acts) {
      srcBtn = document.createElement('button'); srcBtn.className = 'btn btn-dark'; srcBtn.id = 'recipe-camera-source'; srcBtn.type = 'button';
      acts.insertBefore(srcBtn, acts.children[1] || null); paintSource();
      srcBtn.addEventListener('pointerup', () => setSource(piOn() ? 'laptop' : 'pi'));
    }
    // capturing listeners run before (and replace) the original handlers on the same button
    const take = (id, fn) => { const el = $(id); if (el) el.addEventListener('pointerup', e => { e.stopImmediatePropagation(); fn(e); }, true); };
    take('btn-load-slaves', openLoadScreen);
    take('recipe-camera-open', openCamera);
    take('recipe-camera-compare', compareCamera);
    take('recipe-load-save', confirmLoad);
    take('recipe-operator-btn', async () => {
      const b = $('recipe-operator-btn'); b.disabled = true; setText('recipe-cal-status', 'CAPTURING OPERATOR PHOTO...');
      try { stable.operatorImageDataUrl = await grabStill(320, 240); setText('recipe-cal-status', 'OPERATOR PHOTO CAPTURED - ENTER NAME'); }
      catch (e) { setText('recipe-cal-status', 'NO CAMERA (' + e.message + ') - ENTER NAME'); }
      b.disabled = false; openOperatorKeypad();
    });
    // remember how the operator confirmed the load
    $('recipe-confirm-load')?.addEventListener('pointerup', () => { loadSource = 'NAME'; });
    $('recipe-image-confirm')?.addEventListener('pointerup', () => { if (recipeSelectedImage) loadSource = 'IMAGE'; });
    $('recipe-camera-confirm')?.addEventListener('pointerup', () => { if (recipeCameraCandidate) loadSource = 'CAMERA'; });
    ['recipe-select-name', 'recipe-select-operator'].forEach(id => $(id)?.addEventListener('change', () => { loadSource = 'NAME'; }));
    $('btn-open-report')?.addEventListener('pointerup', refreshReport);
    bindPdf();

    syncActive().then(() => refreshReport()).catch(e => toast('DATABASE OFFLINE: ' + e.message, true));
    setInterval(() => { flushProduction().catch(() => {}); if ($('report-screen')?.classList.contains('open')) refreshReport(); }, 5000);
  }
  window.PHASE1 = { setCameraSource: setSource, getCameraSource: () => camSource, flushProduction, refreshReport, syncActive };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
