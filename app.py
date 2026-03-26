from flask import Flask, render_template, request, jsonify, send_file
from io import BytesIO
import re
import base64

from PIL import Image, ImageEnhance, ImageOps, ImageFilter

try:
    from docx import Document
    DOCX_AVAILABLE = True
except Exception:
    DOCX_AVAILABLE = False

app = Flask(__name__)

STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "than", "for", "with",
    "without", "to", "from", "of", "in", "on", "at", "by", "is", "are", "was",
    "were", "be", "been", "being", "that", "this", "these", "those", "it",
    "its", "as", "about", "into", "over", "after", "before", "through", "under",
    "between", "during", "including", "until", "against", "among", "within",
    "news", "update", "latest"
}

SUPPORTED_IMAGE_FORMATS = {"png", "jpg", "jpeg", "webp"}


def clean_text(text):
    text = text.strip()
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text


def split_paragraphs(text):
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    return paragraphs if paragraphs else [text]


def split_sentences(text):
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in sentences if s.strip()]


def smart_truncate(text, limit, add_ellipsis=False):
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text

    words = text.split()
    result_words = []
    current_length = 0

    for word in words:
        extra = len(word) if not result_words else len(word) + 1
        reserved = 3 if add_ellipsis else 0

        if current_length + extra + reserved <= limit:
            result_words.append(word)
            current_length += extra
        else:
            break

    if not result_words:
        fallback = text[: max(0, limit - (3 if add_ellipsis else 0))].rstrip()
        return fallback + "..." if add_ellipsis and fallback else fallback

    result = " ".join(result_words).strip()
    if add_ellipsis and len(result) < len(text):
        return result + "..."
    return result


def title_case_phrase(text):
    words = text.split()
    small_words = {
        "and", "or", "but", "for", "nor", "a", "an", "the", "as", "at", "by",
        "from", "in", "into", "of", "on", "onto", "to", "with"
    }
    out = []
    for i, word in enumerate(words):
        lower = word.lower()
        if i != 0 and i != len(words) - 1 and lower in small_words:
            out.append(lower)
        else:
            out.append(lower.capitalize())
    return " ".join(out)


def extract_keywords(text, limit=8):
    words = re.findall(r"[A-Za-z0-9']+", text.lower())
    freq = {}

    for word in words:
        if len(word) < 3 or word in STOP_WORDS:
            continue
        freq[word] = freq.get(word, 0) + 1

    ranked = sorted(freq.items(), key=lambda x: (-x[1], x[0]))
    return [word for word, _ in ranked[:limit]]


def find_best_sentence(sentences, keywords):
    if not sentences:
        return ""

    best_sentence = sentences[0]
    best_score = -1

    for sentence in sentences:
        lower = sentence.lower()
        score = 0

        for kw in keywords:
            if kw in lower:
                score += 3

        length = len(sentence)
        if 70 <= length <= 170:
            score += 3
        elif 40 <= length <= 220:
            score += 1

        if "," in sentence:
            score += 1

        if score > best_score:
            best_score = score
            best_sentence = sentence

    return best_sentence


def extract_title(paragraphs):
    if not paragraphs:
        return "SEO Article"

    first = re.sub(r"\s+", " ", paragraphs[0]).strip()
    sentences = split_sentences(first)
    candidate = sentences[0] if sentences else first
    candidate = re.sub(r"^[\"'“”‘’\-–—:;\s]+", "", candidate).strip()
    candidate = smart_truncate(candidate, 72, add_ellipsis=False)
    return candidate if candidate else "SEO Article"


def create_focus_keyphrase(title, article):
    keywords = extract_keywords(title + " " + article, limit=5)
    if keywords:
        return title_case_phrase(" ".join(keywords[:3]))
    return title_case_phrase(smart_truncate(title, 50, add_ellipsis=False))


def create_slug(title, focus_keyphrase=""):
    base = focus_keyphrase if focus_keyphrase else title
    slug = base.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug[:80]


def create_intro(text):
    sentences = split_sentences(text)
    if not sentences:
        return smart_truncate(text, 260, add_ellipsis=True)

    intro = " ".join(sentences[:2])
    return smart_truncate(intro, 260, add_ellipsis=True)


def create_seo_title_options(title, focus_keyphrase):
    title = re.sub(r"\s+", " ", title).strip()
    focus_keyphrase = re.sub(r"\s+", " ", focus_keyphrase).strip()

    candidates = [
        title,
        f"{title} | Key Details",
        f"{title} | Full Breakdown",
        f"{focus_keyphrase}: {title}",
        f"{title} - Latest Update",
        f"{focus_keyphrase} - Key Details",
        f"{title} | What Happened",
    ]

    results = []
    seen = set()

    for candidate in candidates:
        clean = smart_truncate(candidate, 60, add_ellipsis=False)
        if clean.lower() not in seen:
            seen.add(clean.lower())
            results.append(clean)

    return results[:3]


def create_meta_description_options(text, focus_keyphrase):
    cleaned = re.sub(r"\s+", " ", text).strip()
    sentences = split_sentences(cleaned)
    keywords = extract_keywords(cleaned, limit=6)

    best = find_best_sentence(sentences, keywords) or cleaned
    alt_1 = smart_truncate(best, 160, add_ellipsis=True)

    if focus_keyphrase and focus_keyphrase.lower() not in alt_1.lower():
        combo = f"{focus_keyphrase}: {best}"
        alt_2 = smart_truncate(combo, 160, add_ellipsis=True)
    else:
        alt_2 = alt_1

    first_two = " ".join(sentences[:2]) if sentences else cleaned
    alt_3 = smart_truncate(first_two, 160, add_ellipsis=True)

    options = []
    seen = set()
    for item in [alt_1, alt_2, alt_3]:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            options.append(item)

    while len(options) < 3:
        options.append(options[-1] if options else "")

    return options[:3]


def create_h2_sections(paragraphs, focus_keyphrase):
    candidates = []
    keywords = extract_keywords(" ".join(paragraphs), limit=8)

    for p in paragraphs[1:8]:
        sentence_list = split_sentences(p)
        candidate = sentence_list[0] if sentence_list else p
        candidate = re.sub(r"\s+", " ", candidate).strip()
        candidate = smart_truncate(candidate, 58, add_ellipsis=False)

        if not candidate:
            continue

        score = 0
        lower = candidate.lower()

        for kw in keywords:
            if kw in lower:
                score += 2

        if focus_keyphrase.lower() in lower:
            score += 2

        if 20 <= len(candidate) <= 58:
            score += 2

        candidates.append((score, title_case_phrase(candidate)))

    candidates = sorted(candidates, key=lambda x: -x[0])
    unique = []
    seen = set()

    for _, cand in candidates:
        key = cand.lower()
        if key not in seen:
            seen.add(key)
            unique.append(cand)
        if len(unique) == 4:
            break

    if not unique:
        unique = [
            f"{focus_keyphrase} Overview",
            "Key Details and Background",
            "Main Developments",
            "What Happens Next"
        ]

    return [f"H2 {i + 1}: {h2}" for i, h2 in enumerate(unique)]


def format_body(paragraphs):
    formatted = []
    for p in paragraphs:
        words = p.split()
        lines = []
        for i in range(0, len(words), 18):
            lines.append(" ".join(words[i:i + 18]))
        formatted.append("\n".join(lines))
    return "\n\n".join(formatted)


def bullet_points_summary(paragraphs):
    bullets = []
    for p in paragraphs[:4]:
        sentence_list = split_sentences(p)
        cleaned = sentence_list[0] if sentence_list else p
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned:
            bullets.append(f"- {smart_truncate(cleaned, 140, add_ellipsis=True)}")

    if not bullets:
        bullets.append("- No summary available.")

    return "\n".join(bullets)


def generate_video_script(title, intro, body):
    body_summary = smart_truncate(re.sub(r"\s+", " ", body), 200, add_ellipsis=True)
    return (
        f"Here’s the latest on {title}. "
        f"{smart_truncate(intro, 110, add_ellipsis=True)} "
        f"{body_summary} "
        f"Follow for more updates."
    )


def generate_caption(title):
    return f"{title} — quick breakdown, key details, and short video summary."


def generate_hashtags(title):
    words = re.findall(r"[A-Za-z0-9]+", title)
    tags = ["#SEO", "#News", "#Content", "#Trending", "#Update"]

    for word in words[:5]:
        if len(word) > 2:
            tags.append(f"#{word}")

    return " ".join(tags[:10])


def get_counters(meta_description, seo_title):
    return {
        "meta_length": len(meta_description),
        "seo_title_length": len(seo_title)
    }


def get_seo_score(seo_title, meta_description, focus_keyphrase):
    score = 0
    notes = []

    if 45 <= len(seo_title) <= 60:
        score += 35
        notes.append("SEO title length is strong.")
    else:
        notes.append("SEO title length should be closer to 45-60 characters.")

    if 120 <= len(meta_description) <= 160:
        score += 35
        notes.append("Meta description length is strong.")
    else:
        notes.append("Meta description should be closer to 120-160 characters.")

    if focus_keyphrase and focus_keyphrase.lower() in seo_title.lower():
        score += 15
        notes.append("Focus keyphrase appears in SEO title.")
    else:
        notes.append("Add the focus keyphrase to SEO title.")

    if focus_keyphrase and focus_keyphrase.lower() in meta_description.lower():
        score += 15
        notes.append("Focus keyphrase appears in meta description.")
    else:
        notes.append("Add the focus keyphrase to meta description.")

    return {"score": score, "notes": notes}


def format_seo_article(article):
    article = clean_text(article)
    paragraphs = split_paragraphs(article)

    title = extract_title(paragraphs)
    focus_keyphrase = create_focus_keyphrase(title, article)
    seo_title_options = create_seo_title_options(title, focus_keyphrase)
    meta_description_options = create_meta_description_options(article, focus_keyphrase)

    seo_title = seo_title_options[0]
    meta_description = meta_description_options[0]

    intro = create_intro(article)
    h2_list = create_h2_sections(paragraphs, focus_keyphrase)
    body = format_body(paragraphs)
    slug = create_slug(title, focus_keyphrase)
    image_alt = f"Main image related to {title}"
    image_title = title
    short_summary = bullet_points_summary(paragraphs)
    internal_link = "Read more about [Topic]..."
    conclusion = (
        "This article ends with the final reported developments and raises discussion "
        "about what may happen next.\nWhat do you think about this situation?"
    )
    video_script = generate_video_script(title, intro, body)
    caption = generate_caption(title)
    hashtags = generate_hashtags(title)
    counters = get_counters(meta_description, seo_title)
    seo_score = get_seo_score(seo_title, meta_description, focus_keyphrase)

    return {
        "H1 Tag": f"{title} 2026",
        "Introduction": intro,
        "H2 Tags": "\n".join(h2_list),
        "Main Content Body": body,
        "Internal Link Placeholder": internal_link,
        "Conclusion & CTA": conclusion,
        "Focus Keyphrase": focus_keyphrase,
        "SEO Title": seo_title,
        "SEO Title Options": seo_title_options,
        "Meta Description": meta_description,
        "Meta Description Options": meta_description_options,
        "Image Alt Text": image_alt,
        "Image Title": image_title,
        "Slug (URL)": slug,
        "Short Summary (20-second video)": short_summary,
        "Video Script": video_script,
        "Caption": caption,
        "Hashtags": hashtags,
        "Counters": counters,
        "SEO Score": seo_score
    }


def build_export_text(data):
    seo_score = data.get("SEO Score", {})
    notes = "\n".join(f"- {note}" for note in seo_score.get("notes", []))
    seo_title_options = "\n".join(f"- {item}" for item in data.get("SEO Title Options", []))
    meta_options = "\n".join(f"- {item}" for item in data.get("Meta Description Options", []))

    return f"""
==================== H1 TAG ====================
{data.get("H1 Tag", "")}

==================== INTRODUCTION ====================
{data.get("Introduction", "")}

==================== H2 TAGS ====================
{data.get("H2 Tags", "")}

==================== MAIN CONTENT BODY ====================
{data.get("Main Content Body", "")}

==================== INTERNAL LINK PLACEHOLDER ====================
{data.get("Internal Link Placeholder", "")}

==================== CONCLUSION & CTA ====================
{data.get("Conclusion & CTA", "")}

==================== SEO TECHNICAL DETAILS ====================

Focus Keyphrase:
{data.get("Focus Keyphrase", "")}

SEO Title:
{data.get("SEO Title", "")}

SEO Title Options:
{seo_title_options}

Meta Description:
{data.get("Meta Description", "")}

Meta Description Options:
{meta_options}

Image Alt Text:
{data.get("Image Alt Text", "")}

Image Title:
{data.get("Image Title", "")}

Slug (URL):
{data.get("Slug (URL)", "")}

Short Summary (20-second video):
{data.get("Short Summary (20-second video)", "")}

==================== VIDEO SECTION ====================

Video Script:
{data.get("Video Script", "")}

Caption:
{data.get("Caption", "")}

Hashtags:
{data.get("Hashtags", "")}

==================== SEO SCORE ====================

Score:
{seo_score.get("score", 0)}

Notes:
{notes}
""".strip()


def decode_base64_image(data_url: str) -> Image.Image:
    if "," not in data_url:
        raise ValueError("Invalid image data.")
    _, encoded = data_url.split(",", 1)
    raw = base64.b64decode(encoded)
    return Image.open(BytesIO(raw))


def encode_image_to_base64(image: Image.Image, fmt: str = "PNG") -> str:
    buffer = BytesIO()
    fmt_upper = fmt.upper()
    save_kwargs = {}

    if fmt_upper == "JPEG":
        save_kwargs["quality"] = 97
        save_kwargs["optimize"] = True
        save_kwargs["subsampling"] = 0
    elif fmt_upper == "WEBP":
        save_kwargs["quality"] = 98
        save_kwargs["method"] = 6
    elif fmt_upper == "PNG":
        save_kwargs["compress_level"] = 1

    image.save(buffer, format=fmt_upper, **save_kwargs)
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")

    if fmt_upper == "PNG":
        mime = "image/png"
    elif fmt_upper == "JPEG":
        mime = "image/jpeg"
    else:
        mime = "image/webp"

    return f"data:{mime};base64,{encoded}"


def upscale_smooth_image(image: Image.Image, scale: int, clean_mode: str = "balanced") -> Image.Image:
    image = ImageOps.exif_transpose(image)

    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA") if "A" in image.getbands() else image.convert("RGB")

    target_size = (image.width * scale, image.height * scale)
    current = image

    while current.width < target_size[0] or current.height < target_size[1]:
        next_w = min(target_size[0], int(current.width * 1.5))
        next_h = min(target_size[1], int(current.height * 1.5))
        current = current.resize((next_w, next_h), Image.Resampling.LANCZOS)
        current = current.filter(ImageFilter.UnsharpMask(radius=1.5, percent=140, threshold=2))

    if current.size != target_size:
        current = current.resize(target_size, Image.Resampling.LANCZOS)

    if clean_mode == "soft":
        current = current.filter(ImageFilter.SMOOTH)
        current = current.filter(ImageFilter.UnsharpMask(radius=1.2, percent=120, threshold=2))
        current = ImageEnhance.Contrast(current).enhance(1.04)
        current = ImageEnhance.Sharpness(current).enhance(1.08)

    elif clean_mode == "balanced":
        current = current.filter(ImageFilter.UnsharpMask(radius=1.8, percent=160, threshold=2))
        current = ImageEnhance.Contrast(current).enhance(1.08)
        current = ImageEnhance.Sharpness(current).enhance(1.18)

    elif clean_mode == "cleanest":
        current = current.filter(ImageFilter.MedianFilter(size=3))
        current = current.filter(ImageFilter.UnsharpMask(radius=2.0, percent=190, threshold=2))
        current = ImageEnhance.Contrast(current).enhance(1.12)
        current = ImageEnhance.Sharpness(current).enhance(1.25)
        current = ImageEnhance.Color(current).enhance(1.03)

    return current


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/format", methods=["POST"])
def format_article():
    try:
        data = request.get_json(silent=True) or {}
        article = (data.get("article") or "").strip()

        if not article:
            return jsonify({"error": "Please paste article content first."}), 400

        result = format_seo_article(article)
        return jsonify(result)
    except Exception as e:
        app.logger.exception("Format error")
        return jsonify({"error": f"Server error: {str(e)}"}), 500


@app.route("/export/txt", methods=["POST"])
def export_txt():
    try:
        data = request.get_json(silent=True) or {}
        content = build_export_text(data)
        buffer = BytesIO()
        buffer.write(content.encode("utf-8"))
        buffer.seek(0)

        return send_file(
            buffer,
            as_attachment=True,
            download_name="seo_output.txt",
            mimetype="text/plain"
        )
    except Exception as e:
        app.logger.exception("TXT export error")
        return jsonify({"error": f"TXT export failed: {str(e)}"}), 500


@app.route("/export/docx", methods=["POST"])
def export_docx():
    try:
        if not DOCX_AVAILABLE:
            return jsonify({"error": "DOCX export is not available. python-docx is missing."}), 500

        data = request.get_json(silent=True) or {}
        doc = Document()
        doc.add_heading("SEO Content Formatter Export", level=1)

        sections = [
            "H1 Tag",
            "Introduction",
            "H2 Tags",
            "Main Content Body",
            "Internal Link Placeholder",
            "Conclusion & CTA",
            "Focus Keyphrase",
            "SEO Title",
            "Meta Description",
            "Image Alt Text",
            "Image Title",
            "Slug (URL)",
            "Short Summary (20-second video)",
            "Video Script",
            "Caption",
            "Hashtags"
        ]

        for section in sections:
            doc.add_heading(section, level=2)
            doc.add_paragraph(str(data.get(section, "")))

        doc.add_heading("SEO Title Options", level=2)
        for item in data.get("SEO Title Options", []):
            doc.add_paragraph(item, style="List Bullet")

        doc.add_heading("Meta Description Options", level=2)
        for item in data.get("Meta Description Options", []):
            doc.add_paragraph(item, style="List Bullet")

        score = data.get("SEO Score", {})
        doc.add_heading("SEO Score", level=2)
        doc.add_paragraph(f"Score: {score.get('score', 0)}")

        for note in score.get("notes", []):
            doc.add_paragraph(note, style="List Bullet")

        buffer = BytesIO()
        doc.save(buffer)
        buffer.seek(0)

        return send_file(
            buffer,
            as_attachment=True,
            download_name="seo_output.docx",
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
    except Exception as e:
        app.logger.exception("DOCX export error")
        return jsonify({"error": f"DOCX export failed: {str(e)}"}), 500


@app.route("/image/upscale-smooth", methods=["POST"])
def image_upscale_smooth():
    try:
        data = request.get_json(silent=True) or {}
        image_data = data.get("image")
        scale = int(data.get("scale", 2))
        clean_mode = (data.get("clean_mode") or "balanced").strip().lower()
        output_format = (data.get("output_format") or "png").strip().lower()

        if not image_data:
            return jsonify({"error": "No image provided."}), 400

        if scale not in (2, 3, 4):
            return jsonify({"error": "Scale must be 2, 3, or 4."}), 400

        if clean_mode not in ("soft", "balanced", "cleanest"):
            clean_mode = "balanced"

        if output_format not in SUPPORTED_IMAGE_FORMATS:
            output_format = "png"

        image = decode_base64_image(image_data)
        result = upscale_smooth_image(image, scale=scale, clean_mode=clean_mode)

        if output_format in ("jpg", "jpeg"):
            if result.mode in ("RGBA", "LA"):
                bg = Image.new("RGB", result.size, (255, 255, 255))
                bg.paste(result, mask=result.getchannel("A"))
                result = bg
            elif result.mode != "RGB":
                result = result.convert("RGB")
            fmt = "JPEG"
        elif output_format == "webp":
            fmt = "WEBP"
        else:
            fmt = "PNG"

        result_data = encode_image_to_base64(result, fmt=fmt)

        return jsonify({
            "image": result_data,
            "width": result.width,
            "height": result.height,
            "scale": scale,
            "clean_mode": clean_mode,
            "output_format": output_format
        })
    except Exception as e:
        app.logger.exception("Upscale smooth error")
        return jsonify({"error": f"Upscale failed: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(debug=True)
