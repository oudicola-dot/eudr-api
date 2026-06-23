import os
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from fastapi.responses import FileResponse

from eudr import create_audit, get_audit
from pdf_report import generate_eudr_pdf


# ---------------- APP ----------------

app = FastAPI(
    title="EUDR API",
    version="1.0"
)


# ---------------- CORS ----------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------- CONFIG ----------------

API_KEY = os.getenv("API_KEY", "EUDR-SECRET-123")

BASE_URL = os.getenv(
    "BASE_URL",
    "https://eudr-api-mi0x.onrender.com"
)


# ---------------- ROOT ----------------

@app.get("/")
def root():
    return {
        "status": "online",
        "service": "EUDR API",
        "version": "1.0"
    }


# ---------------- CHECK (CREATE AUDIT) ----------------

@app.post("/eudr-check")
def eudr_check(payload: dict):

    name = payload.get("name")
    lat = float(payload.get("lat"))
    lon = float(payload.get("lon"))

    audit, error = create_audit(
        api_key=payload.get("api_key"),
        expected_key=API_KEY,
        name=name,
        lat=lat,
        lon=lon
    )

    if error:
        raise HTTPException(status_code=401, detail=error)

    audit_id = audit["audit_id"]

    # build links
    audit["verify_url"] = f"{BASE_URL}/eudr/verify/{audit_id}"
    audit["pdf_url"] = f"{BASE_URL}/download/{audit_id}"

    return audit


# ---------------- VERIFY ----------------

@app.get("/eudr/verify/{audit_id}")
def verify(audit_id: str):

    audit = get_audit(audit_id)

    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    return {
        "audit_id": audit_id,
        "farm_name": audit["farm_name"],
        "risk_level": audit["risk_level"],
        "risk_score": audit["risk_score"],
        "status": audit["status"],
        "issuer": "Tierras de Montaña",
        "message": "EUDR PRELIMINARY AUDIT RECORD"
    }


# ---------------- PDF GENERATION ----------------

@app.post("/eudr-pdf")
def eudr_pdf(payload: dict):

    name = payload.get("name")
    lat = float(payload.get("lat"))
    lon = float(payload.get("lon"))

    audit, error = create_audit(
        api_key=payload.get("api_key"),
        expected_key=API_KEY,
        name=name,
        lat=lat,
        lon=lon
    )

    if error:
        raise HTTPException(status_code=401, detail=error)

    audit_id = audit["audit_id"]

    file_path = generate_eudr_pdf(
        audit_id=audit_id,
        name=name,
        lat=lat,
        lon=lon
    )

    return {
        "audit_id": audit_id,
        "pdf_url": f"{BASE_URL}/download/{audit_id}",
        "verify_url": f"{BASE_URL}/eudr/verify/{audit_id}"
    }


# ---------------- DOWNLOAD PDF ----------------

@app.get("/download/{audit_id}")
def download(audit_id: str):

    file_path = f"/tmp/{audit_id}.pdf"

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="PDF not found")

    return FileResponse(
        file_path,
        media_type="application/pdf",
        filename=f"EUDR_{audit_id}.pdf"
    )
