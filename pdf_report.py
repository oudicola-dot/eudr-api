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
            r = requests.get(LOGO_URL, timeout=8)
            r.raise_for_status()

            with open(path, "wb") as f:
                f.write(r.content)

            print("LOGO SAVED:", path)

        except Exception as e:
            print("LOGO DOWNLOAD ERROR:", str(e))
            return None

    return path


def get_source_label(source):
    """Convertit le code source en label lisible"""
    labels = {
        "ee": "🌍 Earth Engine",
        "gfw": "🛰️ GFW (Global Forest Watch)",
        "fallback": "⚠️ Simulation (Fallback)",
        "unknown": "❓ Unknown"
    }
    return labels.get(source, f"📡 {source}")


def generate_eudr_pdf(
    audit_id,
    name,
    lat,
    lon,
    risk_score,
    risk_level,
    eudr_compliant,
    tree_cover,
    loss_year,
    source="unknown"  # ← NOUVEAU PARAMÈTRE avec valeur par défaut
):
    print("================================")
    print("PDF GENERATION START")
    print("AUDIT:", audit_id)
    print("FARM:", name)
    print("SOURCE:", source)
    print("================================")

    file_path = f"/tmp/{audit_id}.pdf"
    print("TARGET FILE:", file_path)

    doc = SimpleDocTemplate(file_path)
    styles = getSampleStyleSheet()
    content = []

    # ===== PAGE DE GARDE =====
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

    # Logo
    logo = get_logo()
    print("LOGO PATH:", logo)

    if logo:
        try:
            content.append(
                Image(
                    logo,
                    width=150,
                    height=121
                )
            )
            print("LOGO LOADED")
        except Exception as e:
            print("LOGO ERROR:", str(e))

    content.append(Spacer(1, 25))

    # Audit ID et Status
    content.append(
        Paragraph(
            f"<b>Audit ID:</b> {audit_id}",
            styles["Normal"]
        )
    )

    # ✅ Statut avec couleur
    status_color = "#00ff99" if eudr_compliant == "COMPLIANT" else "#ff4444"
    content.append(
        Paragraph(
            f'<b>EUDR Status:</b> <font color="{status_color}">{eudr_compliant}</font>',
            styles["Normal"]
        )
    )

    # ✅ Ajout de la Data Source sur la page de garde
    source_label = get_source_label(source)
    content.append(
        Paragraph(
            f"<b>Data Source:</b> {source_label}",
            styles["Normal"]
        )
    )

    content.append(PageBreak())

    # ===== PAGE DÉTAILLÉE =====
    signature = sign_audit(audit_id)

    verify_url = (
        f"{BASE_URL}/eudr/verify/"
        f"{audit_id}?signature={signature}"
    )

    print("VERIFY URL:", verify_url)

    # QR Code
    qr = qrcode.make(verify_url)
    qr_path = f"/tmp/{audit_id}_qr.png"
    qr.save(qr_path)
    print("QR SAVED:", qr_path)

    # SHA256
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

    # Informations détaillées
    details = [
        ["Farm", name],
        ["Latitude", f"{lat:.6f}"],
        ["Longitude", f"{lon:.6f}"],
        ["Tree Cover", f"{tree_cover}%"],
        ["Loss Year", str(loss_year) if loss_year > 0 else "N/A"],
        ["Data Source", source_label],  # ✅ Ajouté ici aussi
        ["Risk Score", str(risk_score)],
        ["Risk Level", risk_level],
        ["EUDR Status", eudr_compliant],
        ["Issuer", "Tierras de Montaña"]
    ]

    # Tableau stylisé
    table_data = [[Paragraph(f"<b>{k}</b>", styles["Normal"]), v] for k, v in details]
    table = Table(table_data, colWidths=[150, 300])
    
    table.setStyle(TableStyle([
        # En-tête
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#1a2332")),
        ("BACKGROUND", (1, 0), (1, -1), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("ALIGN", (0, 0), (0, -1), "RIGHT"),
        ("ALIGN", (1, 0), (1, -1), "LEFT"),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        # Gris clair pour les lignes paires
        ("BACKGROUND", (1, 0), (1, -1), colors.HexColor("#1a2332")),
    ]))

    content.append(table)

    content.append(Spacer(1, 25))

    # ===== PAGE DE VÉRIFICATION =====
    content.append(
        Paragraph(
            "VERIFY CERTIFICATE",
            styles["Heading1"]
        )
    )

    content.append(Spacer(1, 10))

    # QR Code
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

    # ✅ Ajout d'un badge Data Source
    content.append(Spacer(1, 20))
    
    source_badge = f"📊 Data Source: {source_label}"
    content.append(
        Paragraph(
            f'<font color="#00ff99"><b>{source_badge}</b></font>',
            styles["Normal"]
        )
    )

    # ===== GÉNÉRATION =====
    print("BUILDING PDF...")
    doc.build(content)
    print("PDF BUILT")

    print("FILE EXISTS:", os.path.exists(file_path))

    # Nettoyage
    try:
        os.remove(qr_path)
        print("QR CLEANED")
    except Exception as e:
        print("QR CLEANUP ERROR:", str(e))

    print("PDF RETURN:", file_path)
    return file_path
