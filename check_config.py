#!/usr/bin/env python3
"""Check premium config values."""
import os
import sys

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=== Premium Config Check ===")

# Try to load dotenv if available
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ Loaded environment variables from .env")
except ImportError:
    print("⚠️  dotenv not available, using system environment")

# Try to import config
try:
    try:
        import config_local as config
        print("✅ Using config_local")
    except ImportError:
        import config
        print("✅ Using config")
except ImportError as e:
    print(f"❌ Failed to import config: {e}")
    sys.exit(1)

# Check core configuration
core_url = getattr(config, 'CORE_API_URL', '')
api_key = getattr(config, 'ALPHAPY_SERVICE_KEY', '')
checkout_url = getattr(config, 'PREMIUM_CHECKOUT_URL', '')

print(f"CORE_API_URL: {'SET' if core_url else 'NOT SET'}")
print(f"ALPHAPY_SERVICE_KEY: {'SET' if api_key else 'NOT SET'}")
print(f"PREMIUM_CHECKOUT_URL: {'SET' if checkout_url else 'NOT SET'}")

# Test Core-API connectivity if configured
if core_url and api_key:
    print("\n=== Testing Core-API Connection ===")
    try:
        import httpx
        response = httpx.post(
            f"{core_url}/api/premium/checkout",
            params={"tier": "monthly", "guild_id": 0, "user_id": 123456},
            headers={"X-API-Key": api_key},
            timeout=10.0
        )
        print(f"Response status: {response.status_code}")
        if response.is_success:
            try:
                data = response.json()
                print("✅ Core-API connection successful")
                print(f"Response preview: {str(data)[:200]}...")
            except Exception:
                print("✅ Core-API connection successful (non-JSON response)")
        else:
            print(f"❌ Core-API error: {response.text}")
    except ImportError:
        print("❌ httpx not available for testing")
    except Exception as e:
        print(f"❌ Connection error: {e}")
elif checkout_url:
    print("\n=== Using Fallback Checkout URL ===")
    print(f"Fallback URL configured: {checkout_url}")
else:
    print("\n=== Configuration Incomplete ===")
    print("⚠️  Neither Core-API nor fallback checkout URL configured")
    print("Set CORE_API_URL + ALPHAPY_SERVICE_KEY for full functionality")
    print("Or set PREMIUM_CHECKOUT_URL for basic checkout links")

print("\n=== Configuration Summary ===")
if core_url and api_key:
    print("✅ Full premium functionality available")
elif checkout_url:
    print("⚠️  Basic premium checkout available (limited functionality)")
else:
    print("❌ Premium functionality disabled")

print("\n=== Performance Check ===")

# Test database connection performance
try:
    import asyncpg
    import time
    import asyncio

    async def test_db_performance():
        dsn = getattr(config, "DATABASE_URL", None)
        if not dsn:
            print("❌ No DATABASE_URL configured")
            return

        print("Testing database connection performance...")

        # Test connection time
        start_time = time.time()
        conn = await asyncpg.connect(dsn)
        connect_time = (time.time() - start_time) * 1000
        print(f"✅ Database connection: {connect_time:.1f}ms")

        # Test simple query
        start_time = time.time()
        result = await conn.fetchval("SELECT COUNT(*) FROM information_schema.tables")
        query_time = (time.time() - start_time) * 1000
        print(f"✅ Simple query: {query_time:.1f}ms (tables: {result})")

        await conn.close()

    asyncio.run(test_db_performance())

except ImportError:
    print("⚠️ asyncpg not available for performance testing")
except Exception as e:
    print(f"❌ Database performance test failed: {e}")

# Test API connectivity if configured
if core_url and api_key:
    print("\nTesting Core-API performance...")
    try:
        import httpx
        start_time = time.time()
        response = httpx.get(
            f"{core_url.rstrip('/')}/health",
            headers={"X-API-Key": api_key},
            timeout=5.0
        )
        api_time = (time.time() - start_time) * 1000
        if response.is_success:
            print(f"✅ Core-API health check: {api_time:.1f}ms")
        else:
            print(f"⚠️ Core-API health check: {api_time:.1f}ms (status: {response.status_code})")
    except Exception as e:
        print(f"❌ Core-API performance test failed: {e}")

print("\nConfig check complete!")
