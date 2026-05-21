"""
نظام التثبيت (Pins)
────────────────────
الأوامر:
  ثبّت (رد)        → تثبيت رسالة (مدير+)
  ثبّت بهدوء (رد)  → تثبيت بدون إشعار (مدير+)
  ألغِ التثبيت     → إلغاء تثبيت الرسالة الحالية (مدير+)
  المثبّت          → عرض الرسالة المثبتة الحالية
────────────────────
"""

from pyrogram import Client, filters
from pyrogram.errors import FloodWait, ChatAdminRequired
from pyrogram.types import Message

from config import r, DEV_ID, botkey
from helpers.ranks import is_mod
from helpers.utils import group_enabled, resolve_text


@Client.on_message(filters.text & filters.group, group=49)
async def pins_commands(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    text = resolve_text(m.text, cid)
    k = botkey()

    # ── ثبّت (رد) ──
    if text in ("ثبّت", "ثبت", "ثبت الرسالة", "ثبّت الرسالة"):
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        if not m.reply_to_message:
            return await m.reply(f"╔══ {k} ══╗\n┃ ردّ على الرسالة التي تريد تثبيتها\n╚══════════╝")
        try:
            await c.pin_chat_message(cid, m.reply_to_message.id, disable_notification=False)
            return await m.reply(
                f"╔══ {k} ══╗\n┃ 📌 تم تثبيت الرسالة ✅\n╚══════════╝"
            )
        except ChatAdminRequired:
            return await m.reply(f"‼️ {k} ليس لديّ صلاحية التثبيت")
        except Exception as e:
            return await m.reply(f"‼️ {k} فشل التثبيت: {e}")

    # ── ثبّت بهدوء ──
    if text in ("ثبّت بهدوء", "ثبت بهدوء", "تثبيت هادئ"):
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        if not m.reply_to_message:
            return await m.reply(f"╔══ {k} ══╗\n┃ ردّ على الرسالة التي تريد تثبيتها\n╚══════════╝")
        try:
            await c.pin_chat_message(cid, m.reply_to_message.id, disable_notification=True)
            return await m.reply(
                f"╔══ {k} ══╗\n┃ 📌 تم التثبيت بصمت ✅\n╚══════════╝"
            )
        except ChatAdminRequired:
            return await m.reply(f"‼️ {k} ليس لديّ صلاحية التثبيت")
        except Exception as e:
            return await m.reply(f"‼️ {k} فشل التثبيت: {e}")

    # ── ألغِ التثبيت ──
    if text in ("الغِ التثبيت", "الغ التثبيت", "فك التثبيت", "الغاء التثبيت"):
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        try:
            await c.unpin_chat_message(cid)
            return await m.reply(
                f"╔══ {k} ══╗\n┃ 📌 تم إلغاء التثبيت ✅\n╚══════════╝"
            )
        except ChatAdminRequired:
            return await m.reply(f"‼️ {k} ليس لديّ صلاحية إلغاء التثبيت")
        except Exception as e:
            return await m.reply(f"‼️ {k} فشل إلغاء التثبيت: {e}")

    # ── عرض المثبّت ──
    if text in ("المثبّت", "المثبت", "الرسالة المثبتة"):
        try:
            chat = await c.get_chat(cid)
            if chat.pinned_message:
                pm = chat.pinned_message
                link = ""
                if m.chat.username:
                    link = f"\n┃ الرابط: https://t.me/{m.chat.username}/{pm.id}"
                return await m.reply(
                    f"╔══ {k} ══╗\n"
                    f"┃ 📌 يوجد رسالة مثبتة"
                    f"{link}\n"
                    f"╚══════════╝"
                )
            else:
                return await m.reply(f"✨ {k} لا توجد رسالة مثبتة حالياً")
        except Exception:
            return await m.reply(f"‼️ {k} تعذّر جلب الرسالة المثبتة")
