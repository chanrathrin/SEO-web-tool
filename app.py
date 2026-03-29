import os
import io
import re
import json
import html
import base64
import tempfile
import requests
import threading
from flask import Flask, request, jsonify, render_template, send_from_directory

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

TOGETHER_BASE_URL = "https://api.together.xyz/v1"
ARTICLE_MODEL = "Qwen/Qwen3.5-9B"
VISION_MODEL = "meta-llama/Llama-3.2-11B-Vision-Instruct-Turbo"


def together_headers(api_key):
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def verify_together_api_key(api_key, timeout=20):
    response = requests.get(
        f"{TOGETHER_BASE_URL}/models",
        headers=together_headers(api_key),
        timeout=timeout,
    )
    if response.status_code >= 400:
        try:
            data = response.json()
            detail = data.get("error", {}).get("message") or data.get("message") or response.text
        except Exception:
            detail = response.text
        raise RuntimeError(f"HTTP {response.status_code}: {detail}")
    return response.json()


def together_chat_completion(api_key, model, messages, temperature=0.3, timeout=60):
    payload = {"model": model, "messages": messages, "temperature": temperature}
    response = requests.post(
        f"{TOGETHER_BASE_URL}/chat/completions",
        headers=together_headers(api_key),
        json=payload,
        timeout=timeout,
    )
    if response.status_code >= 400:
        try:
            data = response.json()
            detail = data.get("error", {}).get("message") or data.get("message") or response.text
        except Exception:
            detail = response.text
        raise RuntimeError(f"HTTP {response.status_code}: {detail}")
    return response.json()


def extract_message_content(response_json):
    choices = response_json.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content", "")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                txt = item.get("text") or item.get("content") or ""
                if txt:
                    parts.append(str(txt))
            elif item:
                parts.append(str(item))
        return "\n".join(parts).strip()
    return str(content or "").strip()


# ─── Article Processing Logic ───────────────────────────────────────────────

def normalize_space(text):
    return re.sub(r"\s+", " ", text or "").strip()

def normalize_compare_text(text):
    text = (text or "").lower().strip()
    text = re.sub(r"[\"'\u201c\u201d\u2018\u2019`]+", "", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def trim_at_word_boundary(text, limit):
    text = normalize_space(text)
    if len(text) <= limit:
        return text
    cut = text[:limit].rstrip()
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,.-:;")

def clean_lines(text):
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\u00a0", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    raw_lines = [line.strip() for line in text.split("\n")]
    cleaned = []
    last_blank = True
    for line in raw_lines:
        low = line.lower().strip()
        if low in ("paste your article here...", "paste your article here."):
            continue
        if not line:
            if not last_blank:
                cleaned.append("")
            last_blank = True
            continue
        if cleaned and cleaned[-1] and normalize_compare_text(cleaned[-1]) == normalize_compare_text(line):
            continue
        cleaned.append(line)
        last_blank = False
    while cleaned and cleaned[-1] == "":
        cleaned.pop()
    return cleaned

def strip_internal_seo_lines(lines):
    seo_prefixes = ("Focus Keyphrase:","SEO Title:","Meta Description:","Slug (URL):","Slug:","Short Summary:")
    cleaned = []
    for line in lines:
        s = line.strip()
        if any(s.startswith(prefix) for prefix in seo_prefixes):
            continue
        cleaned.append(line)
    while cleaned and cleaned[-1] == "":
        cleaned.pop()
    return cleaned

def guess_title(lines):
    if not lines:
        return "Untitled Article"
    title = normalize_space(lines[0])
    return trim_at_word_boundary(title, 140) or "Untitled Article"

def build_intro(lines):
    content = [line for line in lines[1:] if line.strip()]
    if not content:
        return ""
    intro_parts = []
    for line in content:
        intro_parts.append(line)
        joined = " ".join(intro_parts).strip()
        if len(joined) >= 180 or line.endswith((".", "!", "?")):
            break
    return trim_at_word_boundary(" ".join(intro_parts).strip(), 240)

def remove_heading_from_body(heading, body):
    body = normalize_space(body)
    heading = normalize_space(heading)
    if not heading or not body:
        return body
    body_words = body.split()
    heading_words = heading.split()
    compare_len = min(len(body_words), len(heading_words))
    matched = 0
    for i in range(compare_len):
        if normalize_compare_text(body_words[i]) == normalize_compare_text(heading_words[i]):
            matched += 1
        else:
            break
    if matched >= max(3, len(heading_words) - 1):
        remaining = " ".join(body_words[matched:]).lstrip(" ,.;:-\u2013\u2014)")
        return remaining or body
    return body

def extract_body_paragraphs(lines):
    paragraphs = []
    current = []
    content_lines = lines[1:] if len(lines) > 1 else []
    for line in content_lines:
        if not line.strip():
            if current:
                paragraphs.append(normalize_space(" ".join(current)))
                current = []
        else:
            current.append(line.strip())
    if current:
        paragraphs.append(normalize_space(" ".join(current)))
    if not paragraphs:
        paragraphs = [normalize_space(line) for line in content_lines if line.strip()]
    intro = build_intro(lines)
    filtered = []
    for idx, para in enumerate(paragraphs):
        if not para:
            continue
        if idx == 0 and intro:
            para = remove_heading_from_body(intro, para)
        if para:
            filtered.append(para)
    return filtered

def split_body_into_sections(lines, num_sections=None):
    blocks = extract_body_paragraphs(lines)
    if not blocks:
        return []
    if num_sections is None:
        if len(blocks) >= 6:
            num_sections = 3
        elif len(blocks) >= 3:
            num_sections = 2
        else:
            num_sections = 1
    if len(blocks) <= num_sections:
        return blocks[:num_sections]
    target = min(num_sections, len(blocks))
    base = len(blocks) // target
    extra = len(blocks) % target
    sections = []
    idx = 0
    for i in range(target):
        take = base + (1 if i < extra else 0)
        chunk = blocks[idx:idx + take]
        idx += take
        merged = "\n\n".join(chunk).strip()
        if merged:
            sections.append(merged)
    return sections[:3]

def clean_heading_candidate(text):
    text = re.sub(r"\s+", " ", text or "").strip()
    text = text.strip(' "\'""''.,:;!?-')
    text = re.sub(r"^[^A-Za-z0-9]+", "", text)
    text = re.sub(r"[^A-Za-z0-9]+$", "", text)
    return text

def sentence_candidates_from_text(text):
    sentences = re.split(r'(?<=[.!?])\s+', (text or "").replace("\n", " "))
    out = []
    for s in sentences:
        s = clean_heading_candidate(s)
        if not s:
            continue
        wc = len(s.split())
        if 4 <= wc <= 12:
            out.append(s)
    return out

def phrase_candidates_from_text(text):
    words = [w for w in clean_heading_candidate(text).split() if w]
    candidates = []
    for length in (5, 6, 7, 8):
        if len(words) >= length:
            candidates.append(" ".join(words[:length]))
    return candidates

def choose_heading_from_text(text, seen):
    candidates = sentence_candidates_from_text(text)
    if not candidates:
        candidates = phrase_candidates_from_text(text)
    ranked = []
    for cand in candidates:
        cleaned = clean_heading_candidate(cand)
        if not cleaned:
            continue
        words = cleaned.split()
        if len(words) < 4:
            continue
        if len(words) > 10:
            cleaned = " ".join(words[:10]).strip()
            words = cleaned.split()
        key = cleaned.lower()
        score = 0
        if 6 <= len(words) <= 10:
            score += 5
        elif len(words) == 5:
            score += 4
        elif len(words) == 4:
            score += 3
        if len(cleaned) >= 32:
            score += 2
        if not cleaned.endswith((":", ",", "-")):
            score += 1
        ranked.append((score, cleaned, key))
    ranked.sort(key=lambda x: (-x[0], -len(x[1]), x[1]))
    for _, cand, key in ranked:
        if key in seen:
            continue
        seen.add(key)
        return cand
    return ""

def build_nested_article_structure(sections):
    structure = []
    seen = set()
    for idx, section in enumerate([s.strip() for s in sections if s and s.strip()][:3], start=1):
        h2 = choose_heading_from_text(section, seen)
        if not h2:
            words = clean_heading_candidate(section).split()
            h2 = " ".join(words[:10]).strip() or f"Section {idx}"
        body = remove_heading_from_body(h2, section).strip()
        body = body or normalize_space(section)
        paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [body]
        subsection_body = "\n\n".join(paragraphs)
        structure.append({"h2": h2, "subsections": [{"h3": h2, "body": subsection_body}]})
    return structure[:3]

def make_slug(title):
    slug = re.sub(r"[^a-z0-9\s-]", "", (title or "").lower())
    slug = re.sub(r"\s+", "-", slug).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug[:80] or "news-update"

def make_focus_keyphrase(title):
    cleaned = re.sub(r"[^\w\s-]", "", title or "").strip()
    words = cleaned.split()
    return " ".join(words[:5]).strip() or "news update"

def make_seo_title_options(title):
    base = normalize_space(title)
    if not base:
        return []
    opts = [
        trim_at_word_boundary(base, 60),
        trim_at_word_boundary(base + " | Key Updates", 60),
        trim_at_word_boundary(base + " | Full Report", 60),
    ]
    out, seen = [], set()
    for x in opts:
        key = x.lower()
        if x and key not in seen:
            out.append(x)
            seen.add(key)
    return out[:3]

def make_meta_options(intro, title):
    source = normalize_space(intro if intro else title)
    if not source:
        return []
    opts = [
        trim_at_word_boundary(source, 160),
        trim_at_word_boundary((title or "") + " \u2014 " + source, 160),
    ]
    out, seen = [], set()
    for x in opts:
        key = x.lower()
        if x and key not in seen:
            out.append(x)
            seen.add(key)
    return out[:2]

def make_short_summary(intro, structure):
    source = normalize_space(intro)
    if not source and structure:
        for sec in structure:
            for sub in sec.get("subsections", []):
                body = normalize_space(sub.get("body", ""))
                if body:
                    source = body
                    break
            if source:
                break
    return trim_at_word_boundary(source, 180)

def build_seo_source_text(h1, intro, structure):
    parts = []
    if h1:
        parts.append(f"Title: {h1}")
    if intro:
        parts.append(f"Intro: {intro}")
    for sec in structure:
        if sec.get("h2"):
            parts.append(f"Section: {sec['h2']}")
        for sub in sec.get("subsections", []):
            if sub.get("body"):
                parts.append(sub["body"])
    return "\n".join(parts).strip()

def build_wordpress_html_fragment(h1, intro, structure):
    def esc(value):
        return html.escape(str(value), quote=True)
    parts = []
    if h1:
        parts.append(f"<h1>{esc(h1)}</h1>")
    if intro:
        parts.append(f"<p>{esc(intro)}</p>")
    for sec in structure:
        if sec.get("h2"):
            parts.append(f"<h2>{esc(sec['h2'])}</h2>")
        body = ""
        if sec.get("subsections"):
            body = sec["subsections"][0].get("body", "").strip()
        if body:
            for paragraph in [p.strip() for p in body.split("\n\n") if p.strip()]:
                parts.append(f"<p>{esc(paragraph)}</p>")
    return "\n".join(parts).strip()

def clean_imported_article_text(text):
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    bad_exact_patterns = [
        r"^\s*advertisement\s*$", r"^\s*sponsored\s*$", r"^\s*promoted\s*$",
        r"^\s*related articles?\s*$", r"^\s*read more\s*$", r"^\s*newsletter\s*$",
        r"^\s*sign up\s*$", r"^\s*adkeeper\s*$", r"^\s*partner content\s*$",
        r"^\s*recommended\s*$", r"^\s*more for you\s*$", r"^\s*continue reading\s*$",
        r"^\s*print\s*$", r"^\s*close\s*$", r"^\s*search for\s*$",
        r"^\s*home\s*$", r"^\s*about\s*$", r"^\s*corrections\s*$",
        r"^\s*politics\s*$", r"^\s*top story\s*$",
    ]
    bad_contains_patterns = [
        r"adkeeper", r"newsletter", r"sign up", r"read more", r"related articles?",
        r"sponsored", r"promoted", r"advertisement",
        r"this article may contain commentary", r"reflects the author'?s opinion",
        r"follow us", r"share this", r"privacy policy", r"terms of use",
        r"sitemap", r"all rights reserved", r"facebook", r"messenger", r"telegram",
        r"email", r"print",
    ]
    stop_patterns = [
        r"related articles?", r"read more", r"more for you", r"recommended",
        r"you may also like", r"latest news", r"trending", r"newsletter",
        r"sign up", r"follow us", r"share this", r"privacy policy",
        r"terms of use", r"sitemap", r"copyright", r"all rights reserved",
    ]
    lines = text.split("\n")
    cleaned_lines = []
    last_blank = True
    seen_recent = []
    for raw_line in lines:
        line = re.sub(r"\s+", " ", raw_line).strip()
        low = line.lower()
        if not line:
            if not last_blank:
                cleaned_lines.append("")
            last_blank = True
            continue
        if any(re.search(p, low, re.IGNORECASE) for p in bad_exact_patterns):
            continue
        if any(re.search(p, low, re.IGNORECASE) for p in bad_contains_patterns):
            if len(line) <= 140:
                continue
        if low == "cbf2 22marcbf2 22mar":
            continue
        if re.fullmatch(r"[A-Za-z]{2,10}\d{1,4}[A-Za-z0-9 ]*", line):
            continue
        if re.fullmatch(r"[A-Za-z0-9 ]{1,40}", line) and any(ch.isdigit() for ch in line) and len(line.split()) <= 6:
            continue
        short_ui_words = {"facebook","twitter","x","telegram","email","print","copy link","menu","search","close","next","previous"}
        if low in short_ui_words:
            continue
        norm = re.sub(r"[^a-z0-9]+", " ", low).strip()
        if norm and norm in seen_recent[-80:]:
            continue
        if norm:
            seen_recent.append(norm)
        cleaned_lines.append(line)
        last_blank = False
    cleaned_text = "\n".join(cleaned_lines)
    cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text).strip()
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", cleaned_text) if p.strip()]
    if not paragraphs:
        return cleaned_text
    filtered_paragraphs = []
    started_main = False
    for i, para in enumerate(paragraphs):
        low = para.lower()
        word_count = len(para.split())
        if word_count <= 8 and any(re.search(p, low, re.IGNORECASE) for p in stop_patterns):
            continue
        if started_main:
            if any(re.search(p, low, re.IGNORECASE) for p in stop_patterns):
                break
            if word_count <= 12 and (
                any(re.search(p, low, re.IGNORECASE) for p in bad_contains_patterns) or
                any(re.search(p, low, re.IGNORECASE) for p in stop_patterns)
            ):
                break
        if not started_main:
            if word_count >= 12:
                started_main = True
                filtered_paragraphs.append(para)
            else:
                if i == 0 and 3 <= word_count <= 14:
                    filtered_paragraphs.append(para)
                continue
        else:
            filtered_paragraphs.append(para)
    final_paragraphs = []
    for para in filtered_paragraphs:
        low = para.lower()
        wc = len(para.split())
        if wc <= 12 and any(re.search(p, low, re.IGNORECASE) for p in stop_patterns):
            continue
        if wc <= 10 and any(re.search(p, low, re.IGNORECASE) for p in bad_contains_patterns):
            continue
        final_paragraphs.append(para)
    result = "\n\n".join(final_paragraphs).strip()
    result = re.sub(r"\n{3,}", "\n\n", result).strip()
    return result

def sanitize_text(text, max_len=None):
    text = str(text).strip()
    banned = ["featured image", "Featured image", "featured-image", "Featured Image"]
    for item in banned:
        text = text.replace(item, "")
    text = " ".join(text.split()).strip(" -,:")
    if max_len:
        text = text[:max_len].strip()
    return text

def make_prompt(keyword):
    return f"""You are an image SEO assistant.

Analyze the image and return ONLY valid JSON with these exact keys:
alt_text
img_title
caption

Rules:
- alt_text: max 60 characters, clear, natural
- img_title: short and clear
- caption: 1 natural sentence, engaging
- never use the phrase "featured image"
- do not mention "featured image"
- include the keyword naturally if it fits
- no markdown
- no explanation
- no extra keys

Focus keyword / scene notes: {keyword}"""


# ─── Flask Routes ────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/test-key", methods=["POST"])
def test_key():
    data = request.json or {}
    api_key = (data.get("api_key") or "").strip()
    if not api_key:
        return jsonify({"ok": False, "error": "API key is empty"}), 400
    try:
        verify_together_api_key(api_key, timeout=20)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/process-article", methods=["POST"])
def process_article():
    data = request.json or {}
    raw = (data.get("text") or "").strip()
    api_key = (data.get("api_key") or "").strip()

    if not raw or raw in ("Paste your article here...", "Paste your article here."):
        return jsonify({"ok": False, "error": "Please paste an article first"}), 400

    lines = strip_internal_seo_lines(clean_lines(raw))
    if not lines:
        return jsonify({"ok": False, "error": "No valid content found"}), 400

    h1 = guess_title(lines)
    intro = build_intro(lines)
    sections = split_body_into_sections(lines, num_sections=None)
    structure = build_nested_article_structure(sections)

    focus_keyphrase = make_focus_keyphrase(h1)
    seo_titles = make_seo_title_options(h1)
    meta_options = make_meta_options(intro, h1)
    seo_title = seo_titles[0] if seo_titles else h1
    meta_description = meta_options[0] if meta_options else trim_at_word_boundary(intro if intro else h1, 160)
    slug = make_slug(h1)
    short_summary = make_short_summary(intro, structure)
    wp_html = build_wordpress_html_fragment(h1, intro, structure)

    result = {
        "ok": True,
        "h1": h1,
        "intro": intro,
        "structure": structure,
        "focus_keyphrase": focus_keyphrase,
        "seo_title": seo_title,
        "meta_description": meta_description,
        "slug": slug,
        "short_summary": short_summary,
        "wp_html": wp_html,
    }

    # AI SEO (optional)
    if api_key:
        try:
            prompt_text = build_seo_source_text(h1, intro, structure)
            system_prompt = (
                "You are an SEO editor for WordPress news articles. "
                "Return only valid JSON with keys focus_keyphrase, seo_title, meta_description. "
                "Choose a focus keyphrase of 2 to 5 words, an SEO title under 60 characters, "
                "and a meta description under 160 characters. Make them engaging, factual, keyword-focused, "
                "and suitable for Rank Math or Yoast style WordPress SEO."
            )
            user_prompt = (
                "Article content:\n" + prompt_text + "\n\n"
                "Return JSON only like:\n"
                '{"focus_keyphrase":"...","seo_title":"...","meta_description":"..."}'
            )
            response = together_chat_completion(
                api_key=api_key,
                model=ARTICLE_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                timeout=20,
            )
            content = extract_message_content(response)
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                ai_data = json.loads(match.group(0))
                if ai_data.get("focus_keyphrase"):
                    result["focus_keyphrase"] = trim_at_word_boundary(normalize_space(ai_data["focus_keyphrase"]), 80)
                if ai_data.get("seo_title"):
                    result["seo_title"] = trim_at_word_boundary(normalize_space(ai_data["seo_title"]), 60)
                if ai_data.get("meta_description"):
                    result["meta_description"] = trim_at_word_boundary(normalize_space(ai_data["meta_description"]), 160)
                result["ai_seo"] = True
        except Exception:
            pass

    return jsonify(result)


@app.route("/api/fetch-url", methods=["POST"])
def fetch_url():
    data = request.json or {}
    url = (data.get("url") or "").strip()
    if not url or not re.match(r"^https?://", url, re.IGNORECASE):
        return jsonify({"ok": False, "error": "Invalid URL"}), 400
    try:
        import trafilatura
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
        response = requests.get(url, headers=headers, timeout=25)
        response.raise_for_status()
        extracted = trafilatura.extract(
            response.text,
            include_comments=False,
            include_tables=False,
            include_images=False,
            include_links=False,
            no_fallback=False,
            favor_precision=True,
        )
        if not extracted or not extracted.strip():
            return jsonify({"ok": False, "error": "Could not extract main article text from this URL"}), 400
        cleaned = clean_imported_article_text(extracted)
        if not cleaned.strip():
            return jsonify({"ok": False, "error": "Article became empty after cleaning"}), 400
        return jsonify({"ok": True, "text": cleaned})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/generate-image-seo", methods=["POST"])
def generate_image_seo():
    api_key = (request.form.get("api_key") or "").strip()
    keyword = (request.form.get("keyword") or "image SEO").strip()
    image_file = request.files.get("image")

    if not image_file:
        return jsonify({"ok": False, "error": "No image uploaded"}), 400

    raw = image_file.read()
    ext = os.path.splitext(image_file.filename)[1].lower().replace(".", "")
    if ext == "jpg":
        ext = "jpeg"
    if ext not in ["jpeg", "png", "webp", "gif"]:
        ext = "jpeg"

    # Resize image if >1MB to avoid timeout on Render free tier
    try:
        from PIL import Image as PILImage
        import io as _io
        if len(raw) > 1_000_000:
            img_pil = PILImage.open(_io.BytesIO(raw)).convert("RGB")
            img_pil.thumbnail((1024, 1024), PILImage.LANCZOS)
            buf = _io.BytesIO()
            img_pil.save(buf, format="JPEG", quality=85)
            raw = buf.getvalue()
            ext = "jpeg"
    except Exception:
        pass

    b64 = base64.b64encode(raw).decode("utf-8")
    image_data_url = f"data:image/{ext};base64,{b64}"

    if not api_key:
        base = sanitize_text(keyword or "image seo", 60)
        base_title = base.title() if base else "Image"
        return jsonify({
            "ok": True,
            "alt_text": sanitize_text(base, 60) or "Optimized image",
            "img_title": sanitize_text(base_title, 80) or "Optimized Image",
            "caption": sanitize_text(f"{base_title} image for WordPress SEO.", 180),
            "ai": False,
        })

    try:
        prompt = make_prompt(keyword)
        response = together_chat_completion(
            api_key=api_key,
            model=VISION_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                ],
            }],
            temperature=0.2,
            timeout=90,
        )
        raw_text = extract_message_content(response)
        try:
            img_data = json.loads(raw_text)
        except Exception:
            cleaned = raw_text.replace("```json", "").replace("```", "").strip()
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            img_data = json.loads(match.group(0) if match else cleaned)
        return jsonify({
            "ok": True,
            "alt_text": sanitize_text(img_data.get("alt_text", ""), 60),
            "img_title": sanitize_text(img_data.get("img_title", ""), 80),
            "caption": sanitize_text(img_data.get("caption", ""), 180),
            "ai": True,
        })
    except Exception as e:
        base = sanitize_text(keyword or "image seo", 60)
        base_title = base.title() if base else "Image"
        return jsonify({
            "ok": True,
            "alt_text": sanitize_text(base, 60) or "Optimized image",
            "img_title": sanitize_text(base_title, 80) or "Optimized Image",
            "caption": sanitize_text(f"{base_title} image for WordPress SEO.", 180),
            "ai": False,
            "ai_error": str(e),  # ← បន្ថែម error detail ដើម្បី debug
        })


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
