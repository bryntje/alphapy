from fastapi import FastAPI, HTTPException
import time
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import asyncpg
import config

from cogs.reminders import (
    get_reminders_for_user,
    create_reminder,
    update_reminder,
    delete_reminder
)




app = FastAPI()
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
    id: str
    user_id: str
    name: str
    time: str  # "HH:MM"
    days: List[str]
    message: str
    channel_id: str
    # recurrence: Literal["once", "daily", "weekly"] # Optional if implemented

@app.get("/api/reminders/{user_id}", response_model=List[Reminder])
async def get_user_reminders(user_id: str):
    conn = await asyncpg.connect(config.DATABASE_URL)
    rows = await get_reminders_for_user(conn, user_id)
    await conn.close()
    return [dict(r) for r in rows]

@app.post("/api/reminders")
async def add_reminder(reminder: Reminder):
    conn = await asyncpg.connect(config.DATABASE_URL)
    await create_reminder(conn, reminder.dict())
    await conn.close()
    return {"success": True}

@app.put("/api/reminders")
async def edit_reminder(reminder: Reminder):
    conn = await asyncpg.connect(config.DATABASE_URL)
    await update_reminder(conn, reminder.dict())
    await conn.close()
    return {"success": True}

@app.delete("/api/reminders/{reminder_id}/{user_id}")
async def remove_reminder(reminder_id: str, user_id: str):
    conn = await asyncpg.connect(config.DATABASE_URL)
    await delete_reminder(conn, int(reminder_id), user_id)
    await conn.close()
    return {"success": True}
