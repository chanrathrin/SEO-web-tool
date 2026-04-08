const $ = (id) => document.getElementById(id);

const state = {
  seoTitles: [],
  metaDescriptions: []
};

function setStatus(text, isError = false) {
  const bar = $('statusBar');
  bar.textContent = text;
  bar.style.color = isError ? '#ef4444' : '#3d5a7a';
}

function updateBadge() {
  const val = $('apiKey').value.trim();
  $('apiBadge').textContent = val ? '● API key active' : '○ API not configured';
  $('apiBadge').style.color = val ? '#22c55e' : '#4a6380';
}

function switchTab(name) {
  document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.toggle('active', btn.dataset.tab === name));
  document.querySelectorAll('.tab-panel').forEach(panel => panel.classList.toggle('active', panel.id === name));
}

function updateCounters() {
  $('seoTitleCount').textContent = `${$('seoTitle').value.length} / 60`;
  $('metaCount').textContent = `${$('metaDescription').value.trim().length} / 160`;
  $('previewTitle').textContent = $('seoTitle').value.trim() || 'SEO Title will appear here';
  $('previewMeta').textContent = $('metaDescription').value.trim() || 'Meta description preview will appear here.';
}

function renderVariants(containerId, items, onClick) {
  const box = $(containerId);
  box.innerHTML = '';
  items.forEach((item) => {
    const div = document.createElement('div');
    div.className = 'variant-item';
    div.textContent = item;
    div.addEventListener('click', () => onClick(item));
    box.appendChild(div);
  });
}

function renderEmbeds(items) {
  const box = $('embedList');
  box.innerHTML = '';
  if (!items || !items.length) {
    box.className = 'embed-list empty';
    box.textContent = 'No embeds detected';
    return;
  }
  box.className = 'embed-list';
  items.forEach((item) => {
    const row = document.createElement('div');
    row.className = 'embed-item';
    row.innerHTML = `<div class="embed-type">${item.type}</div><div>${item.label || item.type}</div><a href="${item.url}" target="_blank" rel="noopener">${item.url}</a>`;
    box.appendChild(row);
  });
}

function clearSeo() {
  ['articleUrl','articleHtml','articleText','focusKeyphrase','seoTitle','metaDescription','slug','excerpt','tags','cleanArticle','wpHtml'].forEach(id => $(id).value = '');
  renderEmbeds([]);
  $('seoVariants').innerHTML = '';
  $('metaVariants').innerHTML = '';
  updateCounters();
  setStatus('Cleared SEO fields');
}

async function generateSeo() {
  setStatus('Generating SEO...');
  try {
    const res = await fetch('/api/generate-seo', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        api_key: $('apiKey').value.trim(),
        article_url: $('articleUrl').value.trim(),
        article_html: $('articleHtml').value,
        article_text: $('articleText').value
      })
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || 'Request failed');
    const d = data.data;
    $('focusKeyphrase').value = d.focus_keyphrase || '';
    $('seoTitle').value = d.seo_title || '';
    $('metaDescription').value = d.meta_description || '';
    $('slug').value = d.slug || '';
    $('excerpt').value = d.excerpt || '';
    $('tags').value = d.tags || '';
    $('cleanArticle').value = d.clean_article || '';
    $('wpHtml').value = d.wp_html || '';
    state.seoTitles = [d.seo_title].filter(Boolean);
    state.metaDescriptions = [d.meta_description].filter(Boolean);
    renderVariants('seoVariants', state.seoTitles, (value) => { $('seoTitle').value = value; updateCounters(); });
    renderVariants('metaVariants', state.metaDescriptions, (value) => { $('metaDescription').value = value; updateCounters(); });
    renderEmbeds(d.embeds || []);
    updateCounters();
    setStatus('SEO generated successfully');
  } catch (err) {
    setStatus(err.message, true);
  }
}

async function generateAiFields() {
  setStatus('Generating AI SEO fields...');
  try {
    const res = await fetch('/api/ai-fields', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        api_key: $('apiKey').value.trim(),
        article_text: $('articleText').value || $('cleanArticle').value,
        title: $('seoTitle').value
      })
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || 'Request failed');
    $('focusKeyphrase').value = data.data.focus_keyphrase || '';
    state.seoTitles = data.data.seo_titles || [];
    state.metaDescriptions = data.data.meta_descriptions || [];
    if (state.seoTitles[0]) $('seoTitle').value = state.seoTitles[0];
    if (state.metaDescriptions[0]) $('metaDescription').value = state.metaDescriptions[0];
    renderVariants('seoVariants', state.seoTitles, (value) => { $('seoTitle').value = value; updateCounters(); });
    renderVariants('metaVariants', state.metaDescriptions, (value) => { $('metaDescription').value = value; updateCounters(); });
    updateCounters();
    setStatus('AI SEO fields ready');
  } catch (err) {
    setStatus(err.message, true);
  }
}

function clearImage() {
  $('imageFile').value = '';
  $('sceneHint').value = '';
  $('altText').value = '';
  $('imgTitle').value = '';
  $('imgCaption').value = '';
  $('imagePreview').src = '';
  $('imagePreview').classList.add('hidden');
  $('imageEmpty').classList.remove('hidden');
  setStatus('Cleared image SEO fields');
}

async function generateImageSeo() {
  const file = $('imageFile').files[0];
  if (!file) {
    setStatus('Please upload an image first', true);
    return;
  }
  setStatus('Generating image SEO...');
  try {
    const form = new FormData();
    form.append('api_key', $('apiKey').value.trim());
    form.append('scene_hint', $('sceneHint').value.trim());
    form.append('image', file);
    const res = await fetch('/api/image-seo', { method: 'POST', body: form });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || 'Request failed');
    $('altText').value = data.data.alt_text || '';
    $('imgTitle').value = data.data.img_title || '';
    $('imgCaption').value = data.data.caption || '';
    setStatus('Image SEO generated successfully');
  } catch (err) {
    setStatus(err.message, true);
  }
}

function previewImage() {
  const file = $('imageFile').files[0];
  if (!file) return clearImage();
  const url = URL.createObjectURL(file);
  $('imagePreview').src = url;
  $('imagePreview').classList.remove('hidden');
  $('imageEmpty').classList.add('hidden');
}

document.querySelectorAll('.tab-btn').forEach(btn => btn.addEventListener('click', () => switchTab(btn.dataset.tab)));
$('apiKey').addEventListener('input', updateBadge);
$('seoTitle').addEventListener('input', updateCounters);
$('metaDescription').addEventListener('input', updateCounters);
$('generateBtn').addEventListener('click', generateSeo);
$('aiFieldsBtn').addEventListener('click', generateAiFields);
$('clearSeoBtn').addEventListener('click', clearSeo);
$('generateImageSeoBtn').addEventListener('click', generateImageSeo);
$('clearImageBtn').addEventListener('click', clearImage);
$('imageFile').addEventListener('change', previewImage);

updateBadge();
updateCounters();
