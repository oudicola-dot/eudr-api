from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import uuid

def generate_eudr_pdf(data):

    file_name = f"EUDR_CERT_{uuid.uuid4().hex[:8]}.pdf"
    file_path = f"./{file_name}"

    doc = SimpleDocTemplate(file_path)
    styles = getSampleStyleSheet()

    content = []

    content.append(
        Paragraph(
            "EUDR DUE DILIGENCE STATEMENT",
            styles["Title"]
        )
    )

    content.append(Spacer(1,12))

    text = f"""
    Farm: {data['name']}<br/>
    Latitude: {data['lat']}<br/>
    Longitude: {data['lon']}<br/><br/>

    Forest cover (2000): {data['forest_cover']}<br/>
    Deforestation detected after 2020: {data['post_2020_deforestation']}<br/>
    Risk: {data['risk']}<br/>
    Score: {data['score']}<br/><br/>

    Regulation: EU 2023/1115 (EUDR)
    """

    content.append(
        Paragraph(text, styles["Normal"])
    )

    doc.build(content)

    return file_path
