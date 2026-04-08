"""Local dev server for The Marathon dashboard."""
import os
from http.server import SimpleHTTPRequestHandler, HTTPServer

PORT = 8110
os.chdir(os.path.dirname(os.path.abspath(__file__)))

print(f"The Marathon — http://localhost:{PORT}")
HTTPServer(("", PORT), SimpleHTTPRequestHandler).serve_forever()
