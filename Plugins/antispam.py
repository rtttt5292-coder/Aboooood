"""
نظام مكافحة السبام المتقدم (Anti-Spam)
──────────────────────────────────────────────────────────
الأوامر:
  تفعيل ضد السبام           → تشغيل الحماية (مدير+)
  تعطيل ضد السبام           → إيقاف الحماية (مدير+)
  حد السبام [عدد]           → عدد الرسائل المتشابهة قبل العقوبة (افتراضي: 3)
  عقوبة السبام [كتم|طرد|حظر] → تحديد العقوبة (مدير+)
  حالة ضد السبام             → عرض الإعدادات الحالية
──────────────────────────────────────────────────────────
يكشف:
  - نفس النص يتكرر أكثر من [حد] مرة خلال 30 ثانية
  - أرقام هاتف مبثوثة في النص
  - روابط دعائية مشبوهة (t.me/+)
──────────────────────────────────────────────────────────
"""

import re
import time
import asyncio
from collections import defaultdict

from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import Message, ChatPermissions

from config import r, ar, DEV_ID, botkey
from helpers.ranks import is_admin, is_mod, is_owner, is_dev, is_pre
from helpers.utils import group_enabled, resolve_text


# ── مفاتيح Redis ──
def _spam_on_key(cid: int) -> str:
    return f"{cid}:antispam_on:{DEV_ID}"

def _spam_limit_key(cid: int) -> str:
    return f"{cid}:antispam_limit:{DEV_ID}"

def _spam_action_key(cid: int) -> str:
    return f"{cid}:antispam_action:{DEV_ID}"


# ── ذاكرة مؤقتة للرسائل: (cid, uid) → [(text_hash, timestamp), ...]
_spam_memory: dict = defaultdict(list)
_WINDOW = 30   # ثانية


def _text_hash(text: str) -> str:
    """بصمة مبسّطة للنص — يزيل المسافات والأرقام ليقارن المحتوى"""
    cleaned = re.sub(r"\s+|\d+", "", text.lower())
    return cleaned[:80]


def _contains_phone(text: str) -> bool:
    """يكشف أرقام هاتف مبثوثة في النص"""
    return bool(re.search(r"(?<!\d)(\+?\d[\d\s\-]{8,14}\d)(?!\d)", text))


def _contains_invite_link(text: str) -> bool:
    """يكشف روابط دعوة تيليجرام"""
    return bool(re.search(r"t\.me/\+\S+|telegram\.me/joinchat/\S+", text))


# ─────────────────────────────────────────────────────────────────────────
# المراقبة التلقائية
# ─────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.text & filters.group, group=11)
async def antispam_watcher(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    if is_admin(uid, cid) or is_mod(uid, cid) or is_owner(uid, cid) or is_dev(uid, cid) or is_pre(uid, cid):
        return

    # هل مفعّل؟
    enabled = await ar.get(_spam_on_key(cid))
    if not enabled:
        return

    text = m.text or ""
    now = time.time()
    key = (cid, uid)

    # نظّف السجل القديم
    _spam_memory[key] = [(h, t) for h, t in _spam_memory[key] if now - t < _WINDOW]

    # أضف الرسالة الحالية
    h = _text_hash(text)
    _spam_memory[key].append((h, now))

    limit = int(await ar.get(_spam_limit_key(cid)) or 3)
    action = await ar.get(_spam_action_key(cid)) or "كتم"
    k = botkey()

    # فحص التكرار
    same_count = sum(1 for oh, _ in _spam_memory[key] if oh == h)
    spam_detected = same_count >= limit

    # فحص أرقام الهاتف
    if not spam_detected and _contains_phone(text):
        spam_detected = True
        action = "كتم"   # أرقام هاتف → كتم تلقائي

    # فحص روابط الدعوة
    if not spam_detected and _contains_invite_link(text):
        spam_detected = True

    if not spam_detected:
        return

    _spam_memory[key] = []   # أعد ضبط السجل

    try:
        await m.delete()
    except Exception:
        pass

    if action == "كتم":
        try:
            await c.restrict_chat_member(cid, uid, ChatPermissions())
            await m.reply(f"{k} تم كتم {m.from_user.mention} بسبب السبام 🔇")
        except Exception:
            pass
    elif action == "طرد":
        try:
            await c.ban_chat_member(cid, uid)
            await c.unban_chat_member(cid, uid)
            await m.reply(f"{k} تم طرد {m.from_user.mention} بسبب السبام 👢")
        except Exception:
            pass
    elif action == "حظر":
        try:
            await c.ban_chat_member(cid, uid)
            await m.reply(f"{k} تم حظر {m.from_user.mention} بسبب السبام 🚫")
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────
# معالج الأوامر
# ─────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.text & filters.group, group=42)
async def antispam_commands(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    text = resolve_text(m.text, cid)
    k = botkey()

    if re.fullmatch(r"تفعيل ضد السبام", text):
        if not (is_admin(uid, cid) or is_mod(uid, cid) or is_owner(uid, cid) or is_dev(uid, cid)):
            return await m.reply(f"{k} ما عندك صلاحية")
        await ar.set(_spam_on_key(cid), "1")
        return await m.reply(f"{k} تم تفعيل الحماية من السبام ✅")

    if re.fullmatch(r"تعطيل ضد السبام", text):
        if not (is_admin(uid, cid) or is_mod(uid, cid) or is_owner(uid, cid) or is_dev(uid, cid)):
            return await m.reply(f"{k} ما عندك صلاحية")
        await ar.delete(_spam_on_key(cid))
        return await m.reply(f"{k} تم تعطيل الحماية من السبام ✅")

    ml = re.fullmatch(r"حد السبام\s+(\d+)", text)
    if ml:
        if not (is_admin(uid, cid) or is_mod(uid, cid) or is_owner(uid, cid) or is_dev(uid, cid)):
            return await m.reply(f"{k} ما عندك صلاحية")
        limit = max(2, min(10, int(ml.group(1))))
        await ar.set(_spam_limit_key(cid), str(limit))
        return await m.reply(f"{k} تم تعيين حد السبام: **{limit}** رسالة متشابهة ✅")

    ma = re.fullmatch(r"عقوبة السبام\s+(كتم|طرد|حظر)", text)
    if ma:
        if not (is_admin(uid, cid) or is_mod(uid, cid) or is_owner(uid, cid) or is_dev(uid, cid)):
            return await m.reply(f"{k} ما عندك صلاحية")
        await ar.set(_spam_action_key(cid), ma.group(1))
        return await m.reply(f"{k} تم تعيين عقوبة السبام: **{ma.group(1)}** ✅")

    if re.fullmatch(r"حالة ضد السبام|إعدادات السبام", text):
        enabled = await ar.get(_spam_on_key(cid))
        limit = await ar.get(_spam_limit_key(cid)) or "3"
        action = await ar.get(_spam_action_key(cid)) or "كتم"
        status = "✅ مفعّل" if enabled else "❌ معطّل"
        return await m.reply(
            f"{k} **إعدادات مكافحة السبام:**\n"
            f"📊 الحالة: {status}\n"
            f"🔢 الحد: {limit} رسائل\n"
            f"⚡ العقوبة: {action}\n\n"
            f"🔍 يكشف: تكرار الرسائل، أرقام الهاتف، روابط الدعوة"
        )
