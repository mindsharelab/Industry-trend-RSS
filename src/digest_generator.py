#!/usr/bin/env python3
"""
Digest Generator

Creates a bi-weekly digest of relevant trends for each client.
Output can be markdown (for review) or structured for future internal tool.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from anthropic import Anthropic

DB_PATH = Path("data/trends.db")
DIGESTS_PATH = Path("digests")

DIGEST_PROMPT = """You are creating a content opportunities digest for {client_name} from {company}.

Here are the highest-relevance trending topics from the past two weeks:

{trends_json}

Create a concise, actionable digest with:

1. **Executive Summary** (2-3 sentences): What's happening in their industry this period?

2. **Top 3-5 Content Opportunities**: For each, include:
   - The trend/topic
   - Why it matters to their audience
   - Suggested content angle
   - Whether it's time-sensitive

3. **Quick Hits**: Any other notable items worth monitoring (bullet points)

Keep it scannable. {client_name} will review this to decide what to create content about.
Format in markdown.
"""


def generate_digest(client_name: str, min_score: int = 6) -> str:
    """Generate markdown digest for a client."""
    profile_path = Path(f"clients/{client_name}/profile.json")
    if not profile_path.exists():
        raise FileNotFoundError(f"No profile found at {profile_path}")

    with open(profile_path) as f:
        profile = json.load(f)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("""
        SELECT t.title, t.url, t.summary, t.source, t.published,
               ts.relevance_score, ts.reasoning, ts.suggested_angle
        FROM trends t
        JOIN trend_scores ts ON t.content_hash = ts.trend_hash
        WHERE ts.client_name = ?
        AND ts.relevance_score >= ?
        ORDER BY ts.relevance_score DESC, t.published DESC
        LIMIT 15
    """, (client_name, min_score))

    trends = [
        {
            "title": row[0],
            "url": row[1],
            "summary": row[2][:200] if row[2] else "",
            "source": row[3],
            "published": row[4],
            "relevance_score": row[5],
            "reasoning": row[6],
            "suggested_angle": row[7]
        }
        for row in cursor.fetchall()
    ]

    if not trends:
        return f"# Trend Digest for {profile.get('name', client_name)}\n\nNo high-relevance trends found this period."

    client = Anthropic()
    response = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": DIGEST_PROMPT.format(
                client_name=profile.get("name", client_name),
                company=profile.get("company", "their company"),
                trends_json=json.dumps(trends, indent=2)
            )
        }]
    )

    digest_content = response.content[0].text

    header = f"""# Trend Digest: {profile.get('name', client_name)}
**Generated**: {datetime.now().strftime('%Y-%m-%d')}
**Company**: {profile.get('company', 'N/A')}

---

"""
    return header + digest_content


def save_digest(client_name: str, content: str) -> Path:
    """Save digest to file."""
    DIGESTS_PATH.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now().strftime('%Y-%m-%d')
    filename = f"{client_name}_{date_str}.md"
    filepath = DIGESTS_PATH / filename

    filepath.write_text(content)
    return filepath


def generate_all_digests() -> list[Path]:
    """Generate digests for all clients with profiles."""
    clients_path = Path("clients")
    saved_files = []

    for client_dir in clients_path.iterdir():
        if not client_dir.is_dir():
            continue

        profile_path = client_dir / "profile.json"
        if not profile_path.exists():
            continue

        client_name = client_dir.name
        print(f"Generating digest for: {client_name}")

        try:
            content = generate_digest(client_name)
            filepath = save_digest(client_name, content)
            saved_files.append(filepath)
            print(f"  Saved: {filepath}")
        except Exception as e:
            print(f"  Error: {e}")

    return saved_files


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        client_name = sys.argv[1].lower()
        print(f"Generating digest for {client_name}...")
        content = generate_digest(client_name)
        filepath = save_digest(client_name, content)
        print(f"\nSaved to: {filepath}")
        print("\n" + "=" * 50)
        print(content)
    else:
        print("Generating digests for all clients...")
        files = generate_all_digests()
        print(f"\nGenerated {len(files)} digests")
