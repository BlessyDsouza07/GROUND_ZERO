import httpx
from urllib.parse import urlparse
from ..config import REQUEST_TIMEOUT_SECONDS, USER_AGENT
from ..robots import allowed_by_robots
from ..parser import parse_jsonld, discover_links

class StAloysiusAdapter:
    def __init__(self, base_url):
        self.base_url = base_url

    def collect(self):
        headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
        if not allowed_by_robots(self.base_url, USER_AGENT, REQUEST_TIMEOUT_SECONDS):
            raise RuntimeError("robots.txt does not permit collection of the configured source")
        seen = set()
        pages = [self.base_url]
        events = []
        with httpx.Client(headers=headers, timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=True) as c:
            while pages and len(seen) < 81:
                url = pages.pop(0)
                if url in seen:
                    continue
                seen.add(url)
                if not allowed_by_robots(url, USER_AGENT, REQUEST_TIMEOUT_SECONDS):
                    continue
                r = c.get(url)
                r.raise_for_status()
                events.extend(parse_jsonld(r.text, str(r.url)))
                if url == self.base_url:
                    pages.extend(discover_links(r.text, str(r.url), urlparse(str(r.url)).netloc))
        # Deduplicate within this collection by source key + title/date.
        uniq = {}
        for e in events:
            key = (e["source_event_key"], e["title"], str(e["start_at"]))
            uniq[key] = e
        return list(uniq.values())
