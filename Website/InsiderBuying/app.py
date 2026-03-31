"""
InsiderBuying -- Minimal Static File Server
Serves index.html at / -- scan data is fetched client-side from data/results.json.
Run: python app.py
"""

from flask import Flask, Response, send_from_directory
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)


@app.route("/")
def index():
    with open(os.path.join(BASE_DIR, "index.html"), "r", encoding="utf-8") as f:
        return Response(f.read(), mimetype="text/html")


@app.route("/data/<path:filename>")
def data(filename):
    return send_from_directory(os.path.join(BASE_DIR, "data"), filename)


@app.route("/ping")
def ping():
    return Response("OK", mimetype="text/plain")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8085))
    print(f"[Startup] InsiderBuying running at http://localhost:{port}")
    app.run(host="0.0.0.0", port=port)
