"""Tests ke chhote helper functions."""
import json


def make_pdf(text: str) -> bytes:
    """Ek chhoti, asli PDF banata hai (ek page, ek line text). text mein ( ) \\ nahi hone chahiye."""
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
    ]
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET"
    objects.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
    objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode()
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF"
    ).encode()
    return out


def parse_stream(response) -> list[dict]:
    """NDJSON response ko events ki list mein badalta hai."""
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def upload(client, headers, filename: str, content: bytes, mime: str = "text/plain"):
    return client.post(
        "/api/documents", headers=headers, files={"file": (filename, content, mime)}
    )
