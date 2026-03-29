let sessionApiKey = "";
let articleData = null;
let imageData = null;
let imageFileObject = null;

const apiInfo = document.getElementById("apiInfo");
const statusBar = document.getElementById("statusBar");

const apiSettingsBtn = document.getElementById("apiSettingsBtn");
const apiModal = document.getElementById("apiModal");
const apiKeyInput = document.getElementById("apiKeyInput");
const showApiCheckbox = document.getElementById("showApiCheckbox");
const saveApiCheckbox = document.getElementById("saveApiCheckbox");
const testApiBtn = document.getElementById("testApiBtn");
const saveApiBtn = document.getElementById("saveApiBtn");
const sessionApiBtn = document.getElementById("sessionApiBtn");
const clearSavedApiBtn = document.getElementById("clearSavedApiBtn");
const apiModalStatus = document.getElementById("apiModalStatus");

const articleUrl = document.getElementById("articleUrl");
const articleInputText = document.getElementById("articleInputText");
const articleOutputText = document.getElementById("articleOutputText");
const generateArticleBtn = document.getElementById("generateArticleBtn");
const clearArticleBtn = document.getElementById("clearArticleBtn");
const copyHtmlBtn = document.getElementById("copyHtmlBtn");

const focusKeyphrase = document.getElementById("focusKeyphrase");
const seoTitle = document.getElementById("seoTitle");
const metaDescription = document.getElementById("metaDescription");
const slug = document.getElementById("slug");
const shortSummary = document.getElementById("shortSummary");
const wordpressHtml = document.getElementById("wordpressHtml");

const imageFileInput = document.getElementById("imageFileInput");
const imagePreview = document.getElementById("imagePreview");
const imagePreviewPlaceholder = document.getElementById("imagePreviewPlaceholder");
const cropInfoLabel = document.getElementById("cropInfoLabel");
const sceneInput = document.getElementById("sceneInput");
const altTextOutput = document.getElementById("altTextOutput");
const imageTitleOutput = document.getElementById("imageTitleOutput");
const captionOutput = document.getElementById("captionOutput");
const processImageBtn = document.getElementById("processImageBtn");
const clearImageBtn = document.getElementById("clearImageBtn");
const exportImageBtn = document.getElementById("exportImageBtn");

const brightnessRange = document.getElementById("brightnessRange");
const sharpnessRange = document.getElementById("sharpnessRange");
const blurRange = document.getElementById("blurRange");

const preset1200x366Btn = document.getElementById("preset1200x366Btn");
const preset800x445Btn = document.getElementById("preset800x445Btn");
const lockRatioCheckbox = document.getElementById("lockRatioCheckbox");
const zoneZoomRange = document.getElementById("zoneZoomRange");
const cropX = document.getElementById("cropX");
const cropY = document.getElementById("cropY");
const cropWidth = document.getElementById("cropWidth");
const cropHeight = document.getElementById("cropHeight");

function setStatus(message) {
  statusBar.textContent = message || "Ready";
}

function setApiModalStatus(message) {
  apiModalStatus.textContent = message || "Ready";
}

function getSavedApiKey() {
  return localStorage.getItem("together_api_key") || "";
}

function getCurrentApiKey() {
  return (sessionApiKey || getSavedApiKey() || "").trim();
}

function updateApiInfo() {
  apiInfo.textContent = getCurrentApiKey() ? "API: configured" : "API: not configured";
}

function openApiModal() {
  apiKeyInput.value = getCurrentApiKey();
  apiModal.classList.remove("hidden");
  setApiModalStatus(getCurrentApiKey() ? "Loaded current API key into this window" : "Paste your Together AI API key");
}

function closeApiModal() {
  apiModal.classList.add("hidden");
}

async function copyToClipboard(text, successStatus) {
  if (!text || !text.trim()) {
    setStatus("Nothing to copy");
    return;
  }

  try {
    await navigator.clipboard.writeText(text);
    setStatus(successStatus);
  } catch {
    const temp = document.createElement("textarea");
    temp.value = text;
    document.body.appendChild(temp);
    temp.select();
    document.execCommand("copy");
    temp.remove();
    setStatus(successStatus);
  }
}

function fileToDataURL(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

async function safeFetchJson(url, options = {}) {
  const res = await fetch(url, options);
  const text = await res.text();

  let data;
  try {
    data = JSON.parse(text);
  } catch {
    throw new Error(`Server returned non-JSON response:\n${text.slice(0, 300)}`);
  }

  if (!res.ok) {
    throw new Error(data.error || `Request failed with status ${res.status}`);
  }

  return data;
}

function activatePreset(name) {
  preset1200x366Btn.dataset.active = name === "1200x366" ? "1" : "0";
  preset800x445Btn.dataset.active = name === "800x445" ? "1" : "0";
}

function setCropPreset(w, h) {
  cropWidth.value = String(w);
  cropHeight.value = String(h);
  cropX.value = "0";
  cropY.value = "0";
  setStatus(`Crop preset set: ${w}x${h}`);
}

function applyLockedRatio(changedField) {
  if (!lockRatioCheckbox.checked) return;

  const w = parseFloat(cropWidth.value || "1");
  const h = parseFloat(cropHeight.value || "1");

  if (changedField === "width") {
    if (preset1200x366Btn.dataset.active === "1") {
      cropHeight.value = String(Math.max(1, Math.round((w * 366) / 1200)));
    } else if (preset800x445Btn.dataset.active === "1") {
      cropHeight.value = String(Math.max(1, Math.round((w * 445) / 800)));
    }
  }

  if (changedField === "height") {
    if (preset1200x366Btn.dataset.active === "1") {
      cropWidth.value = String(Math.max(1, Math.round((h * 1200) / 366)));
    } else if (preset800x445Btn.dataset.active === "1") {
      cropWidth.value = String(Math.max(1, Math.round((h * 800) / 445)));
    }
  }
}

apiSettingsBtn.addEventListener("click", openApiModal);

apiModal.addEventListener("click", (e) => {
  if (e.target === apiModal) closeApiModal();
});

showApiCheckbox.addEventListener("change", () => {
  apiKeyInput.type = showApiCheckbox.checked ? "text" : "password";
});

testApiBtn.addEventListener("click", async () => {
  const key = apiKeyInput.value.trim();
  if (!key) {
    setApiModalStatus("Please paste your API key first.");
    return;
  }

  setApiModalStatus("Testing API key...");
  try {
    const json = await safeFetchJson("/api/test-key", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ api_key: key })
    });

    setApiModalStatus("API key test passed");
    setStatus(json.message || "API key is valid and ready to use.");
  } catch (err) {
    setApiModalStatus("API key test failed");
    setStatus(err.message || "API key test failed");
  }
});

saveApiBtn.addEventListener("click", () => {
  const key = apiKeyInput.value.trim();
  if (!key) {
    setApiModalStatus("Please paste your API key first.");
    return;
  }

  sessionApiKey = key;
  if (saveApiCheckbox.checked) {
    localStorage.setItem("together_api_key", key);
  }
  updateApiInfo();
  setApiModalStatus("API key applied successfully");
  setStatus("API key applied successfully");
  closeApiModal();
});

sessionApiBtn.addEventListener("click", () => {
  const key = apiKeyInput.value.trim();
  if (!key) {
    setApiModalStatus("Please paste your API key first.");
    return;
  }

  sessionApiKey = key;
  updateApiInfo();
  setApiModalStatus("Using API key for this session only");
  setStatus("Using API key for this session only");
  closeApiModal();
});

clearSavedApiBtn.addEventListener("click", () => {
  localStorage.removeItem("together_api_key");
  sessionApiKey = "";
  apiKeyInput.value = "";
  updateApiInfo();
  setApiModalStatus("Saved API key cleared");
  setStatus("Saved API key cleared");
});

function clearArticleHiddenFields() {
  focusKeyphrase.value = "";
  seoTitle.value = "";
  metaDescription.value = "";
  slug.value = "";
  shortSummary.value = "";
  wordpressHtml.value = "";
}

function fillArticleData(data) {
  focusKeyphrase.value = data.focus_keyphrase || "";
  seoTitle.value = data.seo_title || "";
  metaDescription.value = data.meta_description || "";
  slug.value = data.slug || "";
  shortSummary.value = data.short_summary || "";
  wordpressHtml.value = data.wordpress_html || "";
  articleOutputText.value = data.output_preview || "";
}

generateArticleBtn.addEventListener("click", async () => {
  const payload = {
    article_url: articleUrl.value.trim(),
    article_text: articleInputText.value.trim(),
    api_key: getCurrentApiKey()
  };

  if (!payload.article_url && (!payload.article_text || payload.article_text === "Paste your article here...")) {
    articleOutputText.value = "Please paste a news URL or article first.";
    setStatus("Please paste a news URL or article first");
    return;
  }

  generateArticleBtn.disabled = true;
  generateArticleBtn.textContent = "Generating...";
  setStatus("Generating SEO output...");

  try {
    const json = await safeFetchJson("/api/process-article", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });

    articleData = json.data;
    if (json.data.imported_article_text) {
      articleInputText.value = json.data.imported_article_text;
    }
    fillArticleData(json.data);
    setStatus("Article SEO output generated");
  } catch (err) {
    articleData = null;
    clearArticleHiddenFields();
    articleOutputText.value = err.message || "Something went wrong.";
    setStatus(err.message || "Article process failed");
  } finally {
    generateArticleBtn.disabled = false;
    generateArticleBtn.textContent = "Generate News Format";
  }
});

clearArticleBtn.addEventListener("click", () => {
  articleData = null;
  articleUrl.value = "";
  articleInputText.value = "Paste your article here...";
  articleOutputText.value = "Formatted SEO output will appear here.";
  clearArticleHiddenFields();
  setStatus("Input cleared");
});

copyHtmlBtn.addEventListener("click", () => {
  if (!articleData || !wordpressHtml.value.trim()) {
    setStatus("Generate SEO output first");
    return;
  }
  copyToClipboard(wordpressHtml.value, "Copied WordPress HTML");
});

document.querySelectorAll("[data-copy-article]").forEach(btn => {
  btn.addEventListener("click", () => {
    if (!articleData) {
      setStatus("Generate SEO output first");
      return;
    }

    const key = btn.getAttribute("data-copy-article");
    const map = {
      focus_keyphrase: focusKeyphrase.value,
      seo_title: seoTitle.value,
      meta_description: metaDescription.value
    };
    const labelMap = {
      focus_keyphrase: "Focus Keyphrase",
      seo_title: "SEO Title",
      meta_description: "Meta Description"
    };
    copyToClipboard(map[key] || "", `Smooth copied: ${labelMap[key]}`);
  });
});

articleInputText.addEventListener("focus", () => {
  if (articleInputText.value.trim() === "Paste your article here...") {
    articleInputText.value = "";
  }
});

articleInputText.addEventListener("blur", () => {
  if (!articleInputText.value.trim()) {
    articleInputText.value = "Paste your article here...";
  }
});

imageFileInput.addEventListener("change", async (e) => {
  const file = e.target.files && e.target.files[0];
  if (!file) return;

  imageFileObject = file;
  const dataUrl = await fileToDataURL(file);

  imagePreview.src = dataUrl;
  imagePreview.classList.remove("hidden");
  imagePreviewPlaceholder.classList.add("hidden");
  cropInfoLabel.textContent = `${file.name} loaded`;
  imagePreview.style.transform = `scale(${zoneZoomRange.value || "1"})`;
  imagePreview.style.transformOrigin = "center center";
  setStatus("Imported featured image");
});

processImageBtn.addEventListener("click", async () => {
  if (!imageFileObject) {
    setStatus("Please import an image first");
    return;
  }

  processImageBtn.disabled = true;
  processImageBtn.textContent = "Generating...";
  setStatus("Generating image SEO...");

  const formData = new FormData();
  formData.append("image", imageFileObject);
  formData.append("api_key", getCurrentApiKey());
  formData.append("scene_text", sceneInput.value.trim());
  formData.append("max_kb", "100");
  formData.append("brightness", brightnessRange.value);
  formData.append("sharpness", sharpnessRange.value);
  formData.append("blur_radius", blurRange.value);
  formData.append("crop", JSON.stringify({
    x: parseInt(cropX.value || "0", 10),
    y: parseInt(cropY.value || "0", 10),
    width: parseInt(cropWidth.value || "1200", 10),
    height: parseInt(cropHeight.value || "366", 10)
  }));

  try {
    const json = await safeFetchJson("/api/process-image", {
      method: "POST",
      body: formData
    });

    imageData = json.data;
    altTextOutput.value = imageData.alt_text || "";
    imageTitleOutput.value = imageData.image_title || "";
    captionOutput.value = imageData.caption || "";
    cropInfoLabel.textContent = `Optimized image ready • ${imageData.optimized_size_kb} KB`;

    if (imageData.optimized_base64) {
      imagePreview.src = `data:image/jpeg;base64,${imageData.optimized_base64}`;
      imagePreview.style.transform = `scale(${zoneZoomRange.value || "1"})`;
      imagePreview.style.transformOrigin = "center center";
    }

    setStatus("Generated image SEO fields");
  } catch (err) {
    setStatus(err.message || "Image SEO failed");
  } finally {
    processImageBtn.disabled = false;
    processImageBtn.textContent = "Generate Image SEO";
  }
});

clearImageBtn.addEventListener("click", () => {
  imageData = null;
  imageFileObject = null;
  imageFileInput.value = "";
  sceneInput.value = "";
  altTextOutput.value = "";
  imageTitleOutput.value = "";
  captionOutput.value = "";
  brightnessRange.value = "1.0";
  sharpnessRange.value = "1.0";
  blurRange.value = "0";
  cropX.value = "0";
  cropY.value = "0";
  cropWidth.value = "1200";
  cropHeight.value = "366";
  zoneZoomRange.value = "1";
  imagePreview.src = "";
  imagePreview.style.transform = "scale(1)";
  imagePreview.classList.add("hidden");
  imagePreviewPlaceholder.classList.remove("hidden");
  cropInfoLabel.textContent = "No image loaded";
  activatePreset("1200x366");
  setStatus("Cleared all image SEO fields");
});

exportImageBtn.addEventListener("click", async () => {
  if (!imageData || !imageData.optimized_base64) {
    setStatus("Generate image SEO first");
    return;
  }

  try {
    const res = await fetch("/api/download-image", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ image_base64: imageData.optimized_base64 })
    });

    if (!res.ok) {
      const text = await res.text();
      setStatus(`Export failed: ${text.slice(0, 120)}`);
      return;
    }

    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "optimized-image.jpg";
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
    setStatus("Exported image under target size");
  } catch {
    setStatus("Export failed");
  }
});

document.querySelectorAll("[data-copy-image]").forEach(btn => {
  btn.addEventListener("click", () => {
    const key = btn.getAttribute("data-copy-image");
    const map = {
      alt_text: altTextOutput.value,
      image_title: imageTitleOutput.value,
      caption: captionOutput.value
    };
    const labelMap = {
      alt_text: "Alt Text",
      image_title: "Image Title",
      caption: "Caption"
    };
    copyToClipboard(map[key] || "", `Smooth copied: ${labelMap[key]}`);
  });
});

preset1200x366Btn.addEventListener("click", () => {
  activatePreset("1200x366");
  setCropPreset(1200, 366);
});

preset800x445Btn.addEventListener("click", () => {
  activatePreset("800x445");
  setCropPreset(800, 445);
});

cropWidth.addEventListener("input", () => applyLockedRatio("width"));
cropHeight.addEventListener("input", () => applyLockedRatio("height"));

zoneZoomRange.addEventListener("input", () => {
  const zoom = parseFloat(zoneZoomRange.value || "1");
  imagePreview.style.transform = `scale(${zoom})`;
  imagePreview.style.transformOrigin = "center center";
  setStatus(`Zone Zoom: ${zoom.toFixed(1)}x`);
});

activatePreset("1200x366");
updateApiInfo();
setStatus("Ready");
