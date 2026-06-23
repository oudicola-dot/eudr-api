import os
import hashlib
import qrcode
import requests

from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image,
    Table,
    TableStyle,
    PageBreak
)

from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

from security import sign_audit

BASE_URL = os.getenv(
    "BASE_URL",
    "https://eudr-api-mi0x.onrender.com"
)

LOGO_URL = "https://tierrasdemontana.com/wp-content/uploads/2021/03/TDM-L.png"


def get_logo():

    path = "/tmp/tdm_logo.png"

    if not os.path.exists(path):

        try:

            print("DOWNLOADING LOGO...")

            r = requests.get(
                LOGO_URL,
                timeout=8
            )

            r.raise_for_status()

            with open(path, "wb") as f:
                f.write(r.content)

            print("LOGO SAVED:", path)

        except Exception as e:

            print("LOGO DOWNLOAD ERROR:", str(e))
            return None

    return path


def generate_eudr_pdf(
    audit_id,
    name,
    lat,
    lon,
    risk_score,
    risk_level,
    eudr_compliant,
    tree_cover,
    loss_year
):

    print("================================")
    print("PDF GENERATION START")
    print("AUDIT:", audit_id)
    print("FARM:", name)
    print("================================")

    file_path = f"/tmp/{audit_id}.pdf"

    print("TARGET FILE:", file_path)

    doc = SimpleDocTemplate(file_path)

    styles = getSampleStyleSheet()

    content = []

    content.append(Spacer(1, 40))

    content.append(
        Paragraph(
            "<b>TIERRAS DE MONTAÑA</b>",
            styles["Title"]
        )
    )

    content.append(
        Paragraph(
            "EUDR TRACEABILITY REPORT",
            styles["Heading2"]
        )
    )

    content.append(Spacer(1, 20))

    logo = get_logo()

    print("LOGO PATH:", logo)

    if logo:

        try:

            content.append(
                Image(
                    logo,
                    width=160,
                    height=80
                )
            )

            print("LOGO LOADED")

        except Exception as e:

            print("LOGO ERROR:", str(e))

    content.append(Spacer(1, 25))

    content.append(
        Paragraph(
            f"<b>Audit ID:</b> {audit_id}",
            styles["Normal"]
        )
    )

    content.append(
        Paragraph(
            f"<b>EUDR Status:</b> {eudr_compliant}",
            styles["Normal"]
        )
    )

    content.append(PageBreak())

    signature = sign_audit(audit_id)

    verify_url = (
        f"{BASE_URL}/eudr/verify/"
        f"{audit_id}?signature={signature}"
    )

    print("VERIFY URL:", verify_url)

    qr = qrcode.make(verify_url)

    qr_path = f"/tmp/{audit_id}_qr.png"

    qr.save(qr_path)

    print("QR SAVED:", qr_path)

    sha = hashlib.sha256(
        f"{audit_id}{name}{lat}{lon}".encode()
    ).hexdigest()

    content.append(
        Paragraph(
            "EXECUTIVE SUMMARY",
            styles["Heading1"]
        )
    )

    content.append(Spacer(1, 10))

    content.append(
        Paragraph(
            f"<b>Farm:</b> {name}",
            styles["Normal"]
        )
    )

    content.append(
        Paragraph(
            f"<b>Latitude:</b> {lat}",
            styles["Normal"]
        )
    )

    content.append(
        Paragraph(
            f"<b>Longitude:</b> {lon}",
            styles["Normal"]
        )
    )

    content.append(
        Paragraph(
            f"<b>Tree Cover:</b> {tree_cover}%",
            styles["Normal"]
        )
    )

    content.append(
        Paragraph(
            f"<b>Loss Year:</b> {loss_year if loss_year > 0 else 'N/A'}",
            styles["Normal"]
        )
    )

    content.append(Spacer(1, 20))

    table = Table([
        ["Risk Score", risk_score],
        ["Risk Level", risk_level],
        ["EUDR Status", eudr_compliant],
        ["Issuer", "Tierras de Montaña"]
    ])

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#1f2937")),
    ]))

    content.append(table)

    content.append(Spacer(1, 25))

    content.append(
        Paragraph(
            "VERIFY CERTIFICATE",
            styles["Heading1"]
        )
    )

    content.append(Spacer(1, 10))

    try:

        content.append(
            Image(
                qr_path,
                width=150,
                height=150
            )
        )

        print("QR IMAGE LOADED")

    except Exception as e:

        print("QR IMAGE ERROR:", str(e))

    content.append(Spacer(1, 10))

    content.append(
        Paragraph(
            f"<b>Verification URL:</b> {verify_url}",
            styles["Normal"]
        )
    )

    content.append(Spacer(1, 15))

    content.append(
        Paragraph(
            f"<b>SHA256:</b> {sha}",
            styles["Normal"]
        )
    )

    print("BUILDING PDF...")

    doc.build(content)

    print("PDF BUILT")

    print(
        "FILE EXISTS:",
        os.path.exists(file_path)
    )

    try:

        os.remove(qr_path)

        print("QR CLEANED")

    except Exception as e:

        print("QR CLEANUP ERROR:", str(e))

    print("PDF RETURN:", file_path)

    return file_path
