"""
MarketDashboard — Minimal Static File Server
Serves dashboard.html at / — scan data is fetched client-side from GitHub raw.
Run: python app.py
"""

from flask import Flask, send_from_directory, Response
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)


@app.route("/")
def index():
    html_path = os.path.join(BASE_DIR, "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return Response(f.read(), mimetype="text/html")


@app.route("/data/<path:filename>")
def data(filename):
    return send_from_directory(os.path.join(BASE_DIR, "data"), filename)


@app.route("/images/<path:filename>")
def images(filename):
    return send_from_directory(os.path.join(BASE_DIR, "..", "Website", "images"), filename)


@app.route("/ping")
def ping():
    return Response("OK", mimetype="text/plain")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"[Startup] Dashboard running at http://localhost:{port}")
    app.run(host="0.0.0.0", port=port)
