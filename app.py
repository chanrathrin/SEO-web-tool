import os
import re
import io
import html
import json
import base64
from typing import List, Dict, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, jsonify
from PIL import Image

app = Flask(__name__)

TOGETHER_BASE_URL = "https://api.together.xyz/v1"
SEO_MODEL = "Qwen/Qwen2.5-7B-Instruct-Turbo"
VISION_MODEL = "Qwen/Qwen3-VL-8B-Instruct"

APP_TITLE = "WordPress SEO Studio"


# ============================================================
# Helpers
# ============================================================

def clean_text(s: str) -> str:
    s = html.unescape(str(s or ""))
    s = re.sub(r"\s+", " ", s).strip()
    return s


def strip_tags_keep_breaks(raw_html: str) -> str:
    soup = BeautifulSoup(raw_html or "", "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    text = soup.get_text("\n")
    lines = [clean_text(x) for x in text.splitlines()]
    lines = [x for x in lines if x]
    return "\n".join(lines)


def detect_language_simple(text: str) -> str:
    if re.search(r"[\u1780-\u17FF]", text or ""):
        return "Khmer"
    if re.search(r"[\u4E00-\u9FFF]", text or ""):
        return "Chinese"
    if re.search(r"[\u3040-\u30FF]", text or ""):
        return "Japanese"
    if re.search(r"[\u0E00-\u0E7F]", text or ""):
        return "Thai"
    if re.search(r"[\u0600-\u06FF]", text or ""):
        return "Arabic"
    return "English"


def slugify(text: str) -> str:
    text = clean_text(text).lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    return text or "article"


def first_nonempty(items: List[str], default: str = "") -> str:
    for x in items:
        if clean_text(x):
            return clean_text(x)
    return default


# ============================================================
# Embed detection
# ============================================================

class EmbedHelper:
    YOUTUBE_PATTERNS = [
        r"youtube\.com/embed/([\w-]+)",
        r"youtube\.com/watch\?[^\"\'\s]*v=([\w-]+)",
        r"youtu\.be/([\w-]+)",
        r"youtube\.com/v/([\w-]+)",
        r"youtube\.com/shorts/([\w-]+)",
    ]
    FACEBOOK_PATTERNS = [
        r"facebook\.com/[^\s\"\'<>]+/videos/([\d]+)",
        r"facebook\.com/watch/?\?v=(\d+)",
        r"facebook\.com/video/watch\?v=(\d+)",
        r"facebook\.com/video\.php\?v=(\d+)",
        r"fb\.watch/([\w-]+)",
    ]

    @classmethod
    def detect(cls, raw: str) -> Dict:
        raw = str(raw or "")
        raw_lower = raw.lower()

        for pat in cls.YOUTUBE_PATTERNS:
            m = re.search(pat, raw, re.I)
            if m:
                vid_id = m.group(1).split("&")[0].split("?")[0].strip()
                watch_url = f"https://www.youtube.com/watch?v={vid_id}"
                return {
                    "type": "youtube",
                    "icon": "▶",
                    "label": f"YouTube Video [ID: {vid_id}]",
                    "url": watch_url,
                    "embed_html": f'<div class="video-wrap"><iframe src="https://www.youtube.com/embed/{vid_id}" frameborder="0" allowfullscreen></iframe></div>',
                }

        tw = re.search(r'https?://(?:www\.)?(?:twitter|x)\.com/([A-Za-z0-9_]+)/status(?:es)?/(\d+)', raw, re.I)
        if tw:
            url = f"https://twitter.com/{tw.group(1)}/status/{tw.group(2)}"
            return {
                "type": "twitter",
                "icon": "🐦",
                "label": f"Twitter/X Post [ID: {tw.group(2)}]",
                "url": url,
                "embed_html": f'<blockquote class="embed-link"><a href="{html.escape(url)}" target="_blank">{html.escape(url)}</a></blockquote>',
            }

        for pat in cls.FACEBOOK_PATTERNS:
            m = re.search(pat, raw, re.I)
            if m:
                full = re.search(r'https?://(?:www\.)?facebook\.com/[^\s\"\'<>]+', raw, re.I)
                fb_url = full.group(0) if full else raw
                return {
                    "type": "facebook",
                    "icon": "📘",
                    "label": "Facebook Video",
                    "url": fb_url,
                    "embed_html": f'<blockquote class="embed-link"><a href="{html.escape(fb_url)}" target="_blank">{html.escape(fb_url)}</a></blockquote>',
                }

        iframe_src = re.search(r'src=["\'](https?://[^"\'>\s]+)["\']', raw, re.I)
        if iframe_src:
            src = iframe_src.group(1)
            return {
                "type": "generic",
                "icon": "▶",
                "label": "Embedded Media",
                "url": src,
                "embed_html": f'<blockquote class="embed-link"><a href="{html.escape(src)}" target="_blank">{html.escape(src)}</a></blockquote>',
            }

        return {"type": None}


# ============================================================
# Article parsing
# ============================================================

def fetch_url_html(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "en-US,en;q=0.9"
    }
    r = requests.get(url, timeout=20, headers=headers)
    r.raise_for_status()
    return r.text


def extract_title_from_html(raw_html: str) -> str:
    soup = BeautifulSoup(raw_html or "", "html.parser")
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        return clean_text(og["content"])
    if soup.title and soup.title.text:
        return clean_text(soup.title.text)
    h1 = soup.find("h1")
    if h1:
        return clean_text(h1.get_text(" "))
    return ""


def parse_blocks_from_html(raw_html: str) -> List[Dict]:
    soup = BeautifulSoup(raw_html or "", "html.parser")
    blocks: List[Dict] = []

    for tag in soup.find_all(["h1", "h2", "h3", "p", "iframe", "blockquote", "figure"]):
        name = tag.name.lower()

        if name == "h1":
            txt = clean_text(tag.get_text(" "))
            if txt:
                blocks.append({"type": "h1", "content": txt})
            continue

        if name == "h2":
            txt = clean_text(tag.get_text(" "))
            if txt:
                blocks.append({"type": "h2", "content": txt})
            continue

        if name == "h3":
            txt = clean_text(tag.get_text(" "))
            if txt:
                blocks.append({"type": "h3", "content": txt})
            continue

        if name == "p":
            raw_inner = str(tag)
            emb = EmbedHelper.detect(raw_inner)
            if emb.get("type"):
                blocks.append({"type": "embed", "content": emb["embed_html"], "label": emb["label"]})
            txt = clean_text(tag.get_text(" "))
            if txt and len(txt.split()) >= 3:
                blocks.append({"type": "p", "content": html.escape(txt)})
            continue

        if name in ("iframe", "blockquote", "figure"):
            raw_inner = str(tag)
            emb = EmbedHelper.detect(raw_inner)
            if emb.get("type"):
                blocks.append({"type": "embed", "content": emb["embed_html"], "label": emb["label"]})

    deduped = []
    seen = set()
    for b in blocks:
        key = (b["type"], clean_text(b["content"])[:300])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(b)
    return deduped


def parse_plain_text(raw_text: str) -> List[Dict]:
    text = raw_text or ""
    lines = [x.strip() for x in text.splitlines()]
    lines = [x for x in lines if x]

    blocks: List[Dict] = []
    h1_used = False
    for ln in lines:
        emb = EmbedHelper.detect(ln)
        if emb.get("type"):
            blocks.append({"type": "embed", "content": emb["embed_html"], "label": emb["label"]})
            continue

        if not h1_used:
            blocks.append({"type": "h1", "content": ln})
            h1_used = True
            continue

        if len(ln.split()) <= 9 and not ln.endswith("."):
            blocks.append({"type": "h2", "content": ln})
        else:
            blocks.append({"type": "p", "content": html.escape(ln)})

    return blocks


def extract_focus_keyphrase(title: str, text: str) -> str:
    source = clean_text(title or text)
    words = re.findall(r"[A-Za-z0-9\u1780-\u17FF]+", source)
    if not words:
        return "wordpress seo"
    key = " ".join(words[:4]).strip().lower()
    return key[:60]


def make_meta_description(title: str, paragraphs: List[str]) -> str:
    title = clean_text(title)
    base = clean_text(" ".join(paragraphs[:2]))
    if not base:
        base = title
    desc = base
    if title and title.lower() not in desc.lower():
        desc = f"{title}. {desc}"
    desc = clean_text(desc)
    if len(desc) > 160:
        desc = desc[:157].rsplit(" ", 1)[0] + "..."
    return desc


def derive_seo_fields(blocks: List[Dict], page_title: str = "") -> Dict:
    h1 = first_nonempty([b["content"] for b in blocks if b["type"] == "h1"], page_title or "Untitled Article")
    paragraphs = [BeautifulSoup(b["content"], "html.parser").get_text(" ") for b in blocks if b["type"] == "p"]
    focus_keyphrase = extract_focus_keyphrase(h1, " ".join(paragraphs[:3]))
    seo_title = h1[:60]
    meta_description = make_meta_description(h1, paragraphs)
    slug = slugify(h1)
    return {
        "focus_keyphrase": focus_keyphrase,
        "seo_title": seo_title,
        "meta_description": meta_description,
        "slug": slug,
        "title": h1,
    }


def blocks_to_seo_html(blocks: List[Dict]) -> str:
    out = []
    h2_count = 0

    for b in blocks:
        if b["type"] == "h1":
            out.append(f"<h1>{html.escape(clean_text(b['content']))}</h1>")
        elif b["type"] == "h2":
            h2_count += 1
            out.append(f"<h2>{html.escape(clean_text(b['content']))}</h2>")
        elif b["type"] == "h3":
            out.append(f"<h3>{html.escape(clean_text(b['content']))}</h3>")
        elif b["type"] == "p":
            txt = b["content"]
            out.append(f"<p>{txt}</p>")
        elif b["type"] == "embed":
            out.append(b["content"])

    return "\n\n".join(out)


def blocks_to_plain_preview(blocks: List[Dict]) -> str:
    parts = []
    for b in blocks:
        if b["type"] == "embed":
            parts.append(f"[EMBED] {b.get('label', 'Embedded Media')}")
        else:
            parts.append(clean_text(BeautifulSoup(b["content"], "html.parser").get_text(" ")))
    return "\n\n".join([x for x in parts if x])


def make_wp_html(seo: Dict, body_html: str) -> str:
    return f"""<!-- wp:heading {{"level":1}} -->
<h1>{html.escape(seo["title"])}</h1>
<!-- /wp:heading -->

{body_html}

<!-- wp:yoast-seo/meta-description -->
<p>{html.escape(seo["meta_description"])}</p>
<!-- /wp:yoast-seo/meta-description -->"""


# ============================================================
# Together AI
# ============================================================

def together_headers(api_key: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def verify_api_key(api_key: str) -> Dict:
    r = requests.get(
        f"{TOGETHER_BASE_URL}/models",
        headers=together_headers(api_key),
        timeout=(6, 12),
    )
    if r.status_code >= 400:
        raise RuntimeError(r.text[:300])
    return r.json()


def chat_completion(api_key: str, model: str, messages: List[Dict], max_tokens: int = 300) -> Dict:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "top_p": 0.9,
        "max_tokens": max_tokens,
    }
    r = requests.post(
        f"{TOGETHER_BASE_URL}/chat/completions",
        headers=together_headers(api_key),
        json=payload,
        timeout=(8, 40),
    )
    if r.status_code >= 400:
        raise RuntimeError(r.text[:400])
    return r.json()


def extract_content(resp: Dict) -> str:
    choices = resp.get("choices") or []
    if not choices:
        return ""
    msg = choices[0].get("message") or {}
    content = msg.get("content", "")
    if isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict):
                texts.append(item.get("text", ""))
            else:
                texts.append(str(item))
        return "\n".join(texts).strip()
    return str(content or "").strip()


def ai_generate_seo_fields(api_key: str, article_text: str, lang: str) -> Dict:
    prompt = f"""Return ONLY valid JSON in {lang}.

Keys:
{{
  "focus_keyphrase": "2-4 words",
  "seo_title": "max 60 chars",
  "meta_description": "max 160 chars"
}}

Rules:
- concise
- Yoast-friendly
- no markdown
- no explanation

ARTICLE:
{article_text[:1800]}
"""
    resp = chat_completion(
        api_key,
        SEO_MODEL,
        [{"role": "user", "content": prompt}],
        max_tokens=220
    )
    raw = extract_content(resp)
    raw = raw.replace("```json", "").replace("```", "").strip()
    data = json.loads(raw)
    return {
        "focus_keyphrase": clean_text(data.get("focus_keyphrase", ""))[:80],
        "seo_title": clean_text(data.get("seo_title", ""))[:60],
        "meta_description": clean_text(data.get("meta_description", ""))[:160],
    }


def ai_generate_image_seo(api_key: str, image_b64: str, mime: str, lang: str = "English") -> Dict:
    content = [
        {
            "type": "text",
            "text": f"""Look at this image and return ONLY valid JSON in {lang}.

Keys:
{{
  "seo_title": "max 60 chars",
  "alt_text": "clear alt text",
  "caption": "short caption",
  "description": "short seo description",
  "slug": "image-file-slug"
}}
"""
        },
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:{mime};base64,{image_b64}"
            }
        }
    ]

    payload = {
        "model": VISION_MODEL,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.2,
        "top_p": 0.9,
        "max_tokens": 220,
    }

    r = requests.post(
        f"{TOGETHER_BASE_URL}/chat/completions",
        headers=together_headers(api_key),
        json=payload,
        timeout=(8, 45),
    )
    if r.status_code >= 400:
        raise RuntimeError(r.text[:400])

    raw = extract_content(r.json())
    raw = raw.replace("```json", "").replace("```", "").strip()
    data = json.loads(raw)
    return {
        "seo_title": clean_text(data.get("seo_title", ""))[:60],
        "alt_text": clean_text(data.get("alt_text", ""))[:160],
        "caption": clean_text(data.get("caption", ""))[:180],
        "description": clean_text(data.get("description", ""))[:220],
        "slug": slugify(data.get("slug", "") or data.get("seo_title", "") or "image"),
    }


# ============================================================
# Image helpers
# ============================================================

def optimize_image_upload(file_storage) -> Dict:
    img = Image.open(file_storage.stream).convert("RGB")
    w, h = img.size
    longest = max(w, h)
    if longest > 1280:
        ratio = 1280 / float(longest)
        img = img.resize((int(w * ratio), int(h * ratio)))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=88, optimize=True)
    out.seek(0)
    b64 = base64.b64encode(out.read()).decode("utf-8")
    return {
        "base64": b64,
        "mime": "image/jpeg",
        "width": img.size[0],
        "height": img.size[1],
    }


def image_local_fallback(filename: str) -> Dict:
    base = os.path.splitext(filename or "image")[0]
    nice = clean_text(base.replace("-", " ").replace("_", " ")) or "Image"
    return {
        "seo_title": nice[:60],
        "alt_text": nice,
        "caption": f"{nice} preview",
        "description": f"{nice} optimized for WordPress SEO.",
        "slug": slugify(nice),
    }


# ============================================================
# Routes
# ============================================================

@app.route("/")
def index():
    return render_template("index.html", app_title=APP_TITLE)


@app.post("/api/verify-key")
def api_verify_key():
    data = request.get_json(force=True)
    api_key = (data.get("api_key") or "").strip()
    if not api_key:
        return jsonify({"ok": False, "error": "Missing API key"}), 400
    try:
        verify_api_key(api_key)
        return jsonify({"ok": True, "message": "API key is valid"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.post("/api/generate-seo")
def api_generate_seo():
    data = request.get_json(force=True)
    raw_input = data.get("raw_input", "") or ""
    article_url = data.get("article_url", "") or ""
    api_key = (data.get("api_key") or "").strip()

    try:
        if article_url.strip():
            raw_input = fetch_url_html(article_url.strip())

        if not raw_input.strip():
            return jsonify({"ok": False, "error": "Input is empty"}), 400

        is_html = bool(re.search(r"<[a-z][\s\S]*>", raw_input, re.I))
        title_guess = extract_title_from_html(raw_input) if is_html else ""
        blocks = parse_blocks_from_html(raw_input) if is_html else parse_plain_text(raw_input)
        seo = derive_seo_fields(blocks, title_guess)

        article_text = blocks_to_plain_preview(blocks)
        lang = detect_language_simple(article_text)

        if api_key:
            try:
                ai = ai_generate_seo_fields(api_key, article_text, lang)
                if ai.get("focus_keyphrase"):
                    seo["focus_keyphrase"] = ai["focus_keyphrase"]
                if ai.get("seo_title"):
                    seo["seo_title"] = ai["seo_title"]
                if ai.get("meta_description"):
                    seo["meta_description"] = ai["meta_description"]
            except Exception:
                pass

        seo_html = blocks_to_seo_html(blocks)
        wp_html = make_wp_html(seo, seo_html)

        return jsonify({
            "ok": True,
            "language": lang,
            "title": seo["title"],
            "focus_keyphrase": seo["focus_keyphrase"],
            "seo_title": seo["seo_title"],
            "meta_description": seo["meta_description"],
            "slug": seo["slug"],
            "seo_output": seo_html,
            "wp_html_output": wp_html,
            "plain_preview": article_text,
            "status": f"Generated SEO successfully | 🌐 {lang}"
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/api/image-seo")
def api_image_seo():
    api_key = (request.form.get("api_key") or "").strip()
    image = request.files.get("image")

    if not image:
        return jsonify({"ok": False, "error": "No image uploaded"}), 400

    try:
        img_data = optimize_image_upload(image)
        result = None

        if api_key:
            try:
                result = ai_generate_image_seo(api_key, img_data["base64"], img_data["mime"], "English")
            except Exception:
                result = None

        if not result:
            result = image_local_fallback(image.filename)

        return jsonify({
            "ok": True,
            "preview_data_url": f"data:{img_data['mime']};base64,{img_data['base64']}",
            "width": img_data["width"],
            "height": img_data["height"],
            "seo_title": result["seo_title"],
            "alt_text": result["alt_text"],
            "caption": result["caption"],
            "description": result["description"],
            "slug": result["slug"],
            "status": f"Image SEO ready | {img_data['width']}×{img_data['height']}"
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
