import os
import uuid
import json

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from pdf_report import generate_eudr_pdf

app = FastAPI(title="EUDR API", version="2.0")

# ---------------- CORS ----------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = os.getenv("API_KEY", "EUDR-SECRET-123")

REGISTRY_PATH = "/tmp/audits.json"


# ---------------- INIT REGISTRY ----------------

def load_registry():
    if not os.path.exists(REGISTRY_PATH):
        return {}
    with open(REGISTRY_PATH, "r") as f:
        return json.load(f)


def save_registry(data):
    with open(REGISTRY_PATH, "w") as f:
        json.dump(data, f)


# ---------------- ROOT ----------------

@app.get("/")
def root():
    return {
        "status": "online",
        "service": "EUDR API",
        "version": "2.0"
    }


# ---------------- RISK (MVP) ----------------

def compute_risk(lat: float, lon: float):
    seed = abs(int((lat * 1000) + (lon * 1000)))
    risk = seed % 100

    if risk < 30:
        level = "LOW"
    elif risk < 70:
        level = "MEDIUM"
    else:
        level = "HIGH"

    return risk, level


# ---------------- CHECK ----------------

@app.post("/eudr-check")
def eudr_check(payload: dict):

    if payload.get("api_key") != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    name = payload.get("name")
    lat = float(payload.get("lat"))
    lon = float(payload.get("lon"))

    risk_score, risk_level = compute_risk(lat, lon)

    audit_id = str(uuid.uuid4())

    registry = load_registry()

    registry[audit_id] = {
        "audit_id": audit_id,
        "farm_name": name,
        "lat": lat,
        "lon": lon,
        "risk_score": risk_score,
        "risk_level": risk_level
    }

    save_registry(registry)

    return registry[audit_id]


# ---------------- PDF ----------------

@app.post("/eudr-pdf")
def eudr_pdf(payload: dict):

    if payload.get("api_key") != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    audit_id = payload.get("audit_id")

    registry = load_registry()

    if audit_id not in registry:
        raise HTTPException(status_code=404, detail="Audit not found")

    audit = registry[audit_id]

    file_path = generate_eudr_pdf(
        audit_id=audit_id,
        name=audit["farm_name"],
        lat=audit["lat"],
        lon=audit["lon"],
    )

    return {
        "audit_id": audit_id,
        "pdf_url": f"https://eudr-api-mi0x.onrender.com/download/{audit_id}"
    }


# ---------------- DOWNLOAD ----------------

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


# ---------------- VERIFY ----------------

@app.get("/eudr/verify/{audit_id}")
def verify(audit_id: str):

    registry = load_registry()

    if audit_id not in registry:
        raise HTTPException(status_code=404, detail="Audit not found")

    return registry[audit_id]
