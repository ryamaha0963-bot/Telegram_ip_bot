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
TEST_CHAT_ID = int(os.getenv("TEST_CHAT_ID", 0))  # your user ID

if not API_ID or not API_HASH or not BOT_TOKEN:
    LOGGER.error("Missing env")
    sys.exit(1)

bot = Client("minimal", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@bot.on_message()
async def log_all(client, message):
    LOGGER.info(f"RECEIVED: {message.text} from {message.from_user.id}")

@bot.on_message(filters.command("start"))
async def start_cmd(client, message):
    await message.reply("Working")

@bot.on_message(filters.command("ping"))
async def ping_cmd(client, message):
    await message.reply("Pong")

async def main():
    await bot.start()
    me = await bot.get_me()
    LOGGER.info(f"Bot started as @{me.username} (ID: {me.id})")
    if TEST_CHAT_ID:
        try:
            await bot.send_message(TEST_CHAT_ID, f"Bot @{me.username} is online.")
            LOGGER.info(f"Sent startup message to {TEST_CHAT_ID}")
        except Exception as e:
            LOGGER.error(f"Failed to send startup message: {e}")
    await idle()
    await bot.stop()

if __name__ == "__main__":
    asyncio.run(main())
