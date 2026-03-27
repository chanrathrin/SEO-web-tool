const state = {
  processed: null,
  uploadedFile: null,
  sourceImageLoaded: false,
  selectedPreset: { width: 1200, height: 366 },
  latestImageDataUri: "",
  crop: { x: 40, y: 40, width: 320, height: 98 },
  dragMode: null,
  dragOffsetX: 0,
  dragOffsetY: 0
};

const els = {
  articleInput: document.getElementById("articleInput"),
  seoPreview: document.getElementById("seoPreview"),
  wpHtmlOutput: document.getElementById("wpHtmlOutput"),
  titleOptions: document.getElementById("titleOptions"),
  metaOptions: document.getElementById("metaOptions"),
  focusKeyphrase: document.getElementById("focusKeyphrase"),
  seoTitle: document.getElementById("seoTitle"),
  metaDescription: document.getElementById("metaDescription"),
  slug: document.getElementById("slug"),
  shortSummary: document.getElementById("shortSummary"),

  imageInput: document.getElementById("imageInput"),
  sourceImage: document.getElementById("sourceImage"),
  canvasWrap: document.getElementById("canvasWrap"),
  cropBox: document.getElementById("cropBox"),
  cropPreview: document.getElementById("cropPreview"),
  previewMeta: document.getElementById("previewMeta"),

  sceneNotes: document.getElementById("sceneNotes"),
  altText: document.getElementById("altText"),
  imgTitle: document.getElementById("imgTitle"),
  caption: document.getElementById("caption"),

  statusBar: document.getElementById("statusBar"),
  toast: document.getElementById("toast"),

  generateBtn: document.getElementById("generateBtn"),
  clearInputBtn: document.getElementById("clearInputBtn"),
  clearOutputBtn: document.getElementById("clearOutputBtn"),
  copyWpHtmlBtn: document.getElementById("copyWpHtmlBtn"),
  copyAllOutputBtn: document.getElementById("copyAllOutputBtn"),
  exportHtmlBtn: document.getElementById("exportHtmlBtn"),
  exportDocxBtn: document.getElementById("exportDocxBtn"),
  exportTxtBtn: document.getElementById("exportTxtBtn"),

  applyCropBtn: document.getElementById("applyCropBtn"),
  useCroppedInSeoBtn: document.getElementById("useCroppedInSeoBtn"),
  exportUnder100Btn: document.getElementById("exportUnder100Btn"),
  generateImageSeoBtn: document.getElementById("generateImageSeoBtn"),
  copyImageSeoBtn: document.getElementById("copyImageSeoBtn"),
  clearImageSeoBtn: document.getElementById("clearImageSeoBtn")
};

function setStatus(text) {
  els.statusBar.textContent = text;
}

function showToast(text) {
  els.toast.textContent = text;
  els.toast.classList.add("show");
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(() => {
    els.toast.classList.remove("show");
  }, 2200);
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text || "";
  return div.innerHTML;
}

function getFieldValue(id) {
  const el = document.getElementById(id);
  return (el?.value || "").trim();
}

async function copyText(text, successMessage = "Copied") {
  if (!text || !text.trim()) {
    setStatus("Nothing to copy");
    showToast("Nothing to copy");
    return;
  }
  await navigator.clipboard.writeText(text);
  setStatus(successMessage);
  showToast(successMessage);
}

function renderPreview() {
  if (!state.processed) {
    els.seoPreview.innerHTML = `<p class="placeholder-text">Formatted SEO output will appear here.</p>`;
    return;
  }

  const data = state.processed;
  const html = [];

  if (data.h1_copy) html.push(`<h1>${escapeHtml(data.h1_copy)}</h1>`);
  if (data.intro_copy) html.push(`<p>${escapeHtml(data.intro_copy)}</p>`);

  (data.structure_copy || []).forEach(sec => {
    if (sec.h2) html.push(`<h2>${escapeHtml(sec.h2)}</h2>`);
    (sec.subsections || []).forEach(sub => {
      if (sub.h3) html.push(`<h3>${escapeHtml(sub.h3)}</h3>`);
      if (sub.h4) html.push(`<h4>${escapeHtml(sub.h4)}</h4>`);
      if (sub.body) {
        const bodyHtml = escapeHtml(sub.body).replace(/\n\n/g, "<br><br>");
        html.push(`<p>${bodyHtml}</p>`);
      }
    });
  });

  els.seoPreview.innerHTML = html.join("");
}

function updateFieldValuesFromProcessed() {
  if (!state.processed) return;
  els.focusKeyphrase.value = state.processed.focus_keyphrase_value || "";
  els.seoTitle.value = state.processed.seo_title_value || "";
  els.metaDescription.value = state.processed.meta_description_value || "";
  els.slug.value = state.processed.slug_value || "";
  els.shortSummary.value = state.processed.short_summary_value || "";

  els.titleOptions.value = (state.processed.seo_title_options || []).join("\n");
  els.metaOptions.value = (state.processed.meta_options || []).join("\n");
}

function updateProcessedCopiesFromFields() {
  if (!state.processed) return;
  state.processed.focus_keyphrase_copy = els.focusKeyphrase.value.trim();
  state.processed.focus_keyphrase_value = els.focusKeyphrase.value.trim();
  state.processed.seo_title_copy = els.seoTitle.value.trim();
  state.processed.seo_title_value = els.seoTitle.value.trim();
  state.processed.meta_description_copy = els.metaDescription.value.trim();
  state.processed.meta_description_value = els.metaDescription.value.trim();
  state.processed.slug_copy = els.slug.value.trim();
  state.processed.slug_value = els.slug.value.trim();
  state.processed.short_summary_copy = els.shortSummary.value.trim();
  state.processed.short_summary_value = els.shortSummary.value.trim();
}

function buildWpHtmlFromState() {
  if (!state.processed) return "";

  const h1 = state.processed.h1_copy || "";
  const intro = state.processed.intro_copy || "";
  const structure = state.processed.structure_copy || [];
  const altText = els.altText.value.trim() || h1 || "Featured image";
  const imgTitle = els.imgTitle.value.trim() || h1 || "Featured image";
  const caption = els.caption.value.trim() || "";

  const parts = [];

  if (state.latestImageDataUri) {
    let fig = `<figure class="wp-block-image size-full featured-image-wrap">`;
    fig += `<img src="${state.latestImageDataUri}" alt="${escapeHtml(altText)}" title="${escapeHtml(imgTitle)}" />`;
    if (caption) fig += `<figcaption>${escapeHtml(caption)}</figcaption>`;
    fig += `</figure>`;
    parts.push(fig);
  }

  if (h1) parts.push(`<h1>${escapeHtml(h1)}</h1>`);
  if (intro) parts.push(`<p>${escapeHtml(intro)}</p>`);

  structure.forEach(sec => {
    if (sec.h2) parts.push(`<h2>${escapeHtml(sec.h2)}</h2>`);
    (sec.subsections || []).forEach(sub => {
      if (sub.h3) parts.push(`<h3>${escapeHtml(sub.h3)}</h3>`);
      if (sub.h4) parts.push(`<h4>${escapeHtml(sub.h4)}</h4>`);
      (sub.body || "").split("\n\n").filter(Boolean).forEach(p => {
        parts.push(`<p>${escapeHtml(p)}</p>`);
      });
    });
  });

  return parts.join("\n");
}

function refreshWpHtmlOutput() {
  els.wpHtmlOutput.value = buildWpHtmlFromState();
}

async function generateArticle() {
  const article = els.articleInput.value.trim();
  if (!article) {
    setStatus("Please paste an article first");
    showToast("Please paste an article first");
    return;
  }

  try {
    const res = await fetch("/api/process", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ article })
    });
    const data = await res.json();

    if (!data.ok) {
      setStatus(data.error || "Failed to generate");
      showToast(data.error || "Failed");
      return;
    }

    state.processed = data;
    renderPreview();
    updateFieldValuesFromProcessed();
    refreshWpHtmlOutput();
    setStatus("SEO output generated - HTML and DOCX export ready");
    showToast("SEO output generated");
  } catch (err) {
    setStatus("Generate failed");
    showToast("Generate failed");
  }
}

function clearInput() {
  els.articleInput.value = "";
  setStatus("Input cleared");
  showToast("Input cleared");
}

function clearImageSeoFields() {
  els.sceneNotes.value = "";
  els.altText.value = "";
  els.imgTitle.value = "";
  els.caption.value = "";
  refreshWpHtmlOutput();
  setStatus("Image SEO cleared");
  showToast("Image SEO cleared");
}

function clearOutput() {
  state.processed = null;
  state.latestImageDataUri = "";
  state.uploadedFile = null;
  state.sourceImageLoaded = false;

  els.seoPreview.innerHTML = `<p class="placeholder-text">Formatted SEO output will appear here.</p>`;
  els.wpHtmlOutput.value = "";
  els.titleOptions.value = "";
  els.metaOptions.value = "";

  els.focusKeyphrase.value = "";
  els.seoTitle.value = "";
  els.metaDescription.value = "";
  els.slug.value = "";
  els.shortSummary.value = "";

  clearImageSeoFields();

  els.imageInput.value = "";
  els.sourceImage.src = "";
  els.sourceImage.style.display = "none";
  els.cropBox.style.display = "none";
  els.cropPreview.src = "";
  els.previewMeta.textContent = "Preset output size will appear here";

  setStatus("Output cleared");
  showToast("Output cleared");
}

async function copyAllOutput() {
  const payload = els.wpHtmlOutput.value.trim() || state.processed?.plain_text || "";
  await copyText(payload, "Copied all output");
}

async function copyWpHtml() {
  await copyText(els.wpHtmlOutput.value, "Copied WordPress-ready HTML");
}

async function copySection(key) {
  if (!state.processed) {
    setStatus("Generate SEO output first");
    showToast("Generate SEO output first");
    return;
  }
  updateProcessedCopiesFromFields();
  await copyText(state.processed[key] || "", "Copied section");
}

async function copyField(targetId) {
  await copyText(getFieldValue(targetId), "Copied field");
}

async function copyAllImageSeo() {
  const payload = [
    `Alt Text: ${els.altText.value.trim()}`,
    `Img Title: ${els.imgTitle.value.trim()}`,
    `Caption: ${els.caption.value.trim()}`
  ].join("\n");

  const normalized = payload.replace("Alt Text: ", "").replace("Img Title: ", "").replace("Caption: ", "").trim();
  if (!normalized) {
    setStatus("No image SEO fields to copy");
    showToast("No image SEO fields to copy");
    return;
  }

  await copyText(payload, "Copied all featured image SEO fields");
}

async function exportTxt() {
  const text = state.processed?.plain_text || "";
  if (!text) {
    setStatus("Nothing to export");
    showToast("Nothing to export");
    return;
  }

  const res = await fetch("/api/export-txt", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text })
  });

  downloadBlob(await res.blob(), "seo-output.txt");
  setStatus("TXT exported");
}

async function exportHtml() {
  if (!state.processed) {
    setStatus("Nothing to export");
    showToast("Nothing to export");
    return;
  }
  refreshWpHtmlOutput();

  const res = await fetch("/api/export-html", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      h1: state.processed.h1_copy || "",
      wp_html: els.wpHtmlOutput.value || ""
    })
  });

  downloadBlob(await res.blob(), "seo-output.html");
  setStatus("HTML exported");
}

async function exportDocx() {
  if (!state.processed) {
    setStatus("Nothing to export");
    showToast("Nothing to export");
    return;
  }
  refreshWpHtmlOutput();

  const res = await fetch("/api/export-docx", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      h1: state.processed.h1_copy || "",
      intro: state.processed.intro_copy || "",
      structure: state.processed.structure_copy || [],
      image_data_uri: state.latestImageDataUri || "",
      caption: els.caption.value.trim()
    })
  });

  downloadBlob(await res.blob(), "seo-output.docx");
  setStatus("DOCX exported");
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
    els.sourceImage.onload = () => {
      els.sourceImage.style.display = "block";
      state.sourceImageLoaded = true;
      initCropBox();
      setStatus("Featured image loaded");
      showToast("Featured image loaded");
    };
    els.sourceImage.src = reader.result;
  };
  reader.readAsDataURL(file);
}

function getImageBoundsInWrap() {
  const wrapRect = els.canvasWrap.getBoundingClientRect();
  const imgRect = els.sourceImage.getBoundingClientRect();
  return {
    x: imgRect.left - wrapRect.left,
    y: imgRect.top - wrapRect.top,
    width: imgRect.width,
    height: imgRect.height
  };
}

function initCropBox() {
  const imgBounds = getImageBoundsInWrap();
  const ratio = state.selectedPreset.width / state.selectedPreset.height;

  let width = Math.min(imgBounds.width * 0.72, 360);
  let height = width / ratio;

  if (height > imgBounds.height * 0.8) {
    height = imgBounds.height * 0.8;
    width = height * ratio;
  }

  state.crop = {
    x: imgBounds.x + (imgBounds.width - width) / 2,
    y: imgBounds.y + (imgBounds.height - height) / 2,
    width,
    height
  };

  updateCropBox();
}

function updateCropBox() {
  els.cropBox.style.display = "block";
  els.cropBox.style.left = `${state.crop.x}px`;
  els.cropBox.style.top = `${state.crop.y}px`;
  els.cropBox.style.width = `${state.crop.width}px`;
  els.cropBox.style.height = `${state.crop.height}px`;
}

function setPreset(width, height) {
  state.selectedPreset = { width: Number(width), height: Number(height) };
  if (state.sourceImageLoaded) {
    initCropBox();
  }
  setStatus(`Preset ${width}x${height} selected`);
  showToast(`Preset ${width}x${height}`);
}

function clampCrop() {
  const imgBounds = getImageBoundsInWrap();
  const ratio = state.selectedPreset.width / state.selectedPreset.height;

  if (state.crop.width < 60) {
    state.crop.width = 60;
    state.crop.height = 60 / ratio;
  }

  if (state.crop.height < 30) {
    state.crop.height = 30;
    state.crop.width = 30 * ratio;
  }

  if (state.crop.width > imgBounds.width) {
    state.crop.width = imgBounds.width;
    state.crop.height = state.crop.width / ratio;
  }

  if (state.crop.height > imgBounds.height) {
    state.crop.height = imgBounds.height;
    state.crop.width = state.crop.height * ratio;
  }

  state.crop.x = Math.max(imgBounds.x, Math.min(state.crop.x, imgBounds.x + imgBounds.width - state.crop.width));
  state.crop.y = Math.max(imgBounds.y, Math.min(state.crop.y, imgBounds.y + imgBounds.height - state.crop.height));
}

function enableCropInteractions() {
  const handle = els.cropBox.querySelector(".resize-handle.br");

  els.cropBox.addEventListener("mousedown", (e) => {
    if (!state.sourceImageLoaded) return;
    if (e.target === handle) return;

    state.dragMode = "move";
    const boxRect = els.cropBox.getBoundingClientRect();
    state.dragOffsetX = e.clientX - boxRect.left;
    state.dragOffsetY = e.clientY - boxRect.top;
    e.preventDefault();
  });

  handle.addEventListener("mousedown", (e) => {
    if (!state.sourceImageLoaded) return;
    state.dragMode = "resize";
    e.stopPropagation();
    e.preventDefault();
  });

  window.addEventListener("mousemove", (e) => {
    if (!state.dragMode || !state.sourceImageLoaded) return;

    const wrapRect = els.canvasWrap.getBoundingClientRect();
    const ratio = state.selectedPreset.width / state.selectedPreset.height;

    if (state.dragMode === "move") {
      state.crop.x = e.clientX - wrapRect.left - state.dragOffsetX;
      state.crop.y = e.clientY - wrapRect.top - state.dragOffsetY;
      clampCrop();
      updateCropBox();
      return;
    }

    if (state.dragMode === "resize") {
      let newWidth = e.clientX - wrapRect.left - state.crop.x;
      newWidth = Math.max(60, newWidth);
      let newHeight = newWidth / ratio;

      state.crop.width = newWidth;
      state.crop.height = newHeight;
      clampCrop();
      updateCropBox();
    }
  });

  window.addEventListener("mouseup", () => {
    state.dragMode = null;
  });
}

function getRealCropValues() {
  const imgBounds = getImageBoundsInWrap();

  const displayX = state.crop.x - imgBounds.x;
  const displayY = state.crop.y - imgBounds.y;

  const scaleX = els.sourceImage.naturalWidth / imgBounds.width;
  const scaleY = els.sourceImage.naturalHeight / imgBounds.height;

  return {
    x: Math.round(displayX * scaleX),
    y: Math.round(displayY * scaleY),
    width: Math.round(state.crop.width * scaleX),
    height: Math.round(state.crop.height * scaleY)
  };
}

async function cropImage(exportUnder100kb = false) {
  if (!state.uploadedFile) {
    setStatus("Please import an image first");
    showToast("Please import an image first");
    return null;
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
    setStatus(data.error || "Crop failed");
    showToast(data.error || "Crop failed");
    return null;
  }

  els.cropPreview.src = data.image_data_uri;
  els.previewMeta.textContent = exportUnder100kb
    ? `Preview size: ${data.width} x ${data.height} • ${data.size_kb}KB`
    : `Preview size: ${data.width} x ${data.height}`;

  setStatus(exportUnder100kb ? "Exported cropped image under 100KB" : "Crop applied to live preview");
  showToast(exportUnder100kb ? "Exported <100KB" : "Crop applied");

  return data;
}

async function applyCrop() {
  await cropImage(false);
}

async function useCropInSeoOutput() {
  const data = await cropImage(false);
  if (!data) return;

  state.latestImageDataUri = data.image_data_uri;
  refreshWpHtmlOutput();
  await generateImageSeo(true);
  setStatus("Cropped image sent to SEO Output and Yoast image fields updated");
  showToast("Crop used in SEO output");
}

async function exportUnder100() {
  const data = await cropImage(true);
  if (!data) return;

  const blob = dataUriToBlob(data.image_data_uri);
  downloadBlob(blob, "cropped-featured-image-under-100kb.jpg");
}

function dataUriToBlob(dataUri) {
  const [meta, data] = dataUri.split(",");
  const mime = (meta.match(/data:(.*?);base64/) || [])[1] || "application/octet-stream";
  const binary = atob(data);
  const arr = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) arr[i] = binary.charCodeAt(i);
  return new Blob([arr], { type: mime });
}

async function generateImageSeo(silent = false) {
  const payload = {
    h1: state.processed?.h1_copy || "",
    intro: state.processed?.intro_copy || "",
    focus_keyphrase: els.focusKeyphrase.value.trim() || "",
    scene_notes: els.sceneNotes.value.trim() || ""
  };

  const res = await fetch("/api/image-seo", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });

  const data = await res.json();
  if (!data.ok) {
    setStatus("Image SEO failed");
    showToast("Image SEO failed");
    return;
  }

  els.altText.value = data.alt_text || "";
  els.imgTitle.value = data.img_title || "";
  els.caption.value = data.caption || "";
  refreshWpHtmlOutput();

  if (!silent) {
    setStatus("Generated Alt Text, Img Title, and Caption for WordPress + Yoast");
    showToast("Generated image SEO");
  }
}

function bindLiveWpUpdates() {
  [els.altText, els.imgTitle, els.caption, els.focusKeyphrase, els.seoTitle, els.metaDescription, els.slug, els.shortSummary]
    .forEach(el => {
      ["input", "change"].forEach(evt => {
        el.addEventListener(evt, () => {
          updateProcessedCopiesFromFields();
          refreshWpHtmlOutput();
        });
      });
    });
}

els.generateBtn.addEventListener("click", generateArticle);
els.clearInputBtn.addEventListener("click", clearInput);
els.clearOutputBtn.addEventListener("click", clearOutput);
els.copyWpHtmlBtn.addEventListener("click", copyWpHtml);
els.copyAllOutputBtn.addEventListener("click", copyAllOutput);
els.exportTxtBtn.addEventListener("click", exportTxt);
els.exportHtmlBtn.addEventListener("click", exportHtml);
els.exportDocxBtn.addEventListener("click", exportDocx);

document.querySelectorAll(".copy-section-btn").forEach(btn => {
  btn.addEventListener("click", () => copySection(btn.dataset.key));
});

document.querySelectorAll(".copy-field-btn").forEach(btn => {
  btn.addEventListener("click", () => copyField(btn.dataset.target));
});

els.imageInput.addEventListener("change", (e) => {
  const file = e.target.files?.[0];
  if (file) loadImage(file);
});

document.querySelectorAll(".preset-btn").forEach(btn => {
  btn.addEventListener("click", () => setPreset(btn.dataset.width, btn.dataset.height));
});

els.applyCropBtn.addEventListener("click", applyCrop);
els.useCroppedInSeoBtn.addEventListener("click", useCropInSeoOutput);
els.exportUnder100Btn.addEventListener("click", exportUnder100);
els.generateImageSeoBtn.addEventListener("click", () => generateImageSeo(false));
els.copyImageSeoBtn.addEventListener("click", copyAllImageSeo);
els.clearImageSeoBtn.addEventListener("click", clearImageSeoFields);

enableCropInteractions();
bindLiveWpUpdates();
refreshWpHtmlOutput();
setStatus("Ready");
