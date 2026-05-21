"""
نظام القائمة السوداء للملصقات (Blacklist Stickers)
────────────────────────────────────────────────────
الأوامر:
  حظر ملصق (رد على ملصق)       → إضافة ملصق للقائمة السوداء (مدير+)
  رفع حظر ملصق (رد على ملصق)   → إزالة ملصق من القائمة السوداء (مدير+)
  ملصقات محظورة                 → عرض عدد الملصقات المحظورة (مدير+)
  مسح ملصقات محظورة             → حذف كل القائمة السوداء (مالك+)
  عقوبة الملصق [حذف|كتم|طرد|حظر] → تحديد العقوبة (مدير+)
────────────────────────────────────────────────────
"""

import re
import asyncio

from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import Message

from config import r, ar, DEV_ID, botkey
from helpers.ranks import is_admin, is_mod, is_owner, is_dev, is_pre
from helpers.utils import group_enabled, resolve_text


# ── مفاتيح Redis ──
def _blsticker_key(cid: int) -> str:
    return f"{cid}:bl_stickers:{DEV_ID}"

def _blsticker_action_key(cid: int) -> str:
    return f"{cid}:bl_sticker_action:{DEV_ID}"


# ─────────────────────────────────────────────────────────────────────────
# مراقبة الملصقات
# ─────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.sticker & filters.group, group=31)
async def sticker_blacklist_watcher(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    if is_admin(uid, cid) or is_mod(uid, cid) or is_owner(uid, cid) or is_dev(uid, cid) or is_pre(uid, cid):
        return

    sticker_id = m.sticker.file_unique_id
    is_banned = await ar.sismember(_blsticker_key(cid), sticker_id)
    if not is_banned:
        return

    action = await ar.get(_blsticker_action_key(cid)) or "حذف"
    k = botkey()

    try:
        await m.delete()
    except Exception:
        pass

    if action == "كتم":
        try:
            from pyrogram.types import ChatPermissions
            await c.restrict_chat_member(cid, uid, ChatPermissions())
            await m.reply(f"{k} تم كتم {m.from_user.mention} بسبب ملصق محظور 🔇")
        except Exception:
            pass
    elif action == "طرد":
        try:
            await c.ban_chat_member(cid, uid)
            await c.unban_chat_member(cid, uid)
            await m.reply(f"{k} تم طرد {m.from_user.mention} بسبب ملصق محظور 👢")
        except Exception:
            pass
    elif action == "حظر":
        try:
            await c.ban_chat_member(cid, uid)
            await m.reply(f"{k} تم حظر {m.from_user.mention} بسبب ملصق محظور 🚫")
        except Exception:
            pass
    # حذف فقط = الافتراضي، تم الحذف أعلاه


# ─────────────────────────────────────────────────────────────────────────
# معالج الأوامر
# ─────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.group, group=32)
async def sticker_blacklist_commands(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    k = botkey()

    if not m.text:
        return
    text = resolve_text(m.text, cid)

    # ── حظر ملصق ──
    if re.fullmatch(r"حظر ملصق", text):
        if not (is_admin(uid, cid) or is_mod(uid, cid) or is_owner(uid, cid) or is_dev(uid, cid)):
            return await m.reply(f"{k} ما عندك صلاحية")
        if not m.reply_to_message or not m.reply_to_message.sticker:
            return await m.reply(f"{k} ردّ على الملصق الذي تريد حظره")
        sticker_id = m.reply_to_message.sticker.file_unique_id
        sticker_name = m.reply_to_message.sticker.set_name or "بدون مجموعة"
        await ar.sadd(_blsticker_key(cid), sticker_id)
        try:
            await m.reply_to_message.delete()
        except Exception:
            pass
        return await m.reply(f"{k} تم حظر الملصق ✅\n🎭 المجموعة: {sticker_name}")

    # ── رفع حظر ملصق ──
    if re.fullmatch(r"رفع حظر ملصق", text):
        if not (is_admin(uid, cid) or is_mod(uid, cid) or is_owner(uid, cid) or is_dev(uid, cid)):
            return await m.reply(f"{k} ما عندك صلاحية")
        if not m.reply_to_message or not m.reply_to_message.sticker:
            return await m.reply(f"{k} ردّ على الملصق الذي تريد رفع حظره")
        sticker_id = m.reply_to_message.sticker.file_unique_id
        removed = await ar.srem(_blsticker_key(cid), sticker_id)
        if removed:
            return await m.reply(f"{k} تم رفع الحظر عن الملصق ✅")
        else:
            return await m.reply(f"{k} هذا الملصق غير محظور")

    # ── ملصقات محظورة ──
    if re.fullmatch(r"ملصقات محظورة|الملصقات المحظورة", text):
        if not (is_admin(uid, cid) or is_mod(uid, cid) or is_owner(uid, cid) or is_dev(uid, cid)):
            return await m.reply(f"{k} ما عندك صلاحية")
        count = await ar.scard(_blsticker_key(cid))
        action = await ar.get(_blsticker_action_key(cid)) or "حذف"
        return await m.reply(
            f"{k} **الملصقات المحظورة:**\n"
            f"📊 العدد: {count}\n"
            f"⚡ العقوبة: {action}"
        )

    # ── مسح ملصقات محظورة ──
    if re.fullmatch(r"مسح ملصقات محظورة|تصفير الملصقات المحظورة", text):
        if not (is_owner(uid, cid) or is_dev(uid, cid)):
            return await m.reply(f"{k} هذا الأمر للمالك فقط")
        await ar.delete(_blsticker_key(cid))
        return await m.reply(f"{k} تم مسح قائمة الملصقات المحظورة ✅")

    # ── عقوبة الملصق ──
    mp = re.fullmatch(r"عقوبة الملصق\s+(حذف|كتم|طرد|حظر)", text)
    if mp:
        if not (is_admin(uid, cid) or is_mod(uid, cid) or is_owner(uid, cid) or is_dev(uid, cid)):
            return await m.reply(f"{k} ما عندك صلاحية")
        action = mp.group(1)
        await ar.set(_blsticker_action_key(cid), action)
        return await m.reply(f"{k} تم تعيين عقوبة الملصق المحظور: **{action}** ✅")
