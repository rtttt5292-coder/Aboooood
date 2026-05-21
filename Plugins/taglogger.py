"""
taglogger.py — تسجيل التاغات (Tag Logger)
مُستوحى من WilliamButcherBot، مُعاد كتابته لنظام ggggg (Pyrogram + Redis)

يعمل على البوت (Client) فقط — يراقب المجموعات ويُسجِّل في مجموعة اللوق:
  • أي شخص يذكر اسم/يوزر/ID المطور
  • أي شخص يرد على رسالة المطور
  • يتجاهل التسجيل إذا كانت الميزة مطفأة

الأوامر (في خاص المطور أو المجموعة):
  تفعيل التاغ   → تفعيل تسجيل التاغات
  تعطيل التاغ   → تعطيل تسجيل التاغات

متطلبات Redis:
  {DEV_ID}:taglogger:enabled  → "1" أو "0"
  {DEV_ID}:LogGroup           → chat_id مجموعة اللوق
  {DEV_ID}:DevUsername        → يوزر المطور (اختياري)
  {DEV_ID}:DevName            → اسم المطور (اختياري)
"""

import logging

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from config import r, ar, DEV_ID, DEV_ID_INT, botkey, botname
from helpers.ranks import is_dev

logger = logging.getLogger("taglogger")

from config import Client as _BotClient   # noqa

# ─── مفاتيح Redis ────────────────────────────────────────────
_ENABLED_KEY   = f"{DEV_ID}:taglogger:enabled"
_LOG_GROUP_KEY = f"{DEV_ID}:LogGroup"
_DEV_USER_KEY  = f"{DEV_ID}:DevUsername"
_DEV_NAME_KEY  = f"{DEV_ID}:DevName"


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

async def _is_taglogger_on() -> bool:
    val = await ar.get(_ENABLED_KEY)
    return val != "0"   # مفعّل افتراضياً

async def _get_log_group() -> int | None:
    val = await ar.get(_LOG_GROUP_KEY)
    try:
        return int(val) if val else None
    except Exception:
        return None

async def _get_dev_info() -> tuple[str, str]:
    """يُرجع (username, name) للمطور من Redis"""
    username = await ar.get(_DEV_USER_KEY) or ""
    name     = await ar.get(_DEV_NAME_KEY) or ""
    return username.lower(), name.lower()


# ─────────────────────────────────────────────────────────────
# دالة إرسال اللوق
# ─────────────────────────────────────────────────────────────

async def _send_tag_log(client: Client, message: Message):
    log_group = await _get_log_group()
    if not log_group:
        return   # لا مجموعة لوق محددة

    user    = message.from_user
    text    = message.text or message.caption or ""
    chat    = message.chat

    mention = user.mention if user else "مجهول"
    user_id = user.id if user else 0
    is_bot  = user.is_bot if user else False

    msg_txt = (
        f"🔔 **تاغ جديد**\n\n"
        f"**المُرسِل:** {mention} [`{user_id}`]\n"
        f"**المجموعة:** {chat.title} [`{chat.id}`]\n"
        f"**بوت:** {'نعم' if is_bot else 'لا'}\n"
        f"**النص:** {text[:300] if text else '—'}"
    )

    button = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 الرسالة", url=message.link)]
    ]) if message.link else None

    try:
        await client.send_message(
            log_group,
            msg_txt,
            reply_markup=button,
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.warning("taglogger: فشل إرسال اللوق: %s", e)


# ─────────────────────────────────────────────────────────────
# المستمع الرئيسي (group=9 مثل WBB)
# ─────────────────────────────────────────────────────────────

@_BotClient.on_message(
    ~filters.private
    & ~filters.forwarded
    & ~filters.via_bot,
    group=9
)
async def tag_logger_func(client: Client, message: Message):
    if not await _is_taglogger_on():
        return

    if not message.from_user:
        return

    # تجاهل رسائل البوت نفسه
    if message.from_user.is_bot:
        return

    dev_username, dev_name = await _get_dev_info()

    # ─── فحص الرد على رسائل المطور ──────────────────────────
    if message.reply_to_message and message.reply_to_message.from_user:
        replied_id = message.reply_to_message.from_user.id
        if replied_id == DEV_ID_INT:
            return await _send_tag_log(client, message)

    # ─── فحص الذكر في النص ──────────────────────────────────
    text = ""
    if message.text:
        text = message.text.lower()
    elif message.caption:
        text = message.caption.lower()
    else:
        return   # لا نص

    # فحص: ID أو يوزر أو اسم المطور مذكور
    triggers = [str(DEV_ID_INT)]
    if dev_username:
        triggers.append(dev_username)
    if dev_name:
        triggers.append(dev_name)

    if any(t in text for t in triggers):
        await _send_tag_log(client, message)


# ─────────────────────────────────────────────────────────────
# أوامر التحكم
# ─────────────────────────────────────────────────────────────

@_BotClient.on_message(
    filters.regex(r"^(تفعيل التاغ|تعطيل التاغ|حالة التاغ)$")
)
async def taglogger_control(client: Client, message: Message):
    uid = message.from_user.id if message.from_user else 0
    if not is_dev(uid, 0):
        return

    txt = message.text.strip()

    if txt == "حالة التاغ":
        state = "مفعّل ✅" if await _is_taglogger_on() else "معطّل ❌"
        return await message.reply_text(f"تسجيل التاغات: {state}")

    if txt == "تفعيل التاغ":
        await ar.set(_ENABLED_KEY, "1")
        return await message.reply_text("✅ تم تفعيل تسجيل التاغات.")

    if txt == "تعطيل التاغ":
        await ar.set(_ENABLED_KEY, "0")
        return await message.reply_text("❌ تم تعطيل تسجيل التاغات.")


@_BotClient.on_message(
    filters.private
    & filters.regex(r"^وضع لوق\s+")
)
async def set_log_group(client: Client, message: Message):
    """تعيين مجموعة اللوق: وضع لوق -100xxxxxxxxx"""
    uid = message.from_user.id if message.from_user else 0
    if not is_dev(uid, 0):
        return

    parts = message.text.split(None, 1)
    if len(parts) < 2:
        return await message.reply_text("**الاستخدام:** `وضع لوق [chat_id]`")

    try:
        chat_id = int(parts[1].strip())
    except ValueError:
        return await message.reply_text("❌ أدخل chat_id رقمياً صحيحاً.")

    await ar.set(_LOG_GROUP_KEY, str(chat_id))
    await message.reply_text(f"✅ تم تعيين مجموعة اللوق: `{chat_id}`")


@_BotClient.on_message(
    filters.private
    & filters.regex(r"^وضع يوزر مطور\s+")
)
async def set_dev_username(client: Client, message: Message):
    """تسجيل يوزر المطور للتاغ: وضع يوزر مطور username"""
    uid = message.from_user.id if message.from_user else 0
    if not is_dev(uid, 0):
        return

    parts = message.text.split(None, 1)
    if len(parts) < 2:
        return await message.reply_text("**الاستخدام:** `وضع يوزر مطور [username]`")

    username = parts[1].strip().lstrip("@").lower()
    await ar.set(_DEV_USER_KEY, username)
    await message.reply_text(f"✅ يوزر المطور للتاغ: `@{username}`")


@_BotClient.on_message(
    filters.private
    & filters.regex(r"^وضع اسم مطور\s+")
)
async def set_dev_name(client: Client, message: Message):
    """تسجيل اسم المطور للتاغ: وضع اسم مطور اسمي"""
    uid = message.from_user.id if message.from_user else 0
    if not is_dev(uid, 0):
        return

    parts = message.text.split(None, 1)
    if len(parts) < 2:
        return await message.reply_text("**الاستخدام:** `وضع اسم مطور [الاسم]`")

    name = parts[1].strip().lower()
    await ar.set(_DEV_NAME_KEY, name)
    await message.reply_text(f"✅ اسم المطور للتاغ: `{name}`")
