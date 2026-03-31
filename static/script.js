/* ════════════════════════════════════════════════════
   WordPress SEO Studio — Frontend JS
   Tab 1: SEO Formatter  (calls /api/seo-format)
   Tab 2: Image SEO      (calls /api/image-seo)
════════════════════════════════════════════════════ */

'use strict';

/* ── Helpers ─────────────────────────────────────────── */
const $  = id => document.getElementById(id);
const qs = sel => document.querySelector(sel);

function setStatus(msg) {
  $('statusBar').textContent = msg;
}

function toast(msg, ms = 2200) {
  const el = $('toast');
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove('show'), ms);
}

function copyText(text, label = '') {
  if (!text || !text.trim()) { toast('Nothing to copy'); return; }
  navigator.clipboard.writeText(text).then(() => {
    toast(label ? `Copied: ${label}` : 'Copied!');
  }).catch(() => {
    // Fallback
    const ta = document.createElement('textarea');
    ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    toast(label ? `Copied: ${label}` : 'Copied!');
  });
}

/* ── Tab switching ───────────────────────────────────── */
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    $('tab-' + btn.dataset.tab).classList.add('active');
  });
});

/* ══════════════════════════════════════════════════════
   TAB 1 — SEO FORMATTER
══════════════════════════════════════════════════════ */

let seoData = null;  // last API result

/* Quick-copy pills */
document.querySelectorAll('.pill[data-copy]').forEach(btn => {
  btn.addEventListener('click', () => {
    if (!seoData) { toast('Generate first'); return; }
    const key = btn.dataset.copy;
    const val = seoData[key] || '';
    copyText(val, btn.textContent.trim());
  });
});

/* Generate SEO */
$('btnGenerate').addEventListener('click', generateSEO);

async function generateSEO() {
  const raw = $('inputArticle').value.trim();
  if (!raw) { toast('Paste an article first'); return; }

  const btn = $('btnGenerate');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Generating…';
  setStatus('Processing article…');

  try {
    const res  = await fetch('/api/seo-format', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: raw }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Server error');
    seoData = data;
    renderSEOOutput(data);
    setStatus('SEO output generated ✓');
  } catch (e) {
    toast('Error: ' + e.message, 3500);
    setStatus('Error: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '⚡ Generate SEO';
  }
}

function renderSEOOutput(d) {
  /* Article preview */
  const out = $('outputArticle');
  let html = '';
  if (d.h1) {
    html += `<div class="out-h1-lbl">H1</div><div class="out-h1">${esc(d.h1)}</div>`;
  }
  if (d.intro) {
    html += `<p class="out-intro">${esc(d.intro)}</p>`;
  }
  (d.struct || []).forEach(sec => {
    if (sec.h2) html += `<div class="out-h2-lbl">H2</div><div class="out-h2">${esc(sec.h2)}</div>`;
    (sec.subsections || []).forEach(sub => {
      if (sub.h3) html += `<div class="out-h3-lbl">H3</div><div class="out-h3">${esc(sub.h3)}</div>`;
      if (sub.body) {
        sub.body.split('\n\n').forEach(chunk => {
          chunk = chunk.trim();
          if (chunk) html += `<p class="out-body">${esc(chunk)}</p>`;
        });
      }
    });
  });
  out.innerHTML = html || '<p class="placeholder-msg">No content parsed.</p>';

  /* Options boxes */
  $('optTitles').textContent  = 'SEO Title Options\n\n' + (d.seo_titles || [d.seo_title]).join('\n');
  $('optMeta').textContent    =
    'Meta + SEO Fields\n\n' +
    `Focus Keyphrase: ${d.focus_keyphrase}\n` +
    `SEO Title: ${d.seo_title}\n` +
    `Meta Description: ${d.meta}\n` +
    `Slug (URL): ${d.slug}\n` +
    `Short Summary: ${d.short_summary}`;
  $('optCaption').textContent  = 'Short Caption (H1·H2·H3)\n\n' + d.short_caption;
  $('optHashtags').textContent = 'Hashtags\n\n' + (d.hashtags || []).join('  ');
}

function esc(str) {
  return String(str)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

/* Copy WP HTML */
$('btnCopyHTML').addEventListener('click', () => {
  if (!seoData) { toast('Generate first'); return; }
  const html = buildWpHtml(seoData);
  copyText(html, 'WordPress HTML');
});

function buildWpHtml(d) {
  const H1_S = 'font-family:Arial,sans-serif;font-size:clamp(28px,5vw,46px);font-weight:800;color:#1a1a1a;margin:0 0 18px 0;line-height:1.25;';
  const INS  = 'font-size:clamp(16px,3.5vw,20px);line-height:1.75;color:#444;margin:0 0 24px 0;font-style:italic;';
  const H2_S = 'font-family:Arial,sans-serif;font-size:clamp(22px,4vw,34px);font-weight:800;color:#222;margin:32px 0 12px 0;';
  const H3_S = 'font-family:Arial,sans-serif;font-size:clamp(18px,3.2vw,26px);font-weight:700;color:#333;margin:22px 0 8px 0;';
  const P_S  = 'font-size:clamp(15px,3vw,19px);line-height:1.80;color:#444;margin:0 0 20px 0;';

  let parts = [];
  if (d.h1)    parts.push(`<h1 style="${H1_S}">${htmlEsc(d.h1)}</h1>`);
  if (d.intro) parts.push(`<p style="${INS}">${htmlEsc(d.intro)}</p>`);

  (d.struct || []).forEach(sec => {
    if (sec.h2) parts.push(`<h2 style="${H2_S}">${htmlEsc(sec.h2)}</h2>`);
    (sec.subsections || []).forEach(sub => {
      if (sub.h3) parts.push(`<h3 style="${H3_S}">${htmlEsc(sub.h3)}</h3>`);
      (sub.body || '').split('\n\n').forEach(chunk => {
        chunk = chunk.trim();
        if (chunk) parts.push(`<p style="${P_S}">${htmlEsc(chunk).replace(/\n/g,'<br>')}</p>`);
      });
    });
  });

  return `<div style="max-width:760px;margin:0 auto;padding:0 12px;font-family:Georgia,'Times New Roman',serif;color:#222;">\n${parts.join('\n')}\n</div>`;
}

function htmlEsc(str) {
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

/* Clear buttons */
$('btnClearIn').addEventListener('click', () => {
  $('inputArticle').value = '';
  setStatus('Input cleared');
});
$('btnClearOut').addEventListener('click', () => {
  $('outputArticle').innerHTML = '<p class="placeholder-msg">Your formatted output will appear here after generation.</p>';
  $('optTitles').textContent = '';
  $('optMeta').textContent   = '';
  $('optCaption').textContent = '';
  $('optHashtags').textContent = '';
  seoData = null;
  setStatus('Output cleared');
});

/* ══════════════════════════════════════════════════════
   TAB 2 — IMAGE SEO
══════════════════════════════════════════════════════ */

/* ── State ─────────────────────────────────────────── */
const state = {
  originalImg: null,   // HTMLImageElement
  originalFile: null,  // File
  croppedBlob: null,   // Blob
  ratio: 1200 / 366,
  zoom: 1.0,
  offsetX: 0, offsetY: 0,
  crop: { x:0, y:0, w:0, h:0 },
  drag: null,          // {type, startX, startY, startCrop, startOffset}
  imageW: 0, imageH: 0,   // displayed image dimensions
};

const canvas = $('cropCanvas');
const ctx    = canvas.getContext('2d');

function resizeCanvas() {
  const wrap = $('canvasWrap');
  canvas.width  = wrap.clientWidth;
  canvas.height = wrap.clientHeight;
  if (state.originalImg) { layoutImage(); drawAll(); }
}
new ResizeObserver(resizeCanvas).observe($('canvasWrap'));

/* ── Upload ──────────────────────────────────────────── */
$('btnUpload').addEventListener('click', () => $('fileInput').click());
$('fileInput').addEventListener('change', e => {
  const f = e.target.files[0];
  if (!f) return;
  state.originalFile  = f;
  state.croppedBlob   = null;
  const url = URL.createObjectURL(f);
  const img = new Image();
  img.onload = () => {
    state.originalImg = img;
    $('canvasPlaceholder').style.display = 'none';
    state.zoom = 1.0;
    $('zoomSlider').value = 100;
    layoutImage();
    resetCrop();
    drawAll();
    $('cropInfo').textContent = `Loaded: ${f.name}  •  ${img.naturalWidth}×${img.naturalHeight}px`;
    setStatus('Image loaded');
  };
  img.src = url;
  e.target.value = '';
});

function layoutImage() {
  const cw = canvas.width, ch = canvas.height;
  const iw = state.originalImg.naturalWidth;
  const ih = state.originalImg.naturalHeight;
  const base = Math.min(cw / iw, ch / ih);
  const scale = base * state.zoom;
  state.imageW = iw * scale;
  state.imageH = ih * scale;
  state.offsetX = (cw - state.imageW) / 2;
  state.offsetY = (ch - state.imageH) / 2;
}

function resetCrop() {
  const cw = canvas.width, ch = canvas.height;
  const r  = state.ratio;
  let tw = Math.min(cw - 80, Math.max(280, cw * 0.72));
  let th = tw / r;
  if (th > ch - 80) { th = ch - 80; tw = th * r; }
  state.crop = {
    x: (cw - tw) / 2, y: (ch - th) / 2,
    w: tw, h: th,
  };
}

/* ── Draw ─────────────────────────────────────────────── */
function drawAll() {
  if (!state.originalImg) return;
  const cw = canvas.width, ch = canvas.height;
  ctx.clearRect(0, 0, cw, ch);

  /* image */
  ctx.drawImage(state.originalImg, state.offsetX, state.offsetY, state.imageW, state.imageH);

  /* dim overlay */
  const { x, y, w, h } = state.crop;
  ctx.fillStyle = 'rgba(0,0,0,0.52)';
  ctx.fillRect(0,  0,  cw, y);
  ctx.fillRect(0,  y+h, cw, ch - y - h);
  ctx.fillRect(0,  y,   x,  h);
  ctx.fillRect(x+w, y,  cw - x - w, h);

  /* crop border */
  ctx.strokeStyle = '#5eead4';
  ctx.lineWidth   = 2;
  ctx.strokeRect(x, y, w, h);

  /* safe zone */
  if ($('safeZone').checked) {
    const mx = w * 0.08, my = h * 0.08;
    ctx.strokeStyle = '#f59e0b';
    ctx.lineWidth   = 1;
    ctx.setLineDash([4, 4]);
    ctx.strokeRect(x + mx, y + my, w - 2*mx, h - 2*my);
    ctx.setLineDash([]);
  }

  /* handles */
  handles().forEach(([hx, hy]) => {
    ctx.fillStyle   = '#fff';
    ctx.strokeStyle = '#1e40af';
    ctx.lineWidth   = 1.5;
    ctx.fillRect(hx - 5, hy - 5, 10, 10);
    ctx.strokeRect(hx - 5, hy - 5, 10, 10);
  });
}

function handles() {
  const { x, y, w, h } = state.crop;
  const mx = x + w/2, my = y + h/2;
  return [[x,y],[mx,y],[x+w,y],[x,my],[x+w,my],[x,y+h],[mx,y+h],[x+w,y+h]];
}

function detectHandle(px, py) {
  const labels = ['nw','n','ne','w','e','sw','s','se'];
  for (let i = 0; i < 8; i++) {
    const [hx, hy] = handles()[i];
    if (Math.abs(px - hx) <= 8 && Math.abs(py - hy) <= 8) return labels[i];
  }
  return null;
}

function inCrop(px, py) {
  const { x, y, w, h } = state.crop;
  return px >= x && px <= x+w && py >= y && py <= y+h;
}

function inImage(px, py) {
  return px >= state.offsetX && px <= state.offsetX + state.imageW &&
         py >= state.offsetY && py <= state.offsetY + state.imageH;
}

/* ── Mouse events ─────────────────────────────────────── */
canvas.addEventListener('mousedown', e => {
  const { offsetX: px, offsetY: py } = e;
  const handle = detectHandle(px, py);
  state.drag = {
    type: handle ? 'resize' : (inCrop(px, py) ? 'move' : (inImage(px, py) ? 'pan' : null)),
    handle,
    startX: px, startY: py,
    startCrop: { ...state.crop },
    startOffset: { x: state.offsetX, y: state.offsetY },
  };
});

canvas.addEventListener('mousemove', e => {
  if (!state.drag || !state.drag.type) return;
  const dx = e.offsetX - state.drag.startX;
  const dy = e.offsetY - state.drag.startY;

  if (state.drag.type === 'pan') {
    state.offsetX = state.drag.startOffset.x + dx;
    state.offsetY = state.drag.startOffset.y + dy;
    drawAll(); return;
  }
  if (state.drag.type === 'move') {
    const { w, h } = state.drag.startCrop;
    state.crop.x = state.drag.startCrop.x + dx;
    state.crop.y = state.drag.startCrop.y + dy;
    state.crop.w = w; state.crop.h = h;
    clampCrop(); drawAll(); return;
  }
  if (state.drag.type === 'resize') {
    resizeCrop(state.drag.handle, dx, dy);
    clampCrop(); drawAll();
  }
});

canvas.addEventListener('mouseup',    () => { state.drag = null; });
canvas.addEventListener('mouseleave', () => { state.drag = null; });

canvas.addEventListener('wheel', e => {
  e.preventDefault();
  state.zoom = Math.min(3.0, Math.max(0.5, state.zoom + (e.deltaY < 0 ? 0.08 : -0.08)));
  $('zoomSlider').value = Math.round(state.zoom * 100);
  layoutImage(); drawAll();
}, { passive: false });

/* Touch support */
let lastTouch = null;
canvas.addEventListener('touchstart', e => {
  if (e.touches.length === 1) {
    const t = e.touches[0];
    const rect = canvas.getBoundingClientRect();
    lastTouch = { x: t.clientX - rect.left, y: t.clientY - rect.top };
    const handle = detectHandle(lastTouch.x, lastTouch.y);
    state.drag = {
      type: handle ? 'resize' : (inCrop(lastTouch.x, lastTouch.y) ? 'move' : (inImage(lastTouch.x, lastTouch.y) ? 'pan' : null)),
      handle, startX: lastTouch.x, startY: lastTouch.y,
      startCrop: { ...state.crop },
      startOffset: { x: state.offsetX, y: state.offsetY },
    };
  }
}, { passive: true });

canvas.addEventListener('touchmove', e => {
  if (e.touches.length !== 1 || !state.drag) return;
  const t = e.touches[0];
  const rect = canvas.getBoundingClientRect();
  const px = t.clientX - rect.left, py = t.clientY - rect.top;
  const fakeEvt = { offsetX: px, offsetY: py };
  // Reuse mouse logic via simulated event
  const dx = px - state.drag.startX, dy = py - state.drag.startY;
  if (state.drag.type === 'pan') {
    state.offsetX = state.drag.startOffset.x + dx;
    state.offsetY = state.drag.startOffset.y + dy;
  } else if (state.drag.type === 'move') {
    state.crop.x = state.drag.startCrop.x + dx;
    state.crop.y = state.drag.startCrop.y + dy;
    state.crop.w = state.drag.startCrop.w;
    state.crop.h = state.drag.startCrop.h;
    clampCrop();
  } else if (state.drag.type === 'resize') {
    resizeCrop(state.drag.handle, dx, dy);
    clampCrop();
  }
  drawAll();
}, { passive: true });

canvas.addEventListener('touchend', () => { state.drag = null; });

function resizeCrop(handle, dx, dy) {
  let { x, y, w, h } = state.drag.startCrop;
  if (handle.includes('w')) { x += dx; w -= dx; }
  if (handle.includes('e')) { w += dx; }
  if (handle.includes('n')) { y += dy; h -= dy; }
  if (handle.includes('s')) { h += dy; }
  w = Math.max(80, w); h = Math.max(50, h);
  if ($('lockRatio').checked) {
    const r = state.ratio;
    if (Math.abs(dx) >= Math.abs(dy)) {
      h = w / r;
      if (handle.includes('n') && !handle.includes('s')) y = state.drag.startCrop.y + state.drag.startCrop.h - h;
    } else {
      w = h * r;
      if (handle.includes('w') && !handle.includes('e')) x = state.drag.startCrop.x + state.drag.startCrop.w - w;
    }
  }
  Object.assign(state.crop, { x, y, w, h });
}

function clampCrop() {
  const cw = canvas.width, ch = canvas.height;
  const min_w = 80, min_h = 50;
  state.crop.x = Math.max(0, Math.min(cw - min_w, state.crop.x));
  state.crop.y = Math.max(0, Math.min(ch - min_h, state.crop.y));
  state.crop.w = Math.max(min_w, Math.min(cw - state.crop.x, state.crop.w));
  state.crop.h = Math.max(min_h, Math.min(ch - state.crop.y, state.crop.h));
}

/* ── Zoom slider ─────────────────────────────────────── */
$('zoomSlider').addEventListener('input', e => {
  state.zoom = parseInt(e.target.value) / 100;
  if (state.originalImg) { layoutImage(); drawAll(); }
});

/* ── Preset buttons ─────────────────────────────────── */
document.querySelectorAll('[data-ratio]').forEach(btn => {
  btn.addEventListener('click', () => {
    const [w, h] = btn.dataset.ratio.split(',').map(Number);
    state.ratio = w / Math.max(h, 1);
    if (state.originalImg) { resetCrop(); drawAll(); }
    setStatus(`Preset: ${w}×${h}`);
  });
});

/* ── Apply crop ──────────────────────────────────────── */
$('btnApplyCrop').addEventListener('click', () => {
  if (!state.originalImg) { setStatus('Upload an image first'); return; }

  const iw = state.originalImg.naturalWidth;
  const ih = state.originalImg.naturalHeight;
  const sc = state.imageW / iw;  // px-per-natural-pixel

  const left   = Math.max(0, Math.min(iw, (state.crop.x - state.offsetX) / sc));
  const top    = Math.max(0, Math.min(ih, (state.crop.y - state.offsetY) / sc));
  const right  = Math.max(left+1, Math.min(iw, (state.crop.x + state.crop.w - state.offsetX) / sc));
  const bottom = Math.max(top+1,  Math.min(ih, (state.crop.y + state.crop.h - state.offsetY) / sc));

  const tmp = document.createElement('canvas');
  tmp.width = right - left; tmp.height = bottom - top;
  const tc = tmp.getContext('2d');
  tc.drawImage(state.originalImg, left, top, tmp.width, tmp.height, 0, 0, tmp.width, tmp.height);
  tmp.toBlob(blob => {
    state.croppedBlob = blob;
    setStatus(`Crop applied: ${tmp.width}×${tmp.height}px`);
  }, 'image/jpeg', 0.95);
});

/* ── Clear crop ──────────────────────────────────────── */
$('btnClearCrop').addEventListener('click', () => {
  state.croppedBlob = null;
  if (state.originalImg) { resetCrop(); drawAll(); }
  setStatus('Crop cleared');
});

/* ── Export <100KB ───────────────────────────────────── */
$('btnExport').addEventListener('click', async () => {
  const blob = state.croppedBlob;
  if (!blob && !state.originalImg) { setStatus('Upload or crop an image first'); return; }

  const sourceBlob = blob || await new Promise(res => {
    const tmp = document.createElement('canvas');
    tmp.width = state.originalImg.naturalWidth;
    tmp.height = state.originalImg.naturalHeight;
    tmp.getContext('2d').drawImage(state.originalImg, 0, 0);
    tmp.toBlob(res, 'image/jpeg', 0.95);
  });

  // Binary-search for quality that fits <100KB
  let lo = 0.05, hi = 0.95, bestBlob = null;
  for (let i = 0; i < 10; i++) {
    const mid = (lo + hi) / 2;
    const tmp = document.createElement('canvas');
    const img = state.originalImg;
    tmp.width = img.naturalWidth; tmp.height = img.naturalHeight;
    tmp.getContext('2d').drawImage(img, 0, 0);
    const candidate = await new Promise(res => tmp.toBlob(res, 'image/jpeg', mid));
    if (candidate.size <= 100 * 1024) { bestBlob = candidate; lo = mid; }
    else hi = mid;
  }
  if (!bestBlob) { toast('Could not compress below 100KB — try cropping first'); return; }

  const url = URL.createObjectURL(bestBlob);
  const a   = document.createElement('a');
  a.href = url; a.download = 'optimised-image.jpg';
  a.click(); URL.revokeObjectURL(url);
  setStatus(`Exported ${(bestBlob.size / 1024).toFixed(1)}KB`);
});

/* ── Generate Image SEO ──────────────────────────────── */
$('btnGenImg').addEventListener('click', generateImageSEO);

async function generateImageSEO() {
  const activeBlob = state.croppedBlob ||
    (state.originalFile ? state.originalFile : null);
  if (!activeBlob) { setStatus('Upload an image first'); return; }

  const keyword = $('sceneInput').value.trim() || 'image SEO';
  const btn     = $('btnGenImg');
  btn.disabled  = true;
  btn.innerHTML = '<span class="spinner"></span>Generating…';
  setStatus('Sending to Together AI…');

  const formData = new FormData();
  formData.append('image', activeBlob, 'image.jpg');
  formData.append('keyword', keyword);

  try {
    const res  = await fetch('/api/image-seo', { method: 'POST', body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Server error');
    $('altText').value  = data.alt_text  || '';
    $('imgTitle').value = data.img_title || '';
    $('caption').value  = data.caption   || '';
    setStatus(`Image SEO generated via ${data.model} ✓`);
    toast('Image SEO generated ✓');
  } catch (e) {
    toast('Error: ' + e.message, 3500);
    setStatus('Image SEO error: ' + e.message);
  } finally {
    btn.disabled  = false;
    btn.innerHTML = '⚡ Generate SEO';
  }
}

/* ── Copy buttons ────────────────────────────────────── */
$('cAlt').addEventListener('click',   () => copyText($('altText').value,  'Alt Text'));
$('cTitle').addEventListener('click', () => copyText($('imgTitle').value, 'Image Title'));
$('cCap').addEventListener('click',   () => copyText($('caption').value,  'Caption'));
$('cAll').addEventListener('click',   () => {
  const text = [
    'Image SEO',
    '',
    'Keyword: ' + $('sceneInput').value,
    '',
    'Alt Text:',
    $('altText').value,
    '',
    'Image Title:',
    $('imgTitle').value,
    '',
    'Caption:',
    $('caption').value,
  ].join('\n');
  copyText(text, 'all image SEO fields');
});
$('btnCopyAll').addEventListener('click', () => $('cAll').click());

/* ── Clear image fields ──────────────────────────────── */
$('btnClearImg').addEventListener('click', () => {
  $('sceneInput').value = '';
  $('altText').value    = '';
  $('imgTitle').value   = '';
  $('caption').value    = '';
  state.originalImg = state.originalFile = state.croppedBlob = null;
  state.zoom = 1; $('zoomSlider').value = 100;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  $('canvasPlaceholder').style.display = 'flex';
  $('cropInfo').textContent = 'No image loaded';
  setStatus('Cleared all image SEO fields');
});

/* ── Init canvas on load ─────────────────────────────── */
window.addEventListener('load', resizeCanvas);
