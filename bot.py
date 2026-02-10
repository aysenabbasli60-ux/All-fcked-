from flask import Flask, request, jsonify
from telethon import TelegramClient, events
import config
import asyncio
import threading
import json
import time

import os
import sys

app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False
if hasattr(app, 'json'):
    app.json.sort_keys = False

# Initialize Asyncio Loop and Telethon Client
loop = asyncio.new_event_loop()

# Check if session file exists
session_file = 'user_session.session'
if not os.path.exists(session_file):
    print(f"Error: Session file '{session_file}' not found.")
    print("Please run 'python login.py' locally to generate the session file, then upload it to your VPS.")
    sys.exit(1)

# Use file-based session 'user_session' (created by login.py)
client = TelegramClient('user_session', config.API_ID, config.API_HASH, loop=loop)

# Dictionary to store pending requests: number -> asyncio.Future
pending_requests = {}

def run_telethon():
    """
    Runs the Telethon client in a separate thread.
    """
    asyncio.set_event_loop(loop)
    print("Starting Telethon Client...")
    
    # client.start() will ask for phone number/code in terminal if not authenticated
    # With StringSession, it should be authenticated already
    client.start()
    print("Telethon Client Started!")
    
    # Register event handlers
    @client.on(events.NewMessage(chats=config.GROUP_ID))
    @client.on(events.MessageEdited(chats=config.GROUP_ID))
    async def handler(event):
        sender = await event.get_sender()
        # Check if message is from the target bot
        # config.TARGET_BOT usually does not include '@'
        target_username = config.TARGET_BOT.lstrip('@')
        
        if not sender or (sender.username and sender.username.lower() != target_username.lower()):
             # Also check if it's the bot by ID if username fails, but username is safer
             pass
        
        # We can also check if the user is the bot ID, but let's rely on username for now.
        
        text = event.message.message
        print(f"[DEBUG] Received message from {sender.username if sender else 'Unknown'}: {text[:100]}...")

        # Check for JSON in the message
        # The bot might edit the message to "only the details", so we shouldn't enforce a prefix like "TG Results".
        if "{" in text and "}" in text:
            try:
                # Extract JSON - find the first { and the last }
                json_start = text.find('{')
                json_end = text.rfind('}') + 1
                if json_start != -1 and json_end != -1:
                    json_str = text[json_start:json_end]
                    data = json.loads(json_str)
                    
                    # Check the number in the response
                    resp_number = data.get('number')
                    # Ensure resp_number is a string for comparison
                    if resp_number is not None:
                        resp_number = str(resp_number)
                        
                    print(f"[DEBUG] Extracted JSON. Number found: {resp_number}")
                    
                    # Handle cases where number is missing in JSON (Error responses)
                    # OR if there is a mismatch between extracted number and requested number,
                    # we should trust the Reply-To message if available.
                    if event.is_reply:
                        try:
                            reply_msg = await event.get_reply_message()
                            if reply_msg and reply_msg.text.startswith('/num '):
                                original_request_number = reply_msg.text.split(' ')[1].strip()
                                print(f"[DEBUG] Found Reply-To original request: {original_request_number}")
                                
                                # If we found an original request number, we can use it to override/verify
                                # This handles cases where JSON has different number or no number
                                if original_request_number in pending_requests:
                                    # If the JSON number is different, it's weird, but we should probably 
                                    # return the result to the requester anyway (maybe with a warning?)
                                    if resp_number and resp_number != original_request_number:
                                        print(f"[DEBUG] WARNING: JSON number {resp_number} != Requested {original_request_number}. Using Requested.")
                                    
                                    resp_number = original_request_number
                        except Exception as re:
                            print(f"[DEBUG] Error getting reply message: {re}")
                    
                    # Normalize response based on user requirements
                    # Ensure success is at the top by reconstructing the dict
                    final_response = {"success": data.get("success", True)}
                    for k, v in data.items():
                        if k != "success":
                            final_response[k] = v
                    
                    # Case 2: "Phone number not found"
                    if data.get("success") is False and "Phone number not found" in data.get("msg", ""):
                        final_response = {"success": False, "error": "No data found"}
                        
                    # Case 3: "UPI API request failed"
                    if data.get("status") == "error" and "UPI API request failed" in data.get("message", ""):
                        final_response = {"success": False, "error": "API Failure. Try again after 2 min"}
                        
                    # We need to match this with a pending request
                    # The pending request key is the number string passed in URL
                    # We might need to handle matching strictly or loosely
                    if resp_number and resp_number in pending_requests:
                        future = pending_requests[resp_number]
                        if not future.done():
                            print(f"[DEBUG] Matched pending request for {resp_number}. Setting result.")
                            future.set_result(final_response)
                        else:
                            print(f"[DEBUG] Request for {resp_number} already completed/cancelled.")
                    else:
                        print(f"[DEBUG] No pending request found for {resp_number}. Pending: {list(pending_requests.keys())}")
                            
            except Exception as e:
                print(f"[DEBUG] Error parsing JSON: {e}")

    client.run_until_disconnected()

# Start Telethon thread
telethon_thread = threading.Thread(target=run_telethon, daemon=True)
telethon_thread.start()

async def send_search_command(number):
    """
    Sends the command and waits for the result.
    """
    future = loop.create_future()
    pending_requests[number] = future
    
    try:
        await client.send_message(config.GROUP_ID, f"/num {number}")
        
        # Wait for result with a timeout (e.g., 15 seconds)
        # The user mentioned fetching every 0.5s, but Event approach is instant push.
        result = await asyncio.wait_for(future, timeout=150)
        return result
    except asyncio.TimeoutError:
        return {"success": False, "msg": "No data found (Timeout)", "error": "timeout"}
    except Exception as e:
        return {"success": False, "msg": "Error occurred", "error": str(e)}
    finally:
        if number in pending_requests:
            del pending_requests[number]

@app.route('/num/<number>', methods=['GET'])
def tg_search(number):
    # Run the async process in the Telethon loop safely
    if not loop.is_running():
        return jsonify({"success": False, "msg": "Bot not running"}), 500
        
    future = asyncio.run_coroutine_threadsafe(send_search_command(number), loop)
    try:
        result = future.result(timeout=20) # Wait for the thread to finish the task
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "msg": "Internal Server Error", "error": str(e)})

if __name__ == '__main__':
    import os
    
    port = int(os.environ.get("PORT", 5000))
    print(f"Flask server starting on port {port}...")

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False
    )
    
