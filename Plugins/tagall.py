"""
نظام تاق الكل (@all / تاق الكل)
─────────────────────────────────────────────────────────────
الأوامر:
  تاق الكل [نص]      → منشن لجميع الأعضاء (مدير+)
  @all [نص]          → نفس الأمر
  تاق الادمنيه       → منشن للمدراء فقط (مدير+)
  وقف التاق          → إيقاف التاق الجاري (مدير+)
─────────────────────────────────────────────────────────────
"""

import asyncio

from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import Message

from config import DEV_ID, botkey, ar
from helpers.ranks import is_admin, is_mod
from helpers.utils import group_enabled, resolve_text


# ── مجموعات جارٍ فيها تاق حالياً ──────────────────────────
_tagging: set[int] = set()


# ═══════════════════════════════════════════════════════════════
# معالج الأوامر
# ═══════════════════════════════════════════════════════════════

@Client.on_message(filters.text & filters.group, group=2)
async def tagall_cmd(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return

    text = resolve_text(m.text.strip(), cid)
    k = botkey()

    # ── وقف التاق ──────────────────────────────────────────
    if text in ("وقف التاق", "ايقاف التاق", "إيقاف التاق"):
        if not (is_admin(uid, cid) or is_mod(uid, cid)):
            return
        if cid in _tagging:
            _tagging.discard(cid)
            await m.reply(f"{k} تم إيقاف التاق ✅")
        else:
            await m.reply(f"{k} لا يوجد تاق جارٍ.")
        return

    # ── تاق الادمنيه ───────────────────────────────────────
    if text.startswith("تاق الادمنيه") or text.startswith("تاق الإدارة"):
        if not (is_admin(uid, cid) or is_mod(uid, cid)):
            return
        extra_text = text.split(None, 1)[1] if len(text.split(None, 1)) > 1 else ""
        asyncio.get_event_loop().create_task(
            _do_tagall(c, m, cid, uid, extra_text, admins_only=True)
        )
        return

    # ── تاق الكل ───────────────────────────────────────────
    is_tagall = (
        text.startswith("تاق الكل") or
        text.startswith("@all") or
        text.startswith("منشن الكل")
    )
    if not is_tagall:
        return
    if not (is_admin(uid, cid) or is_mod(uid, cid)):
        await m.reply(f"{k} هذا الأمر للمدراء فقط.")
        return

    # استخراج النص المرافق
    for prefix in ("تاق الكل", "@all", "منشن الكل"):
        if text.startswith(prefix):
            extra_text = text[len(prefix):].strip()
            break
    else:
        extra_text = ""

    asyncio.get_event_loop().create_task(
        _do_tagall(c, m, cid, uid, extra_text, admins_only=False)
    )


async def _do_tagall(c: Client, m: Message, cid: int, uid: int,
                     extra_text: str, admins_only: bool):
    """ينفّذ التاق بشكل غير متزامن دون تجميد البوت"""
    k = botkey()
    if cid in _tagging:
        await m.reply(f"{k} يوجد تاق جارٍ بالفعل! استخدم **وقف التاق** لإيقافه.")
        return

    _tagging.add(cid)
    header = f"{extra_text}\n" if extra_text else ""

    try:
        if admins_only:
            admins = await c.get_chat_members(cid, filter="administrators")
            members_iter = iter(admins)
        else:
            members_iter = c.get_chat_members(cid)

        batch = []
        count = 0

        async def send_batch():
            nonlocal count
            if not batch:
                return
            mentions = " ".join(batch)
            try:
                await c.send_message(cid, f"{header}{mentions}")
            except FloodWait as fw:
                await asyncio.sleep(fw.value)
            except Exception:
                pass
            await asyncio.sleep(2)
            count += len(batch)
            batch.clear()

        async for member in members_iter:
            if cid not in _tagging:
                break
            if member.user.is_bot or member.user.is_deleted:
                continue
            mention = f"[‍](tg://user?id={member.user.id})"
            batch.append(mention)
            if len(batch) == 5:
                await send_batch()

        await send_batch()  # الباقي

        if cid in _tagging:
            _tagging.discard(cid)
            msg = f"{k} تم تاق **{count}** عضو بنجاح ✅"
            if extra_text:
                msg = f"{extra_text}\n\n{k} تم تاق **{count}** عضو ✅"
            try:
                await c.send_message(cid, msg)
            except Exception:
                pass

    except Exception as e:
        _tagging.discard(cid)
