from flask import Flask, render_template, request, jsonify
import re

app = Flask(__name__)

def clean_text(text):
    return re.sub(r"\s+", " ", text.strip())

def format_seo(article):
    title = article[:60]
    return {
        "H1 Tag": title + " 2026",
        "Introduction": article[:120],
        "H2 Tags": "H2 1: Main Content",
        "Main Content Body": article,
        "Internal Link Placeholder": "Read more about [Topic]...",
        "Conclusion & CTA": "What do you think?",
        "Focus Keyphrase": title,
        "SEO Title": title,
        "Meta Description": article[:150],
        "Image Alt Text": "Image about article",
        "Image Title": title,
        "Slug (URL)": title.lower().replace(" ", "-"),
        "Short Summary (20-second video)": "- " + article[:100]
    }

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/format", methods=["POST"])
def format_article():
    data = request.json
    article = data.get("article", "")
    return jsonify(format_seo(article))

if __name__ == "__main__":
    app.run(debug=True)
