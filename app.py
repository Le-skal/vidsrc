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
MAX_HISTORY = 12

gc = gspread.authorize(credentials)
workbook = gc.open_by_key(SHEET_ID)


def get_avatar_sheet():
    """Get or create the avatars sheet."""
    try:
        ws = workbook.worksheet("avatars")
        # Check headers and migrate if needed
        try:
            headers = ws.row_values(1)
            # If old schema detected, migrate it
            if headers == ["account", "avatar"]:
                print("Migrating avatar sheet from old schema...")
                # Get all data
                records = ws.get_all_records()
                # Clear and recreate with new schema
                ws.clear()
                ws.append_row(["account", "avatar_url", "avatar_seed"])
                # Migrate existing data - avatar URLs stored as URLs
                for record in records:
                    account = record.get("account", "")
                    avatar_url = record.get("avatar", "")
                    # If it's a URL, use it; otherwise skip (it was text-based)
                    if avatar_url.startswith("http"):
                        seed = avatar_url.split("seed=")[-1] if "seed=" in avatar_url else ""
                        ws.append_row([account, avatar_url, seed])
        except Exception as e:
            print("Migration check error:", e)
        return ws
    except gspread.WorksheetNotFound:
        ws = workbook.add_worksheet(title="avatars", rows=100, cols=3)
        ws.append_row(["account", "avatar_url", "avatar_seed"])
        return ws


def get_gaming_avatars(seed_base, count=4):
    """Fetch random gaming-style avatars from DiceBear API."""
    import random
    import string
    avatars = []
    styles = ["pixel-art", "adventurer", "lorelei"]
    
    # Generate a random suffix to ensure different avatars on each request
    random_suffix = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    
    for i in range(count):
        seed = f"{seed_base}_{random_suffix}_{i}"
        style = styles[i % len(styles)]
        url = f"https://api.dicebear.com/7.x/{style}/svg?seed={seed}"
        avatars.append({
            "url": url,
            "seed": seed,
            "style": style
        })
    return avatars


def get_or_create_avatar(account):
    """Get existing avatar or return None if not set."""
    avatar_sheet = get_avatar_sheet()
    try:
        records = avatar_sheet.get_all_records()
        for record in records:
            if record.get("account", "").strip() == account.strip():
                # Try new schema first, then fallback to old schema
                avatar_url = record.get("avatar_url") or record.get("avatar", "")
                if avatar_url and avatar_url.startswith("http"):
                    return avatar_url
    except Exception as e:
        print(f"Error getting avatar for {account}:", e)
    return None


def has_avatar(account):
    """Check if account has an avatar set."""
    return get_or_create_avatar(account) is not None


def save_avatar(account, avatar_url, seed):
    """Save or update avatar for account."""
    avatar_sheet = get_avatar_sheet()
    try:
        records = avatar_sheet.get_all_records()
        # Find and update existing
        for i, record in enumerate(records):
            if record.get("account") == account:
                avatar_sheet.update_cell(i + 2, 2, avatar_url)  # column B
                avatar_sheet.update_cell(i + 2, 3, seed)        # column C
                return
        # Add new if not found
        avatar_sheet.append_row([account, avatar_url, seed])
    except Exception as e:
        print("Error saving avatar:", e)


def get_user_sheet():
    """Return the active user's Google Sheet worksheet."""
    account = session.get("account")
    if not account:
        return None
    try:
        return workbook.worksheet(account)
    except gspread.WorksheetNotFound:
        # Create new sheet if it doesn't exist
        ws = workbook.add_worksheet(title=account, rows=100, cols=7)
        headers = ["title", "id", "type", "season", "episode", "poster", "timestamp"]
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
        headers = ["title", "id", "type", "season", "episode", "poster", "timestamp"]
        rows = [headers] + [
            [
                h.get("title", ""),
                h.get("id", ""),
                h.get("type", ""),
                h.get("season", ""),
                h.get("episode", ""),
                h.get("poster", ""),
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
                            "poster": item.get("Poster"),
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
        is_new_account = False
        try:
            workbook.worksheet(account)
        except gspread.WorksheetNotFound:
            is_new_account = True
            ws = workbook.add_worksheet(title=account, rows=100, cols=7)
            ws.append_row(["title", "id", "type", "season", "episode", "poster", "timestamp"])

        session["account"] = account
        
        # For new accounts, redirect to avatar selection
        if is_new_account:
            return redirect(url_for("select_avatar"))
        
        # For existing accounts without avatar, redirect to avatar selection
        if not has_avatar(account):
            return redirect(url_for("select_avatar"))
        
        return redirect(url_for("index"))

    # List existing accounts (exclude "avatars" sheet)
    accounts = [ws.title for ws in workbook.worksheets() if ws.title != "avatars"]
    
    # Get avatars for each account
    account_avatars = {}
    for acc in accounts:
        avatar_url = get_or_create_avatar(acc)
        account_avatars[acc] = avatar_url
    
    return render_template("login.html", accounts=accounts, account_avatars=account_avatars)


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
        return jsonify({"error": "Not logged in"}), 403
    q = (request.json or {}).get("q", "")
    t = (request.json or {}).get("type")
    results = search_titles(q, search_type=t)
    return jsonify(results)


@app.route("/api/details/<imdb_id>")
def get_details(imdb_id):
    """Fetch full details from OMDB including ratings, plot, etc."""
    if not OMDB_API_KEY:
        return jsonify({"error": "API key not configured"}), 400
    try:
        r = requests.get(
            "http://www.omdbapi.com/",
            params={"apikey": OMDB_API_KEY, "i": imdb_id},
            timeout=8
        )
        r.raise_for_status()
        data = r.json()
        if data.get("Response") == "True":
            return jsonify(data)
        return jsonify({"error": "Not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/test_player")
def test_player():
    """Minimal test player for debugging embed load times."""
    if "account" not in session:
        return redirect(url_for("login"))

    id_ = request.args.get("id")
    media_type = (request.args.get("type") or "movie").lower()
    season = request.args.get("season")
    episode = request.args.get("episode")

    season_int = int(season) if season and season.isdigit() else 1
    episode_int = int(episode) if episode and episode.isdigit() else 1

    iframe = (
        f"https://vidsrc.to/embed/tv/{id_}/{season_int}/{episode_int}"
        if media_type == "tv"
        else f"https://vidsrc.to/embed/movie/{id_}"
    )

    return render_template("test_player.html", iframe_url=iframe)


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
        f"https://vidsrc.to/embed/tv/{id_}/{season_int}/{episode_int}"
        if media_type == "tv"
        else f"https://vidsrc.to/embed/movie/{id_}"
    )

    # Use existing poster from history if available, avoid unnecessary API call
    poster_url = ""
    if prev and prev.get("poster"):
        poster_url = prev["poster"]

    # Save history immediately to ensure it gets to the top of the sheet
    add_to_history({
        "title": title or id_,
        "id": id_,
        "type": media_type,
        "season": season_int,
        "episode": episode_int,
        "poster": poster_url,
        "timestamp": datetime.utcnow().isoformat(),
    })
    
    # Fetch poster in background if missing (non-blocking)
    if not poster_url and OMDB_API_KEY:
        from threading import Thread
        
        def fetch_poster_async():
            try:
                r = requests.get(
                    "http://www.omdbapi.com/",
                    params={"apikey": OMDB_API_KEY, "i": id_},
                    timeout=5
                )
                if r.status_code == 200:
                    data = r.json()
                    if data.get("Poster") and data.get("Poster") != "N/A":
                        # Update history with poster
                        history = load_history()
                        for h in history:
                            if h["id"] == id_ and h["type"] == media_type:
                                h["poster"] = data["Poster"]
                                break
                        save_history(history)
            except Exception as e:
                print(f"Error fetching poster: {e}")
        
        thread = Thread(target=fetch_poster_async, daemon=True)
        thread.start()

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
    
    # Find existing entry to preserve poster
    existing_poster = ""
    for h in history:
        if h["id"] == data["id"] and h["type"] == data["type"]:
            existing_poster = h.get("poster", "")
            break
    
    # Remove old entry
    history = [
        h for h in history if not (h["id"] == data["id"] and h["type"] == data["type"])
    ]
    
    # Insert updated entry with preserved poster
    history.insert(
        0,
        {
            "title": data.get("title", data["id"]),
            "id": data["id"],
            "type": data["type"],
            "season": data.get("season"),
            "episode": data.get("episode"),
            "poster": data.get("poster", "") or existing_poster,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )
    save_history(history)
    return jsonify({"status": "ok"})
    return jsonify({"status": "ok"})


@app.route("/api/update_poster", methods=["POST"])
def update_poster():
    """Update poster for an existing history item"""
    if "account" not in session:
        return jsonify({"error": "Not logged in"}), 403

    data = request.json
    if not data or "id" not in data or "type" not in data:
        return jsonify({"error": "Missing required fields"}), 400

    history = load_history()
    
    # Find and update the item
    for item in history:
        if item.get("id") == data["id"] and item.get("type") == data["type"]:
            item["poster"] = data.get("poster", "")
            save_history(history)
            return jsonify({"status": "ok"})
    
    return jsonify({"error": "Item not found"}), 404


@app.route("/api/avatar", methods=["POST"])
def update_avatar():
    """Update avatar for current account"""
    if "account" not in session:
        return jsonify({"error": "Not logged in"}), 403

    data = request.json
    if not data or "avatar_url" not in data or "seed" not in data:
        return jsonify({"error": "Missing avatar_url or seed"}), 400

    avatar_url = data.get("avatar_url", "").strip()
    seed = data.get("seed", "").strip()
    
    if not avatar_url or not seed:
        return jsonify({"error": "avatar_url and seed required"}), 400

    save_avatar(session["account"], avatar_url, seed)
    return jsonify({"status": "ok"})


@app.route("/api/random_avatars")
def get_random_avatars():
    """Get random gaming avatars for selection."""
    account = session.get("account", "default")
    avatars = get_gaming_avatars(account)
    return jsonify(avatars)


@app.route("/select_avatar")
def select_avatar():
    """Avatar selection page for new/incomplete accounts."""
    if "account" not in session:
        return redirect(url_for("login"))
    return render_template("select_avatar.html", account=session["account"])


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
