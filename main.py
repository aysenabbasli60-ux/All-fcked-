import os
import asyncio
from telethon import TelegramClient, events
from fastapi import FastAPI, Query, HTTPException
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_NAME = os.getenv("SESSION_NAME")
GROUP_ID = int(os.getenv("GROUP_ID"))
API_KEY = os.getenv("API_KEY")

# Initialize FastAPI
app = FastAPI()
client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

# Pending queries storage
pending = {}

# Start Telethon client
async def start_client():
    await client.start()
    print("Userbot client started")

loop = asyncio.get_event_loop()
loop.create_task(start_client())

# Listen for replies in group
@client.on(events.NewMessage(chats=GROUP_ID))
async def handler(event):
    if event.is_reply:
        reply_to_id = event.reply_to_msg_id
        for user, data in pending.items():
            if data['msg_id'] == reply_to_id:
                data['future'].set_result(event.text)

# API Endpoint
@app.get("/ask")
async def ask(
    user: str = Query(...),
    text: str = Query(...),
    key: str = Query(...)
):
    if key != API_KEY:
        raise HTTPException(status_code=403, detail="Unauthorized")

    # Send query to group
    msg = await client.send_message(GROUP_ID, f"/tg {text}")

    # Wait for reply
    future = loop.create_future()
    pending[user] = {"msg_id": msg.id, "future": future}

    try:
        reply = await asyncio.wait_for(future, timeout=20)
    except asyncio.TimeoutError:
        reply = "No reply yet"

    pending.pop(user, None)
    return {"reply": reply}

# Run server on Render port
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
