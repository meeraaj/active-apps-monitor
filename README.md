# Active Apps Monitor

Full-stack app to download and parse logs from Azure Blob Storage, provide user/admin access, and display parsed results in a React UI.

## Features
- User auth with JWT (roles: user, admin).
- Admin: view parsed reports from extracted logs.
- User: view personal log submissions.
- Azure Blob download + unzip to local folders for parsing.
- SQLite persistence for users and log metadata.

## Prerequisites
- Python 3.12+ and Node 18+.
- Virtualenv set up at `venv/` (already present). If missing: `python -m venv venv`.
- Azure Blob credentials in `.env` (see below).

## Environment (.env)
```
AZURE_STORAGE_CONNECTION_STRING=...
AZURE_CONTAINER_NAME=appmonitor
SECRET_KEY=change_me
```

## Backend (Flask)
From repo root:
```bash
source venv/bin/activate
pip install -r requirements.txt
python server/app.py  # runs on http://127.0.0.1:5001
```

## Frontend (Vite + React)
```bash
cd frontend
npm install
npm run dev  # serves on http://localhost:4173
```

Proxy: frontend `/api/*` calls go to `http://127.0.0.1:5001` (see `frontend/vite.config.js`).

## Accounts
- Default admin (created at startup): `admin@monitor.com` / `admin123`
- Registration flow creates regular users (no UI toggle to register admins).
- Login page has a User/Admin toggle; the backend role on the JWT controls what you see.

## Data + Folders
- SQLite DB: `monitor.db`
- Downloaded zips: `server_downloads/`
- Extracted logs: `server_extracted_logs/`

## Log Parsing
- Text/log files and nested zips are scanned under `server_extracted_logs/`.
- Lines containing `ERROR` (case-insensitive) are marked as `Danger`; others as `Normal`.

## Troubleshooting
- If port 5001 is busy, stop other Flask instances (`lsof -i :5001`).
- If the frontend shows a blank page, hard refresh and check the browser console.
