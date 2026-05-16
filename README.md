# serp-api-example

Search Google Flights through SerpApi.

## Setup

Create `.env` from the example file:

```bash
cp .env.example .env
```

Then put your private SerpApi key in `.env`:

```dotenv
SERPAPI_API_KEY=your_serpapi_private_key_here
```

The script loads `.env` automatically. The file is ignored by git.

## Find San Diego to Madrid Flights

By default, the script searches a round trip from San Diego (`SAN`) to Madrid (`MAD`) leaving three months from today and returning 14 days later.

```bash
uv run python main.py
```

Useful overrides:

```bash
# Pick exact dates
uv run python main.py --outbound-date 2026-08-16 --return-date 2026-08-30

# One-way search
uv run python main.py --one-way

# Save the full SerpApi response while also printing the summary
uv run python main.py --save-json flights.json

# Use SerpApi deep search for results closer to the Google Flights browser UI
uv run python main.py --deep-search
```

Other defaults can be changed with `--from`, `--to`, `--adults`, `--currency`, `--travel-class`, and `--max-results`.
