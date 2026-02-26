<div align="center">

# vidsrc
### *Personal Movie & TV Show Streaming Interface*

<p><em>Search, track, and watch movies and TV shows — all in one place</em></p>

![Status](https://img.shields.io/badge/status-operational-success?style=flat)
![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.x-000000?style=flat&logo=flask&logoColor=white)
![Vercel](https://img.shields.io/badge/Deployed-Vercel-000000?style=flat&logo=vercel&logoColor=white)

<p><em>Built with the tools and technologies:</em></p>

![HTML](https://img.shields.io/badge/HTML5-Templates-E34F26?style=flat&logo=html5&logoColor=white)
![CSS](https://img.shields.io/badge/CSS3-Custom-1572B6?style=flat&logo=css3&logoColor=white)
![Bootstrap](https://img.shields.io/badge/Bootstrap-5.3-7952B3?style=flat&logo=bootstrap&logoColor=white)
![JavaScript](https://img.shields.io/badge/JavaScript-Vanilla-F7DF1E?style=flat&logo=javascript&logoColor=black)
![Google Sheets](https://img.shields.io/badge/Google_Sheets-Storage-34A853?style=flat&logo=google-sheets&logoColor=white)
![OMDB](https://img.shields.io/badge/OMDB-API-F5C518?style=flat)

**Live demo:** [vidsrc-iota-seven.vercel.app](https://vidsrc-iota-seven.vercel.app)

</div>

---

## Table of Contents

- [About the Project](#about-the-project)
- [Features](#features)
- [Architecture](#architecture)
- [Data Storage](#data-storage)
- [Installation](#installation)
- [Configuration](#configuration)
- [Project Structure](#project-structure)
- [API Reference](#api-reference)

---

## About the Project

A lightweight personal web application to search, browse, and watch movies and TV shows using the [vidsrc.to](https://vidsrc.to) embed player. The app supports multiple user profiles, watch history tracking, and avatar customization — all stored in Google Sheets (no database required).

---

## Features

### Multi-Profile System
- Account selection on a Netflix-style login screen
- Each account gets its own Google Sheets worksheet
- Custom avatar selection via DiceBear API (pixel-art, adventurer, lorelei styles)
- Automatic account and worksheet creation on first login

### Search & Discovery
- Search movies and TV shows by title
- Filter by type (Movie / TV Series)
- Results displayed as a poster grid with hover overlay
- Fetches metadata via OMDB API (title, year, genre, plot, IMDb rating, poster)
- Falls back to IMDb scraping if OMDB is unavailable

### Watch History
- "Continue Watching" row on the homepage (up to 12 entries)
- Remembers season and episode progress for TV shows
- Posters fetched and cached asynchronously to avoid blocking the UI
- Deduplication: same title only appears once, updated with latest progress

### Player
- Embedded player via `vidsrc.to` or `vidsrc.icu` (switchable)
- TV show controls: season/episode inputs, Next Episode, Next Season buttons
- Progress automatically saved on navigation

### Design
- Dark space-themed UI (`#0a0e27` background, indigo accent)
- Fully responsive — works on mobile and desktop
- Custom scrollbar, smooth hover transitions, loading spinners

---

## Architecture

```
┌─────────────────────────────────────────────┐
│              Browser (Client)               │
│                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │  Login   │  │  Search  │  │  Player  │   │
│  │  Page    │  │  + Grid  │  │  + Nav   │   │
│  └──────────┘  └──────────┘  └──────────┘   │
└──────────────────────┬──────────────────────┘
                       │ HTTP / Fetch API
                       ▼
┌─────────────────────────────────────────────┐
│            Flask Backend (Python)           │
│                                             │
│  Routes:                                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │  /login  │  │  /search │  │  /player │   │
│  │  /logout │  │ /api/... │  │          │   │
│  └──────────┘  └──────────┘  └──────────┘   │
│                                             │
│  Services:                                  │
│  ┌──────────────┐  ┌──────────────────────┐ │
│  │  OMDB / IMDb │  │  gspread (Sheets IO) │ │
│  │  (metadata)  │  │  DiceBear (avatars)  │ │
│  └──────────────┘  └──────────────────────┘ │
└──────────────────────┬──────────────────────┘
                       │ Google Sheets API
                       ▼
┌─────────────────────────────────────────────┐
│           Google Sheets (Storage)           │
│                                             │
│  ┌──────────────┐  ┌───────────────────┐    │
│  │  [account1]  │  │  [account2]  ...  │    │
│  │  title       │  │  title            │    │
│  │  id          │  │  id               │    │
│  │  type        │  │  type             │    │
│  │  season      │  │  season           │    │
│  │  episode     │  │  episode          │    │
│  │  poster      │  │  poster           │    │
│  │  timestamp   │  │  timestamp        │    │
│  └──────────────┘  └───────────────────┘    │
│                                             │
│  ┌──────────────────────────────────────┐   │
│  │  [avatars]                           │   │
│  │  account | avatar_url | avatar_seed  │   │
│  └──────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│              External Embeds                │
│                                             │
│  ┌─────────────┐        ┌─────────────┐     │
│  │  vidsrc.to  │   or   │  vidsrc.icu │     │
│  └─────────────┘        └─────────────┘     │
└─────────────────────────────────────────────┘
```

---

## Data Storage

This project uses **Google Sheets as a zero-cost database**. No SQL or NoSQL database is needed.

Each user account corresponds to a worksheet tab. The `avatars` worksheet stores avatar URLs for the login screen. A maximum of 12 history entries are kept per account (oldest are automatically dropped).

---

## Installation

### Prerequisites
- Python 3.11+
- A Google Cloud project with the Sheets API enabled
- A `credentials.json` service account file
- An OMDB API key (free at [omdbapi.com](https://www.omdbapi.com/apikey.aspx))

### Setup

```bash
git clone https://github.com/le-skal/vidsrc
cd vidsrc
pip install -r requirements.txt
```

Create a `.env` file at the root (see [Configuration](#configuration)).

```bash
python app.py
```

The app will be available at `http://localhost:5000`.

---

## Configuration

Create a `.env` file with the following variables:

```env
FLASK_SECRET_KEY=your_secret_key_here
OMDB_API_KEY=your_omdb_api_key
GOOGLE_CREDS={"type":"service_account","project_id":"..."}  # full JSON as string
```

The `GOOGLE_CREDS` value is the contents of your Google service account `credentials.json`, serialized as a single-line JSON string. The service account must have editor access to the target spreadsheet.

Update the `SHEET_ID` constant in `app.py` to point to your own Google Sheet.

---

## Project Structure

```
vidsrc/
├── app.py                  # Main Flask application
├── requirements.txt
├── .gitignore
├── static/
│   ├── index.css           # Main page styles
│   ├── login.css           # Login / account selector styles
│   ├── player.css          # Player page styles
│   └── select_avatar.css   # Avatar selection styles
└── templates/
    ├── index.html          # Home: continue watching + search
    ├── login.html          # Account selector
    ├── player.html         # Embedded player + TV controls
    ├── select_avatar.html  # Avatar picker (new accounts)
    └── test_player.html    # Minimal iframe debug page
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Home page (requires session) |
| `GET/POST` | `/login` | Account selector / creation |
| `GET` | `/logout` | Clear session |
| `GET` | `/player` | Embedded player with controls |
| `POST` | `/search` | Search movies & shows (JSON) |
| `GET` | `/api/details/<imdb_id>` | Fetch full OMDB metadata |
| `GET` | `/api/history` | Get current user's watch history |
| `POST` | `/api/update_progress` | Update season/episode progress |
| `POST` | `/api/update_poster` | Update poster for a history item |
| `POST` | `/api/avatar` | Save selected avatar |
| `GET` | `/api/random_avatars` | Get 4 random DiceBear avatars |
| `GET` | `/select_avatar` | Avatar selection page |
