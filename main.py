import asyncio
import logging
import os
import sys

from pyrogram import Client

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)

# Environment variables
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = os.getenv("OWNER_ID")

# Validate
if not API_ID or not API_HASH or not BOT_TOKEN:
    LOGGER.error("Missing: API_ID, API_HASH, BOT_TOKEN are required.")
    sys.exit(1)

if not OWNER_ID:
    LOGGER.error("OWNER_ID is required. Set it to your Telegram User ID.")
    sys.exit(1)

try:
    API_ID = int(API_ID)
    OWNER_ID = int(OWNER_ID)
except ValueError:
    LOGGER.error("API_ID and OWNER_ID must be integers.")
    sys.exit(1)

bot = Client("test", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

async def main():
    LOGGER.info("Starting bot...")
    await bot.start()
    me = await bot.get_me()
    LOGGER.info(f"Bot started: @{me.username} (ID: {me.id})")

    # Try to send message to OWNER_ID
    try:
        await bot.send_message(OWNER_ID, f"✅ Bot @{me.username} is online and working!")
        LOGGER.info(f"✅ Message sent to owner {OWNER_ID}")
    except Exception as e:
        LOGGER.error(f"❌ Failed to send message to owner: {e}")
        # Try sending to "me" (self) – but bot cannot send to itself, so this will fail too.
        try:
            await bot.send_message("me", "Test message to me")
            LOGGER.info("Sent to 'me' (maybe? )")
        except Exception as e2:
            LOGGER.error(f"Also failed to send to 'me': {e2}")

    # Wait a bit so logs can be seen
    await asyncio.sleep(10)
    await bot.stop()
    LOGGER.info("Test finished.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        LOGGER.exception("Fatal error")
        sys.exit(1)
