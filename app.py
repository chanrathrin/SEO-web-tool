import os
import io
import re
import json
import time
import base64
from collections import defaultdict

import requests
from flask import Flask, render_template, request, jsonify
from PIL import Image

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY", "").strip()
TOGETHER_BASE_URL = "https://api.together.xyz/v1"
VISION_MODEL = "moonshotai/Kimi-K2.5"
VISION_FALLBACK_MODEL = "Qwen/Qwen3-VL-8B-Instruct"

RATE_BUCKET = defaultdict(list)


def get_client_ip():
    forwarded = request.headers.get("X-Forwarded-For", "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def rate_limit_ok(ip: str, per_minute: int = 25) -> bool:
    now = time.time()
    RATE_BUCKET[ip] = [t for t in RATE_BUCKET[ip] if now - t < 60]
    if len(RATE_BUCKET[ip]) >= per_minute:
        return False
    RATE_BUCKET[ip].append(now)
    return True


def together_headers(api_key: str):
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def get_effective_api_key(user_key: str = "") -> str:
    user_key = (user_key or "").strip()
    if user_key:
        return user_key
    return TOGETHER_API_KEY


def extract_content(resp_json):
    choices = resp_json.get("choices") or []
    if not choices:
        return ""
    msg = choices[0].get("message") or {}
    content = msg.get("content", "")
    if isinstance(content, list):
        out = []
        for item in content:
            if isinstance(item, dict):
                txt = item.get("text") or item.get("content") or ""
                if txt:
                    out.append(str(txt))
            elif item:
                out.append(str(item))
        return "\n".join(out).strip()
    return str(content or "").strip()


def parse_json_str(raw: str) -> dict:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("Empty model response")

    candidates = [raw]
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    if cleaned != raw:
        candidates.append(cleaned)

    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        candidates.append(match.group(0).strip())

    last_err = None
    for candidate in candidates:
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except Exception as e:
            last_err = e

    raise ValueError(f"Could not parse JSON from model response: {raw[:220]}") from last_err


def clean_inline_text(text: str, max_len: int = 180) -> str:
    text = str(text or "").strip()
    text = re.sub(r"\s+", " ", text)
    text = text.replace("featured image", "").replace("Featured image", "")
    text = text.replace("featured Image", "").replace("Featured Image", "")
    return text[:max_len].strip(" ,.-:;")


def trim_words(text: str, limit: int, chars: bool = False) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not text:
        return ""
    if chars:
        if len(text) <= limit:
            return text
        cut = text[:limit].rstrip()
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]
        return cut.rstrip(" ,.-:;")
    words = text.split()
    return " ".join(words[:limit]).strip()


def normalize_heading(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip(" .,:;-")


def html_to_plain(raw_html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", raw_html, flags=re.I)
    text = re.sub(r"</(p|div|section|article|h1|h2|h3|h4|h5|li|blockquote)>", "\n", text, flags=re.I)
    text = re.sub(r"<iframe\\b[^>]*src=[\"']([^\"']+)[\"'][^>]*>\\s*</iframe>", r"\n\1\n", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"&#39;", "'", text)
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_lines(text: str):
    text = re.sub(r"\u00a0", " ", str(text or "").replace("\r\n", "\n"))
    text = re.sub(r"[ \t]+", " ", text)
    raw = [line.strip() for line in text.split("\n")]

    out = []
    last_blank = True
    for line in raw:
        if not line:
            if not last_blank:
                out.append("")
            last_blank = True
        else:
            out.append(line)
            last_blank = False

    while out and out[-1] == "":
        out.pop()
    return out


def strip_seo_lines(lines):
    prefixes = (
        "Focus Keyphrase:",
        "SEO Title:",
        "Meta Description:",
        "Slug (URL):",
        "Slug:",
        "Short Summary:",
    )
    out = []
    for line in lines:
        s = line.strip()
        if any(s.startswith(prefix) for prefix in prefixes):
            continue
        if re.match(r"^https?://[^\\s]+$", s):
            continue
        if out and s and out[-1].strip() == s:
            continue
        out.append(line)
    while out and out[-1] == "":
        out.pop()
    return out


def guess_title(lines):
    if not lines:
        return "Untitled Article"
    return trim_words(lines[0], 18)


def build_intro(lines):
    content = [x for x in lines[1:] if x.strip()]
    if not content:
        return ""
    parts = []
    for line in content:
        parts.append(line)
        joined = " ".join(parts)
        if len(joined) >= 220 or line.endswith((".", "!", "?")):
            break
    return trim_words(" ".join(parts).strip(), 85)


def split_body(lines):
    paragraphs = []
    current = []

    for line in lines[1:]:
        if not line.strip():
            if current:
                paragraphs.append(" ".join(current).strip())
                current = []
        else:
            current.append(line.strip())

    if current:
        paragraphs.append(" ".join(current).strip())

    blocks = [p for p in paragraphs if p] or [x for x in lines[1:] if x.strip()]
    if not blocks:
        return []

    if len(blocks) <= 3:
        return blocks[:3]

    base = len(blocks) // 3
    extra = len(blocks) % 3
    result = []
    idx = 0
    for i in range(3):
        take = base + (1 if i < extra else 0)
        chunk = "\n\n".join(blocks[idx:idx + take]).strip()
        if chunk:
            result.append(chunk)
        idx += take
    return result[:3]


def choose_heading(text, seen):
    text = str(text or "").replace("\n", " ")
    sentences = re.split(r"(?<=[.!?])\s+", text)
    ranked = []

    for s in sentences:
        s = re.sub(r"[_-]+", " ", s).strip(" \"'.,:;!?-")
        s = re.sub(r"^[^A-Za-z0-9]+", "", s)
        words = s.split()
        if len(words) < 4:
            continue
        score = 4 if 5 <= len(words) <= 10 else (2 if len(words) <= 13 else 0)
        ranked.append((score, s))

    ranked.sort(key=lambda x: -x[0])

    for _, candidate in ranked:
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        return trim_words(candidate, 15)

    return ""


def build_structure(sections):
    structure = []
    seen = set()

    for idx, section in enumerate(sections[:3], start=1):
        parts = [p.strip() for p in section.split("\n\n") if p.strip()]
        if not parts:
            continue

        h2 = ""
        for source in parts[:2] + [section]:
            h2 = choose_heading(source, seen)
            if h2:
                break

        if not h2:
            words = re.sub(r"[_-]+", " ", parts[0]).split()
            h2 = " ".join(words[:8]).strip() or f"Section {idx}"

        structure.append({
            "h2": normalize_heading(h2),
            "subsections": [
                {
                    "h3": "",
                    "h4": "",
                    "body": "\n\n".join(parts).strip()
                }
            ]
        })

    return structure[:3]


def make_slug(title: str) -> str:
    slug = re.sub(r"[^a-z0-9\s-]", "", str(title or "").lower())
    slug = re.sub(r"\s+", "-", slug).strip("-")
    return re.sub(r"-{2,}", "-", slug)


def make_keyphrase(title: str) -> str:
    return " ".join(re.sub(r"[^\w\s-]", "", str(title or "")).split()[:10]).strip()


def seo_title_options(title: str):
    base = re.sub(r"\s+", " ", str(title or "")).strip()
    if not base:
        return []
    opts = [
        trim_words(base, 70, chars=True),
        trim_words(f"{base} | Full Report", 70, chars=True),
        trim_words(f"{base} | Key Updates", 70, chars=True),
    ]
    out = []
    seen = set()
    for item in opts:
        low = item.lower()
        if item and low not in seen:
            seen.add(low)
            out.append(item)
    return out[:4]


def meta_options(intro: str, title: str):
    src = re.sub(r"\s+", " ", intro or title).strip()
    if not src:
        return []
    opts = [
        trim_words(src, 160, chars=True),
        trim_words(f"{title} — {src}", 160, chars=True),
    ]
    out = []
    seen = set()
    for item in opts:
        low = item.lower()
        if item and low not in seen:
            seen.add(low)
            out.append(item)
    return out[:3]


def build_short_caption(h1, intro, structure):
    title = normalize_heading(h1)
    snippet = trim_words(intro, 34)
    if title and snippet:
        cap = f"{title}. {snippet}"
    elif title:
        cap = title
    else:
        cap = snippet

    if len(cap) < 120 and structure:
        h2 = normalize_heading(structure[0].get("h2", ""))
        if h2 and h2.lower() not in cap.lower():
            cap = f"{cap} — {h2}"

    cap = cap.strip(" .,:;-")
    if cap and not cap.endswith((".", "!", "?")):
        cap += "."
    return trim_words(cap, 160, chars=True)


def generate_hashtags(full_text: str, h1: str):
    stop = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with",
        "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do",
        "does", "did", "will", "would", "could", "should", "may", "might", "shall", "can",
        "need", "that", "this", "these", "those", "it", "its", "by", "from", "as", "into",
        "through", "during", "before", "after", "above", "below", "up", "down", "out",
        "off", "over", "under", "again", "further", "then", "once", "here", "there", "when",
        "where", "why", "how", "all", "each", "every", "both", "few", "more", "most",
        "other", "some", "such", "no", "not", "only", "same", "so", "than", "too", "very",
        "just", "about", "also", "which", "who", "whom", "what", "he", "she", "they",
        "we", "you", "i", "my", "your", "his", "her", "our", "their", "new", "one", "two",
        "three", "get", "got", "use", "used", "make", "made", "take", "taken", "give",
        "given", "said", "say", "look", "see"
    }

    clean = re.sub(r"<[^>]+>", " ", full_text)
    clean = re.sub(r"[^\w\s'-]", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip().lower()

    words = clean.split()
    total = max(len(words), 1)

    word_scores = {}
    for idx, word in enumerate(words):
        w = re.sub(r"[^a-z0-9']", "", word)
        if len(w) < 4 or w in stop:
            continue
        pos_weight = 1.5 if idx / total < 0.20 else 1.0
        word_scores[w] = word_scores.get(w, 0) + pos_weight

    bigram_scores = {}
    for i in range(len(words) - 1):
        w1 = re.sub(r"[^a-z0-9']", "", words[i])
        w2 = re.sub(r"[^a-z0-9']", "", words[i + 1])
        if len(w1) >= 3 and len(w2) >= 3 and w1 not in stop and w2 not in stop:
            bg = f"{w1} {w2}"
            bigram_scores[bg] = bigram_scores.get(bg, 0) + 1

    h1_words = set(re.sub(r"[^a-z0-9\s]", "", h1.lower()).split())
    for w in list(word_scores.keys()):
        if w in h1_words:
            word_scores[w] *= 2.0

    candidates = []
    for bg, score in bigram_scores.items():
        if score >= 2:
            tag = "#" + "".join(part.capitalize() for part in bg.split())
            candidates.append((score * 1.8, tag, bg))

    for w, score in sorted(word_scores.items(), key=lambda x: -x[1]):
        tag = "#" + w.capitalize()
        already = any(w in bg for _, _, bg in candidates)
        if not already:
            candidates.append((score, tag, w))

    candidates.sort(key=lambda x: -x[0])

    result = []
    seen = set()
    for _, tag, _ in candidates:
        low = tag.lower()
        if low not in seen:
            seen.add(low)
            result.append(tag)
        if len(result) == 8:
            break

    if len(result) < 6:
        for w in sorted(h1_words - stop, key=lambda x: -len(x)):
            if len(w) >= 4:
                tag = "#" + w.capitalize()
                if tag.lower() not in seen:
                    seen.add(tag.lower())
                    result.append(tag)
            if len(result) == 6:
                break

    return result[:8]


def build_wp_html(h1, intro, structure):
    if not h1 and not intro and not structure:
        return ""

    def esc(v):
        v = str(v or "")
        return (
            v.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;")
        )

    parts = []

    if h1:
        parts.append(f"<h1>{esc(h1)}</h1>")

    if intro:
        parts.append(f"<p><em>{esc(intro)}</em></p>")

    for sec in structure:
        h2 = sec.get("h2", "").strip()
        if h2:
            parts.append(f"<h2>{esc(h2)}</h2>")

        for sub in sec.get("subsections", []):
            h3 = sub.get("h3", "").strip()
            h4 = sub.get("h4", "").strip()
            body = sub.get("body", "").strip()

            if h3:
                parts.append(f"<h3>{esc(h3)}</h3>")
            if h4:
                parts.append(f"<h4>{esc(h4)}</h4>")

            if body:
                paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
                for p in paragraphs:
                    parts.append(f"<p>{esc(p)}</p>")

    return "\n".join(parts).strip()


def process_seo_text(raw_text: str):
    if "<" in raw_text and ">" in raw_text:
        plain = html_to_plain(raw_text)
        lines = clean_lines(plain)
    else:
        lines = clean_lines(raw_text)

    lines = strip_seo_lines(lines)
    if not lines:
        raise ValueError("No valid content found")

    h1 = guess_title(lines)
    intro = build_intro(lines)
    sections = split_body(lines)
    structure = build_structure(sections)

    focus_keyphrase = make_keyphrase(h1)
    slug = make_slug(h1)
    short_summary = trim_words(re.sub(r"\s+", " ", intro or h1).strip(), 200, chars=True)
    short_caption = build_short_caption(h1, intro, structure)

    title_opts = seo_title_options(h1)
    meta_opts = meta_options(intro, h1)
    seo_title = title_opts[0] if title_opts else h1
    meta_description = meta_opts[0] if meta_opts else trim_words(intro or h1, 160, chars=True)

    full_text = h1 + " " + intro
    for sec in structure:
        full_text += " " + sec.get("h2", "")
        for sub in sec.get("subsections", []):
            full_text += " " + sub.get("h3", "") + " " + sub.get("body", "")

    hashtags = generate_hashtags(full_text, h1)
    html_output = build_wp_html(h1, intro, structure)

    return {
        "h1": h1,
        "intro": intro,
        "body_sections": structure,
        "focus_keyphrase": focus_keyphrase,
        "seo_title": seo_title,
        "seo_title_options": title_opts,
        "meta_description": meta_description,
        "meta_options": meta_opts,
        "slug": slug,
        "short_summary": short_summary,
        "short_caption": short_caption,
        "hashtags": hashtags,
        "hashtags_str": " ".join(hashtags),
        "html_output": html_output,
    }


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/ping-key", methods=["POST"])
def api_ping_key():
    payload = request.get_json(silent=True) or {}
    api_key = get_effective_api_key(payload.get("api_key", ""))

    if not api_key:
        return jsonify({"ok": False, "error": "No API key provided"}), 400

    try:
        r = requests.get(
            f"{TOGETHER_BASE_URL}/models",
            headers=together_headers(api_key),
            timeout=25,
        )

        if r.status_code >= 400:
            try:
                d = r.json()
                msg = d.get("error", {}).get("message") or d.get("message") or r.text
            except Exception:
                msg = r.text
            return jsonify({"ok": False, "error": msg}), 400

        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/seo-format", methods=["POST"])
def api_seo_format():
    ip = get_client_ip()
    if not rate_limit_ok(ip, 30):
        return jsonify({"error": "Too many requests. Please wait a minute."}), 429

    payload = request.get_json(silent=True) or {}
    raw = (payload.get("text") or "").strip()

    if not raw:
        return jsonify({"error": "No article text provided."}), 400

    try:
        result = process_seo_text(raw)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/image-seo", methods=["POST"])
def api_image_seo():
    ip = get_client_ip()
    if not rate_limit_ok(ip, 20):
        return jsonify({"error": "Too many requests. Please wait a minute."}), 429

    user_api_key = request.form.get("api_key", "")
    api_key = get_effective_api_key(user_api_key)

    if not api_key:
        return jsonify({"error": "No Together API key configured. Put your API key in website settings."}), 400

    uploaded = request.files.get("image")
    keyword = (request.form.get("keyword") or "").strip()

    if not uploaded:
        return jsonify({"error": "No image uploaded."}), 400

    try:
        img = Image.open(uploaded.stream).convert("RGB")
    except Exception as e:
        return jsonify({"error": f"Invalid image: {e}"}), 400

    max_dim = 1280
    w, h = img.size
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    data_url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("utf-8")

    prompt = (
        "You are an image SEO assistant.\n"
        "Analyze the uploaded image and return ONLY valid JSON with exactly these keys:\n"
        "alt_text, img_title, caption\n\n"
        "Rules:\n"
        "- alt_text: natural, clear, max 65 chars\n"
        "- img_title: short SEO-friendly title, max 80 chars\n"
        "- caption: one natural sentence, max 180 chars\n"
        "- never mention 'featured image'\n"
        "- never output markdown\n"
        "- do not add extra keys\n"
        f"- keyword or scene notes: {keyword or 'image SEO'}"
    )

    errors = []

    for model in [VISION_MODEL, VISION_FALLBACK_MODEL]:
        try:
            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    }
                ],
                "temperature": 0.3,
                "top_p": 0.9,
                "response_format": {"type": "json_object"},
            }

            if "Kimi" in model:
                payload["reasoning"] = {"enabled": False}

            response = requests.post(
                f"{TOGETHER_BASE_URL}/chat/completions",
                headers=together_headers(api_key),
                json=payload,
                timeout=90,
            )
            response.raise_for_status()

            raw = extract_content(response.json())
            data = parse_json_str(raw)

            return jsonify({
                "alt_text": clean_inline_text(data.get("alt_text", ""), 65),
                "img_title": clean_inline_text(data.get("img_title", ""), 80),
                "caption": clean_inline_text(data.get("caption", ""), 180),
                "model": model,
            })

        except Exception as e
            errors.append(str(e))

    return jsonify({"error": " | ".join(errors)[:900] or "Image SEO request failed."}), 502


if __name__ == "__main__":
    app.run(debug=True, port=5000)
