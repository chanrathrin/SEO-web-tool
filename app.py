"""
WordPress SEO Studio — Flask Web App
Converted from desktop Tkinter app (ImageSEOPromptV5Full.py)
Tabs: SEO Formatter | Image SEO
"""

import os, io, re, html, json, base64, time, random, urllib.request, urllib.error
from difflib import SequenceMatcher
import html as html_mod
import requests
from requests.adapters import HTTPAdapter
from flask import Flask, request, jsonify, render_template, session
from PIL import Image

# ── Together AI config ─────────────────────────────────────────────────────────
TOGETHER_BASE_URL        = "https://api.together.xyz/v1"
VISION_MODEL             = "Qwen/Qwen3-VL-8B-Instruct"
SEO_MODEL                = "Qwen/Qwen2.5-7B-Instruct-Turbo"
API_CONNECT_TIMEOUT      = 6
API_READ_TIMEOUT         = 30
API_VERIFY_TIMEOUT       = 8
API_MAX_RETRIES          = 0
API_DEFAULT_TEMPERATURE  = 0.2
API_DEFAULT_TOP_P        = 0.9
API_MAX_TOKENS_SEO       = 420
API_MAX_TOKENS_VISION    = 260
FAST_IMAGE_SEO_MAX_TOKENS = 160
FORCED_TWITTER_USERNAME  = "RepSwalwell"

app = Flask(__name__)
app.secret_key = os.urandom(32)

# ── API Session ────────────────────────────────────────────────────────────────
_API_SESSION = None

def get_api_session():
    global _API_SESSION
    if _API_SESSION is not None:
        return _API_SESSION
    sess = requests.Session()
    adapter = HTTPAdapter(max_retries=0, pool_connections=10, pool_maxsize=10)
    sess.mount("https://", adapter)
    sess.mount("http://", adapter)
    _API_SESSION = sess
    return sess

def _headers(key):
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

def verify_key(api_key):
    sess = get_api_session()
    r = sess.get(
        f"{TOGETHER_BASE_URL}/models",
        headers=_headers(api_key),
        timeout=(API_CONNECT_TIMEOUT, API_VERIFY_TIMEOUT),
    )
    if r.status_code >= 400:
        try:
            d = r.json()
            detail = d.get("error", {}).get("message") or d.get("message") or r.text
        except Exception:
            detail = r.text
        raise RuntimeError(f"HTTP {r.status_code}: {detail}")
    return True

def chat_completion(api_key, model, messages, temperature=API_DEFAULT_TEMPERATURE,
                    timeout=API_READ_TIMEOUT, top_p=API_DEFAULT_TOP_P, max_tokens=None):
    sess = get_api_session()
    payload = {"model": model, "messages": messages, "temperature": temperature, "top_p": top_p}
    if max_tokens:
        payload["max_tokens"] = max_tokens
    r = sess.post(
        f"{TOGETHER_BASE_URL}/chat/completions",
        headers=_headers(api_key),
        json=payload,
        timeout=(API_CONNECT_TIMEOUT, timeout),
    )
    if r.status_code >= 400:
        try:
            d = r.json()
            detail = d.get("error", {}).get("message") or d.get("message") or r.text
        except Exception:
            detail = r.text
        raise RuntimeError(f"HTTP {r.status_code}: {detail}")
    return r.json()

def extract_content(resp):
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

def parse_json_safe(raw: str) -> dict:
    raw = (raw or "").strip()
    candidates = [raw, raw.replace("```json", "").replace("```", "").strip()]
    m = re.search(r"\{.*\}", candidates[-1], re.DOTALL)
    if m:
        candidates.append(m.group(0).strip())
    for c in candidates:
        if not c:
            continue
        try:
            d = json.loads(c)
            if isinstance(d, dict):
                return d
        except Exception:
            pass
    return {}

# ── Charset / decode helpers ───────────────────────────────────────────────────
def _smart_charset(raw_bytes: bytes, content_type: str = "") -> str:
    m = re.search(r"charset=([\w-]+)", content_type, re.I)
    if m:
        cs = m.group(1).strip().lower()
        if cs and cs not in ("utf-8", "utf8"):
            return cs
    sniff = raw_bytes[:8192].decode("ascii", errors="ignore")
    for pat in [r'<meta[^>]+charset=["\']?([\w-]+)', r'charset\s*=\s*["\']?([\w-]+)']:
        mm = re.search(pat, sniff, re.I)
        if mm:
            cs = mm.group(1).strip().lower()
            if cs and cs not in ("utf-8", "utf8"):
                return cs
    return "utf-8"

def _smart_decode(raw_bytes: bytes, charset: str) -> str:
    if raw_bytes[:2] == b"\x1f\x8b":
        try:
            import gzip
            raw_bytes = gzip.decompress(raw_bytes)
        except Exception:
            pass
    for enc in [charset, "utf-8", "utf-8-sig", "windows-1252", "iso-8859-1", "latin-1"]:
        if not enc:
            continue
        try:
            text = raw_bytes.decode(enc, errors="strict")
            if text.count("\ufffd") / max(len(text), 1) < 0.02:
                return text
        except (UnicodeDecodeError, LookupError):
            continue
    return raw_bytes.decode("latin-1", errors="replace")

# ── Twitter / Embed helpers ────────────────────────────────────────────────────
def _forced_public_twitter_url(tweet_id: str, fallback_url: str = "") -> str:
    tweet_id = str(tweet_id or "").strip()
    fallback_url = str(fallback_url or "").strip()
    forced_username = FORCED_TWITTER_USERNAME.strip().lstrip("@")
    if tweet_id and forced_username:
        return f"https://twitter.com/{forced_username}/status/{tweet_id}"
    return fallback_url or (f"https://twitter.com/i/web/status/{tweet_id}" if tweet_id else "")

class EmbedHelper:
    YOUTUBE_PATTERNS = [
        r"youtube\.com/embed/([\w-]+)",
        r'youtube\.com/watch\?[^"\'\s]*v=([\w-]+)',
        r"youtu\.be/([\w-]+)",
        r"youtube\.com/shorts/([\w-]+)",
    ]
    FACEBOOK_PATTERNS = [
        r'facebook\.com/[^\s"\'<>]+/videos/([\d]+)',
        r"facebook\.com/watch/?\?v=(\d+)",
        r"fb\.watch/([\w-]+)",
    ]

    @classmethod
    def _decode_url(cls, value):
        value = html_mod.unescape(str(value or "")).strip()
        try:
            from urllib.parse import unquote
            value = unquote(value)
        except Exception:
            pass
        return value

    @classmethod
    def _extract_tweet_id(cls, raw):
        raw = cls._decode_url(raw)
        patterns = [
            r'https?://(?:www\.)?(?:twitter|x)\.com/[A-Za-z0-9_]+/status(?:es)?/(\d+)',
            r'(?:twitter|x)\.com/i/web/status/(\d+)',
            r'data-tweet-id=["\'](\d+)["\']',
        ]
        for pat in patterns:
            m = re.search(pat, raw, re.I)
            if m:
                return m.group(1)
        return ""

    @classmethod
    def _normalize_twitter_public_url(cls, raw):
        raw = cls._decode_url(raw)
        direct = re.search(
            r'https?://(?:www\.)?(?:twitter|x)\.com/([A-Za-z0-9_]+)/status(?:es)?/(\d+)', raw, re.I
        )
        if direct:
            return f"https://twitter.com/{direct.group(1)}/status/{direct.group(2)}"
        tweet_id = cls._extract_tweet_id(raw)
        return _forced_public_twitter_url(tweet_id) if tweet_id else ""

    @classmethod
    def detect(cls, raw):
        raw = str(raw or "")
        raw_lower = raw.lower()
        for pat in cls.YOUTUBE_PATTERNS:
            m = re.search(pat, raw, re.I)
            if m:
                vid_id = m.group(1).split("&")[0].split("?")[0].strip()
                watch_url = f"https://www.youtube.com/watch?v={vid_id}"
                return {"type": "youtube", "html": watch_url, "label": f"YouTube [{vid_id}]"}
        tw_url = cls._normalize_twitter_public_url(raw)
        if tw_url:
            return {"type": "twitter", "html": tw_url, "label": "Twitter/X Post"}
        for pat in cls.FACEBOOK_PATTERNS:
            m = re.search(pat, raw, re.I)
            if m:
                fb_url_m = re.search(r'https?://(?:www\.)?facebook\.com/[^\s"\'<>]+', raw, re.I)
                if fb_url_m:
                    return {"type": "facebook", "html": fb_url_m.group(0).rstrip('/"\''), "label": "Facebook Video"}
        return {"type": None, "html": raw, "label": "Embedded Media"}

# ── Language detection ─────────────────────────────────────────────────────────
def detect_language(text: str) -> str:
    sample = re.sub(r"<[^>]+>", " ", text)
    sample = re.sub(r"https?://\S+", " ", sample)
    sample = re.sub(r"\s+", " ", sample).strip()[:2000]
    SCRIPTS = [
        ("Khmer",    0x1780, 0x17FF, 0.03), ("Arabic",   0x0600, 0x06FF, 0.05),
        ("Thai",     0x0E00, 0x0E7F, 0.05), ("Korean",   0xAC00, 0xD7AF, 0.05),
        ("Japanese", 0x3040, 0x309F, 0.02), ("Chinese",  0x4E00, 0x9FFF, 0.10),
    ]
    total = max(len(sample), 1)
    for name, start, end, min_ratio in SCRIPTS:
        count = sum(1 for ch in sample if start <= ord(ch) <= end)
        if count / total >= min_ratio:
            return name
    return "English"

# ── HTML helpers ───────────────────────────────────────────────────────────────
def strip_tags_text(html_str):
    t = re.sub(r"<[^>]+>", " ", str(html_str or ""))
    t = html_mod.unescape(t)
    return re.sub(r"\s+", " ", t).strip()

def clean_para_html(inner_html):
    inner_html = re.sub(r'<script[^>]*>.*?</script>', '', inner_html, flags=re.I|re.S)
    inner_html = re.sub(r'<style[^>]*>.*?</style>', '', inner_html, flags=re.I|re.S)
    inner_html = re.sub(r'<(?!/?(?:strong|b|em|i|a|br|span)\b)[^>]+>', ' ', inner_html, flags=re.I)
    return re.sub(r'\s+', ' ', inner_html).strip()

# ── SEO field cleaners ─────────────────────────────────────────────────────────
def clean_field(text: str, max_words: int = 20, mode: str = "generic") -> str:
    text = str(text or "").strip()
    text = html_mod.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    JUNK = [r"\bfeatured image\b", r"\bimage seo\b", r"\bseo\b", r"\bkeyword[s]?\b",
            r"\balt tag\b", r"\balt text\b", r"\bthis image\b", r"\bthe image\b",
            r"\ba photo of\b", r"\ban image of\b", r"\bpicture of\b"]
    for pat in JUNK:
        text = re.sub(pat, "", text, flags=re.I)
    text = re.sub(r"\s*,\s*,", ",", text)
    text = re.sub(r"^\s*[,;:\-–—]\s*", "", text)
    text = re.sub(r"\s*[,;:\-–—]\s*$", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if mode == "title":
        text = re.sub(r"[.!?]+$", "", text).strip()
        SMALL = {"a","an","the","and","or","but","in","on","at","to","for","of","with","by"}
        words = text.split()
        text = " ".join(w.capitalize() if (i == 0 or w.lower() not in SMALL) else w.lower()
                       for i, w in enumerate(words))
    elif mode == "caption":
        sentences = re.split(r'(?<=[.!?])\s+', text)
        text = sentences[0].strip() if sentences else text
        text = text.strip(" -,:;")
        if text and not re.search(r"[.!?]$", text):
            text += "."
    elif mode == "alt":
        text = re.sub(r"[.!?]+$", "", text).strip()
        if text and text[0].isupper() and not re.match(r"^[A-Z]{2,}", text):
            text = text[0].lower() + text[1:]
    words = text.split()
    if len(words) > max_words:
        text = " ".join(words[:max_words]).rstrip(" ,;:-")
        if mode == "caption" and not re.search(r"[.!?]$", text):
            text += "."
    return re.sub(r"\s+", " ", text).strip()

def sanitize_field(text, max_len=None, mode="generic"):
    result = clean_field(text, max_words=30, mode=mode)
    if max_len and len(result) > max_len:
        result = result[:max_len].rsplit(" ", 1)[0].rstrip(" ,;:.-")
        if mode == "caption" and not re.search(r"[.!?]$", result):
            result += "."
    return result

# ── HTML block parser ──────────────────────────────────────────────────────────
def parse_html_blocks(raw):
    blocks = []
    og_title = ""
    m = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', raw, re.I)
    if m:
        og_title = strip_tags_text(m.group(1))
    page_title = ""
    m = re.search(r"<title[^>]*>(.*?)</title>", raw, re.I|re.S)
    if m:
        page_title = strip_tags_text(m.group(1))
    first_h1 = ""
    m = re.search(r"<h1[^>]*>(.*?)</h1>", raw, re.I|re.S)
    if m:
        first_h1 = strip_tags_text(m.group(1))
    page_h1 = og_title or first_h1 or page_title
    if page_h1:
        page_h1 = re.sub(r"\s+[|\-–—]\s+.*$", "", page_h1).strip()
        if page_h1:
            blocks.append({"type": "h1", "content": page_h1})

    token_pat = re.compile(
        r"(<h[1-6][^>]*>.*?</h[1-6]>)"
        r"|(<blockquote\b[^>]*>.*?</blockquote>)"
        r"|(<iframe\b[^>]*>.*?</iframe>)"
        r"|(<figure\b[^>]*>.*?</figure>)"
        r"|(<p\b[^>]*>.*?</p>)",
        re.I|re.S)

    seen_text = set()
    h1_lower = page_h1.lower().strip() if page_h1 else ""

    for m in token_pat.finditer(raw):
        tag = m.group(0)
        hm = re.match(r"<(h[1-6])[^>]*>(.*?)</h[1-6]>", tag, re.I|re.S)
        if hm:
            level = hm.group(1).lower()
            text = strip_tags_text(hm.group(2))
            if not text:
                continue
            if text.lower() in {"share","related articles","read more","comments","leave a reply"}:
                continue
            norm = text.lower().strip()
            if norm in seen_text:
                continue
            seen_text.add(norm)
            blocks.append({"type": level, "content": text})
            continue

        is_embed = any(tag.lower().startswith(t) for t in ("<blockquote","<iframe","<figure"))
        if is_embed:
            info = EmbedHelper.detect(tag)
            emb = info["html"] if info["type"] else tag
            if emb:
                blocks.append({"type": "embed", "content": emb})
            continue

        pm = re.match(r"<p[^>]*>(.*?)</p>", tag, re.I|re.S)
        if pm:
            inner_html = pm.group(1).strip()
            text_plain = strip_tags_text(inner_html)
            if not text_plain or len(text_plain.split()) < 5:
                continue
            if re.match(r"^https?://[^\s]+$", text_plain):
                continue
            junk_pats = [r"follow us", r"share this", r"read more", r"subscribe", r"sign up"]
            if any(re.search(p, text_plain.lower()) for p in junk_pats) and len(text_plain.split()) <= 20:
                continue
            norm = text_plain.lower().strip()
            if norm in seen_text:
                continue
            if h1_lower and SequenceMatcher(None, h1_lower, norm[:len(h1_lower)]).ratio() >= 0.85:
                continue
            seen_text.add(norm)
            para_html = clean_para_html(inner_html)
            if para_html:
                blocks.append({"type": "p", "content": para_html, "plain": text_plain})
    return blocks

# ── Build SEO output ───────────────────────────────────────────────────────────
def trim_words(text, limit, chars=False):
    text = re.sub(r"\s+", " ", text or "").strip()
    if chars:
        if len(text) <= limit:
            return text
        cut = text[:limit].rstrip()
        return (cut.rsplit(" ", 1)[0] if " " in cut else cut).rstrip(" ,.-:;")
    return " ".join(text.split()[:limit]).strip()

def make_slug(title):
    slug = re.sub(r"[^a-z0-9\s-]", "", title.lower())
    slug = re.sub(r"\s+", "-", slug).strip("-")
    return re.sub(r"-{2,}", "-", slug)

def make_keyphrase(title):
    return " ".join(re.sub(r"[^\w\s-]", "", title).split()[:10]).strip()

def process_article_text(raw_input: str) -> dict:
    """Core processing: parse HTML or plain text → return SEO sections dict."""
    looks_html = bool(re.search(r"<(p|h[1-6]|div|article|body|html)\b", raw_input, re.I))
    blocks = []
    if looks_html:
        blocks = parse_html_blocks(raw_input)
    else:
        # Plain text
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', raw_input) if p.strip()]
        for i, p in enumerate(paragraphs):
            if i == 0:
                blocks.append({"type": "h1", "content": trim_words(p, 20)})
            else:
                blocks.append({"type": "p", "content": p, "plain": p})

    h1 = ""
    intro = ""
    struct = []
    current_h2 = None
    current_h3 = None

    def ensure_section(title=""):
        nonlocal current_h2
        if current_h2 is None:
            current_h2 = {"h2": title, "subsections": []}
            struct.append(current_h2)
        return current_h2

    def ensure_sub(title=""):
        nonlocal current_h3
        sec = ensure_section("")
        if current_h3 is None:
            current_h3 = {"h3": title, "body": ""}
            sec["subsections"].append(current_h3)
        return current_h3

    for b in blocks:
        btype = b.get("type")
        content = (b.get("content") or "").strip()
        if not content:
            continue
        if btype == "h1":
            if not h1:
                h1 = content
            continue
        if btype == "h2":
            current_h2 = {"h2": content, "subsections": []}
            struct.append(current_h2)
            current_h3 = None
            continue
        if btype in ("h3", "h4"):
            sec = ensure_section("")
            current_h3 = {"h3": content, "body": ""}
            sec["subsections"].append(current_h3)
            continue
        if btype == "embed":
            sub = ensure_sub("")
            if sub["body"].strip():
                sub["body"] += "\n\n"
            sub["body"] += f"__EMBED__{content}__EMBED__"
            continue
        if btype == "p":
            plain = (b.get("plain") or "").strip()
            if not intro and plain:
                intro = plain
                continue
            sub = ensure_sub("")
            if sub["body"].strip():
                sub["body"] += "\n\n"
            sub["body"] += content
            continue

    if not h1 and intro:
        h1 = trim_words(intro, 20)

    # Build WP HTML output
    wp_html = build_wp_html(h1, intro, struct)
    # Build SEO meta options
    seo_title_opts = []
    base = re.sub(r"\s+", " ", h1).strip()
    if base:
        seo_title_opts = [
            trim_words(base, 60, chars=True),
            trim_words(base + " | Full Report", 60, chars=True),
            trim_words(base + " | Key Updates", 60, chars=True),
        ]
        seo_title_opts = list(dict.fromkeys(x for x in seo_title_opts if x))

    src = re.sub(r"\s+", " ", intro or h1).strip()
    meta_opts = []
    if src:
        meta_opts = [
            trim_words(src, 160, chars=True),
            trim_words(h1 + " — " + src, 160, chars=True),
        ]
        meta_opts = list(dict.fromkeys(x for x in meta_opts if x))

    focus_keyphrase = make_keyphrase(h1)
    slug = make_slug(h1)

    return {
        "h1": h1,
        "intro": intro,
        "slug": slug,
        "focus_keyphrase": focus_keyphrase,
        "seo_title_options": seo_title_opts,
        "meta_options": meta_opts,
        "wp_html": wp_html,
        "struct": struct,
        "language": detect_language(raw_input),
    }

# ── Build WordPress HTML ───────────────────────────────────────────────────────
def build_wp_html(h1, intro, struct):
    if not h1 and not intro and not struct:
        return ""
    parts = []
    H1_S   = 'font-family:Arial,sans-serif;font-size:clamp(28px,5vw,42px);font-weight:800;color:#111111;margin:0 0 20px 0;line-height:1.2;text-align:center;'
    INTRO_S= 'font-size:clamp(16px,3.5vw,20px);line-height:1.8;color:#444444;margin:0 0 24px 0;font-style:italic;text-align:center;'
    H2_S   = 'font-family:Arial,sans-serif;font-size:clamp(20px,4vw,30px);font-weight:800;color:#111111;margin:36px 0 14px 0;line-height:1.25;border-left:4px solid #2563eb;padding-left:12px;'
    H3_S   = 'font-family:Arial,sans-serif;font-size:clamp(17px,3.2vw,24px);font-weight:700;color:#222222;margin:24px 0 10px 0;line-height:1.3;'
    P_S    = 'font-size:clamp(15px,3vw,19px);line-height:1.85;color:#333333;margin:0 0 20px 0;'
    WRAP   = 'max-width:800px;margin:0 auto;padding:0 16px;font-family:Georgia,"Times New Roman",serif;color:#222222;font-size:18px;line-height:1.8;'

    parts.append(f'<div style="{WRAP}">')
    if h1:
        parts.append(f'<h1 style="{H1_S}">{html.escape(h1)}</h1>')
    if intro:
        parts.append(f'<p style="{INTRO_S}">{html.escape(intro)}</p>')

    def render_embed(url):
        info = EmbedHelper.detect(url)
        if info["type"] == "youtube":
            vid_id = re.search(r'v=([\w-]+)', url)
            if vid_id:
                yt_id = vid_id.group(1)
                return (f'<figure style="text-align:center;margin:28px auto;">'
                        f'<iframe width="100%" height="450" src="https://www.youtube.com/embed/{yt_id}" '
                        f'frameborder="0" allowfullscreen></iframe></figure>')
        if info["type"] == "twitter":
            return (f'<blockquote class="twitter-tweet" align="center">'
                    f'<a href="{html.escape(url)}"></a></blockquote>'
                    f'<script async src="https://platform.twitter.com/widgets.js"></script>')
        return f'<p style="{P_S}"><a href="{html.escape(url)}">{html.escape(url)}</a></p>'

    for sec in struct:
        h2 = sec.get("h2", "")
        if h2:
            parts.append(f'<h2 style="{H2_S}">{html.escape(h2)}</h2>')
        for sub in sec.get("subsections", []):
            h3 = sub.get("h3", "")
            if h3:
                parts.append(f'<h3 style="{H3_S}">{html.escape(h3)}</h3>')
            body = sub.get("body", "")
            if body:
                for chunk in re.split(r'(__EMBED__.*?__EMBED__)', body, flags=re.S):
                    chunk = chunk.strip()
                    if not chunk:
                        continue
                    if chunk.startswith("__EMBED__") and chunk.endswith("__EMBED__"):
                        url = chunk[9:-9].strip()
                        parts.append(render_embed(url))
                    else:
                        if not re.search(r'<[a-z]', chunk, re.I):
                            parts.append(f'<p style="{P_S}">{html.escape(chunk)}</p>')
                        else:
                            parts.append(f'<p style="{P_S}">{chunk}</p>')
    parts.append('</div>')
    return "\n".join(parts)

# ── Image SEO via Vision AI ───────────────────────────────────────────────────
def optimize_image_for_api(pil_image, max_side=1280, jpeg_quality=82):
    img = pil_image.copy().convert("RGB")
    w, h = img.size
    longest = max(w, h)
    if longest > max_side:
        scale = max_side / float(longest)
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    bio = io.BytesIO()
    img.save(bio, format="JPEG", quality=jpeg_quality, optimize=True)
    return bio.getvalue(), "image/jpeg"

def generate_image_seo(api_key: str, image_b64: str, scene_notes: str = "") -> dict:
    prompt = (
        "You are an expert WordPress image SEO specialist. "
        "Analyze this image and output ONLY valid JSON with exactly these keys:\n"
        '{"alt_text": "...", "image_title": "...", "caption": "..."}\n\n'
        "Rules:\n"
        "- alt_text: 8-15 words, descriptive, no 'image of' prefix, lowercase start\n"
        "- image_title: 3-8 words, Title Case, no punctuation\n"
        "- caption: 1-2 sentences, ends with period, factual\n"
        "- No SEO jargon, no 'featured image' phrases\n"
        + (f"Scene notes: {scene_notes}\n" if scene_notes else "")
        + "Output ONLY the JSON object, no markdown, no explanation."
    )
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                {"type": "text", "text": prompt},
            ],
        }
    ]
    resp = chat_completion(api_key, VISION_MODEL, messages,
                           timeout=30, max_tokens=FAST_IMAGE_SEO_MAX_TOKENS)
    raw = extract_content(resp)
    d = parse_json_safe(raw)
    return {
        "alt_text": sanitize_field(d.get("alt_text", ""), 90, "alt"),
        "image_title": sanitize_field(d.get("image_title", ""), 90, "title"),
        "caption": sanitize_field(d.get("caption", ""), 180, "caption"),
    }

def generate_ai_seo_fields(api_key: str, article_text: str, language: str = "English") -> dict:
    snippet = article_text[:4000]
    prompt = (
        f"You are an expert Yoast SEO specialist. The article language is: {language}.\n"
        "Analyze the article and output ONLY valid JSON:\n"
        '{"focus_keyphrase":"...","seo_title":"...","meta_description":"...","seo_title_variants":["...","...","..."],"meta_variants":["...","..."]}\n\n'
        "Rules:\n"
        "- focus_keyphrase: 2-4 words, specific, lowercase\n"
        "- seo_title: 50-60 chars max, includes keyphrase, compelling\n"
        "- meta_description: 120-160 chars, includes keyphrase, action-oriented\n"
        "- seo_title_variants: 3 alternative title options\n"
        "- meta_variants: 2 alternative meta descriptions\n"
        "Output ONLY the JSON, no markdown.\n\n"
        f"Article:\n{snippet}"
    )
    messages = [{"role": "user", "content": prompt}]
    resp = chat_completion(api_key, SEO_MODEL, messages,
                           max_tokens=API_MAX_TOKENS_SEO, timeout=API_READ_TIMEOUT)
    raw = extract_content(resp)
    d = parse_json_safe(raw)
    return {
        "focus_keyphrase": d.get("focus_keyphrase", ""),
        "seo_title": d.get("seo_title", ""),
        "meta_description": d.get("meta_description", ""),
        "seo_title_variants": d.get("seo_title_variants", []),
        "meta_variants": d.get("meta_variants", []),
    }

# ══════════════════════════════════════════════════════════════════════════════
# FLASK ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/verify-key", methods=["POST"])
def api_verify_key():
    data = request.get_json(force=True) or {}
    key = (data.get("api_key") or "").strip()
    if not key:
        return jsonify({"ok": False, "error": "API key is empty"}), 400
    try:
        verify_key(key)
        session["api_key"] = key
        return jsonify({"ok": True, "message": "API key is valid ✓"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400

@app.route("/api/set-key", methods=["POST"])
def api_set_key():
    data = request.get_json(force=True) or {}
    key = (data.get("api_key") or "").strip()
    session["api_key"] = key
    return jsonify({"ok": True})

@app.route("/api/fetch-url", methods=["POST"])
def api_fetch_url():
    data = request.get_json(force=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"ok": False, "error": "No URL provided"}), 400
    if not url.startswith("http"):
        url = "https://" + url
    # Clean tracking params
    url = re.sub(r"[?&](utm_\w+|fbclid|aem_\w*|ref|source|medium|campaign)=[^&]*", "", url)
    url = url.rstrip("?&")

    STRATEGIES = [
        {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
         "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
         "Accept-Language": "en-US,en;q=0.9"},
        {"User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
         "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
    ]
    html_content = None
    last_err = None
    for hdrs in STRATEGIES:
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw_bytes = resp.read()
                ct = resp.headers.get("Content-Type", "")
                charset = _smart_charset(raw_bytes, ct)
                html_content = _smart_decode(raw_bytes, charset)
            body_lower = html_content.lower()
            blocked = any(kw in body_lower for kw in ["access denied", "403 forbidden", "captcha", "cloudflare"])
            if blocked and len(html_content) < 8000:
                html_content = None
                continue
            break
        except Exception as e:
            last_err = e
            time.sleep(0.3)

    if not html_content:
        return jsonify({"ok": False, "error": str(last_err) or "All fetch strategies failed"}), 400

    lang = detect_language(html_content)
    return jsonify({"ok": True, "html": html_content, "language": lang, "url": url})

@app.route("/api/process-article", methods=["POST"])
def api_process_article():
    data = request.get_json(force=True) or {}
    raw = (data.get("text") or "").strip()
    if not raw:
        return jsonify({"ok": False, "error": "No article text provided"}), 400
    try:
        result = process_article_text(raw)
        return jsonify({"ok": True, **result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/ai-seo-fields", methods=["POST"])
def api_ai_seo_fields():
    data = request.get_json(force=True) or {}
    api_key = (data.get("api_key") or session.get("api_key") or "").strip()
    article_text = (data.get("text") or "").strip()
    language = (data.get("language") or "English").strip()
    if not api_key:
        return jsonify({"ok": False, "error": "API key not set. Configure it in the API Settings panel."}), 400
    if not article_text:
        return jsonify({"ok": False, "error": "No article text provided"}), 400
    try:
        result = generate_ai_seo_fields(api_key, article_text, language)
        return jsonify({"ok": True, **result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/image-seo", methods=["POST"])
def api_image_seo():
    api_key = (request.form.get("api_key") or session.get("api_key") or "").strip()
    scene_notes = (request.form.get("scene_notes") or "").strip()
    if not api_key:
        return jsonify({"ok": False, "error": "API key not set. Configure it in the API Settings panel."}), 400

    if "image" not in request.files:
        return jsonify({"ok": False, "error": "No image uploaded"}), 400

    file = request.files["image"]
    try:
        img = Image.open(file.stream)
        img_bytes, _ = optimize_image_for_api(img)
        image_b64 = base64.b64encode(img_bytes).decode()
        result = generate_image_seo(api_key, image_b64, scene_notes)
        return jsonify({"ok": True, **result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
