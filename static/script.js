const state = {
  processed: null,
  selectedPreset: { width: 1200, height: 366 },
  uploadedFile: null,
  crop: { x: 20, y: 20, width: 240, height: 120 },
  dragging: false,
  dragOffsetX: 0,
  dragOffsetY: 0,
  latestImageDataUri: ""
};

const els = {
  articleInput: document.getElementById("articleInput"),
  seoPreview: document.getElementById("seoPreview"),
  focusKeyphrase: document.getElementById("focusKeyphrase"),
  seoTitle: document.getElementById("seoTitle"),
  metaDescription: document.getElementById("metaDescription"),
  slug: document.getElementById("slug"),
  shortSummary: document.getElementById("shortSummary"),
  wpHtmlOutput: document.getElementById("wpHtmlOutput"),

  generateBtn: document.getElementById("generateBtn"),
  clearInputBtn: document.getElementById("clearInputBtn"),
  exportHtmlBtn: document.getElementById("exportHtmlBtn"),
  exportTxtBtn: document.getElementById("exportTxtBtn"),
  copyWpHtmlBtn: document.getElementById("copyWpHtmlBtn"),
  clearOutputBtn: document.getElementById("clearOutputBtn"),

  imageInput: document.getElementById("imageInput"),
  sourceImage: document.getElementById("sourceImage"),
  cropBox: document.getElementById("cropBox"),
  croppedPreview: document.getElementById("croppedPreview"),
  imageMeta: document.getElementById("imageMeta"),
  sceneNotes: document.getElementById("sceneNotes"),
  altText: document.getElementById("altText"),
  imgTitle: document.getElementById("imgTitle"),
  caption: document.getElementById("caption"),
  applyCropBtn: document.getElementById("applyCropBtn"),
  exportUnder100Btn: document.getElementById("exportUnder100Btn"),
  generateImageSeoBtn: document.getElementById("generateImageSeoBtn"),

  toast: document.getElementById("toast")
};

function showToast(message) {
  els.toast.textContent = message;
  els.toast.classList.add("show");
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(() => {
    els.toast.classList.remove("show");
  }, 2200);
}

function renderPreview(data) {
  const blocks = [];
  if (data.h1) blocks.push(`<h1>${escapeHtml(data.h1)}</h1>`);
  if (data.intro) blocks.push(`<p>${escapeHtml(data.intro)}</p>`);

  (data.structure || []).forEach(sec => {
    blocks.push(`<h2>${escapeHtml(sec.h2 || "")}</h2>`);
    (sec.subsections || []).forEach(sub => {
      if (sub.h3) blocks.push(`<h3>${escapeHtml(sub.h3)}</h3>`);
      if (sub.h4) blocks.push(`<h4>${escapeHtml(sub.h4)}</h4>`);
      if (sub.body) blocks.push(`<p>${escapeHtml(sub.body).replace(/\n\n/g, "<br><br>")}</p>`);
    });
  });

  els.seoPreview.innerHTML = blocks.join("");
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text || "";
  return div.innerHTML;
}

async function generateArticle() {
  const article = els.articleInput.value.trim();
  if (!article) {
    showToast("Please paste an article first");
    return;
  }

  const res = await fetch("/api/process", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ article })
  });

  const data = await res.json();
  if (!data.ok) {
    showToast(data.error || "Failed");
    return;
  }

  state.processed = data;
  renderPreview(data);

  els.focusKeyphrase.value = data.focus_keyphrase || "";
  els.seoTitle.value = data.seo_title || "";
  els.metaDescription.value = data.meta_description || "";
  els.slug.value = data.slug || "";
  els.shortSummary.value = data.short_summary || "";
  els.wpHtmlOutput.value = data.wp_html || "";

  showToast("SEO output generated");
}

function clearInput() {
  els.articleInput.value = "";
}

function clearOutput() {
  els.seoPreview.innerHTML = `<p class="muted">Formatted SEO output will appear here.</p>`;
  els.focusKeyphrase.value = "";
  els.seoTitle.value = "";
  els.metaDescription.value = "";
  els.slug.value = "";
  els.shortSummary.value = "";
  els.wpHtmlOutput.value = "";
  state.processed = null;
}

async function copyWpHtml() {
  const text = els.wpHtmlOutput.value.trim();
  if (!text) {
    showToast("Nothing to copy");
    return;
  }
  await navigator.clipboard.writeText(text);
  showToast("WP HTML copied");
}

async function copyField(targetId) {
  const el = document.getElementById(targetId);
  if (!el || !el.value) {
    showToast("Nothing to copy");
    return;
  }
  await navigator.clipboard.writeText(el.value);
  showToast("Copied");
}

async function exportTxt() {
  const text = state.processed?.plain_text || "";
  if (!text) {
    showToast("Nothing to export");
    return;
  }

  const res = await fetch("/api/export-txt", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text })
  });

  const blob = await res.blob();
  downloadBlob(blob, "seo-output.txt");
}

async function exportHtml() {
  if (!state.processed) {
    showToast("Nothing to export");
    return;
  }

  const payload = {
    h1: state.processed.h1 || "",
    wp_html: els.wpHtmlOutput.value || ""
  };

  const res = await fetch("/api/export-html", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });

  const blob = await res.blob();
  downloadBlob(blob, "seo-output.html");
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function loadImage(file) {
  state.uploadedFile = file;
  const reader = new FileReader();
  reader.onload = () => {
    els.sourceImage.src = reader.result;
    els.sourceImage.style.display = "block";

    els.sourceImage.onload = () => {
      initCropBox();
    };
  };
  reader.readAsDataURL(file);
}

function initCropBox() {
  const img = els.sourceImage;
  const box = els.cropBox;
  const wrap = img.parentElement.getBoundingClientRect();
  const imgRect = img.getBoundingClientRect();

  const initialWidth = Math.min(imgRect.width * 0.7, 320);
  const ratio = state.selectedPreset.width / state.selectedPreset.height;
  const initialHeight = initialWidth / ratio;

  const left = imgRect.left - wrap.left + (imgRect.width - initialWidth) / 2;
  const top = imgRect.top - wrap.top + (imgRect.height - initialHeight) / 2;

  state.crop = {
    x: left,
    y: top,
    width: initialWidth,
    height: initialHeight
  };

  updateCropBox();
}

function updateCropBox() {
  const box = els.cropBox;
  box.style.display = "block";
  box.style.left = `${state.crop.x}px`;
  box.style.top = `${state.crop.y}px`;
  box.style.width = `${state.crop.width}px`;
  box.style.height = `${state.crop.height}px`;
}

function setPreset(w, h) {
  state.selectedPreset = { width: Number(w), height: Number(h) };
  if (els.sourceImage.src) {
    initCropBox();
  }
  showToast(`Preset ${w}x${h} ready`);
}

function attachCropEvents() {
  els.cropBox.addEventListener("mousedown", (e) => {
    state.dragging = true;
    const rect = els.cropBox.getBoundingClientRect();
    state.dragOffsetX = e.clientX - rect.left;
    state.dragOffsetY = e.clientY - rect.top;
  });

  window.addEventListener("mousemove", (e) => {
    if (!state.dragging) return;

    const wrapRect = els.sourceImage.parentElement.getBoundingClientRect();
    const imgRect = els.sourceImage.getBoundingClientRect();

    let x = e.clientX - wrapRect.left - state.dragOffsetX;
    let y = e.clientY - wrapRect.top - state.dragOffsetY;

    const minX = imgRect.left - wrapRect.left;
    const minY = imgRect.top - wrapRect.top;
    const maxX = minX + imgRect.width - state.crop.width;
    const maxY = minY + imgRect.height - state.crop.height;

    x = Math.max(minX, Math.min(x, maxX));
    y = Math.max(minY, Math.min(y, maxY));

    state.crop.x = x;
    state.crop.y = y;
    updateCropBox();
  });

  window.addEventListener("mouseup", () => {
    state.dragging = false;
  });
}

function getRealCropValues() {
  const imgRect = els.sourceImage.getBoundingClientRect();
  const wrapRect = els.sourceImage.parentElement.getBoundingClientRect();

  const displayX = state.crop.x - (imgRect.left - wrapRect.left);
  const displayY = state.crop.y - (imgRect.top - wrapRect.top);

  const scaleX = els.sourceImage.naturalWidth / imgRect.width;
  const scaleY = els.sourceImage.naturalHeight / imgRect.height;

  return {
    x: Math.round(displayX * scaleX),
    y: Math.round(displayY * scaleY),
    width: Math.round(state.crop.width * scaleX),
    height: Math.round(state.crop.height * scaleY)
  };
}

async function cropImage(exportUnder100kb = false) {
  if (!state.uploadedFile) {
    showToast("Please open an image first");
    return;
  }

  const real = getRealCropValues();
  const form = new FormData();
  form.append("image", state.uploadedFile);
  form.append("x", real.x);
  form.append("y", real.y);
  form.append("width", real.width);
  form.append("height", real.height);
  form.append("target_width", state.selectedPreset.width);
  form.append("target_height", state.selectedPreset.height);
  form.append("export_under_100kb", exportUnder100kb ? "true" : "false");

  const res = await fetch("/api/crop-image", {
    method: "POST",
    body: form
  });

  const data = await res.json();
  if (!data.ok) {
    showToast(data.error || "Crop failed");
    return null;
  }

  state.latestImageDataUri = data.image_data_uri;
  els.croppedPreview.src = data.image_data_uri;
  els.imageMeta.textContent = exportUnder100kb
    ? `Preview size: ${data.width} x ${data.height} • ${data.size_kb}KB`
    : `Preview size: ${data.width} x ${data.height}`;

  showToast(exportUnder100kb ? "Exported preview under 100KB" : "Crop applied");
  updateWpHtmlWithImage();
  return data;
}

function updateWpHtmlWithImage() {
  if (!state.processed) return;

  const h1 = state.processed.h1 || "";
  const intro = state.processed.intro || "";
  const structure = state.processed.structure || [];
  const altText = els.altText.value || h1 || "Featured image";
  const imgTitle = els.imgTitle.value || h1 || "Featured image";
  const caption = els.caption.value || "";

  let htmlParts = [];

  if (state.latestImageDataUri) {
    let fig = `<figure class="wp-block-image size-full featured-image-wrap">`;
    fig += `<img src="${state.latestImageDataUri}" alt="${escapeHtml(altText)}" title="${escapeHtml(imgTitle)}" />`;
    if (caption) fig += `<figcaption>${escapeHtml(caption)}</figcaption>`;
    fig += `</figure>`;
    htmlParts.push(fig);
  }

  if (h1) htmlParts.push(`<h1>${escapeHtml(h1)}</h1>`);
  if (intro) htmlParts.push(`<p>${escapeHtml(intro)}</p>`);

  structure.forEach(sec => {
    if (sec.h2) htmlParts.push(`<h2>${escapeHtml(sec.h2)}</h2>`);
    (sec.subsections || []).forEach(sub => {
      if (sub.h3) htmlParts.push(`<h3>${escapeHtml(sub.h3)}</h3>`);
      if (sub.h4) htmlParts.push(`<h4>${escapeHtml(sub.h4)}</h4>`);
      if (sub.body) {
        const paragraphs = sub.body.split("\n\n").filter(Boolean);
        paragraphs.forEach(p => htmlParts.push(`<p>${escapeHtml(p)}</p>`));
      }
    });
  });

  els.wpHtmlOutput.value = htmlParts.join("\n");
}

async function generateImageSeo() {
  const payload = {
    h1: state.processed?.h1 || "",
    intro: state.processed?.intro || "",
    focus_keyphrase: els.focusKeyphrase.value || "",
    scene_notes: els.sceneNotes.value || ""
  };

  const res = await fetch("/api/image-seo", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });

  const data = await res.json();
  if (!data.ok) {
    showToast("Image SEO failed");
    return;
  }

  els.altText.value = data.alt_text || "";
  els.imgTitle.value = data.img_title || "";
  els.caption.value = data.caption || "";
  updateWpHtmlWithImage();
  showToast("Generated image SEO");
}

els.generateBtn.addEventListener("click", generateArticle);
els.clearInputBtn.addEventListener("click", clearInput);
els.clearOutputBtn.addEventListener("click", clearOutput);
els.copyWpHtmlBtn.addEventListener("click", copyWpHtml);
els.exportTxtBtn.addEventListener("click", exportTxt);
els.exportHtmlBtn.addEventListener("click", exportHtml);

document.querySelectorAll("[data-copy-target]").forEach(btn => {
  btn.addEventListener("click", () => copyField(btn.dataset.copyTarget));
});

els.imageInput.addEventListener("change", (e) => {
  const file = e.target.files?.[0];
  if (file) loadImage(file);
});

document.querySelectorAll(".preset-btn").forEach(btn => {
  btn.addEventListener("click", () => setPreset(btn.dataset.width, btn.dataset.height));
});

els.applyCropBtn.addEventListener("click", () => cropImage(false));
els.exportUnder100Btn.addEventListener("click", () => cropImage(true));
els.generateImageSeoBtn.addEventListener("click", generateImageSeo);

["input", "change"].forEach(evt => {
  els.altText.addEventListener(evt, updateWpHtmlWithImage);
  els.imgTitle.addEventListener(evt, updateWpHtmlWithImage);
  els.caption.addEventListener(evt, updateWpHtmlWithImage);
  els.seoTitle.addEventListener(evt, () => {});
  els.metaDescription.addEventListener(evt, () => {});
  els.slug.addEventListener(evt, () => {});
});

attachCropEvents();
