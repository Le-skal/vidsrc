import os
import json
from datetime import datetime
import urllib.parse
from flask import Flask, render_template, request, jsonify, url_for, redirect
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
OMDB_API_KEY = os.getenv("OMDB_API_KEY")
HISTORY_FILE = "history.json"
MAX_HISTORY = 10


def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_history(history):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print("Error saving history:", e)


def add_to_history(entry):
    history = load_history()
    # remove any duplicate id/type combo
    history = [
        h
        for h in history
        if not (h["id"] == entry["id"] and h["type"] == entry["type"])
    ]
    history.insert(0, entry)
    if len(history) > MAX_HISTORY:
        history = history[:MAX_HISTORY]
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


@app.route("/")
def index():
    history = load_history()
    return render_template("index.html", history=history)


@app.route("/search", methods=["POST"])
def search():
    q = (request.json or {}).get("q", "")
    t = (request.json or {}).get("type")
    return jsonify(search_titles(q, search_type=t))


@app.route("/player")
def player():
    id_ = request.args.get("id")
    media_type = (request.args.get("type") or "movie").lower()
    season = request.args.get("season")
    episode = request.args.get("episode")
    title = request.args.get("title", "")

    # Recover progress if not passed
    history = load_history()
    prev = next(
        (h for h in history if h["id"] == id_ and h["type"] == media_type), None
    )
    season_int = (
        int(season)
        if season and season.isdigit()
        else (
            prev["season"]
            if prev and prev.get("season")
            else 1 if media_type == "tv" else None
        )
    )
    episode_int = (
        int(episode)
        if episode and episode.isdigit()
        else (
            prev["episode"]
            if prev and prev.get("episode")
            else 1 if media_type == "tv" else None
        )
    )

    if media_type == "tv":
        iframe = f"https://vidsrc.icu/embed/tv/{id_}/{season_int}/{episode_int}"
    else:
        iframe = f"https://vidsrc.icu/embed/movie/{id_}"
        # Save new progress

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
    return jsonify(load_history())


@app.route("/api/update_progress", methods=["POST"])
def update_progress():
    data = request.json
    if not data:
        return jsonify({"error": "No data"}), 400

    history = load_history()
    # Remove old entry
    history = [
        h for h in history if not (h["id"] == data["id"] and h["type"] == data["type"])
    ]
    # Add updated entry at the front
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
