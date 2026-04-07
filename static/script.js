const STORAGE_KEY = "wp_seo_studio_api_key";

const apiBadge = document.getElementById("apiBadge");
const statusLabel = document.getElementById("statusLabel");

const openApiSettingsBtn = document.getElementById("openApiSettingsBtn");
const closeApiSettingsBtn = document.getElementById("closeApiSettingsBtn");
const apiModal = document.getElementById("apiModal");
const apiModalStatus = document.getElementById("apiModalStatus");
const apiKeyInput = document.getElementById("apiKeyInput");
const showApiKeyCheckbox = document.getElementById("showApiKeyCheckbox");
const testApiKeyBtn = document.getElementById("testApiKeyBtn");
const saveApiKeyBtn = document.getElementById("saveApiKeyBtn");
const clearApiKeyBtn = document.getElementById("clearApiKeyBtn");

// Tabs
const tabButtons = document.querySelectorAll(".tab-btn");
const tabPanels = document.querySelectorAll(".tab-panel");

// SEO tab
const articleInput = document.getElementById("articleInput");
const generateSeoBtn = document.getElementById("generateSeoBtn");
const clearSeoBtn = document.getElementById("clearSeoBtn");
const copyInputBtn = document.getElementById("copyInputBtn");
const copyAllSeoBtn = document.getElementById("copyAllSeoBtn");
const copySeoOutputBtn = document.getElementById("copySeoOutputBtn");

const focusKeyphrase = document.getElementById("focusKeyphrase");
const seoTitle = document.getElementById("seoTitle");
const metaDescription = document.getElementById("metaDescription");
const seoOutput = document.getElementById("seoOutput");
const detectedEmbeds = document.getElementById("detectedEmbeds");
const structureInfo = document.getElementById("structureInfo");
const previewTitle = document.getElementById("previewTitle");
const previewMeta = document.getElementById("previewMeta");
const seoTitleCounter = document.getElementById("seoTitleCounter");
const metaCounter = document.getElementById("metaCounter");

// Image tab
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


function getApiKey() {
  return localStorage.getItem(STORAGE_KEY) || "";
}

function setStatus(message, tone = "normal") {
  statusLabel.textContent = message;
  statusLabel.className = "";
  if (tone) {
    statusLabel.classList.add(tone);
  }
}

function updateApiBadge() {
  const apiKey = getApiKey();
  if (apiKey) {
    apiBadge.textContent = "● API key saved";
    apiBadge.classList.remove("off");
    apiBadge.classList.add("on");
  } else {
    apiBadge.textContent = "○ API not configured";
    apiBadge.classList.remove("on");
    apiBadge.classList.add("off");
  }
}

function openApiModal() {
  apiModal.classList.remove("hidden");
  apiModal.setAttribute("aria-hidden", "false");
  apiKeyInput.value = getApiKey();
  apiModalStatus.textContent = apiKeyInput.value ? "Current key loaded." : "Paste your API key below.";
}

function closeApiModal() {
  apiModal.classList.add("hidden");
  apiModal.setAttribute("aria-hidden", "true");
}

function switchTab(tabId) {
  tabButtons.forEach(btn => {
    btn.classList.toggle("active", btn.dataset.tab === tabId);
  });
  tabPanels.forEach(panel => {
    panel.classList.toggle("active", panel.id === tabId);
  });
}

async function copyText(value, successMsg = "Copied.") {
  const text = String(value || "").trim();
  if (!text) {
    setStatus("Nothing to copy.", "warn");
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    setStatus(successMsg, "success");
  } catch {
    setStatus("Copy failed.", "error");
  }
}

function updateSeoPreview() {
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

async function testApiKey() {
  const apiKey = apiKeyInput.value.trim();
  if (!apiKey) {
    apiModalStatus.textContent = "Paste API key first.";
    return;
  }

  apiModalStatus.textContent = "Testing API key...";
  try {
    const res = await fetch("/api/test-key", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ api_key: apiKey })
    });
    const data = await res.json();
    apiModalStatus.textContent = data.message || (data.ok ? "API key is valid." : "API key test failed.");
  } catch (err) {
    apiModalStatus.textContent = err.message || "API key test failed.";
  }
}

function saveApiKey() {
  const apiKey = apiKeyInput.value.trim();
  if (!apiKey) {
    apiModalStatus.textContent = "API key is empty.";
    return;
  }
  localStorage.setItem(STORAGE_KEY, apiKey);
  updateApiBadge();
  apiModalStatus.textContent = "API key saved in browser.";
  setStatus("API key saved.", "success");
}

function clearApiKey() {
  localStorage.removeItem(STORAGE_KEY);
  apiKeyInput.value = "";
  updateApiBadge();
  apiModalStatus.textContent = "Saved API key cleared.";
  setStatus("Saved API key cleared.", "warn");
}

async function generateSeo() {
  const article = articleInput.value.trim();
  if (!article) {
    setStatus("Paste article input first.", "error");
    return;
  }

  generateSeoBtn.disabled = true;
  setStatus("Generating SEO...", "normal");

  try {
    const res = await fetch("/api/generate-seo", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        article,
        api_key: getApiKey()
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

    updateSeoPreview();
    setStatus("SEO generated successfully.", "success");
  } catch (err) {
    setStatus(err.message || "Unexpected error.", "error");
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
  updateSeoPreview();
  setStatus("SEO fields cleared.", "warn");
}

function previewSelectedImage() {
  const file = imageInput.files && imageInput.files[0];
  if (!file) {
    imagePreview.src = "";
    imagePreview.classList.add("hidden");
    imagePlaceholder.classList.remove("hidden");
    return;
  }

  const reader = new FileReader();
  reader.onload = () => {
    imagePreview.src = reader.result;
    imagePreview.classList.remove("hidden");
    imagePlaceholder.classList.add("hidden");
  };
  reader.readAsDataURL(file);
}

async function generateImageSeo() {
  const file = imageInput.files && imageInput.files[0];
  if (!file) {
    setStatus("Upload image first.", "error");
    return;
  }

  generateImageSeoBtn.disabled = true;
  setStatus("Generating image SEO...", "normal");

  try {
    const formData = new FormData();
    formData.append("image", file);
    formData.append("scene_notes", sceneNotes.value.trim());
    formData.append("api_key", getApiKey());

    const res = await fetch("/api/generate-image-seo", {
      method: "POST",
      body: formData
    });

    const data = await res.json();
    if (!res.ok || !data.ok) {
      throw new Error(data.error || "Failed to generate image SEO.");
    }

    altText.value = data.alt_text || "";
    imgTitle.value = data.img_title || "";
    caption.value = data.caption || "";

    setStatus("Image SEO generated successfully.", "success");
  } catch (err) {
    setStatus(err.message || "Unexpected error.", "error");
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
  imagePreview.src = "";
  imagePreview.classList.add("hidden");
  imagePlaceholder.classList.remove("hidden");
  setStatus("Image SEO fields cleared.", "warn");
}

function copyAllSeoFields() {
  const parts = [
    `Focus Keyphrase: ${focusKeyphrase.value || ""}`,
    `SEO Title: ${seoTitle.value || ""}`,
    `Meta Description: ${metaDescription.value || ""}`
  ];
  copyText(parts.join("\n"), "All SEO fields copied.");
}

function copyAllImageFields() {
  const parts = [
    `Alt Text: ${altText.value || ""}`,
    `Image Title: ${imgTitle.value || ""}`,
    `Caption: ${caption.value || ""}`
  ];
  copyText(parts.join("\n"), "All image fields copied.");
}


// Event wiring
openApiSettingsBtn.addEventListener("click", openApiModal);
closeApiSettingsBtn.addEventListener("click", closeApiModal);
testApiKeyBtn.addEventListener("click", testApiKey);
saveApiKeyBtn.addEventListener("click", saveApiKey);
clearApiKeyBtn.addEventListener("click", clearApiKey);

showApiKeyCheckbox.addEventListener("change", () => {
  apiKeyInput.type = showApiKeyCheckbox.checked ? "text" : "password";
});

apiModal.addEventListener("click", (e) => {
  if (e.target === apiModal) closeApiModal();
});

tabButtons.forEach(btn => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});

generateSeoBtn.addEventListener("click", generateSeo);
clearSeoBtn.addEventListener("click", clearSeo);
copyInputBtn.addEventListener("click", () => copyText(articleInput.value, "Input copied."));
copyAllSeoBtn.addEventListener("click", copyAllSeoFields);
copySeoOutputBtn.addEventListener("click", () => copyText(seoOutput.value, "SEO output copied."));

imageInput.addEventListener("change", previewSelectedImage);
generateImageSeoBtn.addEventListener("click", generateImageSeo);
clearImageBtn.addEventListener("click", clearImageSeo);
copyAllImageBtn.addEventListener("click", copyAllImageFields);

document.querySelectorAll("[data-copy-target]").forEach(btn => {
  btn.addEventListener("click", () => {
    const id = btn.getAttribute("data-copy-target");
    const el = document.getElementById(id);
    if (!el) return;
    copyText(el.value, `${id} copied.`);
  });
});

// Init
updateApiBadge();
updateSeoPreview();
previewSelectedImage();
