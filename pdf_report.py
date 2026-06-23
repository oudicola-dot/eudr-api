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


# Logo officiel TDM (remote -> on télécharge implicitement si Render supporte, sinon fallback conseillé local)
TDM_LOGO = "https://tierrasdemontana.com/wp-content/uploads/2021/03/TDM-L.png"


def generate_eudr_pdf(audit_id, name, lat, lon):

    file_path = f"/tmp/{audit_id}.pdf"
    qr_path = f"/tmp/{audit_id}_qr.png"

    doc = SimpleDocTemplate(file_path)
    styles = getSampleStyleSheet()

    # ---------------- VERIFY URL ----------------

    verify_url = f"https://eudr-api-mi0x.onrender.com/eudr/verify/{audit_id}"

    # ---------------- QR CODE ----------------

    qr = qrcode.make(verify_url)
    qr.save(qr_path)

    # ---------------- SHA256 ----------------

    sha = hashlib.sha256(
        f"{audit_id}{name}{lat}{lon}".encode()
    ).hexdigest()

    # ---------------- PDF CONTENT ----------------

    content = []

    # HEADER
    content.append(
        Paragraph(
            "🇪🇺 EUDR PRELIMINARY ASSESSMENT REPORT",
            styles["Title"]
        )
    )

    content.append(Spacer(1, 10))

    content.append(
        Paragraph(
            "<b>Tierras de Montaña - Compliance Intelligence Unit</b>",
            styles["Normal"]
        )
    )

    content.append(Spacer(1, 20))

    # ---------------- TABLE INFO CLEAN ----------------

    table_data = [
        ["Audit ID", audit_id],
        ["Farm Name", name],
        ["Latitude", str(lat)],
        ["Longitude", str(lon)],
        ["Status", "PRELIMINARY RECORD"],
    ]

    table = Table(table_data, colWidths=[120, 350])

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("BACKGROUND", (0, 1), (-1, -1), colors.black),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.white),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    content.append(table)

    content.append(Spacer(1, 20))

    # ---------------- HASH ----------------

    content.append(
        Paragraph(
            f"<b>Document SHA256:</b> {sha}",
            styles["Normal"]
        )
    )

    content.append(Spacer(1, 20))

    # ---------------- QR + VERIFY ----------------

    content.append(
        Paragraph(
            "<b>Verification QR Code</b>",
            styles["Heading2"]
        )
    )

    content.append(Image(qr_path, width=160, height=160))

    content.append(Spacer(1, 10))

    content.append(
        Paragraph(
            f"Verify online: {verify_url}",
            styles["Normal"]
        )
    )

    content.append(Spacer(1, 20))

    # ---------------- LEGAL DISCLAIMER ----------------

    content.append(
        Paragraph(
            "This document is a PRELIMINARY automated assessment generated from geolocation inputs. "
            "It does not constitute an official EUDR compliance certificate under EU Regulation (EU) 2023/1115.",
            styles["Normal"]
        )
    )

    # ---------------- BUILD PDF ----------------

    doc.build(content)

    # cleanup QR
    try:
        os.remove(qr_path)
    except:
        pass

    return file_path
