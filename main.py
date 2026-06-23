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
    return {
        "status": "online",
        "service": "EUDR Enterprise Registry"
    }


# ----------------------------
# CREATE AUDIT
# ----------------------------

@app.post("/eudr-check")
def eudr_check(payload: dict):

    if payload.get("api_key") != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    audit = create_audit(
        payload.get("name"),
        float(payload.get("lat")),
        float(payload.get("lon"))
    )

    audit_id = audit["audit_id"]

    # SHA256 fingerprint
    sha = hashlib.sha256(
        f"{audit_id}{audit['farm_name']}{audit['latitude']}{audit['longitude']}".encode()
    ).hexdigest()

    audit["sha256"] = sha
    audit["verify_url"] = f"{BASE_URL}/audit/{audit_id}"
    audit["pdf_url"] = f"{BASE_URL}/download/{audit_id}"

    # PDF generation (IMPORTANT: signature must match pdf_report.py)
    generate_eudr_pdf(
        audit_id=audit_id,
        name=audit["farm_name"],
        lat=audit["latitude"],
        lon=audit["longitude"],
        risk_score=audit["risk_score"],
        risk_level=audit["risk_level"]
    )

    return audit


# ----------------------------
# PUBLIC HTML PAGE
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
    <head>
        <title>EUDR Audit {audit_id}</title>
        <style>
            body {{
                font-family: Arial;
                background:#0b1220;
                color:white;
                padding:40px;
            }}
            .box {{
                background:#111a2e;
                padding:20px;
                border-radius:12px;
                max-width:600px;
            }}
            .ok {{ color:#00ff99; }}
        </style>
    </head>

    <body>
        <div class="box">
            <h2>🌿 EUDR Enterprise Audit</h2>

            <p><b>ID:</b> {audit_id}</p>
            <p><b>Farm:</b> {audit['farm_name']}</p>
            <p><b>Lat:</b> {audit['latitude']}</p>
            <p><b>Lon:</b> {audit['longitude']}</p>

            <p><b>Risk:</b> {audit['risk_level']} ({audit['risk_score']})</p>

            <p class="ok"><b>Status:</b> PRELIMINARY RECORD</p>

            <hr>

            <p><b>SHA256:</b><br>{sha}</p>

            <p>
                <a href="/download/{audit_id}" style="color:#00ff99">
                    Download PDF
                </a>
            </p>
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
