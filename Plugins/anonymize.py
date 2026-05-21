"""
anonymize.py — إرسال مجهول / انتحال هوية
مُستوحى من WilliamButcherBot، مُعاد كتابته لنظام ggggg (Pyrogram + Redis)

يعمل على البوت (Client) — يُرسل رسائل باسم البوت من الخاص

الأوامر (في خاص المطور):
  مجهول [نص]     → إرسال رسالة نصية مجهولة (البوت لا يكشف المُرسِل)
  مجهول (رد)     → إرسال ميديا مجهولة (برد على ميديا)
  لمن @username [نص] → إرسال رسالة مجهولة لمستخدم محدد

ملاحظة: هذا يعمل فقط من خاص المطور — البوت يُرسِل الرسالة للمجموعة/المستخدم
        كأنها من البوت مما يخفي هوية المُرسِل.
"""

import logging
import asyncio
import httpx
from io import BytesIO
from secrets import choice

from pyrogram import Client, filters
from pyrogram.types import Message

from config import r, ar, DEV_ID, DEV_ID_INT, botkey, botname
from helpers.ranks import is_dev

logger = logging.getLogger("anonymize")

_http = httpx.AsyncClient(timeout=30)

from config import Client as _BotClient   # noqa


# ─── مساعد: تحميل صورة عشوائية لشخص غير حقيقي ─────────────
async def _random_face() -> BytesIO | None:
    try:
        resp = await _http.get("https://thispersondoesnotexist.com/image")
        resp.raise_for_status()
        buf = BytesIO(resp.content)
        buf.name = "face.jpg"
        return buf
    except Exception as e:
        logger.warning("anonymize: فشل تحميل الصورة: %s", e)
        return None

# ─── مساعد: اسم عشوائي ──────────────────────────────────────
async def _random_name() -> str:
    try:
        resp = await _http.get(
            "https://raw.githubusercontent.com/dominictarr/random-name/master/first-names.json",
            timeout=10
        )
        import json
        names = json.loads(resp.text)
        return choice(names)
    except Exception:
        return "Anonymous"


# ─────────────────────────────────────────────────────────────
# أمر: مجهول [نص] أو (رد على ميديا)
# ─────────────────────────────────────────────────────────────

@_BotClient.on_message(
    filters.private
    & filters.regex(r"^مجهول(\s|$)")
)
async def anonymize_send(client: Client, message: Message):
    """إرسال رسالة مجهولة باسم البوت في نفس المحادثة"""
    uid = message.from_user.id if message.from_user else 0
    if not is_dev(uid, 0):
        return await message.reply_text("⛔ هذا الأمر للمطور فقط.")

    parts = message.text.split(None, 1)
    text  = parts[1].strip() if len(parts) > 1 else ""

    # رد على ميديا → إعادة إرسالها مجهولة
    if message.reply_to_message:
        rm = message.reply_to_message
        target = message.chat.id
        try:
            if rm.photo:
                await client.send_photo(target, rm.photo.file_id, caption=text or rm.caption)
            elif rm.video:
                await client.send_video(target, rm.video.file_id, caption=text or rm.caption)
            elif rm.document:
                await client.send_document(target, rm.document.file_id, caption=text or rm.caption)
            elif rm.sticker:
                await client.send_sticker(target, rm.sticker.file_id)
            elif rm.audio:
                await client.send_audio(target, rm.audio.file_id, caption=text or rm.caption)
            elif rm.voice:
                await client.send_voice(target, rm.voice.file_id)
            elif rm.text:
                await client.send_message(target, rm.text)
            else:
                return await message.reply_text("نوع الميديا غير مدعوم.")
            await message.delete()
        except Exception as e:
            await message.reply_text(f"❌ خطأ: {e}")
        return

    if not text:
        return await message.reply_text(
            "**الاستخدام:**\n"
            "`مجهول [نص]` — إرسال نص مجهول\n"
            "`مجهول` (رد على ميديا) — إرسال ميديا مجهولة"
        )

    try:
        await client.send_message(message.chat.id, text)
        await message.delete()
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {e}")


# ─────────────────────────────────────────────────────────────
# أمر: لمن @username [نص]  → إرسال رسالة لشخص محدد
# ─────────────────────────────────────────────────────────────

@_BotClient.on_message(
    filters.private
    & filters.regex(r"^لمن\s+")
)
async def anonymize_to_user(client: Client, message: Message):
    uid = message.from_user.id if message.from_user else 0
    if not is_dev(uid, 0):
        return await message.reply_text("⛔ هذا الأمر للمطور فقط.")

    parts = message.text.split(None, 2)
    if len(parts) < 2:
        return await message.reply_text("**الاستخدام:** `لمن @username [نص]`")

    target_raw = parts[1].lstrip("@")
    text       = parts[2].strip() if len(parts) > 2 else "."

    try:
        user = await client.get_users(target_raw)
    except Exception as e:
        return await message.reply_text(f"❌ لم أجد المستخدم: {e}")

    bk = botkey()
    try:
        await client.send_message(user.id, text)
        await message.reply_text(f"✅ تم الإرسال لـ {user.mention} مجهولاً.")
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {e}")


# ─────────────────────────────────────────────────────────────
# أمر: اخفاء هويتي  → تغيير صورة واسم الحساب (يتطلب app2 userbot)
# ─────────────────────────────────────────────────────────────
# إذا أضيف userbot (app2) لاحقاً يمكن تفعيل هذا الجزء

async def do_anonymize_profile(app2):
    """تغيير الصورة والاسم إلى هوية عشوائية (للـ userbot)"""
    img  = await _random_face()
    name = await _random_name()
    tasks = [app2.update_profile(first_name=name)]
    if img:
        tasks.append(app2.set_profile_photo(photo=img))
    await asyncio.gather(*tasks)
    return name
