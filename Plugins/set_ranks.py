"""
نظام الرفع والتنزيل - أوامر تعيين وإزالة الرتب
أوامر الرفع:
  رفع Dev @user / رد      → رفع إلى Dev²🎖 (يحتاج botowner)
  رفع MY @user / رد       → رفع إلى Myth🎖️ (يحتاج Dev²)
  رفع مالك اساسي @user   → يحتاج gowner وفوق
  رفع مالك @user          → يحتاج gowner
  رفع مدير @user          → يحتاج owner
  رفع ادمن @user          → يحتاج mod
  رفع مميز @user          → يحتاج admin
  تعطيل الرفع / تفعيل الرفع → يحتاج owner
أوامر التنزيل:
  تنزيل Dev / تنزيل MY / تنزيل مالك اساسي / تنزيل مالك
  تنزيل مدير / تنزيل ادمن / تنزيل مميز / تنزيل الكل
"""

import re
from pyrogram import Client, filters
from pyrogram.types import Message

from config import r, DEV_ID, DEV_ID_INT, botkey, ar
from helpers.ranks import (
    get_rank, is_dev, is_botowner, is_dev2, is_myth,
    is_gowner, is_owner, is_mod, is_admin, is_pre,
    rank_cache_invalidate, isLockCommand,
)
from helpers.utils import group_enabled, can_speak, resolve_text


def _key(cid, rkey, uid):
    """تنسيق مفاتيح Redis الموحّد"""
    return f"{cid}:{rkey}:{uid}:{DEV_ID}"

def _list_key(cid, rkey):
    return f"{cid}:{rkey}s:{DEV_ID}"


async def _resolve_target(c: Client, m: Message, text_part: str | None):
    if text_part is None:
        if m.reply_to_message and m.reply_to_message.from_user:
            u = m.reply_to_message.from_user
            return u.id, u.mention
        return None, None
    try:
        uid = int(text_part)
    except ValueError:
        uid = text_part.lstrip("@")
    try:
        u = await c.get_users(uid)
        return u.id, u.mention
    except Exception:
        return None, None


def _self_check(m, target_id):
    return target_id == m.from_user.id

def _dev_check(target_id):
    return target_id == DEV_ID_INT


@Client.on_message(filters.text & filters.group, group=7)
async def set_ranks_handler(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    if not can_speak(uid, cid):
        return

    text = resolve_text(m.text, cid)
    k    = botkey()

    if isLockCommand(uid, cid, text):
        return

    # ── تعطيل / تفعيل الرفع ──────────────────────────────────────────────
    if text == "تعطيل الرفع":
        if not is_owner(uid, cid):
            return await m.reply(f"‼️ {k} هـذا الأمـر لـلـمـالـك وفـوق فـقـط")
        if await ar.get(f"{cid}:disableRanks:{DEV_ID}"):
            return await m.reply(f"┌─「 {m.from_user.mention} 」\n├ {k} الـرفـع مـعـطـل مـسـبـقـاً ⚠️\n└──────────")
        await ar.set(f"{cid}:disableRanks:{DEV_ID}", 1)
        return await m.reply(f"╔══ {k} ══╗\n┃ تـم تـعـطـيـل الـرفـع ✅\n╚══════════╝")

    if text == "تفعيل الرفع":
        if not is_owner(uid, cid):
            return await m.reply(f"‼️ {k} هـذا الأمـر لـلـمـالـك وفـوق فـقـط")
        if not await ar.get(f"{cid}:disableRanks:{DEV_ID}"):
            return await m.reply(f"┌─「 {m.from_user.mention} 」\n├ {k} الـرفـع مـفـعـل مـسـبـقـاً ⚠️\n└──────────")
        await ar.delete(f"{cid}:disableRanks:{DEV_ID}")
        return await m.reply(f"╔══ {k} ══╗\n┃ تـم تـفـعـيـل الـرفـع ✅\n╚══════════╝")

    if await ar.get(f"{cid}:disableRanks:{DEV_ID}"):
        return

    rank = get_rank(uid, cid)

    # ─────────── دوال مساعدة لرفع / تنزيل ────────────────────────────────
    async def do_promote(rkey: str, list_rkey: str, rank_label: str, checker, extra_keys_to_clear=None):
        """checker = الدالة التي تتحقق من رتبة الشخص المُرفَّع"""
        # استخراج الهدف
        parts  = text.split()
        raw    = parts[-1] if len(parts) > 2 else None
        has_at = raw and (raw.startswith("@") or raw.lstrip("-").isdigit()) if raw else False

        if has_at:
            target_id, mention = await _resolve_target(c, m, raw)
        else:
            target_id, mention = await _resolve_target(c, m, None)

        if target_id is None:
            return await m.reply(f"🔍 {k} حـدد الـمـسـتـخـدم بـرد أو يـوزر/آيـدي")
        if _self_check(m, target_id):
            return await m.reply(f"😅 {k} مـا تـقـدر تـرفـع نـفـسـك!")
        if _dev_check(target_id):
            return await m.reply("😅 مـا تـقـدر تـرفـع نـفـسـك!")

        key = _key(cid, rkey, target_id)
        if await ar.get(key):
            return await m.reply(f"┌─「 {mention} 」\n├ {k} {rank_label} مـسـبـقـاً ⚠️\n└──────────")

        pipe = await ar.pipeline()
        await pipe.set(key, 1)
        await pipe.sadd(_list_key(cid, rkey), target_id)
        await pipe.execute()
        rank_cache_invalidate(target_id, cid)
        # رفع الكتم إذا موجود
        await _clear_mute(target_id, cid)
        return await m.reply(f"┌─「 {mention} 」\n├ {k} تـم الـرفـع صـار {rank_label} 🌟\n└──────────")

    async def do_demote(rkey: str, list_rkey: str, rank_label: str):
        parts  = text.split()
        raw    = parts[-1] if len(parts) > 2 else None
        has_at = raw and (raw.startswith("@") or raw.lstrip("-").isdigit()) if raw else False

        if has_at:
            target_id, mention = await _resolve_target(c, m, raw)
        else:
            target_id, mention = await _resolve_target(c, m, None)

        if target_id is None:
            return await m.reply(f"🔍 {k} حـدد الـمـسـتـخـدم بـرد أو يـوزر/آيـدي")
        if _dev_check(target_id):
            return await m.reply("😅 مـا تـقـدر تـنـزل نـفـسـك!")
        if rank == get_rank(target_id, cid):
            return await m.reply("⚠️ نـفـس رتـبـتـك أصـلاً!")

        key = _key(cid, rkey, target_id)
        if not await ar.get(key):
            return await m.reply(f"┌─「 {mention} 」\n├ {k} مـو {rank_label} أصـلاً ❕\n└──────────")

        pipe = await ar.pipeline()
        await pipe.delete(key)
        await pipe.srem(_list_key(cid, rkey), target_id)
        await pipe.execute()
        rank_cache_invalidate(target_id, cid)
        return await m.reply(f"「 {mention} 」\n{k} نزلته من {rank_label}\n☆")

    async def _clear_mute(tid, c_id):
        pipe = await ar.pipeline()
        await pipe.delete(f"{tid}:mute:{DEV_ID}")
        await pipe.srem(f"listMUTE:{DEV_ID}", tid)
        await pipe.delete(f"{tid}:mute:{c_id}:{DEV_ID}")
        await pipe.srem(f"{c_id}:listMUTEs:{DEV_ID}", tid)
        await pipe.execute()

    # ═══════════════════════════════════════════════════════════════════════
    # ── أوامر الرفع ────────────────────────────────────────────────────────
    # ═══════════════════════════════════════════════════════════════════════

    # رفع Dev² (يحتاج botowner)
    if re.match(r"^رفع Dev($| .+)", text):
        if not is_botowner(uid, cid):
            return await m.reply(f"{k} هذا الامر يخص ( Dev🎖️ ) بس")
        # تحقق إضافي: لا يرفع Myth أو فوق
        parts = text.split()
        raw = parts[-1] if len(parts) > 1 and (parts[-1].startswith("@") or parts[-1].lstrip("-").isdigit()) else None
        target_id, mention = await _resolve_target(c, m, raw)
        if target_id is None:
            return await m.reply(f"🔍 {k} حـدد الـمـسـتـخـدم بـرد أو يـوزر/آيـدي")
        if _self_check(m, target_id): return await m.reply(f"😅 {k} مـا تـقـدر تـرفـع نـفـسـك!")
        if _dev_check(target_id):     return await m.reply("😅 مـا تـقـدر تـرفـع نـفـسـك!")
        key = f"{target_id}:rankDEV2:{DEV_ID}"
        if await ar.get(key):
            return await m.reply(f"「 {mention} 」\n{k} Dev²🎖 من قبل\n☆")
        pipe = await ar.pipeline()
        await pipe.set(key, 1)
        await pipe.sadd(f"{DEV_ID}:DEV2", target_id)
        rank_cache_invalidate(target_id, cid)
        await _clear_mute(target_id, cid)
        return await m.reply(f"{k} الحلو 「 {mention} 」\n{k} رفعته صار Dev²🎖\n☆")

    # رفع Myth (يحتاج Dev²)
    if re.match(r"^رفع MY($| .+)", text):
        if not is_dev2(uid, cid):
            return await m.reply(f"{k} هذا الامر يخص ( Dev²🎖️ وفوق ) بس")
        parts = text.split()
        raw = parts[-1] if len(parts) > 1 and (parts[-1].startswith("@") or parts[-1].lstrip("-").isdigit()) else None
        target_id, mention = await _resolve_target(c, m, raw)
        if target_id is None:
            return await m.reply(f"🔍 {k} حـدد الـمـسـتـخـدم بـرد أو يـوزر/آيـدي")
        if _self_check(m, target_id): return await m.reply(f"😅 {k} مـا تـقـدر تـرفـع نـفـسـك!")
        if _dev_check(target_id):     return await m.reply("😅 مـا تـقـدر تـرفـع نـفـسـك!")
        if rank == get_rank(target_id, cid): return await m.reply("⚠️ نـفـس رتـبـتـك أصـلاً!")
        key = f"{target_id}:rankDEV:{DEV_ID}"
        if await ar.get(key):
            return await m.reply(f"「 {mention} 」\n{k} Myth🎖️ من قبل\n☆")
        pipe = await ar.pipeline()
        await pipe.set(key, 1)
        await pipe.sadd(f"{DEV_ID}:DEV", target_id)
        rank_cache_invalidate(target_id, cid)
        await _clear_mute(target_id, cid)
        return await m.reply(f"{k} الحلو 「 {mention} 」\n{k} رفعته صار Myth🎖️\n☆")

    # رفع مالك اساسي (يحتاج gowner)
    if re.match(r"^رفع مالك اساسي($| .+)", text):
        if not is_gowner(uid, cid):
            return await m.reply(f"{k} هذا الامر يخص ( المالك الاساسي وفوق ) بس")
        return await do_promote("rankGOWNER", "rankGOWNERs", "المالك الاساسي", is_gowner)

    # رفع مالك (يحتاج gowner)
    if re.match(r"^رفع مالك($| .+)", text):
        if not is_gowner(uid, cid):
            return await m.reply(f"{k} هذا الامر يخص ( المالك الاساسي ) بس")
        return await do_promote("rankOWNER", "rankOWNERs", "المالك", is_owner)

    # رفع مدير (يحتاج owner)
    if re.match(r"^رفع مدير($| .+)", text):
        if not is_owner(uid, cid):
            return await m.reply(f"‼️ {k} هـذا الأمـر لـلـمـالـك وفـوق فـقـط")
        return await do_promote("rankMOD", "rankMODs", "المدير", is_mod)

    # رفع ادمن (يحتاج mod)
    if re.match(r"^رفع ادمن($| .+)", text):
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هـذا الأمـر لـلـمـديـر وفـوق فـقـط")
        return await do_promote("rankADMIN", "rankADMINs", "الادمن", is_admin)

    # رفع مميز (يحتاج admin)
    if re.match(r"^رفع مميز($| .+)", text):
        if not is_admin(uid, cid):
            return await m.reply(f"{k} هذا الامر يخص ( الادمن وفوق ) بس")
        return await do_promote("rankPRE", "rankPREs", "المميز", is_pre)

    # ═══════════════════════════════════════════════════════════════════════
    # ── أوامر التنزيل ──────────────────────────────────────────────────────
    # ═══════════════════════════════════════════════════════════════════════

    if re.match(r"^تنزيل Dev($| .+)", text):
        if not is_botowner(uid, cid):
            return await m.reply(f"{k} هذا الامر يخص ( Dev🎖️ ) بس")
        parts = text.split()
        raw = parts[-1] if len(parts) > 1 and (parts[-1].startswith("@") or parts[-1].lstrip("-").isdigit()) else None
        target_id, mention = await _resolve_target(c, m, raw)
        if target_id is None:
            return await m.reply(f"🔍 {k} حـدد الـمـسـتـخـدم بـرد أو يـوزر/آيـدي")
        if _dev_check(target_id): return await m.reply("😅 مـا تـقـدر تـنـزل نـفـسـك!")
        key = f"{target_id}:rankDEV2:{DEV_ID}"
        if not await ar.get(key):
            return await m.reply(f"「 {mention} 」\n{k} مو Dev²🎖\n☆")
        await ar.delete(key)
        await ar.srem(f"{DEV_ID}:DEV2", target_id)
        rank_cache_invalidate(target_id, cid)
        return await m.reply(f"「 {mention} 」\n{k} نزلته من Dev²🎖\n☆")

    if re.match(r"^تنزيل MY($| .+)", text):
        if not is_dev2(uid, cid):
            return await m.reply(f"{k} هذا الامر يخص ( Dev²🎖️ وفوق ) بس")
        parts = text.split()
        raw = parts[-1] if len(parts) > 1 and (parts[-1].startswith("@") or parts[-1].lstrip("-").isdigit()) else None
        target_id, mention = await _resolve_target(c, m, raw)
        if target_id is None:
            return await m.reply(f"🔍 {k} حـدد الـمـسـتـخـدم بـرد أو يـوزر/آيـدي")
        if _dev_check(target_id): return await m.reply("😅 مـا تـقـدر تـنـزل نـفـسـك!")
        if rank == get_rank(target_id, cid): return await m.reply("⚠️ نـفـس رتـبـتـك أصـلاً!")
        key = f"{target_id}:rankDEV:{DEV_ID}"
        if not await ar.get(key):
            return await m.reply(f"「 {mention} 」\n{k} مو Myth🎖️ من قبل\n☆")
        await ar.delete(key)
        await ar.srem(f"{DEV_ID}:DEV", target_id)
        rank_cache_invalidate(target_id, cid)
        return await m.reply(f"「 {mention} 」\n{k} نزلته من Myth🎖️\n☆")

    if re.match(r"^تنزيل مالك اساسي($| .+)", text):
        if not is_gowner(uid, cid):
            return await m.reply(f"{k} هذا الامر يخص ( المالك الاساسي وفوق ) بس")
        return await do_demote("rankGOWNER", "rankGOWNERs", "المالك الاساسي")

    if re.match(r"^تنزيل مالك($| .+)", text):
        if not is_gowner(uid, cid):
            return await m.reply(f"{k} هذا الامر يخص ( المالك الاساسي ) بس")
        return await do_demote("rankOWNER", "rankOWNERs", "المالك")

    if re.match(r"^تنزيل مدير($| .+)", text):
        if not is_owner(uid, cid):
            return await m.reply(f"‼️ {k} هـذا الأمـر لـلـمـالـك وفـوق فـقـط")
        return await do_demote("rankMOD", "rankMODs", "المدير")

    if re.match(r"^تنزيل ادمن($| .+)", text):
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هـذا الأمـر لـلـمـديـر وفـوق فـقـط")
        return await do_demote("rankADMIN", "rankADMINs", "الادمن")

    if re.match(r"^تنزيل مميز($| .+)", text):
        if not is_admin(uid, cid):
            return await m.reply(f"{k} هذا الامر يخص ( الادمن وفوق ) بس")
        return await do_demote("rankPRE", "rankPREs", "المميز")

    # تنزيل الكل
    if re.match(r"^تنزيل الكل($| .+)", text):
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هـذا الأمـر لـلـمـديـر وفـوق فـقـط")

        parts = text.split()
        raw = parts[-1] if len(parts) > 1 and (parts[-1].startswith("@") or parts[-1].lstrip("-").isdigit()) else None
        target_id, mention = await _resolve_target(c, m, raw)
        if target_id is None:
            return await m.reply(f"🔍 {k} حـدد الـمـسـتـخـدم بـرد أو يـوزر/آيـدي")
        if _dev_check(target_id): return await m.reply("😅 مـا تـقـدر تـنـزل نـفـسـك!")
        if target_id == uid:       return await m.reply(f"{k} مافيك تنزل نفسك")
        if rank == get_rank(target_id, cid): return await m.reply("⚠️ نـفـس رتـبـتـك أصـلاً!")

        t_level   = 0
        my_level  = 0
        from helpers.ranks import _get_rank_level
        t_level  = _get_rank_level(target_id, cid)
        my_level = _get_rank_level(uid, cid)

        if t_level >= my_level:
            return await m.reply(f"{k} رتبته اعلى منك أو مساوية")

        t_rank_name = get_rank(target_id, cid)
        # حذف كل الرتب حسب المستوى
        rank_map = [
            (7, f"{target_id}:rankDEV2:{DEV_ID}",          f"{DEV_ID}:DEV2"),
            (6, f"{target_id}:rankDEV:{DEV_ID}",            f"{DEV_ID}:DEV"),
            (5, _key(cid, "rankGOWNER", target_id),         _list_key(cid, "rankGOWNER")),
            (4, _key(cid, "rankOWNER",  target_id),         _list_key(cid, "rankOWNER")),
            (3, _key(cid, "rankMOD",    target_id),         _list_key(cid, "rankMOD")),
            (2, _key(cid, "rankADMIN",  target_id),         _list_key(cid, "rankADMIN")),
            (1, _key(cid, "rankPRE",    target_id),         _list_key(cid, "rankPRE")),
        ]
        pipe = await ar.pipeline()
        for lvl, rkey, lkey in rank_map:
            if lvl < my_level:
                await pipe.delete(rkey)
                await pipe.srem(lkey, target_id)
        await pipe.execute()

        rank_cache_invalidate(target_id, cid)
        return await m.reply(f"「 {mention} 」\n{k} نزلته من {t_rank_name}\n☆")
