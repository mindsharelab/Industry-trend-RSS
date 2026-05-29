#!/usr/bin/env python3
"""
Profile Generator

Generates a client profile from either:
1. Interview transcripts
2. Onboarding questionnaire responses
3. Both combined

Usage:
    python profile_generator.py --client jenn --input transcripts/
    python profile_generator.py --client jenn --input questionnaire.txt
"""

import argparse
import json
import os
from pathlib import Path
from anthropic import Anthropic

PROFILE_PROMPT = """You are a content strategist analyzing source material to create a client profile.

Your task: Extract a comprehensive profile that will be used to judge whether trending topics are relevant for this person to create content about.

Source material type: {source_type}

<source_material>
{content}
</source_material>

Based on this material, generate a JSON profile with the following structure:

{{
  "name": "Client's name",
  "company": "Company name",
  "product_description": "What the company/product does in 1-2 sentences",
  "expertise": ["Topic 1", "Topic 2", ...],  // Areas they can speak on with authority
  "icp": {{
    "titles": ["Job title 1", "Job title 2"],  // Who they're trying to reach
    "company_types": ["Type 1", "Type 2"],  // What kinds of companies
    "pain_points": ["Pain 1", "Pain 2"]  // Problems their audience faces
  }},
  "content_themes": ["Theme 1", "Theme 2", ...],  // Recurring topics in their content
  "voice": {{
    "tone": "Description of how they communicate",
    "avoids": ["Topic to avoid 1", ...]  // Things they don't talk about
  }},
  "industry_terms": ["term1", "term2", ...],  // Industry jargon for search hints
  "sample_posts": []  // Leave empty, will be populated separately
}}

Important:
- For expertise, only include topics they demonstrate genuine knowledge of
- For ICP, infer from who they're trying to help/sell to
- For content_themes, look for recurring ideas or angles they return to
- For industry_terms, include synonyms and related phrases (e.g., "legal ops" AND "legal operations")
- Be specific, not generic. "AI in contract review" is better than "technology"

Return ONLY the JSON, no other text.
"""


def load_source_material(input_path: str) -> tuple[str, str]:
    """Load content from file or directory."""
    path = Path(input_path)

    if path.is_file():
        content = path.read_text()
        source_type = "onboarding questionnaire" if "questionnaire" in path.name.lower() else "transcript"
        return content, source_type

    elif path.is_dir():
        files = list(path.glob("*.txt")) + list(path.glob("*.md"))
        if not files:
            raise ValueError(f"No .txt or .md files found in {input_path}")

        combined = []
        for f in files:
            combined.append(f"=== {f.name} ===\n{f.read_text()}\n")

        return "\n".join(combined), "multiple transcripts/documents"

    else:
        raise ValueError(f"Path not found: {input_path}")


def generate_profile(content: str, source_type: str, client_name: str) -> dict:
    """Use Claude to generate profile from source material."""
    client = Anthropic()

    response = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": PROFILE_PROMPT.format(source_type=source_type, content=content)
        }]
    )

    response_text = response.content[0].text.strip()

    if response_text.startswith("```"):
        response_text = response_text.split("```")[1]
        if response_text.startswith("json"):
            response_text = response_text[4:]

    return json.loads(response_text)


def save_profile(profile: dict, client_dir: Path):
    """Save profile to client directory."""
    profile_path = client_dir / "profile.json"
    with open(profile_path, "w") as f:
        json.dump(profile, f, indent=2)
    print(f"Profile saved to: {profile_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate client profile from transcripts or questionnaire")
    parser.add_argument("--client", required=True, help="Client name (creates/uses clients/{name}/ directory)")
    parser.add_argument("--input", required=True, help="Path to transcript file, questionnaire, or directory of files")
    parser.add_argument("--output", help="Custom output path (default: clients/{client}/profile.json)")
    args = parser.parse_args()

    client_dir = Path(f"clients/{args.client.lower()}")
    client_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading source material from: {args.input}")
    content, source_type = load_source_material(args.input)
    print(f"Source type detected: {source_type}")
    print(f"Content length: {len(content)} characters")

    print("\nGenerating profile with Claude...")
    profile = generate_profile(content, source_type, args.client)

    output_path = Path(args.output) if args.output else client_dir
    save_profile(profile, output_path if output_path.is_dir() else output_path.parent)

    print("\n=== Generated Profile ===")
    print(json.dumps(profile, indent=2))


if __name__ == "__main__":
    main()
