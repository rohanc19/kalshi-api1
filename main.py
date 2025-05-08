
from flask import Flask, jsonify
import feedparser
import hashlib
import json
from datetime import datetime, timedelta
from cachetools import TTLCache
import time
import os
import google.generativeai as genai

app = Flask(__name__)
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
cache = TTLCache(maxsize=1, ttl=1800)

CATEGORY_TAGS = {
    "Politics": ["Politics", "Government", "Elections", "Law"],
    "Sports": ["Sports", "Public Figures", "Entertainment"],
    "Culture": ["Festivals", "Entertainment", "Awards"],
    "Crypto": ["Crypto", "Currency", "Finance", "Blockchain"],
    "Climate": ["Climate", "Environment", "Natural Disasters"],
    "Economics": ["Economy", "Finance", "Stock Market", "Trade"],
    "Companies": ["Companies", "Startups", "Business", "Mergers & Acquisitions"],
    "Financials": ["Finance", "Economy", "Banking"],
    "Tech & Science": ["Technology", "Science", "Artificial Intelligence", "Gadgets", "Innovation", "Space"],
    "Health": ["Health", "Pandemics", "Wellness", "Environment"],
    "World": ["World Affairs", "Government", "Defense & Military"],
    "Trending": ["Consumer Trends", "Social Media Trends", "Travel"],
    "New": ["New", "IPOs", "Announcements"]
}

RSS_FEEDS = [
    {"url": "https://feeds.feedburner.com/ndtvnews-india-news", "category": "Politics"},
    {"url": "https://www.hindustantimes.com/feeds/rss/sports/rssfeed.xml", "category": "Sports"},
    {"url": "https://www.rollingstone.com/culture/feed/", "category": "Culture"},
    {"url": "https://cointelegraph.com/rss", "category": "Crypto"},
    {"url": "https://climate.nasa.gov/rss_featured_news.xml", "category": "Climate"},
    {"url": "https://www.livemint.com/rss/economy", "category": "Economics"},
    {"url": "https://techcrunch.com/feed/", "category": "Companies"},
    {"url": "https://www.moneycontrol.com/rss/MCtopnews.xml", "category": "Financials"},
    {"url": "https://www.sciencedaily.com/rss/top/science.xml", "category": "Tech & Science"},
    {"url": "https://www.medicalnewstoday.com/rss", "category": "Health"},
    {"url": "https://www.aljazeera.com/xml/rss/all.xml", "category": "World"},
    {"url": "https://www.nytimes.com/services/xml/rss/nyt/Trending.xml", "category": "Trending"},
    {"url": "https://www.cnet.com/rss/new/", "category": "New"}
]

def format_prompt(text):
    return (
        "Convert this news into a YES/NO prediction question with a clear timeframe. "
        "Then provide a one-paragraph explanation that frames it like a prediction Kalshi would publish.\n\n"
        f"{text}"
    )

def safe_generate(prompt, model):
    for attempt in range(3):
        try:
            return model.generate_content(prompt).text
        except Exception as e:
            print(f"⚠️ Gemini error, retrying ({attempt + 1}/3):", e)
            time.sleep(1)
    return "[Gemini failed]"

def extract_title_and_description(generated):
    if generated.startswith("Will") or generated.startswith("**Question:**"):
        parts = generated.split("\n", 1)
        return parts[0].strip(), parts[1].strip() if len(parts) > 1 else ""
    return "**Prediction Market Question:**", generated

def generate_kalshi_cards():
    from collections import defaultdict
    model = genai.GenerativeModel("gemini-1.5-flash")
    category_data = defaultdict(list)

    for feed in RSS_FEEDS:
        parsed = feedparser.parse(feed["url"])
        for entry in parsed.entries:
            title = entry.get("title", "Untitled")
            summary = entry.get("summary", "")
            full_text = f"{title}\n\n{summary}"
            prompt = format_prompt(full_text)
            generated = safe_generate(prompt, model)
            card_title, card_description = extract_title_and_description(generated)

            uid = hashlib.md5((title + entry.get("link", "")).encode()).hexdigest()
            now = datetime.utcnow()

            market = {
                "id": f"market_{uid[:8]}",
                "title": card_title,
                "description": card_description,
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
    for category, items in category_data.items():
        seen = set()
        unique_items = []
        for item in items:
            title_key = item["title"].lower().strip()
            if title_key not in seen:
                seen.add(title_key)
                unique_items.append(item)
            if len(unique_items) == 30:
                break
        print(f"✅ {category}: {len(unique_items)} cards collected.")
        final_markets.extend(unique_items)

    return {"eventsData": [{"markets": final_markets}]}

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
