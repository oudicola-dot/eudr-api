import os
import pathlib

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from eudr import init_db, create_audit, get_audit
from pdf_report import generate_eudr_pdf

app = FastAPI(title="EUDR SaaS - Clean Flow", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = os.getenv("API_KEY", "CHANGE_ME")
BASE_URL = os.getenv("BASE_URL", "https://eudr-api-mi0x.onrender.com")

# INIT DB
init_db()


# ---------------- ROOT ----------------

@app.get("/")
def root():
    return {
        "status": "online",
        "service": "EUDR SaaS Clean Flow"
    }


# ---------------- CORE FLOW (SINGLE ENTRY) ----------------

@app.post("/eudr-check")
def eudr_check(payload: dict):

    if payload.get("api_key") != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    name = payload.get("name")
    lat = float(payload.get("lat"))
    lon = float(payload.get("lon"))

    # 1. CREATE AUDIT (DB)
    audit = create_audit(name, lat, lon)

    audit_id = audit["audit_id"]

    # 2. GENERATE PDF DIRECTLY (IMPORTANT FIX)
    file_path = generate_eudr_pdf(
        audit_id=audit_id,
        name=audit["farm_name"],
        lat=audit["latitude"],
        lon=audit["longitude"],
        risk_score=audit["risk_score"],
        risk_level=audit["risk_level"]
    )

    # 3. VERIFY + PDF LINKS
    verify_url = f"{BASE_URL}/eudr/verify/{audit_id}"
    pdf_url = f"{BASE_URL}/download/{audit_id}"

    return {
        **audit,
        "verify_url": verify_url,
        "pdf_url": pdf_url
    }


# ---------------- VERIFY ----------------

@app.get("/eudr/verify/{audit_id}")
def verify(audit_id: str):

    audit = get_audit(audit_id)

    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    return audit


# ---------------- DOWNLOAD PDF ----------------

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
