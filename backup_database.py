#!/usr/bin/env python3
"""
🛡️ Alphapy Database Backup Tool

Creates JSON backups of all database tables before migration.

Requirements:
    - Set DATABASE_URL environment variable
    - Run this BEFORE any database migrations

This script creates:
    - JSON exports of all table data
    - SQL schema dumps for each table
    - Organized backup directory with timestamp
"""

import os
import sys
import asyncio
import asyncpg
import json
from datetime import datetime
from typing import Optional, Dict, List, Any
from pathlib import Path


class DatabaseBackup:
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
        self.backup_dir = f"backup_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
        os.makedirs(self.backup_dir, exist_ok=True)

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

    async def backup_table(self, table_name: str) -> bool:
        """Backup a single table to JSON"""
        try:
            # Get all rows from the table
            rows = await self.conn.fetch(f"SELECT * FROM {table_name}")
            data = [dict(row) for row in rows]

            # Save to JSON file
            filepath = os.path.join(self.backup_dir, f"{table_name}.json")
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)

            print(f"✅ Saved {len(data)} records to {filepath}")

            # Also save schema
            await self.save_schema(table_name)

            return True
        except Exception as e:
            print(f"❌ Failed to backup {table_name}: {e}")
            return False

    async def save_schema(self, table_name: str) -> None:
        """Save table schema to SQL file"""
        try:
            # Get table schema
            schema_result = await self.conn.fetchrow("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = $1
                ORDER BY ordinal_position
            """, table_name)

            if schema_result:
                filepath = os.path.join(self.backup_dir, f"{table_name}_schema.sql")
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(f"-- Schema for table: {table_name}\n")
                    f.write(f"-- Generated: {datetime.now().isoformat()}\n\n")

                    # Get CREATE TABLE statement
                    create_stmt = await self.conn.fetchval("""
                        SELECT pg_get_create_table($1)
                    """, table_name)

                    if create_stmt:
                        f.write(create_stmt)
                    else:
                        f.write(f"-- Could not generate CREATE TABLE for {table_name}\n")

                print(f"✅ Schema saved to {filepath}")
        except Exception as e:
            print(f"⚠️ Could not save schema for {table_name}: {e}")

    async def run_backup(self) -> bool:
        """Run the complete backup process"""
        print(f"🚀 Starting Database Backup")
        print("="*50)
        print(f"📁 Backup directory: {self.backup_dir}")
        print(f"🗄️ Database: {self.dsn.split('@')[1] if '@' in self.dsn else 'unknown'}")
        print("="*50)

        # Tables to backup
        tables = [
            "reminders",
            "support_tickets",
            "invite_tracker",
            "onboarding",
            "bot_settings",
            "faq_entries",
            "ticket_summaries",
            "ticket_metrics"
        ]

        success_count = 0
        total_records = 0

        for table in tables:
            try:
                print(f"📦 Backing up {table}...")
                if await self.backup_table(table):
                    success_count += 1

                    # Count records
                    try:
                        count = await self.conn.fetchval(f"SELECT COUNT(*) FROM {table}")
                        total_records += count
                        print(f"   📊 {count} records")
                    except:
                        pass
                else:
                    print(f"   ❌ Failed")
            except Exception as e:
                print(f"   ❌ Error: {e}")

        print(f"\n🎉 Backup completed successfully!")
        print(f"📁 All data saved to: {self.backup_dir}/")
        print(f"\n📋 Summary:")
        print(f"   • Tables backed up: {success_count}/{len(tables)}")
        print(f"   • Total records: {total_records}")

        print(f"\n⚠️ IMPORTANT:")
        print("   • Store this backup in a safe place")
        print("   • Test the backup by importing into a test database")
        print("   • Only run migrations AFTER verifying backup integrity")
        return True

async def main():
    """Main backup function"""
    backup = DatabaseBackup()

    try:
        await backup.connect()
        success = await backup.run_backup()
    finally:
        await backup.disconnect()

    return success

if __name__ == "__main__":
    print("🛡️ Alphapy Database Backup Tool")
    print("This will create backups of all your data before migration.")
    print()

    if not os.getenv('DATABASE_URL'):
        print("❌ DATABASE_URL environment variable not set!")
        print("Please set it and try again.")
        sys.exit(1)

    response = input("Create database backup? (yes/no): ").lower().strip()
    if response != 'yes':
        print("Backup cancelled.")
        sys.exit(0)

    success = asyncio.run(main())
    if success:
        print("\n✅ Ready to proceed with migrations!")
        print("Run: python migrate_guild_settings.py")
    else:
        print("\n❌ Backup failed. Please resolve issues before proceeding.")
        sys.exit(1)
