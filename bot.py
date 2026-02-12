from flask import Flask, jsonify
from telethon import TelegramClient, events
import config
import asyncio
import threading
import json
import os
import sys
import time

app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False
if hasattr(app, 'json'):
    app.json.sort_keys = False

loop = asyncio.new_event_loop()

# ===== SESSION CHECK =====
session_file = 'user_session.session'
if not os.path.exists(session_file):
    print(f"Error: Session file '{session_file}' not found.")
    sys.exit(1)

client = TelegramClient('user_session', config.API_ID, config.API_HASH, loop=loop)

pending_requests = {}
cache = {}  # simple memory cache

CACHE_TTL = 300  # 5 min cache

# ===== TELETHON THREAD =====
def run_telethon():
    asyncio.set_event_loop(loop)
    print("Starting Telethon Client...")

    client.start()

    # 🔥 Preload entity (BIG SPEED BOOST)
    try:
        loop.run_until_complete(client.get_entity(config.GROUP_ID))
    except:
        pass

    print("Telethon Client Started!")

    @client.on(events.NewMessage(chats=config.GROUP_ID))
    @client.on(events.MessageEdited(chats=config.GROUP_ID))
    async def handler(event):

        sender = await event.get_sender()

        # ✅ Strong sender filter (FAST)
        if not sender or not sender.username:
            return

        if sender.username.lower() != config.TARGET_BOT.lstrip('@').lower():
            return

        text = event.message.message or ""

        # ✅ Fast JSON detection
        if not text.startswith("{"):
            return

        try:
            data = json.loads(text)

            resp_number = str(data.get("number", ""))

            # Reply match fix
            if event.is_reply:
                try:
                    reply = await event.get_reply_message()
                    if reply and reply.text.startswith('/tg '):
                        resp_number = reply.text.split(' ')[1].strip()
                except:
                    pass

            # Normalize response
            final = {"success": data.get("success", True)}
            for k, v in data.items():
                if k != "success":
                    final[k] = v

            # Custom error handling
            if data.get("success") is False and "Phone number not found" in data.get("msg", ""):
                final = {"success": False, "error": "No data found"}

            if data.get("status") == "error":
                final = {"success": False, "error": "API Failure"}

            # ✅ Save in cache
            cache[resp_number] = {
                "data": final,
                "time": time.time()
            }

            if resp_number in pending_requests:
                fut = pending_requests[resp_number]
                if not fut.done():
                    fut.set_result(final)

        except:
            pass

    client.run_until_disconnected()

threading.Thread(target=run_telethon, daemon=True).start()

# ===== SEND COMMAND =====
async def send_search_command(number):

    # ✅ Cache check
    if number in cache:
        if time.time() - cache[number]["time"] < CACHE_TTL:
            return cache[number]["data"]

    fut = loop.create_future()
    pending_requests[number] = fut

    try:
        await client.send_message(config.GROUP_ID, f"/num {number}")

        result = await asyncio.wait_for(fut, timeout=20)
        return result

    except asyncio.TimeoutError:
        return {"success": False, "error": "timeout"}

    except Exception as e:
        return {"success": False, "error": str(e)}

    finally:
        pending_requests.pop(number, None)

# ===== API ROUTE =====
@app.route('/tg/<number>', methods=['GET'])
def tg_search(number):

    if not loop.is_running():
        return jsonify({"success": False, "error": "Bot not running"}), 500

    fut = asyncio.run_coroutine_threadsafe(send_search_command(number), loop)

    try:
        result = fut.result(timeout=25)
        return jsonify(result)
    except:
        return jsonify({"success": False, "error": "server timeout"})

# ===== MAIN =====
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    print(f"Server running on {port}")

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False
                        )
