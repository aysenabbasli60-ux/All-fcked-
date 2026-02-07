import os
import asyncio
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
pending = {}

# ---- START TELETHON CLIENT ----
@app.on_event("startup")
async def startup_event():
    await client.start()
    print("✅ Userbot client started")

# ---- HANDLE REPLIES ----
@client.on(events.NewMessage(chats=GROUP_ID))
async def handler(event):
    if event.is_reply:
        reply_to_id = event.reply_to_msg_id
        for user, data in pending.copy().items():
            if data['msg_id'] == reply_to_id:
                if not data['future'].done():
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

    # Wait for reply
    future = asyncio.get_event_loop().create_future()
    pending[user] = {"msg_id": msg.id, "future": future}

    try:
        reply = await asyncio.wait_for(future, timeout=20)
    except asyncio.TimeoutError:
        reply = "No reply yet"

    pending.pop(user, None)
    return {"reply": reply}

# ---- RUN SERVER ----
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
