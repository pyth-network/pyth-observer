import asyncio
from aiohttp import web

observer_ready = False

async def live_handler(request):
    return web.Response(text="OK")

async def ready_handler(request):
    if observer_ready:
        return web.Response(text="OK")
    else:
        return web.Response(status=503, text="Not Ready")

async def start_health_server(port=8080):
    app = web.Application()
    app.router.add_get("/live", live_handler)
    app.router.add_get("/ready", ready_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    while True:
        await asyncio.sleep(3600)

