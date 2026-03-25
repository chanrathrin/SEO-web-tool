from flask import Flask, render_template, request, jsonify, send_file
from docx import Document
from io import BytesIO
import re

app = Flask(__name__)


def clean_text(text):
    text = text.strip()
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text


def split_paragraphs(text):
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    return paragraphs if paragraphs else [text]


def extract_title(paragraphs):
    if paragraphs:
        first = re.sub(r"\s+", " ", paragraphs[0]).strip()
        title = first[:70]
        return title if title else "SEO Article"
    return "SEO Article"


def create_slug(title):
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug).strip("-")
    return slug[:80]


def create_meta_description(text):
    text = re.sub(r"\s+", " ", text).strip()
    return text[:160]


def create_intro(text):
    words = text.split()
    return " ".join(words[:80])


def create_h2_sections(paragraphs):
    h2s = []
    for i, p in enumerate(paragraphs[1:5], start=1):
        words = p.split()
        h2 = " ".join(words[:8]).strip()
        if h2:
            h2s.append(f"H2 {i}: {h2}")
    if not h2s:
        h2s.append("H2 1: Main Article Details")
    return h2s


def format_body(paragraphs):
    formatted = []
    for p in paragraphs:
        words = p.split()
        lines = []
        for i in range(0, len(words), 16):
            lines.append(" ".join(words[i:i + 16]))
        formatted.append("\n".join(lines))
    return "\n\n".join(formatted)


def bullet_points_summary(paragraphs):
    bullets = []
    for p in paragraphs[:4]:
        cleaned = re.sub(r"\s+", " ", p).strip()
        if cleaned:
            bullets.append(f"- {cleaned[:140]}")
    if not bullets:
        bullets.append("- No summary available.")
    return "\n".join(bullets)


def generate_video_script(title, intro, body):
    short_body = re.sub(r"\s+", " ", body)[:220]
    return (
        f"Here’s the latest on {title}. "
        f"{intro[:120]}. "
        f"{short_body}. "
        f"Stay tuned for more updates."
    )


def generate_caption(title):
    return f"{title} — quick SEO-ready breakdown, key details, and short video summary."


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


def format_seo_article(article):
    article = clean_text(article)
    paragraphs = split_paragraphs(article)

    title = extract_title(paragraphs)
    h1 = f"{title} 2026"
    intro = create_intro(article)
    h2_list = create_h2_sections(paragraphs)
    body = format_body(paragraphs)
    focus_keyphrase = title
    seo_title = title[:60]
    meta_description = create_meta_description(article)
    image_alt = f"Main image related to {title}"
    image_title = title
    slug = create_slug(title)
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

    return {
        "H1 Tag": h1,
        "Introduction": intro,
        "H2 Tags": "\n".join(h2_list),
        "Main Content Body": body,
        "Internal Link Placeholder": internal_link,
        "Conclusion & CTA": conclusion,
        "Focus Keyphrase": focus_keyphrase,
        "SEO Title": seo_title,
        "Meta Description": meta_description,
        "Image Alt Text": image_alt,
        "Image Title": image_title,
        "Slug (URL)": slug,
        "Short Summary (20-second video)": short_summary,
        "Video Script": video_script,
        "Caption": caption,
        "Hashtags": hashtags,
        "Counters": counters
    }


def build_export_text(data):
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

Meta Description:
{data.get("Meta Description", "")}

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
""".strip()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/format", methods=["POST"])
def format_article():
    data = request.get_json(silent=True) or {}
    article = (data.get("article") or "").strip()

    if not article:
        return jsonify({"error": "Please paste article content first."}), 400

    result = format_seo_article(article)
    return jsonify(result)


@app.route("/export/txt", methods=["POST"])
def export_txt():
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


@app.route("/export/docx", methods=["POST"])
def export_docx():
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
        doc.add_paragraph(data.get(section, ""))

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="seo_output.docx",
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


if __name__ == "__main__":
    app.run(debug=True)
