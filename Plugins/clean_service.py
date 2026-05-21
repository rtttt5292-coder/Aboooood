"""
نظام تنظيف رسائل الخدمة (Clean Service)
──────────────────────────────────────────────────────
يحذف رسائل الخدمة التلقائية مثل:
  - "انضم إلى المجموعة"
  - "غادر المجموعة"
  - "ثبّت رسالة"
  - "تغيير اسم المجموعة/صورتها"

الأوامر:
  تفعيل تنظيف الخدمة      → تشغيل حذف رسائل الخدمة (مدير+)
  تعطيل تنظيف الخدمة     → إيقاف الحذف (مدير+)
  حالة تنظيف الخدمة       → عرض الحالة الحالية
──────────────────────────────────────────────────────
"""

import re

from pyrogram import Client, filters
from pyrogram.enums import MessageServiceType
from pyrogram.types import Message

from config import r, ar, DEV_ID, botkey
from helpers.ranks import is_admin, is_mod, is_owner, is_dev
from helpers.utils import group_enabled, resolve_text


# ── مفاتيح Redis ──
def _clean_service_key(cid: int) -> str:
    return f"{cid}:clean_service:{DEV_ID}"


# ─────────────────────────────────────────────────────────────────────────
# مراقبة رسائل الخدمة
# ─────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.service & filters.group, group=55)
async def clean_service_watcher(c: Client, m: Message):
    cid = m.chat.id
    if not group_enabled(cid):
        return
    enabled = await ar.get(_clean_service_key(cid))
    if not enabled:
        return

    # الأنواع التي نحذفها
    CLEANABLE = {
        MessageServiceType.NEW_CHAT_MEMBERS,
        MessageServiceType.LEFT_CHAT_MEMBERS,
        MessageServiceType.PINNED_MESSAGE,
        MessageServiceType.NEW_CHAT_TITLE,
        MessageServiceType.NEW_CHAT_PHOTO,
        MessageServiceType.DELETE_CHAT_PHOTO,
        MessageServiceType.GROUP_CHAT_CREATED,
        MessageServiceType.MIGRATE_TO_SUPERGROUP,
        MessageServiceType.MIGRATE_FROM_GROUP,
    }

    if m.service in CLEANABLE:
        try:
            await m.delete()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────
# معالج الأوامر
# ─────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.text & filters.group, group=56)
async def clean_service_commands(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    text = resolve_text(m.text, cid)
    k = botkey()

    if re.fullmatch(r"تفعيل تنظيف الخدمة", text):
        if not (is_admin(uid, cid) or is_mod(uid, cid) or is_owner(uid, cid) or is_dev(uid, cid)):
            return await m.reply(f"{k} ما عندك صلاحية")
        await ar.set(_clean_service_key(cid), "1")
        return await m.reply(
            f"{k} تم تفعيل تنظيف رسائل الخدمة ✅\n"
            f"سيتم حذف رسائل: الدخول، الخروج، التثبيت، تغيير الاسم/الصورة"
        )

    if re.fullmatch(r"تعطيل تنظيف الخدمة", text):
        if not (is_admin(uid, cid) or is_mod(uid, cid) or is_owner(uid, cid) or is_dev(uid, cid)):
            return await m.reply(f"{k} ما عندك صلاحية")
        await ar.delete(_clean_service_key(cid))
        return await m.reply(f"{k} تم تعطيل تنظيف رسائل الخدمة ✅")

    if re.fullmatch(r"حالة تنظيف الخدمة", text):
        enabled = await ar.get(_clean_service_key(cid))
        status = "✅ مفعّل" if enabled else "❌ معطّل"
        return await m.reply(f"{k} تنظيف رسائل الخدمة: {status}")
