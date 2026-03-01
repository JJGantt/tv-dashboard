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
from atv_control import run_wake_and_focus, run_command

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


@app.route("/tv/wake", methods=["POST"])
def wake():
    """Wake the Apple TV and switch TV input to it."""
    try:
        run_wake_and_focus()
        return jsonify({"ok": True, "message": "Apple TV woken and focused"})
    except Exception as e:
        logging.error(f"Wake failed: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


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


if __name__ == "__main__":
    logging.info(f"Starting TV Dashboard server on port {PORT}...")
    app.run(host="0.0.0.0", port=PORT, threaded=True)
