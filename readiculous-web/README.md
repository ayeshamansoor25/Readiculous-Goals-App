# Readiculous Goals (Flask + MySQL)
TBR web app: user accounts, book catalog (admin CRUD + search), personal TBR list + yearly reading goal.

Default admin: `admin` / `admin123` (change after first login/deploy).

## Run locally
1. Install MySQL, then run `schema.sql` (or let the app create tables on startup)
2. `python -m venv venv` and activate it
3. `pip install -r requirements.txt`
4. copy `.env.example` to `.env` and set your DB credentials
5. `python application.py` -> http://localhost:5000
Health check: `/health`
