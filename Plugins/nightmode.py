"""
الوضع الليلي (Night Mode)
──────────────────────────
الأوامر:
  تفعيل الليل [HH:MM] [HH:MM]   → يُغلق المجموعة من ساعة لساعة يومياً
  تعطيل الليل                    → إيقاف الوضع الليلي
  وضع الليل                      → عرض الإعداد الحالي

كيف يعمل:
  - كل دقيقة يتحقق cron من المجموعات المفعّلة
  - عند وقت الإغلاق: يُقيّد المجموعة (لا أحد يكتب)
  - عند وقت الفتح: يرفع القيود
──────────────────────────
يتحقق apscheduler (أو asyncio) كل 60 ثانية
"""

import asyncio
import re
from datetime import datetime, timezone

from pyrogram import Client, filters
from pyrogram.types import Message, ChatPermissions

from config import ar, DEV_ID, botkey
from helpers.ranks import is_mod
from helpers.utils import group_enabled, resolve_text

# ── مفاتيح Redis ──
def _night_key(cid: int) -> str:
    return f"{cid}:nightmode:{DEV_ID}"

def _night_close_key(cid: int) -> str:
    return f"{cid}:night_close:{DEV_ID}"

def _night_open_key(cid: int) -> str:
    return f"{cid}:night_open:{DEV_ID}"

def _night_list_key() -> str:
    return f"nightlist:{DEV_ID}"

_ALL_PERMS_OFF = ChatPermissions(
    can_send_messages=False,
    can_send_media_messages=False,
    can_send_other_messages=False,
    can_add_web_page_previews=False,
    can_invite_users=False,
    can_pin_messages=False,
    can_change_info=False,
    can_send_polls=False,
)

_ALL_PERMS_ON = ChatPermissions(
    can_send_messages=True,
    can_send_media_messages=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
    can_invite_users=True,
    can_pin_messages=False,
    can_change_info=False,
    can_send_polls=True,
)


# ─────────────────────────────────────────────────────────────────────────
# دالة التحقق اللحظية — تُشغَّل كل دقيقة
# ─────────────────────────────────────────────────────────────────────────

_night_task_started = False

async def _night_checker(c: Client):
    """تُشغَّل كل 60 ثانية وتتحقق من كل المجموعات المفعّلة"""
    while True:
        try:
            now_str = datetime.now().strftime("%H:%M")
            chat_ids = await ar.smembers(_night_list_key())
            for cid_str in chat_ids:
                try:
                    cid = int(cid_str)
                    close_t = await ar.get(_night_close_key(cid))
                    open_t  = await ar.get(_night_open_key(cid))
                    if not close_t or not open_t:
                        continue
                    if now_str == close_t:
                        k = botkey()
                        try:
                            await c.set_chat_permissions(cid, _ALL_PERMS_OFF)
                            await c.send_message(
                                cid,
                                f"╔══ {k} ══╗\n"
                                f"┃ 🌙 تم تفعيل الوضع الليلي\n"
                                f"┃ المجموعة مغلقة حتى {open_t}\n"
                                f"╚══════════╝"
                            )
                        except Exception:
                            pass
                    elif now_str == open_t:
                        k = botkey()
                        try:
                            await c.set_chat_permissions(cid, _ALL_PERMS_ON)
                            await c.send_message(
                                cid,
                                f"╔══ {k} ══╗\n"
                                f"┃ ☀️ صباح الخير!\n"
                                f"┃ المجموعة مفتوحة الآن ✅\n"
                                f"╚══════════╝"
                            )
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception:
            pass
        await asyncio.sleep(60)


# ─────────────────────────────────────────────────────────────────────────
# أوامر الليل
# ─────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.text & filters.group, group=19)
async def nightmode_commands(c: Client, m: Message):
    global _night_task_started
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    text = resolve_text(m.text, cid)
    k = botkey()

    # ── ابدأ المهمة في المرة الأولى ──
    if not _night_task_started:
        _night_task_started = True
        asyncio.create_task(_night_checker(c))

    # ── تفعيل الليل ──
    night_match = re.fullmatch(
        r"تفعيل الليل\s+(\d{1,2}:\d{2})\s+(\d{1,2}:\d{2})", text
    )
    if night_match:
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        close_t = night_match.group(1)
        open_t  = night_match.group(2)
        # تحقق من صحة التوقيت
        try:
            datetime.strptime(close_t, "%H:%M")
            datetime.strptime(open_t, "%H:%M")
        except ValueError:
            return await m.reply(f"‼️ {k} استخدم الصيغة HH:MM مثال: تفعيل الليل 23:00 06:00")
        await ar.set(_night_key(cid), 1)
        await ar.set(_night_close_key(cid), close_t)
        await ar.set(_night_open_key(cid), open_t)
        await ar.sadd(_night_list_key(), cid)
        return await m.reply(
            f"╔══ {k} ══╗\n"
            f"┃ 🌙 تم تفعيل الوضع الليلي ✅\n"
            f"┃ الإغلاق: {close_t}\n"
            f"┃ الفتح: {open_t}\n"
            f"╚══════════╝"
        )

    # ── تعطيل الليل ──
    if text in ("تعطيل الليل", "تعطيل الوضع الليلي"):
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        await ar.delete(_night_key(cid))
        await ar.delete(_night_close_key(cid))
        await ar.delete(_night_open_key(cid))
        await ar.srem(_night_list_key(), cid)
        return await m.reply(
            f"╔══ {k} ══╗\n┃ ☀️ تم تعطيل الوضع الليلي ❌\n╚══════════╝"
        )

    # ── وضع الليل ──
    if text in ("وضع الليل", "الوضع الليلي"):
        enabled = await ar.get(_night_key(cid))
        close_t = await ar.get(_night_close_key(cid)) or "—"
        open_t  = await ar.get(_night_open_key(cid)) or "—"
        status  = "مفعّل ✅" if enabled else "معطّل ❌"
        return await m.reply(
            f"╔══ {k} ══╗\n"
            f"┃ 🌙 الوضع الليلي: {status}\n"
            f"┃ وقت الإغلاق: {close_t}\n"
            f"┃ وقت الفتح:   {open_t}\n"
            f"╚══════════╝"
        )
