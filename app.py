import base64
import html
import io
import os
import re
from difflib import SequenceMatcher

from flask import Flask, jsonify, render_template, request, send_file
from PIL import Image, ImageOps
from docx import Document
from docx.shared import Inches, Pt, RGBColor

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024


# =========================
# GENERAL HELPERS
# =========================
def normalize_newlines(text: str) -> str:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n")


def clean_lines(text: str):
    text = normalize_newlines(text)
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    raw = [line.strip() for line in text.split("\n")]

    out = []
    prev_blank = True
    for line in raw:
        if not line:
            if not prev_blank:
                out.append("")
            prev_blank = True
            continue
        out.append(line)
        prev_blank = False

    while out and out[-1] == "":
        out.pop()
    return out


def trim_at_word_boundary(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rstrip()
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,.-:;!?/")


def esc(text: str) -> str:
    return html.escape(text or "", quote=True)


def make_slug(title: str) -> str:
    slug = re.sub(r"[^a-z0-9\s-]", "", (title or "").lower())
    slug = re.sub(r"\s+", "-", slug).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug or "news-update"


def trim_words(text: str, max_words: int) -> str:
    words = [w for w in (text or "").split() if w]
    return " ".join(words[:max_words]).strip()


def get_paragraphs(lines):
    paragraphs = []
    current = []
    for line in lines:
        if line == "":
            if current:
                paragraphs.append(" ".join(current).strip())
                current = []
        else:
            current.append(line)
    if current:
        paragraphs.append(" ".join(current).strip())
    return [p for p in paragraphs if p]


# =========================
# ARTICLE / SEO LOGIC
# =========================
def strip_internal_seo_lines(lines):
    prefixes = (
        "Focus Keyphrase:",
        "SEO Title:",
        "Meta Description:",
        "Slug:",
        "Slug (URL):",
        "Short Summary:",
        "Alt Text:",
        "Img Title:",
        "Caption:",
    )
    out = []
    for line in lines:
        s = line.strip()
        if any(s.startswith(p) for p in prefixes):
            continue
        out.append(line)
    while out and out[-1] == "":
        out.pop()
    return out


def guess_title(lines):
    if not lines:
        return "Untitled Article"
    for line in lines:
        if line.strip():
            return trim_at_word_boundary(line.strip(), 140)
    return "Untitled Article"


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
    return trim_at_word_boundary(" ".join(intro_parts), 240)


def split_body_into_sections(lines, num_sections=3):
    paragraphs = get_paragraphs(lines[1:])
    if not paragraphs:
        body_lines = [x for x in lines[1:] if x.strip()]
        return body_lines[:num_sections]

    if len(paragraphs) <= num_sections:
        return paragraphs

    target = min(num_sections, len(paragraphs))
    base = len(paragraphs) // target
    extra = len(paragraphs) % target
    out = []
    i = 0
    for idx in range(target):
        take = base + (1 if idx < extra else 0)
        chunk = paragraphs[i:i + take]
        i += take
        out.append("\n\n".join(chunk).strip())
    return out


def clean_heading_candidate(text: str) -> str:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    text = text.strip(' "\'“”‘’.,:;!?-')
    text = re.sub(r"^[^A-Za-z0-9]+", "", text)
    text = re.sub(r"[^A-Za-z0-9]+$", "", text)
    return text


def sentence_candidates_from_text(text: str):
    text = (text or "").replace("\n", " ")
    sentences = re.split(r"(?<=[.!?])\s+", text)
    out = []
    for s in sentences:
        s = clean_heading_candidate(s)
        wc = len(s.split())
        if 4 <= wc <= 12:
            out.append(s)
    return out


def phrase_candidates_from_text(text: str):
    words = [w for w in clean_heading_candidate(text).split() if w]
    out = []
    for ln in (5, 6, 7, 8):
        if len(words) >= ln:
            out.append(" ".join(words[:ln]))
    return out


def choose_heading_from_text(text: str, seen):
    candidates = sentence_candidates_from_text(text)
    if not candidates:
        candidates = phrase_candidates_from_text(text)

    weak = {"the", "a", "an", "this", "that", "these", "those", "it", "they", "we", "here", "there"}
    ranked = []

    for cand in candidates:
        c = clean_heading_candidate(cand)
        if not c:
            continue
        key = c.lower()
        words = c.split()
        if len(words) < 4:
            continue

        score = 0
        if 5 <= len(words) <= 10:
            score += 4
        elif len(words) <= 12:
            score += 2
        if words[0].lower() not in weak:
            score += 2
        if not c.endswith((":", ",", "-")):
            score += 1
        if any(w[:1].isupper() for w in words if w):
            score += 1

        ranked.append((score, c, key))

    ranked.sort(key=lambda x: (-x[0], abs(len(x[1]) - 52), len(x[1])))

    for _, cand, key in ranked:
        if key in seen:
            continue
        too_similar = any(SequenceMatcher(None, key, prev).ratio() >= 0.72 for prev in seen)
        if too_similar:
            continue
        seen.add(key)
        return cand

    return ""


def build_nested_article_structure(sections):
    structure = []
    seen = set()
    for idx, section in enumerate([s.strip() for s in sections if s.strip()][:3], start=1):
        parts = [p.strip() for p in section.split("\n\n") if p.strip()]
        if not parts:
            continue

        h2 = ""
        for source in parts[:2] + [section]:
            h2 = choose_heading_from_text(source, seen)
            if h2:
                break

        if not h2:
            fallback = clean_heading_candidate(parts[0])
            h2 = " ".join(fallback.split()[:8]).strip() or f"Section {idx}"

        subsections = []
        if len(parts) >= 3:
            lead = parts[0]
            mid = "\n\n".join(parts[1:-1]).strip() if len(parts) > 3 else parts[1]
            end = parts[-1]
            subsections.append({"h3": "", "h4": "", "body": lead})
            if mid and mid != lead and mid != end:
                subsections.append({"h3": "", "h4": "", "body": mid})
            if end and end != lead:
                subsections.append({"h3": "", "h4": "", "body": end})
        else:
            subsections.append({"h3": "", "h4": "", "body": "\n\n".join(parts).strip()})

        structure.append({"h2": h2, "subsections": subsections})

    return structure[:3]


def make_focus_keyphrase(title: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", title or "").strip()
    return " ".join(cleaned.split()[:10]).strip()


def make_seo_title_options(title: str):
    base = re.sub(r"\s+", " ", title or "").strip()
    opts = [
        trim_at_word_boundary(base, 70),
        trim_at_word_boundary(f"{base} | Full Report", 70),
        trim_at_word_boundary(f"{base} | Key Updates", 70),
        trim_at_word_boundary(f"{base} | News Analysis", 70),
    ]
    out, seen = [], set()
    for item in opts:
        key = item.lower()
        if item and key not in seen:
            out.append(item)
            seen.add(key)
    return out[:4]


def make_meta_options(intro: str, title: str):
    source = re.sub(r"\s+", " ", intro or title or "").strip()
    opts = [
        trim_at_word_boundary(source, 160),
        trim_at_word_boundary(f"{title} — {source}", 160),
        trim_at_word_boundary(f"Read the latest details: {source}", 160),
    ]
    out, seen = [], set()
    for item in opts:
        key = item.lower()
        if item and key not in seen:
            out.append(item)
            seen.add(key)
    return out[:3]


def build_plain_text(h1, intro, structure):
    parts = []
    if h1:
        parts.extend([h1, ""])
    if intro:
        parts.extend([intro, ""])

    for sec in structure:
        if sec.get("h2"):
            parts.extend([sec["h2"], ""])
        for sub in sec.get("subsections", []):
            if sub.get("h3"):
                parts.append(sub["h3"])
            if sub.get("h4"):
                parts.append(sub["h4"])
            if sub.get("body"):
                parts.extend([sub["body"], ""])
    return "\n".join(parts).strip()


def build_wordpress_html_fragment(h1, intro, structure, image_data_uri="", alt_text="", img_title="", caption=""):
    parts = []

    if image_data_uri:
        img_html = (
            f'<figure class="wp-block-image size-full featured-image-wrap">'
            f'<img src="{image_data_uri}" alt="{esc(alt_text or h1 or "Featured image")}" '
            f'title="{esc(img_title or h1 or "Featured image")}" />'
        )
        if caption:
            img_html += f"<figcaption>{esc(caption)}</figcaption>"
        img_html += "</figure>"
        parts.append(img_html)

    if h1:
        parts.append(f"<h1>{esc(h1)}</h1>")
    if intro:
        parts.append(f"<p>{esc(intro)}</p>")

    for sec in structure:
        if sec.get("h2"):
            parts.append(f"<h2>{esc(sec['h2'])}</h2>")
        for sub in sec.get("subsections", []):
            if sub.get("h3"):
                parts.append(f"<h3>{esc(sub['h3'])}</h3>")
            if sub.get("h4"):
                parts.append(f"<h4>{esc(sub['h4'])}</h4>")
            for p in [x.strip() for x in sub.get("body", "").split("\n\n") if x.strip()]:
                parts.append(f"<p>{esc(p).replace(chr(10), '<br>')}</p>")

    return "\n".join(parts).strip()


def build_html_document(h1, wp_html):
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(h1 or "SEO Output")}</title>
<style>
:root {{
    --bg: #f4f7fb;
    --card: #ffffff;
    --text: #1f2937;
    --muted: #4b5563;
    --border: #dbe4f0;
}}
* {{ box-sizing: border-box; }}
body {{
    margin: 0;
    font-family: "Segoe UI", Arial, sans-serif;
    background: linear-gradient(180deg, #eef4ff 0%, #f8fbff 100%);
    color: var(--text);
    line-height: 1.8;
    font-size: 18px;
    padding: 28px 18px 48px;
}}
.article-shell {{
    max-width: 940px;
    margin: 0 auto;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 22px;
    box-shadow: 0 18px 50px rgba(15, 23, 42, 0.08);
    padding: 28px 28px 34px;
}}
h1 {{ font-size: 44px; line-height: 1.15; margin: 0 0 18px; color: #162033; }}
h2 {{ font-size: 31px; margin: 28px 0 14px; color: #22304a; }}
h3 {{ font-size: 23px; margin: 20px 0 10px; color: #22304a; }}
p {{ font-size: 18px; color: #243041; margin: 0 0 16px; }}
img {{ max-width: 100%; height: auto; border-radius: 16px; }}
figcaption {{ color: #6b7280; font-size: 14px; margin-top: 8px; }}
@media (max-width: 720px) {{
  .article-shell {{ padding: 18px 16px 24px; border-radius: 18px; }}
  h1 {{ font-size: 34px; }}
  h2 {{ font-size: 27px; }}
  h3 {{ font-size: 21px; }}
  body, p {{ font-size: 17px; }}
}}
</style>
</head>
<body>
<div class="article-shell">
{wp_html}
</div>
</body>
</html>"""


# =========================
# IMAGE / YOAST LOGIC
# =========================
def sentence_case(text):
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if not text:
        return ""
    return text[0].upper() + text[1:]


def normalize_phrase(text, title_case=False):
    text = re.sub(r"[_-]+", " ", (text or ""))
    text = re.sub(r"\s+", " ", text).strip(" .:;|-_")
    if not text:
        return ""
    low = text.lower()
    low = re.sub(r"\b(?:untitled|design|image|photo|copy|edited|edit|thumb|thumbnail|final|new|jpeg|jpg|png|webp)\b", " ", low)
    low = re.sub(r"\b\d{2,}\b", " ", low)
    low = re.sub(r"\s+", " ", low).strip()
    if not low:
        low = text.strip()
    if title_case:
        small = {"and", "or", "with", "at", "in", "on", "for", "to", "of", "the", "a", "an"}
        words = []
        for i, word in enumerate(low.split()):
            words.append(word if i > 0 and word in small else word.capitalize())
        return " ".join(words)
    return low


def trim_chars(text, max_chars):
    return trim_at_word_boundary(text, max_chars)


def infer_subject_from_article(h1, focus_keyphrase):
    title = h1 or focus_keyphrase or "News image"
    return trim_words(normalize_phrase(title, title_case=False), 8)


def infer_action_from_article(h1, intro):
    combined = f"{h1} {intro}".lower()
    actions = [
        "breaking news", "press event", "announcement", "meeting", "report",
        "launch", "discussion", "conference", "interview"
    ]
    for action in actions:
        if action in combined:
            return action
    return "news update"


def infer_context_from_article(intro, h1, scene_notes=""):
    context = (scene_notes or "").strip()
    if context:
        return trim_words(normalize_phrase(context, title_case=False), 8)

    source = intro or h1 or "news image"
    source = re.sub(r"[^\w\s-]", " ", source)
    source = re.sub(r"\s+", " ", source).strip()
    return trim_words(source, 8).lower()


def build_image_alt_text(subject, action, context):
    parts = [subject]
    if action and action.lower() not in subject.lower():
        parts.append(action)
    if context and context.lower() not in " ".join(parts).lower():
        parts.append(context)
    alt_text = sentence_case(" ".join([p for p in parts if p]))
    alt_text = trim_words(alt_text, 16)
    return trim_chars(alt_text, 125)


def build_image_title(subject, context):
    title = subject or context or "Featured image"
    if context and context.lower() not in title.lower() and len(title.split()) < 4:
        title = f"{title} {context}"
    title = normalize_phrase(title, title_case=True)
    title = trim_words(title, 8)
    return trim_chars(title, 70)


def build_image_caption(subject, action, context):
    parts = [subject]
    if action and action.lower() not in subject.lower():
        parts.append(action)
    elif context and context.lower() not in subject.lower():
        parts.append(context)
    if context and context.lower() not in " ".join(parts).lower():
        parts.append(context)

    caption = sentence_case(" ".join([p for p in parts if p]))
    caption = trim_words(caption, 24)
    caption = trim_chars(caption, 160)
    if caption and not caption.endswith("."):
        caption += "."
    return caption


def image_bytes_to_data_uri(data: bytes, mime="image/jpeg") -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode('utf-8')}"


def pil_to_jpeg_bytes(image: Image.Image, quality=92) -> bytes:
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def export_image_under_target_bytes(image: Image.Image, target_kb=100) -> bytes:
    target_bytes = int(target_kb * 1024)
    candidate = image.copy().convert("RGB")
    scales = [1.0, 0.96, 0.92, 0.88, 0.84, 0.80, 0.76, 0.72, 0.68, 0.64]
    qualities = [95, 92, 89, 86, 83, 80, 77, 74, 71, 68, 65, 62, 58, 54, 50, 46, 42, 38]
    best = b""

    for scale in scales:
        trial = candidate
        if scale < 1.0:
            new_w = max(1, int(candidate.width * scale))
            new_h = max(1, int(candidate.height * scale))
            trial = candidate.resize((new_w, new_h), Image.LANCZOS)

        for quality in qualities:
            buf = io.BytesIO()
            trial.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
            data = buf.getvalue()
            best = data
            if len(data) <= target_bytes:
                return data

    return best


# =========================
# ROUTES
# =========================
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/process", methods=["POST"])
def api_process():
    data = request.get_json(force=True)
    raw = (data.get("article") or "").strip()
    if not raw:
        return jsonify({"ok": False, "error": "Please paste an article first."}), 400

    lines = strip_internal_seo_lines(clean_lines(raw))
    if not [x for x in lines if x.strip()]:
        return jsonify({"ok": False, "error": "No valid content found."}), 400

    h1 = guess_title(lines)
    intro = build_intro(lines)
    sections = split_body_into_sections(lines, 3)
    structure = build_nested_article_structure(sections)

    focus_keyphrase = make_focus_keyphrase(h1)
    seo_titles = make_seo_title_options(h1)
    meta_options = make_meta_options(intro, h1)
    seo_title = seo_titles[0] if seo_titles else h1
    meta_description = meta_options[0] if meta_options else trim_at_word_boundary(intro or h1, 160)
    slug = make_slug(h1)
    short_summary = trim_at_word_boundary(re.sub(r"\s+", " ", intro or h1).strip(), 200)
    plain_text = build_plain_text(h1, intro, structure)
    wp_html = build_wordpress_html_fragment(h1, intro, structure)

    headings_summary = []
    body_blocks = []
    for sec in structure[:3]:
        if sec["h2"]:
            headings_summary.append(sec["h2"])
            body_blocks.append(sec["h2"])
        sub_bodies = []
        for sub in sec["subsections"]:
            if sub["h3"]:
                headings_summary.append("  - " + sub["h3"])
            if sub["h4"]:
                headings_summary.append("    * " + sub["h4"])
            if sub["body"].strip():
                sub_bodies.append(sub["body"].strip())
        if sub_bodies:
            body_blocks.append("\n\n".join(sub_bodies))

    return jsonify({
        "ok": True,
        "plain_text": plain_text,
        "structure": structure,
        "wp_html": wp_html,

        "h1_copy": h1,
        "intro_copy": intro,
        "headings_copy": "\n".join(headings_summary),
        "structure_copy": structure,
        "body_copy": "\n\n".join(body_blocks),

        "focus_keyphrase_copy": focus_keyphrase,
        "seo_title_copy": seo_title,
        "meta_description_copy": meta_description,
        "slug_copy": slug,
        "short_summary_copy": short_summary,

        "focus_keyphrase_value": focus_keyphrase,
        "seo_title_value": seo_title,
        "meta_description_value": meta_description,
        "slug_value": slug,
        "short_summary_value": short_summary,

        "seo_title_options": seo_titles,
        "meta_options": meta_options
    })


@app.route("/api/image-seo", methods=["POST"])
def api_image_seo():
    data = request.get_json(force=True)
    h1 = data.get("h1", "")
    intro = data.get("intro", "")
    focus_keyphrase = data.get("focus_keyphrase", "")
    scene_notes = data.get("scene_notes", "")

    subject = infer_subject_from_article(h1, focus_keyphrase)
    action = infer_action_from_article(h1, intro)
    context = infer_context_from_article(intro, h1, scene_notes)

    alt_text = build_image_alt_text(subject, action, context)
    img_title = build_image_title(subject, context)
    caption = build_image_caption(subject, action, context)

    return jsonify({
        "ok": True,
        "alt_text": alt_text,
        "img_title": img_title,
        "caption": caption
    })


@app.route("/api/crop-image", methods=["POST"])
def api_crop_image():
    if "image" not in request.files:
        return jsonify({"ok": False, "error": "No image uploaded."}), 400

    file = request.files["image"]
    if not file.filename:
        return jsonify({"ok": False, "error": "No image selected."}), 400

    try:
        x = int(float(request.form.get("x", 0)))
        y = int(float(request.form.get("y", 0)))
        width = int(float(request.form.get("width", 0)))
        height = int(float(request.form.get("height", 0)))
        target_w = int(request.form.get("target_width", 0) or 0)
        target_h = int(request.form.get("target_height", 0) or 0)
        export_under_100kb = request.form.get("export_under_100kb", "false").lower() == "true"

        image = Image.open(file.stream)
        image = ImageOps.exif_transpose(image).convert("RGB")

        x = max(0, min(x, image.width - 1))
        y = max(0, min(y, image.height - 1))
        width = max(1, min(width, image.width - x))
        height = max(1, min(height, image.height - y))

        cropped = image.crop((x, y, x + width, y + height))
        if target_w > 0 and target_h > 0:
            cropped = cropped.resize((target_w, target_h), Image.LANCZOS)

        if export_under_100kb:
            out_bytes = export_image_under_target_bytes(cropped, 100)
            return jsonify({
                "ok": True,
                "image_data_uri": image_bytes_to_data_uri(out_bytes, "image/jpeg"),
                "width": cropped.width,
                "height": cropped.height,
                "size_kb": round(len(out_bytes) / 1024, 1)
            })

        out_bytes = pil_to_jpeg_bytes(cropped, 92)
        return jsonify({
            "ok": True,
            "image_data_uri": image_bytes_to_data_uri(out_bytes, "image/jpeg"),
            "width": cropped.width,
            "height": cropped.height,
            "size_kb": round(len(out_bytes) / 1024, 1)
        })

    except Exception as exc:
        return jsonify({"ok": False, "error": f"Image processing failed: {exc}"}), 400


@app.route("/api/export-txt", methods=["POST"])
def api_export_txt():
    data = request.get_json(force=True)
    text = data.get("text", "")
    return send_file(
        io.BytesIO(text.encode("utf-8")),
        mimetype="text/plain",
        as_attachment=True,
        download_name="seo-output.txt"
    )


@app.route("/api/export-html", methods=["POST"])
def api_export_html():
    data = request.get_json(force=True)
    h1 = data.get("h1", "")
    wp_html = data.get("wp_html", "")
    html_doc = build_html_document(h1, wp_html)
    return send_file(
        io.BytesIO(html_doc.encode("utf-8")),
        mimetype="text/html",
        as_attachment=True,
        download_name="seo-output.html"
    )


@app.route("/api/export-docx", methods=["POST"])
def api_export_docx():
    data = request.get_json(force=True)

    h1 = data.get("h1", "")
    intro = data.get("intro", "")
    structure = data.get("structure", [])
    image_data_uri = data.get("image_data_uri", "")
    caption = data.get("caption", "")

    doc = Document()
    sec = doc.sections[0]
    sec.top_margin = Inches(0.5)
    sec.bottom_margin = Inches(0.5)
    sec.left_margin = Inches(0.6)
    sec.right_margin = Inches(0.6)

    if image_data_uri.startswith("data:image/"):
        header, encoded = image_data_uri.split(",", 1)
        img_bytes = base64.b64decode(encoded)
        img_stream = io.BytesIO(img_bytes)
        doc.add_picture(img_stream, width=Inches(6.8))
        if caption:
            cap = doc.add_paragraph()
            cap.paragraph_format.space_before = Pt(4)
            cap.paragraph_format.space_after = Pt(10)
            run = cap.add_run(caption)
            run.font.name = "Segoe UI"
            run.font.size = Pt(10)
            run.font.color.rgb = RGBColor(100, 100, 100)

    if h1:
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(8)
        r = p.add_run(h1)
        r.bold = True
        r.font.name = "Segoe UI"
        r.font.size = Pt(22)

    if intro:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(8)
        r = p.add_run(intro)
        r.font.name = "Segoe UI"
        r.font.size = Pt(12)

    for sec_item in structure:
        h2 = sec_item.get("h2", "")
        if h2:
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(10)
            p.paragraph_format.space_after = Pt(4)
            r = p.add_run(h2)
            r.bold = True
            r.font.name = "Segoe UI"
            r.font.size = Pt(16)

        for sub in sec_item.get("subsections", []):
            if sub.get("h3"):
                p = doc.add_paragraph()
                p.paragraph_format.space_before = Pt(8)
                p.paragraph_format.space_after = Pt(3)
                r = p.add_run(sub["h3"])
                r.bold = True
                r.font.name = "Segoe UI"
                r.font.size = Pt(13)

            if sub.get("h4"):
                p = doc.add_paragraph()
                p.paragraph_format.space_before = Pt(6)
                p.paragraph_format.space_after = Pt(3)
                r = p.add_run(sub["h4"])
                r.bold = True
                r.font.name = "Segoe UI"
                r.font.size = Pt(12)

            for para in [x.strip() for x in (sub.get("body", "")).split("\n\n") if x.strip()]:
                p = doc.add_paragraph()
                p.paragraph_format.space_after = Pt(6)
                r = p.add_run(para)
                r.font.name = "Segoe UI"
                r.font.size = Pt(12)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name="seo-output.docx"
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
