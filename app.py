import os
import json
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "supersecretkey")  # Needed for sessions

OMDB_API_KEY = os.getenv("OMDB_API_KEY")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
GOOGLE_CREDS = os.getenv("GOOGLE_CREDS")
credentials_dict = json.loads(GOOGLE_CREDS)
credentials = Credentials.from_service_account_info(credentials_dict, scopes=SCOPES)

SHEET_ID = "1R0Ske-O8Rv_1o6Kp329y3xE2kzwAO7O2_Y_tpJ7dOt4"
MAX_HISTORY = 10

gc = gspread.authorize(credentials)
workbook = gc.open_by_key(SHEET_ID)


def get_user_sheet():
    """Return the active user's Google Sheet worksheet."""
    account = session.get("account")
    if not account:
        return None
    try:
        return workbook.worksheet(account)
    except gspread.WorksheetNotFound:
        # Create new sheet if it doesn't exist
        ws = workbook.add_worksheet(title=account, rows=100, cols=6)
        headers = ["title", "id", "type", "season", "episode", "timestamp"]
        ws.append_row(headers)
        return ws


def load_history():
    sheet = get_user_sheet()
    if not sheet:
        return []
    try:
        records = sheet.get_all_records()
        return records or []
    except Exception as e:
        print("Error loading history:", e)
        return []


def save_history(history):
    sheet = get_user_sheet()
    if not sheet:
        return
    try:
        history = history[:MAX_HISTORY]
        sheet.clear()
        headers = ["title", "id", "type", "season", "episode", "timestamp"]
        rows = [headers] + [
            [
                h.get("title", ""),
                h.get("id", ""),
                h.get("type", ""),
                h.get("season", ""),
                h.get("episode", ""),
                h.get("timestamp", ""),
            ]
            for h in history
        ]
        sheet.update(rows)
    except Exception as e:
        print("Error saving history:", e)


def add_to_history(entry):
    history = load_history()
    history = [
        h for h in history if not (h["id"] == entry["id"] and h["type"] == entry["type"])
    ]
    history.insert(0, entry)
    save_history(history)


def search_titles(query, search_type=None, max_results=10):
    q = query.strip()
    results = []
    if not q:
        return results
    if OMDB_API_KEY:
        params = {"apikey": OMDB_API_KEY, "s": q}
        if search_type:
            params["type"] = search_type
        try:
            r = requests.get("http://www.omdbapi.com/", params=params, timeout=8)
            r.raise_for_status()
            data = r.json()
            if data.get("Response") == "True":
                for item in data.get("Search", [])[:max_results]:
                    results.append(
                        {
                            "title": item.get("Title"),
                            "year": item.get("Year"),
                            "imdb_id": item.get("imdbID"),
                            "type": "movie" if item.get("Type") == "movie" else "tv",
                        }
                    )
                return results
        except Exception:
            pass

    # fallback to IMDb scrape
    try:
        r = requests.get(
            "https://www.imdb.com/find",
            params={"q": q, "s": "tt"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=8,
        )
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        rows = soup.select("table.findList tr")
        for tr in rows[:max_results]:
            a = tr.select_one("td.result_text a")
            if not a:
                continue
            href = a.get("href", "")
            import re

            m = re.search(r"/title/(tt\d+)", href)
            if not m:
                continue
            imdb_id = m.group(1)
            txt = tr.select_one("td.result_text").get_text(strip=True)
            year_match = re.search(r"\((\d{4})\)", txt)
            year = year_match.group(1) if year_match else ""
            typ = "tv" if "TV" in txt else "movie"
            results.append(
                {"title": a.text, "year": year, "imdb_id": imdb_id, "type": typ}
            )
        return results
    except Exception:
        return results


# 🧑‍💻 Account selection routes
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        account = request.form.get("account", "").strip()
        if not account:
            return render_template("login.html", error="Please enter an account name")

        # Create worksheet if it doesn't exist
        try:
            workbook.worksheet(account)
        except gspread.WorksheetNotFound:
            ws = workbook.add_worksheet(title=account, rows=100, cols=6)
            ws.append_row(["title", "id", "type", "season", "episode", "timestamp"])

        session["account"] = account
        return redirect(url_for("index"))

    # List existing accounts
    accounts = [ws.title for ws in workbook.worksheets()]
    return render_template("login.html", accounts=accounts)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
def index():
    if "account" not in session:
        return redirect(url_for("login"))
    history = load_history()
    return render_template("index.html", history=history, account=session["account"])


@app.route("/search", methods=["POST"])
def search():
    if "account" not in session:
        return redirect(url_for("login"))
    q = (request.json or {}).get("q", "")
    t = (request.json or {}).get("type")
    return jsonify(search_titles(q, search_type=t))


@app.route("/player")
def player():
    if "account" not in session:
        return redirect(url_for("login"))

    id_ = request.args.get("id")
    media_type = (request.args.get("type") or "movie").lower()
    season = request.args.get("season")
    episode = request.args.get("episode")
    title = request.args.get("title", "")

    history = load_history()
    prev = next(
        (h for h in history if h["id"] == id_ and h["type"] == media_type), None
    )

    season_int = (
        int(season)
        if season and season.isdigit()
        else (prev["season"] if prev and prev.get("season") else 1 if media_type == "tv" else None)
    )
    episode_int = (
        int(episode)
        if episode and episode.isdigit()
        else (prev["episode"] if prev and prev.get("episode") else 1 if media_type == "tv" else None)
    )

    iframe = (
        f"https://vidsrc.icu/embed/tv/{id_}/{season_int}/{episode_int}"
        if media_type == "tv"
        else f"https://vidsrc.icu/embed/movie/{id_}"
    )

    add_to_history(
        {
            "title": title or id_,
            "id": id_,
            "type": media_type,
            "season": season_int,
            "episode": episode_int,
            "timestamp": datetime.utcnow().isoformat(),
        }
    )

    return render_template(
        "player.html",
        iframe_url=iframe,
        id=id_,
        media_type=media_type,
        season=season_int,
        episode=episode_int,
        title=title,
    )


@app.route("/api/history")
def api_history():
    if "account" not in session:
        return jsonify([])
    return jsonify(load_history())


@app.route("/api/update_progress", methods=["POST"])
def update_progress():
    if "account" not in session:
        return jsonify({"error": "Not logged in"}), 403

    data = request.json
    if not data:
        return jsonify({"error": "No data"}), 400

    history = load_history()
    history = [
        h for h in history if not (h["id"] == data["id"] and h["type"] == data["type"])
    ]
    history.insert(
        0,
        {
            "title": data.get("title", data["id"]),
            "id": data["id"],
            "type": data["type"],
            "season": data.get("season"),
            "episode": data.get("episode"),
            "timestamp": datetime.utcnow().isoformat(),
        },
    )
    save_history(history)
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
