#!/usr/bin/env python3
"""
TV Dashboard Blueprint — serves Apple TV Top Shelf data.

Endpoints:
  GET /tv/dashboard       — all sections as JSON
  GET /tv/section/<id>    — single section
  GET /tv/images/<id>.png — Pillow-rendered poster card (404x608)
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, send_file, abort
from PIL import Image, ImageDraw, ImageFont

tv = Blueprint("tv", __name__)

DATA_DIR = Path("/home/jaredgantt/data")
LISTS_DIR = DATA_DIR / "lists"
REMINDERS_DIR = DATA_DIR / "reminders"
HISTORY_DIR = DATA_DIR / "history"
CACHE_DIR = DATA_DIR / "tv_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Card dimensions (TVTopShelfSectionedContent poster shape)
CARD_W, CARD_H = 404, 608

# Section colors
SECTION_COLORS = {
    "todo": (30, 120, 220),      # blue
    "grocery": (46, 164, 79),    # green
    "reminders": (220, 120, 30), # orange
    "activity": (130, 80, 200),  # purple
}


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------

def _load_json_items(path: Path) -> list[dict]:
    """Load items from a JSON file with {"items": [...]} format."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        return data.get("items", [])
    except (json.JSONDecodeError, KeyError):
        return []


def _get_list_items(path: Path) -> list[dict]:
    """Get active (not done, not deleted) items from a JSON list file."""
    items = _load_json_items(path)
    return [i for i in items if not i.get("done") and not i.get("deleted")]


def _get_activity_summary() -> list[dict]:
    """Summarize today's history by source."""
    today = datetime.now().strftime("%Y-%m-%d")
    hist_file = HISTORY_DIR / f"{today}.json"
    if not hist_file.exists():
        return [{"text": "No activity today", "subtitle": today}]
    entries = json.loads(hist_file.read_text())
    counts: dict[str, int] = {}
    for e in entries:
        src = e.get("source", "unknown")
        counts[src] = counts.get(src, 0) + 1
    items = []
    for src, count in sorted(counts.items(), key=lambda x: -x[1]):
        items.append({
            "text": src,
            "subtitle": f"{count} exchange{'s' if count != 1 else ''}",
        })
    if not items:
        items.append({"text": "No activity today", "subtitle": today})
    return items


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _build_section(section_id: str) -> dict:
    """Build a single section dict."""
    if section_id == "todo":
        items = _get_list_items(LISTS_DIR / "todo.json")
        return {
            "id": "todo",
            "title": "To Do",
            "items": [
                {
                    "id": f"todo-{idx}",
                    "title": it.get("text", ""),
                    "subtitle": "pending",
                    "imageURL": f"/tv/images/todo-{idx}.png",
                }
                for idx, it in enumerate(items)
            ],
        }

    elif section_id == "grocery":
        items = _get_list_items(LISTS_DIR / "grocery.json")
        return {
            "id": "grocery",
            "title": "Grocery List",
            "items": [
                {
                    "id": f"grocery-{idx}",
                    "title": it.get("text", ""),
                    "subtitle": "",
                    "imageURL": f"/tv/images/grocery-{idx}.png",
                }
                for idx, it in enumerate(items)
            ],
        }

    elif section_id == "reminders":
        items = _get_list_items(REMINDERS_DIR / "reminders.json")
        return {
            "id": "reminders",
            "title": "Reminders",
            "items": [
                {
                    "id": f"reminders-{idx}",
                    "title": it.get("text", ""),
                    "subtitle": it.get("due", ""),
                    "imageURL": f"/tv/images/reminders-{idx}.png",
                }
                for idx, it in enumerate(items)
            ],
        }

    elif section_id == "activity":
        items = _get_activity_summary()
        return {
            "id": "activity",
            "title": "Recent Activity",
            "items": [
                {
                    "id": f"activity-{idx}",
                    "title": it["text"],
                    "subtitle": it.get("subtitle", ""),
                    "imageURL": f"/tv/images/activity-{idx}.png",
                }
                for idx, it in enumerate(items)
            ],
        }

    abort(404)


SECTION_ORDER = ["todo", "grocery", "reminders", "activity"]


def _build_dashboard() -> dict:
    return {
        "sections": [_build_section(s) for s in SECTION_ORDER],
        "generated": datetime.now().isoformat(timespec="seconds"),
    }


# ---------------------------------------------------------------------------
# Image rendering
# ---------------------------------------------------------------------------

def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Word-wrap text to fit within max_width pixels."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = font.getbbox(test)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [text]


def _render_card(section_id: str, title: str, subtitle: str) -> Path:
    """Render a 404x608 poster card. Returns cached file path."""
    content_key = f"{section_id}:{title}:{subtitle}"
    h = hashlib.md5(content_key.encode()).hexdigest()[:12]
    cache_path = CACHE_DIR / f"{h}.png"
    if cache_path.exists():
        return cache_path

    color = SECTION_COLORS.get(section_id, (100, 100, 100))
    img = Image.new("RGB", (CARD_W, CARD_H), color)
    draw = ImageDraw.Draw(img)

    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
        font_sub = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
        font_label = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
    except OSError:
        font_title = ImageFont.load_default()
        font_sub = font_title
        font_label = font_title

    padding = 30
    max_text_w = CARD_W - padding * 2

    # Section label at top
    section_label = section_id.upper()
    draw.text((padding, padding), section_label, fill=(255, 255, 255, 180), font=font_label)

    # Title (wrapped)
    title_lines = _wrap_text(title, font_title, max_text_w)
    y = 120
    for line in title_lines[:4]:
        draw.text((padding, y), line, fill="white", font=font_title)
        y += 46

    # Subtitle
    if subtitle:
        sub_lines = _wrap_text(subtitle, font_sub, max_text_w)
        y += 20
        for line in sub_lines[:2]:
            draw.text((padding, y), line, fill=(220, 220, 220), font=font_sub)
            y += 32

    # Bottom decorative line
    draw.line([(padding, CARD_H - 60), (CARD_W - padding, CARD_H - 60)], fill=(255, 255, 255, 100), width=2)

    img.save(cache_path, "PNG")
    return cache_path


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@tv.route("/tv/dashboard", methods=["GET"])
def dashboard():
    return jsonify(_build_dashboard())


@tv.route("/tv/section/<section_id>", methods=["GET"])
def section(section_id):
    if section_id not in SECTION_ORDER:
        abort(404)
    return jsonify(_build_section(section_id))


@tv.route("/tv/images/<image_id>.png", methods=["GET"])
def card_image(image_id):
    """Serve a rendered card image. image_id format: section-index (e.g. todo-0)."""
    parts = image_id.rsplit("-", 1)
    if len(parts) != 2:
        abort(404)
    section_id, idx_str = parts
    if section_id not in SECTION_ORDER:
        abort(404)
    try:
        idx = int(idx_str)
    except ValueError:
        abort(404)

    section = _build_section(section_id)
    if idx >= len(section["items"]):
        abort(404)

    item = section["items"][idx]
    path = _render_card(section_id, item["title"], item.get("subtitle", ""))
    return send_file(path, mimetype="image/png")


# ---------------------------------------------------------------------------
# Coding Mode endpoints
# ---------------------------------------------------------------------------

from coding_session import CodingSessionManager
from flask import request, Response

_session_mgr = CodingSessionManager()


@tv.route("/tv/coding/message", methods=["POST"])
def coding_message():
    """Stream Claude response as NDJSON."""
    data = request.get_json(silent=True) or {}
    terminal = data.get("terminal", 0)
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "no text"}), 400
    return Response(
        _session_mgr.send_message(terminal, text),
        mimetype="application/x-ndjson",
    )


@tv.route("/tv/coding/sessions", methods=["GET"])
def coding_sessions():
    """Return which sessions are active."""
    return jsonify({"sessions": _session_mgr.get_sessions()})


@tv.route("/tv/coding/clear/<int:terminal>", methods=["POST"])
def coding_clear(terminal):
    """Clear a terminal session."""
    _session_mgr.clear(terminal)
    return jsonify({"ok": True})


@tv.route("/tv/coding/transcribe", methods=["POST"])
def coding_transcribe():
    """Transcribe audio using faster-whisper. Expects WAV in request body."""
    import tempfile
    import subprocess as sp

    audio_data = request.get_data()
    if not audio_data:
        return jsonify({"error": "no audio data"}), 400

    # Write to temp file
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(audio_data)
        tmp_path = f.name

    try:
        # Use faster-whisper via the Python API
        result = sp.run(
            ["python3", "-c", f"""
import sys
from faster_whisper import WhisperModel
model = WhisperModel("medium.en", compute_type="int8")
segments, _ = model.transcribe("{tmp_path}")
text = " ".join(s.text.strip() for s in segments)
print(text)
"""],
            capture_output=True, text=True, timeout=30,
        )
        text = result.stdout.strip()
        return jsonify({"text": text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        import os
        os.unlink(tmp_path)


@tv.route("/tv/coding/mac-sessions", methods=["GET"])
def coding_mac_sessions():
    """Scan Mac for existing Claude Code sessions."""
    sessions = _session_mgr.scan_mac_sessions()
    # Add project labels
    for s in sessions:
        path = s.get("project_path", "")
        parts = path.rstrip("/").split("/")
        skip = {"Users", "jaredgantt", "home", "Projects"}
        meaningful = [p for p in parts if p and p not in skip]
        s["label"] = meaningful[-1] if meaningful else path
    return jsonify({"sessions": sessions})


@tv.route("/tv/coding/attach", methods=["POST"])
def coding_attach():
    """Attach an existing Mac session to a TV terminal."""
    data = request.get_json(silent=True) or {}
    terminal = data.get("terminal", 0)
    session_id = data.get("session_id", "").strip()
    label = data.get("label", "")
    if not session_id:
        return jsonify({"error": "no session_id"}), 400
    ok = _session_mgr.attach(terminal, session_id, label)
    if ok:
        return jsonify({"ok": True})
    return jsonify({"error": "invalid terminal"}), 400


@tv.route("/tv/coding/history/<session_id>", methods=["GET"])
def coding_history(session_id):
    """Get conversation history for a session."""
    messages = _session_mgr.get_session_history(session_id)
    return jsonify({"messages": messages})
