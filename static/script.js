const state = {
  result: null,
  originalImage: null,
  croppedImageData: "",
  selection: null,
  dragging: false,
  startX: 0,
  startY: 0,
  scaleX: 1,
  scaleY: 1
};

const el = {
  articleInput: document.getElementById("articleInput"),
  sceneNotes: document.getElementById("sceneNotes"),
  generateBtn: document.getElementById("generateBtn"),
  clearInputBtn: document.getElementById("clearInputBtn"),
  clearOutputBtn: document.getElementById("clearOutputBtn"),
  copyWpHtmlBtn: document.getElementById("copyWpHtmlBtn"),
  exportHtmlBtn: document.getElementById("exportHtmlBtn"),
  exportDocxBtn: document.getElementById("exportDocxBtn"),
  exportTxtBtn: document.getElementById("exportTxtBtn"),
  imageUpload: document.getElementById("imageUpload"),
  cropCompressBtn: document.getElementById("cropCompressBtn"),
  resetImageBtn: document.getElementById("resetImageBtn"),
  imageCanvas: document.getElementById("imageCanvas"),
  previewImage: document.getElementById("previewImage"),
  imageMeta: document.getElementById("imageMeta"),
  statusText: document.getElementById("statusText"),
  h1Title: document.getElementById("h1Title"),
  introText: document.getElementById("introText"),
  headingsText: document.getElementById("headingsText"),
  bodyText: document.getElementById("bodyText"),
  focusKeyphrase: document.getElementById("focusKeyphrase"),
  seoTitle: document.getElementById("seoTitle"),
  metaDescription: document.getElementById("metaDescription"),
  slugValue: document.getElementById("slugValue"),
  shortSummary: document.getElementById("shortSummary"),
  altText: document.getElementById("altText"),
  imgTitle: document.getElementById("imgTitle"),
  captionText: document.getElementById("captionText"),
  formattedOutput: document.getElementById("formattedOutput")
};

const ctx = el.imageCanvas.getContext("2d");

function setStatus(text) {
  el.statusText.textContent = text;
}

function escapeHtml(str) {
  return (str || "").replace(/[&<>"']/g, (m) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;"
  }[m]));
}

function renderFormattedOutput(result) {
  if (!result) {
    el.formattedOutput.innerHTML = "Formatted SEO output will appear here.";
    return;
  }

  let html = "";
  if (result.h1) html += `<h1>${escapeHtml(result.h1)}</h1>`;
  if (result.intro) html += `<p>${escapeHtml(result.intro)}</p>`;

  (result.structure || []).forEach((sec) => {
    html += `<h2>${escapeHtml(sec.h2 || "")}</h2>`;
    (sec.subsections || []).forEach((sub) => {
      if (sub.h3) html += `<h3>${escapeHtml(sub.h3)}</h3>`;
      if (sub.h4) html += `<h4>${escapeHtml(sub.h4)}</h4>`;
      const bodyParts = (sub.body || "").split("\n\n").filter(Boolean);
      bodyParts.forEach((p) => {
        html += `<p>${escapeHtml(p)}</p>`;
      });
    });
  });

  el.formattedOutput.innerHTML = html || "Formatted SEO output will appear here.";
}

function fillFields(result) {
  el.h1Title.value = result.h1 || "";
  el.introText.value = result.intro || "";
  el.headingsText.value = result.headings_copy || "";
  el.bodyText.value = result.body_copy || "";
  el.focusKeyphrase.value = result.focus_keyphrase || "";
  el.seoTitle.value = result.seo_title || "";
  el.metaDescription.value = result.meta_description || "";
  el.slugValue.value = result.slug || "";
  el.shortSummary.value = result.short_summary || "";
  el.altText.value = result.alt_text || "";
  el.imgTitle.value = result.img_title || "";
  el.captionText.value = result.caption || "";
  renderFormattedOutput(result);
}

function clearOutput() {
  state.result = null;
  state.croppedImageData = "";
  el.h1Title.value = "";
  el.introText.value = "";
  el.headingsText.value = "";
  el.bodyText.value = "";
  el.focusKeyphrase.value = "";
  el.seoTitle.value = "";
  el.metaDescription.value = "";
  el.slugValue.value = "";
  el.shortSummary.value = "";
  el.altText.value = "";
  el.imgTitle.value = "";
  el.captionText.value = "";
  el.previewImage.src = "";
  el.imageMeta.textContent = "No image selected.";
  renderFormattedOutput(null);
  setStatus("Output cleared");
}

async function postJson(url, payload) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Request failed");
  return data;
}

el.generateBtn.addEventListener("click", async () => {
  try {
    const article = el.articleInput.value.trim();
    const sceneNotes = el.sceneNotes.value.trim();

    if (!article) {
      setStatus("Please paste an article first.");
      return;
    }

    setStatus("Generating SEO output...");
    const result = await postJson("/process", { article, scene_notes: sceneNotes });
    state.result = result;
    fillFields(result);
    setStatus("SEO output generated.");
  } catch (err) {
    setStatus(err.message);
  }
});

el.clearInputBtn.addEventListener("click", () => {
  el.articleInput.value = "";
  setStatus("Input cleared");
});

el.clearOutputBtn.addEventListener("click", clearOutput);

el.copyWpHtmlBtn.addEventListener("click", async () => {
  try {
    if (!state.result) {
      setStatus("Generate SEO output first.");
      return;
    }

    syncImageSeoFields();
    const data = await postJson("/wp-html", {
      result: state.result,
      image_data: state.croppedImageData
    });

    await navigator.clipboard.writeText(data.html || "");
    setStatus("Copied WordPress-ready HTML.");
  } catch (err) {
    setStatus(err.message);
  }
});

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

async function exportFile(url, filename, payload) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });

  if (!res.ok) {
    let msg = "Export failed";
    try {
      const data = await res.json();
      msg = data.error || msg;
    } catch (_) {}
    throw new Error(msg);
  }

  const blob = await res.blob();
  downloadBlob(blob, filename);
}

function buildFilename() {
  const value = (el.slugValue.value || "seo-output").trim();
  return value || "seo-output";
}

function syncImageSeoFields() {
  if (!state.result) return;
  state.result.alt_text = el.altText.value.trim();
  state.result.img_title = el.imgTitle.value.trim();
  state.result.caption = el.captionText.value.trim();
}

el.exportTxtBtn.addEventListener("click", async () => {
  try {
    if (!state.result) {
      setStatus("Nothing to export.");
      return;
    }
    await exportFile("/export/txt", `${buildFilename()}.txt`, {
      content: state.result.generated_plain_text || "",
      filename: buildFilename()
    });
    setStatus("TXT exported.");
  } catch (err) {
    setStatus(err.message);
  }
});

el.exportHtmlBtn.addEventListener("click", async () => {
  try {
    if (!state.result) {
      setStatus("Nothing to export.");
      return;
    }
    syncImageSeoFields();
    await exportFile("/export/html", `${buildFilename()}.html`, {
      result: state.result,
      image_data: state.croppedImageData,
      filename: buildFilename()
    });
    setStatus("HTML exported.");
  } catch (err) {
    setStatus(err.message);
  }
});

el.exportDocxBtn.addEventListener("click", async () => {
  try {
    if (!state.result) {
      setStatus("Nothing to export.");
      return;
    }
    syncImageSeoFields();
    await exportFile("/export/docx", `${buildFilename()}.docx`, {
      result: state.result,
      image_data: state.croppedImageData,
      filename: buildFilename()
    });
    setStatus("DOCX exported.");
  } catch (err) {
    setStatus(err.message);
  }
});

function fitCanvas() {
  const rect = el.imageCanvas.getBoundingClientRect();
  el.imageCanvas.width = Math.max(300, rect.width);
  el.imageCanvas.height = 420;
  drawCanvas();
}

window.addEventListener("resize", fitCanvas);

el.imageUpload.addEventListener("change", (e) => {
  const file = e.target.files?.[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = () => {
    const img = new Image();
    img.onload = () => {
      state.originalImage = img;
      state.selection = null;
      state.croppedImageData = "";
      el.previewImage.src = "";
      el.imageMeta.textContent = `Original image: ${img.width} x ${img.height}`;
      fitCanvas();
      setStatus("Image loaded.");
    };
    img.src = reader.result;
  };
  reader.readAsDataURL(file);
});

function drawCanvas() {
  ctx.clearRect(0, 0, el.imageCanvas.width, el.imageCanvas.height);

  if (!state.originalImage) {
    ctx.fillStyle = "#09101d";
    ctx.fillRect(0, 0, el.imageCanvas.width, el.imageCanvas.height);
    ctx.fillStyle = "#94a8ca";
    ctx.font = "16px Segoe UI";
    ctx.fillText("Open image to start cropping", 24, 40);
    return;
  }

  const img = state.originalImage;
  const scale = Math.min(el.imageCanvas.width / img.width, el.imageCanvas.height / img.height);
  const drawWidth = img.width * scale;
  const drawHeight = img.height * scale;
  const offsetX = (el.imageCanvas.width - drawWidth) / 2;
  const offsetY = (el.imageCanvas.height - drawHeight) / 2;

  state.scaleX = img.width / drawWidth;
  state.scaleY = img.height / drawHeight;
  state.drawMeta = { offsetX, offsetY, drawWidth, drawHeight };

  ctx.drawImage(img, offsetX, offsetY, drawWidth, drawHeight);

  if (state.selection) {
    const s = state.selection;
    ctx.strokeStyle = "#f59e0b";
    ctx.lineWidth = 2;
    ctx.strokeRect(s.x, s.y, s.w, s.h);

    ctx.fillStyle = "rgba(245, 158, 11, 0.15)";
    ctx.fillRect(s.x, s.y, s.w, s.h);
  }
}

function clampSelection(sel) {
  if (!state.drawMeta) return sel;
  const { offsetX, offsetY, drawWidth, drawHeight } = state.drawMeta;

  let x = Math.max(offsetX, Math.min(sel.x, offsetX + drawWidth));
  let y = Math.max(offsetY, Math.min(sel.y, offsetY + drawHeight));
  let w = sel.w;
  let h = sel.h;

  if (x + w > offsetX + drawWidth) w = offsetX + drawWidth - x;
  if (y + h > offsetY + drawHeight) h = offsetY + drawHeight - y;

  return {
    x,
    y,
    w: Math.max(1, w),
    h: Math.max(1, h)
  };
}

el.imageCanvas.addEventListener("mousedown", (e) => {
  if (!state.originalImage) return;
  const rect = el.imageCanvas.getBoundingClientRect();
  state.dragging = true;
  state.startX = e.clientX - rect.left;
  state.startY = e.clientY - rect.top;
  state.selection = { x: state.startX, y: state.startY, w: 1, h: 1 };
  drawCanvas();
});

el.imageCanvas.addEventListener("mousemove", (e) => {
  if (!state.dragging || !state.originalImage) return;
  const rect = el.imageCanvas.getBoundingClientRect();
  const currentX = e.clientX - rect.left;
  const currentY = e.clientY - rect.top;

  const x = Math.min(state.startX, currentX);
  const y = Math.min(state.startY, currentY);
  const w = Math.abs(currentX - state.startX);
  const h = Math.abs(currentY - state.startY);

  state.selection = clampSelection({ x, y, w, h });
  drawCanvas();
});

window.addEventListener("mouseup", () => {
  state.dragging = false;
});

el.cropCompressBtn.addEventListener("click", async () => {
  try {
    if (!state.originalImage || !state.selection) {
      setStatus("Please select a crop area first.");
      return;
    }

    const tempCanvas = document.createElement("canvas");
    const tempCtx = tempCanvas.getContext("2d");

    const { offsetX, offsetY } = state.drawMeta;
    const sx = (state.selection.x - offsetX) * state.scaleX;
    const sy = (state.selection.y - offsetY) * state.scaleY;
    const sw = state.selection.w * state.scaleX;
    const sh = state.selection.h * state.scaleY;

    tempCanvas.width = Math.max(1, Math.round(sw));
    tempCanvas.height = Math.max(1, Math.round(sh));

    tempCtx.drawImage(
      state.originalImage,
      sx, sy, sw, sh,
      0, 0, tempCanvas.width, tempCanvas.height
    );

    const croppedData = tempCanvas.toDataURL("image/jpeg", 0.95);
    const data = await postJson("/compress-image", { image_data: croppedData });
    state.croppedImageData = data.image_data || "";
    el.previewImage.src = state.croppedImageData;
    el.imageMeta.textContent = `Compressed output: ${data.size_kb}KB`;
    setStatus(`Image compressed to ${data.size_kb}KB.`);
  } catch (err) {
    setStatus(err.message);
  }
});

el.resetImageBtn.addEventListener("click", () => {
  state.originalImage = null;
  state.selection = null;
  state.croppedImageData = "";
  el.imageUpload.value = "";
  el.previewImage.src = "";
  el.imageMeta.textContent = "No image selected.";
  drawCanvas();
  setStatus("Image cleared.");
});

fitCanvas();
