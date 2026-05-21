"""
pipes.py — نظام الـ Pipes (توجيه الرسائل بين المحادثات)
مُستوحى من WilliamButcherBot، مُعاد كتابته لنظام ggggg (Pyrogram + Redis)

يعمل على البوت (Client) فقط — للمطور فقط

الأوامر (في خاص المطور أو أي مكان):
  /تفعيل_بايب [from_chat_id] [to_chat_id]  → تفعيل بايب
  /تعطيل_بايب [from_chat_id]               → تعطيل بايب
  /البايبات                                 → عرض البايبات النشطة

متطلبات Redis:
  {DEV_ID}:pipes  → JSON list للبايبات

ملاحظة: البايبات تُخزَّن في Redis وتبقى بعد إعادة التشغيل
        (على خلاف WBB التي تفقدها عند إعادة التشغيل)
"""

import asyncio
import json
import logging

from pyrogram import Client, filters
from pyrogram.types import Message

from config import r, ar, DEV_ID, DEV_ID_INT, botkey
from helpers.ranks import is_dev

logger = logging.getLogger("pipes")

from config import Client as _BotClient   # noqa

# ─── مفتاح Redis ─────────────────────────────────────────────
_PIPES_KEY = f"{DEV_ID}:pipes"

# ─── ذاكرة محلية للسرعة (يُحدَّث عند كل تغيير) ──────────────
_pipes_cache: dict[int, int] = {}   # {from_chat_id: to_chat_id}
_cache_loaded = False


# ─────────────────────────────────────────────────────────────
# DB Helpers (Redis JSON)
# ─────────────────────────────────────────────────────────────

async def _load_pipes() -> dict[int, int]:
    global _pipes_cache, _cache_loaded
    raw = await ar.get(_PIPES_KEY)
    if raw:
        try:
            data = json.loads(raw)
            _pipes_cache = {int(k): int(v) for k, v in data.items()}
        except Exception:
            _pipes_cache = {}
    else:
        _pipes_cache = {}
    _cache_loaded = True
    return _pipes_cache

async def _save_pipes():
    await ar.set(_PIPES_KEY, json.dumps({str(k): v for k, v in _pipes_cache.items()}))

async def _get_pipes() -> dict[int, int]:
    global _cache_loaded
    if not _cache_loaded:
        await _load_pipes()
    return _pipes_cache

async def _activate_pipe(from_chat: int, to_chat: int):
    pipes = await _get_pipes()
    pipes[from_chat] = to_chat
    await _save_pipes()

async def _deactivate_pipe(from_chat: int):
    pipes = await _get_pipes()
    pipes.pop(from_chat, None)
    await _save_pipes()


# ─────────────────────────────────────────────────────────────
# Worker — يُعيد توجيه الرسائل (group=500)
# ─────────────────────────────────────────────────────────────

@_BotClient.on_message(group=500)
async def pipes_worker(client: Client, message: Message):
    if not message.chat:
        return
    pipes = await _get_pipes()
    chat_id = message.chat.id
    if chat_id not in pipes:
        return
    to_chat = pipes[chat_id]
    try:
        await message.forward(to_chat)
    except Exception as e:
        logger.debug("pipes_worker: فشل إعادة التوجيه من %s إلى %s: %s", chat_id, to_chat, e)


# ─────────────────────────────────────────────────────────────
# أوامر التحكم
# ─────────────────────────────────────────────────────────────

def _is_dev_user(message: Message) -> bool:
    uid = message.from_user.id if message.from_user else 0
    return is_dev(uid, 0)


@_BotClient.on_message(
    filters.command(["تفعيل_بايب", "activate_pipe"])
)
async def activate_pipe_cmd(client: Client, message: Message):
    if not _is_dev_user(message):
        return await message.reply_text("⛔ للمطور فقط.")

    if len(message.command) < 3:
        return await message.reply_text(
            "**الاستخدام:**\n`/تفعيل_بايب [from_chat_id] [to_chat_id]`"
        )

    try:
        from_chat = int(message.command[1])
        to_chat   = int(message.command[2])
    except ValueError:
        return await message.reply_text("❌ أدخل chat_id أرقاماً صحيحة.")

    pipes = await _get_pipes()
    if from_chat in pipes:
        return await message.reply_text("⚠️ هذا البايب مفعَّل مسبقاً.")

    await _activate_pipe(from_chat, to_chat)
    await message.reply_text(
        f"✅ تم تفعيل البايب:\n"
        f"من: `{from_chat}`\n"
        f"إلى: `{to_chat}`"
    )


@_BotClient.on_message(
    filters.command(["تعطيل_بايب", "deactivate_pipe"])
)
async def deactivate_pipe_cmd(client: Client, message: Message):
    if not _is_dev_user(message):
        return await message.reply_text("⛔ للمطور فقط.")

    if len(message.command) < 2:
        return await message.reply_text(
            "**الاستخدام:**\n`/تعطيل_بايب [from_chat_id]`"
        )

    try:
        from_chat = int(message.command[1])
    except ValueError:
        return await message.reply_text("❌ أدخل chat_id رقماً صحيحاً.")

    pipes = await _get_pipes()
    if from_chat not in pipes:
        return await message.reply_text("⚠️ هذا البايب غير مفعَّل.")

    await _deactivate_pipe(from_chat)
    await message.reply_text(f"❌ تم تعطيل البايب من `{from_chat}`.")


@_BotClient.on_message(
    filters.command(["البايبات", "pipes", "show_pipes"])
)
async def show_pipes_cmd(client: Client, message: Message):
    if not _is_dev_user(message):
        return await message.reply_text("⛔ للمطور فقط.")

    pipes = await _get_pipes()
    if not pipes:
        return await message.reply_text("📭 لا توجد بايبات نشطة.")

    lines = ["**🔗 البايبات النشطة:**\n"]
    for i, (from_c, to_c) in enumerate(pipes.items(), 1):
        lines.append(f"`{i}.` من `{from_c}` → إلى `{to_c}`")

    await message.reply_text("\n".join(lines))
