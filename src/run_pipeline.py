#!/usr/bin/env python3
"""
Main Pipeline Runner

Runs the full trend discovery pipeline:
1. Fetch trends for all clients
2. Score relevance for each client
3. Generate digests

Can be run manually or via GitHub Actions scheduler.
"""

import argparse
import json
from pathlib import Path

from trend_fetcher import init_db, fetch_all_for_client, store_trends
from relevance_scorer import score_unscored_trends
from digest_generator import generate_digest, save_digest


def get_all_clients() -> list[str]:
    """Get list of all clients with profiles."""
    clients_path = Path("clients")
    clients = []

    for client_dir in clients_path.iterdir():
        if client_dir.is_dir() and (client_dir / "profile.json").exists():
            clients.append(client_dir.name)

    return clients


def run_for_client(client_name: str, skip_fetch: bool = False, skip_score: bool = False):
    """Run full pipeline for a single client."""
    profile_path = Path(f"clients/{client_name}/profile.json")

    if not profile_path.exists():
        print(f"⚠ No profile found for {client_name}, skipping")
        return None

    with open(profile_path) as f:
        profile = json.load(f)

    print(f"\n{'='*50}")
    print(f"Processing: {profile.get('name', client_name)} ({profile.get('company', 'N/A')})")
    print(f"{'='*50}")

    conn = init_db()

    if not skip_fetch:
        print("\n📡 Fetching trends...")
        items = fetch_all_for_client(profile)
        new_count = store_trends(conn, items)
        print(f"   Fetched {len(items)} items, {new_count} new")
    else:
        print("\n📡 Skipping fetch (--skip-fetch)")

    if not skip_score:
        print("\n🎯 Scoring relevance...")
        results = score_unscored_trends(client_name, limit=30)
        high_score = [r for r in results if r["relevance_score"] >= 7]
        print(f"   Scored {len(results)} trends, {len(high_score)} high-relevance")
    else:
        print("\n🎯 Skipping scoring (--skip-score)")

    print("\n📝 Generating digest...")
    content = generate_digest(client_name)
    filepath = save_digest(client_name, content)
    print(f"   Saved: {filepath}")

    return filepath


def run_all(skip_fetch: bool = False, skip_score: bool = False):
    """Run pipeline for all clients."""
    clients = get_all_clients()

    if not clients:
        print("No client profiles found. Run profile_generator.py first.")
        return

    print(f"Found {len(clients)} clients: {', '.join(clients)}")

    digests = []
    for client_name in clients:
        filepath = run_for_client(client_name, skip_fetch, skip_score)
        if filepath:
            digests.append(filepath)

    print(f"\n{'='*50}")
    print(f"✅ Complete! Generated {len(digests)} digests:")
    for d in digests:
        print(f"   - {d}")


def main():
    parser = argparse.ArgumentParser(description="Run trend discovery pipeline")
    parser.add_argument("--client", help="Run for specific client only")
    parser.add_argument("--skip-fetch", action="store_true", help="Skip fetching new trends")
    parser.add_argument("--skip-score", action="store_true", help="Skip scoring (use existing scores)")
    parser.add_argument("--digest-only", action="store_true", help="Only generate digests from existing data")
    args = parser.parse_args()

    if args.digest_only:
        args.skip_fetch = True
        args.skip_score = True

    if args.client:
        run_for_client(args.client.lower(), args.skip_fetch, args.skip_score)
    else:
        run_all(args.skip_fetch, args.skip_score)


if __name__ == "__main__":
    main()
