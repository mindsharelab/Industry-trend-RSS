# Industry Trend RSS

Automated trend discovery and content opportunity surfacing for clients. Fetches industry news, scores relevance against client profiles, and generates bi-weekly digests.

## How It Works

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Profile Gen    │     │  Trend Fetcher   │     │ Relevance Score │
│                 │     │                  │     │                 │
│ Questionnaire   │────▶│ Google News RSS  │────▶│ Claude analyzes │
│ or Transcripts  │     │ Industry Feeds   │     │ against profile │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                          │
                                                          ▼
                                                 ┌─────────────────┐
                                                 │ Digest Generator│
                                                 │                 │
                                                 │ Top opportunities│
                                                 │ + suggested angles│
                                                 └─────────────────┘
```

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set up API key

```bash
export ANTHROPIC_API_KEY=your_key_here
```

### 3. Create a client profile

From questionnaire/transcript:
```bash
# Add your questionnaire or transcript to: clients/{name}/source/
# Then generate the profile:
python src/profile_generator.py --client jenn --input clients/jenn/source/questionnaire.txt
```

Or create manually: copy `config/schema.json` structure to `clients/{name}/profile.json`

### 4. Run the pipeline

```bash
# Full pipeline for one client
python src/run_pipeline.py --client jenn

# Full pipeline for all clients
python src/run_pipeline.py

# Just generate digests from existing data
python src/run_pipeline.py --digest-only
```

### 5. Review digests

Digests are saved to `digests/{client}_{date}.md`

## Directory Structure

```
├── clients/
│   ├── jenn/
│   │   ├── profile.json          # Generated or manual client profile
│   │   └── source/               # Questionnaires, transcripts
│   └── osman/
│       └── ...
├── config/
│   └── schema.json               # Profile JSON schema reference
├── data/
│   └── trends.db                 # SQLite database of trends + scores
├── digests/
│   └── jenn_2024-01-15.md        # Generated digests
├── src/
│   ├── profile_generator.py      # Create profiles from source material
│   ├── trend_fetcher.py          # Fetch trends from RSS/news
│   ├── relevance_scorer.py       # Score trends with Claude
│   ├── digest_generator.py       # Generate markdown digests
│   └── run_pipeline.py           # Main orchestrator
└── .github/workflows/
    └── trend-digest.yml          # Scheduled runs (Mon/Thu 9am UTC)
```

## Automation

The GitHub Action runs automatically twice weekly. To enable:

1. Add `ANTHROPIC_API_KEY` to repository secrets
2. The workflow runs Monday and Thursday at 9am UTC
3. Digests are auto-committed to the repo

## Adding a New Client

1. Create directory: `clients/{name}/source/`
2. Add questionnaire or transcript files
3. Run: `python src/profile_generator.py --client {name} --input clients/{name}/source/`
4. Review and edit `clients/{name}/profile.json` if needed
5. Run: `python src/run_pipeline.py --client {name}`

## Customizing Sources

Edit `src/trend_fetcher.py` to add industry-specific RSS feeds in the `INDUSTRY_FEEDS` dict.
