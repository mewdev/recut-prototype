"""
Segment boundary editor server.
Run from project root: python editor/server.py
Then open http://localhost:5050
"""

import json
import sys
from pathlib import Path

from flask import Flask, jsonify, request, send_file

sys.path.insert(0, str(Path(__file__).parent.parent))

app = Flask(__name__, static_folder=".", static_url_path="")

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_MAP = PROJECT_ROOT / "map/examples/end_of_beginning-map-v0_1.json"
DEFAULT_MP3 = PROJECT_ROOT / "mp3/end_of_beginning.mp3"


@app.route("/")
def index():
    return send_file("index.html")


@app.route("/audio")
def audio():
    return send_file(DEFAULT_MP3, mimetype="audio/mpeg")


@app.route("/map")
def get_map():
    edited = DEFAULT_MAP.parent / (DEFAULT_MAP.stem + "-edited.json")
    path = edited if edited.exists() else DEFAULT_MAP
    with open(path) as f:
        data = json.load(f)
    resp = jsonify(data)
    resp.headers["X-Map-File"] = str(path)
    return resp


@app.route("/map", methods=["POST"])
def save_map():
    data = request.json
    out_path = DEFAULT_MAP.parent / (DEFAULT_MAP.stem + "-edited.json")
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2)
    return jsonify({"saved": str(out_path)})


if __name__ == "__main__":
    app.run(port=5050, debug=True)
