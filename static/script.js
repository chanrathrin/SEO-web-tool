const apiKey = document.getElementById("apiKey");
const articleInput = document.getElementById("articleInput");
const generateBtn = document.getElementById("generateBtn");
const clearBtn = document.getElementById("clearBtn");
const copyInputBtn = document.getElementById("copyInputBtn");
const copyOutputBtn = document.getElementById("copyOutputBtn");
const themeToggle = document.getElementById("themeToggle");

const statusBox = document.getElementById("statusBox");
const focusKeyphrase = document.getElementById("focusKeyphrase");
const seoTitle = document.getElementById("seoTitle");
const metaDescription = document.getElementById("metaDescription");
const detectedEmbeds = document.getElementById("detectedEmbeds");
const seoOutput = document.getElementById("seoOutput");
const structureInfo = document.getElementById("structureInfo");

const previewTitle = document.getElementById("previewTitle");
const previewMeta = document.getElementById("previewMeta");
const seoTitleCounter = document.getElementById("seoTitleCounter");
const metaCounter = document.getElementById("metaCounter");

function setStatus(message, type = "info") {
  statusBox.textContent = message;
  statusBox.className = `status ${type}`;
}

function updatePreview() {
  const title = (seoTitle.value || "").trim();
  const meta = (metaDescription.value || "").trim();

  previewTitle.textContent = title || "SEO Title will appear here";
  previewMeta.textContent = meta || "Meta description will appear here.";

  seoTitleCounter.textContent = `${title.length} / 60`;
  metaCounter.textContent = `${meta.length} / 160`;

  seoTitleCounter.className = "counter";
  metaCounter.className = "counter";

  if (title.length > 60) seoTitleCounter.classList.add("bad");
  else if (title.length >= 50) seoTitleCounter.classList.add("good");
  else if (title.length > 0) seoTitleCounter.classList.add("warn");

  if (meta.length > 160) metaCounter.classList.add("bad");
  else if (meta.length >= 120) metaCounter.classList.add("good");
  else if (meta.length > 0) metaCounter.classList.add("warn");
}

async function generateSEO() {
  const article = articleInput.value.trim();
  if (!article) {
    setStatus("Please paste article input first.", "error");
    return;
  }

  generateBtn.disabled = true;
  setStatus("Generating SEO...", "info");

  try {
    const res = await fetch("/generate", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        article: article,
        api_key: apiKey.value.trim()
      })
    });

    const data = await res.json();

    if (!res.ok || !data.ok) {
      throw new Error(data.error || "Failed to generate SEO.");
    }

    focusKeyphrase.value = data.focus_keyphrase || "";
    seoTitle.value = data.seo_title || "";
    metaDescription.value = data.meta_description || "";
    detectedEmbeds.value = data.detected_embeds || "";
    seoOutput.value = data.seo_output || "";
    structureInfo.value = data.structure || "";

    updatePreview();
    setStatus("SEO generated successfully.", "success");
  } catch (err) {
    setStatus(err.message || "Unexpected error.", "error");
  } finally {
    generateBtn.disabled = false;
  }
}

function clearAll() {
  articleInput.value = "";
  focusKeyphrase.value = "";
  seoTitle.value = "";
  metaDescription.value = "";
  detectedEmbeds.value = "";
  seoOutput.value = "";
  structureInfo.value = "";
  updatePreview();
  setStatus("Cleared.", "info");
}

async function copyText(value, successMessage = "Copied.") {
  if (!value) {
    setStatus("Nothing to copy.", "warn");
    return;
  }
  try {
    await navigator.clipboard.writeText(value);
    setStatus(successMessage, "success");
  } catch {
    setStatus("Copy failed.", "error");
  }
}

generateBtn.addEventListener("click", generateSEO);
clearBtn.addEventListener("click", clearAll);
copyInputBtn.addEventListener("click", () => copyText(articleInput.value, "Input copied."));
copyOutputBtn.addEventListener("click", () => copyText(seoOutput.value, "SEO output copied."));
themeToggle.addEventListener("click", () => {
  document.body.classList.toggle("light");
});

document.querySelectorAll("[data-copy-target]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const id = btn.getAttribute("data-copy-target");
    const el = document.getElementById(id);
    if (!el) return;
    copyText(el.value, `${id} copied.`);
  });
});

updatePreview();
