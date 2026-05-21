"""
نظام الاشتراك الإجباري (Force Subscribe)
──────────────────────────────────────────
الأوامر:
  تفعيل القسري [@channel أو id]   → تفعيل الاشتراك الإجباري
  تعطيل القسري                     → إيقاف الاشتراك الإجباري
  القسري                            → عرض القناة الحالية
──────────────────────────────────────────
كيف يعمل:
  - عند إرسال رسالة من غير مشترك: يحذف الرسالة ويطلب الاشتراك
  - المميزون والإداريون معفيون
"""

import re

from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import UserNotParticipant, ChatAdminRequired, ChannelInvalid
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from config import ar, DEV_ID, botkey
from helpers.ranks import is_pre, is_mod
from helpers.utils import group_enabled, resolve_text

# ── مفاتيح Redis ──
def _fsub_key(cid: int) -> str:
    return f"{cid}:fsub:{DEV_ID}"

def _fsub_channel_key(cid: int) -> str:
    return f"{cid}:fsub_channel:{DEV_ID}"


# ─────────────────────────────────────────────────────────────────────────
# مراقب الرسائل — يتحقق من الاشتراك
# ─────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.group, group=20)
async def fsub_watcher(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    if not await ar.get(_fsub_key(cid)):
        return
    if is_pre(uid, cid):
        return

    channel = await ar.get(_fsub_channel_key(cid))
    if not channel:
        return

    try:
        member = await c.get_chat_member(channel, uid)
        if member.status in (
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
        ):
            return  # مشترك → اسمح له
    except UserNotParticipant:
        pass
    except Exception:
        return  # خطأ في الجلب → اسمح بمرور الرسالة

    # غير مشترك — احذف الرسالة وأرسل تنبيه
    k = botkey()
    mention = m.from_user.mention

    # جهّز رابط القناة
    if str(channel).startswith("-100"):
        try:
            ch = await c.get_chat(channel)
            invite = await c.export_chat_invite_link(int(channel)) if not ch.username else f"https://t.me/{ch.username}"
            ch_name = ch.title
        except Exception:
            invite = None
            ch_name = "القناة"
    else:
        invite = f"https://t.me/{str(channel).lstrip('@')}"
        ch_name = str(channel).lstrip('@')

    try:
        await m.delete()
    except Exception:
        pass

    keyboard = None
    if invite:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(f"📢 اشترك في {ch_name}", url=invite)
        ]])

    try:
        await c.send_message(
            cid,
            f"╔══ {k} ══╗\n"
            f"┃ 🔒 {mention}\n"
            f"┃ يجب الاشتراك في القناة أولاً\n"
            f"┃ ثم أعد إرسال رسالتك ✅\n"
            f"╚══════════╝",
            reply_markup=keyboard
        )
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────
# أوامر الإعداد
# ─────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.text & filters.group, group=21)
async def fsub_commands(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    text = resolve_text(m.text, cid)
    k = botkey()

    # ── تفعيل القسري ──
    fsub_match = re.fullmatch(r"تفعيل القسري\s+(@?\S+)", text)
    if fsub_match:
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        channel = fsub_match.group(1)
        # تحقق من وجود القناة
        try:
            ch = await c.get_chat(channel)
            channel_id = ch.id
            ch_name = ch.title
        except Exception:
            return await m.reply(f"‼️ {k} لم أجد القناة، تأكد من أن البوت مشرف فيها")
        await ar.set(_fsub_key(cid), 1)
        await ar.set(_fsub_channel_key(cid), str(channel_id))
        return await m.reply(
            f"╔══ {k} ══╗\n"
            f"┃ ✅ تم تفعيل الاشتراك الإجباري\n"
            f"┃ القناة: {ch_name}\n"
            f"╚══════════╝"
        )

    # ── تعطيل القسري ──
    if text in ("تعطيل القسري", "ايقاف القسري"):
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        await ar.delete(_fsub_key(cid))
        await ar.delete(_fsub_channel_key(cid))
        return await m.reply(
            f"╔══ {k} ══╗\n┃ ❌ تم تعطيل الاشتراك الإجباري\n╚══════════╝"
        )

    # ── القسري ──
    if text in ("القسري", "اعدادات القسري"):
        enabled  = await ar.get(_fsub_key(cid))
        channel  = await ar.get(_fsub_channel_key(cid))
        status   = "مفعّل ✅" if enabled else "معطّل ❌"
        ch_text  = channel if channel else "—"
        if channel:
            try:
                ch = await c.get_chat(int(channel))
                ch_text = ch.title
            except Exception:
                pass
        return await m.reply(
            f"╔══ {k} ══╗\n"
            f"┃ 🔒 الاشتراك الإجباري: {status}\n"
            f"┃ القناة: {ch_text}\n"
            f"╚══════════╝"
        )
