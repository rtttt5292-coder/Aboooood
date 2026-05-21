"""
مكافحة رسائل القنوات (Anti-Channel)
──────────────────────────────────────
الأوامر:
  تفعيل ضد القنوات      → منع رسائل القنوات وطردها تلقائياً
  تعطيل ضد القنوات      → إيقاف الحماية
  وضع القنوات            → عرض الحالة الحالية
──────────────────────────────────────
ملاحظة: هذا مختلف عن "قفل/فتح القنوات" في guards_locks.py
هنا يتم حظر القناة نفسها (ليس المستخدم) عند الإرسال بصفة قناة
"""

from pyrogram import Client, filters
from pyrogram.types import Message

from config import ar, DEV_ID, botkey
from helpers.ranks import is_mod
from helpers.utils import group_enabled, resolve_text

# ── مفاتيح Redis ──
def _antichannel_key(cid: int) -> str:
    return f"{cid}:antichannel:{DEV_ID}"


# ─────────────────────────────────────────────────────────────────────────
# مراقب رسائل القنوات
# ─────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.group, group=25)
async def antichannel_watcher(c: Client, m: Message):
    # رسالة من قناة (sender_chat)
    if not m.sender_chat:
        return
    cid = m.chat.id
    if not group_enabled(cid):
        return
    if not await ar.get(_antichannel_key(cid)):
        return

    # احذف الرسالة وحظر القناة
    try:
        await m.delete()
    except Exception:
        pass
    try:
        await c.ban_chat_sender_chat(cid, m.sender_chat.id)
    except Exception:
        pass

    k = botkey()
    try:
        await c.send_message(
            cid,
            f"╔══ {k} ══╗\n"
            f"┃ 🚫 تم حذف رسالة القناة\n"
            f"┃ القناة: {m.sender_chat.title}\n"
            f"┃ وتم حظرها من المجموعة\n"
            f"╚══════════╝"
        )
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────
# أوامر الإعداد
# ─────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.text & filters.group, group=26)
async def antichannel_commands(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    text = resolve_text(m.text, cid)
    k = botkey()

    if text in ("تفعيل ضد القنوات", "تفعيل ضد رسائل القنوات"):
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        await ar.set(_antichannel_key(cid), 1)
        return await m.reply(
            f"╔══ {k} ══╗\n┃ ✅ تم تفعيل الحماية من رسائل القنوات\n╚══════════╝"
        )

    if text in ("تعطيل ضد القنوات", "تعطيل ضد رسائل القنوات"):
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        await ar.delete(_antichannel_key(cid))
        return await m.reply(
            f"╔══ {k} ══╗\n┃ ❌ تم تعطيل الحماية من رسائل القنوات\n╚══════════╝"
        )

    if text in ("وضع القنوات", "اعدادات ضد القنوات"):
        enabled = await ar.get(_antichannel_key(cid))
        status  = "مفعّل ✅" if enabled else "معطّل ❌"
        return await m.reply(
            f"╔══ {k} ══╗\n┃ 📢 ضد رسائل القنوات: {status}\n╚══════════╝"
        )
