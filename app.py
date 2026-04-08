import base64
import html
import io
import json
import os
import re
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, render_template, request
from PIL import Image

app = Flask(__name__)

TOGETHER_BASE_URL = "https://api.together.xyz/v1"
VISION_MODEL = os.getenv("VISION_MODEL", "Qwen/Qwen3-VL-8B-Instruct")
SEO_MODEL = os.getenv("SEO_MODEL", "Qwen/Qwen2.5-7B-Instruct-Turbo")
CONNECT_TIMEOUT = 8
READ_TIMEOUT = 45


# ------------------------------
# Helpers
# ------------------------------
def normalize_text(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def strip_html_keep_structure(raw_html: str) -> str:
    soup = BeautifulSoup(raw_html or "", "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    parts: List[str] = []
    for node in soup.find_all(["h1", "h2", "h3", "p", "li", "blockquote"]):
        text = node.get_text(" ", strip=True)
        if not text:
            continue
        name = node.name.lower()
        if name in {"h1", "h2", "h3"}:
            parts.append(f"{name.upper()}: {text}")
        elif name == "li":
            parts.append(f"- {text}")
        else:
            parts.append(text)
    return normalize_text("\n".join(parts))


def detect_embeds(raw: str) -> List[Dict[str, str]]:
    raw = raw or ""
    embeds: List[Dict[str, str]] = []

    yt_patterns = [
        r'https?://(?:www\.)?youtube\.com/watch\?[^\s"\']*v=([\w-]+)',
        r'https?://(?:www\.)?youtube\.com/embed/([\w-]+)',
        r'https?://youtu\.be/([\w-]+)',
        r'https?://(?:www\.)?youtube\.com/shorts/([\w-]+)',
    ]
    for pat in yt_patterns:
        for match in re.finditer(pat, raw, re.I):
            vid = match.group(1)
            url = f"https://www.youtube.com/watch?v={vid}"
            embeds.append({"type": "youtube", "url": url, "label": f"YouTube Video [ID: {vid}]"})

    for match in re.finditer(r'https?://(?:www\.)?(?:twitter|x)\.com/[A-Za-z0-9_]+/status(?:es)?/(\d+)', raw, re.I):
        full = match.group(0)
        embeds.append({"type": "twitter", "url": full.replace("x.com", "twitter.com"), "label": "Twitter/X Post"})

    for match in re.finditer(r'https?://(?:www\.)?facebook\.com/[^\s"\']+', raw, re.I):
        full = match.group(0)
        if "/videos/" in full or "watch?v=" in full or "video.php" in full:
            embeds.append({"type": "facebook", "url": full, "label": "Facebook Video"})

    unique = []
    seen = set()
    for item in embeds:
        key = (item["type"], item["url"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


MEDIA_RE = re.compile(r'(https?://[^\s"\']+\.(?:jpg|jpeg|png|webp|gif))', re.I)


def extract_article_source(article_url: str, article_html: str, article_text: str) -> Dict[str, object]:
    source_html = article_html or ""
    source_text = article_text or ""

    if article_url and not source_html and not source_text:
        r = requests.get(article_url, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT), headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        source_html = r.text

    if source_html and not source_text:
        source_text = strip_html_keep_structure(source_html)

    embeds = detect_embeds(source_html + "\n" + source_text + "\n" + (article_url or ""))
    title_match = re.search(r"^H1:\s*(.+)$", source_text, re.M)
    title = title_match.group(1).strip() if title_match else ""

    images = []
    if source_html:
        soup = BeautifulSoup(source_html, "html.parser")
        for img in soup.find_all("img"):
            src = (img.get("src") or "").strip()
            if src:
                images.append(src)
    for m in MEDIA_RE.finditer(source_text):
        images.append(m.group(1))
    dedup_images = []
    seen = set()
    for url in images:
        if url not in seen:
            dedup_images.append(url)
            seen.add(url)

    return {
        "title": title,
        "article_text": normalize_text(source_text),
        "article_html": source_html,
        "embeds": embeds,
        "images": dedup_images[:10],
    }


def build_wp_embed_block(embeds: List[Dict[str, str]]) -> str:
    if not embeds:
        return ""
    lines = []
    for item in embeds:
        lines.append(f'<!-- wp:embed {{"url":"{html.escape(item["url"], quote=True)}","type":"rich","providerNameSlug":"{item["type"]}"}} -->')
        lines.append(f'<figure class="wp-block-embed is-type-rich is-provider-{item["type"]}"><div class="wp-block-embed__wrapper">')
        lines.append(html.escape(item["url"]))
        lines.append('</div></figure>')
        lines.append('<!-- /wp:embed -->')
    return "\n".join(lines)


def estimate_keyphrase(text: str) -> str:
    words = re.findall(r"[A-Za-zÀ-ÿ0-9']+", text.lower())
    stop = {
        "the", "and", "for", "with", "from", "that", "this", "have", "has", "had", "was", "were", "are", "but",
        "about", "into", "than", "then", "they", "them", "their", "will", "would", "could", "should", "your", "you",
        "our", "after", "before", "while", "over", "under", "also", "more", "most", "what", "when", "where", "which",
    }
    freq: Dict[str, int] = {}
    for w in words:
        if len(w) < 4 or w in stop:
            continue
        freq[w] = freq.get(w, 0) + 1
    top = [w for w, _ in sorted(freq.items(), key=lambda x: (-x[1], x[0]))[:3]]
    return " ".join(top[:2]) if top else "focus topic"


def fallback_generate(article_text: str, title: str, embeds: List[Dict[str, str]]) -> Dict[str, str]:
    body = normalize_text(article_text)
    sentences = re.split(r"(?<=[.!?])\s+", body)
    excerpt = " ".join(sentences[:2]).strip()[:320]
    focus = estimate_keyphrase(title + " " + body)
    seo_title = (title or focus.title() or "Article Update").strip()
    if len(seo_title) > 60:
        seo_title = seo_title[:60].rsplit(" ", 1)[0]
    meta = excerpt[:160].rsplit(" ", 1)[0] if len(excerpt) > 160 else excerpt
    slug = re.sub(r"[^a-z0-9]+", "-", (title or focus).lower()).strip("-") or "article"
    cleaned_html = "\n".join(f"<p>{html.escape(p)}</p>" for p in body.split("\n\n") if p.strip())
    headings = [line[4:].strip() for line in body.splitlines() if line.startswith("H2:")]
    return {
        "focus_keyphrase": focus,
        "seo_title": seo_title,
        "meta_description": meta,
        "slug": slug,
        "excerpt": meta,
        "tags": ", ".join([w for w in focus.split()][:6]),
        "wp_html": build_wp_embed_block(embeds) + ("\n" if embeds and cleaned_html else "") + cleaned_html,
        "clean_article": body,
        "headings": headings,
    }


def together_chat(api_key: str, model: str, messages: List[Dict], max_tokens: int = 500, temperature: float = 0.2) -> str:
    r = requests.post(
        f"{TOGETHER_BASE_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        json={
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "top_p": 0.9,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        },
        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
    )
    r.raise_for_status()
    data = r.json()
    content = data["choices"][0]["message"]["content"]
    if isinstance(content, list):
        return "\n".join(x.get("text", "") if isinstance(x, dict) else str(x) for x in content)
    return str(content)


def parse_json_loose(raw: str) -> Dict:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def ai_generate_seo(api_key: str, article_text: str, title: str, embeds: List[Dict[str, str]]) -> Dict[str, str]:
    prompt = f"""Return ONLY valid JSON.

Keys:
{{
  "focus_keyphrase": "2-4 words",
  "seo_title": "50-60 chars",
  "meta_description": "120-160 chars",
  "slug": "short-url-slug",
  "excerpt": "short excerpt",
  "tags": "comma separated tags",
  "clean_article_html": "clean html body with h2 and p tags",
  "h2_headings": ["heading one", "heading two"]
}}

Rules:
- Keep meaning from the article.
- Keep important embeds/videos/social references in the article when relevant.
- SEO title must be concise.
- Meta description should be click-friendly but natural.
- clean_article_html must be valid HTML only.
- Use H2 sections when possible.
- No markdown.

Title: {title}

Article:
{article_text[:6000]}
"""
    raw = together_chat(api_key, SEO_MODEL, [{"role": "user", "content": prompt}], max_tokens=850, temperature=0.2)
    data = parse_json_loose(raw)
    cleaned_html = str(data.get("clean_article_html", "")).strip()
    wp_html = build_wp_embed_block(embeds) + ("\n" if embeds and cleaned_html else "") + cleaned_html
    return {
        "focus_keyphrase": str(data.get("focus_keyphrase", "")).strip(),
        "seo_title": str(data.get("seo_title", "")).strip(),
        "meta_description": str(data.get("meta_description", "")).strip(),
        "slug": str(data.get("slug", "")).strip(),
        "excerpt": str(data.get("excerpt", "")).strip(),
        "tags": str(data.get("tags", "")).strip(),
        "wp_html": wp_html.strip(),
        "clean_article": BeautifulSoup(cleaned_html, "html.parser").get_text("\n", strip=True),
        "headings": data.get("h2_headings", []),
    }


def optimize_image(file_storage) -> Tuple[str, str]:
    img = Image.open(file_storage.stream).convert("RGB")
    max_side = 1280
    w, h = img.size
    if max(w, h) > max_side:
        scale = max_side / float(max(w, h))
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    bio = io.BytesIO()
    img.save(bio, format="JPEG", quality=85, optimize=True)
    b64 = base64.b64encode(bio.getvalue()).decode("utf-8")
    return b64, "image/jpeg"


def ai_generate_image_seo(api_key: str, image_file, scene_hint: str = "") -> Dict[str, str]:
    b64, media = optimize_image(image_file)
    data_url = f"data:{media};base64,{b64}"
    prompt = f"""Return ONLY valid JSON with these keys:
{{
  "alt_text": "8-15 words",
  "img_title": "4-10 words, Title Case",
  "caption": "15-30 words, one sentence"
}}

Rules:
- Describe only what is visible.
- Natural journalistic style.
- No generic phrases like image/photo/picture.
- No markdown.
Context hint: {scene_hint}
"""
    raw = together_chat(
        api_key,
        VISION_MODEL,
        [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }],
        max_tokens=250,
        temperature=0.15,
    )
    data = parse_json_loose(raw)
    return {
        "alt_text": str(data.get("alt_text", "")).strip(),
        "img_title": str(data.get("img_title", "")).strip(),
        "caption": str(data.get("caption", "")).strip(),
    }


# ------------------------------
# Routes
# ------------------------------
@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/generate-seo")
def generate_seo():
    payload = request.get_json(force=True)
    api_key = (payload.get("api_key") or "").strip()
    article_url = (payload.get("article_url") or "").strip()
    article_html = payload.get("article_html") or ""
    article_text = payload.get("article_text") or ""

    try:
        source = extract_article_source(article_url, article_html, article_text)
        if not source["article_text"]:
            return jsonify({"ok": False, "error": "Please enter Article URL, HTML, or plain article text."}), 400

        if api_key:
            try:
                result = ai_generate_seo(api_key, source["article_text"], source["title"], source["embeds"])
            except Exception:
                result = fallback_generate(source["article_text"], source["title"], source["embeds"])
        else:
            result = fallback_generate(source["article_text"], source["title"], source["embeds"])

        result["embeds"] = source["embeds"]
        result["images"] = source["images"]
        return jsonify({"ok": True, "data": result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/api/ai-fields")
def ai_fields():
    payload = request.get_json(force=True)
    api_key = (payload.get("api_key") or "").strip()
    article_text = (payload.get("article_text") or "").strip()
    title = (payload.get("title") or "").strip()
    if not api_key:
        return jsonify({"ok": False, "error": "API key is required for AI SEO Fields."}), 400
    try:
        result = ai_generate_seo(api_key, article_text, title, [])
        variants = [
            result["seo_title"],
            (result["seo_title"] + " Live Updates")[:60].strip(),
            (result["seo_title"] + " Explained")[:60].strip(),
        ]
        meta_variants = [
            result["meta_description"],
            result["meta_description"][:150].rstrip(" .") + ".",
            (result["excerpt"] or result["meta_description"])[:155].rstrip(" .") + ".",
        ]
        return jsonify({
            "ok": True,
            "data": {
                "focus_keyphrase": result["focus_keyphrase"],
                "seo_titles": variants,
                "meta_descriptions": meta_variants,
            },
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/api/image-seo")
def image_seo():
    api_key = (request.form.get("api_key") or "").strip()
    scene_hint = (request.form.get("scene_hint") or "").strip()
    image_file = request.files.get("image")
    if not image_file:
        return jsonify({"ok": False, "error": "Please upload an image."}), 400

    try:
        if api_key:
            result = ai_generate_image_seo(api_key, image_file, scene_hint)
        else:
            result = {
                "alt_text": "Uploaded image with visible subject and scene details",
                "img_title": "Uploaded Image Scene",
                "caption": "Uploaded image showing the main subject and scene context provided by the user.",
            }
        return jsonify({"ok": True, "data": result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
