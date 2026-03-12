import io

import qrcode
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from cli_any_app.config import settings

router = APIRouter(prefix="/api", tags=["cert"])


@router.get("/cert")
async def get_certificate():
    cert_path = settings.mitmproxy_ca_dir / "mitmproxy-ca-cert.pem"
    if not cert_path.exists():
        raise HTTPException(404, "mitmproxy CA certificate not found. Run mitmproxy once to generate it.")
    return FileResponse(cert_path, media_type="application/x-pem-file", filename="mitmproxy-ca-cert.pem")


@router.get("/cert/qr")
async def get_cert_qr():
    url = f"http://{settings.host}:{settings.port}/api/cert"
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")
