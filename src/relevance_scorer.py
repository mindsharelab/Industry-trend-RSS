#!/usr/bin/env python3
"""
Relevance Scorer

Uses Claude to score trend relevance against a client's profile.
Scores from 1-10 with reasoning and suggested content angle.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from anthropic import Anthropic

DB_PATH = Path("data/trends.db")

SCORING_PROMPT = """You are a content strategist evaluating whether a trending topic is worth creating content about for a specific client.

## Client Profile
{profile}

## Trend to Evaluate
Title: {title}
Source: {source}
Summary: {summary}
URL: {url}

## Your Task
Evaluate whether this trend is relevant for {client_name} to create content about.

Consider:
1. Does this relate to their expertise areas? They need to speak with authority.
2. Would their ICP (ideal customer profile) care about this topic?
3. Does it fit their content themes and voice?
4. Is there a natural angle that connects to their product/company?
5. Is this timely enough to comment on?

Respond with JSON only:
{{
  "relevance_score": <1-10, where 10 is perfect fit>,
  "reasoning": "<2-3 sentences explaining your score>",
  "suggested_angle": "<If score >= 6, suggest a specific angle or hook for content. If score < 6, put null>"
}}

Scoring guide:
- 9-10: Perfect fit - directly in their expertise, their ICP cares deeply, easy angle
- 7-8: Strong fit - related to expertise, ICP would find valuable
- 5-6: Moderate fit - tangentially related, could work with the right angle
- 3-4: Weak fit - stretching their expertise or ICP interest
- 1-2: Poor fit - outside their lane or audience wouldn't care
"""


def score_trend(profile: dict, trend: dict) -> dict:
    """Use Claude to score a single trend's relevance."""
    client = Anthropic()

    profile_summary = json.dumps({
        "name": profile.get("name"),
        "company": profile.get("company"),
        "product_description": profile.get("product_description"),
        "expertise": profile.get("expertise"),
        "icp": profile.get("icp"),
        "content_themes": profile.get("content_themes"),
        "voice": profile.get("voice")
    }, indent=2)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": SCORING_PROMPT.format(
                profile=profile_summary,
                client_name=profile.get("name", "the client"),
                title=trend["title"],
                source=trend["source"],
                summary=trend["summary"],
                url=trend["url"]
            )
        }]
    )

    response_text = response.content[0].text.strip()

    if response_text.startswith("```"):
        response_text = response_text.split("```")[1]
        if response_text.startswith("json"):
            response_text = response_text[4:]

    return json.loads(response_text)


def store_score(conn: sqlite3.Connection, trend_hash: str, client_name: str, score_data: dict):
    """Store score in database."""
    conn.execute("""
        INSERT OR REPLACE INTO trend_scores
        (trend_hash, client_name, relevance_score, reasoning, suggested_angle, scored_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        trend_hash,
        client_name,
        score_data["relevance_score"],
        score_data["reasoning"],
        score_data.get("suggested_angle"),
        datetime.now().isoformat()
    ))
    conn.commit()


def score_unscored_trends(client_name: str, limit: int = 20) -> list[dict]:
    """Score all unscored trends for a client."""
    profile_path = Path(f"clients/{client_name}/profile.json")
    if not profile_path.exists():
        raise FileNotFoundError(f"No profile found at {profile_path}")

    with open(profile_path) as f:
        profile = json.load(f)

    conn = sqlite3.connect(DB_PATH)

    from trend_fetcher import get_unscored_trends
    unscored = get_unscored_trends(conn, client_name)[:limit]

    print(f"Scoring {len(unscored)} trends for {client_name}...")

    results = []
    for i, trend in enumerate(unscored):
        print(f"  [{i+1}/{len(unscored)}] {trend['title'][:60]}...")

        try:
            score_data = score_trend(profile, trend)
            store_score(conn, trend["content_hash"], client_name, score_data)

            results.append({
                **trend,
                **score_data
            })

            if score_data["relevance_score"] >= 7:
                print(f"    → Score: {score_data['relevance_score']}/10 ✓")
            else:
                print(f"    → Score: {score_data['relevance_score']}/10")

        except Exception as e:
            print(f"    → Error: {e}")

    return results


def get_top_trends(client_name: str, min_score: int = 7, limit: int = 10) -> list[dict]:
    """Get top-scoring trends for a client."""
    conn = sqlite3.connect(DB_PATH)

    cursor = conn.execute("""
        SELECT t.title, t.url, t.summary, t.source, t.published,
               ts.relevance_score, ts.reasoning, ts.suggested_angle
        FROM trends t
        JOIN trend_scores ts ON t.content_hash = ts.trend_hash
        WHERE ts.client_name = ?
        AND ts.relevance_score >= ?
        ORDER BY ts.relevance_score DESC, t.published DESC
        LIMIT ?
    """, (client_name, min_score, limit))

    return [
        {
            "title": row[0],
            "url": row[1],
            "summary": row[2],
            "source": row[3],
            "published": row[4],
            "relevance_score": row[5],
            "reasoning": row[6],
            "suggested_angle": row[7]
        }
        for row in cursor.fetchall()
    ]


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python relevance_scorer.py <client_name> [--top]")
        print("Example: python relevance_scorer.py jenn")
        print("         python relevance_scorer.py jenn --top")
        sys.exit(1)

    client_name = sys.argv[1].lower()

    if "--top" in sys.argv:
        top = get_top_trends(client_name)
        print(f"\n=== Top Trends for {client_name} ===\n")
        for t in top:
            print(f"[{t['relevance_score']}/10] {t['title']}")
            print(f"  Angle: {t['suggested_angle']}")
            print(f"  URL: {t['url']}")
            print()
    else:
        results = score_unscored_trends(client_name)
        high_score = [r for r in results if r["relevance_score"] >= 7]
        print(f"\n{len(high_score)} high-relevance trends found (score >= 7)")
