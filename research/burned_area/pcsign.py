"""Anonymous Planetary Computer SAS signing (same as planetary_computer.sign, no package)."""
import time, threading, httpx
from urllib.parse import urlparse
_cache: dict = {}
_lock = threading.Lock()
def sign(href: str) -> str:
    u = urlparse(href)
    if not u.netloc.endswith(".blob.core.windows.net"):
        return href
    acct = u.netloc.split(".")[0]; cont = u.path.lstrip("/").split("/")[0]
    with _lock:
        tok, exp = _cache.get((acct, cont), (None, 0))
        if time.time() > exp - 300:
            for i in range(5):
                r = httpx.get(f"https://planetarycomputer.microsoft.com/api/sas/v1/token/{acct}/{cont}", timeout=30)
                if r.status_code == 200: break
                time.sleep(2 * (i + 1))
            r.raise_for_status()
            tok = r.json()["token"]; exp = time.time() + 45 * 60
            _cache[(acct, cont)] = (tok, exp)
    return f"{href}?{tok}"
