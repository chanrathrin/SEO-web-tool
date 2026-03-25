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
}

function buildCopyAllText(data) {
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

Meta Description:
${data["Meta Description"] || ""}

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
