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

TARGET_REPLY_INDEX = 2

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
app = FastAPI()

# pending[user] = {msg_id, future, replies[], last_reply_id}
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

    reply_to_id = event.reply_to_msg_id

    for user, data in list(pending.items()):

        # Accept reply if it's to:
        # 1) original message
        # 2) OR last bot reply (reply chain)
        if reply_to_id in [data["msg_id"], data.get("last_reply_id")]:

            data["replies"].append(event.text)
            data["last_reply_id"] = event.id

            print(f"📩 Reply #{len(data['replies'])}")

            if len(data["replies"]) >= TARGET_REPLY_INDEX:
                if not data["future"].done():
                    data["future"].set_result(
                        data["replies"][TARGET_REPLY_INDEX - 1]
                    )

# ---- API ENDPOINT ----
@app.get("/ask")
async def ask(
    user: str = Query(...),
    text: str = Query(...),
    key: str = Query(...)
):
    if key != API_KEY:
        raise HTTPException(status_code=403, detail="Unauthorized")

    msg = await client.send_message(GROUP_ID, f"/num {text}")

    loop = asyncio.get_event_loop()
    future = loop.create_future()

    pending[user] = {
        "msg_id": msg.id,
        "future": future,
        "replies": [],
        "last_reply_id": None
    }

    try:
        reply = await asyncio.wait_for(future, timeout=40)
    except asyncio.TimeoutError:
        reply = "Timeout: Not enough replies"

    pending.pop(user, None)

    return {"reply": reply}

# ---- RUN SERVER ----
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
