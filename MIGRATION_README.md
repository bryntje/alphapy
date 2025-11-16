# 🚀 Alphapy Multi-Guild Migration Guide

## Overview

This guide walks you through migrating your Alphapy Discord bot to support multiple guilds (servers) simultaneously. The migration adds `guild_id` columns to all database tables and updates the application code to isolate data between guilds.

## Prerequisites

- **Backup your database first!** ⚠️
- Access to your PostgreSQL database (Railway, local, etc.)
- `DATABASE_URL` environment variable set
- Python 3.9+ with required dependencies

## Migration Steps

### Step 1: Create Database Backup

**NEVER SKIP THIS STEP!** Your data will be lost if something goes wrong.

```bash
# Set your database URL
export DATABASE_URL="postgresql://username:password@host:port/database"

# Create backup
python3 backup_database.py
```

This creates a timestamped backup directory with:
- JSON exports of all table data
- SQL schema dumps
- Migration-ready backup

### Step 2: Run Database Migration

```bash
# Run the migration script
python3 migrate_guild_settings.py
```

**Important:** When prompted, review the `DEFAULT_GUILD_ID` setting:
- If `DEFAULT_GUILD_ID = 0`, existing data goes to guild 0
- Change this to your main server's ID if you want to preserve existing data for a specific guild

The migration will:
- ✅ Add `guild_id` columns to all tables
- ✅ Update primary keys to composite keys `(guild_id, ...)`
- ✅ Assign existing data to the default guild
- ✅ Maintain all existing functionality

### Step 3: Deploy Updated Code

After successful migration:
1. Deploy the updated bot code
2. Test with multiple guilds
3. Monitor for issues

## Database Schema Changes

### Before Migration
```sql
-- Single-guild tables
CREATE TABLE reminders (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    -- ... other columns
);

CREATE TABLE bot_settings (
    scope TEXT NOT NULL,
    key TEXT NOT NULL,
    value JSONB NOT NULL,
    PRIMARY KEY(scope, key)
);
```

### After Migration
```sql
-- Multi-guild tables
CREATE TABLE reminders (
    id SERIAL,
    guild_id BIGINT NOT NULL,
    name TEXT NOT NULL,
    -- ... other columns
    PRIMARY KEY(id, guild_id)
);

CREATE TABLE bot_settings (
    guild_id BIGINT NOT NULL,
    scope TEXT NOT NULL,
    key TEXT NOT NULL,
    value JSONB NOT NULL,
    PRIMARY KEY(guild_id, scope, key)
);
```

## What Changes in the Bot

### Code Changes
- All database queries now include `guild_id` filtering
- Settings are scoped per guild
- Commands validate guild context
- API endpoints support optional `guild_id` parameter

### Data Isolation
- **Reminders:** Only visible in their guild
- **Support Tickets:** Guild-specific ticket systems
- **Invite Tracking:** Per-server invite counts
- **Settings:** Guild-specific configurations
- **Onboarding:** Guild-scoped user data

## Troubleshooting

### Migration Fails
- Check database permissions
- Verify `DATABASE_URL` is correct
- Ensure no active connections during migration

### Bot Won't Start After Migration
- Verify all tables have `guild_id` columns
- Check that primary keys are updated
- Confirm bot code is deployed

### Data Loss
- Restore from backup created in Step 1
- Check migration logs for errors
- Contact support if needed

## Rollback Procedure

If you need to rollback:

1. **Restore database from backup:**
```bash
# Use your backup directory
# Import JSON files back to original schema
```

2. **Deploy previous bot version**

3. **Test functionality**

## Post-Migration Testing

After migration, test:

1. **Single Guild:** Existing functionality still works
2. **Multiple Guilds:** Data isolation between servers
3. **Settings:** Guild-specific configurations
4. **API Endpoints:** Guild filtering works
5. **Commands:** Guild validation prevents DM usage

## Support

If you encounter issues:
1. Check the logs for error messages
2. Verify database schema matches expectations
3. Test with a fresh database first
4. Contact the development team

---

**Remember:** Always backup before migration! 🛡️

The migration is designed to be safe and reversible, but accidents happen. Better safe than sorry!
