"""
نظام البلاغات (Reports)
────────────────────────
الأوامر:
  بلاغ [سبب]      → إرسال بلاغ للإداريين (رد على رسالة)
  تفعيل البلاغات  → تشغيل نظام البلاغات (مدير+)
  تعطيل البلاغات  → إيقاف نظام البلاغات (مدير+)
────────────────────────
يُرسَل البلاغ لجميع المديرين والمالكين النشطين في المجموعة
"""

import re

from pyrogram import Client, filters
from pyrogram.types import Message

from config import r, ar, DEV_ID, botkey, cached_smembers
from helpers.ranks import is_mod, is_pre, is_admin
from helpers.utils import group_enabled, resolve_text


# ── مفاتيح Redis ──
def _reports_key(cid: int) -> str:
    return f"{cid}:reports_on:{DEV_ID}"

def _admins_key(cid: int) -> str:
    return f"{cid}:admins:{DEV_ID}"


# ─────────────────────────────────────────────────────────────────────────
# أوامر البلاغات
# ─────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.text & filters.group, group=45)
async def reports_commands(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    text = resolve_text(m.text, cid)
    k = botkey()

    # ── تفعيل / تعطيل البلاغات ──
    if text == "تفعيل البلاغات":
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        await ar.set(_reports_key(cid), 1)
        return await m.reply(
            f"╔══ {k} ══╗\n┃ تم تفعيل نظام البلاغات 📢 ✅\n╚══════════╝"
        )

    if text == "تعطيل البلاغات":
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        await ar.delete(_reports_key(cid))
        return await m.reply(
            f"╔══ {k} ══╗\n┃ تم تعطيل نظام البلاغات ❌\n╚══════════╝"
        )

    # ── بلاغ [سبب] ──
    report_m = re.fullmatch(r"بلاغ(?:\s+(.+))?", text, re.DOTALL)
    if report_m:
        # التحقق من التفعيل
        enabled = await ar.get(_reports_key(cid))
        if not enabled:
            return await m.reply(
                f"‼️ {k} نظام البلاغات معطّل\n"
                f"اطلب من المدير تفعيله بـ: تفعيل البلاغات"
            )

        if is_pre(uid, cid):
            return await m.reply(f"‼️ {k} المميزون والإداريون لا يمكنهم إرسال بلاغ")

        if not m.reply_to_message:
            return await m.reply(
                f"╔══ {k} ══╗\n"
                f"┃ رُدّ على الرسالة التي تريد الإبلاغ عنها\n"
                f"┃ ثم أكتب: بلاغ [سبب]\n"
                f"╚══════════╝"
            )

        reason = (report_m.group(1) or "").strip()[:200]
        reported = m.reply_to_message.from_user
        if not reported:
            return await m.reply(f"‼️ {k} لا يمكن الإبلاغ عن قناة")

        if reported.id == uid:
            return await m.reply(f"‼️ {k} لا يمكنك الإبلاغ عن نفسك 😅")

        if is_pre(reported.id, cid):
            return await m.reply(f"‼️ {k} لا يمكن الإبلاغ عن مدير أو مميز")

        # بناء رسالة البلاغ
        reporter_mention = m.from_user.mention
        reported_mention = reported.mention
        reason_line = f"\n┃ السبب: {reason}" if reason else ""
        msg_link = ""
        try:
            if m.chat.username:
                msg_link = f"\n┃ الرابط: https://t.me/{m.chat.username}/{m.reply_to_message.id}"
        except Exception:
            pass

        report_text = (
            f"╔══ {k} ══╗\n"
            f"┃ 🚨 بلاغ جديد!\n"
            f"┃ المُبلِّغ: {reporter_mention}\n"
            f"┃ المُبلَّغ عنه: {reported_mention}\n"
            f"{reason_line}"
            f"{msg_link}\n"
            f"╚══════════╝"
        )

        # جمع الإداريين وإرسال البلاغ لهم
        admins = cached_smembers(_admins_key(cid))
        notified = 0
        for admin_id in admins:
            try:
                await c.send_message(int(admin_id), report_text)
                notified += 1
            except Exception:
                pass

        # إشعار في المجموعة
        try:
            chat_admins = await c.get_chat_members(cid, filter="administrators")
            admin_mentions = []
            for admin in chat_admins:
                if admin.user and not admin.user.is_bot:
                    admin_mentions.append(admin.user.mention)
                    if len(admin_mentions) >= 5:
                        break
        except Exception:
            admin_mentions = []

        group_text = (
            f"╔══ {k} ══╗\n"
            f"┃ 🚨 تم إرسال بلاغ ضد {reported_mention}\n"
            + (f"┃ السبب: {reason}\n" if reason else "")
            + (f"┃ {' '.join(admin_mentions)}\n" if admin_mentions else "")
            + f"╚══════════╝"
        )

        try:
            await m.reply(group_text)
        except Exception:
            pass

        return
