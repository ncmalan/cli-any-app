import io
import socket

import qrcode
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from cli_any_app.config import settings

router = APIRouter(prefix="/api", tags=["cert"])


def get_lan_addresses() -> list[dict]:
    """Return a list of LAN IP addresses with their interface names."""
    import netifaces
    results = []
    for iface in netifaces.interfaces():
        addrs = netifaces.ifaddresses(iface)
        if netifaces.AF_INET in addrs:
            for addr in addrs[netifaces.AF_INET]:
                ip = addr.get("addr", "")
                if ip and ip != "127.0.0.1" and not ip.startswith("169.254."):
                    results.append({"interface": iface, "ip": ip})
    return results


def _get_lan_addresses_fallback() -> list[dict]:
    """Fallback using stdlib if netifaces is not available."""
    results = []
    # Try the connect trick first to find the default route IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip:
            results.append({"interface": "default", "ip": ip})
    except Exception:
        pass
    # Also check getaddrinfo for additional interfaces
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip and ip != "127.0.0.1" and not ip.startswith("169.254."):
                if not any(r["ip"] == ip for r in results):
                    results.append({"interface": hostname, "ip": ip})
    except socket.gaierror:
        pass
    return results


def get_network_interfaces() -> list[dict]:
    try:
        return get_lan_addresses()
    except ImportError:
        return _get_lan_addresses_fallback()


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


@router.get("/network/interfaces")
async def list_network_interfaces():
    return get_network_interfaces()
