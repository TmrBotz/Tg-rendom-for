import asyncio
import logging

from pyrogram import Client, idle

import db
from config import Config
from handlers import register
from poster import scheduler
from server import self_ping, start_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
log = logging.getLogger("bot")


async def main():
    Config.check()
    await db.init()

    # start web server first so Render sees the open port
    runner = await start_server()

    app = Client(
        "forward_bot",
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        bot_token=Config.BOT_TOKEN,
        in_memory=True,
    )
    register(app)
    await app.start()
    me = await app.get_me()
    log.info("Started as @%s", me.username)

    # warm up the peer cache for the saved channels
    s = db.get_settings()
    for key in ("source", "target"):
        if s.get(key):
            try:
                await app.get_chat(s[key])
            except Exception as e:
                log.warning("Could not load %s channel: %s", key, e)

    tasks = [asyncio.create_task(scheduler(app)), asyncio.create_task(self_ping())]
    await idle()

    for t in tasks:
        t.cancel()
    await app.stop()
    await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
