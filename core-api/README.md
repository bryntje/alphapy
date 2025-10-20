# Innersync Core API

FastAPI skeleton that will power `api.innersync.tech`. The service reuses the shared schemas found in `../schemas` and authenticates every request with Supabase access tokens.

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Environment variables:

```
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_ANON_KEY=<anon-key>
```

## Endpoints

- `GET /health` → Service status
- `GET /users/me` → Returns the Supabase user associated with the supplied bearer token
- `GET /profiles/me`, `/reflections`, `/trades`, `/insights` → Placeholders, to be wired up once the data layer is ready

## Railway / Docker

Build with:

```bash
docker build -t innersync-core-api -f Dockerfile .
```

Run locally:

```bash
docker run --rm -p 8080:8080 \
  -e SUPABASE_URL=... \
  -e SUPABASE_ANON_KEY=... \
  innersync-core-api
```

The service listens on port `8080` by default.
