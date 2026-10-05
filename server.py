"""Dummy web server for Render (port binding) + self-ping to avoid sleeping."""
import asyncio
import logging

import aiohttp
from aiohttp import web

from config import Config

log = logging.getLogger("server")


async def _index(request):
    return web.Response(text="Bot is running ✅")


async def start_server():
    app = web.Application()
    app.router.add_get("/", _index)
    app.router.add_get("/health", _index)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", Config.PORT).start()
    log.info("Web server started on port %s", Config.PORT)
    return runner


async def self_ping(every=300):
    url = Config.PING_URL
    if not url:
        log.info("No PING_URL / RENDER_EXTERNAL_URL set: self-ping disabled")
        return
    async with aiohttp.ClientSession() as session:
        while True:
            await asyncio.sleep(every)
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as r:
                    log.info("self-ping %s -> %s", url, r.status)
            except Exception as e:
                log.warning("self-ping failed: %s", e)
