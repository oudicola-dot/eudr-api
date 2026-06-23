import os
import pathlib

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from eudr import init_db, create_audit, get_audit
from eudr import verify_signature
from pdf_report import generate_eudr_pdf


# ----------------------------
# APP CONFIG
# ----------------------------

app = FastAPI(title="EUDR API - Tierras de Montaña", version="1.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


API_KEY = os.getenv("API_KEY", "CHANGE_ME")
BASE_URL = os.getenv("BASE_URL", "https://eudr-api-mi0x.onrender.com")


# ----------------------------
# INIT DB
# ----------------------------

init_db()


# ----------------------------
# ROOT
# ----------------------------

@app.get("/")
def root():
    return {
        "status": "online",
        "service": "EUDR API - Tierras de Montaña"
    }


# ----------------------------
# CREATE AUDIT
# ----------------------------

@app.post("/eudr-check")
def eudr_check(payload: dict):

    if payload.get("api_key") != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    name = payload.get("name")
    lat = float(payload.get("lat"))
    lon = float(payload.get("lon"))

    audit = create_audit(name, lat, lon)

    return audit


# ----------------------------
# GENERATE PDF
# ----------------------------

@app.post("/eudr-pdf")
def eudr_pdf(payload: dict):

    if payload.get("api_key") != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    audit_id = payload.get("audit_id")

    audit = get_audit(audit_id)

    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    file_path = generate_eudr_pdf(
        audit_id=audit_id,
        name=audit["farm_name"],
        lat=audit["latitude"],
        lon=audit["longitude"],
        risk_score=audit["risk_score"],
        risk_level=audit["risk_level"]
    )

    return {
        "audit_id": audit_id,
        "pdf_url": f"{BASE_URL}/download/{audit_id}",
        "verify_url": f"{BASE_URL}/eudr/verify/{audit_id}"
    }


# ----------------------------
# DOWNLOAD PDF
# ----------------------------

@app.get("/download/{audit_id}")
def download(audit_id: str):

    file_path = f"/tmp/{audit_id}.pdf"

    if not pathlib.Path(file_path).exists():
        raise HTTPException(
            status_code=404,
            detail="PDF not found"
        )

    return FileResponse(
        file_path,
        media_type="application/pdf",
        filename=f"EUDR_{audit_id}.pdf"
    )


# ----------------------------
# VERIFY (SECURE)
# ----------------------------

@app.get("/eudr/verify/{audit_id}")
def verify(audit_id: str, sig: str = None):

    audit = get_audit(audit_id)

    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    # 🔐 STEP 3 SECURITY CHECK
    if sig:
        if not verify_signature(audit_id, sig):
            raise HTTPException(status_code=403, detail="Invalid signature")

    return audit
