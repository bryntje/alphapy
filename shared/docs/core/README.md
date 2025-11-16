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

The `core-api/` directory contains a FastAPI skeleton that authenticates requests via Supabase and exposes starter endpoints. Run it locally with `uvicorn app.main:app --reload` or deploy the included Dockerfile on Railway (`api.innersync.tech`).

### Environment

Copy `.env.example` to `.env.local` and adjust if needed:

```
NEXT_PUBLIC_CORE_BASE=https://innersync.tech
NEXT_PUBLIC_APP_URL=https://app.innersync.tech
NEXT_PUBLIC_MIND_URL=https://mind.innersync.tech
NEXT_PUBLIC_ALPHAPY_URL=https://alphapy.innersync.tech
BUILD_TIME=
COMMIT_SHA=
```

`BUILD_TIME` and `COMMIT_SHA` are optional overrides for the health endpoint; defaults are generated automatically.

### Scripts

- `pnpm dev` – run the local dev server on port 3000
- `pnpm build` – compile the Next.js app (`output: standalone`)
- `pnpm start` – serve the production build
- `pnpm lint` – run ESLint (Next + Prettier config)
- `pnpm format` – check formatting with Prettier

## Railway Deploy

1. Ensure the environment variables above are set in Railway.
2. Deploy with the included `Dockerfile` (Next standalone output).
3. Railway assigns `PORT`; the container exposes `8080` and `server.js` listens on `PORT`.
4. Healthcheck path: `/api/health` (mirrored in `railway.json`).

```bash
railway up
```

### Dockerfile summary

```
node:20-alpine → pnpm 9.12 (corepack)
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
- `GET /api/metrics` → `{ uptime, pageViews }`
- `/status` page polls both endpoints every 15 seconds for live previews.

## License

See [LICENSE](./LICENSE) for project licensing details.
