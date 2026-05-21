"""
pmpermit.py — حماية الخاص (PM Permit)
مُستوحى من WilliamButcherBot، مُعاد كتابته لنظام ggggg (Pyrogram + Redis)

الأوامر (بالبوت — Client):
  callback: pmpermit_approve / pmpermit_block / pmpermit_approve_me / pmpermit_scam
  يُرسل رسالة inline تلقائياً لمن يراسل الحساب دون موافقة

الأوامر (إن أضيف userbot — app2):
  .approve   → الموافقة على مستخدم في الخاص
  .disapprove→ إلغاء الموافقة
  .block     → حظر مستخدم
  .unblock   → رفع الحظر

متطلبات Redis:
  {DEV_ID}:pmpermit:approved  → Set  (user_id للمصادق عليهم)
  {DEV_ID}:pmpermit:enabled   → "1" أو "0"
"""

import asyncio
import logging

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)

from config import r, ar, DEV_ID, DEV_ID_INT, botkey, botname
from helpers.ranks import is_dev

logger = logging.getLogger("pmpermit")

# ─── مفاتيح Redis ────────────────────────────────────────────
_APPROVED_KEY = f"{DEV_ID}:pmpermit:approved"
_ENABLED_KEY  = f"{DEV_ID}:pmpermit:enabled"

# ─── flood counter (ذاكرة محلية — يُعاد عند إعادة التشغيل) ──
_flood: dict[str, int] = {}
_flood2: dict[str, int] = {}

# ─────────────────────────────────────────────────────────────
# DB helpers (Redis Sets بدلاً من MongoDB)
# ─────────────────────────────────────────────────────────────

async def _is_approved(user_id: int) -> bool:
    return bool(await ar.sismember(_APPROVED_KEY, str(user_id)))

async def _approve(user_id: int):
    await ar.sadd(_APPROVED_KEY, str(user_id))

async def _disapprove(user_id: int):
    await ar.srem(_APPROVED_KEY, str(user_id))

async def _is_pmpermit_on() -> bool:
    val = await ar.get(_ENABLED_KEY)
    return val != "0"   # مفعّل افتراضياً

async def _set_pmpermit(enabled: bool):
    await ar.set(_ENABLED_KEY, "1" if enabled else "0")


# ─────────────────────────────────────────────────────────────
# أوامر التحكم (في خاص المطور أو بأمر مباشر)
# ─────────────────────────────────────────────────────────────

from config import Client as _BotClient   # noqa: E402

@_BotClient.on_message(
    filters.private
    & filters.incoming
    & ~filters.service
    & ~filters.me
    & ~filters.bot
    & ~filters.via_bot
)
async def pmpermit_guard(client: Client, message: Message):
    """يستقبل رسائل الخاص من غير المصادق عليهم"""
    if not message.from_user:
        return

    uid = message.from_user.id

    # المطور يتجاوز الحماية دائماً
    if is_dev(uid, 0):
        return

    # إذا كانت الميزة مطفأة أو المستخدم مصادق عليه → تجاهل
    if not await _is_pmpermit_on() or await _is_approved(uid):
        return

    # حساب flood
    key = str(uid)
    _flood[key] = _flood.get(key, 0) + 1

    if _flood[key] > 5:
        await message.reply_text("🚫 تم رصد سبام — تم حظرك تلقائياً.")
        try:
            await client.block_user(uid)
        except Exception:
            pass
        return

    bk  = botkey()
    bn  = botname()
    txt = (
        f"{bk} أهلاً! صاحب الحساب مشغول الآن.\n"
        f"اضغط **«اطلب الموافقة»** وانتظر، أو سيتم حظرك عند الإفراط."
    )

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ وافِق",        callback_data=f"pmpermit_approve {uid}"),
            InlineKeyboardButton("🚫 احظر",         callback_data=f"pmpermit_block {uid}"),
        ],
        [
            InlineKeyboardButton("📨 اطلب الموافقة", callback_data=f"pmpermit_approve_me {uid}"),
            InlineKeyboardButton("⚠️ محتال",         callback_data=f"pmpermit_scam {uid}"),
        ],
    ])

    await message.reply_text(txt, reply_markup=kb)


# ─────────────────────────────────────────────────────────────
# Callback Queries
# ─────────────────────────────────────────────────────────────

@_BotClient.on_callback_query(filters.regex(r"^pmpermit_"))
async def pmpermit_callback(client: Client, cq: CallbackQuery):
    parts   = cq.data.split()
    action  = parts[0]          # pmpermit_approve | pmpermit_block | ...
    victim  = int(parts[1]) if len(parts) > 1 else 0
    caller  = cq.from_user.id

    # ─── أزرار المطور ────────────────────────────────────────
    if action == "pmpermit_approve":
        if not is_dev(caller, 0):
            return await cq.answer("هذا الزر ليس لك!", show_alert=True)
        await _approve(victim)
        _flood.pop(str(victim), None)
        await cq.message.edit_text(f"✅ تمت الموافقة على المستخدم `{victim}`.")
        return await cq.answer()

    if action == "pmpermit_block":
        if not is_dev(caller, 0):
            return await cq.answer("هذا الزر ليس لك!", show_alert=True)
        await cq.message.edit_text(f"🚫 تم حظر المستخدم `{victim}`.")
        await cq.answer()
        try:
            await client.block_user(victim)
        except Exception:
            pass
        return

    # ─── أزرار الضيف ─────────────────────────────────────────
    if action == "pmpermit_scam":
        if caller == DEV_ID_INT:
            return await cq.answer("هذا الزر للضيف وليس لك.", show_alert=True)
        await client.send_message(caller, "تم حظرك بسبب السبام/الاحتيال. 🚫")
        await cq.answer()
        try:
            await client.block_user(caller)
        except Exception:
            pass
        return

    if action == "pmpermit_approve_me":
        if caller == DEV_ID_INT:
            return await cq.answer("هذا الزر للضيف.", show_alert=True)
        key2 = str(caller)
        _flood2[key2] = _flood2.get(key2, 0) + 1
        if _flood2[key2] > 5:
            await client.send_message(caller, "سبام مكتشف — تم حظرك. 🚫")
            await cq.answer()
            try:
                await client.block_user(caller)
            except Exception:
                pass
            return
        await client.send_message(
            caller,
            "📨 تم إرسال طلبك، انتظر الموافقة ولا تضغط أكثر من مرة."
        )
        await cq.answer("تم إرسال طلبك ✅")


# ─────────────────────────────────────────────────────────────
# أوامر التحكم في الخاص (المطور فقط)
# ─────────────────────────────────────────────────────────────

async def _only_dev(message: Message) -> bool:
    uid = message.from_user.id if message.from_user else 0
    if not is_dev(uid, 0):
        await message.reply_text("⛔ هذا الأمر للمطور فقط.")
        return False
    return True


@_BotClient.on_message(
    filters.private
    & filters.regex(r"^(تفعيل الخاص|تعطيل الخاص|وافق|ارفض|الخاص)$")
)
async def pmpermit_control(client: Client, message: Message):
    if not await _only_dev(message):
        return

    txt = message.text.strip()

    if txt == "الخاص":
        state = "مفعّل ✅" if await _is_pmpermit_on() else "معطّل ❌"
        return await message.reply_text(f"حماية الخاص: {state}")

    if txt == "تفعيل الخاص":
        await _set_pmpermit(True)
        return await message.reply_text("✅ تم تفعيل حماية الخاص.")

    if txt == "تعطيل الخاص":
        await _set_pmpermit(False)
        return await message.reply_text("❌ تم تعطيل حماية الخاص.")

    if txt == "وافق":
        if not message.reply_to_message or not message.reply_to_message.from_user:
            return await message.reply_text("رُد على رسالة المستخدم المراد الموافقة عليه.")
        uid = message.reply_to_message.from_user.id
        await _approve(uid)
        _flood.pop(str(uid), None)
        await message.reply_text(f"✅ تمت الموافقة على `{uid}`.")

    if txt == "ارفض":
        if not message.reply_to_message or not message.reply_to_message.from_user:
            return await message.reply_text("رُد على رسالة المستخدم المراد رفضه.")
        uid = message.reply_to_message.from_user.id
        await _disapprove(uid)
        await message.reply_text(f"🚫 تم رفع الموافقة عن `{uid}`.")
