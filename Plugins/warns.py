"""
نظام التحذيرات (Warns)
───────────────────────
الأوامر:
  تحذير (رد) / تحذير @user [سبب]   → إعطاء تحذير
  مسح التحذيرات (رد) / مسح التحذيرات @user → إعادة ضبط تحذيرات عضو
  التحذيرات (رد) / التحذيرات @user  → عرض عدد تحذيرات عضو
  كل التحذيرات                       → عرض كل من لديهم تحذيرات
  حد التحذيرات [عدد]                 → ضبط الحد (افتراضي: 3)
  عقوبة التحذيرات [حظر|طرد|كتم]     → ضبط العقوبة عند الوصول للحد
───────────────────────
يستخدم Redis لتخزين عدد التحذيرات والأسباب
"""

import re

from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import Message

from config import r, ar, DEV_ID, botkey, cached_smembers
from helpers.ranks import is_admin, is_mod, is_pre
from helpers.utils import group_enabled, resolve_text

# ── مفاتيح Redis ──
def _warn_key(uid: int, cid: int) -> str:
    return f"{cid}:warns:{uid}:{DEV_ID}"

def _warn_reasons_key(uid: int, cid: int) -> str:
    return f"{cid}:warn_reasons:{uid}:{DEV_ID}"

def _warn_limit_key(cid: int) -> str:
    return f"{cid}:warn_limit:{DEV_ID}"

def _warn_mode_key(cid: int) -> str:
    return f"{cid}:warn_mode:{DEV_ID}"

def _warn_list_key(cid: int) -> str:
    return f"{cid}:warnlist:{DEV_ID}"


# ─────────────────────────────────────────────────────────────────────────
# مساعد استخراج المستخدم
# ─────────────────────────────────────────────────────────────────────────

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
# أوامر التحذير
# ─────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.text & filters.group, group=18)
async def warns_commands(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    text = resolve_text(m.text, cid)
    k = botkey()

    # ── تحذير ──
    warn_match = re.fullmatch(r"تحذير(?:\s+(@?\S+))?(?:\s+(.+))?", text)
    if warn_match:
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        target = warn_match.group(1)
        reason = warn_match.group(2) or "لا يوجد سبب"
        tid, mention = await _resolve_user(c, m, target)
        if not tid:
            return await m.reply(f"‼️ {k} حدد المستخدم بالرد أو المنشن")
        if is_pre(tid, cid):
            return await m.reply(f"‼️ {k} لا يمكن تحذير المميزين والإداريين")

        # أضف التحذير
        warns = await ar.incr(_warn_key(tid, cid))
        await ar.rpush(_warn_reasons_key(tid, cid), reason)
        await ar.sadd(_warn_list_key(cid), tid)

        limit = int(await ar.get(_warn_limit_key(cid)) or 3)

        if warns >= limit:
            # وصل للحد — طبّق العقوبة
            mode = await ar.get(_warn_mode_key(cid)) or "طرد"
            # أعد ضبط التحذيرات
            await ar.delete(_warn_key(tid, cid))
            await ar.delete(_warn_reasons_key(tid, cid))
            await ar.srem(_warn_list_key(cid), tid)
            try:
                if mode == "حظر":
                    await c.ban_chat_member(cid, tid)
                    action = "🔨 تم حظره"
                elif mode == "كتم":
                    await c.restrict_chat_member(
                        cid, tid,
                        permissions={"can_send_messages": False}
                    )
                    action = "🔇 تم كتمه"
                else:
                    await c.ban_chat_member(cid, tid)
                    await c.unban_chat_member(cid, tid)
                    action = "👢 تم طرده"
            except Exception:
                action = "⚠️ لم أتمكن من تطبيق العقوبة"

            return await m.reply(
                f"╔══ {k} ══╗\n"
                f"┃ ⚠️ {mention} وصل للحد!\n"
                f"┃ {action} تلقائياً\n"
                f"┃ السبب الأخير: {reason}\n"
                f"╚══════════╝"
            )

        return await m.reply(
            f"╔══ {k} ══╗\n"
            f"┃ ⚠️ تحذير لـ {mention}\n"
            f"┃ السبب: {reason}\n"
            f"┃ عدد التحذيرات: {warns}/{limit}\n"
            f"╚══════════╝"
        )

    # ── مسح التحذيرات ──
    reset_match = re.fullmatch(r"مسح التحذيرات(?:\s+(@?\S+))?", text)
    if reset_match:
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        target = reset_match.group(1)
        tid, mention = await _resolve_user(c, m, target)
        if not tid:
            return await m.reply(f"‼️ {k} حدد المستخدم بالرد أو المنشن")
        await ar.delete(_warn_key(tid, cid))
        await ar.delete(_warn_reasons_key(tid, cid))
        await ar.srem(_warn_list_key(cid), tid)
        return await m.reply(
            f"╔══ {k} ══╗\n┃ ✅ تم مسح تحذيرات {mention}\n╚══════════╝"
        )

    # ── التحذيرات ──
    check_match = re.fullmatch(r"التحذيرات(?:\s+(@?\S+))?", text)
    if check_match:
        target = check_match.group(1)
        tid, mention = await _resolve_user(c, m, target)
        if not tid:
            return await m.reply(f"‼️ {k} حدد المستخدم بالرد أو المنشن")
        warns = int(await ar.get(_warn_key(tid, cid)) or 0)
        limit = int(await ar.get(_warn_limit_key(cid)) or 3)
        reasons_raw = await ar.lrange(_warn_reasons_key(tid, cid), 0, -1)
        reasons_text = ""
        if reasons_raw:
            reasons_text = "\n" + "\n".join(
                f"┃ {i+1}. {r}" for i, r in enumerate(reasons_raw)
            )
        return await m.reply(
            f"╔══ {k} ══╗\n"
            f"┃ 👤 {mention}\n"
            f"┃ ⚠️ التحذيرات: {warns}/{limit}"
            f"{reasons_text}\n"
            f"╚══════════╝"
        )

    # ── كل التحذيرات ──
    if text == "كل التحذيرات":
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        warned_ids = cached_smembers(_warn_list_key(cid))
        if not warned_ids:
            return await m.reply(f"✨ {k} لا يوجد أحد لديه تحذيرات")
        limit = int(await ar.get(_warn_limit_key(cid)) or 3)
        lines = []
        for wid in warned_ids:
            w = await ar.get(_warn_key(int(wid), cid)) or 0
            if int(w) > 0:
                try:
                    user = await c.get_users(int(wid))
                    name = user.mention
                except Exception:
                    name = f"`{wid}`"
                lines.append(f"┃ {name}: {w}/{limit}")
        if not lines:
            return await m.reply(f"✨ {k} لا يوجد أحد لديه تحذيرات")
        return await m.reply(
            f"╔══ {k} ══╗\n" + "\n".join(lines) + "\n╚══════════╝"
        )

    # ── حد التحذيرات ──
    limit_match = re.fullmatch(r"حد التحذيرات\s+(\d+)", text)
    if limit_match:
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        lim = int(limit_match.group(1))
        if not (1 <= lim <= 20):
            return await m.reply(f"‼️ {k} الحد يجب أن يكون بين 1 و 20")
        await ar.set(_warn_limit_key(cid), lim)
        return await m.reply(
            f"╔══ {k} ══╗\n┃ ✅ تم ضبط حد التحذيرات على {lim}\n╚══════════╝"
        )

    # ── عقوبة التحذيرات ──
    mode_match = re.fullmatch(r"عقوبة التحذيرات\s+(حظر|طرد|كتم)", text)
    if mode_match:
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        mode = mode_match.group(1)
        await ar.set(_warn_mode_key(cid), mode)
        return await m.reply(
            f"╔══ {k} ══╗\n┃ ✅ العقوبة عند الحد: {mode}\n╚══════════╝"
        )
