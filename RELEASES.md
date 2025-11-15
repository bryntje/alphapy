# Release Notes

All notable releases of Alphapy will be documented in this file.

---

## [1.7.0] - 2025-11-15 - "Multi-Guild Horizon"

### 🎉 Major Feature: Complete Multi-Guild Support

Alphapy now supports unlimited Discord servers with complete data isolation and independent configuration for each guild.

#### What's New
- **Guild Isolation**: All features (reminders, tickets, invites, settings, onboarding) work independently per server
- **Database Schema**: Added `guild_id` columns to all tables with composite primary keys for data separation
- **API Security**: Dashboard endpoints now support optional `guild_id` filtering to prevent cross-guild data leakage
- **Migration Tools**: Safe database migration scripts with backup/restore capabilities
- **Error Handling**: Guild validation checks prevent runtime errors in DM contexts

#### Migration Summary
- ✅ **135 data entries** successfully migrated to guild `1160511689263947796`
- ✅ **Zero downtime** deployment with full backup verification
- ✅ **Complete backwards compatibility** maintained
- ✅ **Security hardening** - no cross-guild data leakage possible

#### Technical Improvements
- **Settings Service**: Enhanced to support guild-scoped configuration with per-server overrides
- **Code Architecture**: Updated all cogs to use `interaction.guild.id` for data isolation
- **Database**: Composite primary keys `(guild_id, user_id)` or `(guild_id, id)` across all tables
- **API Endpoints**: Guild filtering implemented for security in dashboard metrics

#### Security Enhancements
- **Data Isolation**: Complete separation between guild data preventing unauthorized access
- **Input Validation**: Guild existence checks prevent DM usage errors
- **API Filtering**: Dashboard endpoints properly filter by guild context

---

## [1.6.0] - 2025-10-17 - "Dashboard Foundations"

### Added
- FastAPI dashboard endpoint `/api/dashboard/metrics` exposing live bot telemetry
- Service health probe `/health` returning service status and database connectivity
- Supabase Auth integration with automatic profile bootstrap and OAuth flows

### Changed
- Project branding updated to **Innersync • Alphapy** across all documentation
- CORS origins and base URLs aligned with Innersync domain suite
- Supabase JWT validation moved to server-side verification

---

## [1.5.0] - 2025-10-04 - "Dynamic Config"

### Added
- Runtime configuration system with per-guild settings management
- Settings commands: `/config system show`, `/config embedwatcher show`, etc.
- Invite tracker with enable/disable toggle and customizable templates
- GDPR announcements with runtime settings control

### Changed
- Bot startup validation improved with early token checks
- Import flows made more robust with embed existence checks

---

## [1.4.0] - 2025-09-13 - "TicketBot & FAQ"

### Added
- Complete TicketBot system with private channels, status management, and AI assistance
- FAQ search system with autocomplete and admin management tools
- Ticket statistics and export functionality
- AI-assisted reply suggestions for support tickets

---

## Previous Releases

See [CHANGELOG.md](changelog.md) for detailed change history of all versions.
