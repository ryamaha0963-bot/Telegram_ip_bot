"""
Telegram IP Grabber Bot - Extra Debugging
"""

import asyncio
import json
import logging
import os
import sqlite3
import sys
import tempfile
import zipfile
from typing import Dict, Optional

from pyrogram import Client, filters, idle
from pyrogram.raw import functions, types
from pyrogram.types import InlineQueryResultArticle, InputTextMessageContent
from aiohttp import web

# ---------- Logging ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
LOGGER = logging.getLogger(__name__)

# ---------- Environment ----------
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not API_ID or not API_HASH or not BOT_TOKEN:
    LOGGER.error("Missing environment variables")
    sys.exit(1)

try:
    API_ID = int(API_ID)
except ValueError:
    LOGGER.error("API_ID must be integer")
    sys.exit(1)

OWNER_ID = int(os.getenv("OWNER_ID", 0))

# ---------- Database (same as before) ----------
DB_PATH = "sessions.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            sid INTEGER PRIMARY KEY AUTOINCREMENT,
            session_string TEXT NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS approved (
            user_id INTEGER PRIMARY KEY
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    if OWNER_ID:
        c.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('owner', ?)", (str(OWNER_ID),))
    conn.commit()
    conn.close()
    LOGGER.info("Database initialized")

init_db()

def get_owner_id() -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT value FROM config WHERE key = 'owner'")
    row = c.fetchone()
    conn.close()
    return int(row[0]) if row else 0

def set_owner_id(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO config (key, value) VALUES ('owner', ?)", (str(user_id),))
    conn.commit()
    conn.close()

def get_approved_users():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM approved")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

def is_approved(user_id: int) -> bool:
    owner = get_owner_id()
    if user_id == owner:
        return True
    return user_id in get_approved_users()

def add_approved(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO approved (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def remove_approved(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM approved WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def add_session(session_string: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO sessions (session_string) VALUES (?)", (session_string,))
    sid = c.lastrowid
    conn.commit()
    conn.close()
    return sid

def delete_session(sid: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM sessions WHERE sid = ?", (sid,))
    conn.commit()
    conn.close()

def clear_sessions():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM sessions")
    conn.commit()
    conn.close()

def get_all_sessions() -> Dict[int, str]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT sid, session_string FROM sessions")
    rows = c.fetchall()
    conn.close()
    return {sid: sess for sid, sess in rows}

def get_session(sid: int) -> Optional[str]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT session_string FROM sessions WHERE sid = ?", (sid,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

# ---------- User Clients ----------
user_clients: Dict[int, Client] = {}

async def get_user_client(sid: int) -> Optional[Client]:
    if sid in user_clients:
        return user_clients[sid]
    session_str = get_session(sid)
    if not session_str:
        return None
    client = Client(
        f"session_{sid}",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=session_str,
        workdir="."
    )
    try:
        await client.start()
        user_clients[sid] = client
        LOGGER.info(f"Started user client for session {sid}")
        return client
    except Exception as e:
        LOGGER.error(f"Failed to start client for sid {sid}: {e}")
        return None

async def close_user_client(sid: int):
    if sid in user_clients:
        try:
            await user_clients[sid].stop()
        except:
            pass
        del user_clients[sid]

# ---------- IP Extraction (same) ----------
async def extract_ip_from_call(user_client: Client, chat_id: int) -> Optional[str]:
    # ... same as before ...
    # (I'll copy the exact function from previous version to save space)
    try:
        peer = await user_client.resolve_peer(chat_id)
    except Exception as e:
        LOGGER.error(f"Resolve peer error: {e}")
        return None

    try:
        if isinstance(peer, types.InputPeerChannel):
            full = await user_client.invoke(
                functions.channels.GetFullChannel(
                    channel=types.InputChannel(
                        channel_id=peer.channel_id,
                        access_hash=peer.access_hash
                    )
                )
            )
        elif isinstance(peer, types.InputPeerChat):
            full = await user_client.invoke(
                functions.messages.GetFullChat(chat_id=peer.chat_id)
            )
        else:
            return None
        call = getattr(full.full_chat, "call", None)
        if not call:
            LOGGER.info("No active voice call in this chat.")
            return None
    except Exception as e:
        LOGGER.error(f"Failed to get call: {e}")
        return None

    joined = False
    try:
        my_peer = await user_client.resolve_peer('me')
        params = call.params
        await user_client.invoke(
            functions.phone.JoinGroupCall(
                call=types.InputGroupCall(
                    id=call.id,
                    access_hash=call.access_hash
                ),
                join_as=my_peer,
                params=params,
                muted=True,
                video_stopped=True
            )
        )
        joined = True
        LOGGER.info("Joined call successfully")
        await asyncio.sleep(2)
    except Exception as e:
        LOGGER.warning(f"Join failed (may already be in call): {e}")

    ip_address = None
    try:
        group_call = await user_client.invoke(
            functions.phone.GetGroupCall(
                call=types.InputGroupCall(
                    id=call.id,
                    access_hash=call.access_hash
                ),
                limit=1
            )
        )
        call_obj = group_call.call
        params_raw = getattr(call_obj, "params", None)
        if params_raw:
            try:
                data = json.loads(params_raw.data)
                endpoints = data.get("endpoints", [])
                for ep in endpoints:
                    if ":" in ep:
                        host = ep.split(":")[0]
                        if host.replace(".", "").isdigit():
                            ip_address = host
                            break
                if not ip_address:
                    servers = data.get("servers", [])
                    for srv in servers:
                        if isinstance(srv, dict):
                            ip = srv.get("ip") or srv.get("host")
                            if ip and ip.replace(".", "").isdigit():
                                ip_address = ip
                                break
            except Exception as e:
                LOGGER.error(f"Failed to parse params: {e}")
    except Exception as e:
        LOGGER.error(f"Failed to get group call: {e}")

    if joined:
        try:
            await user_client.invoke(
                functions.phone.LeaveGroupCall(
                    call=types.InputGroupCall(
                        id=call.id,
                        access_hash=call.access_hash
                    ),
                    source=0
                )
            )
            LOGGER.info("Left call")
        except Exception as e:
            LOGGER.warning(f"Leave failed: {e}")

    return ip_address

# ---------- Bot Initialization ----------
bot = Client("ip_grabber_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

async def check_approval(message) -> bool:
    user_id = message.from_user.id
    if is_approved(user_id):
        return True
    await message.reply("⛔ You are not authorized. Contact owner.")
    return False

# ---------- CATCH-ALL MESSAGE HANDLER (for debugging) ----------
@bot.on_message()
async def catch_all_messages(client, message):
    LOGGER.info(f"Received ANY message from {message.from_user.id} | type: {message.__class__.__name__}")
    # If it's a text message, log the text too
    if message.text:
        LOGGER.info(f"Text: {message.text}")

# ---------- Public Commands ----------
@bot.on_message(filters.command("ping"))
async def ping_cmd(client, message):
    LOGGER.info(f"Ping from {message.from_user.id}")
    await message.reply("🏓 Pong!")

@bot.on_message(filters.command("start"))
async def start_cmd(client, message):
    LOGGER.info(f"Start from {message.from_user.id}")
    await message.reply(
        "👋 **IP Grabber Bot**\n"
        "Manage multiple Telegram sessions to extract IPs from voice chats.\n\n"
        "Commands:\n"
        "/addsession <string> – add session\n"
        "/delsession <sid> – delete\n"
        "/clearsessions – clear all\n"
        "/exportsessions – export ZIP\n"
        "/join <sid|all> <chat> – join VC\n"
        "/leave <sid|all> <chat> – leave VC\n"
        "/getip <sid> <chat> – extract IP\n"
        "Inline: @bot <sid> <chat>\n\n"
        "Owner:\n"
        "/approve <id|reply> – approve user\n"
        "/remove <id> – remove user\n"
        "/approved – list approved"
    )

# ---------- All other commands (require approval) ----------
# ... (keep the same handlers for addsession, delsession, etc.)
# I'm omitting them for brevity, but they are identical to previous version.
# You can copy them from the previous full code.

# ---------- Health Check ----------
async def health_check(request):
    return web.Response(text="OK")

# ---------- Heartbeat (to confirm bot is running) ----------
async def heartbeat_loop():
    while True:
        await asyncio.sleep(30)
        LOGGER.info("Heartbeat: Bot is still running")

# ---------- Main ----------
async def main():
    try:
        LOGGER.info("Starting bot...")
        await bot.start()
        LOGGER.info("Bot started successfully!")

        # Print bot username to confirm identity
        me = await bot.get_me()
        LOGGER.info(f"Bot username: @{me.username} (ID: {me.id})")

        # Start health check
        app = web.Application()
        app.router.add_get('/', health_check)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', 8080)
        await site.start()
        LOGGER.info("Health check server running on port 8080")

        # Start heartbeat
        asyncio.create_task(heartbeat_loop())

        # Notify owner
        owner = get_owner_id()
        if owner:
            try:
                await bot.send_message(owner, f"✅ Bot @{me.username} is online and ready.")
                LOGGER.info(f"Startup notification sent to owner {owner}")
            except Exception as e:
                LOGGER.warning(f"Could not send startup notification: {e}")

        LOGGER.info("Entering idle loop...")
        await idle()
        LOGGER.info("Idle loop ended, stopping bot...")
        await bot.stop()
        LOGGER.info("Bot stopped.")
    except Exception as e:
        LOGGER.exception("Fatal error in main loop")
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        LOGGER.info("Keyboard interrupt, exiting.")
    except Exception as e:
        LOGGER.exception("Unhandled exception")
        sys.exit(1)
