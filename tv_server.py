#!/usr/bin/env python3
"""
TV Dashboard server — standalone Flask app serving Apple TV Top Shelf data.
Runs on port 8766.

Pi IPs:
  Local:     10.0.0.14
  Tailscale: 100.104.197.58
"""

import logging
from flask import Flask, jsonify
from tv_dashboard import tv

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


if __name__ == "__main__":
    logging.info(f"Starting TV Dashboard server on port {PORT}...")
    app.run(host="0.0.0.0", port=PORT, threaded=True)
