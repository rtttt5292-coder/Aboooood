"""
نظام الطرد والحظر المحلي
─────────────────────────────────────────────
الأوامر:
  طرد (رد/@user)          → طرد عضو من المجموعة (مدير+)
  حظر (رد/@user) [سبب]   → حظر عضو من المجموعة (مدير+)
  رفع الحظر (رد/@user)    → رفع الحظر (مدير+)
  المحظورون               → قائمة المحظورين المسجّلين (مدير+)
  حظر مؤقت (رد/@user) [مدة] → حظر مؤقت بوقت (مدير+)
─────────────────────────────────────────────
"""

import re
import asyncio

from pyrogram import Client, filters
from pyrogram.errors import FloodWait, UserAdminInvalid, ChatAdminRequired
from pyrogram.types import Message

from config import r, ar, DEV_ID, botkey, cached_smembers
from helpers.ranks import is_admin, is_mod, is_owner, is_dev, is_pre
from helpers.utils import group_enabled, resolve_text, utils_cache_invalidate


# ── مفاتيح Redis ──
def _ban_key(cid: int) -> str:
    return f"{cid}:banned_users:{DEV_ID}"

def _ban_reason_key(cid: int, uid: int) -> str:
    return f"{cid}:ban_reason:{uid}:{DEV_ID}"


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


def _parse_duration(text: str) -> int | None:
    """يحوّل نص المدة إلى ثواني: '30d' '12h' '60m' '3600s' """
    m = re.fullmatch(r"(\d+)([dhms]?)", text.strip())
    if not m:
        return None
    val, unit = int(m.group(1)), m.group(2) or "m"
    return val * {"d": 86400, "h": 3600, "m": 60, "s": 1}[unit]


# ─────────────────────────────────────────────────────────────────────────
# معالج الأوامر
# ─────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.text & filters.group, group=44)
async def bans_handler(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    text = resolve_text(m.text, cid)
    k = botkey()

    # ── طرد ──
    mt = re.fullmatch(r"طرد(?:\s+(@?\S+))?", text)
    if mt:
        if not (is_mod(uid, cid) or is_admin(uid, cid) or is_owner(uid, cid) or is_dev(uid, cid)):
            return await m.reply(f"{k} ما عندك صلاحية")
        tid, tmention = await _resolve_user(c, m, mt.group(1))
        if not tid:
            return await m.reply(f"{k} ما حددت أحد")
        if is_admin(tid, cid) or is_owner(tid, cid) or is_dev(tid, cid):
            return await m.reply(f"{k} ما أقدر أطرد مدير أو مالك")
        try:
            await c.ban_chat_member(cid, tid)
            await c.unban_chat_member(cid, tid)   # طرد بدون حظر دائم
            await m.reply(f"{k} تم طرد {tmention} ✅")
        except (UserAdminInvalid, ChatAdminRequired):
            await m.reply(f"{k} ما أقدر أطرد هذا الشخص، تحقق من صلاحياتي")
        except Exception as e:
            await m.reply(f"{k} خطأ: {e}")
        return

    # ── حظر ──
    mb = re.fullmatch(r"حظر(?:\s+(@?\S+))?(?:\s+(.+))?", text)
    if mb:
        if not (is_mod(uid, cid) or is_admin(uid, cid) or is_owner(uid, cid) or is_dev(uid, cid)):
            return await m.reply(f"{k} ما عندك صلاحية")
        tid, tmention = await _resolve_user(c, m, mb.group(1))
        reason = mb.group(2) or ""
        if not tid:
            return await m.reply(f"{k} ما حددت أحد")
        if is_admin(tid, cid) or is_owner(tid, cid) or is_dev(tid, cid):
            return await m.reply(f"{k} ما أقدر أحظر مدير أو مالك")
        try:
            await c.ban_chat_member(cid, tid)
            await ar.sadd(_ban_key(cid), str(tid))
            if reason:
                await ar.set(_ban_reason_key(cid, tid), reason)
            msg = f"{k} تم حظر {tmention} ✅"
            if reason:
                msg += f"\n📌 السبب: {reason}"
            await m.reply(msg)
        except (UserAdminInvalid, ChatAdminRequired):
            await m.reply(f"{k} ما أقدر أحظر هذا الشخص، تحقق من صلاحياتي")
        except Exception as e:
            await m.reply(f"{k} خطأ: {e}")
        return

    # ── حظر مؤقت ──
    mbt = re.fullmatch(r"حظر مؤقت(?:\s+(@?\S+))?(?:\s+(\S+))?(?:\s+(.+))?", text)
    if mbt:
        if not (is_mod(uid, cid) or is_admin(uid, cid) or is_owner(uid, cid) or is_dev(uid, cid)):
            return await m.reply(f"{k} ما عندك صلاحية")
        tid, tmention = await _resolve_user(c, m, mbt.group(1))
        dur_str = mbt.group(2)
        reason = mbt.group(3) or ""
        if not tid:
            return await m.reply(f"{k} ما حددت أحد")
        if not dur_str:
            return await m.reply(f"{k} حدد المدة مثال: حظر مؤقت @user 1h\n(d=أيام h=ساعات m=دقائق s=ثواني)")
        secs = _parse_duration(dur_str)
        if not secs:
            return await m.reply(f"{k} صيغة المدة غلط — مثال: 30m / 2h / 1d")
        import time
        try:
            until = int(time.time()) + secs
            await c.ban_chat_member(cid, tid, until_date=until)
            label = dur_str
            msg = f"{k} تم حظر {tmention} مؤقتاً لمدة **{label}** ✅"
            if reason:
                msg += f"\n📌 السبب: {reason}"
            await m.reply(msg)
        except (UserAdminInvalid, ChatAdminRequired):
            await m.reply(f"{k} ما أقدر أحظر هذا الشخص")
        except Exception as e:
            await m.reply(f"{k} خطأ: {e}")
        return

    # ── رفع الحظر ──
    mu = re.fullmatch(r"رفع الحظر(?:\s+(@?\S+))?", text)
    if mu:
        if not (is_mod(uid, cid) or is_admin(uid, cid) or is_owner(uid, cid) or is_dev(uid, cid)):
            return await m.reply(f"{k} ما عندك صلاحية")
        tid, tmention = await _resolve_user(c, m, mu.group(1))
        if not tid:
            return await m.reply(f"{k} ما حددت أحد")
        try:
            await c.unban_chat_member(cid, tid)
            await ar.srem(_ban_key(cid), str(tid))
            await ar.delete(_ban_reason_key(cid, tid))
            await m.reply(f"{k} تم رفع الحظر عن {tmention} ✅")
        except Exception as e:
            await m.reply(f"{k} خطأ: {e}")
        return

    # ── قائمة المحظورين ──
    if re.fullmatch(r"المحظورون|المحظورين|قائمة الحظر", text):
        if not (is_mod(uid, cid) or is_admin(uid, cid) or is_owner(uid, cid) or is_dev(uid, cid)):
            return await m.reply(f"{k} ما عندك صلاحية")
        banned = await ar.smembers(_ban_key(cid))
        if not banned:
            return await m.reply(f"{k} لا يوجد محظورون مسجّلون")
        lines = [f"{k} **المحظورون في المجموعة:**\n"]
        for i, bid in enumerate(banned, 1):
            reason = await ar.get(_ban_reason_key(cid, int(bid))) or "—"
            lines.append(f"{i}. `{bid}` | السبب: {reason}")
        await m.reply("\n".join(lines))
        return
