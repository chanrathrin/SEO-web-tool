import os
import re
import html
import json
from difflib import SequenceMatcher

import requests
from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)

TOGETHER_BASE_URL = "https://api.together.xyz/v1"
SEO_MODEL = os.getenv("TOGETHER_SEO_MODEL", "Qwen/Qwen2.5-7B-Instruct-Turbo")


INDEX_HTML = """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>WordPress SEO Studio - Web</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <div class="container">
        <header class="hero">
            <h1>WordPress SEO Studio</h1>
            <p>Deploy-ready web version for WordPress HTML, article text, and video/embed preservation.</p>
        </header>

        <section class="card">
            <div class="row">
                <div class="field grow">
                    <label for="api_key">Together API Key (optional)</label>
                    <input id="api_key" type="password" placeholder="Paste Together API key if you want AI SEO fields">
                </div>
                <div class="field">
                    <label>&nbsp;</label>
                    <button id="toggle_api_key" class="btn btn-secondary">Show / Hide Key</button>
                </div>
            </div>
        </section>

        <section class="grid two">
            <div class="card">
                <div class="field">
                    <label for="article_input">Article / WordPress HTML Input</label>
                    <textarea id="article_input" rows="22" placeholder="Paste WordPress HTML, mixed content, or article text here..."></textarea>
                </div>

                <div class="button-row">
                    <button id="generate_btn" class="btn btn-primary">Generate SEO</button>
                    <button id="clear_btn" class="btn btn-secondary">Clear</button>
                    <button id="sample_btn" class="btn btn-secondary">Sample</button>
                </div>

                <div id="status" class="status">Ready</div>
            </div>

            <div class="card">
                <div class="field">
                    <label for="focus_keyphrase">Focus Keyphrase</label>
                    <input id="focus_keyphrase" type="text" readonly>
                </div>
                <div class="field">
                    <label for="seo_title">SEO Title</label>
                    <input id="seo_title" type="text" readonly>
                </div>
                <div class="field">
                    <label for="meta_description">Meta Description</label>
                    <textarea id="meta_description" rows="4" readonly></textarea>
                </div>
                <div class="field">
                    <label for="detected_embeds">Detected Embeds</label>
                    <textarea id="detected_embeds" rows="8" readonly></textarea>
                </div>
            </div>
        </section>

        <section class="card">
            <div class="field">
                <label for="seo_output">SEO Output (WordPress-ready HTML)</label>
                <textarea id="seo_output" rows="22" readonly></textarea>
            </div>

            <div class="button-row">
                <button id="copy_output_btn" class="btn btn-primary">Copy SEO Output</button>
                <button id="copy_meta_btn" class="btn btn-secondary">Copy Meta</button>
                <button id="copy_title_btn" class="btn btn-secondary">Copy SEO Title</button>
                <button id="copy_keyphrase_btn" class="btn btn-secondary">Copy Keyphrase</button>
            </div>
        </section>
    </div>

    <script src="/static/script.js"></script>
</body>
</html>
"""


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def parse_json(raw: str) -> dict:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("Empty response")
    candidates = [raw]
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    if cleaned != raw:
        candidates.append(cleaned)
    m = re.search(r"\{.*\}", cleaned, re.S)
    if m:
        candidates.append(m.group(0).strip())
    last_err = None
    for c in candidates:
        try:
            data = json.loads(c)
            if isinstance(data, dict):
                return data
        except Exception as e:
            last_err = e
    raise ValueError(f"Cannot parse JSON: {raw[:180]}") from last_err


def chat_completion(api_key: str, prompt: str) -> dict:
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
    r = requests.post(
        f"{TOGETHER_BASE_URL}/chat/completions",
        headers=headers,
        json=payload,
        timeout=(8, 35),
    )
    if r.status_code >= 400:
        try:
            d = r.json()
            detail = d.get("error", {}).get("message") or d.get("message") or r.text
        except Exception:
            detail = r.text
        raise RuntimeError(f"HTTP {r.status_code}: {detail}")
    return r.json()


class EmbedHelper:
    YOUTUBE_PATTERNS = [
        r"youtube\.com/embed/([\w-]+)",
        r"youtube\.com/watch\?[^\"'\s]*v=([\w-]+)",
        r"youtu\.be/([\w-]+)",
        r"youtube\.com/v/([\w-]+)",
        r"youtube\.com/shorts/([\w-]+)",
    ]
    TWITTER_PATTERNS = [
        r"(?:twitter|x)\.com/\w+/status(?:es)?/(\d+)",
        r"platform\.twitter\.com/embed/Tweet\.html\?[^\"'\s]*(?:id|tweetId)=(\d+)",
        r"twitter\.com/i/web/status/(\d+)",
    ]
    FACEBOOK_PATTERNS = [
        r"facebook\.com/[^\s\"'<>]+/videos/([\d]+)",
        r"facebook\.com/watch/?\?v=(\d+)",
        r"fb\.watch/([\w-]+)",
        r"facebook\.com/video\.php\?v=(\d+)",
    ]

    @classmethod
    def _yt_gutenberg(cls, vid_id: str) -> str:
        url = f"https://www.youtube.com/watch?v={vid_id}"
        safe = html.escape(url)
        return (
            f'<!-- wp:embed {{"url":"{safe}","type":"video","providerNameSlug":"youtube","responsive":true}} -->\n'
            f'<figure class="wp-block-embed is-type-video is-provider-youtube wp-block-embed-youtube">'
            f'<div class="wp-block-embed__wrapper">{safe}</div></figure>\n'
            f'<!-- /wp:embed -->'
        )

    @classmethod
    def _twitter_gutenberg(cls, url: str) -> str:
        safe = html.escape(url)
        return (
            f'<!-- wp:embed {{"url":"{safe}","type":"rich","providerNameSlug":"twitter","responsive":true}} -->\n'
            f'<figure class="wp-block-embed is-type-rich is-provider-twitter wp-block-embed-twitter">'
            f'<div class="wp-block-embed__wrapper">{safe}</div></figure>\n'
            f'<!-- /wp:embed -->'
        )

    @classmethod
    def _facebook_gutenberg(cls, url: str) -> str:
        safe = html.escape(url)
        return (
            f'<!-- wp:embed {{"url":"{safe}","type":"rich","providerNameSlug":"facebook","responsive":true}} -->\n'
            f'<figure class="wp-block-embed is-type-rich is-provider-facebook wp-block-embed-facebook">'
            f'<div class="wp-block-embed__wrapper">{safe}</div></figure>\n'
            f'<!-- /wp:embed -->'
        )

    @classmethod
    def detect(cls, raw: str) -> dict:
        raw = html.unescape(str(raw or "")).strip()
        if not raw:
            return {"type": None, "label": "", "html": "", "html_classic": "", "src": ""}

        for pat in cls.YOUTUBE_PATTERNS:
            m = re.search(pat, raw, re.I)
            if m:
                vid_id = m.group(1).split("&")[0].split("?")[0].strip()
                watch_url = f"https://www.youtube.com/watch?v={vid_id}"
                return {
                    "type": "youtube",
                    "label": f"YouTube Video [{vid_id}]",
                    "html": cls._yt_gutenberg(vid_id),
                    "html_classic": f'<p><a href="{html.escape(watch_url)}">{html.escape(watch_url)}</a></p>',
                    "src": watch_url,
                    "vid_id": vid_id,
                }

        for pat in cls.TWITTER_PATTERNS:
            m = re.search(pat, raw, re.I)
            if m:
                tweet_id = m.group(1)
                direct = re.search(
                    r'https?://(?:www\.)?(?:twitter|x)\.com/([A-Za-z0-9_]+)/status(?:es)?/(\d+)',
                    raw,
                    re.I,
                )
                if direct:
                    url = f"https://twitter.com/{direct.group(1)}/status/{direct.group(2)}"
                else:
                    url = f"https://twitter.com/i/web/status/{tweet_id}"
                return {
                    "type": "twitter",
                    "label": f"Twitter/X Post [{tweet_id}]",
                    "html": cls._twitter_gutenberg(url),
                    "html_classic": f'<p><a href="{html.escape(url)}">{html.escape(url)}</a></p>',
                    "src": url,
                    "tweet_id": tweet_id,
                }

        for pat in cls.FACEBOOK_PATTERNS:
            m = re.search(pat, raw, re.I)
            if m:
                url_m = re.search(r'https?://(?:www\.)?(?:facebook\.com|fb\.watch)/[^\s<>"\']+', raw, re.I)
                url = url_m.group(0) if url_m else raw
                return {
                    "type": "facebook",
                    "label": "Facebook Video",
                    "html": cls._facebook_gutenberg(url),
                    "html_classic": f'<p><a href="{html.escape(url)}">{html.escape(url)}</a></p>',
                    "src": url,
                }

        iframe_src = re.search(r'src=["\'](https?://[^"\']+)["\']', raw, re.I)
        if iframe_src:
            src = iframe_src.group(1).strip()
            return {
                "type": "generic",
                "label": "Embedded Media",
                "html": raw,
                "html_classic": raw,
                "src": src,
            }

        bare_url = re.search(r'https?://[^\s<>"\']+', raw, re.I)
        if bare_url:
            src = bare_url.group(0)
            return {
                "type": "generic",
                "label": "Embedded URL",
                "html": f'<p><a href="{html.escape(src)}">{html.escape(src)}</a></p>',
                "html_classic": f'<p><a href="{html.escape(src)}">{html.escape(src)}</a></p>',
                "src": src,
            }

        return {"type": None, "label": "", "html": "", "html_classic": "", "src": ""}


def strip_tags_text(t: str) -> str:
    t = re.sub(r"<a\b[^>]*>(.*?)</a>", r"\1", str(t or ""), flags=re.I | re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    t = re.sub(r"https?://\S+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def clean_para_html(t: str) -> str:
    t = str(t or "")
    t = re.sub(
        r"<(?:script|style|noscript|form|button|svg|canvas)\b[^>]*>.*?</(?:script|style|noscript|form|button|svg|canvas)>",
        "",
        t,
        flags=re.I | re.S,
    )
    t = html.unescape(t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def link_density(inner_html: str, text: str) -> float:
    if not inner_html or not text:
        return 0.0
    link_texts = re.findall(r"<a\b[^>]*>(.*?)</a>", inner_html, flags=re.I | re.S)
    link_text = " ".join(strip_tags_text(x) for x in link_texts).strip()
    if not link_text:
        return 0.0
    return len(link_text) / max(len(text), 1)


def looks_html(text: str) -> bool:
    s = str(text or "").strip().lower()
    return any(
        m in s
        for m in (
            "<html", "<body", "<div", "<section", "<article",
            "<p", "<h1", "<h2", "<h3", "<iframe", "<video",
            "<figure", "<blockquote", "<ul", "<ol", "[embed]"
        )
    )


def preserve_shortcode_embeds(raw: str) -> str:
    raw = str(raw or "")

    def repl(m):
        url = (m.group(1) or "").strip()
        info = EmbedHelper.detect(url)
        if info["type"]:
            return f"\n__PRESV_EMBED_START__{info['html']}__PRESV_EMBED_END__\n"
        return ""

    raw = re.sub(r"\[embed\](https?://[^\[]+)\[/embed\]", repl, raw, flags=re.I)
    return raw


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
                inner_html, re.I | re.S
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

    def _convert_bare_video_url(m):
        url = m.group(0).strip()
        info = EmbedHelper.detect(url)
        if info["type"]:
            return f"\n__PRESV_EMBED_START__{info['html']}__PRESV_EMBED_END__\n"
        return url

    video_url_pat = (
        r'https?://(?:www\.)?(?:'
        r'youtube\.com/watch\?[^\s<"\']+|'
        r'youtu\.be/[\w\-]+[^\s<"\']*|'
        r'youtube\.com/shorts/[\w\-]+[^\s<"\']*|'
        r'(?:twitter|x)\.com/\S+/status/\d+[^\s<"\']*|'
        r'facebook\.com/[^\s<"\']+/videos/[^\s<"\']+|'
        r'fb\.watch/[\w\-]+[^\s<"\']*'
        r')'
    )
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
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


def sanitize_wp_html(raw: str) -> str:
    raw = str(raw or "")
    raw = preserve_shortcode_embeds(raw)
    raw = re.sub(r"&nbsp;", " ", raw, flags=re.I)
    raw = re.sub(r"\u00a0", " ", raw)
    raw = re.sub(r"[ \t]+", " ", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return raw.strip()


def is_mixed_content(text: str) -> bool:
    has_embed = bool(re.search(r'<iframe|<blockquote|<figure|<video', text, re.I))
    p_tag_count = len(re.findall(r'<p\b', text, re.I))
    has_plain_para = bool(re.search(r'\n[ \t]*\n[A-Za-z\u1780-\u17ff\"\'\u2018\u201c]', text))
    return has_embed and (p_tag_count == 0 or (has_plain_para and p_tag_count < 3))


def wrap_plain_paragraphs(text: str) -> str:
    text = str(text or "")

    def _convert_video_url(m):
        url = m.group(0).strip()
        info = EmbedHelper.detect(url)
        if info["type"]:
            return f"\n__PRESV_EMBED_START__{info['html']}__PRESV_EMBED_END__\n"
        return url

    video_url_pat = (
        r'https?://(?:www\.)?(?:'
        r'youtube\.com/watch\?[^\s<>"\']{5,}|'
        r'youtu\.be/[\w\-]{5,}[^\s<>"\']*|'
        r'youtube\.com/shorts/[\w\-]{5,}[^\s<>"\']*|'
        r'(?:twitter|x)\.com/\S+/status/\d+[^\s<>"\']*|'
        r'facebook\.com/[^\s<>"\']+/videos/[^\s<>"\']+|'
        r'fb\.watch/[\w\-]+[^\s<>"\']*'
        r')'
    )
    text = re.sub(video_url_pat, _convert_video_url, text, flags=re.I)

    parts = re.split(r"\n\s*\n", text)
    out = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if "__PRESV_EMBED_START__" in part:
            out.append(part)
            continue
        if re.search(r"^\s*<(h[1-6]|p|div|figure|blockquote|iframe|video|ul|ol|li)\b", part, re.I):
            out.append(part)
            continue
        out.append(f"<p>{html.escape(part)}</p>")
    return "\n\n".join(out)


def parse_html_blocks(raw: str):
    blocks = []
    raw = sanitize_wp_html(raw)

    og_title = ""
    m = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\'>]*)["\']', raw, re.I | re.S)
    if not m:
        m = re.search(r'<meta[^>]+content=["\']([^"\'>]*)["\'][^>]+property=["\']og:title["\']', raw, re.I | re.S)
    if m:
        og_title = strip_tags_text(m.group(1))

    page_title = ""
    m = re.search(r"<title[^>]*>(.*?)</title>", raw, re.I | re.S)
    if m:
        page_title = strip_tags_text(m.group(1))

    first_h1 = ""
    m = re.search(r"<h1[^>]*>(.*?)</h1>", raw, re.I | re.S)
    if m:
        first_h1 = strip_tags_text(m.group(1))

    page_h1 = og_title or first_h1 or page_title
    if page_h1:
        page_h1 = re.sub(r"\s+[|\-–—]\s+.*$", "", page_h1).strip()
        if page_h1:
            blocks.append({"type": "h1", "content": page_h1})

    token_pat = re.compile(
        r"(__PRESV_EMBED_START__.*?__PRESV_EMBED_END__)"
        r"|(<h[1-6][^>]*>.*?</h[1-6]>)"
        r"|(<blockquote\b[^>]*>.*?</blockquote>(?:\s*<script[^>]*>[^<]*</script>)?)"
        r"|(<iframe\b[^>]*>.*?</iframe>)"
        r"|(<video\b[^>]*>.*?</video>)"
        r"|(<figure\b[^>]*>.*?</figure>)"
        r"|(<div[^>]*style=\"[^\"]*padding-bottom\s*:\s*56\.25%[^\"]*\"[^>]*>.*?</div>)"
        r"|(<p\b[^>]*>.*?</p>)",
        re.I | re.S
    )

    seen_text = set()
    h1_lower = page_h1.lower().strip() if page_h1 else ""

    def make_embed(raw_tag):
        if "__PRESV_EMBED_START__" in raw_tag:
            m2 = re.search(r'__PRESV_EMBED_START__(.*?)__PRESV_EMBED_END__', raw_tag, re.S)
            return m2.group(1).strip() if m2 else ""

        tag_lower = raw_tag.lower()

        if "platform.twitter.com" in tag_lower:
            raw_tag = html.unescape(raw_tag)
            tweet_id = None
            for pat in [
                r'embedid[=&][^&"\']*tweet[_.-](\d{10,})',
                r'(?:id|tweetid)=(\d{10,})',
                r'data-tweet-id=["\'](\d{10,})["\']',
                r'twitter\.com/i/web/status/(\d{10,})',
            ]:
                mm = re.search(pat, raw_tag, re.I)
                if mm:
                    tweet_id = mm.group(1)
                    break
            if tweet_id:
                return EmbedHelper._twitter_gutenberg(f"https://twitter.com/i/web/status/{tweet_id}")

        info = EmbedHelper.detect(raw_tag)
        if info["type"] in ("youtube", "twitter", "facebook"):
            return info["html"]
        if info["type"] == "generic":
            return info.get("html_classic") or info["html"]

        if raw_tag.strip().startswith("<"):
            return raw_tag.strip()
        return ""

    for m in token_pat.finditer(raw):
        tag = m.group(0)
        tag_lower = tag.lower()

        hm = re.match(r"<(h[1-6])[^>]*>(.*?)</h[1-6]>", tag, re.I | re.S)
        if hm:
            level = hm.group(1).lower()
            text = strip_tags_text(hm.group(2))
            if not text:
                continue
            low = text.lower()
            if low in {"share", "related articles", "recommended", "read more", "follow us", "comments", "leave a reply"}:
                continue
            if level == "h1" and blocks and blocks[0]["type"] == "h1":
                if SequenceMatcher(None, blocks[0]["content"].lower(), text.lower()).ratio() >= 0.80:
                    continue
            norm = text.lower().strip()
            if norm in seen_text and level != "h2":
                continue
            seen_text.add(norm)
            blocks.append({"type": level, "content": text})
            continue

        is_embed = (
            "__PRESV_EMBED_START__" in tag or
            tag_lower.startswith("<blockquote") or
            tag_lower.startswith("<iframe") or
            tag_lower.startswith("<video") or
            tag_lower.startswith("<figure") or
            (tag_lower.startswith("<div") and "padding-bottom" in tag_lower)
        )
        if is_embed:
            emb = make_embed(tag)
            if emb:
                blocks.append({"type": "embed", "content": emb})
            continue

        pm = re.match(r"<p[^>]*>(.*?)</p>", tag, re.I | re.S)
        if pm:
            inner_html = pm.group(1).strip()

            for emb_pat in (
                r"__PRESV_EMBED_START__.*?__PRESV_EMBED_END__",
                r"<iframe\b[^>]*>.*?</iframe>",
                r"<video\b[^>]*>.*?</video>",
                r"<blockquote\b[^>]*>.*?</blockquote>",
                r"<figure\b[^>]*>.*?</figure>",
            ):
                emb_m = re.search(emb_pat, inner_html, re.I | re.S)
                if emb_m:
                    raw_emb = emb_m.group(0)
                    emb = make_embed(raw_emb)
                    if emb:
                        blocks.append({"type": "embed", "content": emb})
                    inner_html = re.sub(emb_pat, "", inner_html, flags=re.I | re.S)
                    break

            text_plain = strip_tags_text(inner_html)
            text_plain = re.sub(r'__PRESV_EMBED_START__.*?__PRESV_EMBED_END__', ' ', text_plain, flags=re.S).strip()
            if not text_plain or len(text_plain.split()) < 5:
                continue
            if re.match(r"^https?://[^\s]+$", text_plain):
                continue

            junk_pats = [
                r"follow us", r"share this", r"copy link", r"read more",
                r"related articles?", r"newsletter", r"subscribe",
                r"sign up", r"privacy policy", r"terms of use"
            ]
            if any(re.search(p, text_plain.lower(), re.I) for p in junk_pats) and len(text_plain.split()) <= 20:
                continue
            if link_density(inner_html, text_plain) >= 0.65 and len(text_plain.split()) < 40:
                continue

            norm = text_plain.lower().strip()
            if norm in seen_text:
                continue
            if h1_lower and SequenceMatcher(None, h1_lower, norm[:len(h1_lower)]).ratio() >= 0.85:
                continue
            seen_text.add(norm)

            para_html = clean_para_html(inner_html)
            para_html = re.sub(r'__PRESV_EMBED_START__.*?__PRESV_EMBED_END__', ' ', para_html, flags=re.S).strip()
            if para_html:
                blocks.append({"type": "p", "content": para_html, "plain": text_plain})

    return blocks


def process_plain(raw: str):
    raw = re.sub(r"&nbsp;", " ", raw, flags=re.I)
    raw = re.sub(r"&#\d+;|&[a-z]+;", " ", raw, flags=re.I)
    raw = re.sub(r"\u00a0", " ", raw)

    def _twitter_to_embed(m):
        url = m.group(0).strip()
        info = EmbedHelper.detect(url)
        if info["type"]:
            return f"\n__EMBED__{info['html']}__EMBED__\n"
        return " "

    raw = re.sub(
        r"https?://(?:www\.)?(?:twitter|x)\.com/\S+/status/\d+[^\s]*",
        _twitter_to_embed,
        raw,
        flags=re.I
    )

    if looks_html(raw):
        return process_html(raw)

    blocks = []
    lines = [x.strip() for x in raw.splitlines()]
    seen = set()
    h1_done = False

    for line in lines:
        if not line:
            continue

        emb_m = re.match(r"__EMBED__(.*?)__EMBED__", line, re.S)
        if emb_m:
            emb = emb_m.group(1).strip()
            if emb:
                blocks.append({"type": "embed", "content": emb})
            continue

        info = EmbedHelper.detect(line)
        if info["type"] in ("youtube", "twitter", "facebook"):
            blocks.append({"type": "embed", "content": info["html"]})
            continue

        if not h1_done and len(line.split()) >= 3:
            blocks.append({"type": "h1", "content": line})
            h1_done = True
            continue

        norm = line.lower()
        if norm in seen:
            continue
        seen.add(norm)

        if len(line.split()) >= 5:
            blocks.append({"type": "p", "content": html.escape(line), "plain": line})

    return blocks


def process_html(raw: str):
    raw = sanitize_wp_html(raw)
    if is_mixed_content(raw):
        raw = wrap_plain_paragraphs(raw)
    return parse_html_blocks(raw)


def blocks_to_plain_text(blocks):
    parts = []
    for b in blocks:
        if b["type"] in ("h1", "h2", "h3"):
            parts.append(b["content"])
        elif b["type"] == "p":
            parts.append(strip_tags_text(b["content"]))
    return normalize_ws("\n".join(parts))


def build_sections(blocks):
    h1 = ""
    intro = ""
    sections = []
    current_section = None

    for b in blocks:
        t = b["type"]
        if t == "h1" and not h1:
            h1 = b["content"]
        elif t == "p" and not intro:
            intro = strip_tags_text(b["content"])
        elif t == "h2":
            current_section = {"h2": b["content"], "subsections": []}
            sections.append(current_section)
        elif t == "h3":
            if current_section is None:
                current_section = {"h2": "", "subsections": []}
                sections.append(current_section)
            current_section["subsections"].append({"h3": b["content"], "content": []})
        else:
            if current_section is None:
                current_section = {"h2": "", "subsections": []}
                sections.append(current_section)

            if current_section["subsections"]:
                current_section["subsections"][-1]["content"].append(b)
            else:
                current_section["subsections"].append({"h3": "", "content": [b]})

    return h1, intro, sections


def fallback_seo_from_blocks(h1: str, intro: str, plain_text: str):
    words = re.findall(r"\b[\w'-]+\b", plain_text.lower())
    stop = {
        "this", "that", "with", "from", "have", "will", "were", "been", "about",
        "into", "their", "there", "them", "they", "your", "what", "when", "where",
        "which", "after", "before", "than", "then", "also", "more", "news", "article"
    }
    freq = {}
    for w in words:
        if len(w) < 4 or w in stop:
            continue
        freq[w] = freq.get(w, 0) + 1
    ranked = sorted(freq.items(), key=lambda x: (-x[1], x[0]))
    focus = " ".join([x[0] for x in ranked[:3]]).strip() or "wordpress article"

    seo_title = normalize_ws(h1)[:60] if h1 else "WordPress SEO Article"
    if len(seo_title) < 20 and intro:
        seo_title = normalize_ws((seo_title + " - " + intro)[:60])

    meta = intro or plain_text[:160]
    meta = normalize_ws(meta)
    if len(meta) > 160:
        cut = meta[:160]
        last_space = cut.rfind(" ")
        meta = cut[:last_space].rstrip(" .,:-") if last_space > 80 else cut.rstrip(" .,:-")
    if meta and not meta.endswith((".", "!", "?")):
        meta += "."

    return {
        "focus_keyphrase": focus[:60],
        "seo_title": seo_title[:60],
        "meta_description": meta[:160],
    }


def generate_ai_seo(api_key: str, h1: str, intro: str, plain_text: str):
    if not api_key.strip():
        return fallback_seo_from_blocks(h1, intro, plain_text)

    prompt = f"""Return ONLY valid JSON with keys:
{{
  "focus_keyphrase": "2-4 words",
  "seo_title": "max 60 chars",
  "meta_description": "max 160 chars"
}}

Rules:
- concise
- catchy
- WordPress / Yoast friendly
- no markdown
- no explanation

H1:
{h1[:200]}

Intro:
{intro[:400]}

Article:
{plain_text[:2500]}
"""
    try:
        resp = chat_completion(api_key.strip(), prompt)
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        data = parse_json(content)
        return {
            "focus_keyphrase": str(data.get("focus_keyphrase", "")).strip()[:60],
            "seo_title": str(data.get("seo_title", "")).strip()[:60],
            "meta_description": str(data.get("meta_description", "")).strip()[:160],
        }
    except Exception:
        return fallback_seo_from_blocks(h1, intro, plain_text)


def collect_detected_embeds(blocks):
    items = []
    for b in blocks:
        if b["type"] != "embed":
            continue
        info = EmbedHelper.detect(b["content"])
        if info["src"]:
            items.append(f"{info['label']}: {info['src']}")
        else:
            items.append("Embedded Media")
    return items


def build_output_html(h1: str, intro: str, struct):
    def esc(v):
        return html.escape(str(v or ""), quote=True)

    parts = []

    def _clean_chunk(text: str) -> str:
        text = re.sub(r'\bRead\s+More\b', '', text, flags=re.I).strip()
        text = re.sub(r'<button[^>]*>.*?</button>', '', text, flags=re.I | re.S).strip()
        text = re.sub(r'<a\b[^>]*class=["\'][^"\']*read[\-_]more[^"\']*["\'][^>]*>.*?</a>', '', text, flags=re.I | re.S).strip()
        return text

    H1_S = 'font-family:Arial,sans-serif;font-size:clamp(28px,5vw,42px);font-weight:800;color:#111111;margin:0 0 20px 0;line-height:1.2;text-align:center;'
    INTRO_S = 'font-size:clamp(16px,3.5vw,20px);line-height:1.8;color:#444444;margin:0 0 24px 0;font-style:italic;text-align:center;'
    H2_S = 'font-family:Arial,sans-serif;font-size:clamp(20px,4vw,30px);font-weight:800;color:#111111;margin:36px 0 14px 0;line-height:1.25;border-left:4px solid #2563eb;padding-left:12px;'
    H3_S = 'font-family:Arial,sans-serif;font-size:clamp(17px,3.2vw,24px);font-weight:700;color:#222222;margin:24px 0 10px 0;line-height:1.3;'
    P_S = 'font-size:clamp(15px,3vw,19px);line-height:1.85;color:#333333;margin:0 0 20px 0;'
    WRAP_OPEN = '<div style="max-width:800px;margin:0 auto;padding:0 16px;font-family:Georgia,\\'Times New Roman\\',serif;color:#222222;font-size:18px;line-height:1.8;">'
    WRAP_CLOSE = '</div>'

    embed_count = 0
    current_in_wrapper = False

    def _process_embed(embed_raw: str) -> str:
        nonlocal embed_count
        info = EmbedHelper.detect(embed_raw)

        if info["type"] in ("youtube", "twitter", "facebook"):
            embed_count += 1
            return "\n" + info["html"] + "\n"
        elif info["type"] == "generic":
            embed_count += 1
            return "\n" + info.get("html_classic", info["html"]) + "\n"
        elif embed_raw.strip().startswith("<"):
            embed_count += 1
            return f'\n<div style="margin:28px auto;">{embed_raw}</div>\n'
        elif embed_raw.startswith("http"):
            info2 = EmbedHelper.detect(embed_raw)
            if info2["type"]:
                embed_count += 1
                return "\n" + info2["html"] + "\n"
            return f'\n<p style="{P_S}"><a href="{html.escape(embed_raw)}">{html.escape(embed_raw)}</a></p>\n'
        return f'\n<div style="margin:28px auto;text-align:center;">{embed_raw}</div>\n'

    def _open_wrapper():
        nonlocal current_in_wrapper
        if not current_in_wrapper:
            parts.append(WRAP_OPEN)
            current_in_wrapper = True

    def _close_wrapper():
        nonlocal current_in_wrapper
        if current_in_wrapper:
            parts.append(WRAP_CLOSE)
            current_in_wrapper = False

    _open_wrapper()
    if h1:
        parts.append(f'<h1 style="{H1_S}">{esc(h1)}</h1>')
    if intro:
        parts.append(f'<p style="{INTRO_S}">{esc(intro)}</p>')

    for sec in struct:
        if sec.get("h2"):
            _open_wrapper()
            parts.append(f'<h2 style="{H2_S}">{esc(sec["h2"])}</h2>')

        for sub in sec.get("subsections", []):
            if sub.get("h3"):
                _open_wrapper()
                parts.append(f'<h3 style="{H3_S}">{esc(sub["h3"])}</h3>')

            for block in sub.get("content", []):
                if block["type"] == "embed":
                    _close_wrapper()
                    parts.append(_process_embed(block["content"]))
                elif block["type"] == "p":
                    _open_wrapper()
                    chunk = _clean_chunk(block["content"])
                    if chunk:
                        parts.append(f'<p style="{P_S}">{chunk}</p>')

    _close_wrapper()

    if embed_count:
        parts.insert(0, '<!-- WordPress SEO Studio Output: includes preserved embeds -->')

    return "\n".join(parts).strip()


@app.route("/", methods=["GET"])
def index():
    return render_template_string(INDEX_HTML)


@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json(silent=True) or {}
    raw = (data.get("article") or "").strip()
    api_key = (data.get("api_key") or "").strip()

    if not raw:
        return jsonify({"ok": False, "error": "Input is empty."}), 400

    try:
        has_wp_blocks = "<!-- wp:" in raw or "<!-- /wp:" in raw

        if has_wp_blocks:
            raw = strip_wp_block_comments(raw)
            blocks = process_html(raw)
        elif looks_html(raw):
            blocks = process_html(raw)
        else:
            blocks = process_plain(raw)

        h1, intro, struct = build_sections(blocks)
        plain_text = blocks_to_plain_text(blocks)
        seo = generate_ai_seo(api_key, h1, intro, plain_text)
        detected_embeds = collect_detected_embeds(blocks)
        seo_output = build_output_html(h1 or seo["seo_title"], intro, struct)

        return jsonify({
            "ok": True,
            "focus_keyphrase": seo["focus_keyphrase"],
            "seo_title": seo["seo_title"],
            "meta_description": seo["meta_description"],
            "detected_embeds": "\n".join(detected_embeds),
            "seo_output": seo_output,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
