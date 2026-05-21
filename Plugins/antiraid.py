"""
نظام مكافحة الغزو (Anti-Raid)
──────────────────────────────
الأوامر:
  تفعيل ضد الغزو [عدد]      → تفعيل وضع الحماية (افتراضي: 10 أعضاء/30 ثانية)
  تعطيل ضد الغزو             → إيقاف الحماية
  وضع الغزو [حظر|طرد|كتم]   → تحديد العقوبة عند الغزو
  حد الغزو                   → عرض الإعدادات الحالية
──────────────────────────────
عند اكتشاف غزو: يُعطَّل الانضمام مؤقتاً + يُعاقَب الداخلون الجدد
"""

import asyncio
import time
from collections import deque

from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import ChatMemberUpdated

from config import ar, DEV_ID, botkey
from helpers.ranks import is_mod
from helpers.utils import group_enabled, resolve_text
from pyrogram.types import Message

# ── In-memory: (cid) → deque[timestamps] ──
_raid_data: dict[int, deque] = {}
_RAID_WINDOW = 30  # ثانية
_raid_active: set[int] = set()  # مجموعات في وضع الغزو الآن

def _raid_key(cid: int) -> str:
    return f"{cid}:raid_on:{DEV_ID}"

def _raid_limit_key(cid: int) -> str:
    return f"{cid}:raid_limit:{DEV_ID}"

def _raid_mode_key(cid: int) -> str:
    return f"{cid}:raid_mode:{DEV_ID}"


# ─────────────────────────────────────────────────────────────────────────
# مراقب الأعضاء الجدد
# ─────────────────────────────────────────────────────────────────────────

@Client.on_chat_member_updated(filters.group)
async def raid_member_watcher(c: Client, update: ChatMemberUpdated):
    if not update.new_chat_member:
        return
    if update.old_chat_member and update.old_chat_member.status in (
        "member", "administrator", "creator"
    ):
        return  # ليس عضو جديد

    cid = update.chat.id
    if not group_enabled(cid):
        return
    if not await ar.get(_raid_key(cid)):
        return

    now = time.monotonic()
    if cid not in _raid_data:
        _raid_data[cid] = deque()

    q = _raid_data[cid]
    # نظّف الطوابع القديمة
    while q and now - q[0] > _RAID_WINDOW:
        q.popleft()
    q.append(now)

    limit = int(await ar.get(_raid_limit_key(cid)) or 10)
    if len(q) < limit:
        return

    # ── وقع الغزو ──
    if cid in _raid_active:
        return  # بالفعل في وضع الغزو، عاقب الداخل الجديد فقط
    _raid_active.add(cid)
    _raid_data[cid] = deque()

    mode = await ar.get(_raid_mode_key(cid)) or "طرد"
    k = botkey()
    uid = update.new_chat_member.user.id

    try:
        if mode == "حظر":
            await c.ban_chat_member(cid, uid)
            action_text = "🔨 حظر الغازين"
        elif mode == "كتم":
            await c.restrict_chat_member(
                cid, uid,
                permissions={"can_send_messages": False}
            )
            action_text = "🔇 كتم الغازين"
        else:
            await c.ban_chat_member(cid, uid)
            await c.unban_chat_member(cid, uid)
            action_text = "👢 طرد الغازين"
    except Exception:
        action_text = "⚠️ لم أتمكن من تطبيق العقوبة"

    try:
        await c.send_message(
            cid,
            f"╔══ {k} ══╗\n"
            f"┃ 🚨 تم اكتشاف غزو جماعي!\n"
            f"┃ ⚡ {limit} أعضاء خلال {_RAID_WINDOW} ثانية\n"
            f"┃ {action_text}\n"
            f"╚══════════╝"
        )
    except Exception:
        pass

    # بعد 5 دقائق ارفع وضع الغزو تلقائياً
    await asyncio.sleep(300)
    _raid_active.discard(cid)


# ─────────────────────────────────────────────────────────────────────────
# أوامر الإعداد
# ─────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.text & filters.group, group=14)
async def antiraid_commands(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    text = resolve_text(m.text, cid)
    k = botkey()

    # ── تفعيل ضد الغزو ──
    if text.startswith("تفعيل ضد الغزو"):
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        parts = text.split()
        limit = 10
        if len(parts) >= 3:
            try:
                limit = int(parts[2])
                if not (3 <= limit <= 100):
                    return await m.reply(f"‼️ {k} الحد يجب أن يكون بين 3 و 100")
            except ValueError:
                return await m.reply(f"‼️ {k} أدخل رقماً صحيحاً")
        await ar.set(_raid_key(cid), 1)
        await ar.set(_raid_limit_key(cid), limit)
        return await m.reply(
            f"╔══ {k} ══╗\n"
            f"┃ تم تفعيل الحماية من الغزو ✅\n"
            f"┃ الحد: {limit} عضو / {_RAID_WINDOW} ثانية\n"
            f"╚══════════╝"
        )

    # ── تعطيل ضد الغزو ──
    if text in ("تعطيل ضد الغزو", "تعطيل ضد الغزو"):
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        await ar.delete(_raid_key(cid))
        _raid_active.discard(cid)
        return await m.reply(
            f"╔══ {k} ══╗\n┃ تم تعطيل الحماية من الغزو ❌\n╚══════════╝"
        )

    # ── وضع الغزو ──
    if text.startswith("وضع الغزو"):
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        parts = text.split()
        if len(parts) < 3 or parts[2] not in ("حظر", "طرد", "كتم"):
            return await m.reply(
                f"╔══ {k} ══╗\n"
                f"┃ استخدم: وضع الغزو [حظر|طرد|كتم]\n"
                f"╚══════════╝"
            )
        mode = parts[2]
        await ar.set(_raid_mode_key(cid), mode)
        return await m.reply(
            f"╔══ {k} ══╗\n┃ تم ضبط وضع الغزو على: {mode} ✅\n╚══════════╝"
        )

    # ── حد الغزو ──
    if text in ("حد الغزو", "اعدادات الغزو"):
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        enabled = await ar.get(_raid_key(cid))
        limit   = await ar.get(_raid_limit_key(cid)) or "10"
        mode    = await ar.get(_raid_mode_key(cid)) or "طرد"
        status  = "مفعّل ✅" if enabled else "معطّل ❌"
        return await m.reply(
            f"╔══ {k} ══╗\n"
            f"┃ 🛡️ الحماية من الغزو: {status}\n"
            f"┃ 📊 الحد: {limit} عضو / {_RAID_WINDOW} ثانية\n"
            f"┃ ⚖️ العقوبة: {mode}\n"
            f"╚══════════╝"
        )
