import sqlite3
import asyncpg
import config
import asyncio

async def migrate_gdpr_data():
    """Migreert GDPR-acceptatiegegevens van SQLite naar PostgreSQL."""
    
    # ✅ Stap 1: Connectie met SQLite (oude database)
    sqlite_conn = sqlite3.connect("onboarding.db")
    sqlite_cursor = sqlite_conn.cursor()
    
    # ✅ Stap 2: Haal alle GDPR-gegevens op
    sqlite_cursor.execute("SELECT user_id, accepted, timestamp FROM gdpr_acceptance")
    data = sqlite_cursor.fetchall()
    
    if not data:
        print("❌ Geen GDPR-data gevonden in SQLite.")
        return
    
    print(f"📦 {len(data)} GDPR-records gevonden, starten met migratie...")

    # ✅ Stap 3: Connectie met PostgreSQL (nieuwe database)
    pg_conn = await asyncpg.connect(config.DATABASE_URL)

    for user_id, accepted, timestamp in data:
        # ✅ Stap 4: Data invoegen in PostgreSQL
        await pg_conn.execute(
            """
            INSERT INTO gdpr_acceptance (user_id, accepted, timestamp)
            VALUES ($1, $2, $3)
            ON CONFLICT(user_id) DO UPDATE SET accepted = $2, timestamp = $3;
            """,
            int(user_id), accepted, timestamp
        )
        print(f"✅ GDPR-data gemigreerd voor {user_id}")

    # ✅ Stap 5: Sluit connecties
    await pg_conn.close()
    sqlite_conn.close()

    print("🎉 Migratie voltooid!")

# ✅ Run migratie
asyncio.run(migrate_gdpr_data())
