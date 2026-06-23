import os
import pathlib
import hashlib

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

from eudr import init_db, create_audit, get_audit
from pdf_report import generate_eudr_pdf


# ----------------------------
# APP
# ----------------------------

app = FastAPI(
    title="EUDR Enterprise Registry",
    version="2.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = os.getenv("API_KEY", "CHANGE_ME")
BASE_URL = os.getenv("BASE_URL", "https://eudr-api-mi0x.onrender.com")

init_db()


# ----------------------------
# ROOT
# ----------------------------

@app.get("/")
def root():
    return {"status": "online", "service": "EUDR API"}


# ----------------------------
# CREATE AUDIT (ONLY ENTRY POINT)
# ----------------------------

@app.post("/eudr-check")
def eudr_check(payload: dict):

    if payload.get("api_key") != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    name = payload.get("name")
    lat = float(payload.get("lat"))
    lon = float(payload.get("lon"))

    audit = create_audit(name, lat, lon)
    audit_id = audit["audit_id"]

    # SHA256 fingerprint
    sha = hashlib.sha256(
        f"{audit_id}{name}{lat}{lon}".encode()
    ).hexdigest()

    audit["sha256"] = sha
    audit["verify_url"] = f"{BASE_URL}/audit/{audit_id}"
    audit["pdf_url"] = f"{BASE_URL}/download/{audit_id}"

    # Generate PDF immediately
    generate_eudr_pdf(
        audit_id=audit_id,
        name=name,
        lat=lat,
        lon=lon,
        risk_score=audit["risk_score"],
        risk_level=audit["risk_level"]
    )

    return audit


# ----------------------------
# PUBLIC AUDIT PAGE (HTML)
# ----------------------------

@app.get("/audit/{audit_id}", response_class=HTMLResponse)
def audit_page(audit_id: str):

    audit = get_audit(audit_id)

    if not audit:
        return HTMLResponse("<h1>Audit not found</h1>", status_code=404)

    sha = hashlib.sha256(
        f"{audit_id}{audit['farm_name']}{audit['latitude']}{audit['longitude']}".encode()
    ).hexdigest()

    return HTMLResponse(f"""
    <html>
    <body style="font-family:Arial;background:#0b1220;color:white;padding:40px;">
        <div style="background:#111a2e;padding:20px;border-radius:12px;max-width:600px;">
            <h2>🌿 EUDR Audit</h2>

            <p><b>ID:</b> {audit_id}</p>
            <p><b>Farm:</b> {audit['farm_name']}</p>
            <p><b>Lat:</b> {audit['latitude']}</p>
            <p><b>Lon:</b> {audit['longitude']}</p>

            <p><b>Risk:</b> {audit['risk_level']} ({audit['risk_score']})</p>

            <p style="color:#00ff99;"><b>Status:</b> PRELIMINARY RECORD</p>

            <hr>

            <p><b>SHA256:</b><br>{sha}</p>

            <a href="/download/{audit_id}" style="color:#00ff99">
                Download PDF
            </a>
        </div>
    </body>
    </html>
    """)


# ----------------------------
# DOWNLOAD PDF
# ----------------------------

@app.get("/download/{audit_id}")
def download(audit_id: str):

    file_path = f"/tmp/{audit_id}.pdf"

    if not pathlib.Path(file_path).exists():
        raise HTTPException(status_code=404, detail="PDF not found")

    return FileResponse(
        file_path,
        media_type="application/pdf",
        filename=f"EUDR_{audit_id}.pdf"
    )
