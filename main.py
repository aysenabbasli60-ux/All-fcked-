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

# pending[user] = {msg_id, future, count}
pending = {}

# ---- START CLIENT ----
@app.on_event("startup")
async def startup_event():
    await client.start()
    print("✅ Client started")

# ---- HANDLE REPLIES ----
@client.on(events.NewMessage(chats=GROUP_ID))
async def handler(event):

    if not event.is_reply:
        return

    reply_to = event.reply_to_msg_id

    for user, data in list(pending.items()):

        # reply should be to our message
        if reply_to == data["msg_id"]:

            data["count"] += 1
            print(f"Reply #{data['count']}")

            # send ONLY second reply
            if data["count"] == 2:
                if not data["future"].done():
                    data["future"].set_result(event.text)

# ---- API ----
@app.get("/ask")
async def ask(user: str, text: str, key: str):

    if key != API_KEY:
        raise HTTPException(status_code=403)

    # send command
    msg = await client.send_message(GROUP_ID, f"/num {text}")

    future = asyncio.get_event_loop().create_future()

    pending[user] = {
        "msg_id": msg.id,
        "future": future,
        "count": 0
    }

    try:
        reply = await asyncio.wait_for(future, timeout=40)
    except asyncio.TimeoutError:
        reply = "Second reply not received"

    pending.pop(user, None)

    return {"reply": reply}

# ---- RUN ----
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
