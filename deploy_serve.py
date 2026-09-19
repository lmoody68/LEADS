"""LEADS deploy wrapper — serves the built frontend (single-origin) alongside the FastAPI /api app.
Run: uvicorn serve:app --host 127.0.0.1 --port 8010  (from /opt/leads, with venv active)."""
import os
from fastapi.staticfiles import StaticFiles
from app.main import app   # the existing FastAPI app (all /api routes already registered)

DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend_dist")
# Mount LAST so the explicit /api/* routes win; this serves index.html at "/" + assets.
if os.path.isdir(DIST):
    app.mount("/", StaticFiles(directory=DIST, html=True), name="spa")
