from fastapi import FastAPI
import time
from fastapi.middleware.cors import CORSMiddleware

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
