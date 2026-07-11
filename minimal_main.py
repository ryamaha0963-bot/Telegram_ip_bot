"""
Minimal Echo Bot - Test if Railway can receive messages
"""

import asyncio
import logging
import os
import sys

from pyrogram import Client, filters, idle

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
LOGGER = logging.getLogger(__name__)

# Environment
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

if not API_ID or not API_HASH or not BOT_TOKEN:
    LOGGER.error("Missing environment variables")
    sys.exit(1)

# Bot client
bot = Client("minimal_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ----- Message logger (catch all) -----
@bot.on_message()
async def log_everything(client, message):
    LOGGER.info(f"Received message from {message.from_user.id}: {message.text}")

# ----- Commands -----
@bot.on_message(filters.command("start"))
async def start_cmd(client, message):
    LOGGER.info(f"Start command from {message.from_user.id}")
    await message.reply("✅ Bot is working! Send /ping")

@bot.on_message(filters.command("ping"))
async def ping_cmd(client, message):
    LOGGER.info(f"Ping from {message.from_user.id}")
    await message.reply("🏓 Pong!")

# ----- Main -----
async def main():
    LOGGER.info("Starting minimal bot...")
    await bot.start()
    me = await bot.get_me()
    LOGGER.info(f"Bot started as @{me.username} (ID: {me.id})")
    LOGGER.info("Entering idle...")
    await idle()
    LOGGER.info("Stopping...")
    await bot.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        LOGGER.exception("Fatal error")
        sys.exit(1)
