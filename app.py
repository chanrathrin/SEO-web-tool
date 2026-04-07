# ============================================================
#  WordPress SEO Studio — Web Edition
#  Faithful port of ImageSEOPromptV5Full.py (Tkinter → Flask)
#  Tab 1: SEO Formatter  (article → Yoast fields + WP HTML)
#  Tab 2: Image SEO      (upload/crop/AI generate)
# ============================================================
import os, io, re, html, json, base64, time, random
import urllib.request, urllib.error
from difflib import SequenceMatcher
import html as html_mod
import requests
from requests.adapters import HTTPAdapter
from flask import Flask, request, jsonify, render_template, session
from PIL import Image

# ── Together AI config (identical to desktop) ──────────────────────────────────
TOGETHER_BASE_URL         = "https://api.together.xyz/v1"
VISION_MODEL              = "Qwen/Qwen3-VL-8B-Instruct"
VISION_FALLBACK_MODEL     = ""
SEO_MODEL                 = "Qwen/Qwen2.5-7B-Instruct-Turbo"
API_CONNECT_TIMEOUT       = 6
API_READ_TIMEOUT          = 30
API_VERIFY_TIMEOUT        = 8
API_MAX_RETRIES           = 0
API_RETRY_BACKOFF         = 0.35
API_USE_SESSION           = True
API_ENABLE_CHEAP_FALLBACK = True
API_DEFAULT_TEMPERATURE   = 0.2
API_DEFAULT_TOP_P         = 0.9
API_MAX_TOKENS_SEO        = 420
AI_FAST_MODE              = True
FAST_SEO_FIELDS_MODEL     = SEO_MODEL
FAST_AI_TIMEOUT           = 24
FAST_SEO_FIELD_MAX_TOKENS = 220
FAST_IMAGE_SEO_MAX_TOKENS = 160
FORCED_TWITTER_USERNAME   = "RepSwalwell"

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(32))

# ── API Session ────────────────────────────────────────────────────────────────
_API_SESSION = None
def get_api_session():
    global _API_SESSION
    if _API_SESSION is not None and API_USE_SESSION:
        return _API_SESSION
    sess = requests.Session()
    adapter = HTTPAdapter(max_retries=0, pool_connections=10, pool_maxsize=10)
    sess.mount("https://", adapter); sess.mount("http://", adapter)
    if API_USE_SESSION: _API_SESSION = sess
    return sess

def _headers(key):
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json",
            "Accept": "application/json", "Connection": "keep-alive"}

def verify_key(api_key, timeout=API_VERIFY_TIMEOUT):
    sess = get_api_session()
    r = sess.get(f"{TOGETHER_BASE_URL}/models", headers=_headers(api_key),
                 timeout=(API_CONNECT_TIMEOUT, timeout))
    if r.status_code >= 400:
        try: detail = r.json().get("error", {}).get("message") or r.text
        except: detail = r.text
        raise RuntimeError(f"HTTP {r.status_code}: {detail}")
    return True

def chat_completion(api_key, model, messages, temperature=API_DEFAULT_TEMPERATURE,
                    timeout=API_READ_TIMEOUT, response_format=None,
                    top_p=API_DEFAULT_TOP_P, max_tokens=None, **kw):
    sess = get_api_session()
    payload = {"model": model, "messages": messages,
               "temperature": temperature, "top_p": top_p}
    if response_format: payload["response_format"] = response_format
    if max_tokens:      payload["max_tokens"] = max_tokens
    last_err = None
    for attempt in range(API_MAX_RETRIES + 1):
        try:
            r = sess.post(f"{TOGETHER_BASE_URL}/chat/completions",
                          headers=_headers(api_key), json=payload,
                          timeout=(API_CONNECT_TIMEOUT, timeout))
            if r.status_code >= 400:
                try: detail = r.json().get("error", {}).get("message") or r.text
                except: detail = r.text
                if API_ENABLE_CHEAP_FALLBACK and model == SEO_MODEL and r.status_code in (429, 500, 502, 503, 504):
                    fb = dict(payload); fb["model"] = "meta-llama/Llama-3.2-3B-Instruct-Turbo"
                    rr = sess.post(f"{TOGETHER_BASE_URL}/chat/completions",
                                   headers=_headers(api_key), json=fb,
                                   timeout=(API_CONNECT_TIMEOUT, timeout))
                    if rr.status_code < 400: return rr.json()
                raise RuntimeError(f"HTTP {r.status_code}: {detail}")
            return r.json()
        except Exception as e:
            last_err = e
            if attempt >= API_MAX_RETRIES: break
            time.sleep((API_RETRY_BACKOFF ** attempt) + random.uniform(0.1, 0.35))
    raise RuntimeError(str(last_err) if last_err else "Unknown API error")

def extract_content(resp):
    choices = resp.get("choices") or []
    if not choices: return ""
    msg = choices[0].get("message") or {}
    content = msg.get("content", "")
    if isinstance(content, list):
        return "\n".join(str(i.get("text") or i.get("content") or "")
                         for i in content if isinstance(i, dict)).strip()
    return str(content or "").strip()

def parse_json(raw: str) -> dict:
    raw = (raw or "").strip()
    if not raw: raise ValueError("Empty content from model")
    candidates = [raw, raw.replace("```json", "").replace("```", "").strip()]
    m = re.search(r"\{.*\}", candidates[-1], re.DOTALL)
    if m: candidates.append(m.group(0).strip())
    for c in candidates:
        try:
            d = json.loads(c)
            if isinstance(d, dict): return d
        except: pass
    raise ValueError(f"Cannot parse JSON. Raw: {raw[:200]}")

# ── Charset / decode ───────────────────────────────────────────────────────────
def _smart_charset(raw_bytes: bytes, content_type: str = "") -> str:
    m = re.search(r"charset=([\w-]+)", content_type, re.I)
    if m:
        cs = m.group(1).strip().lower()
        if cs not in ("utf-8", "utf8"): return cs
    sniff = raw_bytes[:8192].decode("ascii", errors="ignore")
    for pat in [r'<meta[^>]+charset=["\']?([\w-]+)',
                r'<meta[^>]+content=["\'][^"\']*charset=([\w-]+)',
                r'charset\s*=\s*["\']?([\w-]+)']:
        mm = re.search(pat, sniff, re.I)
        if mm:
            cs = mm.group(1).strip().lower()
            if cs not in ("utf-8","utf8"): return cs
    if raw_bytes.startswith(b"\xff\xfe"): return "utf-16-le"
    if raw_bytes.startswith(b"\xfe\xff"): return "utf-16-be"
    if raw_bytes.startswith(b"\xef\xbb\xbf"): return "utf-8-sig"
    return "utf-8"

def _smart_decode(raw_bytes: bytes, charset: str) -> str:
    if raw_bytes[:2] == b"\x1f\x8b":
        try:
            import gzip; raw_bytes = gzip.decompress(raw_bytes)
        except: pass
    for enc in [charset, "utf-8", "utf-8-sig", "windows-1252", "iso-8859-1", "latin-1"]:
        if not enc: continue
        try:
            text = raw_bytes.decode(enc, errors="strict")
            if text.count("\ufffd") / max(len(text), 1) < 0.02: return text
        except (UnicodeDecodeError, LookupError): continue
    return raw_bytes.decode("latin-1", errors="replace")

# ── Twitter helpers ────────────────────────────────────────────────────────────
def _forced_public_twitter_url(tweet_id: str, fallback_url: str = "") -> str:
    tweet_id = str(tweet_id or "").strip()
    forced = FORCED_TWITTER_USERNAME.strip().lstrip("@")
    if tweet_id and forced:
        return f"https://twitter.com/{forced}/status/{tweet_id}"
    return str(fallback_url or "").strip() or (
        f"https://twitter.com/i/web/status/{tweet_id}" if tweet_id else "")

def rewrite_twitter_embed_urls(html_text: str) -> str:
    html_text = str(html_text or "")
    html_text = re.sub(r'https?://(?:www\.)?twitter\.com/i/web/status/(\d+)',
        lambda m: _forced_public_twitter_url(m.group(1), m.group(0)), html_text, flags=re.I)
    def _replace_platform(m):
        url = html_mod.unescape(m.group(0))
        tid = re.search(r'[?&](?:id|tweetId)=(\d+)', url, re.I)
        if not tid: tid = re.search(r'data-tweet-id=["\'](\d+)["\']', url, re.I)
        if tid: return _forced_public_twitter_url(tid.group(1), url)
        return url
    html_text = re.sub(r'https?://platform\.twitter\.com/embed/Tweet\.html\?[^"\'\s<]+',
                       _replace_platform, html_text, flags=re.I)
    return html_text

# ── Embed Helper (identical logic to desktop) ─────────────────────────────────
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
    def _decode_url(cls, value):
        value = html_mod.unescape(str(value or "")).strip()
        try:
            from urllib.parse import unquote; value = unquote(value)
        except: pass
        return value

    @classmethod
    def _extract_tweet_id(cls, raw):
        raw = cls._decode_url(raw)
        for pat in [
            r'https?://(?:www\.)?(?:twitter|x)\.com/[A-Za-z0-9_]+/status(?:es)?/(\d+)',
            r'(?:twitter|x)\.com/i/web/status/(\d+)',
            r'data-tweet-id=["\'](\d+)["\']',
            r'[?&](?:id|tweetId)=(\d+)',
        ]:
            m = re.search(pat, raw, re.I)
            if m: return m.group(1)
        return ""

    @classmethod
    def _normalize_twitter_public_url(cls, raw):
        raw = cls._decode_url(raw)
        direct = re.search(
            r'https?://(?:www\.)?(?:twitter|x)\.com/([A-Za-z0-9_]+)/status(?:es)?/(\d+)', raw, re.I)
        if direct:
            return f"https://twitter.com/{direct.group(1)}/status/{direct.group(2)}"
        for key in ("url", "href"):
            m = re.search(rf'[?&]{key}=([^&"\']+)', raw, re.I)
            if m:
                dec = cls._decode_url(m.group(1))
                d2 = re.search(
                    r'https?://(?:www\.)?(?:twitter|x)\.com/([A-Za-z0-9_]+)/status(?:es)?/(\d+)', dec, re.I)
                if d2: return f"https://twitter.com/{d2.group(1)}/status/{d2.group(2)}"
        tid = cls._extract_tweet_id(raw)
        return _forced_public_twitter_url(tid) if tid else ""

    @classmethod
    def detect(cls, raw):
        raw = str(raw or ""); raw_lower = raw.lower()
        for pat in cls.YOUTUBE_PATTERNS:
            m = re.search(pat, raw, re.I)
            if m:
                vid_id = m.group(1).split("&")[0].split("?")[0].strip()
                watch_url = f"https://www.youtube.com/watch?v={vid_id}"
                return {"type":"youtube","icon":"▶","label":f"YouTube [{vid_id}]",
                        "html":watch_url,"html_classic":watch_url,"src":watch_url,"vid_id":vid_id}
        tw_url = cls._normalize_twitter_public_url(raw)
        if tw_url:
            tweet_id = cls._extract_tweet_id(raw)
            return {"type":"twitter","icon":"🐦","label":f"Twitter/X Post [ID:{tweet_id}]" if tweet_id else "Twitter/X Post",
                    "html":tw_url,"html_classic":tw_url,"src":tw_url,"tweet_id":tweet_id}
        for pat in cls.FACEBOOK_PATTERNS:
            m = re.search(pat, raw, re.I)
            if m:
                fb_m = re.search(r'https?://(?:www\.)?facebook\.com/[^\s"\'<>]+', raw, re.I)
                if fb_m:
                    fb_url = fb_m.group(0).rstrip('/"\'')
                    return {"type":"facebook","icon":"📘","label":"Facebook Video",
                            "html":fb_url,"html_classic":fb_url,"src":fb_url}
        src_m = re.search(r'src=["\']([^"\'>\s]+)["\']', raw, re.I)
        if src_m and "<iframe" in raw_lower:
            src = cls._decode_url(src_m.group(1))
            yt = re.search(r'(?:youtube\.com/embed/|youtu\.be/|youtube\.com/watch\?v=)([\w-]+)', src, re.I)
            if yt:
                vid_id = yt.group(1); watch_url = f"https://www.youtube.com/watch?v={vid_id}"
                return {"type":"youtube","icon":"▶","label":f"YouTube [{vid_id}]",
                        "html":watch_url,"html_classic":watch_url,"src":watch_url,"vid_id":vid_id}
            tw_url = cls._normalize_twitter_public_url(src)
            if tw_url:
                tweet_id = cls._extract_tweet_id(src)
                return {"type":"twitter","icon":"🐦","label":f"Twitter/X [{tweet_id}]",
                        "html":tw_url,"html_classic":tw_url,"src":tw_url,"tweet_id":tweet_id}
        return {"type":None,"icon":"▶","label":"Embedded Media","html":raw,"html_classic":raw,"src":""}

# ── Language detection ─────────────────────────────────────────────────────────
def _detect_language(text: str) -> str:
    sample = re.sub(r"<[^>]+>", " ", text)
    sample = re.sub(r"https?://\S+", " ", sample)
    sample = re.sub(r"\s+", " ", sample).strip()[:2000]
    SCRIPTS = [
        ("Khmer",    0x1780,0x17FF,0.03), ("Arabic",   0x0600,0x06FF,0.05),
        ("Thai",     0x0E00,0x0E7F,0.05), ("Hindi",    0x0900,0x097F,0.05),
        ("Korean",   0xAC00,0xD7AF,0.05), ("Japanese", 0x3040,0x309F,0.02),
        ("Japanese", 0x30A0,0x30FF,0.02), ("Chinese",  0x4E00,0x9FFF,0.10),
    ]
    total = max(len(sample), 1); seen = set()
    for name, start, end, min_ratio in SCRIPTS:
        if name in seen: continue
        if sum(1 for ch in sample if start <= ord(ch) <= end) / total >= min_ratio:
            seen.add(name); return name
    freq = {}
    for w in sample.lower().split():
        w = re.sub(r"[^a-zàáâãäåæçèéêëìíîïðñòóôõöùúûüý]", "", w)
        if len(w) >= 3: freq[w] = freq.get(w, 0) + 1
    LANG_WORDS = {
        "French":     ["le","la","les","de","du","des","est","dans","pour","avec"],
        "Spanish":    ["el","la","los","de","del","que","en","es","con","por"],
        "Portuguese": ["de","da","do","que","em","para","com","uma","por","não"],
        "German":     ["der","die","das","und","von","ist","mit","dem","für","auf"],
        "Vietnamese": ["của","và","là","có","trong","được","không","này","cho","với"],
        "Indonesian": ["yang","dan","di","ke","dari","untuk","dengan","ini","pada","ada"],
    }
    best_lang, best_score = "English", 0
    for lang, markers in LANG_WORDS.items():
        score = sum(freq.get(w, 0) for w in markers)
        if score > best_score: best_score = score; best_lang = lang
    return best_lang

# ── HTML helpers ───────────────────────────────────────────────────────────────
def strip_tags_text(s):
    t = re.sub(r"<[^>]+>", " ", str(s or ""))
    return re.sub(r"\s+", " ", html_mod.unescape(t)).strip()

def clean_para_html(inner):
    inner = re.sub(r'<script[^>]*>.*?</script>', '', inner, flags=re.I|re.S)
    inner = re.sub(r'<style[^>]*>.*?</style>', '', inner, flags=re.I|re.S)
    inner = re.sub(r'<(?!/?(?:strong|b|em|i|a|br|span)\b)[^>]+>', ' ', inner, flags=re.I)
    return re.sub(r'\s+', ' ', inner).strip()

def _clean_field(text: str, max_words: int = 20, mode: str = "generic") -> str:
    text = str(text or "").strip()
    text = html_mod.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    JUNK = [r"\bfeatured image\b",r"\bimage seo\b",r"\bseo\b",r"\bkeyword[s]?\b",
            r"\boptimiz\w*\b",r"\branking\b",r"\bmetadata\b",r"\balt tag\b",r"\balt text\b",
            r"\bvisibility\b",r"\bdiscoverability\b",r"\bthis image\b",r"\bthe image\b",
            r"\ba photo of\b",r"\ban image of\b",r"\bpicture of\b",r"\bshowcas\w*\b",
            r"\bIMG_?\d+\b",r"\bDSC_?\d+\b",r"\b\w+\.(jpg|jpeg|png|webp)\b"]
    for pat in JUNK: text = re.sub(pat, "", text, flags=re.I)
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
        if text and not re.search(r"[.!?]$", text): text += "."
    elif mode == "alt":
        text = re.sub(r"[.!?]+$", "", text).strip()
        if text and text[0].isupper() and not re.match(r"^[A-Z]{2,}", text):
            text = text[0].lower() + text[1:]
    words = text.split()
    if len(words) > max_words:
        text = " ".join(words[:max_words]).rstrip(" ,;:-")
        if mode == "caption" and not re.search(r"[.!?]$", text): text += "."
    return re.sub(r"\s+", " ", text).strip()

def _sanitize(text, max_len=None, mode="generic"):
    result = _clean_field(text, max_words=30, mode=mode)
    if max_len and len(result) > max_len:
        result = result[:max_len].rsplit(" ", 1)[0].rstrip(" ,;:.-")
        if mode == "caption" and not re.search(r"[.!?]$", result): result += "."
    return result

# ── HTML parser (full port from desktop) ─────────────────────────────────────
def _sanitize_wp_html(raw):
    for pat in [r'<script[^>]*>.*?</script>', r'<style[^>]*>.*?</style>',
                r'<header\b[^>]*>.*?</header>', r'<footer\b[^>]*>.*?</footer>',
                r'<nav\b[^>]*>.*?</nav>', r'<aside\b[^>]*>.*?</aside>']:
        raw = re.sub(pat, ' ', raw, flags=re.I|re.S)
    return raw

def _parse_html_blocks(raw):
    blocks = []
    og_title = ""
    m = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', raw, re.I)
    if m: og_title = strip_tags_text(m.group(1))
    page_title = ""
    m = re.search(r"<title[^>]*>(.*?)</title>", raw, re.I|re.S)
    if m: page_title = strip_tags_text(m.group(1))
    first_h1 = ""
    m = re.search(r"<h1[^>]*>(.*?)</h1>", raw, re.I|re.S)
    if m: first_h1 = strip_tags_text(m.group(1))
    page_h1 = og_title or first_h1 or page_title
    if page_h1:
        page_h1 = re.sub(r"\s+[|\-–—]\s+.*$", "", page_h1).strip()
        if page_h1: blocks.append({"type": "h1", "content": page_h1})

    def make_embed(raw_tag):
        info = EmbedHelper.detect(raw_tag)
        return info["html"] if info["type"] else raw_tag

    token_pat = re.compile(
        r"(__PRESV_EMBED_START__.*?__PRESV_EMBED_END__)"
        r"|(<h[1-6][^>]*>.*?</h[1-6]>)"
        r"|(<blockquote\b[^>]*>.*?</blockquote>(?:\s*<script[^>]*>[^<]*</script>)?)"
        r"|(<iframe\b[^>]*>.*?</iframe>)"
        r"|(<video\b[^>]*>.*?</video>)"
        r"|(<figure\b[^>]*>.*?</figure>)"
        r"|(<p\b[^>]*>.*?</p>)", re.I|re.S)

    seen_text = set()
    h1_lower = page_h1.lower().strip() if page_h1 else ""

    for m in token_pat.finditer(raw):
        tag = m.group(0)
        hm = re.match(r"<(h[1-6])[^>]*>(.*?)</h[1-6]>", tag, re.I|re.S)
        if hm:
            level = hm.group(1).lower(); text = strip_tags_text(hm.group(2))
            if not text: continue
            if text.lower() in {"share","related articles","recommended","read more","comments"}: continue
            norm = text.lower().strip()
            if norm in seen_text: continue
            seen_text.add(norm); blocks.append({"type": level, "content": text}); continue

        is_embed = any(tag.lower().startswith(t) for t in ("<blockquote","<iframe","<video","<figure"))
        if is_embed:
            emb = make_embed(tag)
            if emb: blocks.append({"type": "embed", "content": emb, "raw": tag}); continue

        pm = re.match(r"<p[^>]*>(.*?)</p>", tag, re.I|re.S)
        if pm:
            inner_html = pm.group(1).strip()
            text_plain = strip_tags_text(inner_html)
            if not text_plain or len(text_plain.split()) < 5: continue
            if re.match(r"^https?://[^\s]+$", text_plain): continue
            junk_pats = [r"follow us", r"share this", r"copy link", r"read more",
                         r"newsletter", r"subscribe", r"sign up", r"privacy policy"]
            if any(re.search(p, text_plain.lower()) for p in junk_pats) and len(text_plain.split()) <= 20: continue
            norm = text_plain.lower().strip()
            if norm in seen_text: continue
            if h1_lower and SequenceMatcher(None, h1_lower, norm[:len(h1_lower)]).ratio() >= 0.85: continue
            seen_text.add(norm)
            para_html = clean_para_html(inner_html)
            if para_html: blocks.append({"type": "p", "content": para_html, "plain": text_plain})
    return blocks

def _trim_to_words(text, max_words=20):
    return " ".join(re.sub(r"\s+", " ", text or "").strip().split()[:max_words])

def _trim_words(text, limit, chars=False):
    text = re.sub(r"\s+", " ", text or "").strip()
    if chars:
        if len(text) <= limit: return text
        cut = text[:limit].rstrip()
        return (cut.rsplit(" ", 1)[0] if " " in cut else cut).rstrip(" ,.-:;")
    return " ".join(text.split()[:limit]).strip()

def _make_slug(title):
    slug = re.sub(r"[^a-z0-9\s-]", "", title.lower())
    slug = re.sub(r"\s+", "-", slug).strip("-")
    return re.sub(r"-{2,}", "-", slug)

def _make_keyphrase(title):
    return " ".join(re.sub(r"[^\w\s-]", "", title).split()[:10]).strip()

def _seo_title_options(title):
    base = re.sub(r"\s+", " ", title).strip()
    if not base: return []
    opts = [_trim_words(base, 70, chars=True),
            _trim_words(base + " | Full Report", 70, chars=True),
            _trim_words(base + " | Key Updates", 70, chars=True)]
    out, seen = [], set()
    for x in opts:
        if x and x.lower() not in seen: out.append(x); seen.add(x.lower())
    return out[:4]

def _meta_options(intro, title):
    src = re.sub(r"\s+", " ", intro or title).strip()
    if not src: return []
    opts = [_trim_words(src, 160, chars=True), _trim_words(title + " — " + src, 160, chars=True)]
    out, seen = [], set()
    for x in opts:
        if x and x.lower() not in seen: out.append(x); seen.add(x.lower())
    return out[:3]

def _build_short_caption(h1, intro, struct):
    def _clean(t): return re.sub(r"\s+", " ", (t or "").strip(" .,:-"))
    h1_part = _clean(h1) if h1 else ""
    intro_words = (intro or "").split(); snippet = " ".join(intro_words[:80])
    for punct in (".","!","?"):
        last = snippet.rfind(punct)
        if last > len(snippet) // 2: snippet = snippet[:last+1]; break
    else:
        snippet = " ".join(intro_words[:100])
    snippet = _clean(snippet)
    cap = f"{h1_part}. {snippet}" if h1_part and snippet else (h1_part or snippet)
    if len(cap) > 160:
        cut = cap[:160]; last_space = cut.rfind(" ")
        cap = cut[:last_space].rstrip(" .,:-") if last_space > 80 else cut.rstrip(" .,:-")
    cap = cap.strip(" .,:-")
    if cap and not cap.endswith((".", "!", "?")): cap += "."
    return cap

def _build_hashtags(h1, struct):
    words = re.findall(r"[A-Za-z]{4,}", h1 + " " + " ".join(
        s.get("h2", "") for s in struct))
    tags = ["#" + w.lower() for w in dict.fromkeys(words) if len(w) >= 4]
    return " ".join(tags[:8])

# ── Core article processor ─────────────────────────────────────────────────────
def process_article_text(raw_input: str) -> dict:
    looks_html = bool(re.search(r"<(p|h[1-6]|div|article|body|html)\b", raw_input, re.I))
    blocks = []
    if looks_html:
        cleaned = _sanitize_wp_html(raw_input)
        blocks = _parse_html_blocks(cleaned)
    else:
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', raw_input) if p.strip()]
        for i, p in enumerate(paragraphs):
            if i == 0: blocks.append({"type": "h1", "content": _trim_to_words(p, 20)})
            else: blocks.append({"type": "p", "content": p, "plain": p})

    h1 = ""; intro = ""; struct = []; current_h2 = None; current_h3 = None

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
            current_h3 = {"h3": title, "h4": "", "body": ""}
            sec["subsections"].append(current_h3)
        return current_h3

    for b in blocks:
        btype = b.get("type"); content = (b.get("content") or "").strip()
        if not content: continue
        if btype == "h1":
            if not h1: h1 = content
            continue
        if btype == "h2":
            current_h2 = {"h2": content, "subsections": []}; struct.append(current_h2); current_h3 = None; continue
        if btype in ("h3","h4"):
            sec = ensure_section(""); current_h3 = {"h3": content, "h4": "", "body": ""}; sec["subsections"].append(current_h3); continue
        if btype == "embed":
            sub = ensure_sub("")
            if sub["body"].strip(): sub["body"] += "\n\n"
            sub["body"] += f"__EMBED__{content}__EMBED__"; continue
        if btype == "p":
            plain = (b.get("plain") or "").strip()
            if not intro and plain: intro = plain; continue
            sub = ensure_sub("")
            if sub["body"].strip(): sub["body"] += "\n\n"
            sub["body"] += content; continue

    if not h1 and intro: h1 = _trim_to_words(intro, 20)

    seo_title_opts = _seo_title_options(h1)
    meta_opts = _meta_options(intro, h1)
    short_caption = _build_short_caption(h1, intro, struct)
    hashtags = _build_hashtags(h1, struct)
    focus_keyphrase = _make_keyphrase(h1)
    slug = _make_slug(h1)

    # Build WP HTML
    wp_html = _build_wp_html(h1, intro, struct)

    # Build rich output text for display (matches desktop output panel)
    output_sections = _build_output_text(h1, intro, struct, focus_keyphrase,
                                          seo_title_opts, meta_opts, short_caption, hashtags, slug)

    return {
        "h1": h1, "intro": intro, "slug": slug,
        "focus_keyphrase": focus_keyphrase,
        "seo_title_options": seo_title_opts,
        "meta_options": meta_opts,
        "short_caption": short_caption,
        "hashtags": hashtags,
        "wp_html": wp_html,
        "output_sections": output_sections,
        "language": _detect_language(raw_input),
        "struct": struct,
    }

def _build_output_text(h1, intro, struct, fk, seo_titles, metas, caption, hashtags, slug):
    """Build the structured output data that the frontend renders."""
    lines = []
    if h1:        lines.append({"tag": "h1_label", "text": "H1 TITLE"}); lines.append({"tag": "h1", "text": h1})
    if intro:     lines.append({"tag": "intro_label", "text": "INTRO"}); lines.append({"tag": "intro", "text": intro})
    for sec in struct:
        h2 = sec.get("h2", "")
        if h2: lines.append({"tag": "h2_label", "text": "H2"}); lines.append({"tag": "h2", "text": h2})
        for sub in sec.get("subsections", []):
            h3 = sub.get("h3", "")
            if h3: lines.append({"tag": "h3_label", "text": "H3"}); lines.append({"tag": "h3", "text": h3})
            body = sub.get("body", "")
            if body:
                for chunk in [x.strip() for x in body.split("\n\n") if x.strip()]:
                    if chunk.startswith("__EMBED__") and chunk.endswith("__EMBED__"):
                        url = chunk[9:-9].strip()
                        info = EmbedHelper.detect(url)
                        etype = info.get("type") or "generic"
                        tag = f"embed_{etype}"
                        lines.append({"tag": tag, "text": f"  {info['icon']}  {info['label']}", "url": url})
                    else:
                        plain = strip_tags_text(chunk)
                        if plain: lines.append({"tag": "body", "text": plain})
    return lines

# ── Build WordPress HTML (identical to desktop) ────────────────────────────────
def _build_wp_html(h1, intro, struct):
    if not h1 and not intro and not struct: return ""
    esc = lambda v: html.escape(str(v), quote=True)
    parts = []
    H1_S   = 'font-family:Arial,sans-serif;font-size:clamp(28px,5vw,42px);font-weight:800;color:#111111;margin:0 0 20px 0;line-height:1.2;text-align:center;'
    INTRO_S= 'font-size:clamp(16px,3.5vw,20px);line-height:1.8;color:#444444;margin:0 0 24px 0;font-style:italic;text-align:center;'
    H2_S   = 'font-family:Arial,sans-serif;font-size:clamp(20px,4vw,30px);font-weight:800;color:#111111;margin:36px 0 14px 0;line-height:1.25;border-left:4px solid #2563eb;padding-left:12px;'
    H3_S   = 'font-family:Arial,sans-serif;font-size:clamp(17px,3.2vw,24px);font-weight:700;color:#222222;margin:24px 0 10px 0;line-height:1.3;'
    P_S    = 'font-size:clamp(15px,3vw,19px);line-height:1.85;color:#333333;margin:0 0 20px 0;'
    WRAP   = 'max-width:800px;margin:0 auto;padding:0 16px;font-family:Georgia,"Times New Roman",serif;color:#222222;font-size:18px;line-height:1.8;'
    embed_count = 0
    in_wrap = False

    def open_w():
        nonlocal in_wrap
        if not in_wrap: parts.append(f'<div style="{WRAP}">'); in_wrap = True

    def close_w():
        nonlocal in_wrap
        if in_wrap: parts.append('</div>'); in_wrap = False

    def wp_embed_block(url, provider, media_type):
        nonlocal embed_count; embed_count += 1
        safe_json_url = html.escape(url, quote=True); safe_html_url = html.escape(url)
        fig_style  = 'text-align:center !important;margin:28px auto !important;display:table !important;max-width:560px;width:100%;'
        wrap_style = 'text-align:center !important;margin:0 auto !important;max-width:560px;width:100%;'
        return (f'\n<!-- wp:embed {{"url":"{safe_json_url}","type":"{media_type}","providerNameSlug":"{provider}","responsive":true,"className":"aligncenter"}} -->\n'
                f'<figure class="wp-block-embed is-type-{media_type} is-provider-{provider} wp-block-embed-{provider} aligncenter" style="{fig_style}"><div class="wp-block-embed__wrapper" style="{wrap_style}">{safe_html_url}</div></figure>\n'
                f'<!-- /wp:embed -->\n')

    def process_embed(embed_raw):
        info = EmbedHelper.detect(embed_raw)
        media_map = {"twitter": ("twitter","rich"), "youtube": ("youtube","video"), "facebook": ("facebook","video")}
        if info["type"] in media_map:
            canonical_url = (info.get("src") or "").strip()
            if canonical_url:
                provider, media_type = media_map[info["type"]]
                return wp_embed_block(canonical_url, provider, media_type)
        if embed_raw.startswith("http"):
            info2 = EmbedHelper.detect(embed_raw)
            if info2.get("type") in media_map:
                canonical_url = (info2.get("src") or embed_raw).strip()
                if canonical_url:
                    provider, media_type = media_map[info2["type"]]
                    return wp_embed_block(canonical_url, provider, media_type)
        return ""

    open_w()
    if h1:    parts.append(f'<h1 style="{H1_S}">{esc(h1)}</h1>')
    if intro: parts.append(f'<p style="{INTRO_S}">{esc(intro)}</p>')

    for sec in struct:
        if sec.get("h2"):
            open_w(); parts.append(f'<h2 style="{H2_S}">{esc(sec["h2"])}</h2>')
        for sub in sec.get("subsections", []):
            if sub.get("h3"):
                open_w(); parts.append(f'<h3 style="{H3_S}">{esc(sub["h3"])}</h3>')
            body_text = sub.get("body", "")
            for chunk in [x.strip() for x in body_text.split("\n\n") if x.strip()]:
                if chunk.startswith("__EMBED__") and chunk.endswith("__EMBED__"):
                    embed_raw = chunk[9:-9].strip()
                    close_w(); parts.append(process_embed(embed_raw))
                else:
                    open_w()
                    chunk_clean = re.sub(r"\s+", " ", chunk.replace("\n", " ")).strip()
                    if not chunk_clean: continue
                    if re.search(r"<a\b|<strong|<em|<b>|<i>", chunk_clean, re.I):
                        parts.append(f'<p style="{P_S}">{chunk_clean}</p>')
                    else:
                        parts.append(f'<p style="{P_S}">{html.escape(chunk_clean, quote=False)}</p>')

    close_w()
    result = "\n".join(parts).strip()
    if embed_count > 0:
        result += (f'\n\n<!-- \n'
                   f'  ✅ This HTML contains {embed_count} embed(s) as WordPress oEmbed URLs.\n'
                   f'  📋 PASTE INSTRUCTIONS:\n'
                   f'     • Classic Editor → "Text" tab: Paste → WordPress auto-embeds URLs ✓\n'
                   f'     • Block Editor: Paste → WordPress auto-converts URLs to embed blocks ✓\n'
                   f'-->')
    result = rewrite_twitter_embed_urls(result)
    return result

# ── Image optimization ─────────────────────────────────────────────────────────
def optimize_image_for_api(pil_image, max_side=1280, jpeg_quality=82):
    img = pil_image.copy().convert("RGB")
    w, h = img.size; longest = max(w, h)
    if longest > max_side:
        scale = max_side / float(longest)
        img = img.resize((max(1, int(w*scale)), max(1, int(h*scale))), Image.LANCZOS)
    bio = io.BytesIO(); img.save(bio, format="JPEG", quality=jpeg_quality, optimize=True)
    return bio.getvalue(), "image/jpeg"

def _fallback_image_seo(scene_notes="", filename=""):
    seed = " ".join([scene_notes or "", os.path.splitext(os.path.basename(filename or ""))[0]])
    seed = re.sub(r"[_\-]+", " ", html_mod.unescape(seed))
    seed = re.sub(r"\s+", " ", seed).strip()
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9'\-]{2,}", seed)
    stop = {"image","photo","news","report","article","homepage","banner","webp","jpg","jpeg","png","crop","img"}
    uniq = []; seen = set()
    for t in tokens:
        if t.lower() in seen or t.lower() in stop: continue
        seen.add(t.lower()); uniq.append(t)
    proper = [t for t in uniq if t[:1].isupper()]
    subject = " ".join(proper[:2]).strip() or " ".join(uniq[:4]).strip() or "political figure"
    alt_text  = _clean_field(f"{subject} speaking in a news photo", max_words=16, mode="alt")
    img_title = _clean_field(subject or "News Photo", max_words=10, mode="title")
    caption   = _clean_field(f"{subject} is shown speaking in a news image related to the article", max_words=24, mode="caption")
    if len(alt_text) < 8:  alt_text  = "political figure speaking in a news photo"
    if len(img_title) < 4: img_title = "News Photo"
    if len(caption) < 12:  caption   = "Political figure is shown speaking in a news image related to the article."
    return alt_text, img_title, caption

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
    if not key: return jsonify({"ok": False, "error": "API key is empty"}), 400
    try:
        verify_key(key); session["api_key"] = key
        return jsonify({"ok": True, "message": "✓ Key is valid"})
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
    if not url: return jsonify({"ok": False, "error": "No URL provided"}), 400
    if not url.startswith("http"): url = "https://" + url
    url = re.sub(r"[?&](utm_\w+|fbclid|aem_\w*|ref|source|medium|campaign)=[^&]*", "", url).rstrip("?&")

    STRATEGIES = [
        {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36","Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8","Accept-Language":"en-US,en;q=0.9","Accept-Encoding":"gzip, deflate, br","Cache-Control":"no-cache"},
        {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0","Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
        {"User-Agent":"Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)","Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
    ]
    html_content = None; last_err = None
    for hdrs in STRATEGIES:
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw_bytes = resp.read(); ct = resp.headers.get("Content-Type", "")
                charset = _smart_charset(raw_bytes, ct); html_content = _smart_decode(raw_bytes, charset)
            body_lower = html_content.lower()
            blocked = any(kw in body_lower for kw in ["access denied","403 forbidden","blocked","captcha","cloudflare","enable javascript"])
            if blocked and len(html_content) < 8000: html_content = None; time.sleep(0.4); continue
            break
        except Exception as e: last_err = e; time.sleep(0.3)

    if not html_content:
        return jsonify({"ok": False, "error": str(last_err) or "All fetch strategies failed — paste article manually"}), 400

    lang = _detect_language(html_content)
    return jsonify({"ok": True, "html": html_content, "language": lang, "url": url})

@app.route("/api/process-article", methods=["POST"])
def api_process_article():
    data = request.get_json(force=True) or {}
    raw = (data.get("text") or "").strip()
    if not raw: return jsonify({"ok": False, "error": "No article text provided"}), 400
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
    if not api_key: return jsonify({"ok": False, "error": "No API key. Open ⚙ API Settings and save your key."}), 400
    if not article_text: return jsonify({"ok": False, "error": "No article text provided"}), 400

    article = re.sub(r"\s+", " ", article_text).strip()[:900]
    tone = random.choice(["direct", "search-friendly", "newsy"])
    prompt = f"""Return ONLY valid JSON in {language}.

Keys:
{{
  "focus_keyphrase": "2-4 word keyphrase in {language}, lowercase",
  "seo_title_1": "50-60 chars",
  "seo_title_2": "50-60 chars",
  "seo_title_3": "50-60 chars",
  "meta_description_1": "120-160 chars",
  "meta_description_2": "120-160 chars",
  "meta_description_3": "120-160 chars"
}}

Rules: concise, catchy, Yoast-friendly, no markdown, tone: {tone}

ARTICLE:
{article}"""

    model_plan = [(FAST_SEO_FIELDS_MODEL, 0.20, FAST_AI_TIMEOUT, FAST_SEO_FIELD_MAX_TOKENS),
                  (SEO_MODEL, 0.18, 28, 280)]
    seen_models = set(); data_out = None; last_err = None

    for model, temp, to_sec, max_tok in model_plan:
        model = (model or "").strip()
        if not model or model in seen_models: continue
        seen_models.add(model)
        try:
            resp = chat_completion(api_key, model,
                messages=[{"role":"user","content":prompt}],
                temperature=temp, response_format={"type":"json_object"},
                timeout=to_sec, max_tokens=max_tok)
            data_out = parse_json(extract_content(resp))
            if isinstance(data_out, dict) and any(data_out.get(k) for k in ("focus_keyphrase","seo_title_1","meta_description_1")):
                break
        except Exception as e:
            last_err = e; data_out = None

    if not isinstance(data_out, dict):
        return jsonify({"ok": False, "error": str(last_err) if last_err else "AI SEO fields failed"}), 500

    def cap_title(t):
        t = str(t or "").strip()
        if len(t) > 60: t = (t[:60].rsplit(" ", 1)[0] if " " in t[:60] else t[:60]).rstrip(" :-,")
        return t

    fk     = str(data_out.get("focus_keyphrase","")).strip()
    title1 = cap_title(data_out.get("seo_title_1",""))
    title2 = cap_title(data_out.get("seo_title_2",""))
    title3 = cap_title(data_out.get("seo_title_3",""))

    def cap_meta(m):
        m = str(m or "").strip()
        return m[:160].rsplit(" ", 1)[0] if len(m) > 160 else m

    meta1 = cap_meta(data_out.get("meta_description_1",""))
    meta2 = cap_meta(data_out.get("meta_description_2",""))
    meta3 = cap_meta(data_out.get("meta_description_3",""))

    return jsonify({"ok": True,
        "focus_keyphrase": fk,
        "seo_titles": [title1, title2, title3],
        "meta_descriptions": [meta1, meta2, meta3]})

@app.route("/api/image-seo", methods=["POST"])
def api_image_seo():
    api_key = (request.form.get("api_key") or session.get("api_key") or "").strip()
    scene_notes = (request.form.get("scene_notes") or "").strip()
    if not api_key:
        return jsonify({"ok": False, "error": "No API key. Open ⚙ API Settings and save your key."}), 400
    if "image" not in request.files:
        return jsonify({"ok": False, "error": "No image uploaded"}), 400

    file = request.files["image"]; filename = file.filename or ""
    try:
        img = Image.open(file.stream)
        img_bytes, media_type = optimize_image_for_api(img)
        b64 = base64.b64encode(img_bytes).decode()
        data_url = f"data:{media_type};base64,{b64}"
        scene_hint = f'\n\nContext/keyword hint from editor: "{scene_notes}"' if scene_notes else ""
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

Output ONLY the JSON object. No markdown, no explanation.{scene_hint}"""

        last_err = None
        for model in [v for v in [VISION_MODEL, VISION_FALLBACK_MODEL] if v]:
            try:
                resp = chat_completion(api_key, model,
                    messages=[{"role":"user","content":[
                        {"type":"text","text":prompt},
                        {"type":"image_url","image_url":{"url":data_url}}
                    ]}],
                    temperature=0.15, top_p=0.85,
                    response_format={"type":"json_object"}, timeout=120)
                raw_data = parse_json(extract_content(resp))
                alt_text  = _clean_field(raw_data.get("alt_text",""),  max_words=20, mode="alt")
                img_title = _clean_field(raw_data.get("img_title",""), max_words=15, mode="title")
                caption   = _clean_field(raw_data.get("caption",""),   max_words=40, mode="caption")
                if len(alt_text) < 10 or len(img_title) < 5 or len(caption) < 15:
                    alt_text, img_title, caption = _fallback_image_seo(scene_notes, filename)
                alt_text  = _sanitize(alt_text,  90, "alt")
                img_title = _sanitize(img_title, 90, "title")
                caption   = _sanitize(caption,  180, "caption")
                return jsonify({"ok": True, "alt_text": alt_text,
                                "img_title": img_title, "caption": caption,
                                "model": model.split("/")[-1]})
            except Exception as e:
                last_err = e

        raise RuntimeError(str(last_err) if last_err else "All models failed")
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/export-image", methods=["POST"])
def api_export_image():
    """Export image optimized to under 100KB — mirrors desktop export_under_100kb()"""
    if "image" not in request.files:
        return jsonify({"ok": False, "error": "No image"}), 400
    try:
        from PIL import ImageEnhance
        file = request.files["image"]
        img = Image.open(file.stream).convert("RGB")
        w, h = img.size
        if w < 1400:
            s = max(1.2, 1400 / max(w, 1))
            img = img.resize((int(w * s), int(h * s)), Image.LANCZOS)
        img = ImageEnhance.Sharpness(img).enhance(1.35)
        img = ImageEnhance.Contrast(img).enhance(1.03)
        best_bytes = best_q = None
        for q in range(95, 14, -5):
            buf = io.BytesIO(); img.save(buf, "JPEG", quality=q, optimize=True)
            if len(buf.getvalue()) / 1024 <= 100:
                best_bytes = buf.getvalue(); best_q = q; break
        if best_bytes is None:
            tmp = img.copy(); q = 85
            while True:
                buf = io.BytesIO(); tmp.save(buf, "JPEG", quality=q, optimize=True)
                if len(buf.getvalue()) / 1024 <= 100 or min(tmp.size) < 200:
                    best_bytes = buf.getvalue(); best_q = q; break
                ew, eh = tmp.size; tmp = tmp.resize((int(ew*.92), int(eh*.92)), Image.LANCZOS)
        from flask import Response
        size_kb = len(best_bytes) / 1024
        resp = Response(best_bytes, mimetype="image/jpeg")
        resp.headers["Content-Disposition"] = 'attachment; filename="optimized.jpg"'
        resp.headers["X-Image-Quality"] = str(best_q)
        resp.headers["X-Image-Size-KB"] = f"{size_kb:.1f}"
        return resp
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
