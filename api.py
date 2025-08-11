from fastapi import FastAPI, HTTPException
import time
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import asyncpg
import config
import os
from contextlib import asynccontextmanager
from fastapi import APIRouter
from fastapi import Header, Depends

from cogs.reminders import (
    get_reminders_for_user,
    create_reminder,
    update_reminder,
    delete_reminder
)

# Security helpers
async def verify_api_key(x_api_key: str = Header(None)):
    # Enforce API key only if configured
    if getattr(config, "API_KEY", None):
        if x_api_key != config.API_KEY:
            raise HTTPException(status_code=401, detail="Unauthorized")

async def get_authenticated_user_id(x_user_id: str = Header(None)) -> str:
    if not x_user_id:
        raise HTTPException(status_code=400, detail="Missing X-User-Id header")
    return x_user_id

# Database pool
db_pool = None
router = APIRouter(prefix="/api", dependencies=[Depends(verify_api_key)])  # 👈 protect API routes

@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_pool
    db_pool = await asyncpg.create_pool(config.DATABASE_URL)
    print("✅ DB pool created")
    yield
    await db_pool.close()
    print("🔌 DB pool closed")
    
app = FastAPI(lifespan=lifespan)

# CORS settings
_allowed_origins = getattr(config, "ALLOWED_ORIGINS", [])
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins if _allowed_origins else ["*"],
    allow_credentials=True if _allowed_origins else False,
    allow_methods=["*"],
    allow_headers=["*"],
)

startup_time = time.time()

@app.get("/status")
def get_status():
    return {
        "online": True,
        "latency": 0,  # deze kunnen we later dynamisch maken
        "uptime": f"{int((time.time() - startup_time) // 60)} min"
    }

@app.get("/top-commands")
def get_top_commands():
    return {
        "create_caption": 182,
        "help": 39
    }

if __name__ == "__main__":
    import uvicorn
    import os
    uvicorn.run("api:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))

class Reminder(BaseModel):
    id: int
    name: str
    time: str  # of `datetime.time` als je deze exact gebruikt
    days: List[str]
    message: str
    channel_id: int
    user_id: str  # ← belangrijk: moet overeenkomen met je response (created_by)

# 🟢 GET reminders (eigen + global)
@router.get("/reminders/{user_id}", response_model=List[Reminder])
async def get_user_reminders(user_id: str, auth_user_id: str = Depends(get_authenticated_user_id)):
    if auth_user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    global db_pool
    try:
        async with db_pool.acquire() as conn:
            rows = await get_reminders_for_user(conn, user_id)
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "time": r["time"].strftime("%H:%M"),  # als datetime.time
                "days": r["days"],
                "message": r["message"],
                "channel_id": r["channel_id"],
                "user_id": str(r["created_by"]),  # expliciet hernoemen
            }
            for r in rows
        ]
  # ✅ must be a list, not None or dict
    except Exception as e:
        print("[ERROR] Failed to get reminders:", e)
        return []  # ✅ default to empty list on error

# 🟡 POST nieuw reminder
@router.post("/reminders")
async def add_reminder(reminder: Reminder, auth_user_id: str = Depends(get_authenticated_user_id)):
    global db_pool
    payload = reminder.dict()
    payload["created_by"] = payload.pop("user_id")
    if payload["created_by"] != auth_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    async with db_pool.acquire() as conn:
        await create_reminder(conn, payload)
    return {"success": True}

# 🟠 PUT update reminder
@router.put("/reminders")
async def edit_reminder(reminder: Reminder, auth_user_id: str = Depends(get_authenticated_user_id)):
    global db_pool
    payload = reminder.dict()
    payload["created_by"] = payload.pop("user_id")
    if payload["created_by"] != auth_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    async with db_pool.acquire() as conn:
        await update_reminder(conn, payload)
    return {"success": True}

# 🔴 DELETE reminder
@router.delete("/reminders/{reminder_id}/{created_by}")
async def remove_reminder(reminder_id: str, created_by: str, auth_user_id: str = Depends(get_authenticated_user_id)):
    if created_by != auth_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    global db_pool
    async with db_pool.acquire() as conn:
        await delete_reminder(conn, int(reminder_id), created_by)
    return {"success": True}

app.include_router(router)