import os
import re
import io
import json
import html as html_mod
import base64
from typing import Dict, List, Tuple

import requests
from bs4 import BeautifulSoup
from PIL import Image
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

TOGETHER_BASE_URL = "https://api.together.xyz/v1"
SEO_MODEL = os.getenv("TOGETHER_SEO_MODEL", "Qwen/Qwen2.5-7B-Instruct-Turbo")
VISION_MODEL = os.getenv("TOGETHER_VISION_MODEL", "Qwen/Qwen3-VL-8B-Instruct")
FORCED_TWITTER_USERNAME = os.getenv("FORCED_TWITTER_USERNAME", "").strip().lstrip("@")

API_CONNECT_TIMEOUT = 8
API_READ_TIMEOUT = 45


def get_headers(api_key: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def verify_api_key(api_key: str) -> Tuple[bool, str]:
    api_key = (api_key or "").strip()
    if not api_key:
        return False, "API key is empty."

    try:
        r = requests.get(
            f"{TOGETHER_BASE_URL}/models",
            headers=get_headers(api_key),
            timeout=(API_CONNECT_TIMEOUT, 15),
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


def chat_completion(
    api_key: str,
    model: str,
    messages,
    temperature: float = 0.2,
    top_p: float = 0.9,
    response_format=None,
    max_tokens: int = 240,
    timeout: int = API_READ_TIMEOUT,
):
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
    }
    if response_format:
        payload["response_format"] = response_format

    r = requests.post(
        f"{TOGETHER_BASE_URL}/chat/completions",
        headers=get_headers(api_key),
        json=payload,
        timeout=(API_CONNECT_TIMEOUT, timeout),
    )
    if r.status_code >= 400:
        try:
            data = r.json()
            detail = data.get("error", {}).get("message") or data.get("message") or r.text
        except Exception:
            detail = r.text
        raise RuntimeError(f"HTTP {r.status_code}: {detail}")
    return r.json()


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
                text = item.get("text") or item.get("content") or ""
                if text:
                    parts.append(str(text))
            elif item:
                parts.append(str(item))
        return "\n".join(parts).strip()
    return str(content or "").strip()


def parse_json(raw: str) -> dict:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("Empty model response")

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
    raise ValueError("Cannot parse JSON response") from last_err


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


def forced_public_twitter_url(tweet_id: str, fallback_url: str = "") -> str:
    tweet_id = str(tweet_id or "").strip()
    fallback_url = str(fallback_url or "").strip()
    if tweet_id and FORCED_TWITTER_USERNAME:
        return f"https://twitter.com/{FORCED_TWITTER_USERNAME}/status/{tweet_id}"
    if fallback_url:
        return fallback_url
    if tweet_id:
        return f"https://twitter.com/i/web/status/{tweet_id}"
    return ""


class EmbedHelper:
    YOUTUBE_PATTERNS = [
        r"youtube\.com/embed/([\w-]+)",
        r'youtube\.com/watch\?[^"\'\s]*v=([\w-]+)',
        r"youtu\.be/([\w-]+)",
        r"youtube\.com/v/([\w-]+)",
        r"youtube\.com/shorts/([\w-]+)",
    ]
    FACEBOOK_PATTERNS = [
        r'facebook\.com/[^\s"\'<>]+/videos/([\d]+)',
        r"facebook\.com/watch/?\?v=(\d+)",
        r"facebook\.com/video/watch\?v=(\d+)",
        r"facebook\.com/video\.php\?v=(\d+)",
        r"fb\.watch/([\w-]+)",
    ]

    @classmethod
    def decode_url(cls, value: str) -> str:
        return html_mod.unescape(str(value or "")).strip()

    @classmethod
    def extract_public_twitter_url(cls, raw: str) -> str:
        raw = cls.decode_url(raw)
        if not raw:
            return ""

        direct = re.search(
            r'https?://(?:www\.)?(?:twitter|x)\.com/([A-Za-z0-9_]+)/status(?:es)?/(\d+)',
            raw, re.I
        )
        if direct:
            return f"https://twitter.com/{direct.group(1)}/status/{direct.group(2)}"

        for key in ("url", "href"):
            m = re.search(rf'[?&]{key}=([^&"\']+)', raw, re.I)
            if m:
                decoded = cls.decode_url(m.group(1))
                direct2 = re.search(
                    r'https?://(?:www\.)?(?:twitter|x)\.com/([A-Za-z0-9_]+)/status(?:es)?/(\d+)',
                    decoded, re.I
                )
                if direct2:
                    return f"https://twitter.com/{direct2.group(1)}/status/{direct2.group(2)}"

        src_m = re.search(r'src=["\']([^"\']+)["\']', raw, re.I)
        if src_m:
            src = cls.decode_url(src_m.group(1))
            found = cls.extract_public_twitter_url(src)
            if found:
                return found

        return ""

    @classmethod
    def extract_tweet_id(cls, raw: str) -> str:
        raw = cls.decode_url(raw)
        if not raw:
            return ""
        patterns = [
            r'https?://(?:www\.)?(?:twitter|x)\.com/[A-Za-z0-9_]+/status(?:es)?/(\d+)',
            r'(?:twitter|x)\.com/i/web/status/(\d+)',
            r'data-tweet-id=["\'](\d+)["\']',
            r'[?&](?:id|tweetId)=(\d+)',
            r'https?://publish\.twitter\.com/\?url=.*?/status(?:es)?/(\d+)',
        ]
        for pat in patterns:
            m = re.search(pat, raw, re.I)
            if m:
                return m.group(1)
        src_m = re.search(r'src=["\']([^"\']+)["\']', raw, re.I)
        if src_m:
            src = cls.decode_url(src_m.group(1))
            for pat in patterns:
                m = re.search(pat, src, re.I)
                if m:
                    return m.group(1)
        return ""

    @classmethod
    def normalize_twitter_public_url(cls, raw: str) -> str:
        public_url = cls.extract_public_twitter_url(raw)
        if public_url:
            return public_url
        tweet_id = cls.extract_tweet_id(raw)
        if not tweet_id:
            return ""
        return forced_public_twitter_url(tweet_id)

    @classmethod
    def youtube_block(cls, vid_id: str) -> str:
        url = f"https://www.youtube.com/watch?v={vid_id}"
        safe = html_mod.escape(url, quote=True)
        return (
            f'<!-- wp:embed {{"url":"{safe}","type":"video","providerNameSlug":"youtube","responsive":true}} -->\n'
            f'<figure class="wp-block-embed is-type-video is-provider-youtube wp-block-embed-youtube">'
            f'<div class="wp-block-embed__wrapper">{safe}</div></figure>\n'
            f'<!-- /wp:embed -->'
        )

    @classmethod
    def twitter_block(cls, url: str) -> str:
        safe = html_mod.escape(url, quote=True)
        return (
            f'<!-- wp:embed {{"url":"{safe}","type":"rich","providerNameSlug":"twitter","responsive":true}} -->\n'
            f'<figure class="wp-block-embed is-type-rich is-provider-twitter wp-block-embed-twitter">'
            f'<div class="wp-block-embed__wrapper">{safe}</div></figure>\n'
            f'<!-- /wp:embed -->'
        )

    @classmethod
    def facebook_block(cls, url: str) -> str:
        safe = html_mod.escape(url, quote=True)
        return (
            f'<!-- wp:embed {{"url":"{safe}","type":"rich","providerNameSlug":"facebook","responsive":true}} -->\n'
            f'<figure class="wp-block-embed is-type-rich is-provider-facebook wp-block-embed-facebook">'
            f'<div class="wp-block-embed__wrapper">{safe}</div></figure>\n'
            f'<!-- /wp:embed -->'
        )

    @classmethod
    def detect(cls, raw: str) -> Dict[str, str]:
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
                    "html": cls.youtube_block(vid_id),
                    "html_classic": watch_url,
                    "src": watch_url,
                }

        tw_url = cls.normalize_twitter_public_url(raw)
        if tw_url:
            tweet_id = cls.extract_tweet_id(raw)
            return {
                "type": "twitter",
                "icon": "🐦",
                "label": f"Twitter/X Post [ID: {tweet_id}]" if tweet_id else "Twitter/X Post",
                "html": cls.twitter_block(tw_url),
                "html_classic": tw_url,
                "src": tw_url,
            }

        for pat in cls.FACEBOOK_PATTERNS:
            m = re.search(pat, raw, re.I)
            if m:
                fb_url_m = re.search(r'https?://(?:www\.)?facebook\.com/[^\s"\'<>]+', raw, re.I)
                if fb_url_m:
                    fb_url = fb_url_m.group(0).rstrip('/"\'')
                    return {
                        "type": "facebook",
                        "icon": "📘",
                        "label": "Facebook Video",
                        "html": cls.facebook_block(fb_url),
                        "html_classic": fb_url,
                        "src": fb_url,
                    }

        src_m = re.search(r'src=["\'](https?://[^"\'>\s]+)["\']', raw, re.I)
        if src_m and "<iframe" in raw_lower:
            src = cls.decode_url(src_m.group(1))
            yt = re.search(r'(?:youtube\.com/embed/|youtu\.be/|youtube\.com/watch\?v=)([\w-]+)', src, re.I)
            if yt:
                vid_id = yt.group(1)
                watch_url = f"https://www.youtube.com/watch?v={vid_id}"
                return {
                    "type": "youtube",
                    "icon": "▶",
                    "label": f"YouTube Video [ID: {vid_id}]",
                    "html": cls.youtube_block(vid_id),
                    "html_classic": watch_url,
                    "src": watch_url,
                }
            tw_url = cls.normalize_twitter_public_url(src)
            if tw_url:
                tweet_id = cls.extract_tweet_id(src)
                return {
                    "type": "twitter",
                    "icon": "🐦",
                    "label": f"Twitter/X Post [ID: {tweet_id}]",
                    "html": cls.twitter_block(tw_url),
                    "html_classic": tw_url,
                    "src": tw_url,
                }
            return {
                "type": "generic",
                "icon": "▶",
                "label": "Embedded Media",
                "html": src,
                "html_classic": src,
                "src": src,
            }

        return {"type": "", "icon": "", "label": "", "html": raw, "html_classic": raw, "src": ""}


def looks_html(text: str) -> bool:
    s = (text or "").strip().lower()
    html_tokens = (
        "<html", "<body", "<div", "<section", "<article", "<p", "<h1", "<h2",
        "<h3", "<iframe", "<figure", "<blockquote", "<video", "<!-- wp:"
    )
    return any(token in s for token in html_tokens)


def strip_wp_block_comments_preserve_embeds(raw: str) -> str:
    raw = str(raw or "")

    def save_wp_embed(match):
        block_json = match.group(1) or ""
        inner_html = (match.group(2) or "").strip()

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

        return f"\n{inner_html}\n"

    raw = re.sub(
        r'<!--\s*wp:embed\s*(\{[^}]*\}|\S*)\s*-->(.*?)<!--\s*/wp:embed\s*-->',
        save_wp_embed,
        raw,
        flags=re.I | re.S,
    )

    def save_wp_video(match):
        inner_html = (match.group(1) or "").strip()
        src_m = re.search(r'src=["\']([^"\']+)["\']', inner_html, re.I)
        url_m = re.search(r'"url"\s*:\s*"([^"]+)"', match.group(0))
        embed_url = (url_m.group(1) if url_m else "") or (src_m.group(1) if src_m else "")
        if embed_url:
            info = EmbedHelper.detect(embed_url)
            if info["type"]:
                return f"\n__PRESV_EMBED_START__{info['html']}__PRESV_EMBED_END__\n"
        return f"\n{inner_html}\n"

    raw = re.sub(
        r'<!--\s*wp:video[^-]*-->(.*?)<!--\s*/wp:video\s*-->',
        save_wp_video,
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

    def convert_bare_video_url(match):
        url = match.group(0).strip()
        info = EmbedHelper.detect(url)
        if info["type"]:
            return f"\n__PRESV_EMBED_START__{info['html']}__PRESV_EMBED_END__\n"
        return url

    raw = re.sub(video_url_pat, convert_bare_video_url, raw, flags=re.I)

    def fix_paragraph_block(match):
        inner = (match.group(1) or "").strip()
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


def sanitize_html(raw: str) -> str:
    raw = str(raw or "")
    raw = re.sub(r"<script\b.*?</script>", "", raw, flags=re.I | re.S)
    raw = re.sub(r"<style\b.*?</style>", "", raw, flags=re.I | re.S)
    raw = re.sub(r"<noscript\b.*?</noscript>", "", raw, flags=re.I | re.S)
    raw = re.sub(r"&nbsp;", " ", raw, flags=re.I)
    raw = raw.replace("\u00a0", " ")
    return raw.strip()


def wrap_plain_paragraphs(text: str) -> str:
    blocks = re.split(r"\n[ \t]*\n", text)
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

        result.append(f"<p>{block}</p>")

    return "\n\n".join(result).strip()


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
        "video", "embed", "from", "were", "been", "being", "also", "more"
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

    try:
        resp = chat_completion(
            api_key=api_key,
            model=SEO_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            top_p=0.9,
            response_format={"type": "json_object"},
            max_tokens=220,
            timeout=35,
        )
        parsed = parse_json(extract_content(resp))
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

    def restore_embed_marker(match):
        inner = (match.group(1) or "").strip()
        return "\n" + inner + "\n"

    content = re.sub(
        r"__PRESV_EMBED_START__(.*?)__PRESV_EMBED_END__",
        restore_embed_marker,
        content,
        flags=re.S,
    )

    parts.append(content)
    output = "\n\n".join([p for p in parts if p.strip()])
    output = re.sub(r"\n{3,}", "\n\n", output).strip()
    return output


def process_article_input(raw: str) -> Dict[str, str]:
    raw = str(raw or "").strip()
    if not raw:
        raise ValueError("Article input is empty.")

    has_wp_blocks = "<!-- wp:" in raw or "<!-- /wp:" in raw
    working = raw
    title_hint = ""

    if has_wp_blocks:
        working = strip_wp_block_comments_preserve_embeds(working)

    if looks_html(working):
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
    plain = plain.replace("\u00a0", " ")

    video_url_pat = (
        r'https?://(?:www\.)?(?:youtube\.com/watch\?[^\s<"\']+|'
        r'youtu\.be/[\w\-]+[^\s<"\']*|'
        r'youtube\.com/shorts/[\w\-]+[^\s<"\']*|'
        r'(?:twitter|x)\.com/\S+/status/\d+[^\s<"\']*|'
        r'facebook\.com/[^\s<"\']+/videos/[^\s<"\']+|'
        r'fb\.watch/[\w\-]+[^\s<"\']*)'
    )

    def convert_url_to_embed(match):
        url = match.group(0).strip()
        info = EmbedHelper.detect(url)
        if info["type"]:
            return f"\n__PRESV_EMBED_START__{info['html']}__PRESV_EMBED_END__\n"
        return url

    plain = re.sub(video_url_pat, convert_url_to_embed, plain, flags=re.I)

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


def decode_image_data_url(data_url: str) -> Image.Image:
    if not data_url or not data_url.startswith("data:image/"):
        raise ValueError("Invalid image data")
    header, encoded = data_url.split(",", 1)
    binary = base64.b64decode(encoded)
    img = Image.open(io.BytesIO(binary)).convert("RGB")
    return img


def image_to_data_url_jpeg(img: Image.Image, max_side: int = 1280, quality: int = 88) -> str:
    img = img.convert("RGB")
    w, h = img.size
    longest = max(w, h)
    if longest > max_side:
        scale = max_side / float(longest)
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)

    bio = io.BytesIO()
    img.save(bio, format="JPEG", quality=quality, optimize=True)
    b64 = base64.b64encode(bio.getvalue()).decode()
    return f"data:image/jpeg;base64,{b64}"


def fallback_image_seo_fields(scene_notes: str = "") -> Dict[str, str]:
    scene_notes = normalize_spaces(scene_notes)
    if scene_notes:
        title = clamp_text(scene_notes.title(), 60)
        alt_text = clamp_text(f"{scene_notes} featured image", 125)
        caption = clamp_text(f"Featured image showing {scene_notes.lower()} in the article.", 160)
    else:
        title = "Featured Image"
        alt_text = "Featured image for the article"
        caption = "Featured image used for the article."
    return {
        "alt_text": alt_text,
        "img_title": title,
        "caption": caption,
    }


def generate_ai_image_seo(api_key: str, image_data_url: str, scene_notes: str = "") -> Dict[str, str]:
    api_key = (api_key or "").strip()
    if not api_key:
        return fallback_image_seo_fields(scene_notes)

    scene_hint = f'\n\nContext/keyword hint from editor: "{scene_notes.strip()}"' if scene_notes.strip() else ""
    prompt = f"""You are a WordPress SEO specialist writing metadata for a FEATURED IMAGE.

Look at the image carefully and return ONLY valid JSON with exactly these 3 keys:

{{
  "alt_text": "...",
  "img_title": "...",
  "caption": "..."
}}

RULES:
alt_text: 8-15 words describing what is visually in the image
img_title: 4-10 words, Title Case
caption: ONE complete sentence 15-30 words, journalistic style

Output ONLY the JSON object. No markdown, no explanation.{scene_hint}
"""

    try:
        resp = chat_completion(
            api_key=api_key,
            model=VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_data_url}},
                    ],
                }
            ],
            temperature=0.15,
            top_p=0.85,
            response_format={"type": "json_object"},
            max_tokens=180,
            timeout=90,
        )
        raw_data = parse_json(extract_content(resp))
        alt_text = clamp_text(str(raw_data.get("alt_text", "")).strip(), 125)
        img_title = clamp_text(str(raw_data.get("img_title", "")).strip(), 80)
        caption = clamp_text(str(raw_data.get("caption", "")).strip(), 180)

        if len(alt_text) < 10 or len(img_title) < 5 or len(caption) < 15:
            return fallback_image_seo_fields(scene_notes)

        return {
            "alt_text": alt_text,
            "img_title": img_title,
            "caption": caption,
        }
    except Exception:
        return fallback_image_seo_fields(scene_notes)


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/verify-key")
def api_verify_key():
    data = request.get_json(silent=True) or {}
    ok, message = verify_api_key(data.get("api_key", ""))
    return jsonify({"ok": ok, "message": message})


@app.post("/api/generate-seo")
def api_generate_seo():
    data = request.get_json(silent=True) or {}
    raw = (data.get("article") or "").strip()
    api_key = (data.get("api_key") or "").strip()

    if not raw:
        return jsonify({"ok": False, "error": "Article input is empty."}), 400

    try:
        processed = process_article_input(raw)
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


@app.post("/api/generate-image-seo")
def api_generate_image_seo():
    data = request.get_json(silent=True) or {}
    api_key = (data.get("api_key") or "").strip()
    image_data_url = (data.get("image_data_url") or "").strip()
    scene_notes = (data.get("scene_notes") or "").strip()

    if not image_data_url:
        return jsonify({"ok": False, "error": "Image is missing."}), 400

    try:
        img = decode_image_data_url(image_data_url)
        resized_data_url = image_to_data_url_jpeg(img, max_side=1280, quality=88)
        result = generate_ai_image_seo(api_key, resized_data_url, scene_notes)
        return jsonify({"ok": True, **result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
