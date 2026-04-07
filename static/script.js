const state = {
  apiKey: sessionStorage.getItem("together_api_key") || "",
  activeTab: "seo",
  imageOriginal: null,
  imageCurrent: null,
  imageObj: null,
  cropRect: null,
  isDragging: false,
  dragStart: null,
  canvasScaleX: 1,
  canvasScaleY: 1,
};

const seoTabBtn = document.getElementById("seoTabBtn");
const imageTabBtn = document.getElementById("imageTabBtn");
const seoTab = document.getElementById("seoTab");
const imageTab = document.getElementById("imageTab");

const openApiSettingsBtn = document.getElementById("openApiSettingsBtn");
const closeApiSettingsBtn = document.getElementById("closeApiSettingsBtn");
const apiModal = document.getElementById("apiModal");
const apiKeyInput = document.getElementById("apiKeyInput");
const toggleApiVisibilityBtn = document.getElementById("toggleApiVisibilityBtn");
const testApiKeyBtn = document.getElementById("testApiKeyBtn");
const saveApiKeyBtn = document.getElementById("saveApiKeyBtn");
const clearApiKeyBtn = document.getElementById("clearApiKeyBtn");
const apiModalStatus = document.getElementById("apiModalStatus");
const apiBadge = document.getElementById("apiBadge");
const bottomStatus = document.getElementById("bottomStatus");

const articleInput = document.getElementById("articleInput");
const generateSeoBtn = document.getElementById("generateSeoBtn");
const clearSeoBtn = document.getElementById("clearSeoBtn");
const copyInputBtn = document.getElementById("copyInputBtn");

const focusKeyphrase = document.getElementById("focusKeyphrase");
const seoTitle = document.getElementById("seoTitle");
const metaDescription = document.getElementById("metaDescription");
const detectedEmbeds = document.getElementById("detectedEmbeds");
const seoOutput = document.getElementById("seoOutput");
const structureInfo = document.getElementById("structureInfo");
const copySeoOutputBtn = document.getElementById("copySeoOutputBtn");

const previewTitle = document.getElementById("previewTitle");
const previewMeta = document.getElementById("previewMeta");
const seoTitleCounter = document.getElementById("seoTitleCounter");
const metaCounter = document.getElementById("metaCounter");

const imageFileInput = document.getElementById("imageFileInput");
const clearImageBtn = document.getElementById("clearImageBtn");
const resetCropBtn = document.getElementById("resetCropBtn");
const applyCropBtn = document.getElementById("applyCropBtn");
const cropInfo = document.getElementById("cropInfo");
const imageCanvas = document.getElementById("imageCanvas");
const imageCtx = imageCanvas.getContext("2d");
const croppedPreview = document.getElementById("croppedPreview");
const sceneNotes = document.getElementById("sceneNotes");
const generateImageSeoBtn = document.getElementById("generateImageSeoBtn");
const copyImageSeoBtn = document.getElementById("copyImageSeoBtn");
const altText = document.getElementById("altText");
const imgTitle = document.getElementById("imgTitle");
const caption = document.getElementById("caption");

function setBottomStatus(text) {
  bottomStatus.textContent = `  ${text}`;
}

function setModalStatus(text) {
  apiModalStatus.textContent = text;
}

function updateApiBadge() {
  apiBadge.classList.remove("badge-empty", "badge-session", "badge-saved");
  if (state.apiKey) {
    apiBadge.textContent = "● Session key active";
    apiBadge.classList.add("badge-session");
  } else {
    apiBadge.textContent = "○ API not configured";
    apiBadge.classList.add("badge-empty");
  }
}

function openApiModal() {
  apiKeyInput.value = state.apiKey || "";
  apiModal.classList.remove("hidden");
}

function closeApiModal() {
  apiModal.classList.add("hidden");
}

function switchTab(tab) {
  state.activeTab = tab;
  seoTabBtn.classList.toggle("active", tab === "seo");
  imageTabBtn.classList.toggle("active", tab === "image");
  seoTab.classList.toggle("active", tab === "seo");
  imageTab.classList.toggle("active", tab === "image");
}

function setCounter(el, value, goodMin, max) {
  el.textContent = `${value} / ${max}`;
  el.classList.remove("good", "warn", "bad");
  if (value === 0) return;
  if (value > max) el.classList.add("bad");
  else if (value >= goodMin) el.classList.add("good");
  else el.classList.add("warn");
}

function updatePreview() {
  const title = (seoTitle.value || "").trim();
  const meta = (metaDescription.value || "").trim();
  previewTitle.textContent = title || "SEO Title will appear here";
  previewMeta.textContent = meta || "Meta description will appear here.";
  setCounter(seoTitleCounter, title.length, 50, 60);
  setCounter(metaCounter, meta.length, 120, 160);
}

async function copyText(text, okMessage = "Copied.") {
  if (!text || !String(text).trim()) {
    setBottomStatus("Nothing to copy");
    return;
  }
  try {
    await navigator.clipboard.writeText(String(text));
    setBottomStatus(okMessage);
  } catch {
    setBottomStatus("Copy failed");
  }
}

async function postJSON(url, payload) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
  const data = await res.json();
  if (!res.ok || !data.ok) {
    throw new Error(data.error || data.message || "Request failed");
  }
  return data;
}

async function testApiKey() {
  const key = apiKeyInput.value.trim();
  if (!key) {
    setModalStatus("Paste your API key first.");
    return;
  }
  setModalStatus("Testing...");
  try {
    const data = await postJSON("/api/verify-key", { api_key: key });
    setModalStatus(data.message || "API key is valid.");
  } catch (e) {
    setModalStatus(e.message || "API test failed.");
  }
}

function saveApiKey() {
  const key = apiKeyInput.value.trim();
  state.apiKey = key;
  if (key) {
    sessionStorage.setItem("together_api_key", key);
    setBottomStatus("API key loaded");
    setModalStatus("Session key active.");
  } else {
    sessionStorage.removeItem("together_api_key");
    setModalStatus("API key cleared.");
    setBottomStatus("API key cleared");
  }
  updateApiBadge();
  closeApiModal();
}

function clearApiKey() {
  state.apiKey = "";
  apiKeyInput.value = "";
  sessionStorage.removeItem("together_api_key");
  updateApiBadge();
  setModalStatus("API key cleared.");
  setBottomStatus("API key cleared");
}

async function generateSeo() {
  const article = articleInput.value.trim();
  if (!article) {
    setBottomStatus("Paste article input first");
    return;
  }

  generateSeoBtn.disabled = true;
  setBottomStatus("Generating SEO...");
  try {
    const data = await postJSON("/api/generate-seo", {
      api_key: state.apiKey,
      article,
    });

    focusKeyphrase.value = data.focus_keyphrase || "";
    seoTitle.value = data.seo_title || "";
    metaDescription.value = data.meta_description || "";
    detectedEmbeds.value = data.detected_embeds || "";
    seoOutput.value = data.seo_output || "";
    structureInfo.value = data.structure || "";
    updatePreview();
    setBottomStatus("SEO generated");
  } catch (e) {
    setBottomStatus(e.message || "SEO generation failed");
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
  setBottomStatus("SEO fields cleared");
}

function imageToDataURL(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.onerror = reject;
    r.readAsDataURL(file);
  });
}

function loadImage(dataUrl) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = dataUrl;
  });
}

function fitImageToCanvas(img) {
  const maxW = imageCanvas.width;
  const maxH = imageCanvas.height;
  const ratio = Math.min(maxW / img.width, maxH / img.height, 1);
  const drawW = Math.round(img.width * ratio);
  const drawH = Math.round(img.height * ratio);
  const dx = Math.round((maxW - drawW) / 2);
  const dy = Math.round((maxH - drawH) / 2);

  state.canvasScaleX = img.width / drawW;
  state.canvasScaleY = img.height / drawH;

  return { drawW, drawH, dx, dy };
}

function drawCanvas() {
  imageCtx.clearRect(0, 0, imageCanvas.width, imageCanvas.height);
  imageCtx.fillStyle = "#02111f";
  imageCtx.fillRect(0, 0, imageCanvas.width, imageCanvas.height);

  if (!state.imageObj) return;

  const fit = fitImageToCanvas(state.imageObj);
  state.lastFit = fit;
  imageCtx.drawImage(state.imageObj, fit.dx, fit.dy, fit.drawW, fit.drawH);

  if (state.cropRect) {
    const { x, y, w, h } = state.cropRect;
    imageCtx.fillStyle = "rgba(0,0,0,0.35)";
    imageCtx.fillRect(0, 0, imageCanvas.width, imageCanvas.height);

    imageCtx.drawImage(state.imageObj, fit.dx, fit.dy, fit.drawW, fit.drawH);

    imageCtx.clearRect(x, y, w, h);
    imageCtx.drawImage(state.imageObj, fit.dx, fit.dy, fit.drawW, fit.drawH);

    imageCtx.strokeStyle = "#22c55e";
    imageCtx.lineWidth = 2;
    imageCtx.strokeRect(x, y, w, h);

    imageCtx.fillStyle = "rgba(34,197,94,0.15)";
    imageCtx.fillRect(x, y, w, h);
  }
}

function clampCropToImage(rect) {
  if (!state.lastFit) return rect;
  const { dx, dy, drawW, drawH } = state.lastFit;

  let x = Math.max(rect.x, dx);
  let y = Math.max(rect.y, dy);
  let w = rect.w;
  let h = rect.h;

  if (x + w > dx + drawW) w = dx + drawW - x;
  if (y + h > dy + drawH) h = dy + drawH - y;

  return {
    x: Math.max(dx, x),
    y: Math.max(dy, y),
    w: Math.max(1, w),
    h: Math.max(1, h),
  };
}

function canvasEventPoint(e) {
  const rect = imageCanvas.getBoundingClientRect();
  const scaleX = imageCanvas.width / rect.width;
  const scaleY = imageCanvas.height / rect.height;
  return {
    x: (e.clientX - rect.left) * scaleX,
    y: (e.clientY - rect.top) * scaleY,
  };
}

async function handleImageUpload(file) {
  if (!file) return;
  const dataUrl = await imageToDataURL(file);
  const img = await loadImage(dataUrl);
  state.imageOriginal = dataUrl;
  state.imageCurrent = dataUrl;
  state.imageObj = img;
  state.cropRect = null;
  croppedPreview.src = dataUrl;
  drawCanvas();
  cropInfo.textContent = `Loaded image: ${img.width} × ${img.height}`;
  setBottomStatus("Image loaded");
}

function resetCropBox() {
  state.cropRect = null;
  drawCanvas();
  cropInfo.textContent = state.imageObj ? `Image ready: ${state.imageObj.width} × ${state.imageObj.height}` : "No image loaded";
  setBottomStatus("Crop box reset");
}

async function applyCrop() {
  if (!state.imageObj || !state.cropRect || !state.lastFit) {
    setBottomStatus("Create crop area first");
    return;
  }

  const fit = state.lastFit;
  const crop = clampCropToImage(state.cropRect);

  const sx = Math.round((crop.x - fit.dx) * state.canvasScaleX);
  const sy = Math.round((crop.y - fit.dy) * state.canvasScaleY);
  const sw = Math.round(crop.w * state.canvasScaleX);
  const sh = Math.round(crop.h * state.canvasScaleY);

  const tmp = document.createElement("canvas");
  tmp.width = Math.max(1, sw);
  tmp.height = Math.max(1, sh);
  const tctx = tmp.getContext("2d");

  const srcImg = await loadImage(state.imageCurrent);
  tctx.drawImage(srcImg, sx, sy, sw, sh, 0, 0, sw, sh);

  const newDataUrl = tmp.toDataURL("image/jpeg", 0.92);
  const newImg = await loadImage(newDataUrl);

  state.imageCurrent = newDataUrl;
  state.imageObj = newImg;
  state.cropRect = null;
  croppedPreview.src = newDataUrl;
  drawCanvas();
  cropInfo.textContent = `Crop applied: ${newImg.width} × ${newImg.height}`;
  setBottomStatus("Crop applied");
}

function clearImageSeoFields() {
  altText.value = "";
  imgTitle.value = "";
  caption.value = "";
}

function clearImageAll() {
  imageFileInput.value = "";
  state.imageOriginal = null;
  state.imageCurrent = null;
  state.imageObj = null;
  state.cropRect = null;
  croppedPreview.removeAttribute("src");
  sceneNotes.value = "";
  clearImageSeoFields();
  imageCtx.clearRect(0, 0, imageCanvas.width, imageCanvas.height);
  imageCtx.fillStyle = "#02111f";
  imageCtx.fillRect(0, 0, imageCanvas.width, imageCanvas.height);
  cropInfo.textContent = "No image loaded";
  setBottomStatus("Cleared all image SEO fields");
}

async function generateImageSeo() {
  if (!state.imageCurrent) {
    setBottomStatus("Upload an image first");
    return;
  }

  generateImageSeoBtn.disabled = true;
  setBottomStatus("Reading image & generating WordPress SEO fields...");
  try {
    const data = await postJSON("/api/generate-image-seo", {
      api_key: state.apiKey,
      image_data_url: state.imageCurrent,
      scene_notes: sceneNotes.value.trim(),
    });

    altText.value = data.alt_text || "";
    imgTitle.value = data.img_title || "";
    caption.value = data.caption || "";
    setBottomStatus("AI image SEO ready");
  } catch (e) {
    setBottomStatus(e.message || "Image SEO generation failed");
  } finally {
    generateImageSeoBtn.disabled = false;
  }
}

function copyImageSeoFields() {
  const text = [
    `Alt Text: ${altText.value || ""}`,
    `Image Title: ${imgTitle.value || ""}`,
    `Caption: ${caption.value
