const articleUrl = document.getElementById("articleUrl");
const articleText = document.getElementById("articleText");
const apiKey = document.getElementById("apiKey");
const apiInfo = document.getElementById("apiInfo");

const generateBtn = document.getElementById("generateBtn");
const clearBtn = document.getElementById("clearBtn");
const copyHtmlBtn = document.getElementById("copyHtmlBtn");

const outputText = document.getElementById("outputText");
const statusBar = document.getElementById("statusBar");

const focusKeyphrase = document.getElementById("focusKeyphrase");
const seoTitle = document.getElementById("seoTitle");
const metaDescription = document.getElementById("metaDescription");
const slug = document.getElementById("slug");
const shortSummary = document.getElementById("shortSummary");
const wordpressHtml = document.getElementById("wordpressHtml");

let latestData = null;
let isGenerating = false;

function setStatus(message) {
  statusBar.textContent = message || "Ready";
}

function updateApiInfo() {
  const hasKey = apiKey.value.trim().length > 0;
  apiInfo.textContent = hasKey ? "API: configured in this session" : "API: not configured";
}

function setGeneratingState(busy) {
  isGenerating = busy;
  generateBtn.disabled = busy;
  clearBtn.disabled = busy;
  generateBtn.textContent = busy ? "Generating..." : "Generate News Format";
}

function setHiddenFields(data) {
  focusKeyphrase.value = data.focus_keyphrase || "";
  seoTitle.value = data.seo_title || "";
  metaDescription.value = data.meta_description || "";
  slug.value = data.slug || "";
  shortSummary.value = data.short_summary || "";
  wordpressHtml.value = data.wordpress_html || "";
}

function clearHiddenFields() {
  focusKeyphrase.value = "";
  seoTitle.value = "";
  metaDescription.value = "";
  slug.value = "";
  shortSummary.value = "";
  wordpressHtml.value = "";
}

async function copyToClipboard(text, successStatus) {
  if (!text || !text.trim()) {
    setStatus("Nothing to copy");
    return;
  }

  try {
    await navigator.clipboard.writeText(text);
    setStatus(successStatus);
  } catch (error) {
    const temp = document.createElement("textarea");
    temp.value = text;
    document.body.appendChild(temp);
    temp.select();
    try {
      document.execCommand("copy");
      setStatus(successStatus);
    } catch {
      setStatus("Clipboard copy failed");
    }
    document.body.removeChild(temp);
  }
}

async function processArticle() {
  if (isGenerating) return;

  const payload = {
    article_url: articleUrl.value.trim(),
    article_text: articleText.value.trim(),
    api_key: apiKey.value.trim()
  };

  if (!payload.article_url && (!payload.article_text || payload.article_text.trim() === "Paste your article here...")) {
    outputText.value = "Please paste a news URL or article first.";
    setStatus("Please paste a news URL or article first");
    return;
  }

  setGeneratingState(true);
  setStatus("Generating SEO output...");

  try {
    const res = await fetch("/api/process", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });

    const json = await res.json();

    if (!json.ok) {
      latestData = null;
      clearHiddenFields();
      outputText.value = json.error || "Something went wrong.";
      if ((json.error || "").includes("403")) {
        setStatus("Import failed: site blocked auto import (403)");
      } else {
        setStatus(`Import failed: ${(json.error || "Unknown error").replace(/\n/g, " ").slice(0, 100)}`);
      }
      return;
    }

    latestData = json.data;
    if (json.data.imported_article_text) {
      articleText.value = json.data.imported_article_text;
    }

    outputText.value = json.data.output_preview || "";
    setHiddenFields(json.data);
    setStatus("Article SEO output generated");
  } catch (error) {
    latestData = null;
    clearHiddenFields();
    outputText.value = String(error);
    setStatus("Network error while processing article");
  } finally {
    setGeneratingState(false);
  }
}

function clearInput() {
  if (isGenerating) return;

  latestData = null;
  articleUrl.value = "";
  articleText.value = "Paste your article here...";
  outputText.value = "Formatted SEO output will appear here.";
  clearHiddenFields();
  setStatus("Input cleared");
}

function copySection(sectionName) {
  if (!latestData) {
    setStatus("Generate SEO output first");
    return;
  }

  const sectionMap = {
    "focus_keyphrase": focusKeyphrase.value,
    "seo_title": seoTitle.value,
    "meta_description": metaDescription.value
  };

  const value = sectionMap[sectionName] || "";
  if (!value.trim()) {
    const labelMap = {
      "focus_keyphrase": "Focus Keyphrase",
      "seo_title": "SEO Title",
      "meta_description": "Meta Description"
    };
    setStatus(`No content for ${labelMap[sectionName] || sectionName}`);
    return;
  }

  const labelMap = {
    "focus_keyphrase": "Focus Keyphrase",
    "seo_title": "SEO Title",
    "meta_description": "Meta Description"
  };

  copyToClipboard(value.trim(), `Smooth copied: ${labelMap[sectionName]}`);
}

generateBtn.addEventListener("click", processArticle);
clearBtn.addEventListener("click", clearInput);

copyHtmlBtn.addEventListener("click", () => {
  if (!latestData || !wordpressHtml.value.trim()) {
    setStatus("Generate SEO output first");
    return;
  }
  copyToClipboard(wordpressHtml.value, "Copied WordPress HTML");
});

document.querySelectorAll("[data-copy]").forEach(btn => {
  btn.addEventListener("click", () => {
    copySection(btn.getAttribute("data-copy"));
  });
});

apiKey.addEventListener("input", updateApiInfo);

articleText.addEventListener("focus", () => {
  if (articleText.value.trim() === "Paste your article here...") {
    articleText.value = "";
  }
});

articleText.addEventListener("blur", () => {
  if (!articleText.value.trim()) {
    articleText.value = "Paste your article here...";
  }
});

updateApiInfo();
setStatus("Ready");
