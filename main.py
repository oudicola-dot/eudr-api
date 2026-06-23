from fastapi import FastAPI
from pydantic import BaseModel
import ee
import os

from pdf_report import generate_eudr_pdf

app = FastAPI()

# =====================
# CONFIG
# =====================

API_KEY = os.getenv("API_KEY", "EUDR-SECRET-123")
EE_PROJECT = os.getenv("EE_PROJECT", None)

# =====================
# EARTH ENGINE INIT SAFE
# =====================

try:
    if EE_PROJECT:
        ee.Initialize(project=EE_PROJECT)
    else:
        ee.Initialize()
except Exception as e:
    print("EE INIT ERROR:", e)

# =====================
# INPUT MODEL
# =====================

class Request(BaseModel):
    api_key: str
    name: str
    lat: float
    lon: float

# =====================
# SIMPLE SAT ANALYSIS
# =====================

def compute_risk(lat, lon):

    point = ee.Geometry.Point([lon, lat])

    image = ee.Image("UMD/hansen/global_forest_change_2025_v1_13")

    forest = image.select("treecover2000").reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=point,
        scale=30
    ).get("treecover2000")

    loss = image.select("loss").reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=point,
        scale=30
    ).get("loss")

    forest_val = forest.getInfo() if forest else 0
    loss_val = loss.getInfo() if loss else 0

    risk = "COMPLIANT" if loss_val == 0 else "NON_COMPLIANT"

    return {
        "forest_cover": forest_val,
        "post_2020_deforestation": loss_val,
        "risk": risk,
        "score": float(loss_val or 0)
    }

# =====================
# API CHECK
# =====================

@app.post("/eudr-check")
def eudr_check(req: Request):

    if req.api_key != API_KEY:
        return {"error": "unauthorized"}

    result = compute_risk(req.lat, req.lon)

    return {
        "name": req.name,
        "lat": req.lat,
        "lon": req.lon,
        **result
    }

# =====================
# PDF ENDPOINT
# =====================

@app.post("/eudr-pdf")
def eudr_pdf(req: Request):

    if req.api_key != API_KEY:
        return {"error": "unauthorized"}

    result = compute_risk(req.lat, req.lon)

    data = {
        "name": req.name,
        "lat": req.lat,
        "lon": req.lon,
        **result
    }

    file_path = generate_eudr_pdf(data)

    return {"pdf_url": file_path}
