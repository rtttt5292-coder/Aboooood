"""
إدارة الكتم والحظر
أوامر:
  كتم (رد) / كتم @user
  كتم [مدة] (رد) / كتم [مدة] @user       ← جديد: 30m / 2h / 1d
  الغاء الكتم (رد) / الغاء الكتم @user
  كتم عام (رد) / كتم عام @user
  الغاء الكتم العام (رد)
  حظر عام (رد) / حظر عام @user
  حظر عام من الالعاب (رد) / حظر عام من الالعاب @user
  الغاء الحظر العام (رد) / الغاء الحظر العام @user
  الغاء الحظر العام من الالعاب (رد) / الغاء الحظر العام من الالعاب @user
  مسح المكتومين / مسح المكتومين عام / مسح المحظورين عام
"""
import asyncio
import re
import time as _time
from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import Message

from config import r, DEV_ID, botkey, ar
from helpers.ranks import (
    get_rank, is_admin, is_mod, is_dev, is_pre,
)
from helpers.utils import group_enabled, resolve_text, can_speak, is_gbanned, utils_cache_invalidate
from helpers.error_logger import log_error
from config import cache_invalidate_prefix


# ─────────────────────── مساعد تحليل المدة الزمنية ───────────────────────

def _parse_duration(text: str):
    """
    يحوّل نصاً مثل '30m' أو '2h' أو '1d' إلى عدد الثواني.
    يُعيد None إذا لم يُطابق أي صيغة.
    صيغ مقبولة:
        m  → دقائق
        h  → ساعات
        d  → أيام
    """
    m = re.fullmatch(r"(\d+)([mhd])", text.strip().lower())
    if not m:
        return None
    val, unit = int(m.group(1)), m.group(2)
    if val <= 0:
        return None
    return {"m": 60, "h": 3600, "d": 86400}[unit] * val


def _duration_label(seconds: int) -> str:
    """يحوّل الثواني إلى نص عربي مقروء: '30 دقيقة' / '2 ساعة' / '1 يوم'"""
    if seconds < 3600:
        return f"{seconds // 60} دقيقة"
    if seconds < 86400:
        return f"{seconds // 3600} ساعة"
    return f"{seconds // 86400} يوم"


# ───────────────────────── مساعد استخراج المستخدم ─────────────────────────

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


# ───────────────────────── حذف رسائل المكتوم/المحظور ─────────────────────

@Client.on_message(filters.group, group=15)
async def enforce_mute_gban(c: Client, m: Message):
    if not m.from_user:
        return
    uid = m.from_user.id
    cid = m.chat.id

    if not group_enabled(cid):
        return

    if is_gbanned(uid):
        try:
            await m.chat.ban_member(uid)
        except Exception:
            try:
                await m.delete()
            except Exception:
                pass
        return

    if not can_speak(uid, cid):
        try:
            await m.delete()
        except FloodWait as fw:
            await asyncio.sleep(fw.value)
        except Exception:
            pass


# ───────────────────────── معالج أوامر الكتم/الحظر ────────────────────────

@Client.on_message(filters.text & filters.group, group=14)
async def mute_handler(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    if not can_speak(uid, cid):
        return

    text = resolve_text(m.text, cid)
    k    = botkey()

    try:
        await _handle_mute_commands(c, m, cid, uid, text, k)
    except Exception as e:
        await log_error(e, context="mute_handler")


async def _handle_mute_commands(c, m, cid, uid, text, k):

    # ══════════════════════════════════════════════════════════════════════
    #  كتم مؤقت: كتم [مدة] (رد أو @user)
    #  مثال: كتم 30m / كتم 2h @user99
    # ══════════════════════════════════════════════════════════════════════

    # كتم [مدة] بالردّ
    m_timed_reply = re.fullmatch(r"كتم\s+(\d+[mhd])", text)
    if m_timed_reply and m.reply_to_message and m.reply_to_message.from_user:
        if not is_admin(uid, cid):
            return await m.reply(f"‼️ {k} هـذا الأمـر لـلـادمـن وفـوق فـقـط")
        duration = _parse_duration(m_timed_reply.group(1))
        if not duration:
            return await m.reply(f"⚠️ {k} مدة غير صحيحة — استخدم: 30m / 2h / 1d")
        target_id      = m.reply_to_message.from_user.id
        target_mention = m.reply_to_message.from_user.mention
        if target_id == uid:
            return await m.reply(f"😅 {k} مـا تـقـدر تـكـتـم نـفـسـك!")
        if is_pre(target_id, cid):
            return await m.reply(f"⛔ {k} مـا تـقـدر تـكـتـم {get_rank(target_id, cid)}")
        until = int(_time.time()) + duration
        label = _duration_label(duration)
        key   = f"{target_id}:mute:{cid}:{DEV_ID}"
        pipe  = await ar.pipeline()
        await pipe.set(key, str(until))
        await pipe.sadd(f"{cid}:listMUTE:{DEV_ID}", target_id)
        await pipe.execute()
        utils_cache_invalidate(key)
        return await m.reply(
            f"┌─「 {target_mention} 」\n"
            f"├ {k} تـم الـكـتـم الـمـؤقـت 🔇\n"
            f"├ الـمـدة : {label}\n"
            f"└──────────"
        )

    # كتم [مدة] @user
    m_timed_user = re.fullmatch(r"كتم\s+(\d+[mhd])\s+(@?\S+)", text)
    if m_timed_user:
        if not is_admin(uid, cid):
            return await m.reply(f"‼️ {k} هـذا الأمـر لـلـادمـن وفـوق فـقـط")
        duration = _parse_duration(m_timed_user.group(1))
        if not duration:
            return await m.reply(f"⚠️ {k} مدة غير صحيحة — استخدم: 30m / 2h / 1d")
        target_id, target_mention = await _resolve_user(c, m, m_timed_user.group(2))
        if target_id is None:
            return await m.reply(f"🔍 {k} مـا لـقـيـت هـذا الـمـسـتـخـدم")
        if target_id == uid:
            return await m.reply(f"😅 {k} مـا تـقـدر تـكـتـم نـفـسـك!")
        if is_pre(target_id, cid):
            return await m.reply(f"⛔ {k} مـا تـقـدر تـكـتـم {get_rank(target_id, cid)}")
        until = int(_time.time()) + duration
        label = _duration_label(duration)
        key   = f"{target_id}:mute:{cid}:{DEV_ID}"
        pipe  = await ar.pipeline()
        await pipe.set(key, str(until))
        await pipe.sadd(f"{cid}:listMUTE:{DEV_ID}", target_id)
        await pipe.execute()
        utils_cache_invalidate(key)
        return await m.reply(
            f"┌─「 {target_mention} 」\n"
            f"├ {k} تـم الـكـتـم الـمـؤقـت 🔇\n"
            f"├ الـمـدة : {label}\n"
            f"└──────────"
        )

    # ══════════════════════════════════════════════════════════════════════
    #  كتم دائم (بالردّ)
    # ══════════════════════════════════════════════════════════════════════
    if text == "كتم" and m.reply_to_message and m.reply_to_message.from_user:
        if not is_admin(uid, cid):
            return await m.reply(f"‼️ {k} هـذا الأمـر لـلـادمـن وفـوق فـقـط")
        target_id      = m.reply_to_message.from_user.id
        target_mention = m.reply_to_message.from_user.mention
        if target_id == uid:
            return await m.reply(f"😅 {k} مـا تـقـدر تـكـتـم نـفـسـك!")
        if is_pre(target_id, cid):
            return await m.reply(f"⛔ {k} مـا تـقـدر تـكـتـم {get_rank(target_id, cid)}")
        key = f"{target_id}:mute:{cid}:{DEV_ID}"
        if await ar.get(key):
            return await m.reply(f"┌─「 {target_mention} 」\n├ {k} مـكـتـوم مـسـبـقـاً ⚠️\n└──────────")
        pipe = await ar.pipeline()
        await pipe.set(key, 1)
        await pipe.sadd(f"{cid}:listMUTE:{DEV_ID}", target_id)
        await pipe.execute()
        utils_cache_invalidate(key)
        return await m.reply(f"┌─「 {target_mention} 」\n├ {k} تـم الـكـتـم 🔇\n└──────────")

    # كتم @user (دائم)
    m_local = re.fullmatch(r"كتم\s+(@?\S+)", text)
    if m_local:
        if not is_admin(uid, cid):
            return await m.reply(f"‼️ {k} هـذا الأمـر لـلـادمـن وفـوق فـقـط")
        target_id, target_mention = await _resolve_user(c, m, m_local.group(1))
        if target_id is None:
            return await m.reply(f"🔍 {k} مـا لـقـيـت هـذا الـمـسـتـخـدم")
        if target_id == uid:
            return await m.reply(f"😅 {k} مـا تـقـدر تـكـتـم نـفـسـك!")
        if is_pre(target_id, cid):
            return await m.reply(f"⛔ {k} مـا تـقـدر تـكـتـم {get_rank(target_id, cid)}")
        key = f"{target_id}:mute:{cid}:{DEV_ID}"
        if await ar.get(key):
            return await m.reply(f"┌─「 {target_mention} 」\n├ {k} مـكـتـوم مـسـبـقـاً ⚠️\n└──────────")
        pipe = await ar.pipeline()
        await pipe.set(key, 1)
        await pipe.sadd(f"{cid}:listMUTE:{DEV_ID}", target_id)
        await pipe.execute()
        utils_cache_invalidate(key)
        return await m.reply(f"┌─「 {target_mention} 」\n├ {k} تـم الـكـتـم 🔇\n└──────────")

    # ══════════════════════════════════════════════════════════════════════
    #  كتم عام
    # ══════════════════════════════════════════════════════════════════════
    if text == "كتم عام" and m.reply_to_message and m.reply_to_message.from_user:
        if not is_dev(uid, cid):
            return await m.reply(f"‼️ {k} هـذا الأمـر لـلـمـطـور فـقـط")
        target_id      = m.reply_to_message.from_user.id
        target_mention = m.reply_to_message.from_user.mention
        if is_dev(target_id, cid):
            return await m.reply(f"⛔ {k} مـا تـقـدر تـكـتـم {get_rank(target_id, cid)}")
        key = f"{target_id}:mute:{DEV_ID}"
        if await ar.get(key):
            return await m.reply(f"┌─「 {target_mention} 」\n├ {k} مـكـتـوم عـامـاً مـسـبـقـاً ⚠️\n└──────────")
        pipe = await ar.pipeline()
        await pipe.set(key, 1)
        await pipe.sadd(f"listMUTE:{DEV_ID}", target_id)
        await pipe.execute()
        utils_cache_invalidate(key)
        return await m.reply(f"┌─「 {target_mention} 」\n├ {k} تـم الـكـتـم الـعـام 🔇\n└──────────")

    m_gmute = re.fullmatch(r"كتم عام\s+(@?\S+)", text)
    if m_gmute:
        if not is_dev(uid, cid):
            return await m.reply(f"‼️ {k} هـذا الأمـر لـلـمـطـور فـقـط")
        target_id, target_mention = await _resolve_user(c, m, m_gmute.group(1))
        if target_id is None:
            return await m.reply(f"🔍 {k} مـا لـقـيـت هـذا الـمـسـتـخـدم")
        if is_dev(target_id, cid):
            return await m.reply(f"⛔ {k} مـا تـقـدر تـكـتـم {get_rank(target_id, cid)}")
        key = f"{target_id}:mute:{DEV_ID}"
        if await ar.get(key):
            return await m.reply(f"┌─「 {target_mention} 」\n├ {k} مـكـتـوم عـامـاً مـسـبـقـاً ⚠️\n└──────────")
        pipe = await ar.pipeline()
        await pipe.set(key, 1)
        await pipe.sadd(f"listMUTE:{DEV_ID}", target_id)
        await pipe.execute()
        utils_cache_invalidate(key)
        return await m.reply(f"┌─「 {target_mention} 」\n├ {k} تـم الـكـتـم الـعـام 🔇\n└──────────")

    # ══════════════════════════════════════════════════════════════════════
    #  الغاء الكتم
    # ══════════════════════════════════════════════════════════════════════
    if text == "الغاء الكتم" and m.reply_to_message and m.reply_to_message.from_user:
        if not is_admin(uid, cid):
            return await m.reply(f"‼️ {k} هـذا الأمـر لـلـادمـن وفـوق فـقـط")
        target_id      = m.reply_to_message.from_user.id
        target_mention = m.reply_to_message.from_user.mention
        key = f"{target_id}:mute:{cid}:{DEV_ID}"
        if not await ar.get(key):
            return await m.reply(f"┌─「 {target_mention} 」\n├ {k} مـو مـكـتـوم أصـلاً ❕\n└──────────")
        pipe = await ar.pipeline()
        await pipe.delete(key)
        await pipe.srem(f"{cid}:listMUTE:{DEV_ID}", target_id)
        await pipe.execute()
        utils_cache_invalidate(key)
        return await m.reply(f"┌─「 {target_mention} 」\n├ {k} تـم رفـع الـكـتـم 🔊\n└──────────")

    m_unmute = re.fullmatch(r"الغاء الكتم\s+(@?\S+)", text)
    if m_unmute:
        if not is_admin(uid, cid):
            return await m.reply(f"‼️ {k} هـذا الأمـر لـلـادمـن وفـوق فـقـط")
        target_id, target_mention = await _resolve_user(c, m, m_unmute.group(1))
        if target_id is None:
            return await m.reply(f"🔍 {k} مـا لـقـيـت هـذا الـمـسـتـخـدم")
        key = f"{target_id}:mute:{cid}:{DEV_ID}"
        if not await ar.get(key):
            return await m.reply(f"┌─「 {target_mention} 」\n├ {k} مـو مـكـتـوم أصـلاً ❕\n└──────────")
        pipe = await ar.pipeline()
        await pipe.delete(key)
        await pipe.srem(f"{cid}:listMUTE:{DEV_ID}", target_id)
        await pipe.execute()
        utils_cache_invalidate(key)
        return await m.reply(f"┌─「 {target_mention} 」\n├ {k} تـم رفـع الـكـتـم 🔊\n└──────────")

    # ══════════════════════════════════════════════════════════════════════
    #  الغاء الكتم العام
    # ══════════════════════════════════════════════════════════════════════
    if text == "الغاء الكتم العام" and m.reply_to_message and m.reply_to_message.from_user:
        if not is_dev(uid, cid):
            return await m.reply(f"‼️ {k} هـذا الأمـر لـلـمـطـور فـقـط")
        target_id      = m.reply_to_message.from_user.id
        target_mention = m.reply_to_message.from_user.mention
        key = f"{target_id}:mute:{DEV_ID}"
        if not await ar.get(key):
            return await m.reply(f"┌─「 {target_mention} 」\n├ {k} مـو مـكـتـوم عـامـاً ❕\n└──────────")
        pipe = await ar.pipeline()
        await pipe.delete(key)
        await pipe.srem(f"listMUTE:{DEV_ID}", target_id)
        await pipe.execute()
        utils_cache_invalidate(key)
        return await m.reply(f"┌─「 {target_mention} 」\n├ {k} تـم رفـع الـكـتـم الـعـام 🔊\n└──────────")

    m_ungmute = re.fullmatch(r"الغاء الكتم العام\s+(@?\S+)", text)
    if m_ungmute:
        if not is_dev(uid, cid):
            return await m.reply(f"‼️ {k} هـذا الأمـر لـلـمـطـور فـقـط")
        target_id, target_mention = await _resolve_user(c, m, m_ungmute.group(1))
        if target_id is None:
            return await m.reply(f"🔍 {k} مـا لـقـيـت هـذا الـمـسـتـخـدم")
        key = f"{target_id}:mute:{DEV_ID}"
        if not await ar.get(key):
            return await m.reply(f"┌─「 {target_mention} 」\n├ {k} مـو مـكـتـوم عـامـاً ❕\n└──────────")
        pipe = await ar.pipeline()
        await pipe.delete(key)
        await pipe.srem(f"listMUTE:{DEV_ID}", target_id)
        await pipe.execute()
        utils_cache_invalidate(key)
        return await m.reply(f"┌─「 {target_mention} 」\n├ {k} تـم رفـع الـكـتـم الـعـام 🔊\n└──────────")

    # ══════════════════════════════════════════════════════════════════════
    #  حظر عام
    # ══════════════════════════════════════════════════════════════════════
    if text == "حظر عام" and m.reply_to_message and m.reply_to_message.from_user:
        if not is_dev(uid, cid):
            return await m.reply(f"‼️ {k} هـذا الأمـر لـلـمـطـور فـقـط")
        target_id      = m.reply_to_message.from_user.id
        target_mention = m.reply_to_message.from_user.mention
        if is_dev(target_id, cid):
            return await m.reply(f"⛔ {k} مـا تـقـدر تـحـظـر {get_rank(target_id, cid)}")
        key = f"{target_id}:gban:{DEV_ID}"
        if await ar.get(key):
            return await m.reply(f"┌─「 {target_mention} 」\n├ {k} مـحـظـور عـامـاً مـسـبـقـاً ⚠️\n└──────────")
        pipe = await ar.pipeline()
        await pipe.set(key, 1)
        await pipe.sadd(f"listGBAN:{DEV_ID}", target_id)
        await pipe.execute()
        utils_cache_invalidate(key)
        return await m.reply(f"┌─「 {target_mention} 」\n├ {k} تـم الـحـظـر الـعـام 🚫\n└──────────")

    m_gban = re.fullmatch(r"حظر عام\s+(@?\S+)", text)
    if m_gban:
        if not is_dev(uid, cid):
            return await m.reply(f"‼️ {k} هـذا الأمـر لـلـمـطـور فـقـط")
        target_id, target_mention = await _resolve_user(c, m, m_gban.group(1))
        if target_id is None:
            return await m.reply(f"🔍 {k} مـا لـقـيـت هـذا الـمـسـتـخـدم")
        if is_dev(target_id, cid):
            return await m.reply(f"⛔ {k} مـا تـقـدر تـحـظـر {get_rank(target_id, cid)}")
        key = f"{target_id}:gban:{DEV_ID}"
        if await ar.get(key):
            return await m.reply(f"┌─「 {target_mention} 」\n├ {k} مـحـظـور عـامـاً مـسـبـقـاً ⚠️\n└──────────")
        pipe = await ar.pipeline()
        await pipe.set(key, 1)
        await pipe.sadd(f"listGBAN:{DEV_ID}", target_id)
        await pipe.execute()
        utils_cache_invalidate(key)
        return await m.reply(f"┌─「 {target_mention} 」\n├ {k} تـم الـحـظـر الـعـام 🚫\n└──────────")

    # ══════════════════════════════════════════════════════════════════════
    #  حظر عام من الالعاب
    # ══════════════════════════════════════════════════════════════════════
    if text == "حظر عام من الالعاب" and m.reply_to_message and m.reply_to_message.from_user:
        if not is_dev(uid, cid):
            return await m.reply(f"‼️ {k} هـذا الأمـر لـلـمـطـور فـقـط")
        target_id      = m.reply_to_message.from_user.id
        target_mention = m.reply_to_message.from_user.mention
        if is_dev(target_id, cid):
            return await m.reply(f"⛔ {k} مـا تـقـدر تـحـظـر {get_rank(target_id, cid)}")
        key = f"{target_id}:gbangames:{DEV_ID}"
        if await ar.get(key):
            return await m.reply(f"┌─「 {target_mention} 」\n├ {k} مـحـظـور مـن الألـعـاب مـسـبـقـاً ⚠️\n└──────────")
        pipe = await ar.pipeline()
        await pipe.set(key, 1)
        await pipe.sadd(f"listGBANGAMES:{DEV_ID}", target_id)
        await pipe.execute()
        pipe = await ar.pipeline()
        await pipe.delete(f"{target_id}:Floos")
        await pipe.srem("BankList", target_id)
        await pipe.execute()
        return await m.reply(f"┌─「 {target_mention} 」\n├ {k} تـم حـظـره مـن الألـعـاب 🎮🚫\n└──────────")

    m_gbangames = re.fullmatch(r"حظر عام من الالعاب\s+(@?\S+)", text)
    if m_gbangames:
        if not is_dev(uid, cid):
            return await m.reply(f"‼️ {k} هـذا الأمـر لـلـمـطـور فـقـط")
        target_id, target_mention = await _resolve_user(c, m, m_gbangames.group(1))
        if target_id is None:
            return await m.reply(f"🔍 {k} مـا لـقـيـت هـذا الـمـسـتـخـدم")
        if is_dev(target_id, cid):
            return await m.reply(f"⛔ {k} مـا تـقـدر تـحـظـر {get_rank(target_id, cid)}")
        key = f"{target_id}:gbangames:{DEV_ID}"
        if await ar.get(key):
            return await m.reply(f"┌─「 {target_mention} 」\n├ {k} مـحـظـور مـن الألـعـاب مـسـبـقـاً ⚠️\n└──────────")
        pipe = await ar.pipeline()
        await pipe.set(key, 1)
        await pipe.sadd(f"listGBANGAMES:{DEV_ID}", target_id)
        await pipe.execute()
        pipe = await ar.pipeline()
        await pipe.delete(f"{target_id}:Floos")
        await pipe.srem("BankList", target_id)
        await pipe.execute()
        return await m.reply(f"┌─「 {target_mention} 」\n├ {k} تـم حـظـره مـن الألـعـاب 🎮🚫\n└──────────")

    # ══════════════════════════════════════════════════════════════════════
    #  الغاء الحظر العام
    # ══════════════════════════════════════════════════════════════════════
    if text == "الغاء الحظر العام" and m.reply_to_message and m.reply_to_message.from_user:
        if not is_dev(uid, cid):
            return await m.reply(f"‼️ {k} هـذا الأمـر لـلـمـطـور فـقـط")
        target_id      = m.reply_to_message.from_user.id
        target_mention = m.reply_to_message.from_user.mention
        key = f"{target_id}:gban:{DEV_ID}"
        if not await ar.get(key):
            return await m.reply(f"┌─「 {target_mention} 」\n├ {k} مـو مـحـظـور عـامـاً ❕\n└──────────")
        pipe = await ar.pipeline()
        await pipe.delete(key)
        await pipe.srem(f"listGBAN:{DEV_ID}", target_id)
        await pipe.execute()
        utils_cache_invalidate(key)
        return await m.reply(f"┌─「 {target_mention} 」\n├ {k} تـم رفـع الـحـظـر الـعـام ✅\n└──────────")

    m_ungban = re.fullmatch(r"الغاء الحظر العام\s+(@?\S+)", text)
    if m_ungban:
        if not is_dev(uid, cid):
            return await m.reply(f"‼️ {k} هـذا الأمـر لـلـمـطـور فـقـط")
        target_id, target_mention = await _resolve_user(c, m, m_ungban.group(1))
        if target_id is None:
            return await m.reply(f"🔍 {k} مـا لـقـيـت هـذا الـمـسـتـخـدم")
        key = f"{target_id}:gban:{DEV_ID}"
        if not await ar.get(key):
            return await m.reply(f"┌─「 {target_mention} 」\n├ {k} مـو مـحـظـور عـامـاً ❕\n└──────────")
        pipe = await ar.pipeline()
        await pipe.delete(key)
        await pipe.srem(f"listGBAN:{DEV_ID}", target_id)
        await pipe.execute()
        utils_cache_invalidate(key)
        return await m.reply(f"┌─「 {target_mention} 」\n├ {k} تـم رفـع الـحـظـر الـعـام ✅\n└──────────")

    # ══════════════════════════════════════════════════════════════════════
    #  الغاء الحظر العام من الالعاب
    # ══════════════════════════════════════════════════════════════════════
    if text == "الغاء الحظر العام من الالعاب" and m.reply_to_message and m.reply_to_message.from_user:
        if not is_dev(uid, cid):
            return await m.reply(f"‼️ {k} هـذا الأمـر لـلـمـطـور فـقـط")
        target_id      = m.reply_to_message.from_user.id
        target_mention = m.reply_to_message.from_user.mention
        key = f"{target_id}:gbangames:{DEV_ID}"
        if not await ar.get(key):
            return await m.reply(f"┌─「 {target_mention} 」\n├ {k} مـو مـحـظـور مـن الألـعـاب ❕\n└──────────")
        pipe = await ar.pipeline()
        await pipe.delete(key)
        await pipe.srem(f"listGBANGAMES:{DEV_ID}", target_id)
        await pipe.execute()
        utils_cache_invalidate(key)
        return await m.reply(f"┌─「 {target_mention} 」\n├ {k} تـم رفـع حـظـر الألـعـاب ✅\n└──────────")

    m_ungbangames = re.fullmatch(r"الغاء الحظر العام من الالعاب\s+(@?\S+)", text)
    if m_ungbangames:
        if not is_dev(uid, cid):
            return await m.reply(f"‼️ {k} هـذا الأمـر لـلـمـطـور فـقـط")
        target_id, target_mention = await _resolve_user(c, m, m_ungbangames.group(1))
        if target_id is None:
            return await m.reply(f"🔍 {k} مـا لـقـيـت هـذا الـمـسـتـخـدم")
        key = f"{target_id}:gbangames:{DEV_ID}"
        if not await ar.get(key):
            return await m.reply(f"┌─「 {target_mention} 」\n├ {k} مـو مـحـظـور مـن الألـعـاب ❕\n└──────────")
        pipe = await ar.pipeline()
        await pipe.delete(key)
        await pipe.srem(f"listGBANGAMES:{DEV_ID}", target_id)
        await pipe.execute()
        utils_cache_invalidate(key)
        return await m.reply(f"┌─「 {target_mention} 」\n├ {k} تـم رفـع حـظـر الألـعـاب ✅\n└──────────")

    # ══════════════════════════════════════════════════════════════════════
    #  مسح المكتومين / المحظورين
    # ══════════════════════════════════════════════════════════════════════
    if text == "مسح المكتومين":
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هـذا الأمـر لـلـمـديـر وفـوق فـقـط")
        muted = await ar.smembers(f"{cid}:listMUTE:{DEV_ID}")
        if not muted:
            return await m.reply(f"✨ {k} لا يـوجـد مـكـتـومـون")
        count = 0
        for mid in list(muted):
            await ar.srem(f"{cid}:listMUTE:{DEV_ID}", mid)
            await ar.delete(f"{mid}:mute:{cid}:{DEV_ID}")
            utils_cache_invalidate(f"{mid}:mute:{cid}:{DEV_ID}")
            count += 1
        return await m.reply(f"╔══ {k} ══╗\n┃ تـم مـسـح {count} مـكـتـوم 🧹\n╚══════════╝")

    if text == "مسح المكتومين عام":
        if not is_dev(uid, cid):
            return await m.reply(f"‼️ {k} هـذا الأمـر لـلـمـطـور فـقـط")
        muted = await ar.smembers(f"listMUTE:{DEV_ID}")
        if not muted:
            return await m.reply(f"✨ {k} لا يـوجـد مـكـتـومـون عـامـاً")
        count = 0
        for mid in list(muted):
            await ar.srem(f"listMUTE:{DEV_ID}", mid)
            await ar.delete(f"{mid}:mute:{DEV_ID}")
            utils_cache_invalidate(f"{mid}:mute:{DEV_ID}")
            count += 1
        return await m.reply(f"╔══ {k} ══╗\n┃ تـم مـسـح {count} مـكـتـوم عـام 🧹\n╚══════════╝")

    if text == "مسح المحظورين عام":
        if not is_dev(uid, cid):
            return await m.reply(f"‼️ {k} هـذا الأمـر لـلـمـطـور فـقـط")
        gbanned = await ar.smembers(f"listGBAN:{DEV_ID}")
        if not gbanned:
            return await m.reply(f"✨ {k} لا يـوجـد مـحـظـورون عـامـاً")
        count = 0
        for gid in list(gbanned):
            await ar.srem(f"listGBAN:{DEV_ID}", gid)
            await ar.delete(f"{gid}:gban:{DEV_ID}")
            utils_cache_invalidate(f"{gid}:gban:{DEV_ID}")
            count += 1
        return await m.reply(f"╔══ {k} ══╗\n┃ تـم مـسـح {count} مـحـظـور عـام 🧹\n╚══════════╝")

    if text == "قائمة المكتومين":
        if not is_admin(uid, cid):
            return await m.reply(f"‼️ {k} هـذا الأمـر لـلـادمـن وفـوق فـقـط")
        muted = await ar.smembers(f"{cid}:listMUTE:{DEV_ID}")
        if not muted:
            return await m.reply(f"✨ {k} لا يـوجـد أحـد مـكـتـوم")
        lines = "\n".join(f"• `{mid}`" for mid in muted)
        return await m.reply(f"{k} المكتومون:\n{lines}")
