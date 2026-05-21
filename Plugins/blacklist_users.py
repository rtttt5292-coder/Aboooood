"""
نظام القائمة السوداء للمستخدمين (Blacklist Users)
──────────────────────────────────────────────────
الأوامر:
  حظر تلقائي (رد/@user)     → إضافة مستخدم للقائمة السوداء (يُطرد فور دخوله)
  رفع حظر تلقائي (رد/@user) → إزالة مستخدم من القائمة السوداء
  القائمة السوداء            → عرض قائمة المحظورين تلقائياً
──────────────────────────────────────────────────
يختلف عن الحظر العام (gban) — هذا القائمة السوداء خاصة بكل مجموعة
"""

import re

from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import Message, ChatMemberUpdated

from config import r, ar, DEV_ID, botkey, cached_smembers
from helpers.ranks import is_mod, is_pre, is_owner
from helpers.utils import group_enabled, resolve_text


# ── مفاتيح Redis ──
def _bl_key(cid: int) -> str:
    return f"{cid}:blacklist_users:{DEV_ID}"


async def _resolve_target(c: Client, m: Message, target: str):
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
# الأوامر
# ─────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.text & filters.group, group=47)
async def blacklist_users_commands(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    text = resolve_text(m.text, cid)
    k = botkey()

    # ── حظر تلقائي ──
    add_m = re.fullmatch(r"حظر تلقائي(?:\s+(\S+))?", text)
    if add_m:
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        target_str = add_m.group(1)
        tid, tmention = await _resolve_target(c, m, target_str)
        if not tid:
            return await m.reply(
                f"╔══ {k} ══╗\n"
                f"┃ ردّ على العضو أو اكتب: حظر تلقائي @username\n"
                f"╚══════════╝"
            )
        if is_pre(tid, cid) or is_owner(tid, cid):
            return await m.reply(f"‼️ {k} لا يمكن إضافة مدير أو مميز للقائمة السوداء")
        await ar.sadd(_bl_key(cid), str(tid))
        # طرده مباشرة إذا كان في المجموعة
        try:
            await c.ban_chat_member(cid, tid)
            await c.unban_chat_member(cid, tid)
        except Exception:
            pass
        return await m.reply(
            f"╔══ {k} ══╗\n"
            f"┃ تم إضافة {tmention} للقائمة السوداء 🚫\n"
            f"┃ سيُطرد فور محاولة الدخول\n"
            f"╚══════════╝"
        )

    # ── رفع حظر تلقائي ──
    rem_m = re.fullmatch(r"رفع حظر تلقائي(?:\s+(\S+))?", text)
    if rem_m:
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        target_str = rem_m.group(1)
        tid, tmention = await _resolve_target(c, m, target_str)
        if not tid:
            return await m.reply(
                f"╔══ {k} ══╗\n"
                f"┃ ردّ على العضو أو اكتب: رفع حظر تلقائي @username\n"
                f"╚══════════╝"
            )
        await ar.srem(_bl_key(cid), str(tid))
        return await m.reply(
            f"╔══ {k} ══╗\n"
            f"┃ تم إزالة {tmention} من القائمة السوداء ✅\n"
            f"╚══════════╝"
        )

    # ── عرض القائمة السوداء ──
    if text == "القائمة السوداء":
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        members = cached_smembers(_bl_key(cid))
        if not members:
            return await m.reply(f"✨ {k} القائمة السوداء فارغة")
        lines = [f"╔══ {k} ══╗", f"┃ 🚫 القائمة السوداء ({len(members)} عضو):"]
        for mid in list(members)[:50]:
            try:
                u = await c.get_users(int(mid))
                lines.append(f"┃ • {u.mention} (`{mid}`)")
            except Exception:
                lines.append(f"┃ • ID: `{mid}`")
        lines.append("╚══════════╝")
        return await m.reply("\n".join(lines))


# ─────────────────────────────────────────────────────────────────────────
# فحص القائمة السوداء عند دخول عضو
# ─────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.new_chat_members, group=48)
async def blacklist_join_check(c: Client, m: Message):
    cid = m.chat.id
    if not group_enabled(cid):
        return

    bl = cached_smembers(_bl_key(cid))
    if not bl:
        return

    k = botkey()
    for member in m.new_chat_members:
        if str(member.id) in bl:
            try:
                await c.ban_chat_member(cid, member.id)
                await c.send_message(
                    cid,
                    f"╔══ {k} ══╗\n"
                    f"┃ 🚫 {member.mention} في القائمة السوداء!\n"
                    f"┃ تم طرده تلقائياً\n"
                    f"╚══════════╝"
                )
            except Exception:
                pass
