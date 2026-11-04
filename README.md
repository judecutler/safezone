# SafeZone

Earthquake and tsunami preparation for coastal households. Built for the Meta Global AI Developer Hackathon with SAM 3.1 and Muse Spark.

## Set up your API key

1. Copy the template: `cp .env.example .env`
2. Open `.env` and paste your key after `MODEL_API_KEY=`.
3. Done. `.env` is in `.gitignore`, so git never commits it.

Do not paste the key into code, chat, issues, or commits. If it leaks, revoke it at dev.meta.ai and make a new one. For a deployed server, put the key in the host's secret store (for example Modal secrets), not in a file.

## Keeping API costs down

Every Meta call goes through `safezone/meta_client.py`:

- Identical requests are cached in `.cache/meta/` and never paid for twice.
- `MAX_API_CALLS` in `.env` is a hard lifetime cap, counted across restarts.
- `SAFEZONE_OFFLINE=1` blocks all network calls and serves only cached responses.

## Phase 1 probe

```
pip install pytest
python -m pytest -q
python scripts/probe.py path/to/room.jpg --dry-run   # free, shows the requests
python scripts/probe.py path/to/room.jpg             # at most 2 paid calls
```

The probe saves the real responses in `fixtures/probe/`. Development then runs against those fixtures.
