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

/* image editor */
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
      headers: {
        "Content-Type": "application/json"
      },
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
      headers: {
        "Content-Type": "application/json"
      },
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

  const text = buildCopyAllText(currentResult);
  await copyText(text, "All output copied.");
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

/* image editor side */
const ctx = imageCanvas.getContext("2d");
let loadedImage = null;
let imageState = {
  rotation: 0,
  flipX: 1,
  flipY: 1,
  grayscale: false,
  brightness: 100,
  contrast: 100
};

function resetImageState() {
  imageState = {
    rotation: 0,
    flipX: 1,
    flipY: 1,
    grayscale: false,
    brightness: 100,
    contrast: 100
  };
  brightnessRange.value = 100;
  contrastRange.value = 100;
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
}

imageUpload.addEventListener("change", (event) => {
  const file = event.target.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = () => {
    const img = new Image();
    img.onload = () => {
      loadedImage = img;
      resetImageState();
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

downloadImageBtn.addEventListener("click", () => {
  if (!loadedImage) return setStatus("Upload image first.", "warning");

  const link = document.createElement("a");
  link.download = "edited-image.png";
  link.href = imageCanvas.toDataURL("image/png");
  link.click();
  setStatus("Edited image downloaded.", "success");
});
