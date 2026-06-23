import os
import hashlib
import qrcode

from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image,
    Table,
    TableStyle
)

from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors


# ----------------------------
# CONFIG
# ----------------------------

BASE_URL = os.getenv(
    "BASE_URL",
    "https://eudr-api-mi0x.onrender.com"
)

LOGO_URL = "https://tierrasdemontana.com/wp-content/uploads/2021/03/TDM-L.png"


# ----------------------------
# PDF GENERATOR PREMIUM
# ----------------------------

def generate_eudr_pdf(audit_id, name, lat, lon):

    file_path = f"/tmp/{audit_id}.pdf"

    doc = SimpleDocTemplate(file_path)
    styles = getSampleStyleSheet()

    verify_url = f"{BASE_URL}/eudr/verify/{audit_id}"

    # ---------------- QR CODE ----------------

    qr = qrcode.make(verify_url)
    qr_path = f"/tmp/{audit_id}_qr.png"
    qr.save(qr_path)

    # ---------------- SHA256 ----------------

    sha = hashlib.sha256(
        f"{audit_id}{name}{lat}{lon}".encode()
    ).hexdigest()

    # ---------------- CONTENT ----------------

    content = []

    # TITLE
    content.append(
        Paragraph(
            "EUDR PRELIMINARY COMPLIANCE REPORT",
            styles["Title"]
        )
    )

    content.append(Spacer(1, 12))

    # HEADER INFO TABLE (PRO LOOK)
    data = [
        ["Audit ID", audit_id],
        ["Farm", name],
        ["Latitude", str(lat)],
        ["Longitude", str(lon)],
        ["Status", "PRELIMINARY RECORD"],
        ["Issuer", "Tierras de Montaña"],
    ]

    table = Table(data, colWidths=[120, 300])

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#111827")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))

    content.append(table)

    content.append(Spacer(1, 20))

    # SHA
    content.append(
        Paragraph(
            f"<b>Security Hash (SHA-256):</b><br/>{sha}",
            styles["Normal"]
        )
    )

    content.append(Spacer(1, 20))

    # QR CODE
    content.append(
        Image(qr_path, width=160, height=160)
    )

    content.append(Spacer(1, 10))

    content.append(
        Paragraph(
            f"Verification URL: {verify_url}",
            styles["Normal"]
        )
    )

    content.append(Spacer(1, 20))

    # WATERMARK STYLE TEXT
    content.append(
        Paragraph(
            "<b>DISCLAIMER:</b> This document is a PRELIMINARY EUDR assessment generated from geolocation inputs. "
            "It does not constitute an official regulatory compliance certification under EU Regulation.",
            styles["Normal"]
        )
    )

    content.append(Spacer(1, 12))

    # FOOTER
    content.append(
        Paragraph(
            "Tierras de Montaña | Digital Traceability System | EU EUDR Support Tool",
            styles["Normal"]
        )
    )

    # BUILD PDF
    doc.build(content)

    # cleanup QR
    try:
        os.remove(qr_path)
    except:
        pass

    return file_path
