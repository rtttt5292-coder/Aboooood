"""
userbot.py — أوامر الـ Userbot (eval / sh / reserve)
مُستوحى من WilliamButcherBot، مُعاد كتابته لنظام ggggg (Pyrogram + Redis)

يعمل على البوت (Client) — للمطور فقط في الخاص

الأوامر (في خاص المطور):
  /eval [كود]   → تنفيذ كود Python async
  /sh [أمر]     → تنفيذ أمر shell
  eval [كود]    → بديل بدون /
  sh [أمر]      → بديل بدون /

ملاحظة: هذه الأوامر موجودة بالفعل في private_sudos.py للمطور الأعلى.
        هذا الملف يُضيف دعم الأوامر .eval و .sh بنمط userbot prefix
        ويُصدِّر دالة eor() المساعدة للاستخدام في الملفات الأخرى.
"""

import asyncio
import logging
import os
import re
import subprocess
import sys
import traceback
from html import escape
from io import StringIO

from pyrogram import Client, filters
from pyrogram.enums import ChatType
from pyrogram.types import Message

from config import r, ar, DEV_ID, DEV_ID_INT, botkey, botname
from helpers.ranks import is_dev

logger = logging.getLogger("userbot")

from config import Client as _BotClient   # noqa


# ─────────────────────────────────────────────────────────────
# دالة eor المساعدة (Edit Or Reply)
# تُصدَّر للاستخدام في الملفات الأخرى
# ─────────────────────────────────────────────────────────────

async def eor(message: Message, text: str, **kwargs) -> Message:
    """Edit if own message, else reply"""
    try:
        if message.from_user and message.from_user.is_self:
            return await message.edit(text, **kwargs)
    except Exception:
        pass
    return await message.reply(text, **kwargs)


# ─────────────────────────────────────────────────────────────
# Async exec helper
# ─────────────────────────────────────────────────────────────

async def _aexec(code: str, client: Client, message: Message):
    exec(
        "async def __aexec(client, message): "
        + "".join(f"\n {line}" for line in code.split("\n"))
    )
    return await locals()["__aexec"](client, message)


def _only_dev_id(uid: int) -> bool:
    return is_dev(uid, 0)


# ─────────────────────────────────────────────────────────────
# /eval — تنفيذ كود Python
# ─────────────────────────────────────────────────────────────

@_BotClient.on_message(
    filters.private
    & filters.regex(r"^[./]?eval\s+")
)
async def eval_cmd(client: Client, message: Message):
    uid = message.from_user.id if message.from_user else 0
    if not _only_dev_id(uid):
        return

    parts = message.text.split(None, 1)
    if len(parts) < 2:
        return await message.reply("**الاستخدام:** `eval [كود]`")

    code = parts[1]
    status = await message.reply("`⏳ جاري التنفيذ...`")

    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = out = StringIO()

    try:
        await _aexec(code, client, message)
        evaluation = out.getvalue() or "✅ نجح بلا مخرجات"
    except Exception:
        evaluation = traceback.format_exc()
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    result = f"**→**\n`{escape(evaluation.strip())}`"

    if len(result) > 4096:
        fname = "eval_output.txt"
        with open(fname, "w", encoding="utf-8") as f:
            f.write(evaluation.strip())
        await message.reply_document(fname, caption="`→` **مرفق**")
        os.remove(fname)
        await status.delete()
    else:
        await status.edit(result)


# ─────────────────────────────────────────────────────────────
# /sh — تنفيذ أمر shell
# ─────────────────────────────────────────────────────────────

@_BotClient.on_message(
    filters.private
    & filters.regex(r"^[./]?sh\s+")
)
async def sh_cmd(client: Client, message: Message):
    uid = message.from_user.id if message.from_user else 0
    if not _only_dev_id(uid):
        return

    parts = message.text.split(None, 1)
    if len(parts) < 2:
        return await message.reply("**الاستخدام:** `sh [أمر shell]`")

    cmd  = parts[1].strip()
    status = await message.reply("`⏳ جاري التنفيذ...`")

    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        output = stdout.decode("utf-8", errors="replace").strip() or \
                 stderr.decode("utf-8", errors="replace").strip() or \
                 "✅ نجح بلا مخرجات"
    except asyncio.TimeoutError:
        output = "⏱ انتهى الوقت (timeout 30s)"
    except Exception:
        output = traceback.format_exc()

    result = f"**INPUT:**\n`{escape(cmd)}`\n\n**OUTPUT:**\n`{escape(output)}`"

    if len(result) > 4096:
        fname = "sh_output.txt"
        with open(fname, "w", encoding="utf-8") as f:
            f.write(output)
        await message.reply_document(fname, caption=f"`{escape(cmd)}`")
        os.remove(fname)
        await status.delete()
    else:
        await status.edit(result)


# ─────────────────────────────────────────────────────────────
# أوامر معلومات userbot
# ─────────────────────────────────────────────────────────────

@_BotClient.on_message(
    filters.private
    & filters.regex(r"^(معلومات البوت|بنج|ping)$")
)
async def userbot_info(client: Client, message: Message):
    uid = message.from_user.id if message.from_user else 0
    if not _only_dev_id(uid):
        return

    import time
    start = time.monotonic()
    msg   = await message.reply("🏓 ...")
    latency = (time.monotonic() - start) * 1000

    me = client.me
    bk = botkey()
    bn = botname()

    txt = (
        f"{bk} **{bn}**\n\n"
        f"🤖 **المعرف:** @{me.username or 'N/A'}\n"
        f"🆔 **الـ ID:** `{me.id}`\n"
        f"⚡ **Latency:** `{latency:.1f}ms`\n"
    )
    await msg.edit(txt)
