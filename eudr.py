import uuid

AUDITS = {}

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


def create_audit(api_key_ok: bool, api_key: str, expected_key: str, name, lat, lon):

    if api_key != expected_key:
        return None, "INVALID_KEY"

    risk_score, risk_level = compute_risk(lat, lon)

    audit_id = str(uuid.uuid4())

    audit = {
        "audit_id": audit_id,
        "farm_name": name,
        "latitude": lat,
        "longitude": lon,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "status": "PRELIMINARY RECORD",
    }

    AUDITS[audit_id] = audit

    return audit, None


def get_audit(audit_id: str):
    return AUDITS.get(audit_id)
