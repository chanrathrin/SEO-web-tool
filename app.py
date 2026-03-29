import os
import re
import io
import html
import json
import base64
import requests
from PIL import Image, ImageEnhance, ImageFilter
from flask import Flask, render_template, request, jsonify, send_file
from bs4 import BeautifulSoup

try:
    import trafilatura
except Exception:
    trafilatura = None

app = Flask(__name__)

TOGETHER_BASE_URL = "https://api.together.xyz/v1"
ARTICLE_MODEL = os.getenv("ARTICLE_MODEL", "Qwen/Qwen3.5-9B")
VISION_MODEL = os.getenv("VISION_MODEL", "moonshotai/Kimi-K2.5")


def together_headers(api_key: str):
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


def together_chat_completion(api_key: str, model: str, messages, temperature: float = 0.3, timeout: int = 60):
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
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


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


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


def esc(value):
    return html.escape(str(value), quote=True)


# -----------------------------
# Article helpers
# -----------------------------
def clean_lines(text: str):
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
        remaining = " ".join(body_words[matched:]).lstrip(" ,.;:-–—)")
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
    text = text.strip(' "\'“”‘’.,:;!?-')
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

        structure.append({
            "h2": h2,
            "subsections": [
                {
                    "h3": h2,
                    "body": subsection_body
                }
            ]
        })

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


def build_wordpress_html_fragment(h1, intro, structure):
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


def build_output_preview(h1, intro, structure):
    parts = []

    if h1:
        parts.extend(["H1", h1, ""])

    if intro:
        parts.extend(["Intro", intro, ""])

    for sec in structure:
        if sec.get("h2"):
            parts.extend(["H2", sec["h2"], ""])

        for sub in sec.get("subsections", []):
            if sub.get("h3"):
                parts.extend(["H3", sub["h3"], ""])

            if sub.get("body"):
                paragraphs = [p.strip() for p in sub["body"].split("\n\n") if p.strip()]
                for para in paragraphs:
                    parts.extend(["Paragraph", para, ""])

    return "\n".join(parts).strip()


def extract_main_text_from_html(html_text):
    extracted = ""

    if trafilatura is not None:
        try:
            extracted = trafilatura.extract(
                html_text,
                include_comments=False,
                include_tables=False,
                include_images=False,
                include_links=False,
                no_fallback=False,
                favor_precision=True,
            ) or ""
        except Exception:
            extracted = ""

    if extracted.strip():
        return extracted

    try:
        soup = BeautifulSoup(html_text, "html.parser")

        for tag in soup(["script", "style", "noscript", "iframe", "svg", "header", "footer", "nav", "aside", "form"]):
            tag.decompose()

        candidates = []
        selectors = [
            "article",
            "main",
            "[role='main']",
            ".post-content",
            ".entry-content",
            ".article-content",
            ".content",
            ".post-body",
        ]

        for sel in selectors:
            try:
                candidates.extend(soup.select(sel))
            except Exception:
                pass

        if candidates:
            best = max(candidates, key=lambda x: len(x.get_text(" ", strip=True)))
            extracted = best.get_text("\n", strip=True)
        else:
            extracted = soup.get_text("\n", strip=True)

    except Exception:
        extracted = re.sub(r"<[^>]+>", " ", html_text or "")

    return html.unescape(extracted or "")


def clean_imported_article_text(text):
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")

    bad_exact_patterns = [
        r"^\s*advertisement\s*$",
        r"^\s*sponsored\s*$",
        r"^\s*promoted\s*$",
        r"^\s*related articles?\s*$",
        r"^\s*read more\s*$",
        r"^\s*newsletter\s*$",
        r"^\s*sign up\s*$",
        r"^\s*recommended\s*$",
        r"^\s*more for you\s*$",
        r"^\s*continue reading\s*$",
        r"^\s*print\s*$",
        r"^\s*close\s*$",
        r"^\s*home\s*$",
        r"^\s*about\s*$",
        r"^\s*corrections\s*$",
    ]

    bad_contains_patterns = [
        r"newsletter",
        r"sign up",
        r"read more",
        r"related articles?",
        r"sponsored",
        r"promoted",
        r"advertisement",
        r"follow us",
        r"share this",
        r"privacy policy",
        r"terms of use",
        r"sitemap",
        r"all rights reserved",
        r"facebook",
        r"messenger",
        r"telegram",
        r"print",
    ]

    raw_lines = [line.strip() for line in text.split("\n")]
    clean = []

    for line in raw_lines:
        if not line:
            clean.append("")
            continue

        low = line.lower().strip()

        if any(re.search(p, low) for p in bad_exact_patterns):
            continue

        if any(re.search(p, low) for p in bad_contains_patterns):
            continue

        clean.append(line)

    text = "\n".join(clean)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def import_article_from_url(url):
    try:
        response = requests.get(
            url,
            timeout=25,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            },
        )
    except requests.RequestException as e:
        raise ValueError(f"Request failed: {e}")

    status_code = response.status_code
    content_type = (response.headers.get("Content-Type") or "").lower()
    html_text = response.text or ""
    lower_html = html_text.lower()

    blocked_markers = [
        "access denied",
        "forbidden",
        "request blocked",
        "bot detected",
        "captcha",
        "verify you are human",
        "cf-browser-verification",
        "attention required",
        "enable javascript and cookies",
        "security check",
        "blocked by",
        "temporarily unavailable",
        "please turn javascript on",
        "please enable javascript",
        "checking your browser",
        "cloudflare",
    ]

    if status_code == 403:
        raise ValueError(
            "Could not import article from URL.\n\n"
            "This website blocked auto import (403).\n\n"
            "Please copy and paste the article text manually into Input Article."
        )

    if status_code == 401:
        raise ValueError(
            "Could not import article from URL.\n\n"
            "This page requires authorization/login and cannot be auto imported."
        )

    if status_code == 404:
        raise ValueError(
            "Could not import article from URL.\n\n"
            "Article not found (404). Please check the URL."
        )

    if status_code == 429:
        raise ValueError(
            "Could not import article from URL.\n\n"
            "This website is rate-limiting requests (429). Please try again later."
        )

    if status_code >= 500:
        raise ValueError(
            f"Could not import article from URL.\n\n"
            f"This website returned a server error ({status_code}). Please try again later."
        )

    if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
        raise ValueError(
            "Could not import article from URL.\n\n"
            "This URL does not appear to be a standard HTML article page."
        )

    if any(marker in lower_html for marker in blocked_markers):
        if "403" in lower_html or "forbidden" in lower_html or "access denied" in lower_html:
            raise ValueError(
                "Could not import article from URL.\n\n"
                "This website blocked auto import (403).\n\n"
                "Please copy and paste the article text manually into Input Article."
            )
        raise ValueError(
            "Could not import article from URL.\n\n"
            "This website appears to block automatic article import.\n\n"
            "Please copy and paste the article text manually into Input Article."
        )

    visible_text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html_text)).strip()
    if len(visible_text) < 200:
        raise ValueError(
            "Could not import article from URL.\n\n"
            "The page loaded, but it does not contain enough readable article content to import."
        )

    extracted = extract_main_text_from_html(html_text)
    extracted = clean_imported_article_text(extracted)

    if not extracted or len(extracted.strip()) < 120:
        raise ValueError(
            "Could not import article from URL.\n\n"
            "This page could not be auto imported. Please copy and paste the article text manually."
        )

    return extracted


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


def generate_ai_seo_fields(api_key, h1, intro, structure):
    if not api_key:
        return None

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

    try:
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
        if not match:
            return None

        data = json.loads(match.group(0))
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
    except Exception:
        return None


def process_article_text(article_text, api_key=""):
    lines = clean_lines(article_text)
    lines = strip_internal_seo_lines(lines)

    if not lines:
        raise ValueError("Please paste a news URL or article first.")

    h1 = guess_title(lines)
    intro = build_intro(lines)
    sections = split_body_into_sections(lines)
    structure = build_nested_article_structure(sections)

    ai_seo = generate_ai_seo_fields(api_key, h1, intro, structure)

    focus_keyphrase = ai_seo["focus_keyphrase"] if ai_seo else make_focus_keyphrase(h1)
    seo_title = ai_seo["seo_title"] if ai_seo else trim_at_word_boundary(h1, 60)
    meta_description = ai_seo["meta_description"] if ai_seo else trim_at_word_boundary(intro or h1, 160)
    slug = make_slug(h1)
    short_summary = make_short_summary(intro, structure)
    wordpress_html = build_wordpress_html_fragment(h1, intro, structure)
    output_preview = build_output_preview(h1, intro, structure)

    return {
        "h1": h1,
        "intro": intro,
        "structure": structure,
        "focus_keyphrase": focus_keyphrase,
        "seo_title": seo_title,
        "meta_description": meta_description,
        "slug": slug,
        "short_summary": short_summary,
        "wordpress_html": wordpress_html,
        "output_preview": output_preview,
    }


# -----------------------------
# Image helpers
# -----------------------------
def sanitize_text(value: str, limit: int):
    value = normalize_space(value or "")
    value = value.replace("featured image", "").replace("Featured Image", "")
    return trim_at_word_boundary(value, limit)


def optimize_image_bytes(
    image_bytes: bytes,
    max_kb: int = 100,
    brightness=1.0,
    sharpness=1.0,
    blur_radius=0.0,
):
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    if abs(brightness - 1.0) > 0.001:
        image = ImageEnhance.Brightness(image).enhance(brightness)

    if abs(sharpness - 1.0) > 0.001:
        image = ImageEnhance.Sharpness(image).enhance(sharpness)

    if blur_radius > 0:
        image = image.filter(ImageFilter.GaussianBlur(radius=blur_radius))

    quality = 95
    best = None

    while quality >= 20:
        out = io.BytesIO()
        image.save(out, format="JPEG", optimize=True, quality=quality)
        data = out.getvalue()
        best = data
        if len(data) <= max_kb * 1024:
            break
        quality -= 5

    return best


def heuristic_image_fields(keyword: str):
    base = sanitize_text(keyword or "image seo", 60)
    base_title = base.title() if base else "Image"
    return {
        "alt_text": sanitize_text(base, 60) or "Optimized image",
        "image_title": sanitize_text(base_title, 80) or "Optimized Image",
        "caption": sanitize_text(f"{base_title} image for WordPress SEO.", 180),
    }


def generate_image_seo_fields(api_key, scene_text, image_b64):
    if not api_key:
        return heuristic_image_fields(scene_text)

    prompt = f"""
You are an image SEO assistant.

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

Focus keyword / scene notes: {scene_text or 'image SEO'}
"""

    try:
        response = together_chat_completion(
            api_key=api_key,
            model=VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                    ],
                }
            ],
            temperature=0.2,
            timeout=90,
        )
        raw_text = extract_message_content(response)
        try:
            data = json.loads(raw_text)
        except Exception:
            cleaned = raw_text.replace("```json", "").replace("```", "").strip()
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            data = json.loads(match.group(0) if match else cleaned)

        alt_text = sanitize_text(data.get("alt_text", ""), 60)
        image_title = sanitize_text(data.get("img_title", ""), 80)
        caption = sanitize_text(data.get("caption", ""), 180)

        if not alt_text and not image_title and not caption:
            return heuristic_image_fields(scene_text)

        return {
            "alt_text": alt_text or heuristic_image_fields(scene_text)["alt_text"],
            "image_title": image_title or heuristic_image_fields(scene_text)["image_title"],
            "caption": caption or heuristic_image_fields(scene_text)["caption"],
        }
    except Exception:
        return heuristic_image_fields(scene_text)


# -----------------------------
# Routes
# -----------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    return {"ok": True}


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


@app.route("/api/process-article", methods=["POST"])
def api_process_article():
    data = request.get_json(silent=True) or {}
    article_text = (data.get("article_text") or "").strip()
    article_url = (data.get("article_url") or "").strip()
    api_key = (data.get("api_key") or os.getenv("TOGETHER_API_KEY", "")).strip()

    try:
        if article_url:
            article_text = import_article_from_url(article_url)

        if not article_text.strip():
            return jsonify({"ok": False, "error": "Please paste a news URL or article first."}), 400

        result = process_article_text(article_text, api_key)
        result["imported_article_text"] = article_text
        return jsonify({"ok": True, "data": result})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/process-image", methods=["POST"])
def api_process_image():
    api_key = (request.form.get("api_key") or os.getenv("TOGETHER_API_KEY", "")).strip()
    scene_text = (request.form.get("scene_text") or "").strip()
    max_kb = int(request.form.get("max_kb") or 100)
    brightness = float(request.form.get("brightness") or 1.0)
    sharpness = float(request.form.get("sharpness") or 1.0)
    blur_radius = float(request.form.get("blur_radius") or 0.0)

    file = request.files.get("image")
    if not file:
        return jsonify({"ok": False, "error": "Please import an image first."}), 400

    try:
        original_bytes = file.read()
        optimized = optimize_image_bytes(
            original_bytes,
            max_kb=max_kb,
            brightness=brightness,
            sharpness=sharpness,
            blur_radius=blur_radius,
        )

        image_b64 = base64.b64encode(optimized).decode("utf-8")
        ai = generate_image_seo_fields(api_key, scene_text, image_b64)

        return jsonify({
            "ok": True,
            "data": {
                "alt_text": ai["alt_text"],
                "image_title": ai["image_title"],
                "caption": ai["caption"],
                "optimized_base64": image_b64,
                "optimized_size_kb": round(len(optimized) / 1024, 1),
            }
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/download-image", methods=["POST"])
def api_download_image():
    data = request.get_json(silent=True) or {}
    image_b64 = data.get("image_base64") or ""
    if not image_b64:
        return jsonify({"ok": False, "error": "No image available."}), 400

    try:
        image_bytes = base64.b64decode(image_b64)
        return send_file(
            io.BytesIO(image_bytes),
            mimetype="image/jpeg",
            as_attachment=True,
            download_name="optimized-image.jpg",
        )
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
