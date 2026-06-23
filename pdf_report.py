import os
import hashlib
import qrcode

from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image
)

from reportlab.lib.styles import getSampleStyleSheet


def generate_eudr_pdf(audit_id, name, lat, lon, risk_level):

    file_path = f"/tmp/{audit_id}.pdf"
    qr_path = f"/tmp/{audit_id}_qr.png"

    doc = SimpleDocTemplate(file_path)
    styles = getSampleStyleSheet()

    # ---------------- VERIFY URL ----------------

    verify_url = f"https://eudr-api-mi0x.onrender.com/eudr/verify/{audit_id}"

    # ---------------- QR ----------------

    qr = qrcode.make(verify_url)
    qr.save(qr_path)

    # ---------------- HASH ----------------

    sha = hashlib.sha256(
        f"{audit_id}{name}{lat}{lon}".encode()
    ).hexdigest()

    # ---------------- PDF ----------------

    content = []

    content.append(Paragraph(
        "EUDR PRELIMINARY ASSESSMENT REPORT",
        styles["Title"]
    ))

    content.append(Spacer(1, 12))

    content.append(Paragraph(f"<b>Audit ID:</b> {audit_id}", styles["Normal"]))
    content.append(Paragraph(f"<b>Farm:</b> {name}", styles["Normal"]))
    content.append(Paragraph(f"<b>Latitude:</b> {lat}", styles["Normal"]))
    content.append(Paragraph(f"<b>Longitude:</b> {lon}", styles["Normal"]))
    content.append(Paragraph(f"<b>Risk Level:</b> {risk_level}", styles["Normal"]))

    content.append(Spacer(1, 12))

    content.append(Paragraph(f"<b>SHA256:</b> {sha}", styles["Normal"]))

    content.append(Spacer(1, 20))

    content.append(Image(qr_path, width=160, height=160))

    content.append(Spacer(1, 10))

    content.append(Paragraph(
        f"Verification URL: {verify_url}",
        styles["Normal"]
    ))

    content.append(Spacer(1, 20))

    content.append(Paragraph(
        "This document is a PRELIMINARY TECHNICAL ASSESSMENT and does not constitute official EUDR compliance certification.",
        styles["Normal"]
    ))

    doc.build(content)

    try:
        os.remove(qr_path)
    except:
        pass

    return file_path
