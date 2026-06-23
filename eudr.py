import uuid

# ----------------------------
# MEMORY REGISTRY (V1 SIMPLE)
# ----------------------------

AUDITS = {}


# ----------------------------
# RISK ENGINE (SIMPLE + STABLE)
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
# CREATE AUDIT (MAIN FUNCTION)
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
        "issuer": "Tierras de Montaña"
    }

    # STORE AUDIT (IMPORTANT)
    AUDITS[audit_id] = audit

    return audit, None


# ----------------------------
# GET ONE AUDIT
# ----------------------------

def get_audit(audit_id: str):

    return AUDITS.get(audit_id)


# ----------------------------
# CHECK EXISTENCE ONLY
# ----------------------------

def audit_exists(audit_id: str) -> bool:

    return audit_id in AUDITS


# ----------------------------
# DEBUG (OPTION)
# ----------------------------

def list_audits():

    return AUDITS
