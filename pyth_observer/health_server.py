import asyncio
from typing import TYPE_CHECKING

from aiohttp import web

if TYPE_CHECKING:
    from aiohttp.web_request import Request

observer_ready = False


async def live_handler(request: "Request") -> web.Response:
    return web.Response(text="OK")


async def ready_handler(request: "Request") -> web.Response:
    if observer_ready:
        return web.Response(text="OK")
    else:
        return web.Response(status=503, text="Not Ready")


async def start_health_server(port: int = 8080) -> None:
    app = web.Application()
    app.router.add_get("/live", live_handler)
    app.router.add_get("/ready", ready_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    while True:
        await asyncio.sleep(3600)
