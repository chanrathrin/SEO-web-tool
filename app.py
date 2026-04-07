# ============================================================
#  WordPress SEO Studio — Web Edition (100% faithful port)
#  Tab 1: SEO Formatter  (article → Yoast fields + WP HTML)
#  Tab 2: Image SEO      (upload/crop/AI generate)
# ============================================================
import os, io, re, html, json, base64, time, random, urllib.request, urllib.error
from difflib import SequenceMatcher
import html as html_mod
import requests
from requests.adapters import HTTPAdapter
from flask import Flask, request, jsonify, render_template, session
from PIL import Image, ImageEnhance

# ── Together AI config (exact copy from desktop) ───────────────────────────────
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
FAST_SEO_FIELDS_FALLBACK_MODEL = ""
FAST_AI_TIMEOUT           = 24
FAST_SEO_FIELD_MAX_TOKENS = 220
FORCED_TWITTER_USERNAME   = "RepSwalwell"

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(32))

# ══════════════════════════════════════════════════════════════
#  API SESSION
# ══════════════════════════════════════════════════════════════
_API_SESSION = None
def get_api_session():
    global _API_SESSION
    if _API_SESSION is not None and API_USE_SESSION: return _API_SESSION
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
    payload = {"model": model, "messages": messages, "temperature": temperature, "top_p": top_p}
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
                if API_ENABLE_CHEAP_FALLBACK and model == SEO_MODEL and r.status_code in (429,500,502,503,504):
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
    candidates = [raw, raw.replace("```json","").replace("```","").strip()]
    m = re.search(r"\{.*\}", candidates[-1], re.DOTALL)
    if m: candidates.append(m.group(0).strip())
    for c in candidates:
        try:
            d = json.loads(c)
            if isinstance(d, dict): return d
        except: pass
    raise ValueError(f"Cannot parse JSON. Raw: {raw[:200]}")

# ══════════════════════════════════════════════════════════════
#  CHARSET / DECODE (exact copy from desktop)
# ══════════════════════════════════════════════════════════════
def _smart_charset(raw_bytes: bytes, content_type: str = "") -> str:
    m = re.search(r"charset=([\w-]+)", content_type, re.I)
    if m:
        cs = m.group(1).strip().lower()
        if cs not in ("utf-8","utf8"): return cs
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

# ══════════════════════════════════════════════════════════════
#  TWITTER HELPERS (exact copy)
# ══════════════════════════════════════════════════════════════
def _forced_public_twitter_url(tweet_id: str, fallback_url: str = "") -> str:
    tweet_id = str(tweet_id or "").strip()
    fallback_url = str(fallback_url or "").strip()
    forced_username = str(FORCED_TWITTER_USERNAME or "").strip().lstrip("@")
    if tweet_id and forced_username:
        return f"https://twitter.com/{forced_username}/status/{tweet_id}"
    if fallback_url: return fallback_url
    if tweet_id: return f"https://twitter.com/i/web/status/{tweet_id}"
    return ""

def rewrite_twitter_embed_urls(html_text: str) -> str:
    html_text = str(html_text or "")
    def _replace_iweb(m): return _forced_public_twitter_url(m.group(1), m.group(0))
    html_text = re.sub(r'https?://(?:www\.)?twitter\.com/i/web/status/(\d+)',
                       _replace_iweb, html_text, flags=re.I)
    def _replace_platform(m):
        url = html_mod.unescape(m.group(0))
        tid = re.search(r'[?&](?:id|tweetId)=(\d+)', url, re.I)
        if not tid: tid = re.search(r'data-tweet-id=["\'](\d+)["\']', url, re.I)
        if tid: return _forced_public_twitter_url(tid.group(1), url)
        return url
    html_text = re.sub(r'https?://platform\.twitter\.com/embed/Tweet\.html\?[^"\'\s<]+',
                       _replace_platform, html_text, flags=re.I)
    return html_text

def optimize_image_for_api(pil_image, max_side=1280, jpeg_quality=82):
    img = pil_image.copy().convert("RGB")
    w, h = img.size; longest = max(w, h)
    if longest > max_side:
        scale = max_side / float(longest)
        img = img.resize((max(1,int(w*scale)), max(1,int(h*scale))), Image.LANCZOS)
    bio = io.BytesIO(); img.save(bio, format="JPEG", quality=jpeg_quality, optimize=True)
    return bio.getvalue(), "image/jpeg"

# ══════════════════════════════════════════════════════════════
#  EMBED HELPER (exact copy from desktop)
# ══════════════════════════════════════════════════════════════
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
    def _extract_public_twitter_url(cls, raw):
        raw = cls._decode_url(raw)
        direct = re.search(
            r'https?://(?:www\.)?(?:twitter|x)\.com/([A-Za-z0-9_]+)/status(?:es)?/(\d+)', raw, re.I)
        if direct:
            return f"https://twitter.com/{direct.group(1)}/status/{direct.group(2)}"
        for key in ("url","href"):
            m = re.search(rf'[?&]{key}=([^&"\']+)', raw, re.I)
            if m:
                decoded = cls._decode_url(m.group(1))
                d2 = re.search(
                    r'https?://(?:www\.)?(?:twitter|x)\.com/([A-Za-z0-9_]+)/status(?:es)?/(\d+)', decoded, re.I)
                if d2: return f"https://twitter.com/{d2.group(1)}/status/{d2.group(2)}"
        src_m = re.search(r'src=["\']([^"\']+)["\']', raw, re.I)
        if src_m:
            found = cls._extract_public_twitter_url(cls._decode_url(src_m.group(1)))
            if found: return found
        return ""

    @classmethod
    def _extract_tweet_id(cls, raw):
        raw = cls._decode_url(raw)
        patterns = [
            r'https?://(?:www\.)?(?:twitter|x)\.com/[A-Za-z0-9_]+/status(?:es)?/(\d+)',
            r'(?:twitter|x)\.com/i/web/status/(\d+)',
            r'data-tweet-id=["\'](\d+)["\']',
            r'[?&](?:id|tweetId)=(\d+)',
            r'https?://publish\.twitter\.com/\?url=.*?/status(?:es)?/(\d+)',
        ]
        for pat in patterns:
            m = re.search(pat, raw, re.I)
            if m: return m.group(1)
        src_m = re.search(r'src=["\']([^"\']+)["\']', raw, re.I)
        if src_m:
            src = cls._decode_url(src_m.group(1))
            for pat in patterns:
                m = re.search(pat, src, re.I)
                if m: return m.group(1)
        return ""

    @classmethod
    def _normalize_twitter_public_url(cls, raw):
        public_url = cls._extract_public_twitter_url(raw)
        if public_url: return public_url
        tweet_id = cls._extract_tweet_id(raw)
        return _forced_public_twitter_url(tweet_id) if tweet_id else ""

    @classmethod
    def detect(cls, raw):
        raw = str(raw or ""); raw_lower = raw.lower()
        for pat in cls.YOUTUBE_PATTERNS:
            m = re.search(pat, raw, re.I)
            if m:
                vid_id = m.group(1).split("&")[0].split("?")[0].strip()
                watch_url = f"https://www.youtube.com/watch?v={vid_id}"
                return {"type":"youtube","icon":"▶","label":f"YouTube Video  [ID: {vid_id}]",
                        "html":watch_url,"html_classic":watch_url,"src":watch_url,"vid_id":vid_id}
        tw_url = cls._normalize_twitter_public_url(raw)
        if tw_url:
            tweet_id = cls._extract_tweet_id(raw)
            return {"type":"twitter","icon":"🐦","label":f"Twitter/X Post  [ID: {tweet_id}]" if tweet_id else "Twitter/X Post",
                    "html":tw_url,"html_classic":tw_url,"src":tw_url,"tweet_id":tweet_id}
        for pat in cls.FACEBOOK_PATTERNS:
            m = re.search(pat, raw, re.I)
            if m:
                fb_url_m = re.search(r'https?://(?:www\.)?facebook\.com/[^\s"\'<>]+', raw, re.I)
                if fb_url_m:
                    fb_url = fb_url_m.group(0).rstrip('/"\'')
                    return {"type":"facebook","icon":"📘","label":"Facebook Video",
                            "html":fb_url,"html_classic":fb_url,"src":fb_url}
        src_m = re.search(r'src=["\']([^"\'>\s]+)["\']', raw, re.I)
        if src_m and "<iframe" in raw_lower:
            src = cls._decode_url(src_m.group(1))
            yt = re.search(r'(?:youtube\.com/embed/|youtu\.be/|youtube\.com/watch\?v=)([\w-]+)', src, re.I)
            if yt:
                vid_id = yt.group(1); watch_url = f"https://www.youtube.com/watch?v={vid_id}"
                return {"type":"youtube","icon":"▶","label":f"YouTube Video  [ID: {vid_id}]",
                        "html":watch_url,"html_classic":watch_url,"src":watch_url,"vid_id":vid_id}
            tw_url = cls._normalize_twitter_public_url(src)
            if tw_url:
                tweet_id = cls._extract_tweet_id(src)
                return {"type":"twitter","icon":"🐦","label":f"Twitter/X Post  [ID: {tweet_id}]",
                        "html":tw_url,"html_classic":tw_url,"src":tw_url,"tweet_id":tweet_id}
            return {"type":"generic","icon":"▶","label":"Embedded Media","html":src,"html_classic":src,"src":src}
        return {"type":None,"icon":"▶","label":"Embedded Media","html":raw,"html_classic":raw,"src":""}

# ══════════════════════════════════════════════════════════════
#  SEO PROCESSOR — all methods ported 1:1 from desktop
# ══════════════════════════════════════════════════════════════
class SEOProcessor:
    """Contains all the exact business logic from SEOFormatterTab, ported to standalone."""

    @staticmethod
    def _detect_language(text: str) -> str:
        sample = re.sub(r"<[^>]+>", " ", text)
        sample = re.sub(r"https?://\S+", " ", sample)
        sample = re.sub(r"\s+", " ", sample).strip()[:2000]
        SCRIPTS = [
            ("Khmer",    0x1780,0x17FF,0.03), ("Arabic",   0x0600,0x06FF,0.05),
            ("Thai",     0x0E00,0x0E7F,0.05), ("Hindi",    0x0900,0x097F,0.05),
            ("Korean",   0xAC00,0xD7AF,0.05), ("Japanese", 0x3040,0x309F,0.02),
            ("Japanese", 0x30A0,0x30FF,0.02), ("Chinese",  0x4E00,0x9FFF,0.10),
            ("Russian",  0x0400,0x04FF,0.05),
        ]
        total = max(len(sample), 1); seen = set()
        for name, start, end, min_ratio in SCRIPTS:
            if name in seen: continue
            count = sum(1 for ch in sample if start <= ord(ch) <= end)
            if count / total >= min_ratio: seen.add(name); return name
        freq = {}
        for w in sample.lower().split():
            w = re.sub(r"[^a-zàáâãäåæçèéêëìíîïðñòóôõöùúûüý]", "", w)
            if len(w) >= 3: freq[w] = freq.get(w, 0) + 1
        LANG_WORDS = {
            "French":     ["le","la","les","de","du","des","est","dans","pour","avec"],
            "Spanish":    ["el","la","los","de","del","que","en","es","con","por"],
            "Portuguese": ["de","da","do","que","em","para","com","uma","por","não"],
            "German":     ["der","die","das","und","von","ist","mit","dem","für","auf"],
            "Italian":    ["il","la","di","che","per","una","non","del","con","sono"],
            "Vietnamese": ["của","và","là","có","trong","được","không","này","cho","với"],
            "Indonesian": ["yang","dan","di","ke","dari","untuk","dengan","ini","pada","ada"],
        }
        best_lang, best_score = "English", 0
        for lang, markers in LANG_WORDS.items():
            score = sum(freq.get(w, 0) for w in markers)
            if score > best_score: best_score = score; best_lang = lang
        return best_lang

    @staticmethod
    def _looks_html(text):
        return bool(re.search(r"<(p|h[1-6]|div|article|body|html|ul|ol|blockquote|iframe|figure)\b",
                               text, re.I))

    @staticmethod
    def _trim_to_words(text, max_words=20):
        words = (text or "").split()
        if len(words) <= max_words: return " ".join(words).strip(" .,:-")
        trimmed = " ".join(words[:max_words])
        for punct in (".","!","?"):
            idx = trimmed.rfind(punct)
            if idx > len(trimmed) // 2: return trimmed[:idx+1].strip()
        return trimmed.rstrip(" .,:-")

    @staticmethod
    def _trim_words(text, limit, chars=False):
        text = re.sub(r"\s+", " ", text or "").strip()
        if chars:
            if len(text) <= limit: return text
            cut = text[:limit].rstrip()
            return (cut.rsplit(" ", 1)[0] if " " in cut else cut).rstrip(" ,.-:;")
        return " ".join(text.split()[:limit]).strip()

    @staticmethod
    def _norm(text, title=False):
        text = re.sub(r"[_-]+", " ", text or ""); text = re.sub(r"\s+", " ", text).strip(" .,:;|-_")
        if not text: return ""
        low = text.lower()
        low = re.sub(r"(?:untitled|design|image|photo|copy|edited|edit|thumb|thumbnail|final|new|jpeg|jpg|png|webp)", " ", low)
        low = re.sub(r"\d{2,}", " ", low); low = re.sub(r"\s+", " ", low).strip() or text.strip()
        if title:
            small = {"and","or","with","at","in","on","for","to","of","the","a","an"}
            return " ".join(w if (i > 0 and w in small) else w.capitalize()
                            for i, w in enumerate(low.split()))
        return low

    @staticmethod
    def _make_slug(title):
        slug = re.sub(r"[^a-z0-9\s-]", "", title.lower())
        slug = re.sub(r"\s+", "-", slug).strip("-")
        return re.sub(r"-{2,}", "-", slug)

    @staticmethod
    def _make_keyphrase(title):
        return " ".join(re.sub(r"[^\w\s-]", "", title).split()[:10]).strip()

    @classmethod
    def _seo_title_options(cls, title):
        base = re.sub(r"\s+", " ", title).strip()
        if not base: return []
        opts = [cls._trim_words(base, 70, chars=True),
                cls._trim_words(base + " | Full Report", 70, chars=True),
                cls._trim_words(base + " | Key Updates", 70, chars=True)]
        out, seen = [], set()
        for x in opts:
            if x and x.lower() not in seen: out.append(x); seen.add(x.lower())
        return out[:4]

    @classmethod
    def _meta_options(cls, intro, title):
        src = re.sub(r"\s+", " ", intro or title).strip()
        if not src: return []
        opts = [cls._trim_words(src, 160, chars=True),
                cls._trim_words(title + " — " + src, 160, chars=True)]
        out, seen = [], set()
        for x in opts:
            if x and x.lower() not in seen: out.append(x); seen.add(x.lower())
        return out[:3]

    @classmethod
    def _build_short_caption(cls, h1, intro, struct):
        def _clean(t): return re.sub(r"\s+", " ", (t or "").strip(" .,:-"))
        h1_part = _clean(cls._norm(h1, title=True)) if h1 else ""
        intro_words = (intro or "").split(); snippet = " ".join(intro_words[:80])
        for punct in (".","!","?"):
            last = snippet.rfind(punct)
            if last > len(snippet) // 2: snippet = snippet[:last+1]; break
        else: snippet = " ".join(intro_words[:100])
        snippet = _clean(snippet)
        if h1_part and snippet: cap = f"{h1_part}. {snippet}"
        elif h1_part: cap = h1_part
        else: cap = snippet
        if len(cap) < 120:
            for sec in struct[:1]:
                h2 = _clean(cls._norm(sec.get("h2",""), title=True))
                if h2 and h2.lower() not in cap.lower(): cap = f"{cap} — {h2}"; break
        if len(cap) > 160:
            cut = cap[:160]; last_space = cut.rfind(" ")
            cap = cut[:last_space].rstrip(" .,:-") if last_space > 80 else cut.rstrip(" .,:-")
        cap = cap.strip(" .,:-")
        if cap and not cap.endswith((".","!","?")): cap += "."
        return cap

    @staticmethod
    def _generate_hashtags(full_text: str, h1: str) -> list:
        STOP = {"the","a","an","and","or","but","in","on","at","to","for","of","with","is","are",
                "was","were","be","been","being","have","has","had","do","does","did","will","would",
                "could","should","may","might","shall","can","need","that","this","these","those",
                "it","its","by","from","as","into","through","during","before","after","above",
                "below","up","down","out","off","over","under","again","further","then","once",
                "here","there","when","where","why","how","all","each","every","both","few","more",
                "most","other","some","such","no","not","only","same","so","than","too","very",
                "just","about","also","which","who","whom","what","he","she","they","we","you",
                "i","my","your","his","her","our","their","its","new","one","two","three","get",
                "got","use","used","make","made","take","taken","give","given","said","say","look","see"}
        clean = re.sub(r'<[^>]+>', ' ', full_text)
        clean = re.sub(r"[^\w\s'-]", ' ', clean)
        clean = re.sub(r'\s+', ' ', clean).strip().lower()
        words = clean.split(); total = max(len(words), 1)
        word_scores = {}
        for idx, word in enumerate(words):
            w = re.sub(r"[^a-z0-9']", "", word)
            if len(w) < 4 or w in STOP: continue
            pos_weight = 1.5 if idx/total < 0.20 else 1.0
            word_scores[w] = word_scores.get(w, 0) + pos_weight
        bigram_scores = {}
        for i in range(len(words)-1):
            w1 = re.sub(r"[^a-z0-9']","",words[i]); w2 = re.sub(r"[^a-z0-9']","",words[i+1])
            if len(w1)>=3 and len(w2)>=3 and w1 not in STOP and w2 not in STOP:
                bg = f"{w1} {w2}"; bigram_scores[bg] = bigram_scores.get(bg,0) + 1
        h1_words = set(re.sub(r"[^a-z0-9\s]","",h1.lower()).split())
        for w in list(word_scores.keys()):
            if w in h1_words: word_scores[w] *= 2.0
        candidates = []
        for bg, score in bigram_scores.items():
            if score >= 2:
                tag = "#" + "".join(p.capitalize() for p in bg.split())
                candidates.append((score*1.8, tag, bg))
        for w, score in sorted(word_scores.items(), key=lambda x: -x[1]):
            tag = "#" + w.capitalize()
            already = any(w in bg for _,_,bg in candidates)
            if not already: candidates.append((score, tag, w))
        candidates.sort(key=lambda x: -x[0])
        seen_tags = set(); result = []
        for _, tag, _ in candidates:
            t_lower = tag.lower()
            if t_lower not in seen_tags: seen_tags.add(t_lower); result.append(tag)
            if len(result) == 8: break
        if len(result) < 6:
            for w in sorted(h1_words - STOP, key=lambda x: -len(x)):
                if len(w) >= 4:
                    tag = "#" + w.capitalize()
                    if tag.lower() not in seen_tags: seen_tags.add(tag.lower()); result.append(tag)
                if len(result) == 6: break
        return result[:8] if len(result) >= 6 else result

    @staticmethod
    def _clean_lines(text):
        text = re.sub(r"&nbsp;"," ",(text or "").replace("\r\n","\n"), flags=re.I)
        text = re.sub(r"&#\d+;|&[a-zA-Z]+;"," ",text)
        text = re.sub(r"\u00a0"," ",text)
        text = re.sub(r"[ \t]+"," ",text)
        raw = [l.strip() for l in text.split("\n")]
        out, last_blank = [], True
        for line in raw:
            stripped_tags = re.sub(r"<[^>]+>","",line).strip()
            if line.startswith("<") and not stripped_tags: continue
            if not line:
                if not last_blank: out.append(""); last_blank = True
            else: out.append(line); last_blank = False
        while out and out[-1] == "": out.pop()
        return out

    @staticmethod
    def _strip_seo_lines(lines):
        prefixes = ("Focus Keyphrase:","SEO Title:","Meta Description:","Slug (URL):","Slug:","Short Summary:")
        out = []
        for l in lines:
            s = l.strip()
            if any(s.startswith(p) for p in prefixes): continue
            if re.match(r'^https?://[^\s]+$', s) and "__EMBED__" not in s: continue
            if re.match(r'^(&nbsp;|\s)+$', s, re.I): continue
            text_only = re.sub(r"<[^>]+>","",s).strip()
            if s.startswith("<") and len(s) < 200 and not text_only: continue
            if out and s and out[-1].strip() == s: continue
            out.append(l)
        while out and out[-1] == "": out.pop()
        return out

    @staticmethod
    def _guess_title(lines):
        if not lines: return "Untitled Article"
        return SEOProcessor._trim_to_words(lines[0].strip(), max_words=20)

    @staticmethod
    def _build_intro(lines):
        content = [l for l in lines[1:] if l.strip()]
        if not content: return ""
        parts = []
        for line in content:
            parts.append(line)
            if len(" ".join(parts)) >= 180 or line.endswith((".","!","?")): break
        return SEOProcessor._trim_to_words(" ".join(parts).strip(), max_words=80)

    @staticmethod
    def _split_body(lines):
        paragraphs, current = [], []
        for line in lines[1:]:
            if not line.strip():
                if current: paragraphs.append(" ".join(current).strip()); current = []
            else: current.append(line.strip())
        if current: paragraphs.append(" ".join(current).strip())
        blocks = [p for p in paragraphs if p] or [l for l in lines[1:] if l.strip()]
        if len(blocks) <= 3: return blocks[:3]
        base, extra, secs, idx = len(blocks)//3, len(blocks)%3, [], 0
        for i in range(3):
            take = base + (1 if i < extra else 0)
            merged = "\n\n".join(blocks[idx:idx+take]).strip()
            if merged: secs.append(merged)
            idx += take
        return secs[:3]

    @classmethod
    def _choose_heading(cls, text, seen):
        text = text.replace("\n"," ")
        sentences = re.split(r'(?<=[.!?])\s+', text); ranked = []
        for s in sentences:
            s = re.sub(r"[_-]+"," ",s).strip(' "\'""''.,:;!?-')
            s = re.sub(r"^[^A-Za-z0-9]+","",s)
            words = s.split()
            if len(words) < 4: continue
            score = 4 if 5 <= len(words) <= 10 else (2 if len(words) <= 12 else 0)
            ranked.append((score, s))
        ranked.sort(key=lambda x: -x[0])
        for _, cand in ranked:
            key = cand.lower()
            if key in seen: continue
            if any(SequenceMatcher(None, key, p).ratio() >= 0.72 for p in seen): continue
            seen.add(key); return cand
        return ""

    @classmethod
    def _build_structure(cls, sections):
        struct, seen = [], set()
        for idx, section in enumerate(sections[:3], 1):
            html_h2 = ""; html_h3 = ""
            hm2 = re.search(r"<h2[^>]*>(.*?)</h2>", section, re.I|re.S)
            if hm2:
                html_h2 = re.sub(r"<[^>]+>","",hm2.group(1)).strip()
                section = re.sub(r"<h2[^>]*>.*?</h2>","",section,flags=re.I|re.S)
            hm3 = re.search(r"<h3[^>]*>(.*?)</h3>", section, re.I|re.S)
            if hm3:
                html_h3 = re.sub(r"<[^>]+>","",hm3.group(1)).strip()
                section = re.sub(r"<h3[^>]*>.*?</h3>","",section,flags=re.I|re.S)
            section_plain = re.sub(r"<[^>]+>"," ",section)
            section_plain = re.sub(r"\s+"," ",section_plain).strip()
            parts = [p.strip() for p in section_plain.split("\n\n") if p.strip()]
            if not parts: continue
            h2 = html_h2 or ""; h3 = html_h3 or ""
            if not h2:
                for src in parts[:2]+[section_plain]:
                    h2 = cls._choose_heading(src, seen)
                    if h2: break
            if not h2:
                words = re.sub(r"[_\-<>]+"," ",parts[0]).split()
                words = [w for w in words if len(w)>1]
                h2 = " ".join(words[:8]).strip() or f"Section {idx}"
            h2 = cls._trim_to_words(re.sub(r"<[^>]+>","",h2), max_words=15)
            seen.add(h2.lower().strip())
            subs = [{"h3":h3,"h4":"","body":"\n\n".join(parts).strip()}]
            struct.append({"h2":h2,"subsections":subs})
        return struct[:3]

    @staticmethod
    def _sanitize_wp_html(raw):
        for pat in [r'<script[^>]*>.*?</script>', r'<style[^>]*>.*?</style>',
                    r'<header\b[^>]*>.*?</header>', r'<footer\b[^>]*>.*?</footer>',
                    r'<nav\b[^>]*>.*?</nav>', r'<aside\b[^>]*>.*?</aside>',
                    r'<!--\[if[^>]*>.*?<!\[endif\]-->', r'<!--\s*wp:html\s*-->.*?<!--\s*/wp:html\s*-->']:
            raw = re.sub(pat, ' ', raw, flags=re.I|re.S)
        return raw

    @classmethod
    def _parse_html_blocks(cls, raw):
        def strip_tags_text(t):
            t = re.sub(r"<[^>]+>", " ", str(t or ""))
            return re.sub(r"\s+", " ", html_mod.unescape(t)).strip()

        def clean_para_html(t):
            t = re.sub(r'<script[^>]*>.*?</script>', '', t, flags=re.I|re.S)
            t = re.sub(r'<style[^>]*>.*?</style>', '', t, flags=re.I|re.S)
            KEEP = r'strong|b|em|i|a|br|span|u|s|del|ins|mark|code|sub|sup'
            t = re.sub(rf'<(?!/?(?:{KEEP})\b)[^>]+>', ' ', t, flags=re.I)
            return re.sub(r'\s+', ' ', t).strip()

        def make_embed(raw_tag):
            info = EmbedHelper.detect(raw_tag)
            return info["html"] if info["type"] else raw_tag

        def link_density(inner_html, text):
            if not inner_html or not text: return 0.0
            link_texts = re.findall(r"<a\b[^>]*>(.*?)</a>", inner_html, flags=re.I|re.S)
            link_text = " ".join(strip_tags_text(x) for x in link_texts).strip()
            if not link_text: return 0.0
            return len(link_text) / max(len(text), 1)

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
            page_h1 = re.sub(r"\s+[|\-–—]\s+.*$","",page_h1).strip()
            if page_h1: blocks.append({"type":"h1","content":page_h1})

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

            if tag.startswith("__PRESV_EMBED_START__"):
                embed_html = tag[len("__PRESV_EMBED_START__"):-len("__PRESV_EMBED_END__")].strip()
                if embed_html: blocks.append({"type":"embed","content":embed_html,"raw":embed_html})
                continue

            hm = re.match(r"<(h[1-6])[^>]*>(.*?)</h[1-6]>", tag, re.I|re.S)
            if hm:
                level = hm.group(1).lower(); text = strip_tags_text(hm.group(2))
                if not text: continue
                low = text.lower()
                if low in {"share","related articles","recommended","read more",
                           "follow us","comments","leave a reply"}: continue
                if level == "h1" and blocks and blocks[0]["type"] == "h1":
                    if SequenceMatcher(None, blocks[0]["content"].lower(), text.lower()).ratio() >= 0.80: continue
                norm = text.lower().strip()
                if norm in seen_text and level != "h2": continue
                seen_text.add(norm); blocks.append({"type":level,"content":text}); continue

            is_embed = any(tag.lower().startswith(t) for t in ("<blockquote","<iframe","<video","<figure"))
            if is_embed:
                emb = make_embed(tag)
                if emb: blocks.append({"type":"embed","content":emb,"raw":tag}); continue

            pm = re.match(r"<p[^>]*>(.*?)</p>", tag, re.I|re.S)
            if pm:
                inner_html = pm.group(1).strip()
                segs = re.split(r'(__PRESV_EMBED_START__.*?__PRESV_EMBED_END__)', inner_html, flags=re.S)
                for seg in segs:
                    seg = (seg or '').strip()
                    if not seg: continue
                    if seg.startswith("__PRESV_EMBED_START__") and seg.endswith("__PRESV_EMBED_END__"):
                        embed_html = seg[len("__PRESV_EMBED_START__"):-len("__PRESV_EMBED_END__")].strip()
                        if embed_html: blocks.append({"type":"embed","content":embed_html,"raw":embed_html})
                        continue
                    part_html = seg
                    for emb_pat in (r"<iframe\b[^>]*>.*?</iframe>",r"<video\b[^>]*>.*?</video>",
                                    r"<blockquote\b[^>]*>.*?</blockquote>"):
                        emb_m = re.search(emb_pat, part_html, re.I|re.S)
                        if emb_m:
                            raw_emb = emb_m.group(0); emb = make_embed(raw_emb)
                            if emb: blocks.append({"type":"embed","content":emb,"raw":raw_emb})
                            part_html = re.sub(emb_pat,"",part_html,flags=re.I|re.S); break
                    text_plain = strip_tags_text(part_html)
                    text_plain = re.sub(r'__PRESV_EMBED_START__.*?__PRESV_EMBED_END__',' ',text_plain,flags=re.S).strip()
                    if not text_plain or len(text_plain.split()) < 5: continue
                    if re.match(r"^https?://[^\s]+$", text_plain): continue
                    junk_pats = [r"follow us",r"share this",r"copy link",r"read more",
                                 r"related articles?",r"newsletter",r"subscribe",r"sign up",
                                 r"privacy policy",r"terms of use"]
                    if any(re.search(p,text_plain.lower(),re.I) for p in junk_pats) and len(text_plain.split())<=20: continue
                    if link_density(part_html, text_plain) >= 0.65 and len(text_plain.split()) < 40: continue
                    norm = text_plain.lower().strip()
                    if norm in seen_text: continue
                    if h1_lower and SequenceMatcher(None,h1_lower,norm[:len(h1_lower)]).ratio()>=0.85: continue
                    seen_text.add(norm)
                    para_html = clean_para_html(part_html)
                    para_html = re.sub(r'__PRESV_EMBED_START__.*?__PRESV_EMBED_END__',' ',para_html,flags=re.S).strip()
                    if para_html: blocks.append({"type":"p","content":para_html,"plain":text_plain})
        return blocks

    @classmethod
    def _html_to_plain(cls, raw):
        def save_iframe(m):
            info = EmbedHelper.detect(m.group(0))
            emb_html = info["html"] if info["type"] else m.group(0)
            return f"\n__EMBED__{emb_html}__EMBED__\n"
        t = re.sub(r"<iframe\b[^>]*>.*?</iframe>", save_iframe, raw, flags=re.I|re.S)
        t = re.sub(r"<br\s*/?>", "\n", t, flags=re.I)
        t = re.sub(r"</(p|div|section|article|h1|h2|h3|h4|li|blockquote)>", "\n", t, flags=re.I)
        t = re.sub(r"<[^>]+>", " ", t); t = html_mod.unescape(t)
        t = re.sub(r"(?<!__EMBED__)https?://\S+(?!__EMBED__)", " ", t)
        t = re.sub(r"[ \t]+", " ", t); t = re.sub(r"\n{3,}", "\n\n", t)
        return t.strip()

    @classmethod
    def _process_plain(cls, raw):
        # Convert bare video URLs to embed markers
        VIDEO_URL_PAT = (
            r'https?://(?:www\.)?(?:'
            r'youtube\.com/watch\?[^\s<>"\']{5,}|'
            r'youtu\.be/[\w\-]{5,}[^\s<>"\']*|'
            r'youtube\.com/shorts/[\w\-]{5,}[^\s<>"\']*|'
            r'(?:twitter|x)\.com/\S+/status/\d{5,}[^\s<>"\']*|'
            r'facebook\.com/[^\s<>"\']+/videos/\d{5,}[^\s<>"\']*'
            r')'
        )
        def _url_to_embed(m):
            url = m.group(0).strip()
            info = EmbedHelper.detect(url)
            if info["type"]: return f"\n__EMBED__{info['html']}__EMBED__\n"
            return url
        raw = re.sub(VIDEO_URL_PAT, _url_to_embed, raw, flags=re.I)
        lines = cls._clean_lines(raw)
        lines = cls._strip_seo_lines(lines)
        if not lines: return None
        text_lines = [l for l in lines if not l.strip().startswith("__EMBED__")]
        h1 = cls._guess_title(text_lines if text_lines else lines)
        intro = cls._build_intro(text_lines if text_lines else lines)
        secs = cls._split_body(lines)
        struct = cls._build_structure(secs)
        return h1, intro, struct

    @classmethod
    def _process_html(cls, raw):
        cleaned_html = cls._sanitize_wp_html(raw)
        blocks = cls._parse_html_blocks(cleaned_html)
        para_count  = sum(1 for b in blocks if b["type"] == "p")
        embed_count = sum(1 for b in blocks if b["type"] == "embed")

        if para_count >= 1 or embed_count >= 1:
            h1 = ""; intro = ""; struct = []; current_h2 = None; current_h3 = None

            def ensure_section(title=""):
                nonlocal current_h2
                if current_h2 is None:
                    current_h2 = {"h2": title, "subsections": []}; struct.append(current_h2)
                return current_h2

            def ensure_subsection(title=""):
                nonlocal current_h3
                sec = ensure_section("")
                if current_h3 is None:
                    current_h3 = {"h3": title, "h4": "", "body": ""}; sec["subsections"].append(current_h3)
                return current_h3

            for b in blocks:
                btype = b.get("type"); content = (b.get("content") or "").strip()
                if not content: continue
                if btype == "h1":
                    if not h1: h1 = content; continue
                elif btype == "h2":
                    current_h2 = {"h2": content, "subsections": []}; struct.append(current_h2); current_h3 = None
                elif btype in ("h3","h4"):
                    sec = ensure_section("")
                    current_h3 = {"h3": content, "h4": "", "body": ""}; sec["subsections"].append(current_h3)
                elif btype == "embed":
                    sub = ensure_subsection("")
                    if sub["body"].strip(): sub["body"] += "\n\n"
                    sub["body"] += f"__EMBED__{content}__EMBED__"
                elif btype == "p":
                    plain = (b.get("plain") or "").strip()
                    if not intro and plain: intro = plain; continue
                    sub = ensure_subsection("")
                    if sub["body"].strip(): sub["body"] += "\n\n"
                    sub["body"] += content

            if not h1 and intro: h1 = cls._trim_to_words(intro, max_words=20); intro = ""
            is_flat = (len(struct) <= 1
                       and all(not sec.get("h2") for sec in struct)
                       and all(not sub.get("h3")
                               for sec in struct for sub in sec.get("subsections", [])))
            if is_flat:
                ordered_chunks = []
                h1_skipped = False
                for b in blocks:
                    btype = b.get("type"); content = (b.get("content") or "").strip()
                    if not content: continue
                    if btype == "p" and not h1_skipped: h1_skipped = True; continue
                    if btype == "embed": ordered_chunks.append(f"__EMBED__{content}__EMBED__")
                    elif btype == "p":  ordered_chunks.append(content)
                if not intro and ordered_chunks:
                    for i, chunk in enumerate(ordered_chunks):
                        if not chunk.startswith("__EMBED__"):
                            plain_text = re.sub(r'<[^>]+>',' ',chunk)
                            plain_text = re.sub(r'\s+',' ',plain_text).strip()
                            intro = cls._trim_to_words(plain_text, max_words=80); break
                if ordered_chunks:
                    PARAS_PER_SECTION = 3
                    new_struct = []
                    def _make_section(chunks_list):
                        h2_text = ""
                        for c in chunks_list:
                            if not c.startswith("__EMBED__"):
                                plain = re.sub(r'<[^>]+>',' ',c)
                                plain = re.sub(r'\s+',' ',plain).strip()
                                sent_m = re.match(r'^(.{15,70}?[.!?"])\s', plain)
                                h2_text = (sent_m.group(1).rstrip('.,;:') if sent_m
                                           else ' '.join(plain.split()[:8])); break
                        return {"h2":h2_text,"subsections":[{"h3":"","h4":"","body":"\n\n".join(chunks_list)}]}
                    current_section = []; para_count_in_section = 0
                    for chunk in ordered_chunks:
                        current_section.append(chunk)
                        if not chunk.startswith("__EMBED__"): para_count_in_section += 1
                        if para_count_in_section >= PARAS_PER_SECTION and not chunk.startswith("__EMBED__"):
                            new_struct.append(_make_section(current_section))
                            current_section = []; para_count_in_section = 0
                    if current_section: new_struct.append(_make_section(current_section))
                    if new_struct: struct = new_struct
            return h1, intro, struct

        # Fallback: plain text path
        plain = cls._html_to_plain(cleaned_html)
        lines = cls._clean_lines(plain); lines = cls._strip_seo_lines(lines)
        if not lines: return None
        text_lines = [l for l in lines if not l.strip().startswith("__EMBED__")]
        h1 = cls._guess_title(text_lines if text_lines else lines)
        intro = cls._build_intro(text_lines if text_lines else lines)
        secs = cls._split_body(lines); struct = cls._build_structure(secs)
        return h1, intro, struct

    @classmethod
    def _build_wp_html(cls, h1, intro, struct):
        if not h1 and not intro and not struct: return ""
        esc = lambda v: html.escape(str(v), quote=True)
        parts = []
        H1_S   = 'font-family:Arial,sans-serif;font-size:clamp(28px,5vw,42px);font-weight:800;color:#111111;margin:0 0 20px 0;line-height:1.2;text-align:center;'
        INTRO_S= 'font-size:clamp(16px,3.5vw,20px);line-height:1.8;color:#444444;margin:0 0 24px 0;font-style:italic;text-align:center;'
        H2_S   = 'font-family:Arial,sans-serif;font-size:clamp(20px,4vw,30px);font-weight:800;color:#111111;margin:36px 0 14px 0;line-height:1.25;border-left:4px solid #2563eb;padding-left:12px;'
        H3_S   = 'font-family:Arial,sans-serif;font-size:clamp(17px,3.2vw,24px);font-weight:700;color:#222222;margin:24px 0 10px 0;line-height:1.3;'
        P_S    = 'font-size:clamp(15px,3vw,19px);line-height:1.85;color:#333333;margin:0 0 20px 0;'
        WRAP   = 'max-width:800px;margin:0 auto;padding:0 16px;font-family:Georgia,"Times New Roman",serif;color:#222222;font-size:18px;line-height:1.8;'
        embed_count = 0; in_wrap = False

        def open_w():
            nonlocal in_wrap
            if not in_wrap: parts.append(f'<div style="{WRAP}">'); in_wrap = True
        def close_w():
            nonlocal in_wrap
            if in_wrap: parts.append('</div>'); in_wrap = False

        def wp_embed_block(url, provider, media_type):
            nonlocal embed_count; embed_count += 1
            safe_json = html.escape(url, quote=True); safe_html = html.escape(url)
            fig_s  = 'text-align:center !important;margin:28px auto !important;display:table !important;max-width:560px;width:100%;'
            wrap_s = 'text-align:center !important;margin:0 auto !important;max-width:560px;width:100%;'
            return (f'\n<!-- wp:embed {{"url":"{safe_json}","type":"{media_type}","providerNameSlug":"{provider}","responsive":true,"className":"aligncenter"}} -->\n'
                    f'<figure class="wp-block-embed is-type-{media_type} is-provider-{provider} wp-block-embed-{provider} aligncenter" style="{fig_s}"><div class="wp-block-embed__wrapper" style="{wrap_s}">{safe_html}</div></figure>\n'
                    f'<!-- /wp:embed -->\n')

        media_map = {"twitter":("twitter","rich"),"youtube":("youtube","video"),"facebook":("facebook","video")}

        def process_embed(embed_raw):
            info = EmbedHelper.detect(embed_raw)
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
                return f"\n<p style=\"{P_S};text-align:center;\"><a href=\"{html.escape(embed_raw)}\">{html.escape(embed_raw)}</a></p>\n"
            return ""

        open_w()
        if h1:    parts.append(f'<h1 style="{H1_S}">{esc(h1)}</h1>')
        if intro: parts.append(f'<p style="{INTRO_S}">{esc(intro)}</p>')

        for sec in struct:
            if sec.get("h2"): open_w(); parts.append(f'<h2 style="{H2_S}">{esc(sec["h2"])}</h2>')
            for sub in sec.get("subsections",[]):
                if sub.get("h3"): open_w(); parts.append(f'<h3 style="{H3_S}">{esc(sub["h3"])}</h3>')
                if sub.get("h4"): open_w(); parts.append(f'<h3 style="{H3_S}">{esc(sub["h4"])}</h3>')
                body_text = re.sub(r'__PRESV_EMBED_START__(.*?)__PRESV_EMBED_END__',
                                   lambda m: f"\n\n__EMBED__{m.group(1).strip()}__EMBED__\n\n",
                                   sub.get("body",""), flags=re.S)
                for chunk in [x.strip() for x in body_text.split("\n\n") if x.strip()]:
                    if chunk.startswith("__EMBED__") and chunk.endswith("__EMBED__"):
                        embed_raw = chunk[9:-9].strip()
                        close_w(); parts.append(process_embed(embed_raw))
                    else:
                        open_w()
                        chunk_clean = re.sub(r"\s+"," ",chunk.replace("\n"," ")).strip()
                        chunk_clean = re.sub(r'\bRead\s+More\b','',chunk_clean,flags=re.I).strip()
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
                       f'     • Works in BOTH editors without any plugin required\n'
                       f'-->')
        result = rewrite_twitter_embed_urls(result)
        return result

    @classmethod
    def _render_output_data(cls, h1, intro, struct):
        """Return list of {tag, text, url} dicts — mirrors _render_output tk.Text inserts."""
        items = []
        def ins(text, tag, url=None):
            items.append({"tag": tag, "text": text, "url": url})
        if h1:    ins("H1  ", "h1_label"); ins(h1 + "\n\n", "h1")
        if intro: ins(intro + "\n\n", "intro")
        for sec in struct:
            if sec.get("h2"): ins("H2  ","h2_label"); ins(sec["h2"]+"\n\n","h2")
            for sub in sec.get("subsections",[]):
                if sub.get("h3"): ins("H3  ","h3_label"); ins(sub["h3"]+"\n\n","h3")
                if sub.get("h4"): ins("H4  ","h3_label"); ins(sub["h4"]+"\n\n","h3")
                if sub.get("body"):
                    body = sub["body"]
                    body = re.sub(r'__PRESV_EMBED_START__(.*?)__PRESV_EMBED_END__',
                                  lambda m: f"__EMBED__{m.group(1).strip()}__EMBED__", body, flags=re.S)
                    chunks = re.split(r'(__EMBED__.*?__EMBED__)', body, flags=re.S)
                    for chunk in chunks:
                        if chunk.startswith("__EMBED__") and chunk.endswith("__EMBED__"):
                            embed_raw = chunk[9:-9].strip()
                            info = EmbedHelper.detect(embed_raw)
                            embed_type = info.get("type") or "generic"
                            icon  = info.get("icon","▶")
                            label = info.get("label","Embedded Media")
                            src   = info.get("src","")
                            tag_map = {"youtube":"embed_yt","twitter":"embed_tw",
                                       "facebook":"embed_fb","generic":"embed_gen"}
                            embed_tag = tag_map.get(embed_type,"embed_gen")
                            ins(f"{icon}  {label}\n", embed_tag)
                            if src: ins(f"    ↳ {src[:80]}\n\n", "embed_url", src)
                            else:   ins("\n","body")
                        elif chunk.strip():
                            ins(chunk.strip()+"\n\n","body")
        return items

    @classmethod
    def process(cls, raw_input: str) -> dict:
        """Main entry point — mirrors process_article() in desktop."""
        looks_html = cls._looks_html(raw_input)
        if looks_html:
            result = cls._process_html(raw_input)
        else:
            result = cls._process_plain(raw_input)

        if result is None:
            return {"ok": False, "error": "No valid content found"}

        h1, intro, struct = result

        h1 = re.sub(r'__PRESV_EMBED_START__(.*?)__PRESV_EMBED_END__',' ',str(h1 or ''),flags=re.S).strip()
        intro = re.sub(r'__PRESV_EMBED_START__(.*?)__PRESV_EMBED_END__',' ',str(intro or ''),flags=re.S).strip()

        fk           = cls._make_keyphrase(h1)
        slug         = cls._make_slug(h1)
        src          = re.sub(r"\s+"," ", intro or h1).strip()
        short_summary= cls._trim_words(src, 200, chars=True)
        short_caption= cls._build_short_caption(h1, intro, struct)
        seo_titles   = cls._seo_title_options(h1)
        meta_options = cls._meta_options(intro, h1)
        seo_title    = seo_titles[0]   if seo_titles   else h1
        meta         = meta_options[0] if meta_options  else cls._trim_words(intro or h1, 160, chars=True)

        full_text = h1 + " " + intro
        for sec in struct:
            full_text += " " + sec.get("h2","")
            for sub in sec.get("subsections",[]):
                full_text += " " + sub.get("h3","") + " " + sub.get("body","")
        try: hashtags = cls._generate_hashtags(full_text, h1)
        except: hashtags = []

        wp_html      = cls._build_wp_html(h1, intro, struct)
        output_items = cls._render_output_data(h1, intro, struct)
        language     = cls._detect_language(raw_input)

        return {
            "ok": True,
            "h1": h1, "intro": intro, "slug": slug,
            "focus_keyphrase": fk,
            "seo_title": seo_title,
            "seo_title_options": seo_titles,
            "meta_description": meta,
            "meta_options": meta_options,
            "short_caption": short_caption,
            "short_summary": short_summary,
            "hashtags": " ".join(hashtags),
            "hashtags_list": hashtags,
            "wp_html": wp_html,
            "output_items": output_items,
            "language": language,
            "struct": struct,
        }

# ══════════════════════════════════════════════════════════════
#  IMAGE SEO (clean field — exact copy from desktop)
# ══════════════════════════════════════════════════════════════
def _clean_field(text: str, max_words: int = 20, mode: str = "generic") -> str:
    text = str(text or "").strip(); text = html_mod.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    JUNK = [r"\bfeatured image\b",r"\bimage seo\b",r"\bseo\b",r"\bkeyword[s]?\b",
            r"\boptimiz\w*\b",r"\branking\b",r"\bmetadata\b",r"\balt tag\b",r"\balt text\b",
            r"\bvisibility\b",r"\bdiscoverability\b",r"\bengagement\b",r"\btraffic\b",
            r"\bcontent marketing\b",r"\bblog post\b",r"\bnews article\b",
            r"\bthis image\b",r"\bthe image\b",r"\ba photo of\b",r"\ban image of\b",
            r"\bpicture of\b",r"\bshowcas\w*\b",r"\bhighlights?\b",
            r"\bIMG_?\d+\b",r"\bDSC_?\d+\b",r"\b\w+\.(jpg|jpeg|png|webp)\b"]
    for pat in JUNK: text = re.sub(pat, "", text, flags=re.I)
    text = re.sub(r"\s*,\s*,",",",text); text = re.sub(r"^\s*[,;:\-–—]\s*","",text)
    text = re.sub(r"\s*[,;:\-–—]\s*$","",text); text = re.sub(r"\s+"," ",text).strip()
    if mode == "title":
        text = re.sub(r"[.!?]+$","",text).strip()
        SMALL = {"a","an","the","and","or","but","in","on","at","to","for","of","with","by"}
        words = text.split()
        text = " ".join(w.capitalize() if (i==0 or w.lower() not in SMALL) else w.lower()
                        for i,w in enumerate(words))
    elif mode == "caption":
        sentences = re.split(r'(?<=[.!?])\s+', text)
        text = sentences[0].strip() if sentences else text
        text = text.strip(" -,:;")
        if text and not re.search(r"[.!?]$", text): text += "."
    elif mode == "alt":
        text = re.sub(r"[.!?]+$","",text).strip()
        if text and text[0].isupper() and not re.match(r"^[A-Z]{2,}",text):
            text = text[0].lower() + text[1:]
    words = text.split()
    if len(words) > max_words:
        text = " ".join(words[:max_words]).rstrip(" ,;:-")
        if mode == "caption" and not re.search(r"[.!?]$",text): text += "."
    return re.sub(r"\s+"," ",text).strip()

def _sanitize(text, max_len=None, mode="generic"):
    result = _clean_field(text, max_words=30, mode=mode)
    if max_len and len(result) > max_len:
        result = result[:max_len].rsplit(" ",1)[0].rstrip(" ,;:.-")
        if mode == "caption" and not re.search(r"[.!?]$",result): result += "."
    return result

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

# ══════════════════════════════════════════════════════════════
#  FLASK ROUTES
# ══════════════════════════════════════════════════════════════
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/verify-key", methods=["POST"])
def api_verify_key():
    data = request.get_json(force=True) or {}
    key = (data.get("api_key") or "").strip()
    if not key: return jsonify({"ok":False,"error":"API key is empty"}), 400
    try:
        verify_key(key); session["api_key"] = key
        return jsonify({"ok":True,"message":"✓ Key is valid"})
    except Exception as e:
        return jsonify({"ok":False,"error":str(e)}), 400

@app.route("/api/set-key", methods=["POST"])
def api_set_key():
    data = request.get_json(force=True) or {}
    key = (data.get("api_key") or "").strip()
    session["api_key"] = key
    return jsonify({"ok":True})

@app.route("/api/fetch-url", methods=["POST"])
def api_fetch_url():
    data = request.get_json(force=True) or {}
    url = (data.get("url") or "").strip()
    if not url: return jsonify({"ok":False,"error":"No URL provided"}), 400
    if not url.startswith("http"): url = "https://" + url
    url = re.sub(r"[?&](utm_\w+|fbclid|aem_\w*|ref|source|medium|campaign)=[^&]*","",url).rstrip("?&")
    STRATEGIES = [
        {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36","Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8","Accept-Language":"en-US,en;q=0.9","Accept-Encoding":"gzip, deflate, br","Cache-Control":"no-cache"},
        {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0","Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8","Accept-Language":"en-US,en;q=0.5"},
        {"User-Agent":"Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)","Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
    ]
    html_content = None; last_err = None
    for hdrs in STRATEGIES:
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw_bytes = resp.read(); ct = resp.headers.get("Content-Type","")
                charset = _smart_charset(raw_bytes, ct); html_content = _smart_decode(raw_bytes, charset)
            body_lower = html_content.lower()
            blocked = any(kw in body_lower for kw in ["access denied","403 forbidden","blocked","captcha","cloudflare","enable javascript"])
            if blocked and len(html_content) < 8000: html_content = None; time.sleep(0.4); continue
            break
        except Exception as e: last_err = e; time.sleep(0.3)
    if not html_content:
        return jsonify({"ok":False,"error":str(last_err) or "All fetch strategies failed — paste article manually"}), 400
    lang = SEOProcessor._detect_language(html_content)
    return jsonify({"ok":True,"html":html_content,"language":lang,"url":url})

@app.route("/api/process-article", methods=["POST"])
def api_process_article():
    data = request.get_json(force=True) or {}
    raw = (data.get("text") or "").strip()
    if not raw: return jsonify({"ok":False,"error":"No article text provided"}), 400
    try:
        result = SEOProcessor.process(raw)
        return jsonify(result)
    except Exception as e:
        return jsonify({"ok":False,"error":str(e)}), 500

@app.route("/api/ai-seo-fields", methods=["POST"])
def api_ai_seo_fields():
    data = request.get_json(force=True) or {}
    api_key = (data.get("api_key") or session.get("api_key") or "").strip()
    article_text = (data.get("text") or "").strip()
    language = (data.get("language") or "English").strip()
    if not api_key: return jsonify({"ok":False,"error":"No API key. Open ⚙ API Settings and save your key."}), 400
    if not article_text: return jsonify({"ok":False,"error":"No article text provided"}), 400

    article = re.sub(r"\s+"," ",article_text).strip()[:900]
    tone = random.choice(["direct","search-friendly","newsy"])
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

Rules: concise, catchy, Yoast-friendly, no markdown, no explanation, tone: {tone}

ARTICLE:
{article}"""

    raw_model_plan = [
        (FAST_SEO_FIELDS_MODEL, 0.20, FAST_AI_TIMEOUT, FAST_SEO_FIELD_MAX_TOKENS),
        (SEO_MODEL, 0.18, 28, 280),
    ]
    seen_models = set(); data_out = None; last_err = None
    for model, temp, to_sec, max_tok in raw_model_plan:
        model = (model or "").strip()
        if not model or model in seen_models: continue
        seen_models.add(model)
        try:
            resp = chat_completion(api_key, model,
                messages=[{"role":"user","content":prompt}],
                temperature=temp, response_format={"type":"json_object"},
                timeout=to_sec, max_tokens=max_tok)
            data_out = parse_json(extract_content(resp))
            if isinstance(data_out,dict) and any(data_out.get(k) for k in ("focus_keyphrase","seo_title_1","meta_description_1")):
                break
        except Exception as e: last_err=e; data_out=None

    if not isinstance(data_out, dict):
        return jsonify({"ok":False,"error":str(last_err) if last_err else "AI SEO fields failed"}), 500

    def cap_title(t):
        t = str(t or "").strip()
        if len(t) > 60: t = (t[:60].rsplit(" ",1)[0] if " " in t[:60] else t[:60]).rstrip(" :-,")
        return t
    def cap_meta(m):
        m = str(m or "").strip()
        return m[:160].rsplit(" ",1)[0] if len(m)>160 else m

    fk     = str(data_out.get("focus_keyphrase","")).strip()
    title1 = cap_title(data_out.get("seo_title_1",""))
    title2 = cap_title(data_out.get("seo_title_2",""))
    title3 = cap_title(data_out.get("seo_title_3",""))
    meta1  = cap_meta(data_out.get("meta_description_1",""))
    meta2  = cap_meta(data_out.get("meta_description_2",""))
    meta3  = cap_meta(data_out.get("meta_description_3",""))

    return jsonify({"ok":True,
        "focus_keyphrase":fk,
        "seo_titles":[title1,title2,title3],
        "meta_descriptions":[meta1,meta2,meta3]})

@app.route("/api/image-seo", methods=["POST"])
def api_image_seo():
    api_key = (request.form.get("api_key") or session.get("api_key") or "").strip()
    scene_notes = (request.form.get("scene_notes") or "").strip()
    if not api_key: return jsonify({"ok":False,"error":"No API key. Open ⚙ API Settings."}), 400
    if "image" not in request.files: return jsonify({"ok":False,"error":"No image uploaded"}), 400

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
                if len(alt_text)<10 or len(img_title)<5 or len(caption)<15:
                    alt_text, img_title, caption = _fallback_image_seo(scene_notes, filename)
                return jsonify({"ok":True,
                    "alt_text":  _sanitize(alt_text,  90, "alt"),
                    "img_title": _sanitize(img_title, 90, "title"),
                    "caption":   _sanitize(caption,  180, "caption"),
                    "model": model.split("/")[-1]})
            except Exception as e: last_err = e
        raise RuntimeError(str(last_err) if last_err else "All models failed")
    except Exception as e:
        return jsonify({"ok":False,"error":str(e)}), 500

@app.route("/api/export-image", methods=["POST"])
def api_export_image():
    if "image" not in request.files: return jsonify({"ok":False,"error":"No image"}), 400
    try:
        file = request.files["image"]
        img = Image.open(file.stream).convert("RGB"); w, h = img.size
        if w < 1400:
            s = max(1.2, 1400/max(w,1)); img = img.resize((int(w*s),int(h*s)),Image.LANCZOS)
        img = ImageEnhance.Sharpness(img).enhance(1.35)
        img = ImageEnhance.Contrast(img).enhance(1.03)
        best_bytes = best_q = None
        for q in range(95, 14, -5):
            buf = io.BytesIO(); img.save(buf,"JPEG",quality=q,optimize=True)
            if len(buf.getvalue())/1024 <= 100: best_bytes=buf.getvalue(); best_q=q; break
        if best_bytes is None:
            tmp = img.copy(); q = 85
            while True:
                buf = io.BytesIO(); tmp.save(buf,"JPEG",quality=q,optimize=True)
                if len(buf.getvalue())/1024 <= 100 or min(tmp.size) < 200:
                    best_bytes=buf.getvalue(); best_q=q; break
                ew,eh=tmp.size; tmp=tmp.resize((int(ew*.92),int(eh*.92)),Image.LANCZOS)
        from flask import Response
        size_kb = len(best_bytes)/1024
        resp = Response(best_bytes, mimetype="image/jpeg")
        resp.headers["Content-Disposition"] = 'attachment; filename="optimized.jpg"'
        resp.headers["X-Image-Quality"] = str(best_q)
        resp.headers["X-Image-Size-KB"] = f"{size_kb:.1f}"
        return resp
    except Exception as e:
        return jsonify({"ok":False,"error":str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG","0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
