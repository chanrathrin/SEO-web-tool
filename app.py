import os
import re
import io
import json
import html
import base64
from typing import Dict, List, Tuple

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, render_template, request
from PIL import Image

app = Flask(__name__)

TOGETHER_BASE_URL = "https://api.together.xyz/v1"
SEO_MODEL = os.getenv("TOGETHER_SEO_MODEL", "Qwen/Qwen2.5-7B-Instruct-Turbo")
VISION_MODEL = os.getenv("TOGETHER_VISION_MODEL", "Qwen/Qwen2.5-VL-72B-Instruct")

MAX_SEO_INPUT_CHARS = 5000
MAX_IMAGE_SIDE = 1280
JPEG_QUALITY = 84


# ============================================================
# Helpers
# ============================================================

def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def clamp_text(text: str, limit: int) -> str:
    text = normalize_ws(text)
    if len(text) <= limit:
        return text
    clipped = text[:limit]
    if " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0]
    return clipped.rstrip(" -,:;|")


def extract_content(resp: dict) -> str:
    choices = resp.get("choices") or []
    if not choices:
        return ""
    msg = choices[0].get("message") or {}
    content = msg.get("content", "")
    if isinstance(content, list):
        out = []
        for item in content:
            if isinstance(item, dict):
                t = item.get("text") or item.get("content") or ""
                if t:
                    out.append(str(t))
            elif item:
                out.append(str(item))
        return "\n".join(out).strip()
    return str(content or "").strip()


def parse_json(raw: str) -> dict:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("Empty AI response")
    candidates = [raw]
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    if cleaned != raw:
        candidates.append(cleaned)
    m = re.search(r"\{.*\}", cleaned, re.S)
    if m:
        candidates.append(m.group(0))

    last_err = None
    for candidate in candidates:
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except Exception as e:
            last_err = e
    raise ValueError("Cannot parse JSON from AI response") from last_err


def headers(api_key: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def chat_completion(api_key: str, model: str, messages: list, max_tokens: int = 300, temperature: float = 0.2):
    r = requests.post(
        f"{TOGETHER_BASE_URL}/chat/completions",
        headers=headers(api_key),
        json={
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "top_p": 0.9,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        },
        timeout=(10, 45),
    )
    r.raise_for_status()
    return r.json()


def verify_api_key(api_key: str) -> Tuple[bool, str]:
    api_key = (api_key or "").strip()
    if not api_key:
        return False, "API key is empty."

    try:
        r = requests.get(
            f"{TOGETHER_BASE_URL}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=(8, 20),
        )
        if r.status_code >= 400:
            try:
                data = r.json()
                detail = data.get("error", {}).get("message") or data.get("message") or r.text
            except Exception:
                detail = r.text
            return False, f"HTTP {r.status_code}: {detail}"
        return True, "API key is valid."
    except Exception as e:
        return False, str(e)


# ============================================================
# Embed logic
# ============================================================

class EmbedHelper:
    YOUTUBE_PATTERNS = [
        r"youtube\.com/embed/([\w-]+)",
        r"youtube\.com/watch\?[^\"'\s]*v=([\w-]+)",
        r"youtu\.be/([\w-]+)",
        r"youtube\.com/shorts/([\w-]+)",
    ]

    FACEBOOK_PATTERNS = [
        r"facebook\.com/[^\s\"'<>]+/videos/(\d+)",
        r"facebook\.com/watch/?\?v=(\d+)",
        r"fb\.watch/([\w-]+)",
        r"facebook\.com/video\.php\?v=(\d+)",
    ]

    @classmethod
    def detect(cls, raw: str) -> Dict[str, str]:
        raw = html.unescape(str(raw or "")).strip()

        for pat in cls.YOUTUBE_PATTERNS:
            m = re.search(pat, raw, re.I)
            if m:
                vid = m.group(1).split("&")[0].split("?")[0].strip()
                url = f"https://www.youtube.com/watch?v={vid}"
                return {
                    "type": "youtube",
                    "label": f"YouTube Video [{vid}]",
                    "url": url,
                    "html": (
                        f'<!-- wp:embed {{"url":"{html.escape(url, quote=True)}","type":"video","providerNameSlug":"youtube","responsive":true}} -->\n'
                        f'<figure class="wp-block-embed is-type-video is-provider-youtube wp-block-embed-youtube">'
                        f'<div class="wp-block-embed__wrapper">{html.escape(url)}</div></figure>\n'
                        f'<!-- /wp:embed -->'
                    ),
                }

        m = re.search(
            r"https?://(?:www\.)?(?:twitter|x)\.com/([A-Za-z0-9_]+)/status(?:es)?/(\d+)",
            raw,
            re.I,
        )
        if m:
            url = f"https://twitter.com/{m.group(1)}/status/{m.group(2)}"
            return {
                "type": "twitter",
                "label": f"Twitter/X Post [{m.group(2)}]",
                "url": url,
                "html": (
                    f'<!-- wp:embed {{"url":"{html.escape(url, quote=True)}","type":"rich","providerNameSlug":"twitter","responsive":true}} -->\n'
                    f'<figure class="wp-block-embed is-type-rich is-provider-twitter wp-block-embed-twitter">'
                    f'<div class="wp-block-embed__wrapper">{html.escape(url)}</div></figure>\n'
                    f'<!-- /wp:embed -->'
                ),
            }

        m = re.search(r"https?://(?:www\.)?twitter\.com/i/web/status/(\d+)", raw, re.I)
        if m:
            url = f"https://twitter.com/i/web/status/{m.group(1)}"
            return {
                "type": "twitter",
                "label": f"Twitter/X Post [{m.group(1)}]",
                "url": url,
                "html": (
                    f'<!-- wp:embed {{"url":"{html.escape(url, quote=True)}","type":"rich","providerNameSlug":"twitter","responsive":true}} -->\n'
                    f'<figure class="wp-block-embed is-type-rich is-provider-twitter wp-block-embed-twitter">'
                    f'<div class="wp-block-embed__wrapper">{html.escape(url)}</div></figure>\n'
                    f'<!-- /wp:embed -->'
                ),
            }

        for pat in cls.FACEBOOK_PATTERNS:
            m = re.search(pat, raw, re.I)
            if m:
                full = re.search(r"https?://(?:www\.)?facebook\.com/[^\s\"'<>]+", raw, re.I)
                url = full.group(0).rstrip('/"\'' ) if full else raw
                return {
                    "type": "facebook",
                    "label": "Facebook Video",
                    "url": url,
                    "html": (
                        f'<!-- wp:embed {{"url":"{html.escape(url, quote=True)}","type":"rich","providerNameSlug":"facebook","responsive":true}} -->\n'
                        f'<figure class="wp-block-embed is-type-rich is-provider-facebook wp-block-embed-facebook">'
                        f'<div class="wp-block-embed__wrapper">{html.escape(url)}</div></figure>\n'
                        f'<!-- /wp:embed -->'
                    ),
                }

        iframe_src = re.search(r'src=["\'](https?://[^"\'>\s]+)["\']', raw, re.I)
        if iframe_src:
            src = iframe_src.group(1)
            nested = cls.detect(src)
            if nested.get("type"):
                return nested
            return {
                "type": "generic",
                "label": "Embedded Media",
                "url": src,
                "html": src,
            }

        bare = re.search(r"https?://[^\s<\"']+", raw, re.I)
        if bare:
            url = bare.group(0)
            nested = cls.detect(url)
            if nested.get("type"):
                return nested
            return {
                "type": "generic",
                "label": "Embedded URL",
                "url": url,
                "html": url,
            }

        return {"type": "", "label": "", "url": "", "html": ""}


def looks_like_html(text: str) -> bool:
    sample = str(text or "").lower()
    tokens = (
        "<html", "<body", "<div", "<article", "<section", "<p", "<h1", "<h2",
        "<h3", "<iframe", "<figure", "<blockquote", "<video", "<!-- wp:"
    )
    return any(token in sample for token in tokens)


def strip_wp_blocks_preserve_embeds(raw: str) -> str:
    raw = str(raw or "")

    def replace_wp_embed(match):
        block_json = match.group(1) or ""
        inner_html = (match.group(2) or "").strip()

        url_m = re.search(r'"url"\s*:\s*"([^"]+)"', block_json)
        embed_url = url_m.group(1) if url_m else ""

        if not embed_url:
            wrapper_m = re.search(
                r'<div[^>]*class=["\'][^"\']*wp-block-embed__wrapper[^"\']*["\'][^>]*>\s*(https?://[^\s<]+)',
                inner_html,
                re.I | re.S,
            )
            if wrapper_m:
                embed_url = wrapper_m.group(1).strip()

        if not embed_url:
            any_url = re.search(r'(https?://[^\s<"\']{8,})', inner_html)
            if any_url:
                embed_url = any_url.group(1).strip()

        if embed_url:
            info = EmbedHelper.detect(embed_url)
            if info["type"]:
                return f"\n__PRESV_EMBED_START__{info['html']}__PRESV_EMBED_END__\n"

        return f"\n{inner_html}\n"

    raw = re.sub(
        r'<!--\s*wp:embed\s*(\{[^}]*\}|\S*)\s*-->(.*?)<!--\s*/wp:embed\s*-->',
        replace_wp_embed,
        raw,
        flags=re.I | re.S,
    )

    def replace_wp_video(match):
        inner_html = (match.group(1) or "").strip()
        src_m = re.search(r'src=["\']([^"\']+)["\']', inner_html, re.I)
        embed_url = src_m.group(1) if src_m else ""
        if embed_url:
            info = EmbedHelper.detect(embed_url)
            if info["type"]:
                return f"\n__PRESV_EMBED_START__{info['html']}__PRESV_EMBED_END__\n"
        return f"\n{inner_html}\n"

    raw = re.sub(
        r'<!--\s*wp:video[^-]*-->(.*?)<!--\s*/wp:video\s*-->',
        replace_wp_video,
        raw,
        flags=re.I | re.S,
    )

    video_url_pat = (
        r'https?://(?:www\.)?(?:youtube\.com/watch\?[^\s<"\']+|'
        r'youtu\.be/[\w\-]+[^\s<"\']*|'
        r'youtube\.com/shorts/[\w\-]+[^\s<"\']*|'
        r'(?:twitter|x)\.com/\S+/status/\d+[^\s<"\']*|'
        r'facebook\.com/[^\s<"\']+/videos/[^\s<"\']+|'
        r'fb\.watch/[\w\-]+[^\s<"\']*)'
    )

    def convert_bare_url(match):
        url = match.group(0).strip()
        info = EmbedHelper.detect(url)
        if info["type"]:
            return f"\n__PRESV_EMBED_START__{info['html']}__PRESV_EMBED_END__\n"
        return url

    raw = re.sub(video_url_pat, convert_bare_url, raw, flags=re.I)
    raw = re.sub(r"<!--\s*/?\s*wp:[^>]*-->", "", raw, flags=re.I | re.S)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return raw.strip()


def wrap_plain_text_with_paragraphs(text: str) -> str:
    blocks = re.split(r"\n\s*\n", str(text or "").strip())
    out = []

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        if "__PRESV_EMBED_START__" in block:
            out.append(block)
            continue

        safe = html.escape(block).replace("\n", "<br>")
        out.append(f"<p>{safe}</p>")

    return "\n\n".join(out).strip()


def sanitize_html(raw: str) -> str:
    raw = str(raw or "")
    raw = re.sub(r"<script\b.*?</script>", "", raw, flags=re.I | re.S)
    raw = re.sub(r"<style\b.*?</style>", "", raw, flags=re.I | re.S)
    raw = re.sub(r"<noscript\b.*?</noscript>", "", raw, flags=re.I | re.S)
    raw = raw.replace("&nbsp;", " ").replace("\u00a0", " ")
    return raw.strip()


def html_to_text_preserving_embeds(raw_html: str) -> str:
    temp = re.sub(r"__PRESV_EMBED_START__(.*?)__PRESV_EMBED_END__", " ", raw_html, flags=re.S)
    soup = BeautifulSoup(temp, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines).strip()


def extract_embed_markers(text: str) -> List[str]:
    return re.findall(r"__PRESV_EMBED_START__(.*?)__PRESV_EMBED_END__", str(text or ""), flags=re.S)


def extract_title_from_html(raw_html: str) -> str:
    raw_html = str(raw_html or "")

    for pat in [
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\'>]*)["\']',
        r'<meta[^>]+content=["\']([^"\'>]*)["\'][^>]+property=["\']og:title["\']',
        r"<title[^>]*>(.*?)</title>",
        r"<h1[^>]*>(.*?)</h1>",
    ]:
        m = re.search(pat, raw_html, re.I | re.S)
        if m:
            cleaned = re.sub(r"<[^>]+>", " ", m.group(1))
            cleaned = html.unescape(cleaned)
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            cleaned = re.sub(r"\s+[|\-–—]\s+.*$", "", cleaned).strip()
            if cleaned:
                return cleaned

    return ""


def guess_title_from_text(text: str) -> str:
    lines = [normalize_ws(line) for line in str(text or "").splitlines() if normalize_ws(line)]
    if not lines:
        return "Untitled Article"
    first = lines[0]
    return clamp_text(first, 90)


def build_intro(text: str) -> str:
    text = normalize_ws(text)
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text)
    intro = " ".join(parts[:2]).strip()
    return clamp_text(intro, 220)


def derive_focus_keyphrase(text: str) -> str:
    words = re.findall(r"\b[a-zA-Z0-9\u1780-\u17ff][a-zA-Z0-9\u1780-\u17ff'-]{2,}\b", text.lower())
    stop_words = {
        "this", "that", "with", "from", "your", "have", "will", "about", "into",
        "after", "before", "their", "there", "they", "them", "what", "when",
        "where", "which", "while", "would", "could", "should", "article", "video", "embed"
    }
    freq = {}
    for w in words:
        if w in stop_words:
            continue
        freq[w] = freq.get(w, 0) + 1

    ranked = sorted(freq.items(), key=lambda x: (-x[1], x[0]))
    phrase = " ".join([item[0] for item in ranked[:3]]).strip()
    return phrase[:60] or "wordpress article"


def fallback_seo(text: str, title_hint: str = "") -> Dict[str, str]:
    title_source = title_hint.strip() or guess_title_from_text(text)
    seo_title = clamp_text(title_source, 60)
    if len(seo_title) < 18:
        seo_title = clamp_text(f"{title_source} | SEO Article", 60)

    meta = build_intro(text)
    if not meta:
        meta = "Read the full article with key details, summaries, and embedded media."
    meta = clamp_text(meta, 160)

    return {
        "focus_keyphrase": derive_focus_keyphrase(text),
        "seo_title": seo_title,
        "meta_description": meta,
    }


def generate_ai_seo(api_key: str, plain_text: str, title_hint: str = "") -> Dict[str, str]:
    api_key = (api_key or "").strip()
    if not api_key:
        return fallback_seo(plain_text, title_hint=title_hint)

    prompt = f"""Return ONLY valid JSON:
{{
  "focus_keyphrase": "2-4 word keyphrase",
  "seo_title": "max 60 chars",
  "meta_description": "max 160 chars"
}}

Rules:
- concise
- search-friendly
- no markdown
- no explanation

TITLE HINT:
{title_hint[:180]}

ARTICLE:
{plain_text[:MAX_SEO_INPUT_CHARS]}
"""

    try:
        resp = chat_completion(
            api_key=api_key,
            model=SEO_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=220,
            temperature=0.2,
        )
        parsed = parse_json(extract_content(resp))
        focus = clamp_text(str(parsed.get("focus_keyphrase", "")).strip(), 60)
        seo_title = clamp_text(str(parsed.get("seo_title", "")).strip(), 60)
        meta = clamp_text(str(parsed.get("meta_description", "")).strip(), 160)

        if not focus or not seo_title or not meta:
            return fallback_seo(plain_text, title_hint=title_hint)

        return {
            "focus_keyphrase": focus,
            "seo_title": seo_title,
            "meta_description": meta,
        }
    except Exception:
        return fallback_seo(plain_text, title_hint=title_hint)


def image_to_data_url(file_storage) -> str:
    img = Image.open(file_storage.stream).convert("RGB")
    w, h = img.size
    longest = max(w, h)
    if longest > MAX_IMAGE_SIDE:
        scale = MAX_IMAGE_SIDE / float(longest)
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)

    bio = io.BytesIO()
    img.save(bio, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    b64 = base64.b64encode(bio.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"


def fallback_image_seo(scene_notes: str = "", filename: str = "") -> Dict[str, str]:
    base = normalize_ws(scene_notes) or "descriptive image"
    title = clamp_text(filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " "), 60) if filename else ""
    if not title:
        title = clamp_text(base.title(), 60)

    alt_text = clamp_text(base, 125)
    caption = clamp_text(f"{base[:90]}.", 160)

    return {
        "alt_text": alt_text or "descriptive image",
        "img_title": title or "Image",
        "caption": caption or "Image caption",
    }


def generate_ai_image_seo(api_key: str, image_data_url: str, scene_notes: str = "", filename: str = "") -> Dict[str, str]:
    api_key = (api_key or "").strip()
    if not api_key:
        return fallback_image_seo(scene_notes=scene_notes, filename=filename)

    prompt = f"""Return ONLY valid JSON:
{{
  "alt_text": "accurate alt text, max 125 chars",
  "img_title": "image title, max 60 chars",
  "caption": "caption, max 160 chars"
}}

Rules:
- describe the image accurately
- include the user's scene hint if useful
- no markdown
- no explanation

Scene hint:
{scene_notes[:300]}
"""

    try:
        r = requests.post(
            f"{TOGETHER_BASE_URL}/chat/completions",
            headers=headers(api_key),
            json={
                "model": VISION_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": image_data_url}},
                        ],
                    }
                ],
                "temperature": 0.2,
                "top_p": 0.9,
                "max_tokens": 220,
                "response_format": {"type": "json_object"},
            },
            timeout=(10, 60),
        )
        r.raise_for_status()
        parsed = parse_json(extract_content(r.json()))

        alt_text = clamp_text(str(parsed.get("alt_text", "")).strip(), 125)
        img_title = clamp_text(str(parsed.get("img_title", "")).strip(), 60)
        caption = clamp_text(str(parsed.get("caption", "")).strip(), 160)

        if not alt_text or not img_title or not caption:
            return fallback_image_seo(scene_notes=scene_notes, filename=filename)

        return {
            "alt_text": alt_text,
            "img_title": img_title,
            "caption": caption,
        }
    except Exception:
        return fallback_image_seo(scene_notes=scene_notes, filename=filename)


def structure_info_from_html(cleaned_html: str) -> str:
    h1 = len(re.findall(r"<h1\b", cleaned_html, re.I))
    h2 = len(re.findall(r"<h2\b", cleaned_html, re.I))
    h3 = len(re.findall(r"<h3\b", cleaned_html, re.I))
    p = len(re.findall(r"<p\b", cleaned_html, re.I))
    embeds = len(extract_embed_markers(cleaned_html))
    return f"H1: {h1}\nH2: {h2}\nH3: {h3}\nParagraphs: {p}\nEmbeds/Videos: {embeds}"


def build_output_html(title: str, intro: str, cleaned_html: str) -> str:
    parts = []

    if title:
        parts.append(f"<h1>{html.escape(title)}</h1>")

    if intro:
        parts.append(f"<p><em>{html.escape(intro)}</em></p>")

    def restore_embed(match):
        return "\n" + (match.group(1) or "").strip() + "\n"

    content = re.sub(
        r"__PRESV_EMBED_START__(.*?)__PRESV_EMBED_END__",
        restore_embed,
        cleaned_html,
        flags=re.S,
    ).strip()

    parts.append(content)
    out = "\n\n".join([p for p in parts if p.strip()])
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def process_article_input(raw: str) -> Dict[str, str]:
    raw = str(raw or "").strip()
    if not raw:
        raise ValueError("Article input is empty.")

    working = raw
    title_hint = ""

    if "<!-- wp:" in working or "<!-- /wp:" in working:
        working = strip_wp_blocks_preserve_embeds(working)

    if looks_like_html(working):
        working = sanitize_html(working)
        title_hint = extract_title_from_html(raw) or extract_title_from_html(working)
        plain_text = html_to_text_preserving_embeds(working)
        cleaned_html = working
    else:
        video_url_pat = (
            r'https?://(?:www\.)?(?:youtube\.com/watch\?[^\s<"\']+|'
            r'youtu\.be/[\w\-]+[^\s<"\']*|'
            r'youtube\.com/shorts/[\w\-]+[^\s<"\']*|'
            r'(?:twitter|x)\.com/\S+/status/\d+[^\s<"\']*|'
            r'facebook\.com/[^\s<"\']+/videos/[^\s<"\']+|'
            r'fb\.watch/[\w\-]+[^\s<"\']*)'
        )

        def convert(match):
            url = match.group(0).strip()
            info = EmbedHelper.detect(url)
            if info["type"]:
                return f"\n__PRESV_EMBED_START__{info['html']}__PRESV_EMBED_END__\n"
            return url

        working = re.sub(video_url_pat, convert, working, flags=re.I)
        plain_text = normalize_ws(re.sub(r"__PRESV_EMBED_START__.*?__PRESV_EMBED_END__", " ", working, flags=re.S))
        cleaned_html = wrap_plain_text_with_paragraphs(working)
        title_hint = guess_title_from_text(plain_text)

    intro = build_intro(plain_text)
    embeds = extract_embed_markers(cleaned_html)
    embeds_text = "\n".join([clamp_text(normalize_ws(re.sub(r"<[^>]+>", " ", x)), 220) for x in embeds]) if embeds else ""

    return {
        "title_hint": title_hint,
        "plain_text": plain_text,
        "intro": intro,
        "cleaned_html": cleaned_html,
        "detected_embeds": embeds_text,
        "structure": structure_info_from_html(cleaned_html),
    }


# ============================================================
# Routes
# ============================================================

@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/test-key")
def api_test_key():
    data = request.get_json(silent=True) or {}
    api_key = (data.get("api_key") or "").strip()
    ok, message = verify_api_key(api_key)
    return jsonify({"ok": ok, "message": message})


@app.post("/api/generate-seo")
def api_generate_seo():
    data = request.get_json(silent=True) or {}
    article = (data.get("article") or "").strip()
    api_key = (data.get("api_key") or "").strip()

    if not article:
        return jsonify({"ok": False, "error": "Article input is empty."}), 400

    try:
        processed = process_article_input(article)
        seo = generate_ai_seo(
            api_key=api_key,
            plain_text=processed["plain_text"],
            title_hint=processed["title_hint"],
        )

        final_title = seo["seo_title"] or processed["title_hint"] or "Untitled Article"
        final_output = build_output_html(
            title=final_title,
            intro=processed["intro"],
            cleaned_html=processed["cleaned_html"],
        )

        return jsonify({
            "ok": True,
            "focus_keyphrase": seo["focus_keyphrase"],
            "seo_title": final_title,
            "meta_description": seo["meta_description"],
            "detected_embeds": processed["detected_embeds"],
            "seo_output": final_output,
            "structure": processed["structure"],
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/api/generate-image-seo")
def api_generate_image_seo():
    api_key = (request.form.get("api_key") or "").strip()
    scene_notes = (request.form.get("scene_notes") or "").strip()
    image_file = request.files.get("image")

    if not image_file:
        return jsonify({"ok": False, "error": "No image uploaded."}), 400

    try:
        image_data_url = image_to_data_url(image_file)
        result = generate_ai_image_seo(
            api_key=api_key,
            image_data_url=image_data_url,
            scene_notes=scene_notes,
            filename=image_file.filename or "",
        )
        return jsonify({"ok": True, **result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
