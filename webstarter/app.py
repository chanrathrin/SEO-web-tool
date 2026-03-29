import base64
import html
import io
import json
import os
import re
import tempfile
from typing import Any, Dict, List, Optional

import requests
import trafilatura
from flask import Flask, jsonify, render_template, request, session
from PIL import Image

TOGETHER_BASE_URL = "https://api.together.xyz/v1"
ARTICLE_MODEL = "Qwen/Qwen3.5-9B"
VISION_MODELS = [
    "moonshotai/Kimi-K2.5",
    "Qwen/Qwen3-VL-8B-Instruct",
]

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024


def together_headers(api_key: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def verify_together_api_key(api_key: str, timeout: int = 20):
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


def together_chat_completion(
    api_key: str,
    model: str,
    messages,
    temperature: float = 0.3,
    timeout: int = 60,
    response_format: Optional[Dict[str, Any]] = None,
    reasoning: Optional[Dict[str, Any]] = None,
):
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if response_format:
        payload["response_format"] = response_format
    if reasoning is not None:
        payload["reasoning"] = reasoning
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


def extract_message_content(response_json: Dict[str, Any]) -> str:
    choices = response_json.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content", "")
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, dict):
                txt = item.get("text") or item.get("content") or ""
                if txt:
                    parts.append(str(txt))
            elif item:
                parts.append(str(item))
        return "\n".join(parts).strip()
    return str(content or "").strip()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    key = (session.get("together_api_key") or "").strip()
    return jsonify({
        "has_api_key": bool(key),
        "status": "Ready",
    })


@app.route("/api/test-key", methods=["POST"])
def api_test_key():
    data = request.get_json(silent=True) or {}
    api_key = (data.get("api_key") or "").strip()
    if not api_key:
        return jsonify({"ok": False, "error": "Please paste your API key first."}), 400
    try:
        verify_together_api_key(api_key)
        return jsonify({"ok": True, "message": "API key is valid and ready to use."})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/save-key", methods=["POST"])
def api_save_key():
    data = request.get_json(silent=True) or {}
    api_key = (data.get("api_key") or "").strip()
    if not api_key:
        return jsonify({"ok": False, "error": "Please paste your API key first."}), 400
    session["together_api_key"] = api_key
    return jsonify({"ok": True, "message": "API key applied successfully"})


@app.route("/api/clear-key", methods=["POST"])
def api_clear_key():
    session.pop("together_api_key", None)
    return jsonify({"ok": True, "message": "Saved API key cleared"})


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_compare_text(text: str) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"[\"'“”`]+", "", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def trim_at_word_boundary(text: str, limit: int) -> str:
    text = normalize_space(text)
    if len(text) <= limit:
        return text
    cut = text[:limit].rstrip()
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,.-:;")


def clean_lines(text: str) -> List[str]:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\u00a0", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    raw_lines = [line.strip() for line in text.split("\n")]
    cleaned: List[str] = []
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


def strip_internal_seo_lines(lines: List[str]) -> List[str]:
    seo_prefixes = (
        "Focus Keyphrase:",
        "SEO Title:",
        "Meta Description:",
        "Slug (URL):",
        "Slug:",
        "Short Summary:",
    )
    cleaned = []
    for line in lines:
        s = line.strip()
        if any(s.startswith(prefix) for prefix in seo_prefixes):
            continue
        cleaned.append(line)
    while cleaned and cleaned[-1] == "":
        cleaned.pop()
    return cleaned


def guess_title(lines: List[str]) -> str:
    if not lines:
        return "Untitled Article"
    title = normalize_space(lines[0])
    return trim_at_word_boundary(title, 140) or "Untitled Article"


def build_intro(lines: List[str]) -> str:
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


def remove_heading_from_body(heading: str, body: str) -> str:
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
        remaining = " ".join(body_words[matched:]).lstrip(" ,.;:-–—)")
        return remaining or body
    return body


def extract_body_paragraphs(lines: List[str]) -> List[str]:
    paragraphs = []
    current: List[str] = []
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


def split_body_into_sections(lines: List[str], num_sections: Optional[int] = None) -> List[str]:
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
        chunk = blocks[idx: idx + take]
        idx += take
        merged = "\n\n".join(chunk).strip()
        if merged:
            sections.append(merged)
    return sections[:3]


def clean_heading_candidate(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    text = text.strip(' "\'“”‘’.,:;!?-')
    text = re.sub(r"^[^A-Za-z0-9]+", "", text)
    text = re.sub(r"[^A-Za-z0-9]+$", "", text)
    return text


def sentence_candidates_from_text(text: str) -> List[str]:
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


def phrase_candidates_from_text(text: str) -> List[str]:
    words = [w for w in clean_heading_candidate(text).split() if w]
    candidates = []
    for length in (5, 6, 7, 8):
        if len(words) >= length:
            candidates.append(" ".join(words[:length]))
    return candidates


def choose_heading_from_text(text: str, seen: set) -> str:
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


def build_nested_article_structure(sections: List[str]) -> List[Dict[str, Any]]:
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
        structure.append({
            "h2": h2,
            "subsections": [{"h3": h2, "body": subsection_body}],
        })
    return structure[:3]


def make_slug(title: str) -> str:
    slug = re.sub(r"[^a-z0-9\s-]", "", (title or "").lower())
    slug = re.sub(r"\s+", "-", slug).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug[:80] or "news-update"


def make_focus_keyphrase(title: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", title or "").strip()
    words = cleaned.split()
    return " ".join(words[:5]).strip() or "news update"


def make_seo_title_options(title: str) -> List[str]:
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


def make_meta_options(intro: str, title: str) -> List[str]:
    source = normalize_space(intro if intro else title)
    if not source:
        return []
    opts = [
        trim_at_word_boundary(source, 160),
        trim_at_word_boundary((title or "") + " — " + source, 160),
    ]
    out, seen = [], set()
    for x in opts:
        key = x.lower()
        if x and key not in seen:
            out.append(x)
            seen.add(key)
    return out[:2]


def make_short_summary(intro: str, structure: List[Dict[str, Any]]) -> str:
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


def build_seo_source_text(h1: str, intro: str, structure: List[Dict[str, Any]]) -> str:
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


def generate_ai_article_fields(api_key: str, h1: str, intro: str, structure: List[Dict[str, Any]]) -> Optional[Dict[str, str]]:
    prompt_text = build_seo_source_text(h1, intro, structure)
    if not prompt_text:
        return None
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
        response_format={"type": "json_object"},
    )
    content = extract_message_content(response)
    data = safe_json_load(content)
    focus_keyphrase = normalize_space(data.get("focus_keyphrase", ""))
    seo_title = normalize_space(data.get("seo_title", ""))
    meta_description = normalize_space(data.get("meta_description", ""))
    if not focus_keyphrase or not seo_title or not meta_description:
        return None
    return {
        "focus_keyphrase": trim_at_word_boundary(focus_keyphrase, 80),
        "seo_title": trim_at_word_boundary(seo_title, 60),
        "meta_description": trim_at_word_boundary(meta_description, 160),
    }


def clean_imported_article_text(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    bad_exact_patterns = [
        r"^\s*advertisement\s*$", r"^\s*sponsored\s*$", r"^\s*promoted\s*$", r"^\s*related articles?\s*$",
        r"^\s*read more\s*$", r"^\s*newsletter\s*$", r"^\s*sign up\s*$", r"^\s*adkeeper\s*$",
        r"^\s*partner content\s*$", r"^\s*recommended\s*$", r"^\s*more for you\s*$", r"^\s*continue reading\s*$",
        r"^\s*print\s*$", r"^\s*close\s*$", r"^\s*search for\s*$", r"^\s*home\s*$", r"^\s*about\s*$",
        r"^\s*corrections\s*$", r"^\s*politics\s*$", r"^\s*top story\s*$",
    ]
    bad_contains_patterns = [
        r"adkeeper", r"newsletter", r"sign up", r"read more", r"related articles?", r"sponsored",
        r"promoted", r"advertisement", r"this article may contain commentary", r"reflects the author'?s opinion",
        r"follow us", r"share this", r"privacy policy", r"terms of use", r"sitemap", r"all rights reserved",
        r"facebook", r"messenger", r"telegram", r"email", r"print",
    ]
    stop_patterns = [
        r"related articles?", r"read more", r"more for you", r"recommended", r"you may also like",
        r"latest news", r"trending", r"newsletter", r"sign up", r"follow us", r"share this",
        r"privacy policy", r"terms of use", r"sitemap", r"copyright", r"all rights reserved",
    ]

    lines = text.split("\n")
    cleaned_lines: List[str] = []
    last_blank = True
    seen_recent: List[str] = []
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
        if re.fullmatch(r"[A-Za-z0-9]{2,10}\s+\d{1,2}[A-Za-z]{2,10}[A-Za-z0-9 ]*", line):
            continue
        short_ui_words = {"facebook", "twitter", "x", "telegram", "email", "print", "copy link", "menu", "search", "close", "next", "previous"}
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
            if word_count <= 12 and (any(re.search(p, low, re.IGNORECASE) for p in bad_contains_patterns) or any(re.search(p, low, re.IGNORECASE) for p in stop_patterns)):
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
    return re.sub(r"\n{3,}", "\n\n", result).strip()


def fetch_article_from_url_sync(url: str) -> str:
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
        raise ValueError("Could not extract main article text from this URL")
    cleaned_text = clean_imported_article_text(extracted)
    if not cleaned_text.strip():
        raise ValueError("Article became empty after cleaning")
    return cleaned_text


@app.route("/api/article/generate", methods=["POST"])
def article_generate():
    data = request.get_json(silent=True) or {}
    article_text = (data.get("article_text") or "").strip()
    url = (data.get("url") or "").strip()

    if url and re.match(r"^https?://", url, re.IGNORECASE) and not article_text:
        article_text = fetch_article_from_url_sync(url)

    if not article_text or article_text.lower() == "paste your article here...":
        return jsonify({"ok": False, "error": "Please paste a news URL or article first."}), 400

    lines = strip_internal_seo_lines(clean_lines(article_text))
    if not lines:
        return jsonify({"ok": False, "error": "No valid content found."}), 400

    h1 = guess_title(lines)
    intro = build_intro(lines)
    sections = split_body_into_sections(lines)
    structure = build_nested_article_structure(sections)

    focus_keyphrase = make_focus_keyphrase(h1)
    seo_titles = make_seo_title_options(h1)
    meta_options = make_meta_options(intro, h1)
    seo_title = seo_titles[0] if seo_titles else h1
    meta_description = meta_options[0] if meta_options else trim_at_word_boundary(intro if intro else h1, 160)
    slug = make_slug(h1)
    short_summary = make_short_summary(intro, structure)

    api_key = (session.get("together_api_key") or "").strip()
    if api_key:
        try:
            ai_fields = generate_ai_article_fields(api_key, h1, intro, structure)
            if ai_fields:
                focus_keyphrase = ai_fields["focus_keyphrase"]
                seo_title = ai_fields["seo_title"]
                meta_description = ai_fields["meta_description"]
        except Exception:
            pass

    html_parts = []
    if h1:
        html_parts.append(f"<h1>{html.escape(h1)}</h1>")
    if intro:
        html_parts.append(f"<p>{html.escape(intro)}</p>")
    for sec in structure:
        if sec.get("h2"):
            html_parts.append(f"<h2>{html.escape(sec['h2'])}</h2>")
        body = ""
        if sec.get("subsections"):
            body = sec["subsections"][0].get("body", "").strip()
        if body:
            for paragraph in [p.strip() for p in body.split("\n\n") if p.strip()]:
                html_parts.append(f"<p>{html.escape(paragraph)}</p>")

    return jsonify({
        "ok": True,
        "article_text": article_text,
        "h1": h1,
        "intro": intro,
        "structure": structure,
        "focus_keyphrase": focus_keyphrase,
        "seo_title": seo_title,
        "meta_description": meta_description,
        "slug": slug,
        "short_summary": short_summary,
        "wordpress_html": "\n".join(html_parts).strip(),
    })


def sanitize_text(text: str, limit: int) -> str:
    text = normalize_space(text)
    text = re.sub(r"[\r\n\t]+", " ", text)
    return trim_at_word_boundary(text, limit)


def image_to_data_url(file_storage) -> str:
    raw = file_storage.read()
    file_storage.stream.seek(0)
    ext = os.path.splitext(file_storage.filename or "")[1].lower().replace(".", "")
    if ext == "jpg":
        ext = "jpeg"
    if ext not in ["jpeg", "png", "webp", "gif"]:
        ext = "jpeg"
    b64 = base64.b64encode(raw).decode("utf-8")
    return f"data:image/{ext};base64,{b64}"


def safe_json_load(raw_text: str) -> Dict[str, Any]:
    raw_text = (raw_text or "").strip()
    if not raw_text:
        raise ValueError("Empty model response")
    try:
        parsed = json.loads(raw_text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    cleaned = raw_text.replace("```json", "").replace("```", "").strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    candidate = match.group(0) if match else cleaned
    parsed = json.loads(candidate)
    if not isinstance(parsed, dict):
        raise ValueError("Model response was not a JSON object")
    return parsed


def make_image_prompt(keyword: str) -> str:
    return f"""
You are an image SEO assistant.

Analyze the image and return ONLY valid JSON with these exact keys:
alt_text
img_title
caption

Rules:
- alt_text: max 60 characters, clear, natural
- img_title: short and clear
- caption: 1 natural sentence, engaging
- never use the phrase \"featured image\"
- do not mention \"featured image\"
- include the keyword naturally if it fits
- no markdown
- no explanation
- no extra keys

Focus keyword / scene notes: {keyword}
""".strip()


def call_image_model(api_key: str, image_data_url: str, keyword: str) -> Dict[str, str]:
    prompt = make_image_prompt(keyword)
    last_error = None
    for model in VISION_MODELS:
        try:
            response = together_chat_completion(
                api_key=api_key,
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": image_data_url}},
                        ],
                    }
                ],
                temperature=0.6,
                timeout=90,
                response_format={"type": "json_object"},
                reasoning={"enabled": False},
            )
            raw_text = extract_message_content(response)
            data = safe_json_load(raw_text)
            alt_text = sanitize_text(data.get("alt_text", ""), 60)
            img_title = sanitize_text(data.get("img_title", ""), 80)
            caption = sanitize_text(data.get("caption", ""), 180)
            if not alt_text or not img_title or not caption:
                raise ValueError("Model returned incomplete SEO fields")
            return {"alt_text": alt_text, "img_title": img_title, "caption": caption, "model": model}
        except Exception as e:
            last_error = f"{model}: {e}"
    raise RuntimeError(last_error or "Image SEO generation failed")


def crop_from_request(file_storage, crop_data: Dict[str, Any]) -> io.BytesIO:
    image = Image.open(file_storage.stream).convert("RGB")
    file_storage.stream.seek(0)
    iw, ih = image.size
    left = max(0, min(iw, int(round(float(crop_data.get("left", 0))))))
    top = max(0, min(ih, int(round(float(crop_data.get("top", 0))))))
    width = max(1, int(round(float(crop_data.get("width", iw)))))
    height = max(1, int(round(float(crop_data.get("height", ih)))))
    right = max(left + 1, min(iw, left + width))
    bottom = max(top + 1, min(ih, top + height))
    cropped = image.crop((left, top, right, bottom))
    out = io.BytesIO()
    cropped.save(out, format="JPEG", quality=92, optimize=True)
    out.seek(0)
    return out


@app.route("/api/image/generate", methods=["POST"])
def image_generate():
    api_key = (session.get("together_api_key") or "").strip()
    if not api_key:
        return jsonify({"ok": False, "error": "No valid Together AI API key loaded."}), 400

    uploaded = request.files.get("image")
    if uploaded is None or not uploaded.filename:
        return jsonify({"ok": False, "error": "Please upload an image first."}), 400

    keyword = (request.form.get("keyword") or "image SEO").strip() or "image SEO"
    crop_raw = request.form.get("crop") or ""
    try:
        if crop_raw:
            crop_data = json.loads(crop_raw)
            cropped_stream = crop_from_request(uploaded, crop_data)
            dummy = io.BytesIO(cropped_stream.read())
            dummy.name = uploaded.filename
            dummy.seek(0)
            image_data_url = image_to_data_url(dummy)
        else:
            image_data_url = image_to_data_url(uploaded)
        result = call_image_model(api_key, image_data_url, keyword)
        return jsonify({
            "ok": True,
            "alt_text": result["alt_text"],
            "img_title": result["img_title"],
            "caption": result["caption"],
            "model": result["model"],
        })
    except Exception as e:
        return jsonify({"ok": False, "error": f"Image SEO could not be generated with the API. Reason: {e}"}), 500


if __name__ == "__main__":
    app.run(debug=True)
