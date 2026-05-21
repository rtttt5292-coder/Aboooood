"""
نظام الفيدراليات (Federations)
────────────────────────────────────────────────────────────
يتيح للمالك تجميع مجموعات في فيدرالية واحدة وحظر شخص من كلها دفعة واحدة.

الأوامر:
  انشاء فيد [اسم]          → إنشاء فيدرالية جديدة (في الخاص) (مالك أساسي+)
  حذف فيد                  → حذف الفيدرالية (في الخاص)
  ربط فيد [ID]             → ربط المجموعة بفيدرالية (مالك أساسي+)
  فصل فيد                  → فصل المجموعة عن الفيدرالية
  معلومات الفيد             → معلومات الفيدرالية الحالية
  حظر فيد (رد/@user) [سبب] → حظر في كل مجموعات الفيدرالية (مالك أساسي+)
  رفع حظر فيد (رد/@user)   → رفع الحظر من كل المجموعات
  المحظورون فيد            → قائمة المحظورين في الفيدرالية
────────────────────────────────────────────────────────────
"""

import re
import uuid
import asyncio

from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import Message

from config import r, ar, DEV_ID, botkey
from helpers.ranks import is_owner, is_gowner, is_dev
from helpers.utils import group_enabled, resolve_text


# ── مفاتيح Redis ──
def _fed_key(fed_id: str) -> str:
    return f"fed:{fed_id}:{DEV_ID}"

def _fed_chats_key(fed_id: str) -> str:
    return f"fed:{fed_id}:chats:{DEV_ID}"

def _fed_bans_key(fed_id: str) -> str:
    return f"fed:{fed_id}:bans:{DEV_ID}"

def _fed_ban_reason_key(fed_id: str, uid: int) -> str:
    return f"fed:{fed_id}:reason:{uid}:{DEV_ID}"

def _chat_fed_key(cid: int) -> str:
    return f"chat:{cid}:fed:{DEV_ID}"

def _user_fed_key(uid: int) -> str:
    return f"user:{uid}:fed:{DEV_ID}"   # الفيد الذي أنشأه المستخدم


# ── مساعد استخراج المستخدم ──
async def _resolve_user(c: Client, m: Message, target: str):
    if target is None and m.reply_to_message and m.reply_to_message.from_user:
        u = m.reply_to_message.from_user
        return u.id, u.mention
    if target is None:
        return None, None
    try:
        uid = int(target)
    except ValueError:
        uid = target.lstrip("@")
    try:
        u = await c.get_users(uid)
        return u.id, u.mention
    except Exception:
        return None, None


# ─────────────────────────────────────────────────────────────────────────
# التطبيق التلقائي: طرد المحظورين فيد عند دخولهم
# ─────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.group, group=16)
async def fed_ban_enforcer(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    fed_id = await ar.get(_chat_fed_key(cid))
    if not fed_id:
        return
    is_banned = await ar.sismember(_fed_bans_key(fed_id), str(uid))
    if is_banned:
        try:
            await m.chat.ban_member(uid)
        except Exception:
            try:
                await m.delete()
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────
# معالج الأوامر في المجموعة
# ─────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.text & filters.group, group=43)
async def feds_group_handler(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    text = resolve_text(m.text, cid)
    k = botkey()

    # ── ربط فيد ──
    ml = re.fullmatch(r"ربط فيد\s+(\S+)", text)
    if ml:
        if not (is_owner(uid, cid) or is_gowner(uid, cid) or is_dev(uid, cid)):
            return await m.reply(f"{k} هذا الأمر للمالك الأساسي فقط")
        fed_id = ml.group(1).strip()
        exists = await ar.exists(_fed_key(fed_id))
        if not exists:
            return await m.reply(f"{k} لم أجد فيدرالية بهذا الـ ID")
        old = await ar.get(_chat_fed_key(cid))
        if old:
            await ar.srem(_fed_chats_key(old), str(cid))
        await ar.set(_chat_fed_key(cid), fed_id)
        await ar.sadd(_fed_chats_key(fed_id), str(cid))
        fed_name = await ar.hget(_fed_key(fed_id), "name") or fed_id
        return await m.reply(f"{k} تم ربط المجموعة بالفيدرالية **{fed_name}** ✅")

    # ── فصل فيد ──
    if re.fullmatch(r"فصل فيد", text):
        if not (is_owner(uid, cid) or is_gowner(uid, cid) or is_dev(uid, cid)):
            return await m.reply(f"{k} هذا الأمر للمالك الأساسي فقط")
        fed_id = await ar.get(_chat_fed_key(cid))
        if not fed_id:
            return await m.reply(f"{k} المجموعة غير مرتبطة بأي فيدرالية")
        await ar.srem(_fed_chats_key(fed_id), str(cid))
        await ar.delete(_chat_fed_key(cid))
        return await m.reply(f"{k} تم فصل المجموعة عن الفيدرالية ✅")

    # ── معلومات الفيد ──
    if re.fullmatch(r"معلومات الفيد|الفيد", text):
        fed_id = await ar.get(_chat_fed_key(cid))
        if not fed_id:
            return await m.reply(f"{k} المجموعة غير مرتبطة بأي فيدرالية")
        fed_name = await ar.hget(_fed_key(fed_id), "name") or "—"
        chats_count = await ar.scard(_fed_chats_key(fed_id))
        bans_count = await ar.scard(_fed_bans_key(fed_id))
        return await m.reply(
            f"{k} **معلومات الفيدرالية:**\n"
            f"📛 الاسم: {fed_name}\n"
            f"🔑 ID: `{fed_id}`\n"
            f"👥 المجموعات: {chats_count}\n"
            f"🚫 المحظورون: {bans_count}"
        )

    # ── حظر فيد ──
    mfb = re.fullmatch(r"حظر فيد(?:\s+(@?\S+))?(?:\s+(.+))?", text)
    if mfb:
        if not (is_owner(uid, cid) or is_gowner(uid, cid) or is_dev(uid, cid)):
            return await m.reply(f"{k} هذا الأمر للمالك الأساسي فقط")
        fed_id = await ar.get(_chat_fed_key(cid))
        if not fed_id:
            return await m.reply(f"{k} المجموعة غير مرتبطة بأي فيدرالية")
        tid, tmention = await _resolve_user(c, m, mfb.group(1))
        if not tid:
            return await m.reply(f"{k} ما حددت أحد")
        reason = mfb.group(2) or ""
        await ar.sadd(_fed_bans_key(fed_id), str(tid))
        if reason:
            await ar.set(_fed_ban_reason_key(fed_id, tid), reason)
        chats = await ar.smembers(_fed_chats_key(fed_id))
        banned_in = 0
        for chat_id in chats:
            try:
                await c.ban_chat_member(int(chat_id), tid)
                banned_in += 1
                await asyncio.sleep(0.3)
            except Exception:
                pass
        msg = f"{k} تم حظر {tmention} في الفيدرالية ✅\n📊 تم التطبيق في {banned_in} مجموعة"
        if reason:
            msg += f"\n📌 السبب: {reason}"
        return await m.reply(msg)

    # ── رفع حظر فيد ──
    mfu = re.fullmatch(r"رفع حظر فيد(?:\s+(@?\S+))?", text)
    if mfu:
        if not (is_owner(uid, cid) or is_gowner(uid, cid) or is_dev(uid, cid)):
            return await m.reply(f"{k} هذا الأمر للمالك الأساسي فقط")
        fed_id = await ar.get(_chat_fed_key(cid))
        if not fed_id:
            return await m.reply(f"{k} المجموعة غير مرتبطة بأي فيدرالية")
        tid, tmention = await _resolve_user(c, m, mfu.group(1))
        if not tid:
            return await m.reply(f"{k} ما حددت أحد")
        await ar.srem(_fed_bans_key(fed_id), str(tid))
        await ar.delete(_fed_ban_reason_key(fed_id, tid))
        chats = await ar.smembers(_fed_chats_key(fed_id))
        unbanned_in = 0
        for chat_id in chats:
            try:
                await c.unban_chat_member(int(chat_id), tid)
                unbanned_in += 1
                await asyncio.sleep(0.3)
            except Exception:
                pass
        return await m.reply(
            f"{k} تم رفع حظر {tmention} من الفيدرالية ✅\n📊 تم التطبيق في {unbanned_in} مجموعة"
        )

    # ── قائمة المحظورين فيد ──
    if re.fullmatch(r"المحظورون فيد|محظورو الفيد", text):
        fed_id = await ar.get(_chat_fed_key(cid))
        if not fed_id:
            return await m.reply(f"{k} المجموعة غير مرتبطة بأي فيدرالية")
        banned = await ar.smembers(_fed_bans_key(fed_id))
        if not banned:
            return await m.reply(f"{k} لا يوجد محظورون في الفيدرالية")
        lines = [f"{k} **محظورو الفيدرالية:**\n"]
        for i, bid in enumerate(list(banned)[:50], 1):
            reason = await ar.get(_fed_ban_reason_key(fed_id, int(bid))) or "—"
            lines.append(f"{i}. `{bid}` | {reason}")
        if len(banned) > 50:
            lines.append(f"\n... و {len(banned)-50} آخرين")
        return await m.reply("\n".join(lines))


# ─────────────────────────────────────────────────────────────────────────
# معالج الأوامر في الخاص (إنشاء/حذف الفيد)
# ─────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.text & filters.private, group=43)
async def feds_private_handler(c: Client, m: Message):
    if not m.from_user:
        return
    uid = m.from_user.id
    text = m.text.strip()
    k = botkey()

    # ── انشاء فيد ──
    mc = re.fullmatch(r"انشاء فيد\s+(.+)", text)
    if mc:
        fed_name = mc.group(1).strip()
        existing = await ar.get(_user_fed_key(uid))
        if existing:
            return await m.reply(
                f"{k} عندك فيدرالية بالفعل: **{await ar.hget(_fed_key(existing), 'name') or existing}**\n"
                f"ID: `{existing}`\nاحذفها أولاً بـ: حذف فيد"
            )
        fed_id = str(uuid.uuid4())[:8].upper()
        await ar.hset(_fed_key(fed_id), mapping={"name": fed_name, "owner": str(uid)})
        await ar.set(_user_fed_key(uid), fed_id)
        return await m.reply(
            f"{k} تم إنشاء الفيدرالية ✅\n"
            f"📛 الاسم: **{fed_name}**\n"
            f"🔑 ID: `{fed_id}`\n\n"
            f"لربط مجموعة: `ربط فيد {fed_id}`"
        )

    # ── حذف فيد ──
    if re.fullmatch(r"حذف فيد", text):
        fed_id = await ar.get(_user_fed_key(uid))
        if not fed_id:
            return await m.reply(f"{k} ما عندك فيدرالية")
        fed_name = await ar.hget(_fed_key(fed_id), "name") or fed_id
        # فك ربط كل المجموعات
        chats = await ar.smembers(_fed_chats_key(fed_id))
        for chat_id in chats:
            await ar.delete(_chat_fed_key(int(chat_id)))
        # حذف كل بيانات الفيد
        await ar.delete(_fed_key(fed_id))
        await ar.delete(_fed_chats_key(fed_id))
        await ar.delete(_fed_bans_key(fed_id))
        await ar.delete(_user_fed_key(uid))
        return await m.reply(f"{k} تم حذف الفيدرالية **{fed_name}** ✅")

    # ── معلومات فيد ──
    if re.fullmatch(r"معلومات الفيد|الفيد", text):
        fed_id = await ar.get(_user_fed_key(uid))
        if not fed_id:
            return await m.reply(f"{k} ما عندك فيدرالية. أنشئ واحدة: `انشاء فيد اسم الفيد`")
        fed_name = await ar.hget(_fed_key(fed_id), "name") or "—"
        chats_count = await ar.scard(_fed_chats_key(fed_id))
        bans_count = await ar.scard(_fed_bans_key(fed_id))
        return await m.reply(
            f"{k} **فيدراليتك:**\n"
            f"📛 الاسم: {fed_name}\n"
            f"🔑 ID: `{fed_id}`\n"
            f"👥 المجموعات: {chats_count}\n"
            f"🚫 المحظورون: {bans_count}"
        )
