#!/usr/bin/env python3
"""
Trend Fetcher

Fetches trending content from multiple sources:
1. Google News RSS (by industry terms)
2. Google Search for LinkedIn posts (site:linkedin.com)
3. Industry-specific RSS feeds

Results are stored in a SQLite database for deduplication and scoring.
"""

import hashlib
import json
import re
import sqlite3
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote_plus

import requests

DB_PATH = Path("data/trends.db")

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"

INDUSTRY_FEEDS = {
    "legal_tech": [
        "https://www.artificiallawyer.com/feed/",
        "https://abovethelaw.com/feed/",
        "https://www.legaltechnews.com/rss/",
    ],
}


@dataclass
class TrendItem:
    source: str
    title: str
    url: str
    summary: str
    published: datetime | None
    content_hash: str


def init_db():
    """Initialize SQLite database."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_hash TEXT UNIQUE,
            source TEXT,
            title TEXT,
            url TEXT,
            summary TEXT,
            published TEXT,
            fetched_at TEXT,
            raw_content TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trend_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trend_hash TEXT,
            client_name TEXT,
            relevance_score INTEGER,
            reasoning TEXT,
            suggested_angle TEXT,
            scored_at TEXT,
            UNIQUE(trend_hash, client_name)
        )
    """)
    conn.commit()
    return conn


def hash_content(title: str, url: str) -> str:
    """Create unique hash for deduplication."""
    return hashlib.md5(f"{title}|{url}".encode()).hexdigest()


def parse_rss_date(date_str: str) -> datetime | None:
    """Parse common RSS date formats."""
    if not date_str:
        return None
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


def fetch_google_news(query: str, max_items: int = 20) -> list[TrendItem]:
    """Fetch from Google News RSS using simple XML parsing."""
    url = GOOGLE_NEWS_RSS.format(query=quote_plus(query))

    try:
        response = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        root = ET.fromstring(response.content)
    except Exception as e:
        print(f"Error fetching Google News for '{query}': {e}")
        return []

    items = []
    for item in root.findall(".//item")[:max_items]:
        title = item.findtext("title", "")
        link = item.findtext("link", "")
        description = item.findtext("description", "")
        pub_date = item.findtext("pubDate", "")

        items.append(TrendItem(
            source="google_news",
            title=title,
            url=link,
            summary=description[:500] if description else "",
            published=parse_rss_date(pub_date),
            content_hash=hash_content(title, link)
        ))

    return items


def fetch_rss_feed(feed_url: str, source_name: str, max_items: int = 10) -> list[TrendItem]:
    """Fetch from a generic RSS feed using simple XML parsing."""
    try:
        response = requests.get(feed_url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        root = ET.fromstring(response.content)
    except Exception as e:
        print(f"Error fetching {feed_url}: {e}")
        return []

    items = []
    for item in root.findall(".//item")[:max_items]:
        title = item.findtext("title", "")
        link = item.findtext("link", "")
        description = item.findtext("description", "")
        pub_date = item.findtext("pubDate", "")

        items.append(TrendItem(
            source=source_name,
            title=title,
            url=link,
            summary=description[:500] if description else "",
            published=parse_rss_date(pub_date),
            content_hash=hash_content(title, link)
        ))

    return items


def store_trends(conn: sqlite3.Connection, items: list[TrendItem]) -> int:
    """Store trends in database, returns count of new items."""
    new_count = 0
    for item in items:
        try:
            conn.execute("""
                INSERT INTO trends (content_hash, source, title, url, summary, published, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                item.content_hash,
                item.source,
                item.title,
                item.url,
                item.summary,
                item.published.isoformat() if item.published else None,
                datetime.now().isoformat()
            ))
            new_count += 1
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    return new_count


def fetch_all_for_client(client_profile: dict) -> list[TrendItem]:
    """Fetch trends based on client's industry terms."""
    all_items = []

    industry_terms = client_profile.get("industry_terms", [])
    if not industry_terms:
        print("Warning: No industry terms in profile, using expertise areas")
        industry_terms = client_profile.get("expertise", [])

    for term in industry_terms[:5]:
        print(f"  Fetching Google News for: {term}")
        items = fetch_google_news(term)
        all_items.extend(items)

    return all_items


def get_unscored_trends(conn: sqlite3.Connection, client_name: str, days: int = 14) -> list[dict]:
    """Get trends that haven't been scored for this client."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    cursor = conn.execute("""
        SELECT t.content_hash, t.source, t.title, t.url, t.summary, t.published
        FROM trends t
        LEFT JOIN trend_scores ts ON t.content_hash = ts.trend_hash AND ts.client_name = ?
        WHERE ts.id IS NULL
        AND (t.published IS NULL OR t.published > ?)
        ORDER BY t.published DESC
        LIMIT 50
    """, (client_name, cutoff))

    return [
        {
            "content_hash": row[0],
            "source": row[1],
            "title": row[2],
            "url": row[3],
            "summary": row[4],
            "published": row[5]
        }
        for row in cursor.fetchall()
    ]


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python trend_fetcher.py <client_name>")
        print("Example: python trend_fetcher.py jenn")
        sys.exit(1)

    client_name = sys.argv[1].lower()
    profile_path = Path(f"clients/{client_name}/profile.json")

    if not profile_path.exists():
        print(f"Error: No profile found at {profile_path}")
        print("Run profile_generator.py first to create a client profile.")
        sys.exit(1)

    with open(profile_path) as f:
        profile = json.load(f)

    print(f"Fetching trends for: {profile.get('name', client_name)}")

    conn = init_db()
    items = fetch_all_for_client(profile)

    new_count = store_trends(conn, items)
    print(f"\nFetched {len(items)} items, {new_count} new")

    unscored = get_unscored_trends(conn, client_name)
    print(f"Unscored trends for {client_name}: {len(unscored)}")
