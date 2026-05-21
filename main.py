import asyncio
import logging
import os
import glob
from aiohttp import web

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")

# إصلاح Pyrogram لبايثون 3.10+
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

from config import Client, DEV_ID_INT

# حذف جلسات قديمة
for f in glob.glob("my_bot*"):
    try:
        os.remove(f)
    except Exception:
        pass


_bot_ready: bool = False


# ── Health-check server ──────────────────────────────────────────────────
async def _health(request):
    if _bot_ready:
        return web.Response(text="✅ Bot is running", status=200)
    return web.Response(text="⏳ Bot is starting...", status=503)

async def _start_health_server():
    port = int(os.environ.get("PORT", 10000))
    app  = web.Application()
    app.router.add_get("/", _health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Health-check server on port %d", port)


async def _preload_games_data():
    """يُحمِّل بيانات الألعاب في الخلفية لتجنب التأخر عند أول لعبة"""
    try:
        import importlib
        await asyncio.get_running_loop().run_in_executor(
            None, importlib.import_module, "helpers.games_data"
        )
        logger.info("بيانات الألعاب جاهزة ✅")
    except Exception as e:
        logger.warning("تعذّر تحميل بيانات الألعاب مسبقاً: %s", e)


# ── معالج الأخطاء غير المتوقعة ──────────────────────────────────────────
async def _global_error_notifier():
    """
    يُرسل للمطور إشعاراً عند بدء البوت وعند أي خطأ غير متوقع.
    """
    try:
        await Client.send_message(
            DEV_ID_INT,
            "✅ **البوت بدأ التشغيل بنجاح**\n"
            "🔔 سيصلك إشعار فوري عند أي خطأ.",
        )
    except Exception:
        pass


def _setup_global_exception_handler():
    """يعترض الأخطاء غير المعالجة في asyncio ويرسلها للمطور"""

    def handler(loop, context):
        exc = context.get("exception")
        msg = context.get("message", "خطأ غير معروف")
        logger.error("Unhandled asyncio error: %s — %s", msg, exc)

        async def _notify():
            try:
                from helpers.error_logger import log_error
                if exc:
                    await log_error(exc, context=f"asyncio global — {msg}")
            except Exception:
                pass

        try:
            loop.create_task(_notify())
        except Exception:
            pass

    loop.set_exception_handler(handler)


async def main():
    from Plugins.auto_clean import _auto_clean_loop
    import Plugins.private_sudos as _ps

    _setup_global_exception_handler()
    await _start_health_server()

    async with Client:
        global _bot_ready
        me = await Client.get_me()
        _bot_ready = True
        logger.info("البوت شغال: @%s", me.username)

        _running_loop = asyncio.get_running_loop()
        _running_loop.create_task(_auto_clean_loop(Client))
        logger.info("حلقة التنظيف التلقائي تعمل")

        # تحميل بيانات الألعاب في الخلفية
        _running_loop.create_task(_preload_games_data())

        # إشعار المطور بنجاح التشغيل
        _running_loop.create_task(_global_error_notifier())

        try:
            await asyncio.sleep(float("inf"))
        finally:
            await _ps._http.aclose()
            import Plugins.downloader as _dl
            await _dl._http.aclose()
            logger.info("تم إغلاق httpx clients")


if __name__ == "__main__":
    loop.run_until_complete(main())
