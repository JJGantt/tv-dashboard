#!/usr/bin/env python3
"""
TV Dashboard server — standalone Flask app serving Apple TV Top Shelf data.
Runs on port 8766.

Pi IPs:
  Local:     10.0.0.14
  Tailscale: 100.104.197.58
"""

import logging
from flask import Flask, jsonify, request
from tv_dashboard import tv
from atv_control import (
    run_wake_and_focus, run_sleep, run_command,
    run_now_playing, run_list_apps, run_launch_app,
    run_play_url, run_set_volume, run_volume_up, run_volume_down,
)

PORT = 8766

app = Flask(__name__)
app.register_blueprint(tv)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)


@app.route("/status")
def status():
    return jsonify({"ok": True, "host": "raspberrypi", "service": "tv-server"})


# --- Wake / Sleep ---

@app.route("/tv/wake", methods=["POST"])
def wake():
    """Wake the Apple TV and switch TV input to it."""
    try:
        run_wake_and_focus()
        return jsonify({"ok": True, "message": "Apple TV woken and focused"})
    except Exception as e:
        logging.error(f"Wake failed: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/tv/sleep", methods=["POST"])
def sleep():
    """Put the Apple TV to sleep."""
    try:
        run_sleep()
        return jsonify({"ok": True, "message": "Apple TV is now sleeping"})
    except Exception as e:
        logging.error(f"Sleep failed: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


# --- Remote Control ---

@app.route("/tv/command", methods=["POST"])
def command():
    """Send a remote control command to the Apple TV."""
    data = request.get_json(silent=True) or {}
    cmd = data.get("command", "").strip()
    if not cmd:
        return jsonify({"ok": False, "error": "no command"}), 400
    try:
        run_command(cmd)
        return jsonify({"ok": True, "message": f"Sent: {cmd}"})
    except Exception as e:
        logging.error(f"Command '{cmd}' failed: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


# --- Now Playing ---

@app.route("/tv/now_playing", methods=["GET"])
def now_playing():
    """Get metadata about what's currently playing."""
    try:
        data = run_now_playing()
        return jsonify({"ok": True, **data})
    except Exception as e:
        logging.error(f"Now playing failed: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


# --- Apps ---

@app.route("/tv/apps", methods=["GET"])
def apps():
    """List installed apps on the Apple TV."""
    try:
        app_list = run_list_apps()
        return jsonify({"ok": True, "apps": app_list})
    except Exception as e:
        logging.error(f"List apps failed: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/tv/launch", methods=["POST"])
def launch():
    """Launch an app by bundle ID."""
    data = request.get_json(silent=True) or {}
    app_id = data.get("app_id", "").strip()
    if not app_id:
        return jsonify({"ok": False, "error": "no app_id"}), 400
    try:
        run_launch_app(app_id)
        return jsonify({"ok": True, "message": f"Launched: {app_id}"})
    except Exception as e:
        logging.error(f"Launch '{app_id}' failed: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


# --- Streaming ---

@app.route("/tv/play_url", methods=["POST"])
def play_url():
    """Stream a URL via AirPlay."""
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"ok": False, "error": "no url"}), 400
    try:
        run_play_url(url)
        return jsonify({"ok": True, "message": f"Playing: {url}"})
    except Exception as e:
        logging.error(f"Play URL failed: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


# --- Audio ---

@app.route("/tv/volume", methods=["POST"])
def volume():
    """Control volume: set level, or step up/down."""
    data = request.get_json(silent=True) or {}
    action = data.get("action", "").strip()
    try:
        if action == "up":
            run_volume_up()
            return jsonify({"ok": True, "message": "Volume up"})
        elif action == "down":
            run_volume_down()
            return jsonify({"ok": True, "message": "Volume down"})
        elif action == "set":
            level = data.get("level")
            if level is None:
                return jsonify({"ok": False, "error": "no level specified"}), 400
            run_set_volume(float(level))
            return jsonify({"ok": True, "message": f"Volume set to {level}"})
        else:
            return jsonify({"ok": False, "error": "action must be 'up', 'down', or 'set'"}), 400
    except Exception as e:
        logging.error(f"Volume failed: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    logging.info(f"Starting TV Dashboard server on port {PORT}...")
    app.run(host="0.0.0.0", port=PORT, threaded=True)
