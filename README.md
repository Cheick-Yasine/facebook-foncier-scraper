# Facebook Foncier Scraper

Apify Actor for scraping Facebook groups focused on **land and property listings in Ouagadougou** (Burkina Faso).

Built with the official **Apify Python SDK** + Playwright.

## Features (roadmap)

- Multi-account support (cookies isolation)
- Proxy support (Apify Proxy or custom residential)
- Daily / backfill modes
- Persistent state (seen posts, cooldowns, health)
- Structured output (dataset)
- Optional LLM enrichment (OpenAI)

## Quick start (local)

```bash
# Install Apify CLI (once)
npm install -g apify-cli

# Clone & enter
git clone https://github.com/Cheick-Yasine/facebook-foncier-scraper.git
cd facebook-foncier-scraper

# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Run locally
apify run
```

## Input

See `.actor/input_schema.json`. Main parameters:

| Field | Description | Default |
|-------|-------------|--------|
| `mode` | `daily` or `backfill` | `daily` |
| `daysBack` | Number of days to look back | `1` |
| `groupLimit` | Max groups (0 = all) | `0` |
| `accountId` | Account identifier ("1".."5") | empty |
| `proxyConfiguration` | Apify Proxy or custom | none |
| `cookies` | Facebook cookies JSON | required for real runs |
| `skipLlm` | Skip OpenAI structuring | `false` |

## Output

Results are stored in the default **Dataset**. Schema is defined in `.actor/dataset_schema.json`.

## Status

🚧 **Skeleton** – The Actor is runnable and produces a sample item.  
The real Playwright scraper (from `ouaga-foncier-etl`) will be migrated next.

## Related

- Previous implementation: [ouaga-foncier-etl](https://github.com/Cheick-Yasine/ouaga-foncier-etl)

## License

Private / educational use.
