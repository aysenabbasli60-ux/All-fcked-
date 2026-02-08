import os
import asyncio
from datetime import datetime, timedelta
from telethon import TelegramClient, events
from fastapi import FastAPI, Query, HTTPException
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_NAME = os.getenv("SESSION_NAME")
GROUP_ID = int(os.getenv("GROUP_ID"))
API_KEY = os.getenv("API_KEY")

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
app = FastAPI()

# store by msg_id instead of user (multi-user safe)
pending = {}

# ---- START TELETHON CLIENT ----
@app.on_event("startup")
async def startup_event():
    await client.start()
    print("✅ Userbot client started")

# ---- HANDLE REPLIES ----
@client.on(events.NewMessage(chats=GROUP_ID))
async def handler(event):
    if not event.is_reply:
        return

    data = pending.get(event.reply_to_msg_id)

    if not data:
        return

    # Ignore replies before 2 sec
    if event.date < data["min_time"]:
        return

    if not data["future"].done():
        data["future"].set_result(event.text)

# ---- API ENDPOINT ----
@app.get("/ask")
async def ask(
    user: str = Query(...),
    text: str = Query(...),
    key: str = Query(...)
):
    if key != API_KEY:
        raise HTTPException(status_code=403, detail="Unauthorized")

    # Send message
    msg = await client.send_message(GROUP_ID, f"/num {text}")

    future = asyncio.get_event_loop().create_future()

    pending[msg.id] = {
        "future": future,
        "min_time": datetime.utcnow() + timedelta(seconds=2)
    }

    try:
        reply = await asyncio.wait_for(future, timeout=25)
    except asyncio.TimeoutError:
        reply = "No valid reply after 2 sec"
    finally:
        pending.pop(msg.id, None)  # cleanup

    return {"reply": reply}

# ---- RUN SERVER ----
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
