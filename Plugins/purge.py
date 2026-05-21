"""
نظام الحذف الجماعي (Purge)
───────────────────────────
الأوامر:
  مسح              → حذف كل الرسائل من رسالة الرد حتى الآن (مدير+)
  مسح [عدد]        → حذف آخر [عدد] رسالة
  مسح رسالتي       → حذف رسائل عضو معين (رد عليه) (مدير+)
───────────────────────────
يعمل بـ Pyrogram + Redis، نمط gggggggg
"""

import asyncio
import re

from pyrogram import Client, filters
from pyrogram.errors import FloodWait, MessageDeleteForbidden
from pyrogram.types import Message

from config import r, ar, DEV_ID, botkey
from helpers.ranks import is_mod, is_pre
from helpers.utils import group_enabled, resolve_text


async def _delete_batch(c: Client, cid: int, msg_ids: list) -> int:
    """حذف مجموعة رسائل مع تجاهل الأخطاء"""
    deleted = 0
    # Pyrogram تحذف 100 رسالة كحد أقصى في طلب واحد
    for i in range(0, len(msg_ids), 100):
        batch = msg_ids[i:i + 100]
        try:
            await c.delete_messages(cid, batch)
            deleted += len(batch)
        except FloodWait as e:
            await asyncio.sleep(e.value)
            try:
                await c.delete_messages(cid, batch)
                deleted += len(batch)
            except Exception:
                pass
        except Exception:
            pass
    return deleted


@Client.on_message(filters.text & filters.group, group=46)
async def purge_commands(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    text = resolve_text(m.text, cid)
    k = botkey()

    # ── مسح (رد) أو مسح [عدد] ──
    purge_m = re.fullmatch(r"مسح(?:\s+(\d+))?", text)
    if purge_m:
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")

        count_arg = purge_m.group(1)

        if count_arg:
            # مسح آخر N رسائل
            count = min(int(count_arg), 500)
            msg_ids = list(range(m.id - count, m.id + 1))
            notice = await m.reply(f"⏳ {k} جاري حذف {count} رسالة...")
            deleted = await _delete_batch(c, cid, msg_ids)
            try:
                await notice.edit_text(
                    f"╔══ {k} ══╗\n"
                    f"┃ تم حذف ~{deleted} رسالة 🗑️\n"
                    f"╚══════════╝"
                )
                # حذف رسالة الإشعار بعد 5 ثوانٍ
                await asyncio.sleep(5)
                await notice.delete()
            except Exception:
                pass

        elif m.reply_to_message:
            # مسح من رسالة الرد حتى الآن
            from_id = m.reply_to_message.id
            to_id   = m.id
            msg_ids = list(range(from_id, to_id + 1))
            notice  = await m.reply(f"⏳ {k} جاري الحذف...")
            deleted = await _delete_batch(c, cid, msg_ids)
            try:
                await notice.edit_text(
                    f"╔══ {k} ══╗\n"
                    f"┃ تم حذف ~{deleted} رسالة 🗑️\n"
                    f"╚══════════╝"
                )
                await asyncio.sleep(5)
                await notice.delete()
            except Exception:
                pass
        else:
            return await m.reply(
                f"╔══ {k} ══╗\n"
                f"┃ ردّ على رسالة لتحديد البداية\n"
                f"┃ أو اكتب: مسح [عدد]\n"
                f"╚══════════╝"
            )
        return

    # ── مسح رسالتي (حذف رسائل عضو) ──
    if text == "مسح رسالتي":
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        if not m.reply_to_message or not m.reply_to_message.from_user:
            return await m.reply(
                f"╔══ {k} ══╗\n"
                f"┃ ردّ على رسالة العضو الذي تريد حذف رسائله\n"
                f"╚══════════╝"
            )
        target = m.reply_to_message.from_user
        if is_pre(target.id, cid):
            return await m.reply(f"‼️ {k} لا يمكن حذف رسائل المميزين والإداريين")

        # نمر على آخر 100 رسالة ونحذف ما تخص العضو
        notice = await m.reply(f"⏳ {k} جاري البحث والحذف...")
        to_delete = []
        async for msg in c.get_chat_history(cid, limit=200):
            if msg.from_user and msg.from_user.id == target.id:
                to_delete.append(msg.id)

        deleted = await _delete_batch(c, cid, to_delete)
        try:
            await notice.edit_text(
                f"╔══ {k} ══╗\n"
                f"┃ تم حذف {deleted} رسالة لـ {target.mention} 🗑️\n"
                f"╚══════════╝"
            )
            await asyncio.sleep(5)
            await notice.delete()
        except Exception:
            pass
