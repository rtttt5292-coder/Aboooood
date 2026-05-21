"""
نظام الغياب (AFK)
──────────────────
الأوامر:
  غائب [سبب]     → وضع علامة غياب مع سبب اختياري
  راجع           → إلغاء علامة الغياب يدوياً
──────────────────
عند غياب شخص يُبلَّغ من يذكره أو يردّ عليه
يستخدم Redis لحفظ حالة الغياب
"""

import time
import re

from pyrogram import Client, filters
from pyrogram.types import Message

from config import r, ar, DEV_ID, botkey
from helpers.utils import group_enabled, resolve_text
from helpers.ranks import is_pre


# ── مفاتيح Redis ──
def _afk_key(uid: int) -> str:
    return f"afk:{uid}:{DEV_ID}"

def _afk_reason_key(uid: int) -> str:
    return f"afk:reason:{uid}:{DEV_ID}"

def _afk_time_key(uid: int) -> str:
    return f"afk:time:{uid}:{DEV_ID}"


def _format_duration(seconds: float) -> str:
    """تحويل الثواني إلى نص مقروء"""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} ثانية"
    elif seconds < 3600:
        m, s = divmod(seconds, 60)
        return f"{m} دقيقة و{s} ثانية"
    elif seconds < 86400:
        h, rem = divmod(seconds, 3600)
        m = rem // 60
        return f"{h} ساعة و{m} دقيقة"
    else:
        d, rem = divmod(seconds, 86400)
        h = rem // 3600
        return f"{d} يوم و{h} ساعة"


# ─────────────────────────────────────────────────────────────────────────
# أوامر الغياب
# ─────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.text & filters.group, group=42)
async def afk_commands(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    text = resolve_text(m.text, cid)
    k = botkey()

    # ── غائب [سبب] ──
    afk_m = re.fullmatch(r"غائب(?:\s+(.+))?", text, re.DOTALL)
    if afk_m:
        reason = (afk_m.group(1) or "").strip()[:100]
        await ar.set(_afk_key(uid), 1)
        await ar.set(_afk_time_key(uid), str(time.time()))
        if reason:
            await ar.set(_afk_reason_key(uid), reason)
        else:
            await ar.delete(_afk_reason_key(uid))

        mention = m.from_user.mention
        reason_line = f"┃ السبب: {reason}\n" if reason else ""
        return await m.reply(
            f"╔══ {k} ══╗\n"
            f"┃ {mention} غائب الآن 🌙\n"
            f"{reason_line}"
            f"╚══════════╝"
        )

    # ── راجع (يدوي) ──
    if text == "راجع":
        is_afk = await ar.get(_afk_key(uid))
        if not is_afk:
            return await m.reply(f"‼️ {k} أنت لست في وضع الغياب")
        await ar.delete(_afk_key(uid))
        await ar.delete(_afk_reason_key(uid))
        await ar.delete(_afk_time_key(uid))
        mention = m.from_user.mention
        return await m.reply(
            f"╔══ {k} ══╗\n┃ أهلاً بعودتك {mention} 👋\n╚══════════╝"
        )


# ─────────────────────────────────────────────────────────────────────────
# إلغاء الغياب تلقائياً عند إرسال رسالة
# ─────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.group, group=43)
async def auto_unafk(c: Client, m: Message):
    if not m.from_user:
        return
    uid = m.from_user.id
    cid = m.chat.id
    if not group_enabled(cid):
        return

    # تخطّي الأوامر (لا تُلغي الغياب عند كتابة "غائب" نفسه)
    if m.text and re.fullmatch(r"غائب(?:\s+.+)?", resolve_text(m.text, cid), re.DOTALL):
        return

    is_afk = await ar.get(_afk_key(uid))
    if not is_afk:
        return

    # احسب مدة الغياب
    start_str = await ar.get(_afk_time_key(uid))
    duration = ""
    if start_str:
        elapsed = time.time() - float(start_str)
        duration = f"┃ مدة الغياب: {_format_duration(elapsed)}\n"

    await ar.delete(_afk_key(uid))
    await ar.delete(_afk_reason_key(uid))
    await ar.delete(_afk_time_key(uid))

    k = botkey()
    mention = m.from_user.mention
    try:
        await c.send_message(
            cid,
            f"╔══ {k} ══╗\n"
            f"┃ أهلاً بعودتك {mention} 👋\n"
            f"{duration}"
            f"╚══════════╝"
        )
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────
# إبلاغ المنشن / الردود عن الغياب
# ─────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.group, group=44)
async def afk_notify(c: Client, m: Message):
    if not m.from_user:
        return
    cid = m.chat.id
    if not group_enabled(cid):
        return

    sender_uid = m.from_user.id
    targets_to_check = []

    # فحص الردود
    if m.reply_to_message and m.reply_to_message.from_user:
        ru = m.reply_to_message.from_user
        if ru.id != sender_uid:
            targets_to_check.append((ru.id, ru.mention))

    # فحص المنشنات في النص
    if m.text and m.entities:
        for ent in m.entities:
            try:
                if ent.type.value == "mention":
                    username = m.text[ent.offset + 1: ent.offset + ent.length]
                    try:
                        u = await c.get_users(username)
                        if u.id != sender_uid:
                            targets_to_check.append((u.id, u.mention))
                    except Exception:
                        pass
                elif ent.type.value == "text_mention" and ent.user:
                    u = ent.user
                    if u.id != sender_uid:
                        targets_to_check.append((u.id, u.mention))
            except Exception:
                pass

    if not targets_to_check:
        return

    k = botkey()
    for tuid, tmention in targets_to_check:
        is_afk = await ar.get(_afk_key(tuid))
        if not is_afk:
            continue
        reason = await ar.get(_afk_reason_key(tuid))
        start_str = await ar.get(_afk_time_key(tuid))
        since = ""
        if start_str:
            elapsed = time.time() - float(start_str)
            since = f"┃ منذ: {_format_duration(elapsed)}\n"
        reason_line = f"┃ السبب: {reason}\n" if reason else ""
        try:
            await m.reply(
                f"╔══ {k} ══╗\n"
                f"┃ {tmention} غائب الآن 🌙\n"
                f"{reason_line}"
                f"{since}"
                f"╚══════════╝"
            )
        except Exception:
            pass
        break  # أبلّغ عن أول غائب فقط لتجنب الفيضان
