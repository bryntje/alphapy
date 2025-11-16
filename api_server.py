#!/usr/bin/env python3
"""
API Server - Standalone FastAPI server voor Railway dashboard service
Deze server draait alleen de web API, niet de Discord bot.
"""

import uvicorn

if __name__ == "__main__":
    print("🚀 Starting API Server (no bot)...")
    uvicorn.run("api:app", host="0.0.0.0", port=8000)
