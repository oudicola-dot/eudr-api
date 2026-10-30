import os
import hmac
import hashlib

NEW_SECRET = os.getenv("API_SECRET")
LEGACY_SECRET = os.getenv("LEGACY_API_SECRET")

if not NEW_SECRET or len(NEW_SECRET) < 32:
    raise RuntimeError("CRITICAL: API_SECRET missing or too short (min 32 chars).")

if LEGACY_SECRET == "SUPER_SECRET_CHANGE_ME":
    print("⚠️ WARNING: Using compromised LEGACY_API_SECRET for old QR codes.")

def sign_audit(audit_id: str) -> str:
    return hmac.new(NEW_SECRET.encode(), audit_id.encode(), hashlib.sha256).hexdigest()

def verify_signature(audit_id: str, signature: str) -> bool:
    expected_new = hmac.new(NEW_SECRET.encode(), audit_id.encode(), hashlib.sha256).hexdigest()
    if hmac.compare_digest(expected_new, signature):
        return True
    
    if LEGACY_SECRET:
        expected_legacy = hmac.new(LEGACY_SECRET.encode(), audit_id.encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected_legacy, signature):
            return True
            
    return False
