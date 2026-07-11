import logging
import sys
import os
from pyrogram import Client, filters, idle

logging.basicConfig(level=logging.INFO, handlers=[logging.StreamHandler(sys.stdout)])
LOGGER = logging.getLogger(__name__)

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", 0))

app = Client("test_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@app.on_message(filters.command("start"))
async def start(client, message):
    LOGGER.info(f"Start from {message.from_user.id}")
    await message.reply("Hello! Bot is working.")

@app.on_message(filters.command("ping"))
async def ping(client, message):
    LOGGER.info(f"Ping from {message.from_user.id}")
    await message.reply("Pong!")

async def main():
    LOGGER.info("Starting bot...")
    await app.start()
    LOGGER.info("Bot started.")
    if OWNER_ID:
        try:
            await app.send_message(OWNER_ID, "Bot is online!")
        except Exception as e:
            LOGGER.warning(f"Can't notify owner: {e}")
    await idle()
    await app.stop()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
