const state = {
  article: null,
  imageFile: null,
  imageElement: null,
  imageNaturalWidth: 1,
  imageNaturalHeight: 1,
  zoom: 1,
  currentRatio: 1200 / 366,
  lockRatio: true,
  safeZone: true,
  cropRect: { x: 120, y: 60, w: 600, h: 183 },
  dragging: false,
  resizeHandle: null,
  startMouse: null,
  startRect: null,
};

const els = {
  statusBar: document.getElementById('statusBar'),
  topTabs: [...document.querySelectorAll('.top-tab')],
  pages: [...document.querySelectorAll('.tab-page')],
  articleUrl: document.getElementById('articleUrl'),
  articleInput: document.getElementById('articleInput'),
  articleOutput: document.getElementById('articleOutput'),
  generateNewsBtn: document.getElementById('generateNewsBtn'),
  clearInputBtn: document.getElementById('clearInputBtn'),
  copyWpHtmlBtn: document.getElementById('copyWpHtmlBtn'),
  copyFocusBtn: document.getElementById('copyFocusBtn'),
  copySeoTitleBtn: document.getElementById('copySeoTitleBtn'),
  copyMetaBtn: document.getElementById('copyMetaBtn'),
  imageFile: document.getElementById('imageFile'),
  generateImageSeoBtn: document.getElementById('generateImageSeoBtn'),
  copyAllImageSeoBtn: document.getElementById('copyAllImageSeoBtn'),
  clearAllImageBtn: document.getElementById('clearAllImageBtn'),
  cropCanvas: document.getElementById('cropCanvas'),
  preset1200: document.getElementById('preset1200'),
  preset800: document.getElementById('preset800'),
  lockRatio: document.getElementById('lockRatio'),
  safeZone: document.getElementById('safeZone'),
  zoomSlider: document.getElementById('zoomSlider'),
  sceneEntry: document.getElementById('sceneEntry'),
  altText: document.getElementById('altText'),
  imgTitle: document.getElementById('imgTitle'),
  captionText: document.getElementById('captionText'),
  apiKeyInput: document.getElementById('apiKeyInput'),
  showApiKey: document.getElementById('showApiKey'),
  testKeyBtn: document.getElementById('testKeyBtn'),
  saveUseBtn: document.getElementById('saveUseBtn'),
  useSessionBtn: document.getElementById('useSessionBtn'),
  clearSavedKeyBtn: document.getElementById('clearSavedKeyBtn'),
};

function setStatus(text) {
  els.statusBar.textContent = text;
}

async function copyText(text, okText) {
  if (!text || !text.trim()) {
    setStatus('Nothing to copy');
    return;
  }
  await navigator.clipboard.writeText(text);
  setStatus(okText);
}

function switchTab(id) {
  els.topTabs.forEach(btn => btn.classList.toggle('active', btn.dataset.tab === id));
  els.pages.forEach(page => page.classList.toggle('active', page.id === id));
}

els.topTabs.forEach(btn => btn.addEventListener('click', () => switchTab(btn.dataset.tab)));

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok || data.ok === false) throw new Error(data.error || 'Request failed');
  return data;
}

function renderArticleOutput(data) {
  const htmlParts = [];
  if (data.h1) htmlParts.push(`<h1>${escapeHtml(data.h1)}</h1>`);
  if (data.intro) htmlParts.push(`<p>${escapeHtml(data.intro)}</p>`);
  (data.structure || []).forEach(sec => {
    if (sec.h2) htmlParts.push(`<h2>${escapeHtml(sec.h2)}</h2>`);
    (sec.subsections || []).forEach(sub => {
      if (sub.h3) htmlParts.push(`<h3>${escapeHtml(sub.h3)}</h3>`);
      (sub.body || '').split(/\n\n+/).filter(Boolean).forEach(p => htmlParts.push(`<p>${escapeHtml(p)}</p>`));
    });
  });
  els.articleOutput.innerHTML = htmlParts.join('');
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text || '';
  return div.innerHTML;
}

els.generateNewsBtn.addEventListener('click', async () => {
  try {
    setStatus('Generating SEO output...');
    const data = await postJson('/api/article/generate', {
      url: els.articleUrl.value,
      article_text: isPlaceholderArticle() ? '' : els.articleInput.value,
    });
    state.article = data;
    if (data.article_text && isPlaceholderArticle()) {
      els.articleInput.value = data.article_text;
    }
    renderArticleOutput(data);
    setStatus('Article SEO output generated');
  } catch (err) {
    els.articleOutput.textContent = err.message;
    setStatus(err.message);
  }
});

els.clearInputBtn.addEventListener('click', () => {
  state.article = null;
  els.articleUrl.value = '';
  els.articleInput.value = 'Paste your article here...';
  els.articleOutput.textContent = 'Formatted SEO output will appear here.';
  setStatus('Input cleared');
});

els.copyWpHtmlBtn.addEventListener('click', () => copyText(state.article?.wordpress_html || '', 'Copied WordPress HTML'));
els.copyFocusBtn.addEventListener('click', () => copyText(state.article?.focus_keyphrase || '', 'Smooth copied: Focus Keyphrase'));
els.copySeoTitleBtn.addEventListener('click', () => copyText(state.article?.seo_title || '', 'Smooth copied: SEO Title'));
els.copyMetaBtn.addEventListener('click', () => copyText(state.article?.meta_description || '', 'Smooth copied: Meta Description'));

function isPlaceholderArticle() {
  const s = (els.articleInput.value || '').trim().toLowerCase();
  return s === '' || s === 'paste your article here...' || s === 'paste your article here.';
}

els.showApiKey.addEventListener('change', () => {
  els.apiKeyInput.type = els.showApiKey.checked ? 'text' : 'password';
});

els.testKeyBtn.addEventListener('click', async () => {
  try {
    setStatus('Testing API key...');
    const data = await postJson('/api/test-key', { api_key: els.apiKeyInput.value });
    setStatus('API key test passed');
    alert(data.message);
  } catch (err) {
    setStatus('API key test failed');
    alert(err.message);
  }
});

async function saveApiKey() {
  const data = await postJson('/api/save-key', { api_key: els.apiKeyInput.value });
  setStatus(data.message);
}

els.saveUseBtn.addEventListener('click', async () => {
  try {
    await saveApiKey();
  } catch (err) {
    setStatus(err.message);
    alert(err.message);
  }
});

els.useSessionBtn.addEventListener('click', async () => {
  try {
    await saveApiKey();
    setStatus('Using API key for this session only');
  } catch (err) {
    setStatus(err.message);
    alert(err.message);
  }
});

els.clearSavedKeyBtn.addEventListener('click', async () => {
  try {
    const data = await postJson('/api/clear-key', {});
    els.apiKeyInput.value = '';
    setStatus(data.message);
  } catch (err) {
    setStatus(err.message);
  }
});

els.imageFile.addEventListener('change', (e) => {
  const file = e.target.files[0];
  if (!file) return;
  state.imageFile = file;
  const img = new Image();
  img.onload = () => {
    state.imageElement = img;
    state.imageNaturalWidth = img.width;
    state.imageNaturalHeight = img.height;
    state.zoom = 1;
    els.zoomSlider.value = '1';
    fitCropToCanvas();
    drawCanvas();
    setStatus('Image loaded');
  };
  img.src = URL.createObjectURL(file);
});

els.preset1200.addEventListener('click', () => { state.currentRatio = 1200 / 366; fitCropToCanvas(); drawCanvas(); });
els.preset800.addEventListener('click', () => { state.currentRatio = 800 / 445; fitCropToCanvas(); drawCanvas(); });
els.lockRatio.addEventListener('change', () => { state.lockRatio = els.lockRatio.checked; drawCanvas(); });
els.safeZone.addEventListener('change', () => { state.safeZone = els.safeZone.checked; drawCanvas(); });
els.zoomSlider.addEventListener('input', () => { state.zoom = parseFloat(els.zoomSlider.value); drawCanvas(); });

els.clearAllImageBtn.addEventListener('click', () => {
  state.imageFile = null;
  state.imageElement = null;
  els.imageFile.value = '';
  els.sceneEntry.value = 'image SEO';
  els.altText.value = '';
  els.imgTitle.value = '';
  els.captionText.value = '';
  clearCanvas();
  setStatus('Image SEO fields cleared');
});

els.copyAllImageSeoBtn.addEventListener('click', () => {
  const text = `Alt Text: ${els.altText.value}\nImage Title: ${els.imgTitle.value}\nCaption: ${els.captionText.value}`;
  copyText(text, 'Copied all image SEO');
});

els.generateImageSeoBtn.addEventListener('click', async () => {
  try {
    if (!state.imageFile) {
      setStatus('Please upload an image first');
      return;
    }
    setStatus('Generating image SEO with Together AI.');
    const form = new FormData();
    form.append('image', state.imageFile);
    form.append('keyword', els.sceneEntry.value || 'image SEO');
    form.append('crop', JSON.stringify(getCropInImageSpace()));
    const response = await fetch('/api/image/generate', { method: 'POST', body: form });
    const data = await response.json();
    if (!response.ok || data.ok === false) throw new Error(data.error || 'Request failed');
    els.altText.value = data.alt_text || '';
    els.imgTitle.value = data.img_title || '';
    els.captionText.value = data.caption || '';
    setStatus(`Generated image SEO with ${data.model}`);
  } catch (err) {
    setStatus(err.message);
    alert(err.message);
  }
});

function clearCanvas() {
  const ctx = els.cropCanvas.getContext('2d');
  ctx.clearRect(0, 0, els.cropCanvas.width, els.cropCanvas.height);
  ctx.fillStyle = '#000';
  ctx.fillRect(0, 0, els.cropCanvas.width, els.cropCanvas.height);
}

function fitCropToCanvas() {
  const canvas = els.cropCanvas;
  const maxW = canvas.width * 0.6;
  const w = maxW;
  const h = w / state.currentRatio;
  state.cropRect = {
    x: (canvas.width - w) / 2,
    y: (canvas.height - h) / 2,
    w,
    h,
  };
}

function getDrawMetrics() {
  const canvas = els.cropCanvas;
  const iw = state.imageNaturalWidth;
  const ih = state.imageNaturalHeight;
  const baseScale = Math.min(canvas.width / iw, canvas.height / ih);
  const scale = baseScale * state.zoom;
  const dw = iw * scale;
  const dh = ih * scale;
  const dx = (canvas.width - dw) / 2;
  const dy = (canvas.height - dh) / 2;
  return { dx, dy, dw, dh, scale };
}

function drawCanvas() {
  const canvas = els.cropCanvas;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = '#000';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  if (!state.imageElement) return;

  const { dx, dy, dw, dh } = getDrawMetrics();
  ctx.drawImage(state.imageElement, dx, dy, dw, dh);

  const r = state.cropRect;
  ctx.save();
  ctx.fillStyle = 'rgba(0,0,0,0.45)';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.clearRect(r.x, r.y, r.w, r.h);
  ctx.restore();

  ctx.strokeStyle = '#78a5ff';
  ctx.lineWidth = 2;
  ctx.strokeRect(r.x, r.y, r.w, r.h);

  if (state.safeZone) {
    ctx.strokeStyle = 'rgba(255,255,255,0.7)';
    ctx.setLineDash([8, 6]);
    ctx.strokeRect(r.x + r.w * 0.1, r.y + r.h * 0.1, r.w * 0.8, r.h * 0.8);
    ctx.setLineDash([]);
  }

  drawHandle(ctx, r.x, r.y);
  drawHandle(ctx, r.x + r.w, r.y);
  drawHandle(ctx, r.x, r.y + r.h);
  drawHandle(ctx, r.x + r.w, r.y + r.h);
}

function drawHandle(ctx, x, y) {
  const s = 12;
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(x - s / 2, y - s / 2, s, s);
  ctx.strokeStyle = '#365b96';
  ctx.strokeRect(x - s / 2, y - s / 2, s, s);
}

function pointInRect(x, y, r) {
  return x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h;
}

function getHandleAt(x, y) {
  const r = state.cropRect;
  const pts = [
    ['nw', r.x, r.y],
    ['ne', r.x + r.w, r.y],
    ['sw', r.x, r.y + r.h],
    ['se', r.x + r.w, r.y + r.h],
  ];
  for (const [name, hx, hy] of pts) {
    if (Math.abs(x - hx) <= 10 && Math.abs(y - hy) <= 10) return name;
  }
  return null;
}

els.cropCanvas.addEventListener('mousedown', (e) => {
  if (!state.imageElement) return;
  const rect = els.cropCanvas.getBoundingClientRect();
  const x = e.clientX - rect.left;
  const y = e.clientY - rect.top;
  state.resizeHandle = getHandleAt(x, y);
  if (state.resizeHandle || pointInRect(x, y, state.cropRect)) {
    state.dragging = true;
    state.startMouse = { x, y };
    state.startRect = { ...state.cropRect };
  }
});

window.addEventListener('mouseup', () => {
  state.dragging = false;
  state.resizeHandle = null;
});

window.addEventListener('mousemove', (e) => {
  if (!state.dragging || !state.imageElement) return;
  const rect = els.cropCanvas.getBoundingClientRect();
  const x = e.clientX - rect.left;
  const y = e.clientY - rect.top;
  const dx = x - state.startMouse.x;
  const dy = y - state.startMouse.y;
  const r = { ...state.startRect };

  if (!state.resizeHandle) {
    state.cropRect.x = clamp(r.x + dx, 0, els.cropCanvas.width - r.w);
    state.cropRect.y = clamp(r.y + dy, 0, els.cropCanvas.height - r.h);
  } else {
    let newW = r.w;
    let newH = r.h;
    let newX = r.x;
    let newY = r.y;
    if (state.resizeHandle.includes('e')) newW = r.w + dx;
    if (state.resizeHandle.includes('s')) newH = r.h + dy;
    if (state.resizeHandle.includes('w')) { newW = r.w - dx; newX = r.x + dx; }
    if (state.resizeHandle.includes('n')) { newH = r.h - dy; newY = r.y + dy; }

    if (state.lockRatio) {
      if (Math.abs(dx) > Math.abs(dy)) newH = newW / state.currentRatio;
      else newW = newH * state.currentRatio;
      if (state.resizeHandle.includes('w')) newX = r.x + (r.w - newW);
      if (state.resizeHandle.includes('n')) newY = r.y + (r.h - newH);
    }

    state.cropRect.w = clamp(newW, 40, els.cropCanvas.width);
    state.cropRect.h = clamp(newH, 30, els.cropCanvas.height);
    state.cropRect.x = clamp(newX, 0, els.cropCanvas.width - state.cropRect.w);
    state.cropRect.y = clamp(newY, 0, els.cropCanvas.height - state.cropRect.h);
  }
  drawCanvas();
});

function clamp(v, min, max) { return Math.max(min, Math.min(max, v)); }

function getCropInImageSpace() {
  const { dx, dy, dw, dh } = getDrawMetrics();
  const sx = state.imageNaturalWidth / dw;
  const sy = state.imageNaturalHeight / dh;
  const left = clamp((state.cropRect.x - dx) * sx, 0, state.imageNaturalWidth);
  const top = clamp((state.cropRect.y - dy) * sy, 0, state.imageNaturalHeight);
  const width = clamp(state.cropRect.w * sx, 1, state.imageNaturalWidth - left);
  const height = clamp(state.cropRect.h * sy, 1, state.imageNaturalHeight - top);
  return { left, top, width, height };
}

async function init() {
  clearCanvas();
  try {
    const response = await fetch('/api/status');
    const data = await response.json();
    setStatus(data.status || 'Ready');
  } catch {
    setStatus('Ready');
  }
}

init();
