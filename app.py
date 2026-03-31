"""
WordPress SEO Studio — Flask Backend
API key is stored server-side in .env and never exposed to the browser.
"""
import os, io, re, json, base64, time
from flask import Flask, request, jsonify, render_template, abort
import requests
from dotenv import load_dotenv
from PIL import Image, ImageEnhance

load_dotenv()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024   # 16 MB upload limit

TOGETHER_BASE_URL     = "https://api.together.xyz/v1"
VISION_MODEL          = "moonshotai/Kimi-K2.5"
VISION_FALLBACK_MODEL = "Qwen/Qwen3-VL-8B-Instruct"
TOGETHER_API_KEY      = os.getenv("TOGETHER_API_KEY", "")

RATE_LIMIT: dict = {}   # simple in-process rate limiter ip→timestamp list


# ── helpers ───────────────────────────────────────────────────────────────────
def _headers():
    return {"Authorization": f"Bearer {TOGETHER_API_KEY}",
            "Content-Type": "application/json"}


def _rate_ok(ip: str, max_per_min: int = 10) -> bool:
    now = time.time()
    hits = [t for t in RATE_LIMIT.get(ip, []) if now - t < 60]
    RATE_LIMIT[ip] = hits
    if len(hits) >= max_per_min:
        return False
    RATE_LIMIT[ip].append(now)
    return True


def _together_chat(model, messages, temperature=0.6,
                   top_p=0.95, response_format=None, reasoning=None):
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "top_p": top_p,
    }
    if response_format:
        payload["response_format"] = response_format
    if reasoning is not None:
        payload["reasoning"] = reasoning

    r = requests.post(
        f"{TOGETHER_BASE_URL}/chat/completions",
        headers=_headers(), json=payload, timeout=90
    )
    r.raise_for_status()
    return r.json()


def _extract(resp):
    choices = resp.get("choices") or []
    if not choices:
        return ""
    msg = choices[0].get("message") or {}
    content = msg.get("content", "")
    if isinstance(content, list):
        return "\n".join(
            str(i.get("text") or i.get("content") or "")
            for i in content if i
        ).strip()
    return str(content or "").strip()


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    for candidate in [raw, raw.replace("```json","").replace("```","").strip()]:
        m = re.search(r"\{.*\}", candidate, re.DOTALL)
        blob = m.group(0) if m else candidate
        try:
            d = json.loads(blob)
            if isinstance(d, dict):
                return d
        except Exception:
            pass
    raise ValueError("Cannot parse model JSON: " + raw[:200])


# ── routes ────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/image-seo", methods=["POST"])
def image_seo():
    """Receive image + keyword, call Together AI vision, return SEO fields."""
    ip = request.remote_addr
    if not _rate_ok(ip):
        return jsonify({"error": "Rate limit exceeded — try again in a minute."}), 429

    if not TOGETHER_API_KEY:
        return jsonify({"error": "Server API key not configured."}), 500

    file    = request.files.get("image")
    keyword = request.form.get("keyword", "image SEO").strip() or "image SEO"

    if not file:
        return jsonify({"error": "No image uploaded."}), 400

    # Resize to max 1024px on longest side to keep payload small
    try:
        img = Image.open(file.stream).convert("RGB")
        w, h = img.size
        max_dim = 1024
        if max(w, h) > max_dim:
            scale = max_dim / max(w, h)
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=85)
        data_url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        return jsonify({"error": f"Image processing failed: {e}"}), 400

    prompt = (
        "You are an image SEO assistant.\n"
        "Analyze the image and return ONLY valid JSON with exactly these keys:\n"
        "alt_text, img_title, caption\n\n"
        "Rules:\n"
        "- alt_text: max 60 chars, clear, natural description\n"
        "- img_title: short, clear, keyword-rich title\n"
        "- caption: 1 engaging natural sentence\n"
        "- never use the phrase 'featured image'\n"
        "- include the keyword naturally if it fits\n"
        "- no markdown, no explanation, no extra keys\n\n"
        f"Focus keyword / scene notes: {keyword}"
    )

    last_err = None
    for model in [VISION_MODEL, VISION_FALLBACK_MODEL]:
        try:
            extra = {"reasoning": {"enabled": False}} if "Kimi" in model else {}
            resp  = _together_chat(
                model,
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ]}],
                response_format={"type": "json_object"},
                **extra,
            )
            data = _parse_json(_extract(resp))
            def _s(t, mx):
                t = str(t).strip().replace("featured image","").replace("Featured Image","")
                return " ".join(t.split())[:mx].strip(" -,:")
            return jsonify({
                "alt_text":  _s(data.get("alt_text",""),  60),
                "img_title": _s(data.get("img_title",""), 80),
                "caption":   _s(data.get("caption",""),  180),
                "model":     model,
            })
        except Exception as e:
            last_err = e

    return jsonify({"error": str(last_err) or "Together AI failed"}), 502


@app.route("/api/seo-format", methods=["POST"])
def seo_format():
    """
    Pure Python SEO formatting — no AI needed.
    Accepts JSON: { "text": "..." }
    Returns all SEO fields including hashtags.
    """
    body = request.get_json(silent=True) or {}
    raw  = (body.get("text") or "").strip()
    if not raw:
        return jsonify({"error": "No text provided."}), 400

    from seo_logic import process_text
    try:
        result = process_text(raw)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
