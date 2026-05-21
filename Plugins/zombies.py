"""
تنظيف الأشباح (Zombies Cleaner)
──────────────────────────────────
الأوامر:
  تنظيف الاشباح              → طرد الحسابات المحذوفة (Deleted Accounts)
  احصاء الاشباح              → عدّ الحسابات المحذوفة بدون طرد
──────────────────────────────────
الأشباح = حسابات Telegram المحذوفة (Deleted Account)
تبقى في المجموعة وتضخّمها بأرقام وهمية
"""

import asyncio

from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import Message

from config import botkey
from helpers.ranks import is_mod
from helpers.utils import group_enabled, resolve_text


@Client.on_message(filters.text & filters.group, group=24)
async def zombies_commands(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    text = resolve_text(m.text, cid)
    k = botkey()

    # ── احصاء الاشباح ──
    if text in ("احصاء الاشباح", "عدد الاشباح"):
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        status_msg = await m.reply(f"╔══ {k} ══╗\n┃ 🔍 جاري فحص الأعضاء...\n╚══════════╝")
        count = 0
        try:
            async for member in c.get_chat_members(cid):
                if member.user and member.user.is_deleted:
                    count += 1
        except Exception as e:
            return await status_msg.edit(f"‼️ {k} حدث خطأ: {e}")
        return await status_msg.edit(
            f"╔══ {k} ══╗\n"
            f"┃ 👻 عدد الأشباح: {count}\n"
            f"┃ استخدم 'تنظيف الاشباح' لطردهم\n"
            f"╚══════════╝"
        )

    # ── تنظيف الاشباح ──
    if text in ("تنظيف الاشباح", "حذف الاشباح", "مسح الاشباح"):
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        status_msg = await m.reply(
            f"╔══ {k} ══╗\n┃ 🔍 جاري فحص الأعضاء...\n╚══════════╝"
        )
        zombies = []
        try:
            async for member in c.get_chat_members(cid):
                if member.user and member.user.is_deleted:
                    zombies.append(member.user.id)
        except Exception as e:
            return await status_msg.edit(f"‼️ {k} حدث خطأ أثناء الفحص: {e}")

        if not zombies:
            return await status_msg.edit(
                f"╔══ {k} ══╗\n┃ ✨ لا يوجد أشباح! المجموعة نظيفة\n╚══════════╝"
            )

        await status_msg.edit(
            f"╔══ {k} ══╗\n"
            f"┃ 👻 تم العثور على {len(zombies)} شبح\n"
            f"┃ جاري الطرد...\n"
            f"╚══════════╝"
        )

        kicked = 0
        failed = 0
        for zid in zombies:
            try:
                await c.ban_chat_member(cid, zid)
                await c.unban_chat_member(cid, zid)
                kicked += 1
                await asyncio.sleep(0.3)  # تجنب FloodWait
            except FloodWait as e:
                await asyncio.sleep(e.value)
                try:
                    await c.ban_chat_member(cid, zid)
                    await c.unban_chat_member(cid, zid)
                    kicked += 1
                except Exception:
                    failed += 1
            except Exception:
                failed += 1

        result = (
            f"╔══ {k} ══╗\n"
            f"┃ ✅ تم تنظيف الأشباح!\n"
            f"┃ 👢 تم طرد: {kicked}\n"
        )
        if failed:
            result += f"┃ ⚠️ فشل طرد: {failed}\n"
        result += "╚══════════╝"
        return await status_msg.edit(result)
