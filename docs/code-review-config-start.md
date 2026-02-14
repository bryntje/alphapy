# Code review: `/config start` wizard

Review van de setup-wizard in `cogs/configuration.py` (SETUP_STEPS, SetupWizardView, config_start) tegen AGENTS.md en de Embed Styling Guide.

---

## Checklist

### Algemeen
- [x] Code volgt bestaande patronen (Configuration cog, settings.set, _send_audit_log)
- [x] Geen hardcoded secrets of credentials
- [x] Error handling voor settings.set / edit_original_response (Suggestion 2 toegepast)
- [x] Geen print; logging via _send_audit_log voor config changes

### Embeds
- [x] **Timestamp** – Toegevoegd: `timestamp=datetime.now(BRUSSELS_TZ)` op alle wizard-embeds (Suggestion 1 toegepast).
- [x] Geen user input in embed content (alleen vaste Engelse strings en step.label); field "Configured in this session" gebruikt onze eigen labels.
- [x] Field values onder 1024 (korte regels).

### Cogs
- [x] config_start gebruikt @requires_admin() en guild check
- [x] Ephemeral response correct
- [x] Geen BRUSSELS_TZ in deze cog elders; wizard-embeds wel timestamp toevoegen voor consistentie

### Security
- [x] Admin check via requires_admin()
- [x] Alleen de starter kan de wizard gebruiken: `_ensure_same_user` in alle callbacks (Nice to have 1 toegepast).
- [x] Geen gevoelige data in logs

---

## Feedback

### Suggestion 1 – Timestamp op embeds ✅ Toegepast
- `timestamp=datetime.now(BRUSSELS_TZ)` toegevoegd op alle wizard-embeds; import BRUSSELS_TZ en datetime.

### Suggestion 2 – Error handling in wizard ✅ Toegepast
- `_apply_and_next`: try/except rond settings.set en _send_audit_log; bij fout log + followup. try/except rond _render_step; bij fout log + followup.
- `_on_skip`: try/except rond _render_step.
- `on_timeout`: exception loggen met log_with_guild i.p.v. pass.

### Suggestion 3 – Robuustheid resolved data ✅ Toegepast
- `_get_resolved_channels` en `_get_resolved_role`: try/except (ValueError, TypeError, IndexError) rond int(values[0]); return None bij fout.

### Nice to have 1 – Alleen starter mag wizard bedienen ✅ Toegepast
- `_ensure_same_user(interaction)` toegevoegd; aanroep aan het begin van _on_channel_select, _on_role_select, _on_skip. Bij andere gebruiker: ephemeral "Only the user who started the setup can use this."

### Nice to have 2 – Logging ✅ Toegepast
- Debug-log bij start: `log_with_guild("Setup wizard started (guild_id=..., user_id=...)", guild_id, "debug")`.
- Debug-log bij complete: `log_with_guild("Setup wizard complete (guild_id=..., configured=N steps)", ..., "debug")`.

---

## Samenvatting

| Prioriteit | Item | Actie |
|------------|------|--------|
| Suggestion | Timestamp op embeds | BRUSSELS_TZ + datetime toevoegen |
| Suggestion | Error handling | try/except in _apply_and_next, _render_step, on_timeout |
| Suggestion | int(values[0]) | try/except in _get_resolved_* |
| Nice to have | Same-user check | interaction.user.id == self.user_id in callbacks |
| Nice to have | Logging | ✅ log_with_guild bij start/complete |

Geen critical issues; na toepassen van de suggestions is de code in lijn met de projectstandaarden.
