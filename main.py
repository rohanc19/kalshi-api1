from flask import Flask, jsonify
import feedparser
import hashlib
import json
from datetime import datetime, timedelta
from cachetools import TTLCache
import google.generativeai as genai

app = Flask(__name__)
genai.configure(api_key="YOUR_GEMINI_API_KEY")

cache = TTLCache(maxsize=1, ttl=1800)

CATEGORY_TAGS = {
    "Politics": ["Politics", "Government", "Elections"],
    "Crypto": ["Crypto", "Currency", "Finance"],
    "Companies": ["Companies", "Business", "Startups"],
    "Economics": ["Economy", "Finance", "Markets"]
}

RSS_FEEDS = [
    {"url": "https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml", "category": "Politics"},
    {"url": "https://www.livemint.com/rss/politics", "category": "Politics"},
    {"url": "https://feeds.feedburner.com/ndtvnews-india-news", "category": "Politics"},
    {"url": "https://www.business-standard.com/rss/politics-155.rss", "category": "Politics"},
    {"url": "https://www.thehindu.com/news/national/?service=rss", "category": "Politics"},
    {"url": "https://cointelegraph.com/rss", "category": "Crypto"},
    {"url": "https://coingape.com/feed/", "category": "Crypto"},
    {"url": "https://www.bitcoinworld.co.in/feed/", "category": "Crypto"},
    {"url": "https://www.business-standard.com/rss/markets/cryptocurrency-10622.rss", "category": "Crypto"},
    {"url": "https://www.hindustantimes.com/feeds/rss/infographic/companies/rssfeed.xml", "category": "Companies"},
    {"url": "https://www.livemint.com/rss/industry", "category": "Companies"},
    {"url": "https://economictimes.indiatimes.com/industry/rssfeeds/13352306.cms", "category": "Companies"},
    {"url": "https://www.business-standard.com/rss/companies-101.rss", "category": "Companies"},
    {"url": "https://www.hindustantimes.com/feeds/rss/infographic/money/rssfeed.xml", "category": "Economics"},
    {"url": "https://www.livemint.com/rss/money", "category": "Economics"},
    {"url": "https://www.business-standard.com/rss/finance-103.rss", "category": "Economics"},
    {"url": "https://economictimes.indiatimes.com/wealth/rssfeeds/13359518.cms", "category": "Economics"},
]

def format_prompt(text):
    return (
        "From the news below, create a binary YES/NO prediction market question with a verifiable timeframe. "
        "Then provide a one-paragraph explanation that frames this event like a prediction Kalshi would list.\n\n"
        + text
    )

def extract_title_and_description(response_text):
    parts = response_text.strip().split("\n", 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    else:
        return response_text[:80] + "?", response_text

def generate_kalshi_cards():
    model = genai.GenerativeModel("gemini-1.5-flash")
    from collections import defaultdict
    category_data = defaultdict(list)

    for feed in RSS_FEEDS:
        parsed = feedparser.parse(feed["url"])
        for entry in parsed.entries:
            title = entry.get("title", "Untitled")
            summary = entry.get("summary", "")
            full_text = f"{title}\n\n{summary}"
            prompt = format_prompt(full_text)
            try:
                response = model.generate_content(prompt)
                card_title, description = extract_title_and_description(response.text)
            except Exception as e:
                card_title, description = title, f"[Gemini error: {str(e)}]"
            uid = hashlib.md5((title + entry.get("link", "")).encode()).hexdigest()
            now = datetime.utcnow()
            market = {
                "id": f"market_{uid[:8]}",
                "title": card_title,
                "description": description,
                "category": feed["category"],
                "tags": CATEGORY_TAGS.get(feed["category"], []),
                "status": "open",
                "createdAt": now.isoformat() + "Z",
                "startTime": now.isoformat() + "Z",
                "endTime": (now + timedelta(days=30)).isoformat() + "Z",
                "resolutionTime": (now + timedelta(days=32)).isoformat() + "Z",
                "result": None,
                "yesCount": 50000,
                "noCount": 50000,
                "totalVolume": 100000,
                "currentYesProbability": 0.5,
                "currentNoProbability": 0.5,
                "creatorId": "kalshi-generator",
                "resolutionSource": entry.get("link", "")
            }
            category_data[feed["category"]].append(market)

    final_markets = []
    for cat, items in category_data.items():
        seen = set()
        unique = []
        for i in items:
            if i["title"].lower() not in seen:
                seen.add(i["title"].lower())
                unique.append(i)
            if len(unique) == 30:
                break
        final_markets.extend(unique)

    return {
        "eventsData": [
            {
                "markets": final_markets
            }
        ]
    }

@app.route("/generate", methods=["GET"])
def get_data():
    if "cached" not in cache:
        print("🟡 Refreshing cache...")
        cache["cached"] = generate_kalshi_cards()
    else:
        print("🟢 Using cached version")
    return jsonify(cache["cached"])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
