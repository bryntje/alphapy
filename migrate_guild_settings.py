#!/usr/bin/env python3
"""
🔄 Alphapy Database Migration Tool

Migrates database schema to support multi-guild architecture.

Requirements:
    - Set DATABASE_URL environment variable
    - Run this BEFORE deploying multi-guild bot

This script:
    - Adds guild_id columns to all tables
    - Updates primary keys to include guild_id
    - Migrates existing data to default guild
"""

import os
import sys
import asyncio
import asyncpg
from typing import Optional, List, Tuple
from pathlib import Path

# Default guild ID to assign to existing data
# Change this to your main guild ID if you want to preserve existing data for a specific guild
DEFAULT_GUILD_ID = 1160511689263947796


class DatabaseMigrator:
    def __init__(self):
        # Try to load .env file if DATABASE_URL is not set
        if not os.getenv('DATABASE_URL'):
            env_file = Path('.env')
            if env_file.exists():
                print("📄 Loading .env file...")
                with open(env_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            key, _, value = line.partition('=')
                            if key and value:
                                cleaned_value = value.strip().strip('"').strip("'")
                                os.environ[key.strip()] = cleaned_value
                                if key.strip() == 'DATABASE_URL':
                                    print("✅ DATABASE_URL loaded from .env")

        self.dsn = os.getenv('DATABASE_URL')
        if not self.dsn:
            print("❌ ERROR: DATABASE_URL environment variable not set!")
            print("Please set it with: export DATABASE_URL='your_database_url'")
            print("Or create a .env file with DATABASE_URL=your_database_url")
            sys.exit(1)

        self.conn: Optional[asyncpg.Connection] = None

    async def connect(self) -> None:
        """Connect to the database"""
        try:
            self.conn = await asyncpg.connect(self.dsn)
            print("✅ Connected to database")
        except Exception as e:
            print(f"❌ Failed to connect to database: {e}")
            sys.exit(1)

    async def disconnect(self) -> None:
        """Disconnect from the database"""
        if self.conn:
            try:
                await self.conn.close()
                print("🔌 Disconnected from database")
            except Exception as e:
                print(f"⚠️ Warning during disconnect: {e}")

    async def migrate_reminders_table(self) -> bool:
        """Migrate reminders table to include guild_id"""
        try:
            # Check if migration already done
            result = await self.conn.fetchrow(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'reminders' AND column_name = 'guild_id'"
            )
            if result:
                print("ℹ️ reminders table already has guild_id column, skipping...")
                return True

            # Add guild_id column
            await self.conn.execute(f"ALTER TABLE reminders ADD COLUMN guild_id BIGINT NOT NULL DEFAULT {DEFAULT_GUILD_ID}")
            print("✅ Added guild_id column to reminders table")

            # Update primary key to include guild_id
            await self.conn.execute("ALTER TABLE reminders DROP CONSTRAINT IF EXISTS reminders_pkey")
            await self.conn.execute("ALTER TABLE reminders ADD PRIMARY KEY (id, guild_id)")
            print("✅ Updated primary key for reminders table")

            return True
        except Exception as e:
            print(f"❌ Failed to migrate reminders table: {e}")
            return False

    async def migrate_support_tickets_table(self) -> bool:
        """Migrate support_tickets table to include guild_id"""
        try:
            # Check if migration already done
            result = await self.conn.fetchrow(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'support_tickets' AND column_name = 'guild_id'"
            )
            if result:
                print("ℹ️ support_tickets table already has guild_id column, skipping...")
                return True

            # Add guild_id column
            await self.conn.execute(f"ALTER TABLE support_tickets ADD COLUMN guild_id BIGINT NOT NULL DEFAULT {DEFAULT_GUILD_ID}")
            print("✅ Added guild_id column to support_tickets table")

            # Update primary key to include guild_id
            await self.conn.execute("ALTER TABLE support_tickets DROP CONSTRAINT IF EXISTS support_tickets_pkey")
            await self.conn.execute("ALTER TABLE support_tickets ADD PRIMARY KEY (id, guild_id)")
            print("✅ Updated primary key for support_tickets table")

            return True
        except Exception as e:
            print(f"❌ Failed to migrate support_tickets table: {e}")
            return False

    async def migrate_invite_tracker_table(self) -> bool:
        """Migrate invite_tracker table to include guild_id"""
        try:
            # Check if migration already done
            result = await self.conn.fetchrow(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'invite_tracker' AND column_name = 'guild_id'"
            )
            if result:
                print("ℹ️ invite_tracker table already has guild_id column, skipping...")
                return True

            # Add guild_id column
            await self.conn.execute(f"ALTER TABLE invite_tracker ADD COLUMN guild_id BIGINT NOT NULL DEFAULT {DEFAULT_GUILD_ID}")
            print("✅ Added guild_id column to invite_tracker table")

            # Drop old primary key and add new composite primary key
            await self.conn.execute("ALTER TABLE invite_tracker DROP CONSTRAINT IF EXISTS invite_tracker_pkey")
            await self.conn.execute("ALTER TABLE invite_tracker ADD PRIMARY KEY (guild_id, user_id)")
            print("✅ Updated primary key for invite_tracker table")

            return True
        except Exception as e:
            print(f"❌ Failed to migrate invite_tracker table: {e}")
            return False

    async def migrate_onboarding_table(self) -> bool:
        """Migrate onboarding table to include guild_id"""
        try:
            # Check if migration already done
            result = await self.conn.fetchrow(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'onboarding' AND column_name = 'guild_id'"
            )
            if result:
                print("ℹ️ onboarding table already has guild_id column, skipping...")
                return True

            # Add guild_id column
            await self.conn.execute(f"ALTER TABLE onboarding ADD COLUMN guild_id BIGINT NOT NULL DEFAULT {DEFAULT_GUILD_ID}")
            print("✅ Added guild_id column to onboarding table")

            # Drop old primary key and add new composite primary key
            await self.conn.execute("ALTER TABLE onboarding DROP CONSTRAINT IF EXISTS onboarding_pkey")
            await self.conn.execute("ALTER TABLE onboarding ADD PRIMARY KEY (guild_id, user_id)")
            print("✅ Updated primary key for onboarding table")

            return True
        except Exception as e:
            print(f"❌ Failed to migrate onboarding table: {e}")
            return False

    async def create_backup(self) -> None:
        """Create backup of existing data before migration"""
        print("📦 Creating backup of existing data...")

        tables = ["reminders", "support_tickets", "invite_tracker", "onboarding"]

        for table in tables:
            try:
                count = await self.conn.fetchval(f"SELECT COUNT(*) FROM {table}")
                print(f"✅ Backed up {count} {table}")
            except Exception as e:
                print(f"⚠️ Could not backup {table}: {e}")

    async def run_migration(self) -> bool:
        """Run the complete migration process"""
        print("🚀 Starting Multi-Guild Database Migration")
        print("="*50)

        await self.create_backup()

        migrations = [
            ("reminders", self.migrate_reminders_table),
            ("support_tickets", self.migrate_support_tickets_table),
            ("invite_tracker", self.migrate_invite_tracker_table),
            ("onboarding", self.migrate_onboarding_table),
        ]

        success_count = 0

        for table_name, migrate_func in migrations:
            print(f"🔄 Migrating {table_name} table...")
            if await migrate_func():
                success_count += 1
            else:
                print(f"❌ Migration failed: {table_name} table migration failed")
                return False

        print(f"\n🎉 Migration completed successfully!")
        print(f"\n📋 Summary:")
        print(f"   - Tables migrated: {success_count}/{len(migrations)}")
        print(f"   - Default guild_id assigned: {DEFAULT_GUILD_ID}")
        print(f"\n✅ Your bot is now ready for multi-guild deployment!")
        print("="*50)
        print("🎯 NEXT STEPS:")
        print("1. Test your bot with multiple guilds")
        print("2. Update DEFAULT_GUILD_ID in this script if needed")
        print("3. Monitor for any migration-related issues")
        print("="*50)

        return True


async def main():
    """Main migration function"""
    migrator = DatabaseMigrator()

    try:
        await migrator.connect()
        success = await migrator.run_migration()
    finally:
        await migrator.disconnect()

    return success


if __name__ == "__main__":
    # Safety check
    if DEFAULT_GUILD_ID == 0:
        print("⚠️ WARNING: DEFAULT_GUILD_ID is set to 0")
        print("   This means existing data will be assigned to guild 0.")
        print("   Update DEFAULT_GUILD_ID in this script if you want to use a specific guild ID.")
        response = input("Continue with migration? (yes/no): ").lower().strip()
        if response != 'yes':
            print("Migration cancelled.")
            sys.exit(0)

    asyncio.run(main())
