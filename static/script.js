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
    const res = await fetch("/api/test-key", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ api_key: key })
    });
    const json = await res.json();
    if (!json.ok) {
      setApiModalStatus("API key test failed");
      setStatus("API key test failed");
      return;
    }
    setApiModalStatus("API key test passed");
    setStatus("API key is valid and ready to use.");
  } catch {
    setApiModalStatus("API key test failed");
    setStatus("Network error while testing API key");
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
    const res = await fetch("/api/process-article", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });
    const json = await res.json();

    if (!json.ok) {
      articleData = null;
      clearArticleHiddenFields();
      articleOutputText.value = json.error || "Something went wrong.";
      setStatus("Article process failed");
      return;
    }

    articleData = json.data;
    if (json.data.imported_article_text) {
      articleInputText.value = json.data.imported_article_text;
    }
    fillArticleData(json.data);
    setStatus("Article SEO output generated");
  } catch (err) {
    articleData = null;
    clearArticleHiddenFields();
    articleOutputText.value = String(err);
    setStatus("Network error while processing article");
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

  try {
    const res = await fetch("/api/process-image", {
      method: "POST",
      body: formData
    });
    const json = await res.json();

    if (!json.ok) {
      setStatus(json.error || "Image SEO failed");
      return;
    }

    imageData = json.data;
    altTextOutput.value = imageData.alt_text || "";
    imageTitleOutput.value = imageData.image_title || "";
    captionOutput.value = imageData.caption || "";
    cropInfoLabel.textContent = `Optimized image ready • ${imageData.optimized_size_kb} KB`;

    if (imageData.optimized_base64) {
      imagePreview.src = `data:image/jpeg;base64,${imageData.optimized_base64}`;
    }

    setStatus("Generated image SEO fields");
  } catch {
    setStatus("Network error while generating image SEO");
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
  imagePreview.src = "";
  imagePreview.classList.add("hidden");
  imagePreviewPlaceholder.classList.remove("hidden");
  cropInfoLabel.textContent = "No image loaded";
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
      setStatus("Export failed");
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

updateApiInfo();
setStatus("Ready");
