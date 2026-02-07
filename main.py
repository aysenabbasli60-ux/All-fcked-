import os
import asyncio
from telethon import TelegramClient, events
from fastapi import FastAPI, Query, HTTPException
from dotenv import load_dotenv

load_dotenv()

# ---- ENVIRONMENT VARIABLES ----
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_NAME = os.getenv("SESSION_NAME")   # Example: 'session'
GROUP_ID = int(os.getenv("GROUP_ID"))      # Example: -1001234567890
API_KEY = os.getenv("API_KEY")

# ---- TELETHON CLIENT ----
client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

# ---- FASTAPI ----
app = FastAPI()
pending = {}  # store user queries

# ---- START TELETHON CLIENT ----
async def start_client():
    await client.start()
    print("✅ Userbot client started")

loop = asyncio.get_event_loop()
loop.create_task(start_client())

# ---- HANDLE REPLIES IN GROUP ----
@client.on(events.NewMessage(chats=GROUP_ID))
async def handler(event):
    if event.is_reply:
        reply_to_id = event.reply_to_msg_id
        for user, data in pending.items():
            if data['msg_id'] == reply_to_id:
                data['future'].set_result(event.text)

# ---- API ENDPOINT ----
@app.get("/ask")
async def ask(
    user: str = Query(...),
    text: str = Query(...),
    key: str = Query(...)
):
    if key != API_KEY:
        raise HTTPException(status_code=403, detail="Unauthorized")

    # Send message to Telegram group
    msg = await client.send_message(GROUP_ID, f"/tg {text}")

    # Prepare future to wait for reply
    future = loop.create_future()
    pending[user] = {"msg_id": msg.id, "future": future}

    try:
        # Wait max 20 sec for reply
        reply = await asyncio.wait_for(future, timeout=20)
    except asyncio.TimeoutError:
        reply = "No reply yet"

    pending.pop(user, None)
    return {"reply": reply}

# ---- RUN SERVER ----
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
