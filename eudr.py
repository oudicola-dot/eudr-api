import uuid

# ----------------------------
# SIMPLE IN-MEMORY REGISTRY
# ----------------------------

AUDITS = {}


# ----------------------------
# RISK ENGINE (MVP LEGAL SAFE)
# ----------------------------

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


# ----------------------------
# CREATE AUDIT
# ----------------------------

def create_audit(api_key: str, expected_key: str, name: str, lat: float, lon: float):

    if api_key != expected_key:
        return None, "INVALID_API_KEY"

    audit_id = str(uuid.uuid4())

    risk_score, risk_level = compute_risk(lat, lon)

    audit = {
        "audit_id": audit_id,
        "farm_name": name,
        "latitude": lat,
        "longitude": lon,

        "risk_score": risk_score,
        "risk_level": risk_level,

        "status": "PRELIMINARY RECORD",
        "issuer": "Tierras de Montaña",

        # SaaS links (filled later in main.py)
        "verify_url": None,
        "pdf_url": None,
    }

    AUDITS[audit_id] = audit

    return audit, None


# ----------------------------
# GET AUDIT
# ----------------------------

def get_audit(audit_id: str):

    return AUDITS.get(audit_id)


# ----------------------------
# LIST (OPTION DEBUG)
# ----------------------------

def list_audits():

    return AUDITS
