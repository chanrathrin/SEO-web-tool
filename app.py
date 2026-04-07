import os
import re
import json
import html as html_mod
from typing import List, Dict, Optional

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)

TOGETHER_BASE_URL = "https://api.together.xyz/v1"
SEO_MODEL = os.getenv("TOGETHER_SEO_MODEL", "Qwen/Qwen2.5-7B-Instruct-Turbo")

INDEX_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>WordPress SEO Studio</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <div class="app-shell">
    <header class="hero">
      <div>
        <h1>WordPress SEO Studio</h1>
        <p>Paste WordPress HTML, Gutenberg blocks, or plain article text. Generate SEO output and keep video/embed content.</p>
      </div>
      <div class="hero-actions">
        <button id="themeToggle" class="btn ghost" type="button">Toggle Theme</button>
      </div>
    </header>

    <section class="card">
      <div class="field-row">
        <div class="field grow">
          <label for="apiKey">Together API Key (optional)</label>
          <input id="apiKey" type="password" placeholder="Paste Together API key for AI SEO fields">
        </div>
      </div>
    </section>

    <section class="grid two">
      <div class="card">
        <div class="section-title">Input</div>

        <div class="field">
          <label for="articleInput">Article / WordPress HTML</label>
          <textarea id="articleInput" class="input-xl" placeholder="Paste article HTML, Gutenberg HTML, or plain article text here..."></textarea>
        </div>

        <div class="toolbar">
          <button id="generateBtn" class="btn primary" type="button">Generate SEO</button>
          <button id="clearBtn" class="btn" type="button">Clear</button>
          <button id="copyInputBtn" class="btn" type="button">Copy Input</button>
        </div>

        <div id="statusBox" class="status info">Ready.</div>
      </div>

      <div class="card">
        <div class="section-title">SEO Fields</div>

        <div class="field">
          <label for="focusKeyphrase">Focus Keyphrase</label>
          <div class="copy-row">
            <input id="focusKeyphrase" readonly>
            <button class="btn small" type="button" data-copy-target="focusKeyphrase">Copy</button>
          </div>
        </div>

        <div class="field">
          <label for="seoTitle">SEO Title</label>
          <div class="copy-row">
            <input id="seoTitle" readonly>
            <button class="btn small" type="button" data-copy-target="seoTitle">Copy</button>
          </div>
          <div id="seoTitleCounter" class="counter">0 / 60</div>
        </div>

        <div class="field">
          <label for="metaDescription">Meta Description</label>
          <div class="copy-row align-start">
            <textarea id="metaDescription" readonly></textarea>
            <button class="btn small" type="button" data-copy-target="metaDescription">Copy</button>
          </div>
          <div id="metaCounter" class="counter">0 / 160</div>
        </div>

        <div class="field">
          <label for="detectedEmbeds">Detected Embeds / Videos</label>
          <textarea id="detectedEmbeds" readonly></textarea>
        </div>
      </div>
    </section>

    <section class="card">
      <div class="section-title">SEO Output HTML</div>
      <div class="toolbar">
        <button id="copyOutputBtn" class="btn success" type="button">Copy SEO Output</button>
      </div>
      <textarea id="seoOutput" class="input-xxl" readonly></textarea>
    </section>

    <section class="grid two">
      <div class="card">
        <div class="section-title">Google Preview</div>
        <div class="preview-google">
          <div class="preview-url">example.com › article</div>
          <div id="previewTitle" class="preview-title">SEO Title will appear here</div>
          <div id="previewMeta" class="preview-meta">Meta description will appear here.</div>
        </div>
      </div>

      <div class="card">
        <div class="section-title">Detected Structure</div>
        <textarea id="structureInfo" readonly></textarea>
      </div>
    </section>
  </div>

  <script src="/static/script.js"></script>
</body>
</html>
"""


def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def clamp_text(text: str, limit: int) -> str:
    text = normalize_spaces(text)
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
        parts = []
        for item in content:
            if isinstance(item, dict):
                t = item.get("text") or item.get("content") or ""
                if t:
                    parts.append(str(t))
            elif item:
                parts.append(str(item))
        return "\n".join(parts).strip()
    return str(content or "").strip()


def parse_json(raw: str) -> dict:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("Empty AI response")
    tries = [raw]
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    if cleaned != raw:
        tries.append(cleaned)
    m = re.search(r"\{.*\}", cleaned, re.S)
    if m:
        tries.append(m.group(0))
    last_err = None
    for candidate in tries:
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except Exception as e:
            last_err = e
    raise ValueError("Cannot parse AI JSON") from last_err


class EmbedHelper:
    YOUTUBE_PATTERNS = [
        r"youtube\.com/embed/([\w-]+)",
        r"youtube\.com/watch\?[^\"'\s]*v=([\w-]+)",
        r"youtu\.be/([\w-]+)",
        r"youtube\.com/v/([\w-]+)",
        r"youtube\.com/shorts/([\w-]+)",
    ]
    TWITTER_PATTERNS = [
        r"https?://(?:www\.)?(?:twitter|x)\.com/([A-Za-z0-9_]+)/status(?:es)?/(\d+)",
        r"https?://(?:www\.)?twitter\.com/i/web/status/(\d+)",
        r"platform\.twitter\.com/embed/Tweet\.html\?[^\"'\s]*(?:id|tweetId)=(\d+)",
        r"data-tweet-id=[\"'](\d+)[\"']",
    ]
    FACEBOOK_PATTERNS = [
        r"facebook\.com/[^\s\"'<>]+/videos/(\d+)",
        r"facebook\.com/watch/?\?v=(\d+)",
        r"fb\.watch/([\w-]+)",
        r"facebook\.com/video\.php\?v=(\d+)",
    ]

    @classmethod
    def _decode_url(cls, value: str) -> str:
        return html_mod.unescape(str(value or "")).strip()

    @classmethod
    def _yt_watch_url(cls, vid_id: str) -> str:
        return f"https://www.youtube.com/watch?v={vid_id}"

    @classmethod
    def _yt_gutenberg(cls, vid_id: str) -> str:
        url = cls._yt_watch_url(vid_id)
        safe = html_mod.escape(url, quote=True)
        return (
            f'<!-- wp:embed {{"url":"{safe}","type":"video","providerNameSlug":"youtube","responsive":true}} -->\n'
            f'<figure class="wp-block-embed is-type-video is-provider-youtube wp-block-embed-youtube">'
            f'<div class="wp-block-embed__wrapper">{safe}</div></figure>\n'
            f'<!-- /wp:embed -->'
        )

    @classmethod
    def _twitter_public_url(cls, username: str, tweet_id: str) -> str:
        return f"https://twitter.com/{username}/status/{tweet_id}"

    @classmethod
    def _twitter_generic_url(cls, tweet_id: str) -> str:
        return f"https://twitter.com/i/web/status/{tweet_id}"

    @classmethod
    def _twitter_gutenberg(cls, url: str) -> str:
        safe = html_mod.escape(url, quote=True)
        return (
            f'<!-- wp:embed {{"url":"{safe}","type":"rich","providerNameSlug":"twitter","responsive":true}} -->\n'
            f'<figure class="wp-block-embed is-type-rich is-provider-twitter wp-block-embed-twitter">'
            f'<div class="wp-block-embed__wrapper">{safe}</div></figure>\n'
            f'<!-- /wp:embed -->'
        )

    @classmethod
    def _facebook_gutenberg(cls, url: str) -> str:
        safe = html_mod.escape(url, quote=True)
        return (
            f'<!-- wp:embed {{"url":"{safe}","type":"rich","providerNameSlug":"facebook","responsive":true}} -->\n'
            f'<figure class="wp-block-embed is-type-rich is-provider-facebook wp-block-embed-facebook">'
            f'<div class="wp-block-embed__wrapper">{safe}</div></figure>\n'
            f'<!-- /wp:embed -->'
        )

    @classmethod
    def detect(cls, raw: str) -> Dict[str, str]:
        raw = cls._decode_url(raw)
        low = raw.lower()

        for pat in cls.YOUTUBE_PATTERNS:
            m = re.search(pat, raw, re.I)
            if m:
                vid_id = m.group(1).split("&")[0].split("?")[0].strip()
                url = cls._yt_watch_url(vid_id)
                return {
                    "type": "youtube",
                    "icon": "▶",
                    "label": f"YouTube Video [{vid_id}]",
                    "html": cls._yt_gutenberg(vid_id),
                    "html_classic": url,
                    "src": url,
                }

        m = re.search(
            r"https?://(?:www\.)?(?:twitter|x)\.com/([A-Za-z0-9_]+)/status(?:es)?/(\d+)",
            raw,
            re.I,
        )
        if m:
            username = m.group(1)
            tweet_id = m.group(2)
            public_url = cls._twitter_public_url(username, tweet_id)
            return {
                "type": "twitter",
                "icon": "🐦",
                "label": f"Twitter/X Post [{tweet_id}]",
                "html": cls._twitter_gutenberg(public_url),
                "html_classic": public_url,
                "src": public_url,
            }

        for pat in cls.TWITTER_PATTERNS:
            m = re.search(pat, raw, re.I)
            if m:
                tweet_id = m.group(m.lastindex or 1)
                tw_url = cls._twitter_generic_url(tweet_id)
                return {
                    "type": "twitter",
                    "icon": "🐦",
                    "label": f"Twitter/X Post [{tweet_id}]",
                    "html": cls._twitter_gutenberg(tw_url),
                    "html_classic": tw_url,
                    "src": tw_url,
                }

        for pat in cls.FACEBOOK_PATTERNS:
            m = re.search(pat, raw, re.I)
            if m:
                fb_url_match = re.search(r"https?://(?:www\.)?facebook\.com/[^\s\"'<>]+", raw, re.I)
                fb_url = fb_url_match.group(0).rstrip('/"\'' ) if fb_url_match else raw
                return {
                    "type": "facebook",
                    "icon": "📘",
                    "label": "Facebook Video",
                    "html": cls._facebook_gutenberg(fb_url),
                    "html_classic": fb_url,
                    "src": fb_url,
                }

        src_m = re.search(r'src=["\'](https?://[^"\'>\s]+)["\']', raw, re.I)
        if src_m:
            src = cls._decode_url(src_m.group(1))
            yt_info = cls.detect(src)
            if yt_info["type"]:
                return yt_info
            return {
                "type": "generic",
                "icon": "▶",
                "label": "Embedded Media",
                "html": src,
                "html_classic": src,
                "src": src,
            }

        bare = re.search(r"https?://[^\s<\"']+", raw, re.I)
        if bare:
            src = bare.group(0)
            info = cls.detect(src)
            if info["type"]:
                return info
            return {
                "type": "generic",
                "icon": "▶",
                "label": "Embedded URL",
                "html": src,
                "html_classic": src,
                "src": src,
            }

        return {
            "type": "",
            "icon": "",
            "label": "",
            "html": "",
            "html_classic": "",
            "src": "",
        }


def looks_html(text: str) -> bool:
    s = (text or "").strip().lower()
    html_tokens = (
        "<html", "<body", "<div", "<section", "<article", "<p", "<h1", "<h2",
        "<h3", "<iframe", "<figure", "<blockquote", "<video", "<!-- wp:"
    )
    return any(token in s for token in html_tokens)


def strip_wp_block_comments(raw: str) -> str:
    raw = str(raw or "")

    def _save_wp_embed(m):
        block_json = m.group(1) or ""
        inner_html = (m.group(2) or "").strip()

        url_m = re.search(r'"url"\s*:\s*"([^"]+)"', block_json)
        embed_url = url_m.group(1) if url_m else ""

        if not embed_url:
            bare_m = re.search(
                r'<div[^>]*class=["\'][^"\']*wp-block-embed__wrapper[^"\']*["\'][^>]*>\s*(https?://[^\s<]+)',
                inner_html,
                re.I | re.S,
            )
            if bare_m:
                embed_url = bare_m.group(1).strip()

        if not embed_url:
            any_url = re.search(r'(https?://[^\s<"\']{10,})', inner_html)
            if any_url:
                embed_url = any_url.group(1).strip()

        if embed_url:
            info = EmbedHelper.detect(embed_url)
            if info["type"]:
                return f"\n__PRESV_EMBED_START__{info['html']}__PRESV_EMBED_END__\n"
            return f"\n__PRESV_EMBED_START__{inner_html}__PRESV_EMBED_END__\n"

        return f"\n{inner_html}\n"

    raw = re.sub(
        r'<!--\s*wp:embed\s*(\{[^}]*\}|\S*)\s*-->(.*?)<!--\s*/wp:embed\s*-->',
        _save_wp_embed,
        raw,
        flags=re.I | re.S,
    )

    def _save_wp_video(m):
        inner_html = (m.group(1) or "").strip()
        src_m = re.search(r'src=["\']([^"\']+)["\']', inner_html, re.I)
        url_m = re.search(r'"url"\s*:\s*"([^"]+)"', m.group(0))
        embed_url = (url_m.group(1) if url_m else "") or (src_m.group(1) if src_m else "")
        if embed_url:
            info = EmbedHelper.detect(embed_url)
            if info["type"]:
                return f"\n__PRESV_EMBED_START__{info['html']}__PRESV_EMBED_END__\n"
        return f"\n{inner_html}\n"

    raw = re.sub(
        r'<!--\s*wp:video[^-]*-->(.*?)<!--\s*/wp:video\s*-->',
        _save_wp_video,
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

    def _convert_bare_video_url(m):
        url = m.group(0).strip()
        info = EmbedHelper.detect(url)
        if info["type"]:
            return f"\n__PRESV_EMBED_START__{info['html']}__PRESV_EMBED_END__\n"
        return url

    raw = re.sub(video_url_pat, _convert_bare_video_url, raw, flags=re.I)

    def fix_paragraph_block(m):
        inner = (m.group(1) or "").strip()
        if not inner:
            return ""
        if re.match(r"^<p[\s>]", inner, re.I):
            return inner + "\n"
        if re.search(r"^<(h[1-6]|div|figure|ul|ol|blockquote|iframe|video)", inner, re.I):
            return inner + "\n"
        if "__PRESV_EMBED_START__" in inner:
            return inner + "\n"
        return f"<p>{inner}</p>\n"

    cleaned = re.sub(
        r"<!--\s*wp:paragraph[^>]*-->\s*(.*?)\s*<!--\s*/wp:paragraph\s*-->",
        fix_paragraph_block,
        raw,
        flags=re.I | re.S,
    )

    cleaned = re.sub(r"<!--\s*/?\s*wp:[^>]*-->", "", cleaned, flags=re.I | re.S)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def wrap_plain_paragraphs(text: str) -> str:
    video_url_pat = (
        r'https?://(?:www\.)?(?:'
        r'youtube\.com/watch\?[^\s<>"\']{5,}|'
        r'youtu\.be/[\w\-]{5,}[^\s<>"\']*|'
        r'youtube\.com/shorts/[\w\-]{5,}[^\s<>"\']*|'
        r'(?:twitter|x)\.com/\S+/status/\d{5,}[^\s<>"\']*|'
        r'facebook\.com/[^\s<>"\']+/videos/\d{5,}[^\s<>"\']*|'
        r'fb\.watch/[\w\-]{3,}[^\s<>"\']*'
        r')'
    )

    blocks = re.split(r'\n[ \t]*\n', text)
    result = []

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        if re.match(r'^<|^__PRESV_EMBED', block, re.I):
            result.append(block)
            continue

        if re.match(r'^(?:&nbsp;|\xa0|\s)+$', block, re.I):
            continue

        bare_url_m = re.match(r'^(' + video_url_pat + r')$', block.strip(), re.I)
        if bare_url_m:
            url = bare_url_m.group(1).strip()
            info = EmbedHelper.detect(url)
            if info["type"]:
                result.append(f"__PRESV_EMBED_START__{info['html']}__PRESV_EMBED_END__")
                continue

        def _inline_url_to_embed(m):
            url = m.group(0).strip()
            info = EmbedHelper.detect(url)
            if info["type"]:
                return f" __PRESV_EMBED_START__{info['html']}__PRESV_EMBED_END__ "
            return url

        block = re.sub(video_url_pat, _inline_url_to_embed, block, flags=re.I)
        result.append(f"<p>{block}</p>")

    return "\n\n".join(result).strip()


def sanitize_html(raw: str) -> str:
    raw = str(raw or "")

    raw = re.sub(r"<script\b.*?</script>", "", raw, flags=re.I | re.S)
    raw = re.sub(r"<style\b.*?</style>", "", raw, flags=re.I | re.S)
    raw = re.sub(r"<noscript\b.*?</noscript>", "", raw, flags=re.I | re.S)
    raw = re.sub(r"&nbsp;", " ", raw, flags=re.I)
    raw = re.sub(r"\u00a0", " ", raw)

    return raw.strip()


def html_to_text_preserving_embeds(raw_html: str) -> str:
    temp = re.sub(r"__PRESV_EMBED_START__(.*?)__PRESV_EMBED_END__", " ", raw_html, flags=re.S)
    soup = BeautifulSoup(temp, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = soup.get_text("\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines).strip()


def extract_title_from_html(raw_html: str) -> str:
    text = raw_html or ""

    for pat in [
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\'>]*)["\']',
        r'<meta[^>]+content=["\']([^"\'>]*)["\'][^>]+property=["\']og:title["\']',
        r"<title[^>]*>(.*?)</title>",
        r"<h1[^>]*>(.*?)</h1>",
    ]:
        m = re.search(pat, text, re.I | re.S)
        if m:
            cleaned = re.sub(r"<[^>]+>", " ", m.group(1))
            cleaned = html_mod.unescape(cleaned)
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            cleaned = re.sub(r"\s+[|\-–—]\s+.*$", "", cleaned).strip()
            if cleaned:
                return cleaned

    return ""


def guess_title_from_text(text: str) -> str:
    lines = [normalize_spaces(x) for x in str(text or "").splitlines() if normalize_spaces(x)]
    if not lines:
        return "Untitled Article"
    first = lines[0]
    if len(first) > 90:
        first = clamp_text(first, 90)
    return first


def build_intro(text: str) -> str:
    text = normalize_spaces(text)
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text)
    intro = " ".join(parts[:2]).strip()
    return clamp_text(intro, 220)


def derive_focus_keyphrase(text: str) -> str:
    words = re.findall(r"\b[a-zA-Z0-9\u1780-\u17ff][a-zA-Z0-9\u1780-\u17ff'-]{2,}\b", text.lower())
    stop = {
        "this", "that", "with", "from", "your", "have", "will", "about", "into",
        "after", "before", "their", "there", "they", "them", "what", "when",
        "where", "which", "while", "would", "could", "should", "article",
        "video", "embed"
    }
    freq = {}
    for w in words:
        if w in stop:
            continue
        freq[w] = freq.get(w, 0) + 1
    ranked = sorted(freq.items(), key=lambda x: (-x[1], x[0]))
    phrase = " ".join([item[0] for item in ranked[:3]]).strip()
    return phrase[:60] or "wordpress article"


def generate_fallback_seo(text: str, title_hint: str = "") -> Dict[str, str]:
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
        return generate_fallback_seo(plain_text, title_hint=title_hint)

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
{plain_text[:3500]}
"""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload = {
        "model": SEO_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "top_p": 0.9,
        "response_format": {"type": "json_object"},
        "max_tokens": 220,
    }

    try:
        r = requests.post(
            f"{TOGETHER_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=(8, 30),
        )
        r.raise_for_status()
        data = r.json()
        parsed = parse_json(extract_content(data))
        focus = clamp_text(str(parsed.get("focus_keyphrase", "")).strip(), 60)
        seo_title = clamp_text(str(parsed.get("seo_title", "")).strip(), 60)
        meta = clamp_text(str(parsed.get("meta_description", "")).strip(), 160)

        if not focus or not seo_title or not meta:
            return generate_fallback_seo(plain_text, title_hint=title_hint)

        return {
            "focus_keyphrase": focus,
            "seo_title": seo_title,
            "meta_description": meta,
        }
    except Exception:
        return generate_fallback_seo(plain_text, title_hint=title_hint)


def extract_embed_markers(raw: str) -> List[str]:
    return re.findall(r"__PRESV_EMBED_START__(.*?)__PRESV_EMBED_END__", raw or "", flags=re.S)


def structure_info_from_html(cleaned_html: str) -> str:
    h1_count = len(re.findall(r"<h1\b", cleaned_html, re.I))
    h2_count = len(re.findall(r"<h2\b", cleaned_html, re.I))
    h3_count = len(re.findall(r"<h3\b", cleaned_html, re.I))
    p_count = len(re.findall(r"<p\b", cleaned_html, re.I))
    embeds = len(extract_embed_markers(cleaned_html))
    return (
        f"H1: {h1_count}\n"
        f"H2: {h2_count}\n"
        f"H3: {h3_count}\n"
        f"Paragraphs: {p_count}\n"
        f"Embeds/Videos: {embeds}"
    )


def build_output_html(title: str, intro: str, cleaned_html: str) -> str:
    parts = []

    if title:
        parts.append(f"<h1>{html_mod.escape(title)}</h1>")

    if intro:
        parts.append(f"<p><em>{html_mod.escape(intro)}</em></p>")

    content = cleaned_html.strip()

    def _restore_embed_marker(m):
        inner = (m.group(1) or "").strip()
        return "\n" + inner + "\n"

    content = re.sub(
        r"__PRESV_EMBED_START__(.*?)__PRESV_EMBED_END__",
        _restore_embed_marker,
        content,
        flags=re.S,
    )

    parts.append(content)
    output = "\n\n".join([p for p in parts if p.strip()])
    output = re.sub(r"\n{3,}", "\n\n", output).strip()
    return output


def process_input(raw: str) -> Dict[str, str]:
    raw = str(raw or "").strip()
    if not raw:
        raise ValueError("Article input is empty.")

    has_wp_blocks = "<!-- wp:" in raw or "<!-- /wp:" in raw

    working = raw
    title_hint = ""

    if has_wp_blocks:
        working = strip_wp_block_comments(working)

    if looks_html(working):
        if "__PRESV_EMBED_START__" not in working and re.search(r"<iframe|<blockquote|<video|<figure", working, re.I):
            pass
        working = sanitize_html(working)
        title_hint = extract_title_from_html(raw) or extract_title_from_html(working)
        if not re.search(r"<p\b", working, re.I) and "__PRESV_EMBED_START__" in working:
            working = wrap_plain_paragraphs(working)
        plain_text = html_to_text_preserving_embeds(working)
        intro = build_intro(plain_text)
        structure = structure_info_from_html(working)
        embeds = extract_embed_markers(working)
        return {
            "title_hint": title_hint,
            "plain_text": plain_text,
            "intro": intro,
            "cleaned_html": working,
            "embeds": "\n".join([normalize_spaces(re.sub(r"<[^>]+>", " ", x))[:220] for x in embeds]) if embeds else "",
            "structure": structure,
        }

    plain = raw
    plain = re.sub(r"&nbsp;", " ", plain, flags=re.I)
    plain = re.sub(r"&#\d+;|&[a-z]+;", " ", plain, flags=re.I)
    plain = re.sub(r"\u00a0", " ", plain)

    def _convert_url_to_embed(m):
        url = m.group(0).strip()
        info = EmbedHelper.detect(url)
        if info["type"]:
            return f"\n__PRESV_EMBED_START__{info['html']}__PRESV_EMBED_END__\n"
        return url

    video_url_pat = (
        r'https?://(?:www\.)?(?:youtube\.com/watch\?[^\s<"\']+|'
        r'youtu\.be/[\w\-]+[^\s<"\']*|'
        r'youtube\.com/shorts/[\w\-]+[^\s<"\']*|'
        r'(?:twitter|x)\.com/\S+/status/\d+[^\s<"\']*|'
        r'facebook\.com/[^\s<"\']+/videos/[^\s<"\']+|'
        r'fb\.watch/[\w\-]+[^\s<"\']*)'
    )
    plain = re.sub(video_url_pat, _convert_url_to_embed, plain, flags=re.I)

    blocks = []
    for chunk in re.split(r"\n\s*\n", plain):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "__PRESV_EMBED_START__" in chunk:
            blocks.append(chunk)
        else:
            safe = html_mod.escape(chunk).replace("\n", "<br>")
            blocks.append(f"<p>{safe}</p>")

    cleaned_html = "\n\n".join(blocks).strip()
    plain_text = re.sub(r"__PRESV_EMBED_START__.*?__PRESV_EMBED_END__", " ", plain, flags=re.S)
    plain_text = normalize_spaces(plain_text)
    title_hint = guess_title_from_text(plain_text)
    intro = build_intro(plain_text)
    embeds = extract_embed_markers(cleaned_html)
    structure = structure_info_from_html(cleaned_html)

    return {
        "title_hint": title_hint,
        "plain_text": plain_text,
        "intro": intro,
        "cleaned_html": cleaned_html,
        "embeds": "\n".join([normalize_spaces(re.sub(r"<[^>]+>", " ", x))[:220] for x in embeds]) if embeds else "",
        "structure": structure,
    }


@app.get("/")
def index():
    return render_template_string(INDEX_HTML)


@app.post("/generate")
def generate():
    payload = request.get_json(silent=True) or {}
    raw = (payload.get("article") or "").strip()
    api_key = (payload.get("api_key") or "").strip()

    if not raw:
        return jsonify({"ok": False, "error": "Article input is empty."}), 400

    try:
        processed = process_input(raw)
        seo = generate_ai_seo(
            api_key=api_key,
            plain_text=processed["plain_text"],
            title_hint=processed["title_hint"],
        )

        final_title = seo["seo_title"] or processed["title_hint"] or "Untitled Article"
        final_intro = processed["intro"]
        final_output = build_output_html(
            title=final_title,
            intro=final_intro,
            cleaned_html=processed["cleaned_html"],
        )

        return jsonify({
            "ok": True,
            "focus_keyphrase": seo["focus_keyphrase"],
            "seo_title": final_title,
            "meta_description": seo["meta_description"],
            "detected_embeds": processed["embeds"],
            "seo_output": final_output,
            "structure": processed["structure"],
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
