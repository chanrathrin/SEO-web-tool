/* ═══════════════════════════════════════════════════════
   WordPress SEO Studio — Frontend JS
═══════════════════════════════════════════════════════ */

'use strict';

// ── State ──────────────────────────────────────────────
let _apiKey = localStorage.getItem('togetherApiKey') || '';
let _currentLang = 'English';
let _currentWpHtml = '';
let _selectedImageFile = null;

// ── Init ───────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  if (_apiKey) {
    updateApiBadge(true, false);
    document.getElementById('api-key-input').value = _apiKey;
  }
  setupImageDrop();
  // Live update Google preview whenever SEO title / meta changes
  document.getElementById('out-seo-title').addEventListener('input', updateGooglePreview);
  document.getElementById('out-meta').addEventListener('input', updateGooglePreview);
});

// ── Tab switching ──────────────────────────────────────
function switchTab(name, btn) {
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  btn.classList.add('active');
}

// ── API Modal ──────────────────────────────────────────
function openApiModal() {
  document.getElementById('api-modal').style.display = 'flex';
  document.getElementById('api-modal-status').textContent = '';
  document.getElementById('api-modal-status').className = 'modal-status';
  if (_apiKey) document.getElementById('api-key-input').value = _apiKey;
}
function closeApiModal() {
  document.getElementById('api-modal').style.display = 'none';
}
function toggleApiKeyVisibility() {
  const inp = document.getElementById('api-key-input');
  inp.type = inp.type === 'password' ? 'text' : 'password';
}
function modalStatus(msg, cls = 'info') {
  const el = document.getElementById('api-modal-status');
  el.textContent = msg;
  el.className = 'modal-status ' + cls;
}

async function testApiKey() {
  const key = document.getElementById('api-key-input').value.trim();
  if (!key) { modalStatus('Please paste your API key first.', 'err'); return; }
  modalStatus('⏳ Testing key…', 'info');
  try {
    const res = await fetch('/api/verify-key', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ api_key: key })
    });
    const data = await res.json();
    if (data.ok) {
      modalStatus('✓ Key is valid!', 'ok');
    } else {
      modalStatus('✗ ' + (data.error || 'Invalid key'), 'err');
    }
  } catch (e) {
    modalStatus('✗ Network error: ' + e.message, 'err');
  }
}

async function saveApiKey() {
  const key = document.getElementById('api-key-input').value.trim();
  if (!key) { modalStatus('Please paste your API key first.', 'err'); return; }
  modalStatus('⏳ Saving…', 'info');
  try {
    await fetch('/api/set-key', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ api_key: key })
    });
    _apiKey = key;
    localStorage.setItem('togetherApiKey', key);
    updateApiBadge(true, true);
    modalStatus('✓ Key saved & active', 'ok');
    setTimeout(closeApiModal, 800);
  } catch (e) {
    modalStatus('✗ ' + e.message, 'err');
  }
}

function clearApiKey() {
  _apiKey = '';
  localStorage.removeItem('togetherApiKey');
  document.getElementById('api-key-input').value = '';
  fetch('/api/set-key', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ api_key: '' }) });
  updateApiBadge(false, false);
  modalStatus('Key cleared.', 'info');
}

function updateApiBadge(hasKey, saved) {
  const badge = document.getElementById('api-badge');
  if (hasKey && saved) {
    badge.textContent = '● API key saved';
    badge.className = 'badge badge-ok';
  } else if (hasKey) {
    badge.textContent = '● Session key active';
    badge.className = 'badge badge-warn';
  } else {
    badge.textContent = '○ API not configured';
    badge.className = 'badge badge-off';
  }
}

// ── Loading overlay ────────────────────────────────────
function showLoading(msg = 'Processing…') {
  document.getElementById('loading-text').textContent = msg;
  document.getElementById('loading-overlay').style.display = 'flex';
}
function hideLoading() {
  document.getElementById('loading-overlay').style.display = 'none';
}

// ── Status bar ─────────────────────────────────────────
function setStatus(id, msg, cls = '') {
  const el = document.getElementById(id);
  el.textContent = msg;
  el.className = 'status-bar ' + cls;
}

// ── Copy helpers ───────────────────────────────────────
function copyField(id, isTextarea = false) {
  const el = document.getElementById(id);
  const val = isTextarea ? el.value : el.value;
  if (!val.trim()) return;
  navigator.clipboard.writeText(val).then(() => {
    const btn = el.nextElementSibling;
    if (btn) { const orig = btn.textContent; btn.textContent = '✓'; setTimeout(() => btn.textContent = orig, 1000); }
  });
}
function copyText(text) {
  navigator.clipboard.writeText(text);
}

// ── Character counters ─────────────────────────────────
function updateFkCounter(val) {
  const words = val.trim().split(/\s+/).filter(Boolean).length;
  const chars = val.length;
  const el = document.getElementById('fk-counter');
  if (!chars) { el.textContent = ''; el.className = 'char-counter'; return; }
  if (words <= 4) {
    el.textContent = `✓ Good (${words} words, ${chars} chars)`;
    el.className = 'char-counter ok';
  } else {
    el.textContent = `⚠ Try shorter (${words} words — Yoast recommends ≤4)`;
    el.className = 'char-counter warn';
  }
}

function updateSeoCounter(val) {
  const n = val.length, MAX = 60;
  const bar = document.getElementById('seo-bar');
  const counter = document.getElementById('seo-counter');
  const pct = Math.min(100, (n / MAX) * 100);
  bar.style.width = pct + '%';
  let color, msg;
  if (n === 0)       { color = 'var(--text-soft)'; msg = '0 / 60'; }
  else if (n < 30)   { color = 'var(--warn)';      msg = `⚠ Too short (${n}/60)`; }
  else if (n < 50)   { color = 'var(--warn)';      msg = `⚠ Could be longer (${n}/60)`; }
  else if (n <= MAX) { color = 'var(--ok)';         msg = `✓ Good length (${n}/60)`; }
  else               { color = 'var(--bad)';        msg = `✗ Too long — cut ${n - MAX} chars (${n}/60)`; }
  bar.style.background = color;
  counter.textContent = msg;
  counter.style.color = color;
  updateGooglePreview();
}

function updateMetaCounter(val) {
  const n = val.trim().length, MAX = 160;
  const bar = document.getElementById('meta-bar');
  const counter = document.getElementById('meta-counter');
  const pct = Math.min(100, (n / MAX) * 100);
  bar.style.width = pct + '%';
  let color, msg;
  if (n === 0)       { color = 'var(--text-soft)'; msg = '0 / 160'; }
  else if (n < 120)  { color = 'var(--warn)';      msg = `⚠ Too short (${n}/160)`; }
  else if (n <= 155) { color = 'var(--ok)';         msg = `✓ Good length (${n}/160)`; }
  else if (n <= MAX) { color = 'var(--ok)';         msg = `✓ Acceptable (${n}/160)`; }
  else               { color = 'var(--bad)';        msg = `✗ Too long — cut ${n - MAX} chars (${n}/160)`; }
  bar.style.background = color;
  counter.textContent = msg;
  counter.style.color = color;
  updateGooglePreview();
}

function updateAltCounter(val) {
  const n = val.length;
  const el = document.getElementById('alt-counter');
  el.textContent = `${n} / 90`;
  el.className = 'char-counter ' + (n === 0 ? '' : n <= 90 ? 'ok' : 'bad');
}

function updateTitleCounter(val) {
  const n = val.length;
  const el = document.getElementById('title-counter');
  el.textContent = `${n} / 90`;
  el.className = 'char-counter ' + (n === 0 ? '' : n <= 90 ? 'ok' : 'bad');
}

function updateCaptionCounter(val) {
  const n = val.length;
  const el = document.getElementById('caption-counter');
  el.textContent = `${n} / 180`;
  el.className = 'char-counter ' + (n === 0 ? '' : n <= 180 ? 'ok' : 'bad');
}

// ── Google preview ─────────────────────────────────────
function updateGooglePreview() {
  let title = document.getElementById('out-seo-title').value.trim() || 'SEO Title will appear here';
  let meta  = document.getElementById('out-meta').value.trim() || 'Meta description will appear here…';
  if (title.length > 60) title = title.slice(0, 57) + '…';
  if (meta.length > 160)  meta  = meta.slice(0, 157) + '…';
  document.getElementById('gp-title').textContent = title;
  document.getElementById('gp-meta').textContent  = meta;
}

// ── Variants ───────────────────────────────────────────
function renderVariants(containerId, items, maxChars, onClickFn) {
  const wrap = document.getElementById(containerId);
  wrap.innerHTML = '';
  (items || []).slice(0, 4).forEach((v, i) => {
    v = (v || '').trim();
    if (!v) return;
    const n = v.length;
    const cls = n <= maxChars ? 'ok' : 'warn';
    const div = document.createElement('div');
    div.className = 'variant-item';
    div.innerHTML = `
      <span class="variant-num">${i+1}.</span>
      <span class="variant-text">${escHtml(v.length > 100 ? v.slice(0, 100) + '…' : v)}</span>
      <span class="variant-count ${cls}">${n}/${maxChars}</span>`;
    div.addEventListener('click', () => onClickFn(v));
    wrap.appendChild(div);
  });
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Populate SEO fields ────────────────────────────────
function populateSeoFields(data) {
  const set = (id, val) => { const el = document.getElementById(id); if (el) el.value = val || ''; };
  set('out-keyphrase',  data.focus_keyphrase || '');
  set('out-seo-title',  (data.seo_title_options || [])[0] || data.seo_title || '');
  set('out-meta',       (data.meta_options || [])[0] || data.meta_description || '');
  set('out-slug',       data.slug || '');

  updateFkCounter(document.getElementById('out-keyphrase').value);
  updateSeoCounter(document.getElementById('out-seo-title').value);
  updateMetaCounter(document.getElementById('out-meta').value);
  updateGooglePreview();

  const seoVariants = data.seo_title_options || data.seo_title_variants || [];
  const metaVariants = data.meta_options || data.meta_variants || [];

  renderVariants('seo-variants', seoVariants, 60, val => {
    document.getElementById('out-seo-title').value = val;
    updateSeoCounter(val);
  });
  renderVariants('meta-variants', metaVariants, 160, val => {
    document.getElementById('out-meta').value = val;
    updateMetaCounter(val);
  });

  if (data.wp_html) {
    _currentWpHtml = data.wp_html;
    document.getElementById('out-wp-html').value = data.wp_html;
  }

  if (data.language) {
    _currentLang = data.language;
    const badge = document.getElementById('lang-badge');
    badge.textContent = '🌐 ' + data.language;
  }
}

// ── Fetch URL ──────────────────────────────────────────
async function fetchUrl() {
  const url = document.getElementById('url-input').value.trim();
  if (!url) { setStatus('seo-status', 'Please paste a URL first', 'err'); return; }
  const btn = document.getElementById('fetch-btn');
  btn.disabled = true; btn.textContent = '⏳ Fetching…';
  setStatus('seo-status', 'Fetching: ' + url.slice(0, 60) + '…');
  try {
    const res = await fetch('/api/fetch-url', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ url })
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || 'Fetch failed');
    document.getElementById('article-input').value = data.html;
    _currentLang = data.language || 'English';
    document.getElementById('lang-badge').textContent = '🌐 ' + _currentLang;
    setStatus('seo-status', `Fetched ${data.html.length.toLocaleString()} chars | 🌐 ${_currentLang} — generating SEO…`);
    btn.textContent = '⬇ Fetch & Generate';
    btn.disabled = false;
    await processArticle();
  } catch (e) {
    setStatus('seo-status', '✗ Fetch failed: ' + e.message, 'err');
    btn.textContent = '⬇ Fetch & Generate';
    btn.disabled = false;
  }
}

// ── Process article ────────────────────────────────────
async function processArticle() {
  const raw = document.getElementById('article-input').value.trim();
  if (!raw) { setStatus('seo-status', 'Please paste an article first', 'err'); return; }
  showLoading('Generating SEO output…');
  setStatus('seo-status', 'Processing…');
  try {
    const res = await fetch('/api/process-article', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ text: raw })
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || 'Processing failed');
    populateSeoFields(data);
    setStatus('seo-status', `✓ SEO output generated | ${data.language || ''}`, 'ok');
  } catch (e) {
    setStatus('seo-status', '✗ Error: ' + e.message, 'err');
  } finally {
    hideLoading();
  }
}

// ── AI SEO fields ──────────────────────────────────────
async function generateAiFields() {
  const raw = document.getElementById('article-input').value.trim();
  if (!raw) { setStatus('seo-status', 'Please paste an article first', 'err'); return; }
  if (!_apiKey) {
    openApiModal();
    document.getElementById('api-modal-status').textContent = 'Set your API key to use AI features';
    document.getElementById('api-modal-status').className = 'modal-status err';
    return;
  }
  const btn = document.getElementById('ai-gen-btn');
  btn.disabled = true; btn.textContent = '⏳ Generating…';
  showLoading('Calling AI to generate Yoast fields…');
  setStatus('seo-status', '⏳ AI generating SEO fields…');
  try {
    const res = await fetch('/api/ai-seo-fields', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ text: raw, api_key: _apiKey, language: _currentLang })
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || 'AI generation failed');

    // Merge AI fields into current display
    if (data.focus_keyphrase) {
      document.getElementById('out-keyphrase').value = data.focus_keyphrase;
      updateFkCounter(data.focus_keyphrase);
    }
    if (data.seo_title) {
      document.getElementById('out-seo-title').value = data.seo_title;
      updateSeoCounter(data.seo_title);
    }
    if (data.meta_description) {
      document.getElementById('out-meta').value = data.meta_description;
      updateMetaCounter(data.meta_description);
    }

    const seoVariants = [data.seo_title, ...(data.seo_title_variants || [])].filter(Boolean);
    const metaVariants = [data.meta_description, ...(data.meta_variants || [])].filter(Boolean);

    renderVariants('seo-variants', seoVariants, 60, val => {
      document.getElementById('out-seo-title').value = val;
      updateSeoCounter(val);
    });
    renderVariants('meta-variants', metaVariants, 160, val => {
      document.getElementById('out-meta').value = val;
      updateMetaCounter(val);
    });
    updateGooglePreview();
    setStatus('seo-status', '✓ AI SEO fields generated successfully', 'ok');
  } catch (e) {
    setStatus('seo-status', '✗ AI Error: ' + e.message, 'err');
  } finally {
    hideLoading();
    btn.disabled = false;
    btn.textContent = '🤖 AI SEO Fields';
  }
}

// ── Copy WP HTML ───────────────────────────────────────
function copyWpHtml() {
  const val = document.getElementById('out-wp-html').value;
  if (!val.trim()) { setStatus('seo-status', 'Generate SEO first', 'err'); return; }
  navigator.clipboard.writeText(val).then(() => setStatus('seo-status', '✓ WordPress HTML copied to clipboard', 'ok'));
}

function clearInput() {
  document.getElementById('article-input').value = '';
  document.getElementById('url-input').value = '';
  setStatus('seo-status', 'Input cleared');
}

function clearOutput() {
  ['out-keyphrase','out-seo-title','out-meta','out-slug','out-wp-html'].forEach(id => {
    document.getElementById(id).value = '';
  });
  document.getElementById('seo-variants').innerHTML = '';
  document.getElementById('meta-variants').innerHTML = '';
  document.getElementById('gp-title').textContent = 'SEO Title will appear here';
  document.getElementById('gp-meta').textContent = 'Meta description will appear here…';
  document.getElementById('seo-counter').textContent = '0 / 60';
  document.getElementById('meta-counter').textContent = '0 / 160';
  document.getElementById('seo-bar').style.width = '0%';
  document.getElementById('meta-bar').style.width = '0%';
  setStatus('seo-status', 'Output cleared');
}

// ── IMAGE TAB ──────────────────────────────────────────
function setupImageDrop() {
  const zone = document.getElementById('drop-zone');
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith('image/')) loadImagePreview(file);
  });
}

function handleImageFile(input) {
  const file = input.files[0];
  if (file) loadImagePreview(file);
}

function loadImagePreview(file) {
  _selectedImageFile = file;
  const url = URL.createObjectURL(file);
  const img = document.getElementById('image-preview');
  img.src = url;
  document.getElementById('image-preview-wrap').style.display = 'block';
  document.getElementById('img-info').textContent = `${file.name} — ${(file.size / 1024).toFixed(1)} KB`;
  setStatus('img-status', 'Image loaded: ' + file.name);
}

async function analyzeImage() {
  if (!_selectedImageFile) { setStatus('img-status', 'Please upload an image first', 'err'); return; }
  if (!_apiKey) {
    openApiModal();
    document.getElementById('api-modal-status').textContent = 'Set your API key to use AI analysis';
    document.getElementById('api-modal-status').className = 'modal-status err';
    return;
  }
  const btn = document.getElementById('analyze-btn');
  btn.disabled = true; btn.textContent = '⏳ Analyzing…';
  showLoading('AI analyzing image…');
  setStatus('img-status', '⏳ Sending image to AI…');

  const formData = new FormData();
  formData.append('image', _selectedImageFile);
  formData.append('api_key', _apiKey);
  formData.append('scene_notes', document.getElementById('scene-notes').value.trim());

  try {
    const res = await fetch('/api/image-seo', { method: 'POST', body: formData });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || 'Analysis failed');

    document.getElementById('img-alt').value = data.alt_text || '';
    document.getElementById('img-title').value = data.image_title || '';
    document.getElementById('img-caption').value = data.caption || '';

    updateAltCounter(data.alt_text || '');
    updateTitleCounter(data.image_title || '');
    updateCaptionCounter(data.caption || '');

    updateAllImageOutput();
    setStatus('img-status', '✓ Image SEO fields generated by AI', 'ok');
  } catch (e) {
    setStatus('img-status', '✗ Error: ' + e.message, 'err');
  } finally {
    hideLoading();
    btn.disabled = false;
    btn.textContent = '🤖 Analyze Image with AI';
  }
}

function updateAllImageOutput() {
  const alt  = document.getElementById('img-alt').value.trim();
  const title = document.getElementById('img-title').value.trim();
  const cap  = document.getElementById('img-caption').value.trim();
  document.getElementById('img-all-output').value =
    `Alt Text:\n${alt}\n\nImage Title:\n${title}\n\nCaption:\n${cap}`;
}

// Listen for manual edits to image fields
['img-alt','img-title','img-caption'].forEach(id => {
  document.addEventListener('DOMContentLoaded', () => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('input', updateAllImageOutput);
  });
});

function copyAllImageFields() {
  const val = document.getElementById('img-all-output').value;
  if (!val.trim()) { setStatus('img-status', 'Analyze an image first', 'err'); return; }
  navigator.clipboard.writeText(val).then(() => setStatus('img-status', '✓ All image fields copied', 'ok'));
}

function clearImageFields() {
  _selectedImageFile = null;
  document.getElementById('image-file-input').value = '';
  document.getElementById('image-preview-wrap').style.display = 'none';
  document.getElementById('scene-notes').value = '';
  ['img-alt','img-title','img-caption','img-all-output'].forEach(id => {
    document.getElementById(id).value = '';
  });
  ['alt-counter','title-counter','caption-counter'].forEach(id => {
    document.getElementById(id).textContent = '0 / ' + (id === 'caption-counter' ? '180' : '90');
    document.getElementById(id).className = 'char-counter';
  });
  setStatus('img-status', 'Cleared');
}
