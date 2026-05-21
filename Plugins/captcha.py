"""
نظام الكابتشا (التحقق من الأعضاء الجدد)
─────────────────────────────────────────────────────────────
الأوامر:
  تفعيل الكابتشا          → تشغيل التحقق عند الدخول (مدير+)
  تعطيل الكابتشا          → إيقاف التحقق (مدير+)
  نوع الكابتشا [عدد|نص|زر] → اختر نوع التحقق (مدير+)
  مهلة الكابتشا [ثواني]   → مهلة الإجابة قبل الطرد (افتراضي: 60 ث)
  حالة الكابتشا           → عرض الإعدادات الحالية
─────────────────────────────────────────────────────────────
الأنواع:
  عدد  → اضغط الزر الصحيح (حساب بسيط مثل 3+4)
  نص   → اكتب الرمز المعروض
  زر   → اضغط زر "لستُ روبوت"
─────────────────────────────────────────────────────────────
"""

import asyncio
import random
import time

from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import (
    ChatMemberUpdated, InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
)

from config import r, ar, DEV_ID, botkey
from helpers.ranks import is_admin, is_mod
from helpers.utils import group_enabled, resolve_text


# ── مفاتيح Redis ──────────────────────────────────────────────────────────
def _cap_on_key(cid: int)     -> str: return f"{cid}:captcha_on:{DEV_ID}"
def _cap_type_key(cid: int)   -> str: return f"{cid}:captcha_type:{DEV_ID}"
def _cap_timeout_key(cid: int)-> str: return f"{cid}:captcha_timeout:{DEV_ID}"

# ── حالة مؤقتة: {(cid, uid): {answer, msg_id, task, ts}} ─────────────────
_pending: dict = {}


# ═══════════════════════════════════════════════════════════════
# مراقب الأعضاء الجدد
# ═══════════════════════════════════════════════════════════════

@Client.on_chat_member_updated(filters.group)
async def captcha_new_member(c: Client, update: ChatMemberUpdated):
    if not update.new_chat_member:
        return
    old = update.old_chat_member
    if old and old.status in ("member", "administrator", "creator"):
        return  # ليس عضو جديد

    cid = update.chat.id
    if not group_enabled(cid):
        return
    if not await ar.get(_cap_on_key(cid)):
        return

    user = update.new_chat_member.user
    if not user or user.is_bot:
        return

    cap_type = (await ar.get(_cap_type_key(cid))) or "زر"
    timeout  = int((await ar.get(_cap_timeout_key(cid))) or 60)

    try:
        # كتم العضو الجديد مؤقتاً
        await c.restrict_chat_member(
            cid, user.id,
            permissions=__import__("pyrogram.types", fromlist=["ChatPermissions"]).ChatPermissions(
                can_send_messages=False
            )
        )
    except Exception:
        return

    # ── اختر نوع الكابتشا ──────────────────────────────────
    if cap_type == "عدد":
        a, b = random.randint(1, 9), random.randint(1, 9)
        correct = a + b
        choices = list({correct, correct + random.randint(1,3), correct - random.randint(1,3), random.randint(1,18)})
        random.shuffle(choices)
        text = (f"👋 مرحباً {user.mention}!\n"
                f"⚡ للتحقق من أنك لستَ روبوت، أجب على:\n\n"
                f"**{a} + {b} = ?**\n\n"
                f"⏱ لديك **{timeout}** ثانية للإجابة وإلا ستُطرد.")
        buttons = [[InlineKeyboardButton(str(ch), callback_data=f"cap:{cid}:{user.id}:{correct}:{ch}")
                    for ch in choices]]
        answer = str(correct)
    elif cap_type == "نص":
        code = _random_code()
        text = (f"👋 مرحباً {user.mention}!\n"
                f"⚡ اكتب الرمز التالي للتحقق:\n\n"
                f"`{code}`\n\n"
                f"⏱ لديك **{timeout}** ثانية وإلا ستُطرد.")
        buttons = []
        answer = code
    else:  # زر
        text = (f"👋 مرحباً {user.mention}!\n"
                f"⚡ اضغط الزر أدناه للتحقق من أنك لستَ روبوت.\n\n"
                f"⏱ لديك **{timeout}** ثانية وإلا ستُطرد.")
        buttons = [[InlineKeyboardButton("✅ لستُ روبوت", callback_data=f"cap:{cid}:{user.id}:btn:btn")]]
        answer = "btn"

    markup = InlineKeyboardMarkup(buttons) if buttons else None
    try:
        sent = await c.send_message(cid, text, reply_markup=markup)
    except Exception:
        return

    # مهمة الطرد التلقائي بعد انتهاء المهلة
    task = asyncio.get_event_loop().create_task(
        _captcha_timeout(c, cid, user.id, sent.id, timeout)
    )
    _pending[(cid, user.id)] = {
        "answer": answer,
        "msg_id": sent.id,
        "task": task,
        "ts": time.monotonic(),
        "type": cap_type,
    }


def _random_code(length: int = 5) -> str:
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(random.choices(chars, k=length))


async def _captcha_timeout(c: Client, cid: int, uid: int, msg_id: int, delay: int):
    await asyncio.sleep(delay)
    if (cid, uid) not in _pending:
        return
    _pending.pop((cid, uid), None)
    try:
        await c.delete_messages(cid, msg_id)
        await c.ban_chat_member(cid, uid)
        await asyncio.sleep(2)
        await c.unban_chat_member(cid, uid)  # طرد بدون حظر دائم
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
# معالج ضغط الأزرار (عدد / زر)
# ═══════════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex(r"^cap:"))
async def captcha_callback(c: Client, query: CallbackQuery):
    parts = query.data.split(":")
    # cap:{cid}:{uid}:{correct}:{chosen}
    if len(parts) < 5:
        return await query.answer("بيانات خاطئة", show_alert=True)

    _, cid_s, uid_s, correct_s, chosen_s = parts[:5]
    cid, uid = int(cid_s), int(uid_s)

    if query.from_user.id != uid:
        return await query.answer("هذا ليس تحققك!", show_alert=True)

    data = _pending.get((cid, uid))
    if not data:
        return await query.answer("انتهت صلاحية التحقق.", show_alert=True)

    if chosen_s == correct_s or chosen_s == "btn":
        # ✅ إجابة صحيحة
        data["task"].cancel()
        _pending.pop((cid, uid), None)
        try:
            await c.restrict_chat_member(
                cid, uid,
                permissions=__import__("pyrogram.types", fromlist=["ChatPermissions"]).ChatPermissions(
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True,
                    can_send_polls=True,
                )
            )
            await query.message.edit_text(f"✅ تم التحقق بنجاح! مرحباً بك.")
        except Exception:
            await query.answer("✅ تم التحقق!", show_alert=True)
    else:
        # ❌ إجابة خاطئة
        await query.answer("❌ إجابة خاطئة! حاول مجدداً.", show_alert=True)


# ═══════════════════════════════════════════════════════════════
# معالج رسائل النص (نوع "نص")
# ═══════════════════════════════════════════════════════════════

@Client.on_message(filters.text & filters.group, group=20)
async def captcha_text_check(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    data = _pending.get((cid, uid))
    if not data or data["type"] != "نص":
        return

    if m.text.strip().upper() == data["answer"].upper():
        data["task"].cancel()
        _pending.pop((cid, uid), None)
        try:
            await m.delete()
            await c.delete_messages(cid, data["msg_id"])
            await c.restrict_chat_member(
                cid, uid,
                permissions=__import__("pyrogram.types", fromlist=["ChatPermissions"]).ChatPermissions(
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True,
                    can_send_polls=True,
                )
            )
            await c.send_message(cid, f"✅ {m.from_user.mention} تم التحقق بنجاح! مرحباً بك.")
        except Exception:
            pass
    else:
        try:
            await m.delete()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
# أوامر الإعداد
# ═══════════════════════════════════════════════════════════════

@Client.on_message(filters.text & filters.group, group=2)
async def captcha_cmd(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    text = resolve_text(m.text.strip(), cid)

    k = botkey()

    # ── تفعيل الكابتشا ──────────────────────────────────────
    if text == "تفعيل الكابتشا":
        if not (is_admin(uid, cid) or is_mod(uid, cid)):
            return
        await ar.set(_cap_on_key(cid), "1")
        await m.reply(f"{k} تم تفعيل الكابتشا ✅\nالأعضاء الجدد سيُطلب منهم التحقق قبل الكتابة.")

    # ── تعطيل الكابتشا ──────────────────────────────────────
    elif text == "تعطيل الكابتشا":
        if not (is_admin(uid, cid) or is_mod(uid, cid)):
            return
        await ar.delete(_cap_on_key(cid))
        await m.reply(f"{k} تم تعطيل الكابتشا ✅")

    # ── نوع الكابتشا ────────────────────────────────────────
    elif text.startswith("نوع الكابتشا"):
        if not (is_admin(uid, cid) or is_mod(uid, cid)):
            return
        parts = text.split(None, 1)
        if len(parts) < 2 or parts[1] not in ("عدد", "نص", "زر"):
            return await m.reply(f"{k} الأنواع المتاحة: **عدد** | **نص** | **زر**")
        await ar.set(_cap_type_key(cid), parts[1])
        await m.reply(f"{k} نوع الكابتشا: **{parts[1]}** ✅")

    # ── مهلة الكابتشا ───────────────────────────────────────
    elif text.startswith("مهلة الكابتشا"):
        if not (is_admin(uid, cid) or is_mod(uid, cid)):
            return
        parts = text.split(None, 1)
        if len(parts) < 2 or not parts[1].isdigit():
            return await m.reply(f"{k} الاستخدام: مهلة الكابتشا [ثواني]")
        secs = max(15, min(int(parts[1]), 300))
        await ar.set(_cap_timeout_key(cid), str(secs))
        await m.reply(f"{k} مهلة الكابتشا: **{secs}** ثانية ✅")

    # ── حالة الكابتشا ───────────────────────────────────────
    elif text == "حالة الكابتشا":
        on      = bool(await ar.get(_cap_on_key(cid)))
        cap_t   = (await ar.get(_cap_type_key(cid))) or "زر"
        timeout = (await ar.get(_cap_timeout_key(cid))) or "60"
        status  = "✅ مفعّل" if on else "❌ معطّل"
        await m.reply(
            f"{k} **حالة الكابتشا**\n\n"
            f"الحالة: {status}\n"
            f"النوع: **{cap_t}**\n"
            f"المهلة: **{timeout}** ثانية"
        )
