"""
نظام مكافحة الفيضان (Anti-Flood)
─────────────────────────────────
الأوامر:
  تفعيل ضد الفيض [عدد]     → تفعيل الحماية من الفيضان (الحد الافتراضي 5 رسائل)
  تعطيل ضد الفيض            → إيقاف الحماية
  وضع الفيض [حظر|طرد|كتم]  → تحديد العقوبة عند الفيضان
  حد الفيض                  → عرض الإعدادات الحالية
─────────────────────────────────
يعمل بـ Pyrogram + Redis، نمط gggggggg
"""

import time
from collections import defaultdict

from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import Message

from config import r, ar, DEV_ID, botkey, cached_smembers
from helpers.ranks import is_admin, is_mod, is_pre
from helpers.utils import group_enabled, resolve_text

# ─────────────────────────────────────────────────────────────────────────
# ذاكرة مؤقتة للرسائل (in-memory) — مفتاح: (cid, uid) → [timestamps]
# ─────────────────────────────────────────────────────────────────────────
_flood_data: dict[tuple, list] = defaultdict(list)
_WINDOW = 5  # ثواني: نافذة الزمن لحساب الفيضان

# ── مفاتيح Redis ──
def _flood_limit_key(cid: int) -> str:
    return f"{cid}:flood_limit:{DEV_ID}"

def _flood_mode_key(cid: int) -> str:
    return f"{cid}:flood_mode:{DEV_ID}"

def _flood_enabled_key(cid: int) -> str:
    return f"{cid}:flood_on:{DEV_ID}"


# ─────────────────────────────────────────────────────────────────────────
# كاشف الفيضان الأساسي
# ─────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.group, group=12)
async def flood_watcher(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id

    if not group_enabled(cid):
        return
    if not await ar.get(_flood_enabled_key(cid)):
        return
    if is_pre(uid, cid):
        return

    now = time.monotonic()
    key = (cid, uid)
    timestamps = _flood_data[key]

    # احتفظ فقط بالرسائل ضمن نافذة الـ _WINDOW ثانية
    _flood_data[key] = [t for t in timestamps if now - t < _WINDOW]
    _flood_data[key].append(now)

    limit = int(await ar.get(_flood_limit_key(cid)) or 5)
    if len(_flood_data[key]) < limit:
        return

    # وقع الفيضان — طبّق العقوبة
    _flood_data[key] = []  # أعد ضبط العداد
    mode = await ar.get(_flood_mode_key(cid)) or "كتم"
    k = botkey()
    mention = m.from_user.mention

    try:
        if mode == "حظر":
            await c.ban_chat_member(cid, uid)
            action = "🔨 تم حظره"
        elif mode == "طرد":
            await c.ban_chat_member(cid, uid)
            await c.unban_chat_member(cid, uid)
            action = "👢 تم طرده"
        else:  # كتم
            await c.restrict_chat_member(
                cid, uid,
                permissions={"can_send_messages": False,
                             "can_send_media_messages": False,
                             "can_send_other_messages": False}
            )
            action = "🔇 تم كتمه"
    except FloodWait as e:
        await m.sleep(e.value)
        return
    except Exception:
        return

    try:
        await c.send_message(
            cid,
            f"╔══ {k} ══╗\n"
            f"┃ {mention} قام بالفيضان!\n"
            f"┃ {action} تلقائياً 🚨\n"
            f"╚══════════╝"
        )
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────
# أوامر الإعداد
# ─────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.text & filters.group, group=13)
async def antiflood_commands(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    text = resolve_text(m.text, cid)
    k = botkey()

    # ── تفعيل ضد الفيض [عدد] ──
    if text.startswith("تفعيل ضد الفيض"):
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        parts = text.split()
        limit = 5
        if len(parts) >= 3:
            try:
                limit = int(parts[2])
                if not (2 <= limit <= 50):
                    return await m.reply(f"‼️ {k} الحد يجب أن يكون بين 2 و 50")
            except ValueError:
                return await m.reply(f"‼️ {k} أدخل رقماً صحيحاً")
        await ar.set(_flood_enabled_key(cid), 1)
        await ar.set(_flood_limit_key(cid), limit)
        return await m.reply(
            f"╔══ {k} ══╗\n"
            f"┃ تم تفعيل الحماية من الفيضان ✅\n"
            f"┃ الحد: {limit} رسائل خلال {_WINDOW} ثواني\n"
            f"╚══════════╝"
        )

    # ── تعطيل ضد الفيض ──
    if text in ("تعطيل ضد الفيض", "تعطيل ضد الفيضان"):
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        await ar.delete(_flood_enabled_key(cid))
        return await m.reply(
            f"╔══ {k} ══╗\n┃ تم تعطيل الحماية من الفيضان ❌\n╚══════════╝"
        )

    # ── وضع الفيض [حظر|طرد|كتم] ──
    if text.startswith("وضع الفيض"):
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        parts = text.split()
        if len(parts) < 3 or parts[2] not in ("حظر", "طرد", "كتم"):
            return await m.reply(
                f"╔══ {k} ══╗\n"
                f"┃ استخدم: وضع الفيض [حظر|طرد|كتم]\n"
                f"╚══════════╝"
            )
        mode = parts[2]
        await ar.set(_flood_mode_key(cid), mode)
        return await m.reply(
            f"╔══ {k} ══╗\n┃ تم ضبط وضع الفيضان على: {mode} ✅\n╚══════════╝"
        )

    # ── حد الفيض ──
    if text in ("حد الفيض", "اعدادات الفيض"):
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        enabled = await ar.get(_flood_enabled_key(cid))
        limit   = await ar.get(_flood_limit_key(cid)) or "5"
        mode    = await ar.get(_flood_mode_key(cid)) or "كتم"
        status  = "مفعّل ✅" if enabled else "معطّل ❌"
        return await m.reply(
            f"╔══ {k} ══╗\n"
            f"┃ 🌊 الحماية من الفيضان: {status}\n"
            f"┃ 📊 الحد: {limit} رسائل / {_WINDOW} ثواني\n"
            f"┃ ⚖️ العقوبة: {mode}\n"
            f"╚══════════╝"
        )
