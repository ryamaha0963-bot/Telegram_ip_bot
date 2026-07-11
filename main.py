import asyncio
import logging
import os
import sys

from pyrogram import Client, filters, idle

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)

API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

if not API_ID or not API_HASH or not BOT_TOKEN:
    LOGGER.error("Missing API_ID, API_HASH, or BOT_TOKEN")
    sys.exit(1)

bot = Client("minimal", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@bot.on_message(filters.command("start"))
async def start_cmd(client, message):
    LOGGER.info(f"Start from {message.from_user.id}")
    await message.reply("✅ Bot is online!\nSend /ping")

@bot.on_message(filters.command("ping"))
async def ping_cmd(client, message):
    LOGGER.info(f"Ping from {message.from_user.id}")
    await message.reply("🏓 Pong!")

@bot.on_message()  # catch all messages for logging
async def log_all(client, message):
    LOGGER.info(f"Received: {message.text} from {message.from_user.id}")

async def main():
    await bot.start()
    me = await bot.get_me()
    LOGGER.info(f"Bot @{me.username} started")
    await idle()
    await bot.stop()

if __name__ == "__main__":
    asyncio.run(main())
