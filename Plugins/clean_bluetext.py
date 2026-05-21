"""
نظام تنظيف النص الأزرق (Clean Blue Text)
──────────────────────────────────────────────────────
يحذف رسائل تحتوي على:
  - نصوص فيها hyperlinks مخفية (inline URL)
  - منشنات مخفية في النص

الأوامر:
  تفعيل ضد النص الأزرق    → تشغيل الحماية (مدير+)
  تعطيل ضد النص الأزرق   → إيقاف الحماية (مدير+)
  عقوبة النص الأزرق [حذف|كتم|طرد] → تحديد العقوبة (مدير+)
  حالة النص الأزرق         → عرض الإعدادات
──────────────────────────────────────────────────────
"""

import re

from pyrogram import Client, filters
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message, ChatPermissions

from config import r, ar, DEV_ID, botkey
from helpers.ranks import is_admin, is_mod, is_owner, is_dev, is_pre
from helpers.utils import group_enabled, resolve_text


# ── مفاتيح Redis ──
def _bluekey(cid: int) -> str:
    return f"{cid}:cleanblue:{DEV_ID}"

def _blue_action_key(cid: int) -> str:
    return f"{cid}:cleanblue_action:{DEV_ID}"


# ─────────────────────────────────────────────────────────────────────────
# المراقبة
# ─────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.text & filters.group, group=33)
async def clean_bluetext_watcher(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    if is_admin(uid, cid) or is_mod(uid, cid) or is_owner(uid, cid) or is_dev(uid, cid) or is_pre(uid, cid):
        return

    enabled = await ar.get(_bluekey(cid))
    if not enabled:
        return

    # فحص كيانات النص
    bad = False
    if m.entities:
        for ent in m.entities:
            if ent.type in (
                MessageEntityType.TEXT_LINK,
                MessageEntityType.TEXT_MENTION,
            ):
                bad = True
                break

    if not bad:
        return

    action = await ar.get(_blue_action_key(cid)) or "حذف"
    k = botkey()

    try:
        await m.delete()
    except Exception:
        pass

    if action == "كتم":
        try:
            await c.restrict_chat_member(cid, uid, ChatPermissions())
            await m.reply(f"{k} تم كتم {m.from_user.mention} بسبب نص أزرق مخفي 🔇")
        except Exception:
            pass
    elif action == "طرد":
        try:
            await c.ban_chat_member(cid, uid)
            await c.unban_chat_member(cid, uid)
            await m.reply(f"{k} تم طرد {m.from_user.mention} بسبب نص أزرق مخفي 👢")
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────
# معالج الأوامر
# ─────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.text & filters.group, group=57)
async def clean_bluetext_commands(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    text = resolve_text(m.text, cid)
    k = botkey()

    if re.fullmatch(r"تفعيل ضد النص الأزرق", text):
        if not (is_admin(uid, cid) or is_mod(uid, cid) or is_owner(uid, cid) or is_dev(uid, cid)):
            return await m.reply(f"{k} ما عندك صلاحية")
        await ar.set(_bluekey(cid), "1")
        return await m.reply(f"{k} تم تفعيل الحماية من النص الأزرق (Hyperlinks المخفية) ✅")

    if re.fullmatch(r"تعطيل ضد النص الأزرق", text):
        if not (is_admin(uid, cid) or is_mod(uid, cid) or is_owner(uid, cid) or is_dev(uid, cid)):
            return await m.reply(f"{k} ما عندك صلاحية")
        await ar.delete(_bluekey(cid))
        return await m.reply(f"{k} تم تعطيل الحماية من النص الأزرق ✅")

    ma = re.fullmatch(r"عقوبة النص الأزرق\s+(حذف|كتم|طرد)", text)
    if ma:
        if not (is_admin(uid, cid) or is_mod(uid, cid) or is_owner(uid, cid) or is_dev(uid, cid)):
            return await m.reply(f"{k} ما عندك صلاحية")
        await ar.set(_blue_action_key(cid), ma.group(1))
        return await m.reply(f"{k} تم تعيين عقوبة النص الأزرق: **{ma.group(1)}** ✅")

    if re.fullmatch(r"حالة النص الأزرق", text):
        enabled = await ar.get(_bluekey(cid))
        action = await ar.get(_blue_action_key(cid)) or "حذف"
        status = "✅ مفعّل" if enabled else "❌ معطّل"
        return await m.reply(
            f"{k} **الحماية من النص الأزرق:**\n"
            f"📊 الحالة: {status}\n"
            f"⚡ العقوبة: {action}"
        )
