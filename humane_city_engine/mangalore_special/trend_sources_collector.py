"""
Mangalore Trend Source Collector

Collects trending tourism signals from:
- YouTube Data API
- RSS Feeds
- Blog sources

Outputs:
data_core/mangalore_trends.json
"""

import requests
import json
import feedparser
from datetime import datetime
from pathlib import Path

# ----------------------------
# CONFIG
# ----------------------------

YOUTUBE_API_KEY = "YOUR_YOUTUBE_API_KEY"

SEARCH_QUERIES = [
    "Mangalore food",
    "Mangalore street food",
    "Mangalore travel guide",
    "best restaurants in Mangalore"
]

RSS_FEEDS = [
    "https://timesofindia.indiatimes.com/rssfeeds/-2128838597.cms",
    "https://www.thehindu.com/feeder/default.rss",
]

OUTPUT_FILE = "data_core/mangalore_trends.json"


# ----------------------------
# YOUTUBE TREND COLLECTOR
# ----------------------------

def fetch_youtube_trends():

    print("Collecting YouTube trends...")

    trends = []

    for query in SEARCH_QUERIES:

        url = "https://www.googleapis.com/youtube/v3/search"

        params = {
            "part": "snippet",
            "q": query,
            "maxResults": 10,
            "key": YOUTUBE_API_KEY,
            "type": "video"
        }

        try:

            r = requests.get(url, params=params)

            data = r.json()

            for item in data.get("items", []):

                snippet = item["snippet"]

                trends.append({
                    "title": snippet["title"],
                    "channel": snippet["channelTitle"],
                    "published": snippet["publishedAt"]
                })

        except Exception as e:

            print("YouTube API error:", e)

    return trends


# ----------------------------
# RSS TREND COLLECTOR
# ----------------------------

def fetch_rss_trends():

    print("Collecting news/blog trends...")

    rss_items = []

    for url in RSS_FEEDS:

        feed = feedparser.parse(url)

        for entry in feed.entries[:10]:

            rss_items.append({
                "title": entry.title,
                "link": entry.link,
                "published": entry.published
            })

    return rss_items


# ----------------------------
# BUILD TREND DATASET
# ----------------------------

def build_trend_dataset():

    dataset = {
        "generated_at": datetime.utcnow().isoformat(),
        "youtube_trends": [],
        "rss_trends": []
    }

    dataset["youtube_trends"] = fetch_youtube_trends()
    dataset["rss_trends"] = fetch_rss_trends()

    Path("data_core").mkdir(exist_ok=True)

    with open(OUTPUT_FILE, "w", encoding="utf8") as f:

        json.dump(dataset, f, indent=4)

    print("Trend dataset created:", OUTPUT_FILE)


# ----------------------------
# MAIN
# ----------------------------

if __name__ == "__main__":

    build_trend_dataset()