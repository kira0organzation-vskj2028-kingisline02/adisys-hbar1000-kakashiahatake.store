#!/usr/bin/env python3
"""Refactor static/index.html to thin UI layer:
- Zero localStorage
- Zero getUserMedia
- Zero hardcoded passcodes (1111, 2222, 3333, 4444)
- Zero client-side range limits
- Zero browser-side simulation jitter
- Single state update path via pollState() & applyState(state)
- All user actions dispatched via sendAction(action, params)
"""
import re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
INDEX_HTML = HERE / "static" / "index.html"

def refactor():
    content = INDEX_HTML.read_text(encoding="utf-8")
    orig_len = len(content)

    # 1. HTML Passcode hints & badges
    content = content.replace(
        'PASSWORD 1111 = CONTROL PARAMETERS &nbsp;&nbsp; | &nbsp;&nbsp; PASSWORD 2222 = LOADCELL CALIBRATION',
        'CONTROL PARAMETERS &nbsp;&nbsp; | &nbsp;&nbsp; LOADCELL CALIBRATION'
    )
    content = content.replace(
        '<div class="cal-title">STN 1 CONTROL PARAMETERS</div><div class="cal-badge">PASSWORD: 1111</div>',
        '<div class="cal-title">STN 1 CONTROL PARAMETERS</div><div class="cal-badge">AUTHORIZED ACCESS</div>'
    )
    content = content.replace(
        '<div class="cal-title">STN 1 LOADCELL CALIBRATION</div><div class="cal-badge">PASSWORD: 2222</div>',
        '<div class="cal-title">STN 1 LOADCELL CALIBRATION</div><div class="cal-badge">AUTHORIZED ACCESS</div>'
    )
    content = content.replace(
        "openProtectedNumericPassword('recipecal_password','RECIPE CALIBRATION (PASSWORD: 4444)');",
        "openProtectedNumericPassword('recipecal_password','RECIPE CALIBRATION');"
    )
    content = content.replace(
        "target==='recipecal_password' ? 'PASSWORD: 4444' : ''",
        "''"
    )
    content = content.replace(
        "handleProtectedPasswordConfirm('recipecal_password','4444',",
        "handleProtectedPasswordConfirm('recipecal_password','',"
    )

    # 2. Keypad password verification in handleCalibrationConfirm -> POST /api/login
    old_cal_pass = """  if(activeNumpadTarget==='cal_password'){
    const ok=raw==='1111'||raw==='2222';
    document.getElementById('numpad-modal').classList.remove('open');
    if(ok){
      const isControl=raw==='1111';
      document.getElementById('stn1-password-screen').style.display='none';
      document.getElementById('stn1-control-screen').style.display=isControl?'flex':'none';
      document.getElementById('stn1-loadcell-screen').style.display=isControl?'none':'flex';
      document.getElementById('stn1-cal-badge').textContent=isControl?'PASSWORD 1111 VERIFIED':'PASSWORD 2222 VERIFIED';
      if (isControl) { initStn1ControlDraft(); discardStn1LoadcellDraft(); }
      else { initStn1LoadcellDraft(); discardStn1ControlDraft(); }
      updateCalibrationDisplay();
    }
    else { document.getElementById('numpad-display-val').textContent='INVALID'; setTimeout(()=>openCalibrationPad('password'),700); }
    return true;
  }"""

    new_cal_pass = """  if(activeNumpadTarget==='cal_password'){
    fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ passcode: raw })
    }).then(r => r.json()).then(res => {
      if(res.ok){
        document.getElementById('numpad-modal').classList.remove('open');
        const isControl = (res.role === 'stn1_control');
        document.getElementById('stn1-password-screen').style.display='none';
        document.getElementById('stn1-control-screen').style.display=isControl?'flex':'none';
        document.getElementById('stn1-loadcell-screen').style.display=isControl?'none':'flex';
        document.getElementById('stn1-cal-badge').textContent=isControl?'CONTROL PARAMETERS AUTHORIZED':'LOADCELL CALIBRATION AUTHORIZED';
        if (isControl) { initStn1ControlDraft(); discardStn1LoadcellDraft(); }
        else { initStn1LoadcellDraft(); discardStn1ControlDraft(); }
        updateCalibrationDisplay();
      } else {
        document.getElementById('numpad-display-val').textContent=res.error||'INVALID';
        setTimeout(()=>openCalibrationPad('password'),700);
      }
    }).catch(e => {
      document.getElementById('numpad-display-val').textContent='SERVER ERROR';
      setTimeout(()=>openCalibrationPad('password'),700);
    });
    return true;
  }"""
    if old_cal_pass in content:
        content = content.replace(old_cal_pass, new_cal_pass)
    else:
        content = re.sub(
            r"if\s*\(\s*activeNumpadTarget\s*===\s*'cal_password'\s*\)\s*\{[\s\S]*?return\s+true;\s*\}",
            new_cal_pass.strip(),
            content,
            count=1
        )

    # 3. Numeric range check in handleCalibrationConfirm -> validate number, save to server
    old_cal_range = """  const target=activeNumpadTarget.replace('cal_',''); const v=Number(raw); const cap=Math.max(1,Math.round(Number((stn1LoadcellDraft||HMI_STATE.stn1.calibration).loadcellCapacity)||1)); const ranges={acErr:[0.01,9.99],dcErr:[0,999],displayDamp:[1,99],brakePower:[1,99],loadcellCapacity:[1,999],knownWeight:[1,cap]};
  if(!Number.isFinite(v)||v<ranges[target][0]||v>ranges[target][1]||(target==='knownWeight'&&!Number.isInteger(v))) {
    document.getElementById('numpad-display-val').textContent='INVALID';
    isFirstNumpadKeypress = true;
    return false;
  }"""
    new_cal_range = """  const target=activeNumpadTarget.replace('cal_',''); const v=Number(raw);
  if(!Number.isFinite(v)) {
    document.getElementById('numpad-display-val').textContent='INVALID';
    isFirstNumpadKeypress = true;
    return false;
  }"""
    if old_cal_range in content:
        content = content.replace(old_cal_range, new_cal_range)
    else:
        content = re.sub(
            r"const\s+target\s*=\s*activeNumpadTarget\.replace\('cal_',''\);[\s\S]*?return\s+false;\s*\}",
            new_cal_range.strip(),
            content,
            count=1
        )

    # 4. handleProtectedPasswordConfirm -> POST /api/login
    old_prot_pass = """function handleProtectedPasswordConfirm(target,expected,onSuccess,reopenTitle){
  const raw=String(numpadBuffer||'');
  const modal=document.getElementById('numpad-modal');
  const valid = (raw === expected) || (target === 'recipecal_password' && (raw === '1111' || raw === '4444' || raw === '111' || raw.length >= 3));
  if(valid){ modal.classList.remove('open'); modal.querySelector('.numpad-modal').classList.remove('password-entry'); document.getElementById('numpad-btn-ok').textContent='CONFIRM & SET'; onSuccess(); return true; }
  document.getElementById('numpad-display-val').textContent='INVALID';
  isFirstNumpadKeypress=true;
  setTimeout(()=>openProtectedNumericPassword(target,reopenTitle),700);
  return false;
}"""

    new_prot_pass = """function handleProtectedPasswordConfirm(target,expected,onSuccess,reopenTitle){
  const raw=String(numpadBuffer||'');
  const modal=document.getElementById('numpad-modal');
  fetch('/api/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ passcode: raw })
  }).then(r => r.json()).then(res => {
    if(res.ok){
      modal.classList.remove('open');
      modal.querySelector('.numpad-modal').classList.remove('password-entry');
      document.getElementById('numpad-btn-ok').textContent='CONFIRM & SET';
      onSuccess();
    } else {
      document.getElementById('numpad-display-val').textContent=res.error||'INVALID';
      isFirstNumpadKeypress=true;
      setTimeout(()=>openProtectedNumericPassword(target,reopenTitle),700);
    }
  }).catch(() => {
    document.getElementById('numpad-display-val').textContent='SERVER ERROR';
    isFirstNumpadKeypress=true;
    setTimeout(()=>openProtectedNumericPassword(target,reopenTitle),700);
  });
  return false;
}"""
    if old_prot_pass in content:
        content = content.replace(old_prot_pass, new_prot_pass)

    # 5. handleStn2CalibrationConfirm range check -> validate number, server validates range on save
    old_stn2cal_ranges = """  const ranges={
    acErr:[0.1,99.9],
    dcErr:[0,999],
    spkErr:[0,999],
    encoderPprSet:[100,9999],
    markOffset:[-999,999],
    cylinderCircumference:[50,9999],
    b2bAlarm:[5,25],
    markSkipAlarm:[1,9],
    brakePower:[0,100],
    brakeCapacity:[1,20],
    brakeCurrent:[0.0,5.0],
    brakeCurrentCal:[1000,30000]
  };
  if(!Number.isFinite(v) || !ranges[target] || v<ranges[target][0] || v>ranges[target][1]){
    document.getElementById('numpad-display-val').textContent='INVALID';
    isFirstNumpadKeypress = true;
    return false;
  }"""
    new_stn2cal_ranges = """  if(!Number.isFinite(v)){
    document.getElementById('numpad-display-val').textContent='INVALID';
    isFirstNumpadKeypress = true;
    return false;
  }"""
    content = content.replace(old_stn2cal_ranges, new_stn2cal_ranges)
    content = content.replace("CALIBRATION MODE (CODE 3333 VERIFIED)", "CALIBRATION MODE AUTHORIZED")

    # 6. Replace localStorage in stn1 calibration save handlers
    content = content.replace(
        "try { localStorage.setItem('stn1LoadcellCalibration', JSON.stringify(applied)); } catch(e) {}",
        "fetch('/api/calibration', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ category: 'stn1_loadcell', data: applied }) }).catch(()=>{});"
    )
    content = content.replace(
        "try { localStorage.setItem('stn1ControlParameters', JSON.stringify(applied)); } catch(e) {}",
        "fetch('/api/calibration', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ category: 'stn1_control', data: applied }) }).catch(()=>{});"
    )

    # 7. Replace localStorage in RecipeDB
    content = content.replace(" *   - Storage : IndexedDB (images included).  Falls back to localStorage.", " *   - Storage : SQLite on server (/api/recipes).")
    old_ls_write = """  function lsWrite(){
    const pack=(withImg)=>JSON.stringify({list:list.map(r=>withImg?r:Object.assign({},r,{imageDataUrl:''})),ops,activeId,seedVersion});
    try{ localStorage.setItem(LS_KEY,pack(true)); }
    catch(e){ try{ localStorage.setItem(LS_KEY,pack(false)); mode='localStorage (no images)'; }catch(e2){ mode='memory'; } }
  }"""
    content = content.replace(old_ls_write, "  function lsWrite(){ mode='memory'; }")

    old_ls_read = """    if(!idb){
      mode='localStorage';
      try{ const d=JSON.parse(localStorage.getItem(LS_KEY)||'null'); if(d){ list=d.list||[]; meta={operators:d.ops,activeId:d.activeId,seedVersion:d.seedVersion}; } }catch(e){}
    }"""
    content = content.replace(old_ls_read, "    if(!idb){ mode='memory'; }")

    old_ls_legacy = """    // one-time import of the old localStorage library used by earlier versions
    if(!list.length && !seedVersion){
      try{ const old=JSON.parse(localStorage.getItem('recipeLibrary')||'null');
        if(Array.isArray(old)) old.forEach(o=>{ if(o&&o.name){ const n=normalizeRecipe(o); n.id=uid(); n.imageSig=null; list.push(n);} }); }catch(e){}
    }"""
    content = content.replace(old_ls_legacy, "    // Recipe library loaded from SQLite server /api/recipes")

    # 8. Replace localStorage in jobState (startJob, endJob, restoreJobState)
    content = re.sub(
        r"try\s*\{\s*localStorage\.setItem\('ricevision_job_state'[\s\S]*?\}\s*catch\(e\)\s*\{\s*\}",
        "// job state persisted on server via /api/action start_job",
        content,
        count=1
    )
    content = re.sub(
        r"try\s*\{\s*localStorage\.removeItem\('ricevision_job_state'\);\s*\}\s*catch\(e\)\s*\{\s*\}",
        "// job state cleared on server via /api/action end_job",
        content,
        count=1
    )
    old_restore_job = """function restoreJobState(){
  try{
    const saved = JSON.parse(localStorage.getItem('ricevision_job_state') || 'null');
    if(saved && saved.active && saved.startTime){
      jobState.active = true;
      jobState.startTime = new Date(saved.startTime);
      jobState.recipeId = saved.recipeId;
      jobState.recipeName = saved.recipeName;
      jobState.operator = saved.operator;
      updateJobUI();
    }
  }catch(e){}
}"""
    content = content.replace(old_restore_job, "function restoreJobState(){ if(typeof pollState==='function') pollState(); }")

    # 9. Replace recipeCalibration in applyRecipeToHmi & DOMContentLoaded
    content = re.sub(
        r"try\s*\{\s*const\s+lite\s*=\s*Object\.assign\(\{\},\s*rec,\s*\{imageDataUrl:'',imageSig:null\}\);\s*localStorage\.setItem\('recipeCalibration',JSON\.stringify\(lite\)\);\s*\}\s*catch\(e\)\{\}",
        "// active recipe tracked on server in machine_state",
        content
    )
    content = content.replace(
        "if(!a){ try{ const old=JSON.parse(localStorage.getItem('recipeCalibration')||'null'); if(old&&old.name) a=RecipeDB.findByName(old.name); }catch(e){} }",
        "// active recipe loaded from server /api/state"
    )

    # 10. Remove getUserMedia and replace with server stream
    old_cam_block = """async function getCameraStream(){
  if(!navigator.mediaDevices?.getUserMedia) throw new Error('Camera API unavailable');
  try{ return await navigator.mediaDevices.getUserMedia({video:{facingMode:'environment'},audio:false}); }
  catch(e){ return await navigator.mediaDevices.getUserMedia({video:true,audio:false}); }
}

async function openRecipeCamera(){
  if(LS.stream){ stopLoadCamera(); return; }
  lastDetectedRecipeId = null;
  try{
    LS.stream = await getCameraStream();
    const v = $rl('recipe-camera-video');
    v.srcObject = LS.stream;
    v.style.display = 'block';
    await v.play().catch(()=>{});
    $rl('recipe-camera-placeholder').style.display = 'none';
    const c = $rl('recipe-camera-compare');
    if(c) c.classList.remove('btn-cam-disabled');
    const st = $rl('recipe-camera-status');
    if(st) { st.textContent = 'CAMERA LIVE • SCANNING'; st.className = 'badge-cam-on'; }
    const b = $rl('recipe-camera-open');
    if(b) b.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/></svg> CLOSE CAMERA';
    updateRecipeLoadStatus('CAMERA LIVE • DETECTING...');

    if(autoDetectTimer) clearInterval(autoDetectTimer);
    setTimeout(()=>{ if(LS.stream) runAutoCameraDetection(); }, 250);
    autoDetectTimer = setInterval(()=>{
      if(LS.stream && v && v.readyState >= 2) runAutoCameraDetection();
    }, 350);
  }catch(e){
    console.warn('getUserMedia unavailable, falling back to /api/camera/stream', e);
    const v = $rl('recipe-camera-video');
    let streamImg = document.getElementById('recipe-camera-stream-img');
    if(!streamImg) {
      streamImg = document.createElement('img');
      streamImg.id = 'recipe-camera-stream-img';
      streamImg.style.cssText = 'width:100%;height:100%;object-fit:cover;display:block;';
      if(v && v.parentElement) v.parentElement.appendChild(streamImg);
    }
    streamImg.src = '/api/camera/stream?t=' + Date.now();
    streamImg.style.display = 'block';
    if(v) v.style.display = 'none';
    $rl('recipe-camera-placeholder').style.display = 'none';
    const c = $rl('recipe-camera-compare');
    if(c) c.classList.remove('btn-cam-disabled');
    const st = $rl('recipe-camera-status');
    if(st) { st.textContent = 'CAMERA LIVE • STREAM'; st.className = 'badge-cam-on'; }
    const b = $rl('recipe-camera-open');
    if(b) b.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/></svg> CLOSE CAMERA';
    updateRecipeLoadStatus('CAMERA LIVE • DETECTING...');
    LS.stream = {
      serverStream: true,
      stop: () => {
        if(streamImg) { streamImg.style.display = 'none'; streamImg.src = ''; }
      }
    };
    if(autoDetectTimer) clearInterval(autoDetectTimer);
    setTimeout(()=>{ if(LS.stream) runAutoCameraDetection(); }, 250);
    autoDetectTimer = setInterval(()=>{
      if(LS.stream) runAutoCameraDetection();
    }, 350);
  }
}"""

    new_cam_block = """// Server camera only: /api/camera/stream
async function openRecipeCamera(){
  if(LS.stream){ stopLoadCamera(); return; }
  lastDetectedRecipeId = null;
  const v = $rl('recipe-camera-video');
  let streamImg = document.getElementById('recipe-camera-stream-img');
  if(!streamImg) {
    streamImg = document.createElement('img');
    streamImg.id = 'recipe-camera-stream-img';
    streamImg.style.cssText = 'width:100%;height:100%;object-fit:cover;display:block;';
    if(v && v.parentElement) v.parentElement.appendChild(streamImg);
  }
  streamImg.src = '/api/camera/stream';
  streamImg.style.display = 'block';
  if(v) v.style.display = 'none';
  $rl('recipe-camera-placeholder').style.display = 'none';
  const c = $rl('recipe-camera-compare');
  if(c) c.classList.remove('btn-cam-disabled');
  const st = $rl('recipe-camera-status');
  if(st) { st.textContent = 'SERVER STREAM LIVE'; st.className = 'badge-cam-on'; }
  const b = $rl('recipe-camera-open');
  if(b) b.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/></svg> CLOSE CAMERA';
  updateRecipeLoadStatus('SERVER STREAM LIVE • READY');
  LS.stream = {
    serverStream: true,
    stop: () => {
      if(streamImg) { streamImg.style.display = 'none'; streamImg.src = ''; }
    }
  };
}"""
    if old_cam_block in content:
        content = content.replace(old_cam_block, new_cam_block)
    else:
        print("WARNING: old_cam_block not found exactly, doing regex replacement")
        content = re.sub(
            r"async\s+function\s+getCameraStream\s*\(\)\s*\{[\s\S]*?async\s+function\s+openRecipeCamera\s*\(\)\s*\{[\s\S]*?autoDetectTimer\s*=\s*setInterval\([\s\S]*?\}\s*\}",
            new_cam_block,
            content,
            count=1
        )

    old_open_capture = """    const v = $('recipe-cam-video');
    const fallback = $('recipe-cam-stream-fallback');
    try{
      camStream = await getCameraStream();
      if (v) {
        v.srcObject = camStream;
        v.style.display = 'block';
        await v.play().catch(()=>{});
      }
      if (fallback) fallback.style.display = 'none';
      $('recipe-cam-modal').classList.add('open');
    }catch(e){
      console.warn('getUserMedia error, using /api/camera/stream fallback', e);
      if (v) { v.srcObject = null; v.style.display = 'none'; }
      if (fallback) {
        fallback.src = '/api/camera/stream?t=' + Date.now();
        fallback.style.display = 'block';
      }
      $('recipe-cam-modal').classList.add('open');
    }"""
    new_open_capture = """    const v = $('recipe-cam-video');
    const fallback = $('recipe-cam-stream-fallback');
    if (v) { v.srcObject = null; v.style.display = 'none'; }
    if (fallback) {
      fallback.src = '/api/camera/stream';
      fallback.style.display = 'block';
    }
    camStream = { serverStream: true };
    $('recipe-cam-modal').classList.add('open');"""
    content = content.replace(old_open_capture, new_open_capture)

    # 11. Remove startSimulatedSensors random jitter
    old_sim_sensors = """function startSimulatedSensors() {
  setInterval(() => {
    if (HMI_STATE.stn1.mode === 'AUTO') {
      const jitter = (Math.random() - 0.5) * 0.12;
      const targetTension = Number(HMI_STATE.recipe?.sTensionTarget) || 5.0;
      HMI_STATE.stn1.sTension = Math.max(0, Math.min(99.9, targetTension + jitter));
      HMI_STATE.stn1.aTension = Math.max(0, Math.min(99.9, targetTension * 0.9 + jitter * 0.8));
    }

    const indicator = document.getElementById('svg-reg-indicator');
    if (indicator) {
      const offset = (Math.random() - 0.5) * 6;
      indicator.setAttribute('x', 165 + offset);
    }

    refreshUI();
  }, 1000);

  // Cyclic 200 ms poll for STN 2 REGISMATIC state (MODBUS_MESSAGES.md Section 1)
  setInterval(() => {
    if (typeof pollFBarXState === 'function') pollFBarXState();
  }, 200);
  if (typeof pollFBarXState === 'function') pollFBarXState();
}"""
    new_sim_sensors = """function startSimulatedSensors() {
  // Pure server poll loop - all simulation, counting, and measurements run on server.py
  setInterval(() => {
    if (typeof pollState === 'function') pollState();
  }, 250);
  if (typeof pollState === 'function') pollState();
}"""
    content = content.replace(old_sim_sensors, new_sim_sensors)

    # 12. Remove browser comparison loop startLiveComparisonLoop
    old_live_comp = """  function startLiveComparisonLoop() {
    if (liveCompareTimer) clearInterval(liveCompareTimer);
    liveCompareTimer = setInterval(async () => {
      const s2Mode = (window.HMI_STATE?.stn2?.mode || 'OFF');
      if (s2Mode === 'OFF') {
        stopLiveCamera();
        return;
      }
      if (activeCamError !== 'live' || isComparing) return;
      isComparing = true;
      try {
        const vid = document.getElementById('full-cam-video');
        const activeRid = (window.HMI_STATE && window.HMI_STATE.recipe && window.HMI_STATE.recipe.numericId) ? window.HMI_STATE.recipe.numericId : 0;
        let cmpData = null;

        if (vid && vid.style.display !== 'none' && vid.readyState >= 2 && vid.videoWidth > 0) {
          // Mirror frame to Screen 1 mini-img
          const miniImg = document.getElementById('recipe-live-cam-img');
          const canvas = document.createElement('canvas');
          canvas.width = Math.min(860, vid.videoWidth);
          canvas.height = Math.round(canvas.width * vid.videoHeight / vid.videoWidth);
          const ctx = canvas.getContext('2d');
          ctx.drawImage(vid, 0, 0, canvas.width, canvas.height);
          if (miniImg && !miniImg.src.startsWith('blob:')) {
            miniImg.src = canvas.toDataURL('image/jpeg', 0.6);
          }
          const curErr = window.activeCamError || 'live';
          const blob = await new Promise(res => canvas.toBlob(res, 'image/jpeg', 0.85));
          cmpData = await fetch('/api/camera/compare_front_back?error=' + encodeURIComponent(curErr) + '&recipe_id=' + activeRid + '&mode=' + encodeURIComponent(s2Mode), {
            method: 'POST',
            headers: { 'Content-Type': 'image/jpeg' },
            body: blob
          }).then(r => r.json()).catch(() => null);
        } else {
          const curErr = window.activeCamError || 'live';
          cmpData = await fetch('/api/camera/compare_front_back?error=' + encodeURIComponent(curErr) + '&recipe_id=' + activeRid + '&mode=' + encodeURIComponent(s2Mode))
            .then(r => r.json()).catch(() => null);
        }

        if (cmpData && activeCamError === 'live') {
          (window.updateErrorPercentageDisplay || updateErrorPercentageDisplay)(cmpData);
        }
      } catch (err) {
        console.warn('[LIVE CAM] Comparison cycle error:', err);
      } finally {
        isComparing = false;
      }
    }, 350);
  }"""

    new_live_comp = """  function startLiveComparisonLoop() {
    // Camera measurements run in background CameraService thread on server.py
    if (liveCompareTimer) clearInterval(liveCompareTimer);
    liveCompareTimer = null;
  }"""
    content = content.replace(old_live_comp, new_live_comp)

    # 13. Add sendAction, pollState, applyState, and disconnection banner
    ui_engine = """
<script>
/* ===================== UNIFIED SERVER STATE & ACTION ENGINE ===================== */
let _lastServerStartId = null;
let _lastStateSuccessTime = Date.now();

function showServerDisconnectedBanner(msg) {
  let el = document.getElementById('server-disconnected-banner');
  if (!el) {
    el = document.createElement('div');
    el.id = 'server-disconnected-banner';
    el.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:99999;background:#b91c1c;color:#fff;text-align:center;font-weight:bold;font-size:14px;padding:8px;letter-spacing:1px;box-shadow:0 2px 10px rgba(0,0,0,0.5);font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;';
    document.body.appendChild(el);
  }
  const age = Math.round((Date.now() - _lastStateSuccessTime) / 1000);
  el.textContent = `⚠ ${msg} (Last update: ${age}s ago)`;
  el.style.display = 'block';
}

function hideServerDisconnectedBanner() {
  const el = document.getElementById('server-disconnected-banner');
  if (el) el.style.display = 'none';
}

async function sendAction(action, params = {}) {
  try {
    const body = Object.assign({ action }, params);
    const res = await fetch('/api/action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      const err = data.error || ('HTTP ' + res.status);
      if (typeof showToast === 'function') showToast(err);
      return { ok: false, error: err };
    }
    if (data.state) {
      applyState(data.state);
    }
    return data;
  } catch (e) {
    if (typeof showToast === 'function') showToast('Network error: ' + e.message);
    return { ok: false, error: e.message };
  }
}
window.sendAction = sendAction;

function applyState(state) {
  if (!state || !state.ok) return;

  // 1. Restart detection
  if (state.server_start_id) {
    if (_lastServerStartId && _lastServerStartId !== state.server_start_id) {
      console.log('Server restarted, reloading UI...');
      window.location.reload();
      return;
    }
    _lastServerStartId = state.server_start_id;
  }

  // 2. Hardware link & banner
  const live = Boolean(state.connected);
  const statusDots = document.querySelectorAll('.serial-port-dot, #status-bar .status-dot, .port-status-dot');
  statusDots.forEach(dot => {
    dot.classList.toggle('online', live);
    dot.classList.toggle('offline', !live);
    dot.style.background = state.status === 'OK' ? '#20e85a' : (state.simulated ? '#f5a623' : '#ff3b30');
  });
  if (typeof setFbarxBanner === 'function') setFbarxBanner(state.status || (live ? 'OK' : 'NOT CONNECTED'));
  document.getElementById('col-stn2')?.classList.toggle('link-down', !live);

  // 3. Station 1
  if (state.stn1) {
    HMI_STATE.stn1.mode = state.stn1.mode;
    HMI_STATE.stn1.outputPct = state.stn1.outputPct;
    HMI_STATE.stn1.ammeter = state.stn1.ammeter;
    HMI_STATE.stn1.unit = state.stn1.unit;
    HMI_STATE.stn1.sTension = state.stn1.sTensionTarget;
    HMI_STATE.stn1.aTension = state.stn1.aTension;
    HMI_STATE.stn1.brakeType = state.stn1.brakeType;

    document.querySelectorAll('#col-stn1 .mode-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.mode === state.stn1.mode);
    });
    const col1 = document.getElementById('col-stn1');
    if (col1) {
      col1.classList.remove('mode-auto', 'mode-man', 'mode-off');
      col1.classList.add(state.stn1.mode === 'AUTO' ? 'mode-auto' : (state.stn1.mode === 'MAN' ? 'mode-man' : 'mode-off'));
    }
    const bar1 = document.getElementById('stn1-out-bar');
    const txt1 = document.getElementById('stn1-out-bar-txt');
    if (bar1) bar1.style.width = Math.max(0, Math.min(100, state.stn1.outputPct)) + '%';
    if (txt1) txt1.textContent = (state.stn1.outputPct % 1 === 0 ? Math.round(state.stn1.outputPct) : state.stn1.outputPct.toFixed(1)) + '%';

    const valTen = document.getElementById('val-tension');
    const unitTen = document.getElementById('unit-tension');
    if (valTen) valTen.textContent = (state.stn1.sTensionTarget || 5.0).toFixed(1);
    if (unitTen) unitTen.textContent = state.stn1.unit || 'kg';
  }

  // 4. Station 2
  if (state.stn2) {
    HMI_STATE.stn2.mode = state.stn2.mode;
    HMI_STATE.stn2.outputPct = state.stn2.outputPct;
    HMI_STATE.stn2.ammeter = state.stn2.ammeter;
    HMI_STATE.stn2.speedMpm = state.stn2.speedMpm;

    document.querySelectorAll('#col-stn2 .mode-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.mode === state.stn2.mode);
    });
    const col2 = document.getElementById('col-stn2');
    if (col2) {
      col2.classList.remove('mode-auto', 'mode-man', 'mode-off');
      col2.classList.add(state.stn2.mode === 'AUTO' ? 'mode-auto' : (state.stn2.mode === 'MAN' ? 'mode-man' : 'mode-off'));
    }
    const bar2 = document.getElementById('stn2-out-bar');
    const txt2 = document.getElementById('stn2-out-bar-txt');
    if (bar2) bar2.style.width = Math.max(0, Math.min(100, state.stn2.outputPct)) + '%';
    if (txt2) txt2.textContent = (state.stn2.outputPct % 1 === 0 ? Math.round(state.stn2.outputPct) : state.stn2.outputPct.toFixed(1)) + '%';

    const speedEls = document.querySelectorAll('#stn2-line-speed, #status-speed-val, [data-stn2-speed]');
    speedEls.forEach(el => el.textContent = state.stn2.speedMpm);

    if (activeNumpadTarget !== 'repeat') {
      const dispRepeat = document.getElementById('disp-repeat');
      if (dispRepeat) dispRepeat.textContent = state.stn2.repeatLength;
      if (HMI_STATE.recipe) HMI_STATE.recipe.repeatLength = state.stn2.repeatLength;
    }
    if (activeNumpadTarget !== 'markwin') {
      const dispWindow = document.getElementById('disp-window');
      if (dispWindow) dispWindow.textContent = state.stn2.markWindow;
      if (HMI_STATE.recipe) HMI_STATE.recipe.markWindow = state.stn2.markWindow;
    }
  }

  // 5. Render live ammeters
  if (typeof window.renderLiveAmmeters === 'function') window.renderLiveAmmeters();
  if (typeof applyModeInteractionState === 'function') applyModeInteractionState();

  // 6. Registration display
  if (state.registration) {
    const reg = state.registration;
    updateRepAndRulerDisplay(reg.repeatLengthActual, reg.errorMm, reg.valid, state.stn2.mode === 'OFF');
    const camMatch = document.getElementById('cam-matched-name');
    if (camMatch && state.recipe && state.recipe.name) {
      camMatch.textContent = state.recipe.name + ' (Front & Back)';
    }
  }

  // 7. Counters & Bands
  if (state.counters) {
    const c = state.counters;
    updateDynamicCounterBands(c.counterBands, c, state.registration?.errorMm, state.registration?.valid);
    if (!HMI_STATE.report) HMI_STATE.report = {};
    HMI_STATE.report.counters = Object.assign({}, c);

    const totEl = document.getElementById('report-total-count') || document.getElementById('count-total');
    if (totEl) totEl.textContent = c.total;
    const passEl = document.getElementById('report-pass-pct') || document.getElementById('count-pass-pct');
    if (passEl) passEl.textContent = c.passPct + '%';
  }

  // 8. Active Job
  if (state.job) {
    jobState.active = Boolean(state.job.active);
    jobState.recipeId = state.job.recipeId;
    jobState.recipeName = state.job.recipeName;
    jobState.operator = state.job.operator;
    jobState.durationStr = state.job.durationStr;
    if (state.job.startTime) jobState.startTime = new Date(state.job.startTime);
    updateJobUI();
  }

  // 9. Camera status & badges
  if (state.camera) {
    const camBadge = document.getElementById('cam-mode-badge') || document.getElementById('badge-cam-mode');
    if (camBadge && state.camera.modeBadge) {
      camBadge.textContent = state.camera.modeBadge;
      const isAuto = state.stn2?.mode === 'AUTO';
      const isMan = state.stn2?.mode === 'MAN';
      camBadge.style.background = isAuto ? '#061c14' : (isMan ? '#241a04' : '#161b22');
      camBadge.style.color = isAuto ? '#10b981' : (isMan ? '#f59e0b' : '#8b949e');
      camBadge.style.borderColor = isAuto ? '#10b981' : (isMan ? '#f59e0b' : '#30363d');
    }
  }

  // 10. Active Recipe
  if (state.recipe) {
    const el = document.getElementById('active-recipe-name');
    if (el && state.recipe.name) el.textContent = state.recipe.name;
    if (state.recipe.imageUrl) {
      const img1 = document.getElementById('recipe-img-preview');
      if (img1 && !img1.src.includes(state.recipe.imageUrl)) img1.src = state.recipe.imageUrl;
    }
  }
}
window.applyState = applyState;

async function pollState() {
  if (pollState._inFlight) return;
  pollState._inFlight = true;
  try {
    const res = await fetch('/api/state', { cache: 'no-store' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const state = await res.json();
    _lastStateSuccessTime = Date.now();
    hideServerDisconnectedBanner();
    applyState(state);
  } catch (err) {
    if (Date.now() - _lastStateSuccessTime > 2000) {
      showServerDisconnectedBanner('SERVER NOT CONNECTED');
    }
  } finally {
    pollState._inFlight = false;
  }
}
window.pollState = pollState;
</script>
"""
    # Insert right before the FINAL </body> at the end of the document (only once!)
    if "/* ===================== UNIFIED SERVER STATE & ACTION ENGINE ===================== */" not in content:
        last_body = content.rfind("</body>")
        if last_body != -1:
            content = content[:last_body] + ui_engine + "\n" + content[last_body:]

    INDEX_HTML.write_text(content, encoding="utf-8")
    print(f"Refactor complete. File size: {orig_len} -> {len(content)}")

if __name__ == "__main__":
    refactor()
