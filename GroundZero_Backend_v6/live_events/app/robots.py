from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
import httpx

def allowed_by_robots(url: str, user_agent: str, timeout: float) -> bool:
    p = urlparse(url)
    robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
    rp = RobotFileParser()
    try:
        r = httpx.get(robots_url, headers={"User-Agent": user_agent}, timeout=timeout, follow_redirects=True)
        if r.status_code >= 400:
            return True
        rp.parse(r.text.splitlines())
        return rp.can_fetch(user_agent, url)
    except Exception:
        return False
