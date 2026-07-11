"""
Telegram IP Grabber Bot - Debug version with ping
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

# ---------- Force logging to stdout ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
LOGGER = logging.getLogger(__name__)

# ---------- Validate environment ----------
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not API_ID or not API_HASH or not BOT_TOKEN:
    LOGGER.error("Missing environment variables: API_ID, API_HASH, BOT_TOKEN must be set")
    sys.exit(1)

try:
    API_ID = int(API_ID)
except ValueError:
    LOGGER.error("API_ID must be an integer")
    sys.exit(1)

OWNER_ID = int(os.getenv("OWNER_ID", 0))

# ---------- Database ----------
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

# ---------- Client cache ----------
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

# ---------- Voice Chat IP Extraction ----------
async def extract_ip_from_call(user_client: Client, chat_id: int) -> Optional[str]:
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

# ---------- Bot ----------
bot = Client("ip_grabber_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

async def check_approval(message) -> bool:
    user_id = message.from_user.id
    if is_approved(user_id):
        return True
    await message.reply("⛔ You are not authorized. Contact owner.")
    return False

# ----- Global message logger (for debugging) -----
@bot.on_message(filters.text & filters.private)
async def log_all_private_messages(client, message):
    LOGGER.info(f"Private message from {message.from_user.id}: {message.text}")

# ----- Public commands (no approval needed) -----
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

# ----- All other commands (require approval) -----
@bot.on_message(filters.command("addsession") & filters.private)
async def add_session_cmd(client, message):
    if not await check_approval(message):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("Usage: /addsession <session_string>")
        return
    session_str = parts[1].strip()
    try:
        test_client = Client("test", api_id=API_ID, api_hash=API_HASH, session_string=session_str)
        await test_client.start()
        me = await test_client.get_me()
        await test_client.stop()
        sid = add_session(session_str)
        await message.reply(f"✅ Session added with ID `{sid}` (user: {me.first_name})")
    except Exception as e:
        await message.reply(f"❌ Invalid session: {e}")

@bot.on_message(filters.command("delsession") & filters.private)
async def del_session_cmd(client, message):
    if not await check_approval(message):
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.reply("Usage: /delsession <sid>")
        return
    try:
        sid = int(parts[1])
    except ValueError:
        await message.reply("Invalid SID.")
        return
    if get_session(sid) is None:
        await message.reply("Session not found.")
        return
    delete_session(sid)
    await close_user_client(sid)
    await message.reply(f"🗑️ Session {sid} deleted.")

@bot.on_message(filters.command("clearsessions") & filters.private)
async def clear_sessions_cmd(client, message):
    if not await check_approval(message):
        return
    clear_sessions()
    for sid in list(user_clients.keys()):
        await close_user_client(sid)
    await message.reply("🧹 All sessions cleared.")

@bot.on_message(filters.command("exportsessions") & filters.private)
async def export_sessions_cmd(client, message):
    if not await check_approval(message):
        return
    sessions = get_all_sessions()
    if not sessions:
        await message.reply("No sessions to export.")
        return
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        zip_path = tmp.name
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for sid, sess in sessions.items():
            zipf.writestr(f"session_{sid}.txt", sess)
    await message.reply_document(zip_path, caption=f"📦 Exported {len(sessions)} sessions.")
    os.unlink(zip_path)

@bot.on_message(filters.document & filters.private)
async def handle_zip_upload(client, message):
    if not await check_approval(message):
        return
    if not message.document.file_name.endswith(".zip"):
        return
    file_path = await message.download()
    try:
        with zipfile.ZipFile(file_path, 'r') as zipf:
            for name in zipf.namelist():
                if name.endswith(".txt"):
                    content = zipf.read(name).decode('utf-8').strip()
                    if content:
                        sid = add_session(content)
                        await message.reply(f"✅ Added session from {name} with ID `{sid}`")
    except Exception as e:
        await message.reply(f"❌ Error processing ZIP: {e}")
    finally:
        os.unlink(file_path)

@bot.on_message(filters.command("join") & filters.private)
async def join_cmd(client, message):
    if not await check_approval(message):
        return
    parts = message.text.split()
    if len(parts) < 3:
        await message.reply("Usage: /join <sid|all> <chat>")
        return
    sid_str = parts[1]
    chat_identifier = parts[2]
    if sid_str.lower() == "all":
        sids = list(get_all_sessions().keys())
        if not sids:
            await message.reply("No sessions available.")
            return
        await message.reply(f"Attempting to join with {len(sids)} sessions...")
        results = []
        for sid in sids:
            user_client = await get_user_client(sid)
            if not user_client:
                results.append(f"Session {sid}: failed to start")
                continue
            ip = await extract_ip_from_call(user_client, chat_identifier)
            results.append(f"Session {sid}: {'joined' if ip is not None else 'failed'}")
        await message.reply("\n".join(results))
    else:
        try:
            sid = int(sid_str)
        except ValueError:
            await message.reply("Invalid SID.")
            return
        user_client = await get_user_client(sid)
        if not user_client:
            await message.reply(f"Session {sid} not found or failed to start.")
            return
        ip = await extract_ip_from_call(user_client, chat_identifier)
        if ip:
            await message.reply(f"✅ Joined and got IP: `{ip}`")
        else:
            await message.reply("❌ Could not join or extract IP.")

@bot.on_message(filters.command("leave") & filters.private)
async def leave_cmd(client, message):
    if not await check_approval(message):
        return
    parts = message.text.split()
    if len(parts) < 3:
        await message.reply("Usage: /leave <sid|all> <chat>")
        return
    sid_str = parts[1]
    chat_identifier = parts[2]
    if sid_str.lower() == "all":
        sids = list(get_all_sessions().keys())
        if not sids:
            await message.reply("No sessions available.")
            return
        await message.reply(f"Attempting to leave with {len(sids)} sessions...")
        results = []
        for sid in sids:
            user_client = await get_user_client(sid)
            if not user_client:
                results.append(f"Session {sid}: failed to start")
                continue
            try:
                peer = await user_client.resolve_peer(chat_identifier)
                if isinstance(peer, types.InputPeerChannel):
                    full = await user_client.invoke(
                        functions.channels.GetFullChannel(
                            channel=types.InputChannel(
                                channel_id=peer.channel_id,
                                access_hash=peer.access_hash
                            )
                        )
                    )
                else:
                    full = await user_client.invoke(
                        functions.messages.GetFullChat(chat_id=peer.chat_id)
                    )
                call = getattr(full.full_chat, "call", None)
                if not call:
                    results.append(f"Session {sid}: no active call")
                    continue
                await user_client.invoke(
                    functions.phone.LeaveGroupCall(
                        call=types.InputGroupCall(id=call.id, access_hash=call.access_hash),
                        source=0
                    )
                )
                results.append(f"Session {sid}: left")
            except Exception as e:
                results.append(f"Session {sid}: error - {e}")
        await message.reply("\n".join(results))
    else:
        try:
            sid = int(sid_str)
        except ValueError:
            await message.reply("Invalid SID.")
            return
        user_client = await get_user_client(sid)
        if not user_client:
            await message.reply(f"Session {sid} not found or failed to start.")
            return
        try:
            peer = await user_client.resolve_peer(chat_identifier)
            if isinstance(peer, types.InputPeerChannel):
                full = await user_client.invoke(
                    functions.channels.GetFullChannel(
                        channel=types.InputChannel(
                            channel_id=peer.channel_id,
                            access_hash=peer.access_hash
                        )
                    )
                )
            else:
                full = await user_client.invoke(
                    functions.messages.GetFullChat(chat_id=peer.chat_id)
                )
            call = getattr(full.full_chat, "call", None)
            if not call:
                await message.reply("No active call in this chat.")
                return
            await user_client.invoke(
                functions.phone.LeaveGroupCall(
                    call=types.InputGroupCall(id=call.id, access_hash=call.access_hash),
                    source=0
                )
            )
            await message.reply("✅ Left the call.")
        except Exception as e:
            await message.reply(f"❌ Error: {e}")

@bot.on_message(filters.command("getip") & filters.private)
async def getip_cmd(client, message):
    if not await check_approval(message):
        return
    parts = message.text.split()
    if len(parts) < 3:
        await message.reply("Usage: /getip <sid> <chat>")
        return
    try:
        sid = int(parts[1])
    except ValueError:
        await message.reply("Invalid SID.")
        return
    chat_identifier = parts[2]
    user_client = await get_user_client(sid)
    if not user_client:
        await message.reply(f"Session {sid} not found or failed to start.")
        return
    ip = await extract_ip_from_call(user_client, chat_identifier)
    if ip:
        await message.reply(f"🕵️ IP: `{ip}`")
    else:
        await message.reply("❌ Could not extract IP (no active VC or permission).")

# Inline query
@bot.on_inline_query()
async def inline_ip(client, inline_query):
    query = inline_query.query.strip()
    if not query:
        await inline_query.answer([], switch_pm_text="Use: sid chat", switch_pm_parameter="help")
        return
    parts = query.split(maxsplit=1)
    if len(parts) < 2:
        await inline_query.answer([], switch_pm_text="Provide: sid and chat", switch_pm_parameter="help")
        return
    sid_str, chat_identifier = parts
    try:
        sid = int(sid_str)
    except ValueError:
        await inline_query.answer([], switch_pm_text="Invalid SID", switch_pm_parameter="help")
        return
    user_id = inline_query.from_user.id
    if not is_approved(user_id):
        await inline_query.answer([], switch_pm_text="You are not approved.", switch_pm_parameter="help")
        return
    user_client = await get_user_client(sid)
    if not user_client:
        results = [InlineQueryResultArticle(
            title="Session not found",
            input_message_content=InputTextMessageContent(f"Session {sid} not available.")
        )]
        await inline_query.answer(results, cache_time=0)
        return
    ip = await extract_ip_from_call(user_client, chat_identifier)
    if ip:
        result = InlineQueryResultArticle(
            title=f"IP: {ip}",
            description=f"From session {sid} in {chat_identifier}",
            input_message_content=InputTextMessageContent(f"🕵️ IP: `{ip}`\nSession: `{sid}`\nChat: `{chat_identifier}`")
        )
        await inline_query.answer([result], cache_time=0)
    else:
        result = InlineQueryResultArticle(
            title="No IP found",
            description="Could not extract IP (no active VC?)",
            input_message_content=InputTextMessageContent("❌ No IP extracted.")
        )
        await inline_query.answer([result], cache_time=0)

# Owner commands
@bot.on_message(filters.command("approve") & filters.private)
async def approve_cmd(client, message):
    owner = get_owner_id()
    if owner == 0:
        set_owner_id(message.from_user.id)
        owner = message.from_user.id
        await message.reply("✅ You are now the owner.")
    elif message.from_user.id != owner:
        await message.reply("⛔ Only the owner can approve users.")
        return
    user_id = None
    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
    else:
        parts = message.text.split()
        if len(parts) > 1:
            try:
                user_id = int(parts[1])
            except ValueError:
                pass
    if not user_id:
        await message.reply("Usage: /approve <user_id> or reply to a message")
        return
    add_approved(user_id)
    await message.reply(f"✅ User {user_id} approved.")

@bot.on_message(filters.command("remove") & filters.private)
async def remove_cmd(client, message):
    owner = get_owner_id()
    if message.from_user.id != owner:
        await message.reply("⛔ Only owner can remove users.")
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.reply("Usage: /remove <user_id>")
        return
    try:
        user_id = int(parts[1])
    except ValueError:
        await message.reply("Invalid user ID.")
        return
    remove_approved(user_id)
    await message.reply(f"🗑️ User {user_id} removed.")

@bot.on_message(filters.command("approved") & filters.private)
async def approved_cmd(client, message):
    owner = get_owner_id()
    if message.from_user.id != owner:
        await message.reply("⛔ Only owner can view approved list.")
        return
    users = get_approved_users()
    if not users:
        await message.reply("No approved users.")
    else:
        await message.reply("Approved users:\n" + "\n".join(str(u) for u in users))

# ---------- Main ----------
async def main():
    try:
        LOGGER.info("Starting bot...")
        await bot.start()
        LOGGER.info("Bot started successfully!")

        # Notify owner if set
        owner = get_owner_id()
        if owner:
            try:
                await bot.send_message(owner, "✅ Bot is online and ready.")
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
