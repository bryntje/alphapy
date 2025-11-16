## Innersync • Alphapips Dashboard

Deze Next.js-app maakt deel uit van het **Innersync** ecosysteem en visualiseert de realtime statistieken van de Alphapips Discord bot.  
Via een beveiligde proxy naar de FastAPI-backend (`/api/dashboard/metrics`) tonen we:

- Botstatus (uptime, latency, versie, guilds, commands)
- GPT-gebruik (tokens, successen/fouten, recente events)
- Reminder statistieken (per kanaal, aankomende events)
- Tickethealth (open items, doorlooptijden, statusverdeling)
- Runtime overrides en database health

## Installatie

```bash
npm install
npm run dev
```

### Vereiste environment-variabelen

Plaats in `.env`:

```
NEXT_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<public-anon-key>
APP_BASE_URL=https://app.innersync.tech
MIND_BASE_URL=https://mind.innersync.tech
CORE_API_BASE_URL=https://api.innersync.tech
# Optioneel: service key voor de Core API
# CORE_API_SERVICE_KEY=<optioneel: service key>
ALPHAPY_BASE_URL=https://alphapy.innersync.tech
ALPHAPY_API_KEY=<optioneel: zelfde key als FastAPI>
NEXT_PUBLIC_DISCORD_GUILD_ID=<discord guild id voor deeplinks>
```

- `NEXT_PUBLIC_SUPABASE_URL` en `NEXT_PUBLIC_SUPABASE_ANON_KEY` laten de app verbinden met het centrale Innersync-authproject (Supabase).
- `CORE_API_BASE_URL` verwijst naar de centrale Innersync Core API (`api.innersync.tech`). Als deze niet is gezet valt de proxy terug op `ALPHAPY_BASE_URL`.
- `CORE_API_SERVICE_KEY` en `ALPHAPY_API_KEY` zijn optioneel; wanneer ingevuld wordt de waarde als `X-Api-Key` header meegestuurd.
- Requests naar `/api/dashboard/metrics` sturen automatisch `Authorization: Bearer <supabase-access-token>` zodat de backend Supabase JWT’s kan valideren.

### Health endpoint

Deze service exposeert `/health` met een JSON status (`service`, `version`, `uptime_seconds`, `db_status`, `timestamp`) zodat Railway probes of externe monitors de beschikbaarheid kunnen checken.

### Data-refresh

De dashboardpagina haalt de metriek elke 45 seconden automatisch opnieuw op (via polling), toont een sparkline van GPT tokens per interval en badge bij recente fouten. Je kunt ook handmatig verversen met de knop “Vernieuw data”. Dit houdt de cijfers redelijk realtime zonder agressieve (dure) requestfrequentie.

## Scripts

- `npm run dev` – ontwikkelmodus
- `npm run build` – productie build
- `npm run lint` – TypeScript/ESLint check

## Deployment

Deploy op Vercel of Railway. Vergeet niet dezelfde env-variabelen te configureren zodat de proxy naar Alphapy blijft werken en houd de branding consistent binnen Innersync.
