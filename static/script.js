const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

const STORAGE_KEY = "wpseostudio_together_api_key";

const state = {
  seoData: null,
  imageName: "",
  originalImage: null,
  croppedBlob: null,
  crop: null,
  drag: null,
  zoom: 1,
  aspectRatio: null,
  safeZone: true,
  lockRatio: true,
  apiKey: "",
};

const els = {
  apiBadge: $("#apiBadge"),
  statusBar: $("#statusBar"),
  toast: $("#toast"),

  openApiModal: $("#openApiModal"),
  apiModal: $("#apiModal"),
  closeApiModal: $("#closeApiModal"),
  apiKeyInput: $("#apiKeyInput"),
  showApiKey: $("#showApiKey"),
  btnTestApi: $("#btnTestApi"),
  btnSaveApi: $("#btnSaveApi"),
  btnClearApi: $("#btnClearApi"),
  apiModalStatus: $("#apiModalStatus"),

  tabBtns: $$(".tab-btn"),
  panels: $$(".tab-panel"),

  inputArticle: $("#inputArticle"),
  outputArticle: $("#outputArticle"),
  optTitles: $("#optTitles"),
  optMeta: $("#optMeta"),
  optCaption: $("#optCaption"),
  optHashtags: $("#optHashtags"),

  btnGenerate: $("#btnGenerate"),
  btnCopyHTML: $("#btnCopyHTML"),
  btnClearIn: $("#btnClearIn"),
  btnClearOut: $("#btnClearOut"),

  btnUpload: $("#btnUpload"),
  btnGenImg: $("#btnGenImg"),
  btnCopyAll: $("#btnCopyAll"),
  btnClearImg: $("#btnClearImg"),
  fileInput: $("#fileInput"),

  cropCanvas: $("#cropCanvas"),
  canvasWrap: $("#canvasWrap"),
  canvasPlaceholder: $("#canvasPlaceholder"),
  cropInfo: $("#cropInfo"),
  zoomSlider: $("#zoomSlider"),
  lockRatio: $("#lockRatio"),
  safeZone: $("#safeZone"),
  ratioBtns: $$(".btn-sm.blue[data-ratio]"),

  btnApplyCrop: $("#btnApplyCrop"),
  btnExport: $("#btnExport"),
  btnClearCrop: $("#btnClearCrop"),

  sceneInput: $("#sceneInput"),
  altText: $("#altText"),
  imgTitle: $("#imgTitle"),
  caption: $("#caption"),

  cAlt: $("#cAlt"),
  cTitle: $("#cTitle"),
  cCap: $("#cCap"),
  cAll: $("#cAll"),
};

const ctx = els.cropCanvas.getContext("2d");


function setStatus(text) {
  els.statusBar.textContent = text;
}

function setBadge(mode, text) {
  els.apiBadge.classList.remove("ready", "busy", "error");
  if (mode === "busy") els.apiBadge.classList.add("busy");
  else if (mode === "error") els.apiBadge.classList.add("error");
  else els.apiBadge.classList.add("ready");
  els.apiBadge.textContent = text;
}

function refreshApiBadge() {
  if (state.apiKey) {
    setBadge("ready", "● User API Saved");
  } else {
    setBadge("ready", "○ Ready");
  }
}

function toast(msg) {
  els.toast.textContent = msg;
  els.toast.classList.add("show");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => els.toast.classList.remove("show"), 1800);
}

async function copyText(text, label = "Copied") {
  if (!text || !String(text).trim()) {
    setStatus("Nothing to copy");
    return;
  }
  try {
    await navigator.clipboard.writeText(String(text));
    toast(label);
    setStatus(label);
  } catch {
    const ta = document.createElement("textarea");
    ta.value = String(text);
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
    toast(label);
    setStatus(label);
  }
}

function escapeHtml(s = "") {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function nl2br(s = "") {
  return escapeHtml(s).replace(/\n/g, "<br>");
}

function switchTab(tab) {
  els.tabBtns.forEach(btn => btn.classList.toggle("active", btn.dataset.tab === tab));
  els.panels.forEach(panel => panel.classList.toggle("active", panel.id === `tab-${tab}`));
}

els.tabBtns.forEach(btn => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});


function openApiModal() {
  els.apiModal.classList.remove("hidden");
  els.apiKeyInput.value = state.apiKey || "";
  els.apiModalStatus.textContent = state.apiKey ? "Saved key loaded from browser" : "No key saved";
}

function closeApiModal() {
  els.apiModal.classList.add("hidden");
}

function loadApiKey() {
  state.apiKey = localStorage.getItem(STORAGE_KEY) || "";
  refreshApiBadge();
}

function saveApiKey() {
  const key = els.apiKeyInput.value.trim();
  if (!key) {
    els.apiModalStatus.textContent = "API key is empty";
    return;
  }
  localStorage.setItem(STORAGE_KEY, key);
  state.apiKey = key;
  refreshApiBadge();
  els.apiModalStatus.textContent = "API key saved in browser";
  toast("API key saved");
  setStatus("API key saved");
}

function clearApiKey() {
  localStorage.removeItem(STORAGE_KEY);
  state.apiKey = "";
  els.apiKeyInput.value = "";
  refreshApiBadge();
  els.apiModalStatus.textContent = "Saved API key cleared";
  toast("API key cleared");
  setStatus("API key cleared");
}

async function testApiKey() {
  const key = els.apiKeyInput.value.trim();
  if (!key) {
    els.apiModalStatus.textContent = "Paste API key first";
    return;
  }

  els.apiModalStatus.textContent = "Testing API key...";
  try {
    const res = await fetch("/api/ping-key", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ api_key: key })
    });

    const data = await res.json();
    if (!res.ok || !data.ok) {
      throw new Error(data.error || "Invalid API key");
    }

    els.apiModalStatus.textContent = "API key is valid";
    toast("API key valid");
  } catch (err) {
    els.apiModalStatus.textContent = err.message;
    toast("API key failed");
  }
}

els.openApiModal.addEventListener("click", openApiModal);
els.closeApiModal.addEventListener("click", closeApiModal);
els.apiModal.addEventListener("click", (e) => {
  if (e.target === els.apiModal) closeApiModal();
});
els.showApiKey.addEventListener("change", () => {
  els.apiKeyInput.type = els.showApiKey.checked ? "text" : "password";
});
els.btnSaveApi.addEventListener("click", saveApiKey);
els.btnClearApi.addEventListener("click", clearApiKey);
els.btnTestApi.addEventListener("click", testApiKey);


function renderSEO(data) {
  state.seoData = data;

  const html = [];
  html.push(`<div class="render-block">`);

  if (data.h1) html.push(`<h1>${escapeHtml(data.h1)}</h1>`);
  if (data.intro) html.push(`<p class="intro">${escapeHtml(data.intro)}</p>`);

  (data.body_sections || []).forEach(section => {
    if (section.h2) html.push(`<h2>${escapeHtml(section.h2)}</h2>`);
    (section.subsections || []).forEach(sub => {
      if (sub.h3) html.push(`<h3>${escapeHtml(sub.h3)}</h3>`);
      if (sub.h4) html.push(`<h3>${escapeHtml(sub.h4)}</h3>`);
      if (sub.body) {
        sub.body.split(/\n{2,}/).forEach(p => {
          if (p.trim()) html.push(`<p>${nl2br(p.trim())}</p>`);
        });
      }
    });
  });

  html.push(`</div>`);
  els.outputArticle.innerHTML = html.join("");

  els.optTitles.textContent = (data.seo_title_options || []).join("\n");
  els.optMeta.textContent = [
    `Focus Keyphrase: ${data.focus_keyphrase || ""}`,
    `SEO Title: ${data.seo_title || ""}`,
    `Meta Description: ${data.meta_description || ""}`,
    `Slug (URL): ${data.slug || ""}`,
    `Short Summary: ${data.short_summary || ""}`
  ].join("\n");

  els.optCaption.textContent = data.short_caption || "";
  els.optHashtags.textContent = (data.hashtags || []).join("  ");
}

function clearSEOOutput() {
  state.seoData = null;
  els.outputArticle.innerHTML = `<div class="placeholder-msg">Your formatted output will appear here after generation.</div>`;
  els.optTitles.textContent = "";
  els.optMeta.textContent = "";
  els.optCaption.textContent = "";
  els.optHashtags.textContent = "";
}

async function generateSEO() {
  const text = els.inputArticle.value.trim();
  if (!text) {
    setStatus("Please paste article text first");
    toast("Please paste article text first");
    return;
  }

  setStatus("Generating SEO...");
  setBadge("busy", "◌ Working");

  try {
    const res = await fetch("/api/seo-format", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ text })
    });

    const data = await res.json();

    if (!res.ok) throw new Error(data.error || "SEO generation failed");

    renderSEO(data);
    refreshApiBadge();
    setStatus("SEO output generated ✓");
    toast("SEO generated");
  } catch (err) {
    setStatus(err.message);
    setBadge("error", "● Error");
    toast("Failed");
  }
}

els.btnGenerate.addEventListener("click", generateSEO);

els.btnClearIn.addEventListener("click", () => {
  els.inputArticle.value = "";
  setStatus("Input cleared");
});

els.btnClearOut.addEventListener("click", () => {
  clearSEOOutput();
  setStatus("Output cleared");
});

els.btnCopyHTML.addEventListener("click", async () => {
  if (!state.seoData) {
    setStatus("Generate SEO first");
    return;
  }
  await copyText(state.seoData.html_output || "", "Copied WP HTML");
});

$$(".pill").forEach(btn => {
  btn.addEventListener("click", async () => {
    if (!state.seoData) {
      setStatus("Generate SEO first");
      return;
    }
    const key = btn.dataset.copy;
    const val = state.seoData[key] || "";
    await copyText(val, `Copied ${btn.textContent.trim()}`);
  });
});


// IMAGE / CROP
function fitCanvasToWrap() {
  const rect = els.canvasWrap.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  els.cropCanvas.width = Math.max(1, Math.floor(rect.width * dpr));
  els.cropCanvas.height = Math.max(1, Math.floor(rect.height * dpr));
  els.cropCanvas.style.width = `${rect.width}px`;
  els.cropCanvas.style.height = `${rect.height}px`;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  drawCanvas();
}

function defaultCropRect() {
  const rect = els.canvasWrap.getBoundingClientRect();
  const w = rect.width;
  const h = rect.height;
  const rw = Math.min(w * 0.55, 620);
  const rh = state.aspectRatio ? rw / state.aspectRatio : h * 0.55;

  let finalW = rw;
  let finalH = rh;

  if (finalH > h * 0.74) {
    finalH = h * 0.74;
    finalW = state.aspectRatio ? finalH * state.aspectRatio : rw;
  }

  return {
    x: (w - finalW) / 2,
    y: (h - finalH) / 2,
    w: finalW,
    h: finalH
  };
}

function drawCanvas() {
  const rect = els.canvasWrap.getBoundingClientRect();
  ctx.clearRect(0, 0, rect.width, rect.height);

  if (!state.originalImage) return;

  const img = state.originalImage;
  const zoom = state.zoom;

  const baseScale = Math.min(rect.width / img.width, rect.height / img.height);
  const drawW = img.width * baseScale * zoom;
  const drawH = img.height * baseScale * zoom;
  const x = (rect.width - drawW) / 2;
  const y = (rect.height - drawH) / 2;

  state.imageDraw = { x, y, w: drawW, h: drawH, baseScale };

  ctx.drawImage(img, x, y, drawW, drawH);

  if (!state.crop) return;

  ctx.save();
  ctx.fillStyle = "rgba(0,0,0,.42)";
  ctx.beginPath();
  ctx.rect(0, 0, rect.width, rect.height);
  ctx.rect(state.crop.x, state.crop.y, state.crop.w, state.crop.h);
  ctx.fill("evenodd");
  ctx.restore();

  ctx.save();
  ctx.strokeStyle = "#4f8dff";
  ctx.lineWidth = 1.8;
  ctx.strokeRect(state.crop.x, state.crop.y, state.crop.w, state.crop.h);

  const thirdX = state.crop.w / 3;
  const thirdY = state.crop.h / 3;

  ctx.strokeStyle = "rgba(120,170,255,.45)";
  ctx.lineWidth = 1;

  ctx.beginPath();
  ctx.moveTo(state.crop.x + thirdX, state.crop.y);
  ctx.lineTo(state.crop.x + thirdX, state.crop.y + state.crop.h);
  ctx.moveTo(state.crop.x + thirdX * 2, state.crop.y);
  ctx.lineTo(state.crop.x + thirdX * 2, state.crop.y + state.crop.h);

  ctx.moveTo(state.crop.x, state.crop.y + thirdY);
  ctx.lineTo(state.crop.x + state.crop.w, state.crop.y + thirdY);
  ctx.moveTo(state.crop.x, state.crop.y + thirdY * 2);
  ctx.lineTo(state.crop.x + state.crop.w, state.crop.y + thirdY * 2);
  ctx.stroke();

  if (state.safeZone) {
    const insetX = state.crop.w * 0.08;
    const insetY = state.crop.h * 0.08;
    ctx.strokeStyle = "rgba(84,170,255,.55)";
    ctx.setLineDash([6, 5]);
    ctx.strokeRect(
      state.crop.x + insetX,
      state.crop.y + insetY,
      state.crop.w - insetX * 2,
      state.crop.h - insetY * 2
    );
    ctx.setLineDash([]);
  }

  const hs = 10;
  const corners = [
    [state.crop.x, state.crop.y],
    [state.crop.x + state.crop.w, state.crop.y],
    [state.crop.x, state.crop.y + state.crop.h],
    [state.crop.x + state.crop.w, state.crop.y + state.crop.h],
  ];
  ctx.fillStyle = "#ffffff";
  corners.forEach(([cx, cy]) => {
    ctx.fillRect(cx - hs / 2, cy - hs / 2, hs, hs);
  });

  ctx.restore();
}

function pointerPos(evt) {
  const rect = els.canvasWrap.getBoundingClientRect();
  return {
    x: evt.clientX - rect.left,
    y: evt.clientY - rect.top
  };
}

function hitCorner(pos) {
  if (!state.crop) return null;
  const hs = 14;
  const pts = {
    tl: { x: state.crop.x, y: state.crop.y },
    tr: { x: state.crop.x + state.crop.w, y: state.crop.y },
    bl: { x: state.crop.x, y: state.crop.y + state.crop.h },
    br: { x: state.crop.x + state.crop.w, y: state.crop.y + state.crop.h },
  };
  for (const [name, p] of Object.entries(pts)) {
    if (Math.abs(pos.x - p.x) <= hs && Math.abs(pos.y - p.y) <= hs) {
      return name;
    }
  }
  return null;
}

function pointInCrop(pos) {
  if (!state.crop) return false;
  return (
    pos.x >= state.crop.x &&
    pos.x <= state.crop.x + state.crop.w &&
    pos.y >= state.crop.y &&
    pos.y <= state.crop.y + state.crop.h
  );
}

function clampCropToCanvas() {
  const rect = els.canvasWrap.getBoundingClientRect();
  if (!state.crop) return;

  state.crop.w = Math.max(40, state.crop.w);
  state.crop.h = Math.max(40, state.crop.h);

  if (state.crop.x < 0) state.crop.x = 0;
  if (state.crop.y < 0) state.crop.y = 0;
  if (state.crop.x + state.crop.w > rect.width) state.crop.x = rect.width - state.crop.w;
  if (state.crop.y + state.crop.h > rect.height) state.crop.y = rect.height - state.crop.h;

  state.crop.x = Math.max(0, state.crop.x);
  state.crop.y = Math.max(0, state.crop.y);
}

function resizeCrop(corner, pos) {
  let { x, y, w, h } = state.crop;
  const minSize = 40;

  if (corner === "tl") {
    const right = x + w;
    const bottom = y + h;
    x = pos.x;
    y = pos.y;
    w = right - x;
    h = bottom - y;
  }
  if (corner === "tr") {
    const left = x;
    const bottom = y + h;
    y = pos.y;
    w = pos.x - left;
    h = bottom - y;
  }
  if (corner === "bl") {
    const right = x + w;
    const top = y;
    x = pos.x;
    w = right - x;
    h = pos.y - top;
  }
  if (corner === "br") {
    w = pos.x - x;
    h = pos.y - y;
  }

  w = Math.max(minSize, w);
  h = Math.max(minSize, h);

  if (state.lockRatio && state.aspectRatio) {
    const ratio = state.aspectRatio;

    if (w / h > ratio) {
      w = h * ratio;
    } else {
      h = w / ratio;
    }

    if (corner === "tl") {
      x = state.crop.x + state.crop.w - w;
      y = state.crop.y + state.crop.h - h;
    }
    if (corner === "tr") {
      y = state.crop.y + state.crop.h - h;
    }
    if (corner === "bl") {
      x = state.crop.x + state.crop.w - w;
    }
  }

  state.crop = { x, y, w, h };
  clampCropToCanvas();
}

els.canvasWrap.addEventListener("pointerdown", (evt) => {
  if (!state.originalImage) return;
  const pos = pointerPos(evt);
  const corner = hitCorner(pos);

  if (corner) {
    state.drag = { mode: "resize", corner };
    return;
  }

  if (pointInCrop(pos)) {
    state.drag = {
      mode: "move",
      offsetX: pos.x - state.crop.x,
      offsetY: pos.y - state.crop.y
    };
    return;
  }

  state.crop = { x: pos.x, y: pos.y, w: 1, h: 1 };
  state.drag = { mode: "new", startX: pos.x, startY: pos.y };
  drawCanvas();
});

window.addEventListener("pointermove", (evt) => {
  if (!state.drag || !state.originalImage) return;
  const pos = pointerPos(evt);

  if (state.drag.mode === "move") {
    state.crop.x = pos.x - state.drag.offsetX;
    state.crop.y = pos.y - state.drag.offsetY;
    clampCropToCanvas();
    drawCanvas();
    return;
  }

  if (state.drag.mode === "resize") {
    resizeCrop(state.drag.corner, pos);
    drawCanvas();
    return;
  }

  if (state.drag.mode === "new") {
    let x = Math.min(state.drag.startX, pos.x);
    let y = Math.min(state.drag.startY, pos.y);
    let w = Math.abs(pos.x - state.drag.startX);
    let h = Math.abs(pos.y - state.drag.startY);

    if (state.lockRatio && state.aspectRatio) {
      const ratio = state.aspectRatio;
      if (w / Math.max(h, 1) > ratio) h = w / ratio;
      else w = h * ratio;

      if (pos.x < state.drag.startX) x = state.drag.startX - w;
      if (pos.y < state.drag.startY) y = state.drag.startY - h;
    }

    state.crop = { x, y, w, h };
    clampCropToCanvas();
    drawCanvas();
  }
});

window.addEventListener("pointerup", () => {
  state.drag = null;
});

function loadImageFile(file) {
  if (!file) return;
  state.imageName = file.name || "image";
  const url = URL.createObjectURL(file);
  const img = new Image();
  img.onload = () => {
    state.originalImage = img;
    state.croppedBlob = null;
    state.zoom = 1;
    els.zoomSlider.value = "100";
    state.crop = defaultCropRect();
    els.canvasPlaceholder.style.display = "none";
    els.cropInfo.textContent = `${img.width} × ${img.height}`;
    fitCanvasToWrap();
    URL.revokeObjectURL(url);
    setStatus("Image loaded");
  };
  img.src = url;
}

els.btnUpload.addEventListener("click", () => els.fileInput.click());
els.fileInput.addEventListener("change", (e) => loadImageFile(e.target.files[0]));

els.zoomSlider.addEventListener("input", () => {
  state.zoom = Number(els.zoomSlider.value) / 100;
  drawCanvas();
});

els.lockRatio.addEventListener("change", () => {
  state.lockRatio = els.lockRatio.checked;
});

els.safeZone.addEventListener("change", () => {
  state.safeZone = els.safeZone.checked;
  drawCanvas();
});

els.ratioBtns.forEach(btn => {
  btn.addEventListener("click", () => {
    const [a, b] = btn.dataset.ratio.split(",").map(Number);
    state.aspectRatio = a / b;
    state.crop = defaultCropRect();
    drawCanvas();
    setStatus(`Ratio set: ${btn.textContent.trim()}`);
  });
});

function cropToBlob(maxBytes = null) {
  if (!state.originalImage || !state.crop || !state.imageDraw) return null;

  const { x, y, w, h } = state.crop;
  const draw = state.imageDraw;

  const sx = Math.max(0, (x - draw.x) / draw.w * state.originalImage.width);
  const sy = Math.max(0, (y - draw.y) / draw.h * state.originalImage.height);
  const sw = Math.max(1, w / draw.w * state.originalImage.width);
  const sh = Math.max(1, h / draw.h * state.originalImage.height);

  const out = document.createElement("canvas");
  out.width = Math.round(sw);
  out.height = Math.round(sh);
  const octx = out.getContext("2d");
  octx.drawImage(
    state.originalImage,
    sx, sy, sw, sh,
    0, 0, out.width, out.height
  );

  return new Promise((resolve) => {
    if (!maxBytes) {
      out.toBlob(resolve, "image/jpeg", 0.92);
      return;
    }

    let quality = 0.92;

    const tryCompress = () => {
      out.toBlob((blob) => {
        if (!blob) return resolve(null);
        if (blob.size <= maxBytes || quality <= 0.38) {
          resolve(blob);
        } else {
          quality -= 0.08;
          tryCompress();
        }
      }, "image/jpeg", quality);
    };

    tryCompress();
  });
}

els.btnApplyCrop.addEventListener("click", async () => {
  if (!state.originalImage || !state.crop) {
    setStatus("No crop selected");
    return;
  }

  const blob = await cropToBlob();
  if (!blob) {
    setStatus("Crop failed");
    return;
  }

  state.croppedBlob = blob;
  setStatus("Crop applied");
  toast("Crop applied");
});

els.btnExport.addEventListener("click", async () => {
  if (!state.originalImage || !state.crop) {
    setStatus("No crop selected");
    return;
  }

  const blob = await cropToBlob(100 * 1024);
  if (!blob) {
    setStatus("Export failed");
    return;
  }

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = (state.imageName || "image").replace(/\.[^.]+$/, "") + "-crop.jpg";
  a.click();
  URL.revokeObjectURL(url);

  setStatus(`Exported ${(blob.size / 1024).toFixed(1)}KB`);
  toast("Exported");
});

function clearImageTool() {
  state.originalImage = null;
  state.croppedBlob = null;
  state.crop = null;
  state.drag = null;
  state.zoom = 1;
  state.aspectRatio = null;
  els.zoomSlider.value = "100";
  els.fileInput.value = "";
  els.sceneInput.value = "";
  els.altText.value = "";
  els.imgTitle.value = "";
  els.caption.value = "";
  els.canvasPlaceholder.style.display = "flex";
  els.cropInfo.textContent = "No image loaded";
  ctx.clearRect(0, 0, els.cropCanvas.width, els.cropCanvas.height);
}

els.btnClearCrop.addEventListener("click", () => {
  if (!state.originalImage) return;
  state.crop = defaultCropRect();
  drawCanvas();
  setStatus("Crop reset");
});

els.btnClearImg.addEventListener("click", () => {
  clearImageTool();
  setStatus("Image tool cleared");
});

async function generateImageSEO() {
  const imageBlob = state.croppedBlob || await cropToBlob() || null;

  if (!imageBlob) {
    setStatus("Please upload an image first");
    toast("Upload image first");
    return;
  }

  if (!state.apiKey) {
    openApiModal();
    els.apiModalStatus.textContent = "Put your API key first";
    setStatus("Need user API key");
    return;
  }

  const fd = new FormData();
  fd.append("image", imageBlob, "image.jpg");
  fd.append("keyword", els.sceneInput.value.trim());
  fd.append("api_key", state.apiKey);

  setStatus("Generating image SEO...");
  setBadge("busy", "◌ Working");

  try {
    const res = await fetch("/api/image-seo", {
      method: "POST",
      body: fd
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Image SEO failed");

    els.altText.value = data.alt_text || "";
    els.imgTitle.value = data.img_title || "";
    els.caption.value = data.caption || "";

    refreshApiBadge();
    setStatus(`Image SEO generated ✓`);
    toast("Image SEO generated");
  } catch (err) {
    setStatus(err.message);
    setBadge("error", "● Error");
    toast("Failed");
  }
}

els.btnGenImg.addEventListener("click", generateImageSEO);

els.btnCopyAll.addEventListener("click", async () => {
  const txt = [
    `Alt Text: ${els.altText.value || ""}`,
    `Image Title: ${els.imgTitle.value || ""}`,
    `Caption: ${els.caption.value || ""}`
  ].join("\n");
  await copyText(txt, "Copied All SEO");
});

els.cAlt.addEventListener("click", () => copyText(els.altText.value, "Copied Alt Text"));
els.cTitle.addEventListener("click", () => copyText(els.imgTitle.value, "Copied Img Title"));
els.cCap.addEventListener("click", () => copyText(els.caption.value, "Copied Caption"));
els.cAll.addEventListener("click", () => {
  const txt = [
    `Alt Text: ${els.altText.value || ""}`,
    `Image Title: ${els.imgTitle.value || ""}`,
    `Caption: ${els.caption.value || ""}`
  ].join("\n");
  copyText(txt, "Copied All");
});

window.addEventListener("resize", fitCanvasToWrap);
window.addEventListener("load", () => {
  loadApiKey();
  clearSEOOutput();
  clearImageTool();
  setStatus("Ready");
});
