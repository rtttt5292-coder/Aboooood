"""
نظام التحذيرات الذكي المتدرج (Smart Warn)
─────────────────────────────────────────────────────────────
مميزات إضافية على warns.py الحالي:
  - عقوبات متدرجة: تحذير → كتم مؤقت → طرد → حظر
  - ذاكرة التحذيرات تُحفظ في Redis
  - أسباب التحذير تُسجَّل
  - سجل التحذيرات لكل مستخدم

الأوامر:
  تحذير (رد) [سبب]       → إعطاء تحذير (مدير+)
  تحذير @user [سبب]      → تحذير بالذكر (مدير+)
  إلغاء تحذير (رد)       → إزالة آخر تحذير (مدير+)
  مسح التحذيرات (رد)     → مسح كل تحذيرات مستخدم (مدير+)
  تحذيرات (رد)/@user     → عرض تحذيرات مستخدم
  حد التحذيرات [عدد]     → ضبط الحد الأقصى (مدير+)
  إعدادات التحذيرات      → عرض الإعدادات
─────────────────────────────────────────────────────────────
"""

import asyncio
import json
import time

from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import Message, ChatPermissions

from config import r, ar, DEV_ID, botkey
from helpers.ranks import is_admin, is_mod, is_owner, is_dev
from helpers.utils import group_enabled, resolve_text


# ── مفاتيح Redis ──────────────────────────────────────────────
def _warns_key(cid: int, uid: int) -> str:
    return f"{cid}:smartwarn:{uid}:{DEV_ID}"

def _limit_key(cid: int) -> str:
    return f"{cid}:swarn_limit:{DEV_ID}"


async def _get_warns(cid: int, uid: int) -> list:
    raw = await ar.get(_warns_key(cid, uid))
    if not raw:
        return []
    try:
        return json.loads(raw)
    except Exception:
        return []


async def _save_warns(cid: int, uid: int, warns: list):
    await ar.set(_warns_key(cid, uid), json.dumps(warns, ensure_ascii=False))


async def _get_limit(cid: int) -> int:
    val = await ar.get(_limit_key(cid))
    return int(val) if val else 3


async def _resolve_target(c: Client, m: Message):
    """يحل المستخدم المستهدف من الرد أو الذكر"""
    if m.reply_to_message and m.reply_to_message.from_user:
        u = m.reply_to_message.from_user
        return u.id, u.mention, ""
    # بحث عن @mention أو ID في النص
    parts = m.text.strip().split()
    reason_start = 2
    if len(parts) >= 2:
        target_str = parts[1]
        if target_str.startswith("@") or target_str.lstrip("-").isdigit():
            try:
                uid_or_uname = int(target_str) if target_str.lstrip("-").isdigit() else target_str.lstrip("@")
                u = await c.get_users(uid_or_uname)
                reason = " ".join(parts[reason_start:])
                return u.id, u.mention, reason
            except Exception:
                pass
    return None, None, ""


# ═══════════════════════════════════════════════════════════════
# تطبيق العقوبة بحسب عدد التحذيرات
# ═══════════════════════════════════════════════════════════════

async def _apply_penalty(c: Client, cid: int, uid: int, warn_count: int, limit: int):
    """عقوبات متدرجة بحسب نسبة التحذيرات من الحد"""
    k = botkey()
    ratio = warn_count / limit
    try:
        if ratio < 0.5:
            pass  # تحذير فقط
        elif ratio < 1.0:
            # كتم مؤقت 10 دقائق
            await c.restrict_chat_member(
                cid, uid, ChatPermissions(can_send_messages=False),
                until_date=int(time.time()) + 600
            )
            await c.send_message(cid, f"{k} ⚠️ تم كتمه 10 دقائق ({warn_count}/{limit} تحذيرات)")
        else:
            # وصل الحد — طرد
            await c.ban_chat_member(cid, uid)
            await asyncio.sleep(1)
            await c.unban_chat_member(cid, uid)
            await c.send_message(cid, f"{k} 🚫 طُرد بسبب تجاوز حد التحذيرات ({warn_count}/{limit})")
            # مسح التحذيرات بعد الطرد
            await ar.delete(_warns_key(cid, uid))
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
# معالج الأوامر
# ═══════════════════════════════════════════════════════════════

@Client.on_message(filters.text & filters.group, group=2)
async def smartwarn_cmd(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    text = resolve_text(m.text.strip(), cid)
    k = botkey()

    # ── تحذير ───────────────────────────────────────────────
    if text.startswith("تحذير") and not text.startswith("تحذيرات"):
        if not (is_admin(uid, cid) or is_mod(uid, cid)):
            return

        target_id, target_mention, reason = await _resolve_target(c, m)
        # استخراج السبب من النص إذا لم يكن هناك رد
        if not target_id and m.reply_to_message and m.reply_to_message.from_user:
            target_id = m.reply_to_message.from_user.id
            target_mention = m.reply_to_message.from_user.mention
            parts = text.split(None, 1)
            reason = parts[1].strip() if len(parts) > 1 else ""

        if not target_id:
            return await m.reply(f"{k} ردّ على رسالة أو اذكر @المستخدم")
        if is_admin(target_id, cid) or is_mod(target_id, cid):
            return await m.reply(f"{k} لا يمكن تحذير المدراء.")
        if is_dev(target_id):
            return await m.reply(f"{k} لا يمكن تحذير المطور.")

        warns = await _get_warns(cid, target_id)
        limit = await _get_limit(cid)

        # أضف التحذير
        entry = {"by": uid, "reason": reason or "—", "at": int(time.time())}
        warns.append(entry)
        await _save_warns(cid, target_id, warns)

        warn_count = len(warns)
        reason_txt = f"\n📝 السبب: {reason}" if reason else ""
        await m.reply(
            f"{k} ⚠️ تحذير لـ {target_mention}\n"
            f"العدد: **{warn_count}/{limit}**{reason_txt}"
        )

        await _apply_penalty(c, cid, target_id, warn_count, limit)

    # ── إلغاء تحذير ─────────────────────────────────────────
    elif text in ("إلغاء تحذير", "الغاء تحذير"):
        if not (is_admin(uid, cid) or is_mod(uid, cid)):
            return
        if not m.reply_to_message or not m.reply_to_message.from_user:
            return await m.reply(f"{k} ردّ على رسالة المستخدم.")
        target_id = m.reply_to_message.from_user.id
        warns = await _get_warns(cid, target_id)
        if not warns:
            return await m.reply(f"{k} لا توجد تحذيرات.")
        warns.pop()
        await _save_warns(cid, target_id, warns)
        limit = await _get_limit(cid)
        await m.reply(f"{k} ✅ تم إلغاء آخر تحذير. العدد: **{len(warns)}/{limit}**")

    # ── مسح التحذيرات ───────────────────────────────────────
    elif text in ("مسح التحذيرات", "مسح تحذيرات"):
        if not (is_admin(uid, cid) or is_mod(uid, cid)):
            return
        if not m.reply_to_message or not m.reply_to_message.from_user:
            return await m.reply(f"{k} ردّ على رسالة المستخدم.")
        target_id = m.reply_to_message.from_user.id
        await ar.delete(_warns_key(cid, target_id))
        await m.reply(f"{k} ✅ تم مسح جميع تحذيرات {m.reply_to_message.from_user.mention}")

    # ── تحذيرات ─────────────────────────────────────────────
    elif text.startswith("تحذيرات"):
        target_id, target_mention = None, None
        if m.reply_to_message and m.reply_to_message.from_user:
            target_id = m.reply_to_message.from_user.id
            target_mention = m.reply_to_message.from_user.mention
        else:
            parts = text.split(None, 1)
            if len(parts) > 1:
                ts = parts[1].strip()
                if ts.startswith("@") or ts.lstrip("-").isdigit():
                    try:
                        uid_or = int(ts) if ts.lstrip("-").isdigit() else ts.lstrip("@")
                        u = await c.get_users(uid_or)
                        target_id, target_mention = u.id, u.mention
                    except Exception:
                        pass
            if not target_id:
                target_id, target_mention = uid, m.from_user.mention

        warns = await _get_warns(cid, target_id)
        limit = await _get_limit(cid)
        if not warns:
            return await m.reply(f"{k} {target_mention} ليس لديه تحذيرات ✅")

        lines = []
        for i, w in enumerate(warns, 1):
            ts = time.strftime("%Y-%m-%d", time.localtime(w.get("at", 0)))
            lines.append(f"{i}. {w.get('reason','—')} ({ts})")

        await m.reply(
            f"{k} **تحذيرات {target_mention}**\n"
            f"العدد: **{len(warns)}/{limit}**\n\n"
            + "\n".join(lines)
        )

    # ── حد التحذيرات ────────────────────────────────────────
    elif text.startswith("حد التحذيرات"):
        if not (is_admin(uid, cid) or is_mod(uid, cid)):
            return
        parts = text.split(None, 1)
        if len(parts) < 2 or not parts[1].isdigit():
            return await m.reply(f"{k} الاستخدام: `حد التحذيرات [عدد]`")
        limit = max(1, min(int(parts[1]), 10))
        await ar.set(_limit_key(cid), str(limit))
        await m.reply(f"{k} حد التحذيرات: **{limit}** ✅")

    # ── إعدادات التحذيرات ───────────────────────────────────
    elif text == "إعدادات التحذيرات":
        limit = await _get_limit(cid)
        await m.reply(
            f"{k} **إعدادات التحذيرات الذكية**\n\n"
            f"الحد الأقصى: **{limit}** تحذيرات\n\n"
            f"العقوبات:\n"
            f"• < 50% من الحد → تحذير نصي فقط\n"
            f"• 50-99% من الحد → كتم 10 دقائق\n"
            f"• 100% من الحد → طرد من المجموعة"
        )
