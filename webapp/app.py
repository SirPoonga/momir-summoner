#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flask import Flask, jsonify, render_template, request, send_file
from momir_config import get_web_host, get_web_port

from momir_adapter import (
    card_details,
    card_update_status,
    dashboard_status,
    network_status,
    preview_card,
    printer_status,
    print_back_current,
    print_last,
    mark_current_printed,
    reprint_last,
    search,
    select_card,
    start_card_update,
    status,
    summon,
)

app = Flask(__name__)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 3600


@app.after_request
def add_response_headers(response):
    # API state should never be replayed from a mobile browser cache.
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/settings")
def settings_page():
    return render_template("settings.html")


@app.get("/card/<card_id>")
def card_page(card_id):
    card = card_details(card_id)
    if not card:
        return ("Card not found", 404)
    return render_template("card_detail.html", card=card)


@app.get("/api/dashboard")
def api_dashboard():
    return jsonify(dashboard_status())


@app.get("/api/network")
def api_network():
    return jsonify(network_status())


@app.get("/api/printer")
def api_printer():
    return jsonify(printer_status())


@app.get("/api/status")
def api_status():
    return jsonify(status())


@app.post("/api/summon")
def api_summon():
    data = request.get_json(force=True)
    mv = int(data.get("mana_value", 1))
    result = summon(mv)
    if not result:
        return jsonify({"ok": False, "error": "No creature found for that mana value."}), 404
    return jsonify({"ok": True, **result})


@app.post("/api/print")
def api_print():
    return jsonify(print_last())


@app.post("/api/reprint")
def api_reprint():
    return jsonify(reprint_last())


@app.post("/api/mark_printed")
def api_mark_printed():
    result = mark_current_printed()
    status_code = 200 if result.get("ok") else 400
    return jsonify(result), status_code


@app.post("/api/print_back")
def api_print_back():
    return jsonify(print_back_current())


@app.post("/api/select")
def api_select():
    data = request.get_json(force=True)
    card_id = data.get("id")
    result = select_card(card_id)
    if not result:
        return jsonify({"ok": False, "error": "Card not found."}), 404
    return jsonify({"ok": True, **result})


@app.get("/api/cards/update")
def api_card_update_status():
    return jsonify({"ok": True, **card_update_status()})


@app.post("/api/cards/update")
def api_start_card_update():
    started, update_state = start_card_update()
    return jsonify({"ok": True, "started": started, **update_state}), 202


@app.get("/api/search")
def api_search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    return jsonify(search(q))


@app.get("/preview/card/<card_id>.jpg")
def preview_card_image(card_id):
    path = preview_card(card_id)
    if not path or not Path(path).exists():
        return ("Preview not found", 404)

    # Card-specific URLs are immutable and may be cached by the phone.
    return send_file(
        path,
        mimetype="image/jpeg",
        conditional=True,
        max_age=31536000,
    )


@app.get("/preview/card/<card_id>/back.jpg")
def preview_card_back_image(card_id):
    path = preview_card(card_id, face="back")
    if not path or not Path(path).exists():
        return ("Back preview not found", 404)

    return send_file(
        path,
        mimetype="image/jpeg",
        conditional=True,
        max_age=31536000,
    )


if __name__ == "__main__":
    app.run(host=get_web_host(), port=get_web_port(), threaded=True)
