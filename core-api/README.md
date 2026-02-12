# Core-API (innersync_core)

De daadwerkelijke **Core-API** (api.innersync.tech) draait in een **ander repo** en een **aparte deployment**: **innersync_core**. Deze folder is een remnant van een eerdere koppeling en bevat geen code meer.

Alphapy stuurt telemetry en operational events naar Core via **ingress** (zie `alphapy/utils/core_ingress.py`). De implementatie van die endpoints hoort in het **innersync_core**-repo.

## Ingress-contract (geïmplementeerd in innersync_core)

- **Auth:** `X-API-Key` header (service key, bijv.zelfde waarde als `ALPHAPY_SERVICE_KEY` in Alphapy).
- **Rate limits:** bijv. 60/min voor telemetry, 200/min voor operational-events (per key).

| Endpoint | Method | Body | Actie |
|---------|--------|------|--------|
| `/ingress/telemetry` | POST | `{"snapshots": [{ "subsystem", "label", "status", "uptime_seconds", "throughput_per_minute", "error_rate", "latency_p50", "latency_p95", "last_updated", "computed_at", "queue_depth?", "active_bots?", "notes?" }]}` | Valideren → schrijven naar `telemetry.subsystem_snapshots` |
| `/ingress/operational-events` | POST | `{"events": [{ "timestamp" (ISO), "event_type", "guild_id"?, "message", "details" (object) }]}` | `event_type` in `BOT_READY`, `BOT_RECONNECT`, `BOT_DISCONNECT`, `GUILD_SYNC`, `ONBOARDING_ERROR`, `SETTINGS_CHANGED`, `COG_ERROR` → schrijven naar bv. `telemetry.operational_events` |

Alphapy gebruikt `CORE_API_URL` en `ALPHAPY_SERVICE_KEY`; als Core niet geconfigureerd is, valt telemetry terug op directe Supabase-write.
