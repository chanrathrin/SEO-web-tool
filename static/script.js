/* ═══════════════════════════════════════════════════════════════
   WordPress SEO Studio — Frontend JS
   Mirrors Tkinter desktop app behaviour exactly
═══════════════════════════════════════════════════════════════ */
'use strict';

// ── Global state ───────────────────────────────────────────────
let _apiKey       = localStorage.getItem('wps_apiKey') || '';
let _apiKeySaved  = !!_apiKey;
let _detectedLang = 'English';
let _currentSections = {};  // mirrors self.current_sections in desktop
let _generatedPlain  = '';

// Image / crop state
let _origImage    = null;   // HTMLImageElement of uploaded image
let _origFile     = null;
let _croppedBlob  = null;   // result of applyCrop()
let _zoomFactor   = 1.0;
let _currentRatio = 1200/366;
let _imageOffsetX = 0, _imageOffsetY = 0;
let _baseScale    = 1, _displayScale = 1;
let _displayW     = 1, _displayH     = 1;
let _cropRect     = [120, 60, 720, 243];   // [x1,y1,x2,y2] in canvas coords
let _draggingCrop  = false, _draggingImage = false;
let _resizingHandle = null;
let _cropDragStart  = [0,0];
let _startCropRect  = null;
let _startOffset    = null;
let _handleSize     = 12;
let _redrawId       = null;
let _lastCanvasSize = [0,0];
let _previewCache   = null;   // {sz, bitmap}

// ── Init ───────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  if (_apiKey) { updateApiBadge(); document.getElementById('api-key-input').value = _apiKey; }
  resizeCanvas();
  window.addEventListener('resize', () => { resizeCanvas(); requestRedraw(30); });
  setStatus('Ready');
  // canvas drag-and-drop
  document.getElementById('canvas-wrap').addEventListener('dragover', e => e.preventDefault());
  document.getElementById('canvas-wrap').addEventListener('drop', e => { e.preventDefault(); onCanvasDrop(e); });
});

// ════════════════════ TABS ══════════════════════════════════════
function switchTab(name, btn) {
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  btn.classList.add('active');
  if (name === 'image') { resizeCanvas(); requestRedraw(60); }
}

// ════════════════════ STATUS ════════════════════════════════════
function setStatus(msg) { document.getElementById('status-text').textContent = '  ' + msg; }
function log(msg) {
  const el = document.getElementById('process-log');
  const now = new Date(); const ts = now.toTimeString().slice(0,8);
  el.textContent += `[${ts}]  ${msg}\n${'─'.repeat(50)}\n`;
  el.scrollTop = el.scrollHeight;
}
function clearLog() { document.getElementById('process-log').textContent = ''; }

// ════════════════════ SPINNER ═══════════════════════════════════
function showSpinner(msg='Processing…') {
  document.getElementById('spinner-text').textContent = msg;
  document.getElementById('spinner').style.display = 'flex';
}
function hideSpinner() { document.getElementById('spinner').style.display = 'none'; }

// ════════════════════ CLIPBOARD ═════════════════════════════════
function clipboard(text) {
  if (!text || !text.trim()) { setStatus('Nothing to copy'); return; }
  navigator.clipboard.writeText(text).catch(() => {
    const ta = document.createElement('textarea');
    ta.value = text; document.body.appendChild(ta); ta.select();
    document.execCommand('copy'); document.body.removeChild(ta);
  });
}

// ════════════════════ API MODAL ══════════════════════════════════
function openApiModal() {
  document.getElementById('api-modal').style.display = 'flex';
  document.getElementById('api-status').textContent = '';
  document.getElementById('api-status').className = 'api-status';
  if (_apiKey) {
    document.getElementById('api-key-input').value = _apiKey;
    apiStatus('Current key loaded', '');
  } else {
    apiStatus('Paste your Together AI key below', '');
  }
}
function closeApiModal() { document.getElementById('api-modal').style.display = 'none'; }
function apiStatus(msg, cls='') {
  const el = document.getElementById('api-status');
  el.textContent = msg; el.className = 'api-status ' + cls;
}
function toggleKeyVis() {
  const inp = document.getElementById('api-key-input');
  const cb  = document.getElementById('show-key-cb');
  inp.type  = cb.checked ? 'text' : 'password';
}
async function testKey() {
  const k = document.getElementById('api-key-input').value.trim();
  if (!k) { apiStatus('Paste your API key first.', 'err'); return; }
  apiStatus('Testing…', 'info');
  try {
    const r = await fetch('/api/verify-key', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({api_key:k}) });
    const d = await r.json();
    if (d.ok) { apiStatus('✓ Key is valid', 'ok'); }
    else       { apiStatus('✗ ' + (d.error||'Invalid key'), 'err'); }
  } catch(e) { apiStatus('✗ Network error: ' + e.message, 'err'); }
}
async function saveKey() {
  const k = document.getElementById('api-key-input').value.trim();
  if (!k) { apiStatus('Paste your API key first.', 'err'); return; }
  await fetch('/api/set-key', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({api_key:k}) });
  _apiKey = k; _apiKeySaved = true;
  localStorage.setItem('wps_apiKey', k);
  updateApiBadge(); apiStatus('✓ Key saved & applied', 'ok');
  setTimeout(closeApiModal, 700);
  setStatus('API key loaded');
}
function sessionKey() {
  const k = document.getElementById('api-key-input').value.trim();
  if (!k) { apiStatus('Paste your API key first.', 'err'); return; }
  _apiKey = k; _apiKeySaved = false;
  fetch('/api/set-key', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({api_key:k}) });
  updateApiBadge(); closeApiModal(); setStatus('Session key active');
}
function clearKey() {
  _apiKey = ''; _apiKeySaved = false;
  localStorage.removeItem('wps_apiKey');
  document.getElementById('api-key-input').value = '';
  fetch('/api/set-key', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({api_key:''}) });
  updateApiBadge(); apiStatus('Saved key cleared', 'info');
}
function updateApiBadge() {
  const el = document.getElementById('api-badge');
  if (_apiKey && _apiKeySaved)  { el.textContent = '●  API key saved';     el.className = 'badge badge-ok'; }
  else if (_apiKey)             { el.textContent = '●  Session key active'; el.className = 'badge badge-warn'; }
  else                          { el.textContent = '○  API not configured'; el.className = 'badge badge-off'; }
}

// ════════════════════ SEO TAB — FETCH & GENERATE ════════════════
async function fetchAndGenerate() {
  const url = document.getElementById('url-entry').value.trim();
  if (!url) { setStatus('Paste a URL first'); return; }
  const btn = document.getElementById('fetch-btn');
  btn.disabled = true; btn.textContent = '⏳ Fetching…'; btn.style.background = '#5b21b6';
  const langBadge = document.getElementById('lang-badge');
  langBadge.textContent = '🌐 …';
  setStatus('Fetching: ' + url.slice(0,60) + '…');
  log('Fetching URL: ' + url);
  try {
    const r = await fetch('/api/fetch-url', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({url}) });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'Fetch failed');
    document.getElementById('article-input').value = d.html;
    _detectedLang = d.language || 'English';
    langBadge.textContent = '🌐 ' + _detectedLang;
    log(`Fetched ${d.html.length} chars | Language: ${_detectedLang}`);
    setStatus(`Fetched ${d.html.length.toLocaleString()} chars | 🌐 ${_detectedLang} — generating SEO…`);
    btn.textContent = '⬇  Fetch & Generate'; btn.disabled = false; btn.style.background = '';
    // update cleaned URL
    if (d.url) { document.getElementById('url-entry').value = d.url; }
    await processArticle();
  } catch(e) {
    log('All urllib strategies failed: ' + e.message);
    setStatus('Fetch failed — paste article manually');
    btn.textContent = '⬇  Fetch & Generate'; btn.disabled = false; btn.style.background = '';
    alert('Fetch Failed\n\nCould not fetch URL:\n' + e.message + '\n\nPlease paste article text manually.');
  }
}

async function processArticle() {
  const raw = document.getElementById('article-input').value.trim();
  // clear placeholder text
  if (!raw || raw === 'Paste article text or full HTML code here…') {
    setStatus('Please paste an article first'); return;
  }
  const btn = document.getElementById('seo-gen-btn');
  btn.disabled = true; btn.textContent = '⏳ Generating...'; btn.style.background = '#1a3a1a';
  log(`Input length: ${raw.length} chars`);
  setStatus('Generating SEO…');
  try {
    const r = await fetch('/api/process-article', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({text:raw}) });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'Processing failed');
    _detectedLang = d.language || 'English';
    document.getElementById('lang-badge').textContent = '🌐 ' + _detectedLang;
    _currentSections = {
      h1_copy:               d.h1,
      intro_copy:            d.intro,
      focus_keyphrase_copy:  d.focus_keyphrase,
      seo_title_copy:        (d.seo_title_options||[])[0] || '',
      meta_description_copy: (d.meta_options||[])[0] || '',
      hashtags_copy:         d.hashtags,
      short_caption_copy:    d.short_caption,
      wp_html_copy:          d.wp_html,
      structure_copy:        d.struct || [],
    };
    _generatedPlain = d.wp_html || '';
    renderOutput(d.output_sections || []);
    log(`✓ Generate SEO completed successfully.`);
    setStatus(`✓ SEO output generated | 🌐 ${_detectedLang}`);
  } catch(e) {
    log('GENERATE SEO FAILED: ' + e.message);
    setStatus('Error: ' + e.message.slice(0,120));
  } finally {
    btn.disabled = false; btn.textContent = '⚡ Generate SEO'; btn.style.background = '';
  }
}

// Render output_sections array → output display div (matches tag_configure styles)
function renderOutput(sections) {
  const div = document.getElementById('output-display');
  div.innerHTML = '';
  for (const s of sections) {
    const span = document.createElement('span');
    span.className = 'out-' + (s.tag || 'body');
    span.textContent = s.text || '';
    if (s.url) {
      const link = document.createElement('a');
      link.href = s.url; link.textContent = '  ' + s.url;
      link.className = 'embed-url-link'; link.target = '_blank';
      span.appendChild(document.createElement('br'));
      span.appendChild(link);
    }
    div.appendChild(span);
  }
}

// Quick Copy pills — matches copy_section()
function copySection(name) {
  if (!_currentSections || Object.keys(_currentSections).length === 0) {
    setStatus('Generate SEO output first'); return;
  }
  const MAP = {
    'Focus Keyphrase': _currentSections.focus_keyphrase_copy || '',
    'SEO Title':       _currentSections.seo_title_copy || '',
    'Meta Description': _currentSections.meta_description_copy || '',
    'Hashtags':        _currentSections.hashtags_copy || '',
  };
  const val = (MAP[name] || '').replace(/\s+/g,' ').trim();
  if (!val) { setStatus('No content for ' + name); return; }
  clipboard(val); setStatus('Copied: ' + name);
}

function copyWpHtml() {
  const payload = _currentSections.wp_html_copy || _generatedPlain || '';
  if (!payload.trim()) { setStatus('Nothing to copy — generate first'); return; }
  clipboard(payload); setStatus('Copied WordPress-ready HTML');
}

function clearInput() {
  document.getElementById('article-input').value = '';
  document.getElementById('url-entry').value = '';
  setStatus('Input cleared');
}

function clearOutput() {
  document.getElementById('output-display').innerHTML = '';
  document.getElementById('process-log').textContent = '';
  _currentSections = {}; _generatedPlain = '';
  setStatus('Output cleared');
}

// ════════════════════ AI SEO POPUP ══════════════════════════════
function openAiSeoPopup() {
  if (!_apiKey) {
    alert('API Key Required\n\nNo Together AI key found.\n\nOpen API Settings → paste key → Save & Use.');
    openApiModal(); return;
  }
  const article = document.getElementById('article-input').value.trim();
  if (!article || article === 'Paste article text or full HTML code here…') {
    alert('No Article\n\nPlease paste an article first, then click AI SEO Fields.');
    return;
  }
  document.getElementById('ai-seo-modal').style.display = 'flex';
  document.getElementById('ai-lang-badge').textContent = '🌐 ' + _detectedLang;
  aiPopupStatus('⏳ Generating SEO fields with AI…', 'info');
  document.getElementById('regen-btn').disabled = false;
  document.getElementById('regen-btn').textContent = '⟳  Regenerate';
  // clear fields
  ['ai-fk','ai-seo-title','ai-meta'].forEach(id => {
    const el = document.getElementById(id);
    if (el.tagName === 'TEXTAREA') el.value = ''; else el.value = '';
  });
  document.getElementById('ai-seo-variants').innerHTML = '';
  document.getElementById('ai-meta-variants').innerHTML = '';
  updateFkCounter(''); updateSeoCounter(''); updateMetaCounter('');
  updateGooglePreview();
  // auto-generate
  runAiGenerate(article);
}
function closeAiModal() { document.getElementById('ai-seo-modal').style.display = 'none'; }

function aiPopupStatus(msg, cls='') {
  const el = document.getElementById('ai-popup-status');
  el.textContent = msg;
  el.style.color = cls==='ok' ? 'var(--ok)' : cls==='err' ? 'var(--bad)' : 'var(--warn)';
}

async function runAiGenerate(articleText) {
  const btn = document.getElementById('regen-btn');
  btn.disabled = true; btn.textContent = '⏳ Generating…';
  if (!articleText) articleText = document.getElementById('article-input').value.trim();
  try {
    const r = await fetch('/api/ai-seo-fields', { method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ text: articleText, api_key: _apiKey, language: _detectedLang }) });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'AI SEO fields failed');

    // fill fields
    document.getElementById('ai-fk').value = d.focus_keyphrase || '';
    updateFkCounter(d.focus_keyphrase || '');

    const title1 = (d.seo_titles||[])[0]||'';
    document.getElementById('ai-seo-title').value = title1;
    updateSeoCounter(title1);

    const meta1 = (d.meta_descriptions||[])[0]||'';
    document.getElementById('ai-meta').value = meta1;
    updateMetaCounter(meta1);

    renderVariants('ai-seo-variants', d.seo_titles||[], 60, v => {
      document.getElementById('ai-seo-title').value = v; updateSeoCounter(v);
    });
    renderVariants('ai-meta-variants', d.meta_descriptions||[], 160, v => {
      document.getElementById('ai-meta').value = v; updateMetaCounter(v);
    });
    updateGooglePreview();
    aiPopupStatus('✓ AI SEO fields ready', 'ok');
  } catch(e) {
    aiPopupStatus('✗ Error: ' + e.message.slice(0,200), 'err');
    alert('AI SEO Fields Error\n\nCould not generate AI SEO Fields.\n\nReason:\n' + e.message);
  } finally {
    btn.disabled = false; btn.textContent = '⟳  Regenerate';
  }
}

function regenAiFields() {
  const article = document.getElementById('article-input').value.trim();
  aiPopupStatus('⏳ Regenerating…', 'info');
  runAiGenerate(article);
}

function applyAiFields() {
  const fk    = document.getElementById('ai-fk').value.trim();
  const title = document.getElementById('ai-seo-title').value.trim();
  const meta  = document.getElementById('ai-meta').value.trim();
  if (!fk && !title && !meta) {
    alert('Empty Fields\n\nGenerate SEO fields first.'); return;
  }
  _currentSections.focus_keyphrase_copy  = fk;
  _currentSections.seo_title_copy        = title;
  _currentSections.meta_description_copy = meta;
  setStatus('AI SEO Fields applied ✓');
  closeAiModal();
}

function copyAiField(id, isTextarea=false) {
  const el = document.getElementById(id);
  const val = el.tagName === 'TEXTAREA' ? el.value : el.value;
  if (!val.trim()) return;
  clipboard(val);
}

// ── Character counters ─────────────────────────────────────────
function updateFkCounter(val) {
  const words = val.trim() ? val.trim().split(/\s+/).length : 0;
  const chars = val.length;
  const el = document.getElementById('ai-fk-counter');
  if (!chars) { el.textContent = ''; el.style.color = 'var(--text-soft)'; return; }
  if (words <= 4) { el.textContent = `✓ Good  (${words} words, ${chars} chars)`; el.style.color = 'var(--ok)'; }
  else            { el.textContent = `⚠ Try shorter  (${words} words — Yoast recommends ≤4)`; el.style.color = 'var(--warn)'; }
}

function updateSeoCounter(val) {
  const n = val.length, MAX = 60;
  const pct = Math.min(100, (n/MAX)*100);
  const bar = document.getElementById('ai-seo-bar');
  const cnt = document.getElementById('ai-seo-count');
  const hint = document.getElementById('ai-seo-hint');
  bar.style.width = pct + '%';
  let col, hintText;
  if (!n)        { col='var(--text-soft)'; hintText='—'; }
  else if (n<30) { col='var(--warn)'; hintText=`⚠ Too short (${n}/60)`; }
  else if (n<50) { col='var(--warn)'; hintText=`⚠ Could be longer (${n}/60)`; }
  else if (n<=60){ col='var(--ok)';   hintText=`✓ Good length (${n}/60)`; }
  else           { col='var(--bad)';  hintText=`✗ Too long — cut ${n-MAX} chars (${n}/60)`; }
  bar.style.background = col;
  cnt.textContent = `${n} / 60`; cnt.style.color = col;
  hint.textContent = hintText; hint.style.color = col;
  updateGooglePreview();
}

function updateMetaCounter(val) {
  const n = val.trim().length, MAX = 160;
  const pct = Math.min(100, (n/MAX)*100);
  const bar = document.getElementById('ai-meta-bar');
  const cnt = document.getElementById('ai-meta-count');
  const hint = document.getElementById('ai-meta-hint');
  bar.style.width = pct + '%';
  let col, hintText;
  if (!n)        { col='var(--text-soft)'; hintText='—'; }
  else if (n<120){ col='var(--warn)'; hintText=`⚠ Too short (${n}/160)`; }
  else if (n<=155){ col='var(--ok)';  hintText=`✓ Good length (${n}/160)`; }
  else if (n<=160){ col='var(--ok)';  hintText=`✓ Acceptable (${n}/160)`; }
  else           { col='var(--bad)';  hintText=`✗ Too long — cut ${n-MAX} chars (${n}/160)`; }
  bar.style.background = col;
  cnt.textContent = `${n} / 160`; cnt.style.color = col;
  hint.textContent = hintText; hint.style.color = col;
  updateGooglePreview();
}

function updateGooglePreview() {
  let title = document.getElementById('ai-seo-title').value.trim() || 'SEO Title will appear here';
  let meta  = document.getElementById('ai-meta').value.trim()      || 'Meta description will appear here…';
  if (title.length > 60) title = title.slice(0,57) + '…';
  if (meta.length  > 160) meta  = meta.slice(0,157) + '…';
  document.getElementById('gp-title').textContent = title;
  document.getElementById('gp-meta').textContent  = meta;
}

function renderVariants(containerId, items, maxChars, onClickFn) {
  const wrap = document.getElementById(containerId);
  wrap.innerHTML = '';
  (items||[]).slice(0,3).forEach((v, i) => {
    v = (v||'').trim(); if (!v) return;
    const n = v.length; const cls = n <= maxChars ? 'av-ok' : 'av-warn';
    const div = document.createElement('div');
    div.className = 'ai-variant-row';
    div.innerHTML = `<span class="av-num">${i+1}.</span><span class="av-text">${esc(v.length>130?v.slice(0,130)+'…':v)}</span><span class="av-count ${cls}">${n}/${maxChars}</span>`;
    div.addEventListener('click', () => onClickFn(v));
    wrap.appendChild(div);
  });
}
function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

// ════════════════════ IMAGE SEO TAB ═════════════════════════════

function triggerUpload() { document.getElementById('img-file-input').click(); }

function onFileSelected(input) {
  const file = input.files[0];
  if (!file) return;
  loadImageFile(file);
}

function loadImageFile(file) {
  _origFile = file;
  const url = URL.createObjectURL(file);
  const img = new Image();
  img.onload = () => {
    _origImage   = img;
    _croppedBlob = null;
    _zoomFactor  = 1.0;
    document.getElementById('zoom-slider').value = 100;
    _imageOffsetX = _imageOffsetY = 0;
    _previewCache = null;
    resetCrop();
    requestRedraw(30);
    document.getElementById('canvas-hint').style.display = 'none';
    document.getElementById('crop-info').textContent = `Loaded: ${file.name}  •  ${img.naturalWidth}×${img.naturalHeight}px`;
    setStatus('Image loaded');
  };
  img.src = url;
}

function onCanvasDrop(e) {
  const file = e.dataTransfer.files[0];
  if (file && /\.(png|jpg|jpeg|webp|bmp)$/i.test(file.name)) loadImageFile(file);
}

function setPreset(w, h) {
  _currentRatio = w / Math.max(h, 1);
  resetCrop(); requestRedraw(10);
  setStatus(`Crop preset: ${w}×${h}`);
}

function onZoom(val) {
  _zoomFactor = parseFloat(val) / 100;
  requestRedraw(5);
}

// ── Canvas resize ──────────────────────────────────────────────
function resizeCanvas() {
  const wrap = document.getElementById('canvas-wrap');
  const canvas = document.getElementById('crop-canvas');
  canvas.width  = wrap.clientWidth  || 800;
  canvas.height = wrap.clientHeight || 460;
}

// ── Crop reset ─────────────────────────────────────────────────
function resetCrop() {
  const canvas = document.getElementById('crop-canvas');
  const cw = canvas.width || 800, ch = canvas.height || 460;
  const r = _currentRatio;
  let tw = Math.min(cw-100, Math.max(320, cw*0.72));
  let th = tw / r;
  if (th > ch - 100) { th = ch - 100; tw = th * r; }
  const x1 = (cw - tw) / 2, y1 = (ch - th) / 2;
  _cropRect = [x1, y1, x1+tw, y1+th];
}

// ── Redraw ─────────────────────────────────────────────────────
function requestRedraw(delay=10) {
  if (_redrawId) clearTimeout(_redrawId);
  _redrawId = setTimeout(redraw, delay);
}

function redraw() {
  _redrawId = null;
  const canvas = document.getElementById('crop-canvas');
  const ctx = canvas.getContext('2d');
  const cw = canvas.width, ch = canvas.height;
  ctx.clearRect(0, 0, cw, ch);
  if (!_origImage) return;

  const iw = _origImage.naturalWidth, ih = _origImage.naturalHeight;
  _baseScale   = Math.min(cw/Math.max(iw,1), ch/Math.max(ih,1));
  _displayScale = _baseScale * _zoomFactor;
  _displayW    = Math.max(1, Math.round(iw * _displayScale));
  _displayH    = Math.max(1, Math.round(ih * _displayScale));

  const csz = [cw, ch];
  if ((_imageOffsetX === 0 && _imageOffsetY === 0) ||
      (_lastCanvasSize[0] !== csz[0] || _lastCanvasSize[1] !== csz[1])) {
    _imageOffsetX = (cw - _displayW) / 2;
    _imageOffsetY = (ch - _displayH) / 2;
    _lastCanvasSize = csz;
  }

  // Draw image
  ctx.drawImage(_origImage, _imageOffsetX, _imageOffsetY, _displayW, _displayH);
  drawOverlay(ctx, cw, ch);
}

function drawOverlay(ctx, cw, ch) {
  const [x1,y1,x2,y2] = _cropRect;
  // Dim outside crop
  ctx.fillStyle = 'rgba(0,0,0,0.5)';
  ctx.fillRect(0,0,cw,y1);
  ctx.fillRect(0,y2,cw,ch-y2);
  ctx.fillRect(0,y1,x1,y2-y1);
  ctx.fillRect(x2,y1,cw-x2,y2-y1);
  // Crop border
  ctx.strokeStyle = '#5eead4'; ctx.lineWidth = 2;
  ctx.strokeRect(x1, y1, x2-x1, y2-y1);
  // Safe zone
  if (document.getElementById('safe-zone').checked) {
    const mx = (x2-x1)*0.08, my = (y2-y1)*0.08;
    ctx.strokeStyle = '#f59e0b'; ctx.lineWidth = 1;
    ctx.setLineDash([4,4]);
    ctx.strokeRect(x1+mx, y1+my, (x2-x1)-2*mx, (y2-y1)-2*my);
    ctx.setLineDash([]);
  }
  // Handles
  const s = _handleSize / 2;
  for (const [hx,hy] of getHandles()) {
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(hx-s, hy-s, _handleSize, _handleSize);
    ctx.strokeStyle = '#1e40af'; ctx.lineWidth = 1;
    ctx.strokeRect(hx-s, hy-s, _handleSize, _handleSize);
  }
}

function getHandles() {
  const [x1,y1,x2,y2] = _cropRect;
  const mx=(x1+x2)/2, my=(y1+y2)/2;
  return [[x1,y1],[mx,y1],[x2,y1],[x1,my],[x2,my],[x1,y2],[mx,y2],[x2,y2]];
}
const HANDLE_LABELS = ['nw','n','ne','w','e','sw','s','se'];

function detectHandle(x, y) {
  const handles = getHandles();
  for (let i=0; i<handles.length; i++) {
    const [hx,hy] = handles[i];
    if (Math.abs(x-hx) <= _handleSize && Math.abs(y-hy) <= _handleSize) return HANDLE_LABELS[i];
  }
  return null;
}
function inCrop(x,y)  { const [x1,y1,x2,y2]=_cropRect; return x>=x1&&x<=x2&&y>=y1&&y<=y2; }
function inImage(x,y) { return x>=_imageOffsetX&&x<=_imageOffsetX+_displayW&&y>=_imageOffsetY&&y<=_imageOffsetY+_displayH; }

function canvasPress(e) {
  const [x,y] = canvasXY(e);
  _resizingHandle = detectHandle(x, y);
  _cropDragStart  = [x, y];
  _startCropRect  = [..._cropRect];
  _startOffset    = [_imageOffsetX, _imageOffsetY];
  if (_resizingHandle) { _draggingCrop=true; _draggingImage=false; }
  else if (inCrop(x,y)) { _draggingCrop=true; _draggingImage=false; }
  else if (inImage(x,y)) { _draggingImage=true; _draggingCrop=false; }
  else { _draggingCrop=false; _draggingImage=false; }
}

function canvasDrag(e) {
  if (!_draggingCrop && !_draggingImage) return;
  const [x,y] = canvasXY(e);
  const dx=x-_cropDragStart[0], dy=y-_cropDragStart[1];
  if (_draggingImage) {
    _imageOffsetX = _startOffset[0]+dx; _imageOffsetY = _startOffset[1]+dy;
    requestRedraw(5); return;
  }
  if (_draggingCrop) {
    if (_resizingHandle) {
      doResize(_resizingHandle, dx, dy);
    } else {
      let [x1,y1,x2,y2] = _startCropRect; const w=x2-x1,h=y2-y1;
      _cropRect = [x1+dx, y1+dy, x1+dx+w, y1+dy+h]; clampCrop();
    }
    requestRedraw(5);
  }
}

function canvasRelease() { _draggingCrop=false; _draggingImage=false; _resizingHandle=null; }

function canvasWheel(e) {
  e.preventDefault();
  const delta = e.deltaY < 0 ? 0.08 : -0.08;
  const v = Math.min(3.0, Math.max(0.5, _zoomFactor+delta));
  if (Math.abs(v-_zoomFactor) < 0.0001) return;
  _zoomFactor = v;
  document.getElementById('zoom-slider').value = Math.round(v*100);
  requestRedraw(5);
}

function canvasXY(e) {
  const canvas = document.getElementById('crop-canvas');
  const rect = canvas.getBoundingClientRect();
  return [e.clientX - rect.left, e.clientY - rect.top];
}

function doResize(handle, dx, dy) {
  let [x1,y1,x2,y2] = _startCropRect;
  if (handle.includes('w')) x1+=dx;
  if (handle.includes('e')) x2+=dx;
  if (handle.includes('n')) y1+=dy;
  if (handle.includes('s')) y2+=dy;
  if (document.getElementById('lock-ratio').checked) {
    const r=_currentRatio, w=Math.max(80,x2-x1), h=Math.max(50,y2-y1);
    if (Math.abs(dx)>=Math.abs(dy)) {
      const nh=w/r;
      y1 = (handle.includes('n') && !handle.includes('s')) ? y2-nh : y1;
      y2 = y1+nh;
    } else {
      const nw=h*r;
      x1 = (handle.includes('w') && !handle.includes('e')) ? x2-nw : x1;
      x2 = x1+nw;
    }
  }
  _cropRect = [x1,y1,x2,y2]; clampCrop();
}

function clampCrop() {
  const canvas = document.getElementById('crop-canvas');
  const cw=canvas.width, ch=canvas.height;
  let [x1,y1,x2,y2] = _cropRect;
  const mw=80, mh=50;
  x1=Math.max(0,Math.min(cw-mw,x1)); y1=Math.max(0,Math.min(ch-mh,y1));
  x2=Math.max(x1+mw,Math.min(cw,x2)); y2=Math.max(y1+mh,Math.min(ch,y2));
  _cropRect=[x1,y1,x2,y2];
}

function applyCrop() {
  if (!_origImage) { setStatus('Upload an image first'); return; }
  const canvas = document.getElementById('crop-canvas');
  const [x1,y1,x2,y2] = _cropRect;
  const left   = Math.max(0, Math.round((x1-_imageOffsetX)/_displayScale));
  const top    = Math.max(0, Math.round((y1-_imageOffsetY)/_displayScale));
  const right  = Math.max(left+1, Math.round((x2-_imageOffsetX)/_displayScale));
  const bottom = Math.max(top+1, Math.round((y2-_imageOffsetY)/_displayScale));

  // Draw cropped onto offscreen canvas
  const oc = document.createElement('canvas');
  oc.width  = right-left; oc.height = bottom-top;
  oc.getContext('2d').drawImage(_origImage, left, top, oc.width, oc.height, 0, 0, oc.width, oc.height);
  oc.toBlob(blob => {
    _croppedBlob = blob;
    setStatus(`Crop applied: ${oc.width}×${oc.height}px`);
  }, 'image/jpeg', 0.95);
}

function clearCrop() {
  _croppedBlob = null;
  if (_origImage) { resetCrop(); requestRedraw(10); }
  setStatus('Crop cleared');
}

async function exportUnder100kb() {
  if (!_origImage && !_croppedBlob) { setStatus('Upload or crop an image first'); return; }
  showSpinner('Optimizing image to <100KB…');
  const formData = new FormData();
  const sourceFile = _croppedBlob ? new File([_croppedBlob],'crop.jpg',{type:'image/jpeg'}) : _origFile;
  formData.append('image', sourceFile);
  try {
    const r = await fetch('/api/export-image', { method:'POST', body: formData });
    if (!r.ok) { const d=await r.json(); throw new Error(d.error||'Export failed'); }
    const sizeKb  = r.headers.get('X-Image-Size-KB') || '?';
    const quality = r.headers.get('X-Image-Quality') || '?';
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'optimized.jpg'; a.click();
    URL.revokeObjectURL(url);
    setStatus(`Saved ${sizeKb}KB  quality=${quality}`);
  } catch(e) {
    alert('Export Error\n\n' + e.message);
  } finally { hideSpinner(); }
}

async function generateImageSeo() {
  const activeBlob = _croppedBlob || (_origFile ? _origFile : null);
  if (!activeBlob) { setStatus('Upload an image first'); return; }
  if (!_apiKey) {
    alert('Together AI Not Ready\n\nNo API key loaded.\nOpen API Settings → paste key → Test → Save & Use.');
    openApiModal(); return;
  }
  const sceneNotes = document.getElementById('scene-entry').value.trim();
  const btn = document.getElementById('gen-seo-btn');
  btn.disabled = true; btn.textContent = '⏳ Generating…'; btn.style.background = '#1a3a1a';
  setStatus('Reading image & generating WordPress SEO fields…');

  const formData = new FormData();
  formData.append('image', activeBlob instanceof Blob ? new File([activeBlob],'image.jpg',{type:'image/jpeg'}) : activeBlob);
  formData.append('api_key', _apiKey);
  formData.append('scene_notes', sceneNotes);

  try {
    const r = await fetch('/api/image-seo', { method:'POST', body: formData });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'Generation failed');
    document.getElementById('img-alt').value         = d.alt_text  || '';
    document.getElementById('img-title-field').value = d.img_title || '';
    document.getElementById('img-caption').value     = d.caption   || '';
    setStatus(`✓ WordPress Featured Image SEO generated via ${d.model||'AI'}`);
  } catch(e) {
    setStatus('Error: ' + e.message.slice(0,100));
    alert('Image SEO Error\n\nCould not generate WordPress image SEO.\n\nReason:\n' + e.message);
  } finally {
    btn.disabled = false; btn.textContent = '⚡ Generate SEO'; btn.style.background = '';
  }
}

function copyImgField(field) {
  const MAP = { alt:'img-alt', title:'img-title-field', caption:'img-caption' };
  const id = MAP[field];
  const el = document.getElementById(id);
  const val = el.tagName==='TEXTAREA' ? el.value : el.value;
  if (!val.trim()) { setStatus('No ' + field + ' to copy'); return; }
  clipboard(val); setStatus('Copied ' + field);
}

function copyAllImageSeo() {
  const alt     = document.getElementById('img-alt').value.trim();
  const title   = document.getElementById('img-title-field').value.trim();
  const caption = document.getElementById('img-caption').value.trim();
  if (!alt && !title && !caption) { setStatus('No image SEO fields to copy'); return; }
  clipboard(`Alt Text:\n${alt}\n\nImage Title:\n${title}\n\nCaption:\n${caption}`);
  setStatus('Copied all image fields');
}

function clearImageFields() {
  _origImage=null; _origFile=null; _croppedBlob=null; _previewCache=null;
  document.getElementById('img-file-input').value = '';
  document.getElementById('scene-entry').value = '';
  document.getElementById('img-alt').value = '';
  document.getElementById('img-title-field').value = '';
  document.getElementById('img-caption').value = '';
  document.getElementById('canvas-hint').style.display = 'flex';
  document.getElementById('crop-info').textContent = 'No image loaded';
  _imageOffsetX=_imageOffsetY=0; _zoomFactor=1.0;
  document.getElementById('zoom-slider').value=100;
  const canvas=document.getElementById('crop-canvas');
  canvas.getContext('2d').clearRect(0,0,canvas.width,canvas.height);
  setStatus('Cleared all image SEO fields');
}
