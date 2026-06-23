import hmac
import hashlib
import os

SECRET = os.getenv("API_SECRET", "SUPER_SECRET_CHANGE_ME")


def sign_audit(audit_id: str) -> str:
    return hmac.new(
        SECRET.encode(),
        audit_id.encode(),
        hashlib.sha256
    ).hexdigest()


def verify_signature(audit_id: str, signature: str) -> bool:
    expected = sign_audit(audit_id)
    return hmac.compare_digest(expected, signature)
