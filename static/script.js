const articleInput = document.getElementById("articleInput");
const formatBtn = document.getElementById("formatBtn");
const clearInputBtn = document.getElementById("clearInputBtn");
const copyAllBtn = document.getElementById("copyAllBtn");
const clearOutputBtn = document.getElementById("clearOutputBtn");
const exportTxtBtn = document.getElementById("exportTxtBtn");
const exportDocxBtn = document.getElementById("exportDocxBtn");
const outputContainer = document.getElementById("outputContainer");
const statusText = document.getElementById("statusText");
const themeToggle = document.getElementById("themeToggle");
const copyButtons = document.querySelectorAll(".copy-chip");
const seoTitleLength = document.getElementById("seoTitleLength");
const metaLength = document.getElementById("metaLength");
const seoScore = document.getElementById("seoScore");
const seoNotes = document.getElementById("seoNotes");
const seoTitleOptions = document.getElementById("seoTitleOptions");
const metaOptions = document.getElementById("metaOptions");

const imageUpload = document.getElementById("imageUpload");
const imageCanvas = document.getElementById("imageCanvas");
const rotateLeftBtn = document.getElementById("rotateLeftBtn");
const rotateRightBtn = document.getElementById("rotateRightBtn");
const flipXBtn = document.getElementById("flipXBtn");
const flipYBtn = document.getElementById("flipYBtn");
const grayscaleBtn = document.getElementById("grayscaleBtn");
const resetImageBtn = document.getElementById("resetImageBtn");
const brightnessRange = document.getElementById("brightnessRange");
const contrastRange = document.getElementById("contrastRange");
const downloadImageBtn = document.getElementById("downloadImageBtn");
const toggleCropBtn = document.getElementById("toggleCropBtn");
const applyCropBtn = document.getElementById("applyCropBtn");
const overlayTextInput = document.getElementById("overlayTextInput");
const overlayFontSizeRange = document.getElementById("overlayFontSizeRange");
const overlayColorInput = document.getElementById("overlayColorInput");
const overlayXRange = document.getElementById("overlayXRange");
const overlayYRange = document.getElementById("overlayYRange");
const applyTextBtn = document.getElementById("applyTextBtn");
const clearTextBtn = document.getElementById("clearTextBtn");
const watermarkInput = document.getElementById("watermarkInput");
const watermarkSizeRange = document.getElementById("watermarkSizeRange");
const watermarkOpacityRange = document.getElementById("watermarkOpacityRange");
const applyWatermarkBtn = document.getElementById("applyWatermarkBtn");
const clearWatermarkBtn = document.getElementById("clearWatermarkBtn");
const presetYoutubeBtn = document.getElementById("presetYoutubeBtn");
const presetFacebookBtn = document.getElementById("presetFacebookBtn");
const presetTikTokBtn = document.getElementById("presetTikTokBtn");
const presetSquareBtn = document.getElementById("presetSquareBtn");
const upscale2xBtn = document.getElementById("upscale2xBtn");
const upscale4xBtn = document.getElementById("upscale4xBtn");

let currentResult = {};

function setStatus(message, type = "normal") {
  statusText.textContent = message;
  if (type === "success") statusText.style.color = "var(--success)";
  else if (type === "warning") statusText.style.color = "var(--warning)";
  else if (type === "accent") statusText.style.color = "var(--accent)";
  else statusText.style.color = "var(--muted)";
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function renderOptionList(container, items, prefix) {
  container.innerHTML = "";
  items.forEach((item, index) => {
    const btn = document.createElement("button");
    btn.className = "option-item";
    btn.textContent = `${prefix} ${index + 1}: ${item}`;
    btn.addEventListener("click", async () => {
      await copyText(item, `${prefix} ${index + 1} copied.`);
    });
    container.appendChild(btn);
  });
}

function renderOutput(data) {
  const mainSections = [
    "H1 Tag",
    "Introduction",
    "H2 Tags",
    "Main Content Body",
    "Internal Link Placeholder",
    "Conclusion & CTA"
  ];

  const seoSections = [
    "Focus Keyphrase",
    "SEO Title",
    "Meta Description",
    "Image Alt Text",
    "Image Title",
    "Slug (URL)",
    "Short Summary (20-second video)",
    "Video Script",
    "Caption",
    "Hashtags"
  ];

  let html = "";

  mainSections.forEach((key) => {
    html += `
      <div class="output-section">
        <div class="section-title">==================== ${escapeHtml(key.toUpperCase())} ====================</div>
        <div class="section-content">${escapeHtml(data[key] || "")}</div>
      </div>
    `;
  });

  html += `
    <div class="output-section">
      <div class="section-title">==================== SEO TECHNICAL DETAILS ====================</div>
    </div>
  `;

  seoSections.forEach((key) => {
    html += `
      <div class="output-section">
        <div class="field-title">${escapeHtml(key)}:</div>
        <div class="section-content">${escapeHtml(data[key] || "")}</div>
      </div>
    `;
  });

  outputContainer.innerHTML = html;
  seoTitleLength.textContent = data.Counters?.seo_title_length || 0;
  metaLength.textContent = data.Counters?.meta_length || 0;
  seoScore.textContent = data["SEO Score"]?.score || 0;

  const notes = data["SEO Score"]?.notes || [];
  seoNotes.innerHTML = notes.map(note => `<div class="seo-note-item">• ${escapeHtml(note)}</div>`).join("");

  renderOptionList(seoTitleOptions, data["SEO Title Options"] || [], "Title");
  renderOptionList(metaOptions, data["Meta Description Options"] || [], "Meta");
}

function buildCopyAllText(data) {
  const titleOptions = (data["SEO Title Options"] || []).map(x => `- ${x}`).join("\n");
  const metaOptionsText = (data["Meta Description Options"] || []).map(x => `- ${x}`).join("\n");

  return `
==================== H1 TAG ====================
${data["H1 Tag"] || ""}

==================== INTRODUCTION ====================
${data["Introduction"] || ""}

==================== H2 TAGS ====================
${data["H2 Tags"] || ""}

==================== MAIN CONTENT BODY ====================
${data["Main Content Body"] || ""}

==================== INTERNAL LINK PLACEHOLDER ====================
${data["Internal Link Placeholder"] || ""}

==================== CONCLUSION & CTA ====================
${data["Conclusion & CTA"] || ""}

==================== SEO TECHNICAL DETAILS ====================

Focus Keyphrase:
${data["Focus Keyphrase"] || ""}

SEO Title:
${data["SEO Title"] || ""}

SEO Title Options:
${titleOptions}

Meta Description:
${data["Meta Description"] || ""}

Meta Description Options:
${metaOptionsText}

Image Alt Text:
${data["Image Alt Text"] || ""}

Image Title:
${data["Image Title"] || ""}

Slug (URL):
${data["Slug (URL)"] || ""}

Short Summary (20-second video):
${data["Short Summary (20-second video)"] || ""}

Video Script:
${data["Video Script"] || ""}

Caption:
${data["Caption"] || ""}

Hashtags:
${data["Hashtags"] || ""}

SEO Score:
${data["SEO Score"]?.score || 0}
  `.trim();
}

async function copyText(text, successMessage) {
  try {
    await navigator.clipboard.writeText(text);
    setStatus(successMessage, "success");
  } catch {
    setStatus("Copy failed.", "warning");
  }
}

async function exportFile(url, filename) {
  if (!Object.keys(currentResult).length) {
    setStatus("No output to export.", "warning");
    return;
  }

  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(currentResult)
    });

    if (!response.ok) {
      setStatus("Export failed.", "warning");
      return;
    }

    const blob = await response.blob();
    const link = document.createElement("a");
    link.href = window.URL.createObjectURL(blob);
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();

    setStatus(`${filename} downloaded.`, "success");
  } catch {
    setStatus("Export failed.", "warning");
  }
}

formatBtn.addEventListener("click", async () => {
  const article = articleInput.value.trim();
  if (!article) {
    setStatus("Please paste article content first.", "warning");
    return;
  }

  setStatus("Formatting SEO content...", "accent");

  try {
    const response = await fetch("/format", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ article })
    });

    const data = await response.json();
    if (!response.ok) {
      setStatus(data.error || "Something went wrong.", "warning");
      return;
    }

    currentResult = data;
    renderOutput(data);
    setStatus("SEO content formatted successfully.", "success");
  } catch {
    setStatus("Server error. Please try again.", "warning");
  }
});

clearInputBtn.addEventListener("click", () => {
  articleInput.value = "";
  setStatus("Input cleared.", "accent");
});

clearOutputBtn.addEventListener("click", () => {
  currentResult = {};
  outputContainer.innerHTML = `<div class="empty-state">Formatted SEO output will appear here.</div>`;
  seoTitleLength.textContent = "0";
  metaLength.textContent = "0";
  seoScore.textContent = "0";
  seoNotes.innerHTML = "";
  seoTitleOptions.innerHTML = "";
  metaOptions.innerHTML = "";
  setStatus("Output cleared.", "accent");
});

copyAllBtn.addEventListener("click", async () => {
  if (!Object.keys(currentResult).length) {
    setStatus("No output to copy.", "warning");
    return;
  }
  await copyText(buildCopyAllText(currentResult), "All output copied.");
});

copyButtons.forEach((btn) => {
  btn.addEventListener("click", async () => {
    const section = btn.dataset.section;
    const value = currentResult[section];
    if (!value) {
      setStatus(`No content for ${section}.`, "warning");
      return;
    }
    await copyText(value, `${section} copied.`);
  });
});

exportTxtBtn.addEventListener("click", async () => {
  await exportFile("/export/txt", "seo_output.txt");
});

exportDocxBtn.addEventListener("click", async () => {
  await exportFile("/export/docx", "seo_output.docx");
});

themeToggle.addEventListener("click", () => {
  document.body.classList.toggle("light-theme");
  const isLight = document.body.classList.contains("light-theme");
  setStatus(`Theme changed to ${isLight ? "light" : "dark"}.`, "accent");
});

/* IMAGE EDITOR V5 */
const ctx = imageCanvas.getContext("2d");
let loadedImage = null;

let imageState = {
  rotation: 0,
  flipX: 1,
  flipY: 1,
  grayscale: false,
  brightness: 100,
  contrast: 100,
  overlayText: "",
  overlayFontSize: 42,
  overlayColor: "#ffffff",
  overlayX: 50,
  overlayY: 85,
  watermarkText: "",
  watermarkSize: 22,
  watermarkOpacity: 35,
  cropMode: false,
  cropRect: { x: 80, y: 80, w: 260, h: 180 }
};

let dragMode = null;
let dragOffset = { x: 0, y: 0 };

function resetImageState() {
  imageState = {
    rotation: 0,
    flipX: 1,
    flipY: 1,
    grayscale: false,
    brightness: 100,
    contrast: 100,
    overlayText: "",
    overlayFontSize: 42,
    overlayColor: "#ffffff",
    overlayX: 50,
    overlayY: 85,
    watermarkText: "",
    watermarkSize: 22,
    watermarkOpacity: 35,
    cropMode: false,
    cropRect: { x: 80, y: 80, w: 260, h: 180 }
  };

  brightnessRange.value = 100;
  contrastRange.value = 100;
  overlayTextInput.value = "";
  overlayFontSizeRange.value = 42;
  overlayColorInput.value = "#ffffff";
  overlayXRange.value = 50;
  overlayYRange.value = 85;
  watermarkInput.value = "";
  watermarkSizeRange.value = 22;
  watermarkOpacityRange.value = 35;
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function drawCropOverlay() {
  const { x, y, w, h } = imageState.cropRect;
  ctx.save();
  ctx.fillStyle = "rgba(0,0,0,0.35)";
  ctx.fillRect(0, 0, imageCanvas.width, imageCanvas.height);
  ctx.clearRect(x, y, w, h);
  ctx.strokeStyle = "#5da9ff";
  ctx.lineWidth = 2;
  ctx.strokeRect(x, y, w, h);

  const handles = [
    [x, y], [x + w, y], [x, y + h], [x + w, y + h]
  ];

  ctx.fillStyle = "#ffffff";
  handles.forEach(([hx, hy]) => {
    ctx.fillRect(hx - 6, hy - 6, 12, 12);
  });
  ctx.restore();
}

function drawTextOverlay() {
  if (!imageState.overlayText) return;
  ctx.save();
  ctx.font = `bold ${imageState.overlayFontSize}px Segoe UI, Arial`;
  ctx.fillStyle = imageState.overlayColor;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.lineWidth = 4;
  ctx.strokeStyle = "rgba(0,0,0,0.45)";
  const x = (imageState.overlayX / 100) * imageCanvas.width;
  const y = (imageState.overlayY / 100) * imageCanvas.height;
  ctx.strokeText(imageState.overlayText, x, y);
  ctx.fillText(imageState.overlayText, x, y);
  ctx.restore();
}

function drawWatermark() {
  if (!imageState.watermarkText) return;
  ctx.save();
  ctx.globalAlpha = imageState.watermarkOpacity / 100;
  ctx.font = `${imageState.watermarkSize}px Segoe UI, Arial`;
  ctx.fillStyle = "#ffffff";
  ctx.textAlign = "right";
  ctx.textBaseline = "bottom";
  ctx.fillText(imageState.watermarkText, imageCanvas.width - 20, imageCanvas.height - 20);
  ctx.restore();
}

function drawImageToCanvas() {
  if (!loadedImage) return;

  const radians = (imageState.rotation * Math.PI) / 180;
  const rotated = imageState.rotation % 180 !== 0;

  const w = loadedImage.width;
  const h = loadedImage.height;
  const canvasW = rotated ? h : w;
  const canvasH = rotated ? w : h;

  imageCanvas.width = canvasW;
  imageCanvas.height = canvasH;

  ctx.save();
  ctx.clearRect(0, 0, imageCanvas.width, imageCanvas.height);
  ctx.filter = `brightness(${imageState.brightness}%) contrast(${imageState.contrast}%) grayscale(${imageState.grayscale ? 100 : 0}%)`;

  ctx.translate(imageCanvas.width / 2, imageCanvas.height / 2);
  ctx.rotate(radians);
  ctx.scale(imageState.flipX, imageState.flipY);
  ctx.drawImage(loadedImage, -w / 2, -h / 2, w, h);
  ctx.restore();

  drawTextOverlay();
  drawWatermark();

  if (imageState.cropMode) {
    drawCropOverlay();
  }
}

function commitCanvasAsImage() {
  const img = new Image();
  img.onload = () => {
    loadedImage = img;
    imageState.rotation = 0;
    imageState.flipX = 1;
    imageState.flipY = 1;
    imageState.grayscale = false;
    imageState.brightness = 100;
    imageState.contrast = 100;
    drawImageToCanvas();
  };
  img.src = imageCanvas.toDataURL("image/png");
}

function applyPreset(width, height) {
  if (!loadedImage) {
    setStatus("Upload image first.", "warning");
    return;
  }

  const tempCanvas = document.createElement("canvas");
  const tempCtx = tempCanvas.getContext("2d");
  tempCanvas.width = width;
  tempCanvas.height = height;

  tempCtx.imageSmoothingEnabled = true;
  tempCtx.imageSmoothingQuality = "high";

  const srcRatio = imageCanvas.width / imageCanvas.height;
  const destRatio = width / height;

  let drawW, drawH, offsetX, offsetY;
  if (srcRatio > destRatio) {
    drawH = height;
    drawW = drawH * srcRatio;
    offsetX = (width - drawW) / 2;
    offsetY = 0;
  } else {
    drawW = width;
    drawH = drawW / srcRatio;
    offsetX = 0;
    offsetY = (height - drawH) / 2;
  }

  tempCtx.drawImage(imageCanvas, offsetX, offsetY, drawW, drawH);

  const img = new Image();
  img.onload = () => {
    loadedImage = img;
    resetImageState();
    drawImageToCanvas();
    setStatus(`Preset applied: ${width}x${height}`, "success");
  };
  img.src = tempCanvas.toDataURL("image/png");
}

function upscaleSmooth(scale) {
  if (!loadedImage) {
    setStatus("Upload image first.", "warning");
    return;
  }

  const src = imageCanvas;
  const tempCanvas = document.createElement("canvas");
  const tempCtx = tempCanvas.getContext("2d");

  tempCanvas.width = src.width * scale;
  tempCanvas.height = src.height * scale;

  tempCtx.imageSmoothingEnabled = true;
  tempCtx.imageSmoothingQuality = "high";
  tempCtx.drawImage(src, 0, 0, tempCanvas.width, tempCanvas.height);

  // mild sharpen
  const imgData = tempCtx.getImageData(0, 0, tempCanvas.width, tempCanvas.height);
  const data = imgData.data;
  for (let i = 0; i < data.length; i += 4) {
    data[i] = clamp(data[i] * 1.02, 0, 255);
    data[i + 1] = clamp(data[i + 1] * 1.02, 0, 255);
    data[i + 2] = clamp(data[i + 2] * 1.02, 0, 255);
  }
  tempCtx.putImageData(imgData, 0, 0);

  const img = new Image();
  img.onload = () => {
    loadedImage = img;
    resetImageState();
    drawImageToCanvas();
    setStatus(`Smooth upscale ${scale}x applied.`, "success");
  };
  img.src = tempCanvas.toDataURL("image/png");
}

function getMousePos(evt) {
  const rect = imageCanvas.getBoundingClientRect();
  const scaleX = imageCanvas.width / rect.width;
  const scaleY = imageCanvas.height / rect.height;

  return {
    x: (evt.clientX - rect.left) * scaleX,
    y: (evt.clientY - rect.top) * scaleY
  };
}

function getCropHandle(pos) {
  const { x, y, w, h } = imageState.cropRect;
  const handles = {
    tl: { x, y },
    tr: { x: x + w, y },
    bl: { x, y: y + h },
    br: { x: x + w, y: y + h }
  };

  for (const key in handles) {
    const hx = handles[key].x;
    const hy = handles[key].y;
    if (Math.abs(pos.x - hx) <= 12 && Math.abs(pos.y - hy) <= 12) {
      return key;
    }
  }

  if (pos.x >= x && pos.x <= x + w && pos.y >= y && pos.y <= y + h) {
    return "move";
  }

  return null;
}

imageCanvas.addEventListener("mousedown", (evt) => {
  if (!loadedImage || !imageState.cropMode) return;
  const pos = getMousePos(evt);
  const handle = getCropHandle(pos);
  if (!handle) return;

  dragMode = handle;
  dragOffset.x = pos.x;
  dragOffset.y = pos.y;
});

imageCanvas.addEventListener("mousemove", (evt) => {
  if (!loadedImage || !imageState.cropMode || !dragMode) return;
  const pos = getMousePos(evt);
  const dx = pos.x - dragOffset.x;
  const dy = pos.y - dragOffset.y;
  const rect = imageState.cropRect;
  const minSize = 40;

  if (dragMode === "move") {
    rect.x = clamp(rect.x + dx, 0, imageCanvas.width - rect.w);
    rect.y = clamp(rect.y + dy, 0, imageCanvas.height - rect.h);
  } else if (dragMode === "tl") {
    rect.x = clamp(rect.x + dx, 0, rect.x + rect.w - minSize);
    rect.y = clamp(rect.y + dy, 0, rect.y + rect.h - minSize);
    rect.w = rect.w - dx;
    rect.h = rect.h - dy;
  } else if (dragMode === "tr") {
    rect.y = clamp(rect.y + dy, 0, rect.y + rect.h - minSize);
    rect.w = clamp(rect.w + dx, minSize, imageCanvas.width - rect.x);
    rect.h = rect.h - dy;
  } else if (dragMode === "bl") {
    rect.x = clamp(rect.x + dx, 0, rect.x + rect.w - minSize);
    rect.w = rect.w - dx;
    rect.h = clamp(rect.h + dy, minSize, imageCanvas.height - rect.y);
  } else if (dragMode === "br") {
    rect.w = clamp(rect.w + dx, minSize, imageCanvas.width - rect.x);
    rect.h = clamp(rect.h + dy, minSize, imageCanvas.height - rect.y);
  }

  dragOffset = pos;
  drawImageToCanvas();
});

window.addEventListener("mouseup", () => {
  dragMode = null;
});

imageUpload.addEventListener("change", (event) => {
  const file = event.target.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = () => {
    const img = new Image();
    img.onload = () => {
      loadedImage = img;
      resetImageState();
      imageState.cropRect = {
        x: img.width * 0.15,
        y: img.height * 0.15,
        w: img.width * 0.7,
        h: img.height * 0.7
      };
      drawImageToCanvas();
      setStatus("Image uploaded successfully.", "success");
    };
    img.src = reader.result;
  };
  reader.readAsDataURL(file);
});

rotateLeftBtn.addEventListener("click", () => {
  if (!loadedImage) return setStatus("Upload image first.", "warning");
  imageState.rotation = (imageState.rotation - 90 + 360) % 360;
  drawImageToCanvas();
});

rotateRightBtn.addEventListener("click", () => {
  if (!loadedImage) return setStatus("Upload image first.", "warning");
  imageState.rotation = (imageState.rotation + 90) % 360;
  drawImageToCanvas();
});

flipXBtn.addEventListener("click", () => {
  if (!loadedImage) return setStatus("Upload image first.", "warning");
  imageState.flipX *= -1;
  drawImageToCanvas();
});

flipYBtn.addEventListener("click", () => {
  if (!loadedImage) return setStatus("Upload image first.", "warning");
  imageState.flipY *= -1;
  drawImageToCanvas();
});

grayscaleBtn.addEventListener("click", () => {
  if (!loadedImage) return setStatus("Upload image first.", "warning");
  imageState.grayscale = !imageState.grayscale;
  drawImageToCanvas();
});

brightnessRange.addEventListener("input", () => {
  if (!loadedImage) return;
  imageState.brightness = Number(brightnessRange.value);
  drawImageToCanvas();
});

contrastRange.addEventListener("input", () => {
  if (!loadedImage) return;
  imageState.contrast = Number(contrastRange.value);
  drawImageToCanvas();
});

resetImageBtn.addEventListener("click", () => {
  if (!loadedImage) return setStatus("Upload image first.", "warning");
  resetImageState();
  drawImageToCanvas();
  setStatus("Image reset.", "accent");
});

toggleCropBtn.addEventListener("click", () => {
  if (!loadedImage) return setStatus("Upload image first.", "warning");
  imageState.cropMode = !imageState.cropMode;
  drawImageToCanvas();
  setStatus(`Crop mode ${imageState.cropMode ? "enabled" : "disabled"}.`, "accent");
});

applyCropBtn.addEventListener("click", () => {
  if (!loadedImage) return setStatus("Upload image first.", "warning");

  const { x, y, w, h } = imageState.cropRect;
  const tempCanvas = document.createElement("canvas");
  const tempCtx = tempCanvas.getContext("2d");
  tempCanvas.width = Math.round(w);
  tempCanvas.height = Math.round(h);
  tempCtx.drawImage(imageCanvas, x, y, w, h, 0, 0, tempCanvas.width, tempCanvas.height);

  const img = new Image();
  img.onload = () => {
    loadedImage = img;
    imageState.cropMode = false;
    imageState.cropRect = { x: 40, y: 40, w: img.width * 0.7, h: img.height * 0.7 };
    drawImageToCanvas();
    setStatus("Crop applied.", "success");
  };
  img.src = tempCanvas.toDataURL("image/png");
});

applyTextBtn.addEventListener("click", () => {
  if (!loadedImage) return setStatus("Upload image first.", "warning");
  imageState.overlayText = overlayTextInput.value.trim();
  imageState.overlayFontSize = Number(overlayFontSizeRange.value);
  imageState.overlayColor = overlayColorInput.value;
  imageState.overlayX = Number(overlayXRange.value);
  imageState.overlayY = Number(overlayYRange.value);
  drawImageToCanvas();
  setStatus("Text overlay applied.", "success");
});

clearTextBtn.addEventListener("click", () => {
  imageState.overlayText = "";
  overlayTextInput.value = "";
  drawImageToCanvas();
  setStatus("Text overlay cleared.", "accent");
});

applyWatermarkBtn.addEventListener("click", () => {
  if (!loadedImage) return setStatus("Upload image first.", "warning");
  imageState.watermarkText = watermarkInput.value.trim();
  imageState.watermarkSize = Number(watermarkSizeRange.value);
  imageState.watermarkOpacity = Number(watermarkOpacityRange.value);
  drawImageToCanvas();
  setStatus("Watermark applied.", "success");
});

clearWatermarkBtn.addEventListener("click", () => {
  imageState.watermarkText = "";
  watermarkInput.value = "";
  drawImageToCanvas();
  setStatus("Watermark cleared.", "accent");
});

presetYoutubeBtn.addEventListener("click", () => applyPreset(1280, 720));
presetFacebookBtn.addEventListener("click", () => applyPreset(1200, 630));
presetTikTokBtn.addEventListener("click", () => applyPreset(1080, 1920));
presetSquareBtn.addEventListener("click", () => applyPreset(1080, 1080));

upscale2xBtn.addEventListener("click", () => upscaleSmooth(2));
upscale4xBtn.addEventListener("click", () => upscaleSmooth(4));

downloadImageBtn.addEventListener("click", () => {
  if (!loadedImage) return setStatus("Upload image first.", "warning");
  const link = document.createElement("a");
  link.download = "edited-image.png";
  link.href = imageCanvas.toDataURL("image/png");
  link.click();
  setStatus("Edited image downloaded.", "success");
});
