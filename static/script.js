const STORAGE_KEY = "wp_seo_studio_api_key";

const statusLabel = document.getElementById("statusLabel");
const apiBadge = document.getElementById("apiBadge");

const tabButtons = document.querySelectorAll(".tab-btn");
const tabPanels = document.querySelectorAll(".tab-panel");

const openApiSettingsBtn = document.getElementById("openApiSettingsBtn");
const closeApiSettingsBtn = document.getElementById("closeApiSettingsBtn");
const apiModal = document.getElementById("apiModal");
const apiKeyInput = document.getElementById("apiKeyInput");
const testApiKeyBtn = document.getElementById("testApiKeyBtn");
const saveApiKeyBtn = document.getElementById("saveApiKeyBtn");
const clearApiKeyBtn = document.getElementById("clearApiKeyBtn");
const showApiKeyCheckbox = document.getElementById("showApiKeyCheckbox");
const apiModalStatus = document.getElementById("apiModalStatus");

const articleInput = document.getElementById("articleInput");
const generateSeoBtn = document.getElementById("generateSeoBtn");
const clearSeoBtn = document.getElementById("clearSeoBtn");
const copyInputBtn = document.getElementById("copyInputBtn");
const copyAllSeoBtn = document.getElementById("copyAllSeoBtn");
const copySeoOutputBtn = document.getElementById("copySeoOutputBtn");

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

const imageInput = document.getElementById("imageInput");
const sceneNotes = document.getElementById("sceneNotes");
const generateImageSeoBtn = document.getElementById("generateImageSeoBtn");
const clearImageBtn = document.getElementById("clearImageBtn");
const imagePreview = document.getElementById("imagePreview");
const imagePlaceholder = document.getElementById("imagePlaceholder");
const altText = document.getElementById("altText");
const imgTitle = document.getElementById("imgTitle");
const caption = document.getElementById("caption");
const copyAllImageBtn = document.getElementById("copyAllImageBtn");

function currentApiKey() {
  return localStorage.getItem(STORAGE_KEY) || "";
}

function setStatus(message) {
  statusLabel.textContent = message;
}

function setApiBadge() {
  const key = currentApiKey();
  apiBadge.classList.remove("off", "saved");
  if (key) {
    apiBadge.textContent = "● API key saved";
    apiBadge.classList.add("saved");
  } else {
    apiBadge.textContent = "○ API not configured";
    apiBadge.classList.add("off");
  }
}

function openApiModal() {
  apiKeyInput.value = currentApiKey();
  apiModal.classList.remove("hidden");
  apiModal.setAttribute("aria-hidden", "false");
}

function closeApiModal() {
  apiModal.classList.add("hidden");
  apiModal.setAttribute("aria-hidden", "true");
}

function switchTab(tabId) {
  tabButtons.forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === tabId);
  });
  tabPanels.forEach((panel) => {
    panel.classList.toggle("active", panel.id === tabId);
  });
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

async function copyText(value, successLabel) {
  if (!value || !value.trim()) {
    setStatus("Nothing to copy.");
    return;
  }
  try {
    await navigator.clipboard.writeText(value);
    setStatus(successLabel || "Copied.");
  } catch (err) {
    setStatus("Copy failed.");
  }
}

async function testApiKey() {
  const apiKey = apiKeyInput.value.trim();
  if (!apiKey) {
    apiModalStatus.textContent = "API key is empty.";
    return;
  }

  apiModalStatus.textContent = "Testing API key...";
  try {
    const res = await fetch("/api/verify-key", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: apiKey })
    });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      throw new Error(data.error || "API key test failed.");
    }
    apiModalStatus.textContent = "✓ API key is valid.";
  } catch (err) {
    apiModalStatus.textContent = `✗ ${err.message || "API key test failed."}`;
  }
}

function saveApiKey() {
  const apiKey = apiKeyInput.value.trim();
  if (!apiKey) {
    apiModalStatus.textContent = "API key is empty.";
    return;
  }
  localStorage.setItem(STORAGE_KEY, apiKey);
  setApiBadge();
  apiModalStatus.textContent = "✓ API key saved and active.";
  setStatus("API key loaded");
}

function clearApiKey() {
  localStorage.removeItem(STORAGE_KEY);
  apiKeyInput.value = "";
  setApiBadge();
  apiModalStatus.textContent = "Saved key cleared.";
  setStatus("API key cleared");
}

async function generateSeo() {
  const article = articleInput.value.trim();
  if (!article) {
    setStatus("Paste article input first");
    return;
  }

  generateSeoBtn.disabled = true;
  setStatus("Generating SEO...");

  try {
    const res = await fetch("/api/generate-seo", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        article,
        api_key: currentApiKey()
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
    setStatus("SEO generated successfully");
  } catch (err) {
    setStatus(err.message || "Failed to generate SEO.");
  } finally {
    generateSeoBtn.disabled = false;
  }
}

function clearSeo() {
  articleInput.value = "";
  focusKeyphrase.value = "";
  seoTitle.value = "";
  metaDescription.value = "";
  detectedEmbeds.value = "";
  seoOutput.value = "";
  structureInfo.value = "";
  updatePreview();
  setStatus("SEO fields cleared");
}

function previewImage(file) {
  if (!file) {
    imagePreview.src = "";
    imagePreview.classList.add("hidden");
    imagePlaceholder.classList.remove("hidden");
    return;
  }
  const reader = new FileReader();
  reader.onload = (e) => {
    imagePreview.src = e.target.result;
    imagePreview.classList.remove("hidden");
    imagePlaceholder.classList.add("hidden");
  };
  reader.readAsDataURL(file);
}

async function generateImageSeo() {
  const file = imageInput.files[0];
  if (!file) {
    setStatus("Upload an image first");
    return;
  }

  generateImageSeoBtn.disabled = true;
  setStatus("Reading image & generating WordPress SEO fields...");

  try {
    const form = new FormData();
    form.append("image", file);
    form.append("scene_notes", sceneNotes.value.trim());
    form.append("api_key", currentApiKey());

    const res = await fetch("/api/generate-image-seo", {
      method: "POST",
      body: form
    });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      throw new Error(data.error || "Failed to generate image SEO.");
    }

    altText.value = data.alt_text || "";
    imgTitle.value = data.img_title || "";
    caption.value = data.caption || "";
    setStatus("Image SEO fields ready");
  } catch (err) {
    setStatus(err.message || "Failed to generate image SEO.");
  } finally {
    generateImageSeoBtn.disabled = false;
  }
}

function clearImageSeo() {
  imageInput.value = "";
  sceneNotes.value = "";
  altText.value = "";
  imgTitle.value = "";
  caption.value = "";
  previewImage(null);
  setStatus("Image SEO fields cleared");
}

function copyAllSeo() {
  const value = [
    `Focus Keyphrase:\n${focusKeyphrase.value.trim()}`,
    `SEO Title:\n${seoTitle.value.trim()}`,
    `Meta Description:\n${metaDescription.value.trim()}`,
  ].join("\n\n");
  copyText(value, "Copied all SEO fields");
}

function copyAllImage() {
  const value = [
    `Alt Text:\n${altText.value.trim()}`,
    `Image Title:\n${imgTitle.value.trim()}`,
    `Caption:\n${caption.value.trim()}`,
  ].join("\n\n");
  copyText(value, "Copied all image fields");
}

openApiSettingsBtn.addEventListener("click", openApiModal);
closeApiSettingsBtn.addEventListener("click", closeApiModal);
testApiKeyBtn.addEventListener("click", testApiKey);
saveApiKeyBtn.addEventListener("click", saveApiKey);
clearApiKeyBtn.addEventListener("click", clearApiKey);
showApiKeyCheckbox.addEventListener("change", () => {
  apiKeyInput.type = showApiKeyCheckbox.checked ? "text" : "password";
});

generateSeoBtn.addEventListener("click", generateSeo);
clearSeoBtn.addEventListener("click", clearSeo);
copyInputBtn.addEventListener("click", () => copyText(articleInput.value, "Input copied"));
copyAllSeoBtn.addEventListener("click", copyAllSeo);
copySeoOutputBtn.addEventListener("click", () => copyText(seoOutput.value, "SEO output copied"));

generateImageSeoBtn.addEventListener("click", generateImageSeo);
clearImageBtn.addEventListener("click", clearImageSeo);
copyAllImageBtn.addEventListener("click", copyAllImage);
imageInput.addEventListener("change", (e) => previewImage(e.target.files[0] || null));

tabButtons.forEach((btn) => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});

document.querySelectorAll("[data-copy-target]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const id = btn.dataset.copyTarget;
    const el = document.getElementById(id);
    if (!el) return;
    copyText(el.value, `${id} copied`);
  });
});

apiModal.addEventListener("click", (e) => {
  if (e.target === apiModal) closeApiModal();
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !apiModal.classList.contains("hidden")) {
    closeApiModal();
  }
});

setApiBadge();
updatePreview();
setStatus("Ready.");
