import asyncio
import time
import os
from fastapi import FastAPI, Query
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# ===== CONFIG FROM ENV =====

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION = os.getenv("SESSION")
GROUP_ID = int(os.getenv("GROUP_ID"))

TIMEOUT = 20

# ===========================

app = FastAPI()

client = TelegramClient(
    StringSession(SESSION),
    API_ID,
    API_HASH
)

reply_store = {}
lock = asyncio.Lock()


@app.on_event("startup")
async def startup():
    await client.start()
    print("✅ Telegram client started")


@client.on(events.NewMessage(chats=GROUP_ID))
async def handler(event):
    text = event.raw_text.strip()
    if not text:
        return

    async with lock:
        for key in reply_store:
            data = reply_store[key]
            if not data["done"]:
                data["count"] += 1

                # SECOND REPLY ONLY
                if data["count"] == 2:
                    data["reply"] = text
                    data["done"] = True
                break


@app.get("/")
async def root():
    return {"status": "running"}


@app.get("/ask")
async def ask(text: str = Query(...)):
    uid = str(time.time())

    async with lock:
        reply_store[uid] = {
            "count": 0,
            "reply": None,
            "done": False
        }

    await client.send_message(GROUP_ID, text)

    start = time.time()

    while time.time() - start < TIMEOUT:
        async with lock:
            if reply_store[uid]["done"]:
                r = reply_store[uid]["reply"]
                del reply_store[uid]
                return {"success": True, "reply": r}

        await asyncio.sleep(0.5)

    async with lock:
        del reply_store[uid]

    return {"success": False, "error": "Timeout"}


# Render needs this
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
