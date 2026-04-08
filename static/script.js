const $ = (id) => document.getElementById(id);

let currentApiKey = localStorage.getItem("together_api_key") || "";
let currentImageFile = null;

// ============================================================
// Init
// ============================================================

document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initApiModal();
  initSeoTab();
  initImageTab();
  syncApiUi();
  updateGooglePreview();
  updateSeoMeters();
});

// ============================================================
// Status
// ============================================================

function setStatus(text) {
  $("statusText").textContent = text || "Ready";
}

// ============================================================
// Tabs
// ============================================================

function initTabs() {
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach(x => x.classList.remove("active"));
      document.querySelectorAll(".tab-page").forEach(x => x.classList.remove("active"));
      btn.classList.add("active");
      $(btn.dataset.tab).classList.add("active");
    });
  });
}

// ============================================================
// API Modal
// ============================================================

function syncApiUi() {
  const badge = $("apiBadge");
  const input = $("apiKeyInput");

  input.value = currentApiKey || "";

  badge.classList.remove("badge-off", "badge-session", "badge-on");
  if (!currentApiKey) {
    badge.textContent = "○ API not configured";
    badge.classList.add("badge-off");
  } else {
    badge.textContent = "● API key saved";
    badge.classList.add("badge-on");
  }
}

function initApiModal() {
  $("openApiModalBtn").addEventListener("click", () => {
    $("apiModal").classList.remove("hidden");
  });

  $("closeApiModalBtn").addEventListener("click", () => {
    $("apiModal").classList.add("hidden");
  });

  $("showApiKey").addEventListener("change", (e) => {
    $("apiKeyInput").type = e.target.checked ? "text" : "password";
  });

  $("testApiKeyBtn").addEventListener("click", async () => {
    const key = $("apiKeyInput").value.trim();
    if (!key) {
      setApiModalStatus("Missing API key");
      return;
    }
    setApiModalStatus("Testing...");
    try {
      const r = await fetch("/api/verify-key", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ api_key: key })
      });
      const data = await r.json();
      if (!r.ok || !data.ok) throw new Error(data.error || "Failed");
      setApiModalStatus("✓ API key is valid");
    } catch (err) {
      setApiModalStatus("✗ " + err.message);
    }
  });

  $("saveApiKeyBtn").addEventListener("click", () => {
    currentApiKey = $("apiKeyInput").value.trim();
    localStorage.setItem("together_api_key", currentApiKey);
    syncApiUi();
    setApiModalStatus(currentApiKey ? "✓ Key saved & applied" : "Key cleared");
    setStatus(currentApiKey ? "API key loaded" : "API key cleared");
    $("apiModal").classList.add("hidden");
  });

  $("sessionApiKeyBtn").addEventListener("click", () => {
    currentApiKey = $("apiKeyInput").value.trim();
    syncApiUi();
    setApiModalStatus(currentApiKey ? "● Session key active" : "Key cleared");
    setStatus(currentApiKey ? "API key loaded (session)" : "API key cleared");
    $("apiModal").classList.add("hidden");
  });

  $("clearApiKeyBtn").addEventListener("click", () => {
    currentApiKey = "";
    localStorage.removeItem("together_api_key");
    syncApiUi();
    setApiModalStatus("Saved key cleared");
    setStatus("API key cleared");
  });
}

function setApiModalStatus(text) {
  $("apiModalStatus").textContent = text;
}

// ============================================================
// SEO Tab
// ============================================================

function initSeoTab() {
  $("generateSeoBtn").addEventListener("click", generateSeo);
  $("fetchGenerateBtn").addEventListener("click", generateSeo);
  $("clearSeoBtn").addEventListener("click", clearSeoFields);

  $("copySeoOutputBtn").addEventListener("click", () => copyText($("seoOutput").value));
  $("copyWpOutputBtn").addEventListener("click", () => copyText($("wpHtmlOutput").value));
  $("copyInputBtn").addEventListener("click", () => copyText($("rawInput").value));

  $("copyAllFieldsBtn").addEventListener("click", () => {
    const payload = [
      `Focus Keyphrase: ${$("focusKeyphrase").value}`,
      `SEO Title: ${$("seoTitle").value}`,
      `Meta Description: ${$("metaDescription").value}`,
      `Slug: ${$("slugField").value}`
    ].join("\n");
    copyText(payload);
  });

  $("aiFieldsBtn").addEventListener("click", generateAiFieldsOnly);

  $("pasteSampleBtn").addEventListener("click", () => {
    $("rawInput").value = `<h1>Example News Article About Technology</h1>
<p>This is a sample article paragraph for testing SEO generation.</p>
<p>It includes enough text to generate a title, focus keyphrase, and meta description.</p>
<iframe src="https://www.youtube.com/embed/dQw4w9WgXcQ"></iframe>
<h2>Main Update</h2>
<p>The article also contains an embedded video block like your Python app handles.</p>`;
    setStatus("Sample content loaded");
  });

  $("seoTitle").addEventListener("input", () => {
    updateGooglePreview();
    updateSeoMeters();
  });
  $("metaDescription").addEventListener("input", () => {
    updateGooglePreview();
    updateSeoMeters();
  });

  document.querySelectorAll(".mini-copy").forEach(btn => {
    btn.addEventListener("click", () => {
      const target = $(btn.dataset.copyTarget);
      copyText(target.value);
    });
  });
}

async function generateSeo() {
  const rawInput = $("rawInput").value.trim();
  const articleUrl = $("articleUrl").value.trim();

  if (!rawInput && !articleUrl) {
    setStatus("Please paste an article first");
    return;
  }

  setStatus("Generate SEO started...");
  $("generateSeoBtn").disabled = true;
  $("fetchGenerateBtn").disabled = true;

  try {
    const r = await fetch("/api/generate-seo", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        raw_input: rawInput,
        article_url: articleUrl,
        api_key: currentApiKey
      })
    });

    const data = await r.json();
    if (!r.ok || !data.ok) throw new Error(data.error || "Generate SEO failed");

    $("plainPreview").value = data.plain_preview || "";
    $("focusKeyphrase").value = data.focus_keyphrase || "";
    $("seoTitle").value = data.seo_title || "";
    $("metaDescription").value = data.meta_description || "";
    $("slugField").value = data.slug || "";
    $("seoOutput").value = data.seo_output || "";
    $("wpHtmlOutput").value = data.wp_html_output || "";

    updateGooglePreview();
    updateSeoMeters();
    setStatus(data.status || "Generate SEO completed successfully.");
  } catch (err) {
    setStatus("Error: " + err.message);
  } finally {
    $("generateSeoBtn").disabled = false;
    $("fetchGenerateBtn").disabled = false;
  }
}

async function generateAiFieldsOnly() {
  const rawInput = $("rawInput").value.trim();
  if (!rawInput) {
    setStatus("Paste article first");
    return;
  }
  await generateSeo();
}

function clearSeoFields() {
  [
    "articleUrl",
    "rawInput",
    "plainPreview",
    "focusKeyphrase",
    "seoTitle",
    "metaDescription",
    "slugField",
    "seoOutput",
    "wpHtmlOutput"
  ].forEach(id => $(id).value = "");
  updateGooglePreview();
  updateSeoMeters();
  setStatus("SEO fields cleared");
}

function updateGooglePreview() {
  let title = $("seoTitle").value.trim() || "SEO Title will appear here";
  let meta = $("metaDescription").value.trim() || "Meta description will appear here...";
  if (title.length > 60) title = title.slice(0, 57) + "...";
  if (meta.length > 160) meta = meta.slice(0, 157) + "...";
  $("googleTitle").textContent = title;
  $("googleMeta").textContent = meta;
}

function updateSeoMeters() {
  updateMeter(
    $("seoTitle").value.trim().length,
    60,
    $("seoTitleCount"),
    $("seoTitleHint"),
    $("seoTitleBar")
  );

  updateMeter(
    $("metaDescription").value.trim().length,
    160,
    $("metaDescCount"),
    $("metaDescHint"),
    $("metaDescBar")
  );
}

function updateMeter(value, max, countEl, hintEl, barEl) {
  countEl.textContent = `${value} / ${max}`;
  let color = "var(--ok)";
  let hint = "✓ Good length";

  if (value === 0) {
    hint = "—";
    color = "var(--text-soft)";
  } else if (max === 60) {
    if (value < 30) {
      hint = `⚠ Too short (${value}/60)`;
      color = "var(--warn)";
    } else if (value < 50) {
      hint = `⚠ Could be longer (${value}/60)`;
      color = "var(--warn)";
    } else if (value <= 60) {
      hint = `✓ Good length (${value}/60)`;
      color = "var(--ok)";
    } else {
      hint = `✗ Too long (${value}/60)`;
      color = "var(--bad)";
    }
  } else {
    if (value < 120) {
      hint = `⚠ Too short (${value}/160)`;
      color = "var(--warn)";
    } else if (value <= 160) {
      hint = `✓ Good length (${value}/160)`;
      color = "var(--ok)";
    } else {
      hint = `✗ Too long (${value}/160)`;
      color = "var(--bad)";
    }
  }

  hintEl.textContent = hint;
  countEl.style.color = color;
  hintEl.style.color = color;
  barEl.style.width = `${Math.min(100, (value / max) * 100)}%`;
  barEl.style.background = color;
}

// ============================================================
// Image Tab
// ============================================================

function initImageTab() {
  $("imageFile").addEventListener("change", onImageSelected);
  $("generateImageSeoBtn").addEventListener("click", generateImageSeo);
  $("clearImageBtn").addEventListener("click", clearImageSeo);
  $("copyAllImageSeoBtn").addEventListener("click", () => {
    const payload = [
      `SEO Title: ${$("imgSeoTitle").value}`,
      `Alt Text: ${$("imgAltText").value}`,
      `Caption: ${$("imgCaption").value}`,
      `Description: ${$("imgDescription").value}`,
      `Slug: ${$("imgSlug").value}`
    ].join("\n");
    copyText(payload);
  });

  $("safeZone").addEventListener("change", () => {
    $("safeZoneOverlay").style.display = $("safeZone").checked ? "block" : "none";
  });

  $("zoomRange").addEventListener("input", () => {
    const img = $("imagePreview");
    const z = Number($("zoomRange").value);
    img.style.transform = `scale(${z})`;
  });

  document.querySelectorAll(".preset-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".preset-btn").forEach(x => x.classList.remove("active"));
      btn.classList.add("active");
      setCanvasRatio(btn.dataset.ratio);
    });
  });
}

function onImageSelected(e) {
  const file = e.target.files[0];
  if (!file) return;
  currentImageFile = file;

  const reader = new FileReader();
  reader.onload = () => {
    $("imagePreview").src = reader.result;
    $("imagePreview").classList.remove("hidden");
    $("canvasPlaceholder").classList.add("hidden");
    $("imagePreview").style.transform = "scale(1)";
    $("zoomRange").value = 1;
    setStatus(`Image loaded: ${file.name}`);
  };
  reader.readAsDataURL(file);

  const img = new Image();
  img.onload = () => {
    $("imageSizeText").textContent = `${img.width}×${img.height}`;
    $("imageInfoText").textContent = "Visible: 0% - 100%";
  };
  img.src = URL.createObjectURL(file);
}

function setCanvasRatio(ratioStr) {
  const frame = document.querySelector(".canvas-frame");
  let ratio = "1200 / 366";

  if (ratioStr === "800x445") ratio = "800 / 445";
  if (ratioStr === "1x1") ratio = "1 / 1";
  if (ratioStr === "16x9") ratio = "16 / 9";
  if (ratioStr === "4x3") ratio = "4 / 3";

  frame.style.aspectRatio = ratio;
  setStatus(`Preset set: ${ratioStr}`);
}

async function generateImageSeo() {
  if (!currentImageFile) {
    setStatus("Please upload an image first");
    return;
  }

  $("generateImageSeoBtn").disabled = true;
  setStatus("Generating image SEO...");

  try {
    const fd = new FormData();
    fd.append("image", currentImageFile);
    fd.append("api_key", currentApiKey);

    const r = await fetch("/api/image-seo", {
      method: "POST",
      body: fd
    });

    const data = await r.json();
    if (!r.ok || !data.ok) throw new Error(data.error || "Image SEO failed");

    $("imagePreview").src = data.preview_data_url;
    $("imagePreview").classList.remove("hidden");
    $("canvasPlaceholder").classList.add("hidden");

    $("imgSeoTitle").value = data.seo_title || "";
    $("imgAltText").value = data.alt_text || "";
    $("imgCaption").value = data.caption || "";
    $("imgDescription").value = data.description || "";
    $("imgSlug").value = data.slug || "";

    $("imageSizeText").textContent = `${data.width}×${data.height}`;
    setStatus(data.status || "Image SEO ready");
  } catch (err) {
    setStatus("Error: " + err.message);
  } finally {
    $("generateImageSeoBtn").disabled = false;
  }
}

function clearImageSeo() {
  currentImageFile = null;
  $("imageFile").value = "";
  $("imagePreview").src = "";
  $("imagePreview").classList.add("hidden");
  $("canvasPlaceholder").classList.remove("hidden");
  $("zoomRange").value = 1;
  $("imagePreview").style.transform = "scale(1)";
  $("imgSeoTitle").value = "";
  $("imgAltText").value = "";
  $("imgCaption").value = "";
  $("imgDescription").value = "";
  $("imgSlug").value = "";
  $("imageInfoText").textContent = "Visible: 0% - 100%";
  $("imageSizeText").textContent = "No image";
  setStatus("Image SEO fields cleared");
}

// ============================================================
// Utilities
// ============================================================

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text || "");
    setStatus("Copied to clipboard");
  } catch {
    setStatus("Copy failed");
  }
}
