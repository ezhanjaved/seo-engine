# SEO Engine

SEO Engine is a small toolbox of SEO capabilities ("skills") meant to be called by an external agent.

The intended consumer is **Hermes**, a separate general-purpose agent runtime. Hermes is not part of this repository: this repo contains no agent, no LLM, and no decision-making. It only exposes deterministic capabilities and the written methodologies that explain how to interpret their output.

## Scope of V0

V0 does exactly one thing: retrieve Google Search Console (GSC) performance data in a structured, deterministic way.

| Layer | Lives in | Responsibility |
| --- | --- | --- |
| Skill | `skills/gsc/` | Retrieves data. No analysis. |
| Skill | `skills/serp/` | Collects search-results and ranking-page evidence. No analysis. |
| Methodology | `methodologies/` | Explains how to interpret data. |
| Agent (Hermes) | outside this repo | Decides how and when to call a skill. |

## Local setup

Requires Python 3.10+.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium   # only needed for skills/serp

cp .env.example .env
cp config/sites.example.yaml config/sites.yaml
```

Then:

1. Create a Google Cloud service account, enable the Search Console API, and download its JSON key.
2. Add the service account's email as a user on each GSC property you want to query.
3. Point `GSC_SERVICE_ACCOUNT_FILE` in `.env` at the key file.
4. List your properties in `config/sites.yaml`.

See [skills/gsc/README.md](skills/gsc/README.md) and [skills/serp/README.md](skills/serp/README.md) for usage.

## Repository structure

```
seo-engine/
├── README.md
├── requirements.txt
├── .env.example              # environment variable placeholders
├── .gitignore
├── config/
│   └── sites.example.yaml    # site alias -> GSC property mapping (template)
├── methodologies/
│   └── monitoring.md         # how to interpret GSC data (template)
├── skills/
│   ├── gsc/
│   │   ├── __init__.py
│   │   ├── __main__.py       # CLI: python -m skills.gsc
│   │   ├── client.py         # GSC Search Analytics retrieval
│   │   └── README.md
│   └── serp/
│       ├── __init__.py
│       ├── __main__.py       # CLI: python -m skills.serp
│       ├── collector.py      # browser lifecycle and orchestration
│       ├── google.py         # Google results-page parsing
│       ├── bing.py           # Bing results-page parsing
│       ├── extractor.py      # ranking-page content extraction
│       ├── urls.py           # URL safety checks
│       └── README.md
└── tests/
    ├── __init__.py
    ├── test_gsc.py           # pytest; Google API mocked
    └── test_serp.py          # pytest; browser faked, static HTML
```

## Usage

```bash
python -m skills.gsc --site example --start-date 2026-07-01 --end-date 2026-09-30 --dimensions date
python -m skills.serp --query "best local seo tools"
```

Each prints JSON to stdout. Run the tests with `python -m pytest`.

## Security

**Never commit credentials.**

- `.env`, `config/sites.yaml`, and the `credentials/` directory are git-ignored. Keep service account keys there or outside the repository entirely.
- `.env.example` and `config/sites.example.yaml` must only ever contain placeholders.
- Grant the service account the lowest GSC permission that works (read-only: "Restricted" or "Full" user, never "Owner").
- If a key is ever committed, revoke it in Google Cloud immediately; removing it from git history is not enough.
