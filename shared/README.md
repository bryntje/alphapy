# Innersync Core

Production-ready landing hub for the Innersync platform with a dark, neural aesthetic and the App → Alphapy → Mind → Core hero morph.

![Innersync Core preview](./public/og.png)

## Highlights

- **Hero morph animation** composed with Framer Motion + GSAP to transform the four-node diamond into a central neural root, with reduced-motion fallbacks.
- **Smooth scrolling** via Lenis, gated by `prefers-reduced-motion`.
- **Railway-ready** shipping container (Docker) that respects `PORT` and serves the standalone Next.js output.
- **Health & metrics endpoints** powering the `/status` page (`/api/health`, `/api/metrics`).
- **Deep accessibility & performance** focus: keyboard-visible CTAs, responsive typography, Tailwind tokens, and ≥95 Lighthouse targets.

## Stack

- Next.js 15 (App Router, TypeScript)
- Tailwind CSS 3.4 + `@tailwindcss/typography`
- Framer Motion + GSAP (MorphSVG)
- Lenis smooth-scrolling
- ESLint + Prettier
- pnpm (via Corepack)

## Getting Started

```bash
pnpm install
pnpm dev
```

Then visit [http://localhost:3000](http://localhost:3000).

### Shared Schemas

This repo now contains shared data contracts under `schemas/`:

- `schemas/typescript` – TypeScript type definitions you can import directly or publish as `@innersync/schemas`.
- `schemas/python` – Pydantic models for server and worker workloads.

See `schemas/README.md` for details on how to consume them inside the other Innersync services.

### Core API (beta)

The `core-api/` directory contains a FastAPI skeleton that authenticates requests via Supabase and exposes starter endpoints. Run it locally with `uvicorn app.main:app --reload` or deploy the included Dockerfile on Railway (`api.innersync.tech`). Available routes include:

- `GET /health` – service heartbeat
- `GET /users/me`, `/profiles/me`, `/reflections`, `/trades`, `/insights` – per-user resources
- `GET /dashboard/summary` – combined payload (user + profile + reflections/trades/insights + stats) for the Mind dashboard

### Supabase schema

Initial SQL to provision the shared `profiles`, `reflections`, `trades` and `insights` tables (plus RLS policies) lives in `supabase/0001_core_tables.sql`. Execute it inside the Supabase SQL editor or through `supabase db push` before wiring up the Core API or the Alphapy sync jobs.

### Environment

Copy `.env.example` to `.env.local` and adjust if needed:

```
NEXT_PUBLIC_CORE_BASE=https://innersync.tech
NEXT_PUBLIC_APP_URL=https://app.innersync.tech
NEXT_PUBLIC_MIND_URL=https://mind.innersync.tech
NEXT_PUBLIC_ALPHAPY_URL=https://alphapy.innersync.tech
SUPABASE_SERVICE_ROLE_KEY=
BUILD_TIME=
COMMIT_SHA=
```

Key values:

- `NEXT_PUBLIC_CORE_BASE` anchors links rendered on the marketing surface.
- `NEXT_PUBLIC_CORE_API_URL` points to the FastAPI deployment (`api.innersync.tech`) used for CTA and status links.
- `NEXT_PUBLIC_APP_URL`, `NEXT_PUBLIC_MIND_URL`, and `NEXT_PUBLIC_ALPHAPY_URL` power cross-site navigation.
- `SUPABASE_SERVICE_ROLE_KEY` laat Core (en Mind) schrijven/lezen in het gedeelde `telemetry` schema.
- `BUILD_TIME` en `COMMIT_SHA` zijn optionele overrides voor de health endpoint; defaults worden automatisch ingevuld.

### Scripts

- `pnpm dev` – run the local dev server on port 3000
- `pnpm build` – compile the Next.js app (`output: standalone`)
- `pnpm start` – serve the production build
- `pnpm lint` – run ESLint (Next + Prettier config)
- `pnpm format` – check formatting with Prettier

## Railway Deploy

### Service Configuration
This repository is deployed as a **submodule** within the main Alphapy repository. The Railway service requires special configuration:

#### Manual Setup Required
Due to submodule structure, configure Railway manually:

1. **Railway Dashboard** → Service Settings
2. **"Railway Config File"**: `/shared/innersync-core/railway.toml`
3. **"Root Directory"**: `/shared/innersync-core`
4. **"Watch Paths"**: `/shared/innersync-core/**`

#### Environment Variables
Ensure these are set in Railway:
- All variables listed in "Environment" section above
- Railway assigns `PORT`; container exposes `8080`

#### Health Checks
- **Path**: `/api/health` (Next.js API route)
- **Type**: HTTP GET with automatic Railway monitoring

```bash
# After manual config in Railway dashboard:
railway up
```

### Dockerfile summary

```
node:20-alpine → pnpm 10.19.0 (corepack)
deps  → install dependencies
build → pnpm build (standalone output)
run   → copy .next/standalone + static + public, run `node server.js`
```

## Accessibility & Performance

- All CTAs have visible focus states and support keyboard navigation.
- Hero animation auto-skips when `prefers-reduced-motion` is set.
- Tailwind tokens centralize colors, glows, and typography for consistent contrast.
- Images served via Next static assets with `og.png` preview.
- Smooth scrolling, GSAP morph timeline, and Lenis are wrapped in guards to avoid main-thread leaks.

## Status Endpoints

- `GET /api/health` → `{ status, commitSha, buildTime }`
- `GET /api/metrics` → unified telemetry snapshot for Core, API, and Alphapy (see `types/telemetry.ts`)

`/status` polls both endpoints every 15 seconds. The metrics endpoint returns a payload shaped like:

```jsonc
{
  "generatedAt": "2025-01-05T10:52:00.000Z",
  "summary": {
    "overallStatus": "operational",
    "incidentsOpen": 0,
    "totalRequests24h": 172800
  },
  "subsystems": {
    "core": {
      "id": "core",
      "label": "Core",
      "status": "operational",
      "uptimeSeconds": 268000,
      "throughputPerMinute": 184,
      "errorRate": 0.42,
      "latencyP50": 108,
      "latencyP95": 162,
      "queueDepth": 7,
      "notes": "Event bus nominal",
      "lastUpdated": "2025-01-05T10:52:00.000Z"
    },
    "api": { "...": "..." },
    "alphapy": { "...": "..." }
  },
  "trends": {
    "throughput": [{ "timestamp": "2025-01-05T10:48:00.000Z", "value": 480 }],
    "errorRate": [{ "timestamp": "2025-01-05T10:48:00.000Z", "value": 0.6 }]
  }
}
```

Mind (and other services) can publish real metrics in this format; the marketing surface renders it immediately without a schema switch.

### FastAPI Core API Deployment

The `core-api` service (FastAPI) powers Supabase-backed routes such as `/dashboard/summary` and now mirrors the same `/api/metrics` payload. When deploying this service (e.g. via `core-api/railway.toml`), configure:

```
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_ANON_KEY=<public-anon-key>
SUPABASE_SERVICE_ROLE_KEY=<service-role-key> # optional but required to persist telemetry
SUPABASE_DB_URL=postgresql://<user>:<password>@<host>:6543/postgres
```

If `SUPABASE_SERVICE_ROLE_KEY` (or `CORE_SUPABASE_SERVICE_KEY`) is present, the API writes snapshots to the shared `telemetry.*` tables; without it the endpoint still serves live synthetic metrics.

> **Heads-up**  
> Voeg in Supabase Studio bij *Settings → API* het schema `telemetry` toe aan **Exposed Schemas**. Anders accepteert PostgREST alleen `public` en `graphql_public` en geven de REST calls van Core een 406 “schema must be public, graphql_public”.

## License

See [LICENSE](./LICENSE) for project licensing details.
