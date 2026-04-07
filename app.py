import base64
import html as html_mod
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
app.config['MAX_CONTENT_LENGTH'] = 12 * 1024 * 1024

TOGETHER_BASE_URL = "https://api.together.xyz/v1"
SEO_MODEL = os.getenv("TOGETHER_SEO_MODEL", "Qwen/Qwen2.5-7B-Instruct-Turbo")
VISION_MODEL = os.getenv("TOGETHER_VISION_MODEL", "Qwen/Qwen2.5-VL-72B-Instruct")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
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
    candidates = [raw]
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    if cleaned != raw:
        candidates.append(cleaned)
    match = re.search(r"\{.*\}", cleaned, re.S)
    if match:
        candidates.append(match.group(0))
    last_error = None
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except Exception as exc:
            last_error = exc
    raise ValueError("Could not parse AI JSON") from last_error


def chat_completion(api_key: str, model: str, messages: list, *, temperature: float = 0.2,
                    top_p: float = 0.9, timeout: Tuple[int, int] = (8, 60),
                    response_format: Optional[dict] = None, max_tokens: Optional[int] = None) -> dict:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "top_p": top_p,
    }
    if response_format:
        payload["response_format"] = response_format
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    response = requests.post(
        f"{TOGETHER_BASE_URL}/chat/completions",
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def verify_key(api_key: str) -> bool:
    response = requests.get(
        f"{TOGETHER_BASE_URL}/models",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=(8, 20),
    )
    response.raise_for_status()
    return True


def file_allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ---------------------------------------------------------------------------
# Embed handling (adapted from original desktop logic)
# ---------------------------------------------------------------------------
class EmbedHelper:
    YOUTUBE_PATTERNS = [
        r"youtube\.com/embed/([\w-]+)",
        r"youtube\.com/watch\?[^\"'\s]*v=([\w-]+)",
        r"youtu\.be/([\w-]+)",
        r"youtube\.com/v/([\w-]+)",
        r"youtube\.com/shorts/([\w-]+)",
    ]
    FACEBOOK_PATTERNS = [
        r'facebook\.com/[^\s\"\'<>]+/videos/(\d+)',
        r"facebook\.com/watch/?\?v=(\d+)",
        r"facebook\.com/video/watch\?v=(\d+)",
        r"facebook\.com/video\.php\?v=(\d+)",
        r"fb\.watch/([\w-]+)",
    ]

    @classmethod
    def _decode_url(cls, value: str) -> str:
        return html_mod.unescape(str(value or "")).strip()

    @classmethod
    def _youtube_url(cls, vid_id: str) -> str:
        return f"https://www.youtube.com/watch?v={vid_id}"

    @classmethod
    def _twitter_url(cls, username: str, tweet_id: str) -> str:
        return f"https://twitter.com/{username}/status/{tweet_id}"

    @classmethod
    def _twitter_generic_url(cls, tweet_id: str) -> str:
        return f"https://twitter.com/i/web/status/{tweet_id}"

    @classmethod
    def _wp_embed_markup(cls, url: str, provider_slug: str, embed_type: str = "rich") -> str:
        safe = html_mod.escape(url, quote=True)
        return (
            f'<!-- wp:embed {{"url":"{safe}","type":"{embed_type}","providerNameSlug":"{provider_slug}","responsive":true}} -->\n'
            f'<figure class="wp-block-embed is-type-{embed_type} is-provider-{provider_slug} wp-block-embed-{provider_slug}">'
            f'<div class="wp-block-embed__wrapper">{safe}</div></figure>\n'
            f'<!-- /wp:embed -->'
        )

    @classmethod
    def detect(cls, raw: str) -> Dict[str, str]:
        raw = cls._decode_url(raw)

        for pat in cls.YOUTUBE_PATTERNS:
            match = re.search(pat, raw, re.I)
            if match:
                vid_id = match.group(1).split("&")[0].split("?")[0].strip()
                url = cls._youtube_url(vid_id)
                return {
                    "type": "youtube",
                    "icon": "▶",
                    "label": f"YouTube Video [{vid_id}]",
                    "html": cls._wp_embed_markup(url, "youtube", "video"),
                    "html_classic": url,
                    "src": url,
                }

        direct = re.search(
            r'https?://(?:www\.)?(?:twitter|x)\.com/([A-Za-z0-9_]+)/status(?:es)?/(\d+)',
            raw,
            re.I,
        )
        if direct:
            url = cls._twitter_url(direct.group(1), direct.group(2))
            return {
                "type": "twitter",
                "icon": "🐦",
                "label": f"Twitter/X Post [{direct.group(2)}]",
                "html": cls._wp_embed_markup(url, "twitter", "rich"),
                "html_classic": url,
                "src": url,
            }

        iweb = re.search(r'https?://(?:www\.)?twitter\.com/i/web/status/(\d+)', raw, re.I)
        if iweb:
            tweet_id = iweb.group(1)
            url = cls._twitter_generic_url(tweet_id)
            return {
                "type": "twitter",
                "icon": "🐦",
                "label": f"Twitter/X Post [{tweet_id}]",
                "html": cls._wp_embed_markup(url, "twitter", "rich"),
                "html_classic": url,
                "src": url,
            }

        for pat in cls.FACEBOOK_PATTERNS:
            match = re.search(pat, raw, re.I)
            if match:
                fb_url_match = re.search(r'https?://(?:www\.)?facebook\.com/[^\s\"\'<>]+', raw, re.I)
                fb_url = fb_url_match.group(0).rstrip('/"\'') if fb_url_match else raw
                return {
                    "type": "facebook",
                    "icon": "📘",
                    "label": "Facebook Video",
                    "html": cls._wp_embed_markup(fb_url, "facebook", "rich"),
                    "html_classic": fb_url,
                    "src": fb_url,
                }

        src_m = re.search(r'src=["\'](https?://[^"\'>\s]+)["\']', raw, re.I)
        if src_m:
            src = cls._decode_url(src_m.group(1))
            nested = cls.detect(src)
            if nested.get("type"):
                return nested
            return {
                "type": "generic",
                "icon": "▶",
                "label": "Embedded Media",
                "html": src,
                "html_classic": src,
                "src": src,
            }

        bare = re.search(r'https?://[^\s<"\']+', raw, re.I)
        if bare:
            src = bare.group(0)
            nested = cls.detect(src) if src != raw else {"type": "", "src": ""}
            if nested.get("type"):
                return nested
            return {
                "type": "generic",
                "icon": "▶",
                "label": "Embedded URL",
                "html": src,
                "html_classic": src,
                "src": src,
            }

        return {"type": "", "icon": "", "label": "", "html": "", "html_classic": "", "src": ""}


def rewrite_twitter_embed_urls(text: str) -> str:
    text = str(text or "")

    def _replace_platform(match):
        url = html_mod.unescape(match.group(0))
        tweet_id = re.search(r'[?&](?:id|tweetId)=(\d+)', url, re.I)
        if tweet_id:
            return f"https://twitter.com/i/web/status/{tweet_id.group(1)}"
        return url

    text = re.sub(r'https?://platform\.twitter\.com/embed/Tweet\.html\?[^"\'\s<]+', _replace_platform, text, flags=re.I)
    return text


def strip_wp_block_comments(raw: str) -> str:
    raw = str(raw or "")

    def _save_wp_embed(match):
        block_json = match.group(1) or ""
        inner_html = (match.group(2) or "").strip()
        url_match = re.search(r'"url"\s*:\s*"([^"]+)"', block_json)
        embed_url = url_match.group(1) if url_match else ""

        if not embed_url:
            wrapper_match = re.search(
                r'<div[^>]*class=["\'][^"\']*wp-block-embed__wrapper[^"\']*["\'][^>]*>\s*(https?://[^\s<]+)',
                inner_html,
                re.I | re.S,
            )
            if wrapper_match:
                embed_url = wrapper_match.group(1).strip()

        if not embed_url:
            any_url = re.search(r'(https?://[^\s<"\']{10,})', inner_html)
            if any_url:
                embed_url = any_url.group(1).strip()

        if embed_url:
            info = EmbedHelper.detect(embed_url)
            if info.get("type"):
                return f"\n__PRESV_EMBED_START__{info['html']}__PRESV_EMBED_END__\n"
            return f"\n__PRESV_EMBED_START__{inner_html}__PRESV_EMBED_END__\n"

        return f"\n{inner_html}\n"

    raw = re.sub(
        r'<!--\s*wp:embed\s*(\{[^}]*\}|\S*)\s*-->(.*?)<!--\s*/wp:embed\s*-->',
        _save_wp_embed,
        raw,
        flags=re.I | re.S,
    )

    def _save_wp_video(match):
        inner_html = (match.group(1) or "").strip()
        src_match = re.search(r'src=["\']([^"\']+)["\']', inner_html, re.I)
        url_match = re.search(r'"url"\s*:\s*"([^"]+)"', match.group(0))
        embed_url = (url_match.group(1) if url_match else "") or (src_match.group(1) if src_match else "")
        if embed_url:
            info = EmbedHelper.detect(embed_url)
            if info.get("type"):
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

    def _convert_bare_video_url(match):
        url = match.group(0).strip()
        info = EmbedHelper.detect(url)
        if info.get("type"):
            return f"\n__PRESV_EMBED_START__{info['html']}__PRESV_EMBED_END__\n"
        return url

    raw = re.sub(video_url_pat, _convert_bare_video_url, raw, flags=re.I)
    raw = re.sub(r'<!--\s*/?\s*wp:[^>]*-->', '', raw, flags=re.I | re.S)
    raw = re.sub(r'\n{3,}', '\n\n', raw)
    return raw.strip()


def extract_embed_markers(raw: str) -> List[str]:
    return re.findall(r'__PRESV_EMBED_START__(.*?)__PRESV_EMBED_END__', raw or '', flags=re.S)


def sanitize_html(raw: str) -> str:
    raw = str(raw or '')
    raw = re.sub(r'<script\b.*?</script>', '', raw, flags=re.I | re.S)
    raw = re.sub(r'<style\b.*?</style>', '', raw, flags=re.I | re.S)
    raw = re.sub(r'<noscript\b.*?</noscript>', '', raw, flags=re.I | re.S)
    return raw.strip()


def looks_html(text: str) -> bool:
    s = (text or '').strip().lower()
    html_tokens = (
        '<html', '<body', '<div', '<section', '<article', '<p', '<h1', '<h2',
        '<h3', '<iframe', '<figure', '<blockquote', '<video', '<!-- wp:'
    )
    return any(token in s for token in html_tokens)


def html_to_text_preserving_embeds(raw_html: str) -> str:
    temp = re.sub(r'__PRESV_EMBED_START__(.*?)__PRESV_EMBED_END__', ' ', raw_html, flags=re.S)
    soup = BeautifulSoup(temp, 'html.parser')
    for tag in soup(['script', 'style', 'noscript']):
        tag.decompose()
    text = soup.get_text('\n')
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return '\n'.join(lines).strip()


def extract_title_from_html(raw_html: str) -> str:
    text = raw_html or ''
    patterns = [
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\'>]*)["\']',
        r'<meta[^>]+content=["\']([^"\'>]*)["\'][^>]+property=["\']og:title["\']',
        r'<title[^>]*>(.*?)</title>',
        r'<h1[^>]*>(.*?)</h1>',
    ]
    for pat in patterns:
        match = re.search(pat, text, re.I | re.S)
        if match:
            cleaned = re.sub(r'<[^>]+>', ' ', match.group(1))
            cleaned = html_mod.unescape(cleaned)
            cleaned = normalize_spaces(cleaned)
            cleaned = re.sub(r'\s+[|\-–—]\s+.*$', '', cleaned).strip()
            if cleaned:
                return cleaned
    return ''


def guess_title_from_text(text: str) -> str:
    lines = [normalize_spaces(x) for x in str(text or '').splitlines() if normalize_spaces(x)]
    if not lines:
        return 'Untitled Article'
    first = lines[0]
    return clamp_text(first, 90)


def build_intro(text: str) -> str:
    text = normalize_spaces(text)
    if not text:
        return ''
    parts = re.split(r'(?<=[.!?])\s+', text)
    intro = ' '.join(parts[:2]).strip()
    return clamp_text(intro, 220)


def derive_focus_keyphrase(text: str) -> str:
    words = re.findall(r"\b[a-zA-Z0-9\u1780-\u17ff][a-zA-Z0-9\u1780-\u17ff'-]{2,}\b", text.lower())
    stop = {
        'this', 'that', 'with', 'from', 'your', 'have', 'will', 'about', 'into',
        'after', 'before', 'their', 'there', 'they', 'them', 'what', 'when',
        'where', 'which', 'while', 'would', 'could', 'should', 'article', 'video',
        'embed', 'image', 'title', 'caption'
    }
    freq = {}
    for word in words:
        if word in stop:
            continue
        freq[word] = freq.get(word, 0) + 1
    ranked = sorted(freq.items(), key=lambda x: (-x[1], x[0]))
    phrase = ' '.join([item[0] for item in ranked[:3]]).strip()
    return phrase[:60] or 'wordpress article'


def generate_fallback_seo(text: str, title_hint: str = '') -> Dict[str, str]:
    title_source = title_hint.strip() or guess_title_from_text(text)
    seo_title = clamp_text(title_source, 60)
    if len(seo_title) < 18:
        seo_title = clamp_text(f"{title_source} | SEO Article", 60)

    meta = build_intro(text)
    if not meta:
        meta = 'Read the full article with key details, summaries, and embedded media.'
    meta = clamp_text(meta, 160)

    return {
        'focus_keyphrase': derive_focus_keyphrase(text),
        'seo_title': seo_title,
        'meta_description': meta,
    }


def generate_ai_seo(api_key: str, plain_text: str, title_hint: str = '') -> Dict[str, str]:
    api_key = (api_key or '').strip()
    if not api_key:
        return generate_fallback_seo(plain_text, title_hint)

    prompt = f'''Return ONLY valid JSON:\n{{\n  "focus_keyphrase": "2-4 word keyphrase",\n  "seo_title": "max 60 chars",\n  "meta_description": "max 160 chars"\n}}\n\nRules:\n- concise\n- search-friendly\n- no markdown\n- no explanation\n\nTITLE HINT:\n{title_hint[:180]}\n\nARTICLE:\n{plain_text[:3500]}'''
    try:
        resp = chat_completion(
            api_key,
            SEO_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            top_p=0.9,
            timeout=(8, 45),
            response_format={"type": "json_object"},
            max_tokens=220,
        )
        parsed = parse_json(extract_content(resp))
        focus = clamp_text(str(parsed.get('focus_keyphrase', '')).strip(), 60)
        seo_title = clamp_text(str(parsed.get('seo_title', '')).strip(), 60)
        meta = clamp_text(str(parsed.get('meta_description', '')).strip(), 160)
        if not focus or not seo_title or not meta:
            return generate_fallback_seo(plain_text, title_hint)
        return {
            'focus_keyphrase': focus,
            'seo_title': seo_title,
            'meta_description': meta,
        }
    except Exception:
        return generate_fallback_seo(plain_text, title_hint)


def build_output_html(title: str, intro: str, cleaned_html: str) -> str:
    parts = []
    if title:
        parts.append(f"<h1>{html_mod.escape(title)}</h1>")
    if intro:
        parts.append(f"<p><em>{html_mod.escape(intro)}</em></p>")

    content = cleaned_html.strip()

    def _restore_embed(match):
        return '\n' + (match.group(1) or '').strip() + '\n'

    content = re.sub(r'__PRESV_EMBED_START__(.*?)__PRESV_EMBED_END__', _restore_embed, content, flags=re.S)
    content = rewrite_twitter_embed_urls(content)
    parts.append(content)
    return re.sub(r'\n{3,}', '\n\n', '\n\n'.join([p for p in parts if p.strip()])).strip()


def structure_info_from_html(cleaned_html: str) -> str:
    h1_count = len(re.findall(r'<h1\b', cleaned_html, re.I))
    h2_count = len(re.findall(r'<h2\b', cleaned_html, re.I))
    h3_count = len(re.findall(r'<h3\b', cleaned_html, re.I))
    p_count = len(re.findall(r'<p\b', cleaned_html, re.I))
    embed_count = len(extract_embed_markers(cleaned_html))
    return (
        f"H1: {h1_count}\n"
        f"H2: {h2_count}\n"
        f"H3: {h3_count}\n"
        f"Paragraphs: {p_count}\n"
        f"Embeds/Videos: {embed_count}"
    )


def wrap_plain_paragraphs(text: str) -> str:
    blocks = re.split(r'\n\s*\n', text)
    result = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        if block.startswith('__PRESV_EMBED_START__'):
            result.append(block)
        elif block.startswith('<'):
            result.append(block)
        else:
            safe = html_mod.escape(block).replace('\n', '<br>')
            result.append(f'<p>{safe}</p>')
    return '\n\n'.join(result).strip()


def process_input(raw: str) -> Dict[str, str]:
    raw = str(raw or '').strip()
    if not raw:
        raise ValueError('Article input is empty.')

    has_wp_blocks = '<!-- wp:' in raw or '<!-- /wp:' in raw
    working = strip_wp_block_comments(raw) if has_wp_blocks else raw

    if looks_html(working):
        working = sanitize_html(working)
        if not re.search(r'<p\b', working, re.I) and '__PRESV_EMBED_START__' in working:
            working = wrap_plain_paragraphs(working)
        plain_text = html_to_text_preserving_embeds(working)
        title_hint = extract_title_from_html(raw) or extract_title_from_html(working) or guess_title_from_text(plain_text)
        intro = build_intro(plain_text)
        embeds = extract_embed_markers(working)
        return {
            'title_hint': title_hint,
            'plain_text': plain_text,
            'intro': intro,
            'cleaned_html': working,
            'embeds': '\n'.join([normalize_spaces(re.sub(r'<[^>]+>', ' ', x))[:220] for x in embeds]) if embeds else '',
            'structure': structure_info_from_html(working),
        }

    plain = raw
    video_url_pat = (
        r'https?://(?:www\.)?(?:youtube\.com/watch\?[^\s<"\']+|'
        r'youtu\.be/[\w\-]+[^\s<"\']*|'
        r'youtube\.com/shorts/[\w\-]+[^\s<"\']*|'
        r'(?:twitter|x)\.com/\S+/status/\d+[^\s<"\']*|'
        r'facebook\.com/[^\s<"\']+/videos/[^\s<"\']+|'
        r'fb\.watch/[\w\-]+[^\s<"\']*)'
    )

    def _convert_url(match):
        url = match.group(0).strip()
        info = EmbedHelper.detect(url)
        if info.get('type'):
            return f"\n__PRESV_EMBED_START__{info['html']}__PRESV_EMBED_END__\n"
        return url

    plain = re.sub(video_url_pat, _convert_url, plain, flags=re.I)
    cleaned_html = wrap_plain_paragraphs(plain)
    plain_text = re.sub(r'__PRESV_EMBED_START__.*?__PRESV_EMBED_END__', ' ', plain, flags=re.S)
    plain_text = normalize_spaces(plain_text)
    title_hint = guess_title_from_text(plain_text)
    intro = build_intro(plain_text)
    embeds = extract_embed_markers(cleaned_html)
    return {
        'title_hint': title_hint,
        'plain_text': plain_text,
        'intro': intro,
        'cleaned_html': cleaned_html,
        'embeds': '\n'.join([normalize_spaces(re.sub(r'<[^>]+>', ' ', x))[:220] for x in embeds]) if embeds else '',
        'structure': structure_info_from_html(cleaned_html),
    }


# ---------------------------------------------------------------------------
# Image SEO
# ---------------------------------------------------------------------------
def prepare_image_bytes(file_storage) -> Tuple[str, str, Image.Image]:
    image = Image.open(file_storage.stream).convert('RGB')
    width, height = image.size
    max_side = 1280
    if max(width, height) > max_side:
        scale = max_side / max(width, height)
        image = image.resize((int(width * scale), int(height * scale)), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, 'JPEG', quality=88, optimize=True)
    b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    return b64, 'image/jpeg', image


def fallback_image_seo_fields(scene_notes: str, filename: str) -> Dict[str, str]:
    base = os.path.splitext(os.path.basename(filename or ''))[0]
    tokens = re.findall(r"[A-Za-z0-9\u1780-\u17ff']+", base.replace('_', ' ').replace('-', ' '))
    stop = {'image', 'photo', 'news', 'report', 'article', 'homepage', 'banner', 'webp', 'jpg', 'jpeg', 'png', 'crop', 'img'}
    uniq = []
    seen = set()
    for t in tokens:
        tl = t.lower()
        if tl in seen or tl in stop:
            continue
        seen.add(tl)
        uniq.append(t)

    proper = [t for t in uniq if t[:1].isupper() or t.isupper()]
    subject = ' '.join(proper[:2]).strip() or ' '.join(uniq[:4]).strip() or scene_notes.strip() or 'News Photo'

    alt_text = clamp_text(f"{subject} shown in a news photo", 90)
    img_title = clamp_text(subject.title() if subject else 'News Photo', 90)
    caption = clamp_text(f"{subject} is shown in an image related to the article.", 180)
    return {
        'alt_text': alt_text or 'news photo related to the article',
        'img_title': img_title or 'News Photo',
        'caption': caption or 'News photo related to the article.',
    }


def generate_image_seo(api_key: str, file_storage, scene_notes: str) -> Dict[str, str]:
    scene_notes = (scene_notes or '').strip()
    filename = getattr(file_storage, 'filename', 'image') or 'image'
    if not api_key:
        return fallback_image_seo_fields(scene_notes, filename)

    try:
        b64, media_type, _ = prepare_image_bytes(file_storage)
        data_url = f"data:{media_type};base64,{b64}"
        scene_hint = f'\n\nContext/keyword hint from editor: "{scene_notes}"' if scene_notes else ''
        prompt = f'''You are a WordPress SEO specialist writing metadata for a FEATURED IMAGE.\n\nLook at the image carefully and return ONLY valid JSON with exactly these 3 keys:\n\n{{\n  "alt_text": "...",\n  "img_title": "...",\n  "caption": "..."\n}}\n\nRULES:\nalt_text: 8-15 words describing what is visually in the image\nimg_title: 4-10 words, Title Case\ncaption: ONE complete sentence 15-30 words, journalistic style\n\nOutput ONLY the JSON object. No markdown, no explanation.{scene_hint}'''
        resp = chat_completion(
            api_key,
            VISION_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }],
            temperature=0.15,
            top_p=0.85,
            timeout=(8, 90),
            response_format={"type": "json_object"},
            max_tokens=220,
        )
        parsed = parse_json(extract_content(resp))
        alt_text = clamp_text(str(parsed.get('alt_text', '')).strip(), 90)
        img_title = clamp_text(str(parsed.get('img_title', '')).strip(), 90)
        caption = clamp_text(str(parsed.get('caption', '')).strip(), 180)
        if len(alt_text) < 8 or len(img_title) < 4 or len(caption) < 12:
            return fallback_image_seo_fields(scene_notes, filename)
        return {
            'alt_text': alt_text,
            'img_title': img_title,
            'caption': caption if re.search(r'[.!?]$', caption) else caption + '.',
        }
    except Exception:
        return fallback_image_seo_fields(scene_notes, filename)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get('/')
def index():
    return render_template('index.html')


@app.post('/api/verify-key')
def api_verify_key():
    payload = request.get_json(silent=True) or {}
    api_key = (payload.get('api_key') or '').strip()
    if not api_key:
        return jsonify({'ok': False, 'error': 'API key is empty.'}), 400
    try:
        verify_key(api_key)
        return jsonify({'ok': True, 'message': 'API key is valid.'})
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400


@app.post('/api/generate-seo')
def api_generate_seo():
    payload = request.get_json(silent=True) or {}
    raw = (payload.get('article') or '').strip()
    api_key = (payload.get('api_key') or '').strip()
    if not raw:
        return jsonify({'ok': False, 'error': 'Article input is empty.'}), 400

    try:
        processed = process_input(raw)
        seo = generate_ai_seo(api_key, processed['plain_text'], processed['title_hint'])
        final_title = seo['seo_title'] or processed['title_hint'] or 'Untitled Article'
        final_output = build_output_html(final_title, processed['intro'], processed['cleaned_html'])
        return jsonify({
            'ok': True,
            'focus_keyphrase': seo['focus_keyphrase'],
            'seo_title': final_title,
            'meta_description': seo['meta_description'],
            'detected_embeds': processed['embeds'],
            'seo_output': final_output,
            'structure': processed['structure'],
        })
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500


@app.post('/api/generate-image-seo')
def api_generate_image_seo():
    api_key = (request.form.get('api_key') or '').strip()
    scene_notes = (request.form.get('scene_notes') or '').strip()
    file = request.files.get('image')
    if not file or not file.filename:
        return jsonify({'ok': False, 'error': 'Upload an image first.'}), 400
    if not file_allowed(file.filename):
        return jsonify({'ok': False, 'error': 'Allowed image types: PNG, JPG, JPEG, WEBP.'}), 400

    try:
        result = generate_image_seo(api_key, file, scene_notes)
        return jsonify({'ok': True, **result})
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500


if __name__ == '__main__':
    port = int(os.getenv('PORT', '5000'))
    app.run(host='0.0.0.0', port=port, debug=False)
