/* ═══════════════════════════════════════════════════════════════════
   SEO Tool + Together AI  — Web Port of Tkinter App
   Matches all logic and layout of ImageSEOPromptV4Full.py exactly
═══════════════════════════════════════════════════════════════════ */

// ── State ──────────────────────────────────────────────────────────
let apiKey = localStorage.getItem("together_api_key") || "";
let sessionKey = "";

// Article tool state
let currentSections = {};
let aiRequestCounter = 0;

// Image tool state
let originalImage = null;      // HTMLImageElement
let originalImageFile = null;  // File blob for upload
let croppedBlob = null;        // cropped Blob
let croppedDataUrl = null;

let zoomFactor = 1.0;
let baseScale = 1.0;
let displayScale = 1.0;
let displayW = 1, displayH = 1;
let imageOffsetX = 0, imageOffsetY = 0;
let currentRatio = 1200 / 366;
let lockRatio = true;
let safeZone = true;

// crop_rect = [x1, y1, x2, y2] in canvas coords
let cropRect = [120, 60, 720, 243];
let draggingCrop = false;
let draggingImage = false;
let resizingHandle = null;
let cropDragStart = [0, 0];
let imageDragStart = [0, 0];
let startCropRect = null;
let startOffset = null;
const HANDLE_SIZE = 12;

// ── Helpers ────────────────────────────────────────────────────────
function setStatus(text) {
  document.getElementById("status-text").textContent = "  " + text;
}

function showToast(msg, ms = 1800) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), ms);
}

function copyToClipboard(text, statusMsg) {
  if (!text || !text.trim()) { setStatus("Nothing to copy"); return; }
  navigator.clipboard.writeText(text).then(() => {
    setStatus(statusMsg || "Copied");
    showToast(statusMsg || "Copied");
  }).catch(() => {
    // fallback
    const el = document.createElement("textarea");
    el.value = text;
    document.body.appendChild(el);
    el.select();
    document.execCommand("copy");
    document.body.removeChild(el);
    setStatus(statusMsg || "Copied");
    showToast(statusMsg || "Copied");
  });
}

function getActiveApiKey() {
  return sessionKey || apiKey || "";
}

// ═══════════════════════════════════════════════════════════════════
// API SETTINGS (APISettingsPopup)
// ═══════════════════════════════════════════════════════════════════

function openApiSettings() {
  const modal = document.getElementById("api-modal");
  modal.classList.add("open");
  const entry = document.getElementById("modal-api-entry");
  const current = getActiveApiKey();
  entry.value = current || "";
  setModalStatus(current ? "Loaded current API key into this window" : "Paste your Together AI API key to test and save");
}

function closeApiSettings() {
  document.getElementById("api-modal").classList.remove("open");
}

document.getElementById("api-modal").addEventListener("click", function(e) {
  if (e.target === this) closeApiSettings();
});

function toggleShowKey() {
  const cb = document.getElementById("show-key-cb");
  const entry = document.getElementById("modal-api-entry");
  entry.type = cb.checked ? "text" : "password";
}

function setModalStatus(text) {
  document.getElementById("modal-status").textContent = text;
}

async function testApiKey() {
  const key = document.getElementById("modal-api-entry").value.trim();
  if (!key) { alert("Please paste your API key first."); return; }
  setModalStatus("Testing API key...");
  try {
    const res = await fetch("/api/test-key", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: key }),
    });
    const data = await res.json();
    if (data.ok) {
      setModalStatus("API key test passed ✓");
      alert("API key is valid and ready to use.");
    } else {
      setModalStatus("API key test failed");
      alert("Could not verify this Together AI API key.\n\n" + (data.error || ""));
    }
  } catch (e) {
    setModalStatus("API key test failed");
    alert("Network error: " + e.message);
  }
}

function saveAndUse() {
  const key = document.getElementById("modal-api-entry").value.trim();
  if (!key) { alert("Please paste your API key first."); return; }
  const save = document.getElementById("save-key-cb").checked;
  applyApiKey(key, save);
  setModalStatus("API key applied successfully");
  closeApiSettings();
}

function useSessionOnly() {
  const key = document.getElementById("modal-api-entry").value.trim();
  if (!key) { alert("Please paste your API key first."); return; }
  sessionKey = key;
  apiKey = "";
  updateApiBadge();
  setStatus("Together AI API key loaded successfully");
  setModalStatus("Using API key for this session only");
  closeApiSettings();
}

function clearSavedKey() {
  localStorage.removeItem("together_api_key");
  apiKey = "";
  sessionKey = "";
  document.getElementById("modal-api-entry").value = "";
  updateApiBadge();
  setStatus("API key cleared");
  setModalStatus("Saved API key cleared");
  alert("Saved API key has been removed.");
}

function applyApiKey(key, save) {
  sessionKey = key || "";
  if (save && key) {
    localStorage.setItem("together_api_key", key);
    apiKey = key;
  } else if (!key) {
    localStorage.removeItem("together_api_key");
    apiKey = "";
  }
  updateApiBadge();
  setStatus(key ? "Together AI API key loaded successfully" : "API key cleared");
}

function updateApiBadge() {
  const el = document.getElementById("api-info-label");
  const saved = !!localStorage.getItem("together_api_key");
  const active = getActiveApiKey();
  if (active && saved) {
    el.textContent = "API: Together key saved";
  } else if (active) {
    el.textContent = "API: Together session key loaded";
  } else {
    el.textContent = "API: not configured";
  }
}

// ═══════════════════════════════════════════════════════════════════
// ARTICLE TOOL (ArticleToolFrame)
// ═══════════════════════════════════════════════════════════════════

async function processArticle() {
  const url = document.getElementById("url-entry").value.trim();
  const raw = document.getElementById("input-text").value.trim();
  const isPlaceholder = !raw || raw === "Paste your article here...";

  if (url && /^https?:\/\//i.test(url) && isPlaceholder) {
    // Import from URL
    setStatus("Importing article from URL.");
    document.getElementById("output-text").value = "";
    try {
      const res = await fetch("/api/fetch-url", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      const data = await res.json();
      if (!data.ok) {
        const msg = data.error || "Unknown error";
        setStatus(msg.includes("403") ? "Import failed: site blocked auto import (403)" : "Import failed: " + msg.slice(0, 100));
        document.getElementById("output-text").value = data.error || "";
        return;
      }
      document.getElementById("input-text").value = data.text;
      setStatus("Article imported successfully");
      await _processArticleCore();
    } catch (e) {
      setStatus("Import failed: " + e.message.slice(0, 100));
    }
    return;
  }

  if (isPlaceholder) {
    document.getElementById("output-text").value = "Please paste a news URL or article first.";
    setStatus("Please paste a news URL or article first");
    return;
  }

  await _processArticleCore();
}

async function _processArticleCore() {
  const raw = document.getElementById("input-text").value.trim();
  if (!raw || raw === "Paste your article here...") {
    document.getElementById("output-text").value = "Please paste an article first.";
    setStatus("Please paste an article first");
    return;
  }

  aiRequestCounter++;
  const myId = aiRequestCounter;
  setStatus("Generating SEO fields...");

  try {
    const res = await fetch("/api/process-article", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: raw, api_key: getActiveApiKey() }),
    });
    const data = await res.json();

    if (myId !== aiRequestCounter) return; // stale

    if (!data.ok) {
      document.getElementById("output-text").value = data.error || "Error";
      setStatus(data.error || "Error");
      return;
    }

    currentSections = {
      focus_keyphrase_copy: data.focus_keyphrase || "",
      seo_title_copy:       data.seo_title || "",
      meta_description_copy:data.meta_description || "",
      slug_copy:            data.slug || "",
      short_summary_copy:   data.short_summary || "",
      h1_copy:              data.h1 || "",
      intro_copy:           data.intro || "",
      structure_copy:       data.structure || [],
      wp_html_copy:         data.wp_html || "",
    };

    // Build output preview (matches render_output_preview)
    let preview = "";
    if (data.h1)    preview += data.h1 + "\n\n";
    if (data.intro) preview += data.intro + "\n\n";
    for (const sec of (data.structure || [])) {
      if (sec.h2) preview += sec.h2 + "\n\n";
      for (const sub of (sec.subsections || [])) {
        if (sub.h3) preview += sub.h3 + "\n\n";
        if (sub.body) {
          const paras = sub.body.split(/\n\n+/).filter(p => p.trim());
          preview += paras.join("\n\n") + "\n\n";
        }
      }
    }
    document.getElementById("output-text").value = preview.trim();

    if (data.ai_seo) {
      setStatus("AI SEO fields ready");
    } else {
      setStatus("Article SEO output generated");
    }
  } catch (e) {
    setStatus("Error: " + e.message);
  }
}

function clearInput() {
  aiRequestCounter++;
  currentSections = {};
  document.getElementById("url-entry").value = "";
  document.getElementById("input-text").value = "Paste your article here...";
  document.getElementById("output-text").value = "Formatted SEO output will appear here.";
  setStatus("Input cleared");
}

function copyWpHtml() {
  const html = (currentSections.wp_html_copy || "").trim();
  if (!html) { setStatus("Generate SEO output first"); return; }
  copyToClipboard(html, "Copied WordPress HTML");
}

function copySection(name) {
  if (!currentSections || !Object.keys(currentSections).length) {
    setStatus("Generate SEO output first"); return;
  }
  const map = {
    "Focus Keyphrase": currentSections.focus_keyphrase_copy || "",
    "SEO Title":       currentSections.seo_title_copy || "",
    "Meta Description":currentSections.meta_description_copy || "",
  };
  const value = (map[name] || "").trim();
  if (!value) { setStatus(`No content for ${name}`); return; }
  copyToClipboard(value, `Smooth copied: ${name}`);
}

// ═══════════════════════════════════════════════════════════════════
// IMAGE TOOL (ImageToolFrame)
// ═══════════════════════════════════════════════════════════════════

function triggerImageUpload() {
  document.getElementById("image-file-input").click();
}

function onImageSelected(event) {
  const file = event.target.files[0];
  if (!file) return;
  originalImageFile = file;
  croppedBlob = null;
  croppedDataUrl = null;

  const img = new Image();
  const url = URL.createObjectURL(file);
  img.onload = function() {
    originalImage = img;
    zoomFactor = 1.0;
    document.getElementById("zoom-slider").value = 1.0;
    imageOffsetX = 0; imageOffsetY = 0;
    resetCropRect();
    redrawCanvas();
    document.getElementById("crop-info-label").textContent =
      `Loaded: ${file.name}  •  ${img.naturalWidth}x${img.naturalHeight} px`;
    setStatus("Image loaded");
    URL.revokeObjectURL(url);
  };
  img.src = url;
  // reset file input so same file can be re-selected
  event.target.value = "";
}

// ── Canvas ──────────────────────────────────────────────────────────
function getCanvas() { return document.getElementById("crop-canvas"); }
function getCtx()    { return getCanvas().getContext("2d"); }

function syncCanvasSize() {
  const wrap = document.getElementById("crop-canvas-wrap");
  const canvas = getCanvas();
  canvas.width  = wrap.clientWidth;
  canvas.height = wrap.clientHeight;
}

function resetCropRect() {
  const canvas = getCanvas();
  const cw = canvas.width  || 800;
  const ch = canvas.height || 560;
  const ratio = currentRatio;
  let target_w = Math.min(cw - 100, Math.max(320, Math.floor(cw * 0.72)));
  let target_h = target_w / ratio;
  if (target_h > ch - 100) { target_h = ch - 100; target_w = target_h * ratio; }
  const x1 = (cw - target_w) / 2;
  const y1 = (ch - target_h) / 2;
  cropRect = [x1, y1, x1 + target_w, y1 + target_h];
}

function setCropPreset(w, h) {
  currentRatio = w / Math.max(h, 1);
  resetCropRect();
  redrawCanvas();
  setStatus(`Crop preset set: ${w}x${h}`);
}

function toggleLockRatio() {
  lockRatio = !lockRatio;
  const sw = document.getElementById("lock-ratio-switch");
  sw.classList.toggle("active", lockRatio);
  setStatus(lockRatio ? "Lock ratio enabled" : "Lock ratio disabled");
}

function toggleSafeZone() {
  safeZone = !safeZone;
  const sw = document.getElementById("safe-zone-switch");
  sw.classList.toggle("active", safeZone);
  redrawCanvas();
}

function onZoomChanged(value) {
  zoomFactor = parseFloat(value);
  redrawCanvas();
}

function redrawCanvas() {
  syncCanvasSize();
  const canvas = getCanvas();
  const ctx = getCtx();
  const cw = canvas.width;
  const ch = canvas.height;
  ctx.clearRect(0, 0, cw, ch);

  // Fill background
  ctx.fillStyle = "#031020";
  ctx.fillRect(0, 0, cw, ch);

  if (!originalImage) return;

  const imgW = originalImage.naturalWidth;
  const imgH = originalImage.naturalHeight;
  baseScale   = Math.min(cw / Math.max(imgW, 1), ch / Math.max(imgH, 1));
  displayScale = baseScale * zoomFactor;
  displayW = Math.max(1, Math.round(imgW * displayScale));
  displayH = Math.max(1, Math.round(imgH * displayScale));

  if (imageOffsetX === 0 && imageOffsetY === 0) {
    imageOffsetX = (cw - displayW) / 2;
    imageOffsetY = (ch - displayH) / 2;
  }

  ctx.drawImage(originalImage, imageOffsetX, imageOffsetY, displayW, displayH);
  drawCropOverlay(ctx, cw, ch);
}

function drawCropOverlay(ctx, cw, ch) {
  const [x1, y1, x2, y2] = cropRect;

  // Dark overlay outside crop
  ctx.fillStyle = "rgba(0,0,0,0.45)";
  ctx.fillRect(0, 0, cw, y1);
  ctx.fillRect(0, y2, cw, ch - y2);
  ctx.fillRect(0, y1, x1, y2 - y1);
  ctx.fillRect(x2, y1, cw - x2, y2 - y1);

  // Crop border
  ctx.strokeStyle = "#5eead4";
  ctx.lineWidth = 2;
  ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);

  // Safe zone
  if (safeZone) {
    const mx = (x2 - x1) * 0.08;
    const my = (y2 - y1) * 0.08;
    ctx.strokeStyle = "#f59e0b";
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.strokeRect(x1 + mx, y1 + my, (x2 - x1) - mx * 2, (y2 - y1) - my * 2);
    ctx.setLineDash([]);
  }

  // Handles
  for (const [hx, hy] of getHandlePoints()) {
    const s = HANDLE_SIZE / 2;
    ctx.fillStyle = "#ffffff";
    ctx.strokeStyle = "#1e40af";
    ctx.lineWidth = 1;
    ctx.fillRect(hx - s, hy - s, HANDLE_SIZE, HANDLE_SIZE);
    ctx.strokeRect(hx - s, hy - s, HANDLE_SIZE, HANDLE_SIZE);
  }
}

function getHandlePoints() {
  const [x1, y1, x2, y2] = cropRect;
  const mx = (x1 + x2) / 2;
  const my = (y1 + y2) / 2;
  return [[x1,y1],[mx,y1],[x2,y1],[x1,my],[x2,my],[x1,y2],[mx,y2],[x2,y2]];
}

function detectHandle(x, y) {
  const labels = ["nw","n","ne","w","e","sw","s","se"];
  const points = getHandlePoints();
  for (let i = 0; i < labels.length; i++) {
    const [hx, hy] = points[i];
    if (Math.abs(x - hx) <= HANDLE_SIZE && Math.abs(y - hy) <= HANDLE_SIZE) return labels[i];
  }
  return null;
}

function pointInCrop(x, y) {
  const [x1, y1, x2, y2] = cropRect;
  return x >= x1 && x <= x2 && y >= y1 && y <= y2;
}

function pointInImage(x, y) {
  return x >= imageOffsetX && x <= imageOffsetX + displayW &&
         y >= imageOffsetY && y <= imageOffsetY + displayH;
}

function clampCrop() {
  const canvas = getCanvas();
  const cw = canvas.width;
  const ch = canvas.height;
  const minW = 80, minH = 50;
  let [x1, y1, x2, y2] = cropRect;
  x1 = Math.max(0, Math.min(cw - minW, x1));
  y1 = Math.max(0, Math.min(ch - minH, y1));
  x2 = Math.max(x1 + minW, Math.min(cw, x2));
  y2 = Math.max(y1 + minH, Math.min(ch, y2));
  cropRect = [x1, y1, x2, y2];
}

function resizeCrop(handle, dx, dy) {
  let [x1, y1, x2, y2] = startCropRect;
  if (handle.includes("w")) x1 += dx;
  if (handle.includes("e")) x2 += dx;
  if (handle.includes("n")) y1 += dy;
  if (handle.includes("s")) y2 += dy;
  if (lockRatio) {
    const ratio = currentRatio;
    let w = Math.max(80, x2 - x1);
    let h = Math.max(50, y2 - y1);
    if (Math.abs(dx) >= Math.abs(dy)) {
      h = w / ratio;
      if (handle.includes("n") && !handle.includes("s")) y1 = y2 - h;
      else y2 = y1 + h;
    } else {
      w = h * ratio;
      if (handle.includes("w") && !handle.includes("e")) x1 = x2 - w;
      else x2 = x1 + w;
    }
  }
  cropRect = [x1, y1, x2, y2];
  clampCrop();
}

// Canvas mouse events
(function setupCanvas() {
  window.addEventListener("load", function() {
    syncCanvasSize();
    resetCropRect();
    redrawCanvas();

    const wrap = document.getElementById("crop-canvas-wrap");

    function getPos(e) {
      const rect = wrap.getBoundingClientRect();
      const clientX = e.touches ? e.touches[0].clientX : e.clientX;
      const clientY = e.touches ? e.touches[0].clientY : e.clientY;
      return [clientX - rect.left, clientY - rect.top];
    }

    function onPress(e) {
      const [x, y] = getPos(e);
      resizingHandle = detectHandle(x, y);
      cropDragStart = [x, y];
      startCropRect = [...cropRect];
      startOffset = [imageOffsetX, imageOffsetY];
      if (resizingHandle) {
        draggingCrop = true; draggingImage = false;
      } else if (pointInCrop(x, y)) {
        draggingCrop = true; draggingImage = false;
      } else if (pointInImage(x, y)) {
        draggingImage = true; draggingCrop = false;
      } else {
        draggingCrop = false; draggingImage = false;
      }
      e.preventDefault();
    }

    function onDrag(e) {
      const [x, y] = getPos(e);
      const dx = x - cropDragStart[0];
      const dy = y - cropDragStart[1];
      if (draggingImage) {
        imageOffsetX = startOffset[0] + dx;
        imageOffsetY = startOffset[1] + dy;
        redrawCanvas(); return;
      }
      if (draggingCrop) {
        if (resizingHandle) {
          resizeCrop(resizingHandle, dx, dy);
        } else {
          const [sx1, sy1, sx2, sy2] = startCropRect;
          const w = sx2 - sx1, h = sy2 - sy1;
          cropRect = [sx1 + dx, sy1 + dy, sx1 + dx + w, sy1 + dy + h];
          clampCrop();
        }
        redrawCanvas();
      }
      e.preventDefault();
    }

    function onRelease() {
      draggingCrop = false; draggingImage = false; resizingHandle = null;
    }

    wrap.addEventListener("mousedown",  onPress);
    wrap.addEventListener("mousemove",  onDrag);
    wrap.addEventListener("mouseup",    onRelease);
    wrap.addEventListener("mouseleave", onRelease);
    wrap.addEventListener("touchstart", onPress, { passive: false });
    wrap.addEventListener("touchmove",  onDrag,  { passive: false });
    wrap.addEventListener("touchend",   onRelease);

    // Mousewheel zoom
    wrap.addEventListener("wheel", function(e) {
      const delta = e.deltaY < 0 ? 0.1 : -0.1;
      zoomFactor = Math.min(3.0, Math.max(0.5, zoomFactor + delta));
      document.getElementById("zoom-slider").value = zoomFactor;
      redrawCanvas();
      e.preventDefault();
    }, { passive: false });

    // Redraw on resize
    new ResizeObserver(() => {
      syncCanvasSize();
      redrawCanvas();
    }).observe(wrap);
  });
})();

// ── Apply Crop ────────────────────────────────────────────────────
function applyCrop() {
  if (!originalImage) { setStatus("Please upload an image first"); return; }
  const imgW = originalImage.naturalWidth;
  const imgH = originalImage.naturalHeight;
  const [cx1, cy1, cx2, cy2] = cropRect;

  const left   = Math.max(0, Math.min(imgW, Math.round((cx1 - imageOffsetX) / displayScale)));
  const top    = Math.max(0, Math.min(imgH, Math.round((cy1 - imageOffsetY) / displayScale)));
  const right  = Math.max(left + 1, Math.min(imgW, Math.round((cx2 - imageOffsetX) / displayScale)));
  const bottom = Math.max(top  + 1, Math.min(imgH, Math.round((cy2 - imageOffsetY) / displayScale)));

  const offscreen = document.createElement("canvas");
  offscreen.width  = right - left;
  offscreen.height = bottom - top;
  const ctx = offscreen.getContext("2d");
  ctx.drawImage(originalImage, left, top, right - left, bottom - top, 0, 0, right - left, bottom - top);

  croppedDataUrl = offscreen.toDataURL("image/jpeg", 0.95);
  offscreen.toBlob(blob => {
    croppedBlob = blob;
    setStatus(`Crop applied successfully: ${right - left}x${bottom - top} px`);
  }, "image/jpeg", 0.95);
}

// ── Export <100KB ─────────────────────────────────────────────────
function exportUnder100kb() {
  if (!originalImage && !croppedBlob) {
    setStatus("Please upload or crop an image first"); return;
  }

  const src = croppedDataUrl || getOriginalDataUrl();
  if (!src) { setStatus("Please upload an image first"); return; }

  const img = new Image();
  img.onload = function() {
    // Upscale if needed
    let w = img.width, h = img.height;
    const offscreen = document.createElement("canvas");
    if (w < 1400) {
      const scale = Math.max(1.2, 1400 / Math.max(w, 1));
      w = Math.round(w * scale); h = Math.round(h * scale);
    }
    offscreen.width = w; offscreen.height = h;
    const ctx = offscreen.getContext("2d");
    ctx.drawImage(img, 0, 0, w, h);

    // Find quality under 100KB
    let bestBlob = null, bestQ = 85;
    const tryQ = [95,90,85,80,75,70,65,60,55,50,45,40,35,30,25,20,15];
    let idx = 0;

    function tryNext() {
      if (idx >= tryQ.length) {
        // Still over — shrink
        shrinkAndExport(offscreen, bestQ);
        return;
      }
      const q = tryQ[idx++];
      offscreen.toBlob(blob => {
        if (blob.size / 1024 <= 100) {
          bestBlob = blob; bestQ = q;
          doSave(bestBlob, q);
        } else {
          tryNext();
        }
      }, "image/jpeg", q / 100);
    }

    function shrinkAndExport(canvas, q) {
      let cw = canvas.width, ch = canvas.height;
      const sc2 = document.createElement("canvas");
      sc2.width = cw; sc2.height = ch;
      const c2 = sc2.getContext("2d");
      c2.drawImage(canvas, 0, 0);

      function shrink() {
        sc2.toBlob(blob => {
          if (blob.size / 1024 <= 100 || cw < 400 || ch < 200) {
            doSave(blob, q);
          } else {
            cw = Math.round(cw * 0.92); ch = Math.round(ch * 0.92);
            const tmp = document.createElement("canvas");
            tmp.width = cw; tmp.height = ch;
            tmp.getContext("2d").drawImage(sc2, 0, 0, cw, ch);
            sc2.width = cw; sc2.height = ch;
            sc2.getContext("2d").drawImage(tmp, 0, 0);
            shrink();
          }
        }, "image/jpeg", q / 100);
      }
      shrink();
    }

    function doSave(blob, q) {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "optimized.jpg";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      setStatus(`Image saved successfully: ${(blob.size / 1024).toFixed(1)}KB | Quality: ${q}`);
    }

    tryNext();
  };
  img.src = src;
}

function getOriginalDataUrl() {
  if (!originalImage) return null;
  const c = document.createElement("canvas");
  c.width = originalImage.naturalWidth;
  c.height = originalImage.naturalHeight;
  c.getContext("2d").drawImage(originalImage, 0, 0);
  return c.toDataURL("image/jpeg", 0.95);
}

// ── Clear Crop ────────────────────────────────────────────────────
function clearCropOnly() {
  croppedBlob = null;
  croppedDataUrl = null;
  if (originalImage) { resetCropRect(); redrawCanvas(); }
  setStatus("Crop cleared");
}

// ── Generate Image SEO ────────────────────────────────────────────
async function generateImageSeo() {
  if (!originalImageFile && !originalImage) {
    setStatus("Please upload an image first"); return;
  }
  const keyword = document.getElementById("scene-entry").value.trim() || "image SEO";
  const key = getActiveApiKey();

  setStatus("Generating image SEO with Together AI...");

  // Determine which image to send: cropped blob or original file
  let imageBlob = croppedBlob || originalImageFile;
  if (!imageBlob && originalImage) {
    // fallback: create blob from canvas
    imageBlob = await new Promise(res => {
      const c = document.createElement("canvas");
      c.width = originalImage.naturalWidth;
      c.height = originalImage.naturalHeight;
      c.getContext("2d").drawImage(originalImage, 0, 0);
      c.toBlob(b => res(b), "image/jpeg", 0.95);
    });
  }

  const formData = new FormData();
  formData.append("api_key", key);
  formData.append("keyword", keyword);
  formData.append("image", imageBlob, "image.jpg");

  try {
    const res = await fetch("/api/generate-image-seo", {
      method: "POST",
      body: formData,
    });
    const data = await res.json();
    if (!data.ok) {
      setStatus("Image SEO generation failed: " + (data.error || ""));
      return;
    }
    document.getElementById("alt-text").value         = data.alt_text || "";
    document.getElementById("img-title-entry").value  = data.img_title || "";
    document.getElementById("caption-text").value     = data.caption || "";
    setStatus(data.ai ? "Image SEO generated successfully" : "Generated simple image SEO without API");
  } catch (e) {
    setStatus("Error: " + e.message);
  }
}

// ── Copy Image Fields ─────────────────────────────────────────────
function copyImageField(which) {
  const alt     = (document.getElementById("alt-text").value || "").trim();
  const title   = (document.getElementById("img-title-entry").value || "").trim();
  const caption = (document.getElementById("caption-text").value || "").trim();
  const scene   = (document.getElementById("scene-entry").value || "").trim();

  if (which === "alt") {
    if (!alt) { setStatus("No Alt Text to copy"); return; }
    copyToClipboard(alt, "Copied Alt Text");
  } else if (which === "title") {
    if (!title) { setStatus("No Img Title to copy"); return; }
    copyToClipboard(title, "Copied Img Title");
  } else if (which === "caption") {
    if (!caption) { setStatus("No Caption to copy"); return; }
    copyToClipboard(caption, "Copied Caption");
  } else if (which === "all") {
    const content = `Image SEO\n\nKeyword / Scene Notes:\n${scene}\n\nAlt Text:\n${alt}\n\nImg Title:\n${title}\n\nCaption:\n${caption}`;
    copyToClipboard(content, "Copied all image SEO fields");
  }
}

// ── Clear All Image Fields ────────────────────────────────────────
function clearImageFields() {
  document.getElementById("scene-entry").value   = "";
  document.getElementById("alt-text").value      = "";
  document.getElementById("img-title-entry").value = "";
  document.getElementById("caption-text").value  = "";
  originalImage = null;
  originalImageFile = null;
  croppedBlob = null;
  croppedDataUrl = null;
  imageOffsetX = 0; imageOffsetY = 0;
  document.getElementById("crop-info-label").textContent = "No image loaded";
  syncCanvasSize();
  resetCropRect();
  const canvas = getCanvas();
  const ctx = getCtx();
  ctx.fillStyle = "#031020";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  setStatus("Cleared all image SEO fields");
}

// ═══════════════════════════════════════════════════════════════════
// INIT
// ═══════════════════════════════════════════════════════════════════
(function init() {
  // Restore saved key
  const saved = localStorage.getItem("together_api_key");
  if (saved) { apiKey = saved; sessionKey = saved; }
  updateApiBadge();

  // Switch initial visual state
  document.getElementById("lock-ratio-switch").classList.toggle("active", lockRatio);
  document.getElementById("safe-zone-switch").classList.toggle("active", safeZone);
})();
