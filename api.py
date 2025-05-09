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

from cogs.reminders import (
    get_reminders_for_user,
    create_reminder,
    update_reminder,
    delete_reminder
)

db_conn = None
router = APIRouter(prefix="/api")  # 👈

@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_conn
    db_conn = await asyncpg.connect(config.DATABASE_URL)
    print("✅ DB connected")
    yield
    await db_conn.close()
    print("🔌 DB connection closed")
    
app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # of specifieker: ["http://localhost:3000"]
    allow_credentials=True,
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
async def get_user_reminders(user_id: str):
    global db_conn
    try:
        rows = await get_reminders_for_user(db_conn, int(user_id))
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
async def add_reminder(reminder: Reminder):
    global db_conn
    await create_reminder(db_conn, reminder.dict())
    return {"success": True}

# 🟠 PUT update reminder
@router.put("/reminders")
async def edit_reminder(reminder: Reminder):
    global db_conn
    await update_reminder(db_conn, reminder.dict())
    return {"success": True}

# 🔴 DELETE reminder
@router.delete("/reminders/{reminder_id}/{created_by}")
async def remove_reminder(reminder_id: str, created_by: str):
    global db_conn
    await delete_reminder(db_conn, int(reminder_id), created_by)
    return {"success": True}

app.include_router(router)