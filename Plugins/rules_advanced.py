"""
نظام القوانين المتقدم (Rules Advanced)
────────────────────────────────────────
ملاحظة: الأوامر الأساسية (وضع قوانين / مسح القوانين / القوانين)
موجودة في welcome.py — هذا الملف يضيف ميزات متقدمة:

  القوانين رقم [رقم]    → عرض قانون محدد
  اضف قانون [نص]        → إضافة قانون جديد للقائمة (مدير+)
  حذف قانون [رقم]       → حذف قانون بالرقم (مدير+)
  قوانين المجموعة       → عرض القوانين بشكل مرتب ومرقّم
────────────────────────────────────────
"""

import re

from pyrogram import Client, filters
from pyrogram.types import Message

from config import r, ar, DEV_ID, botkey
from helpers.ranks import is_mod
from helpers.utils import group_enabled, resolve_text


def _rules_list_key(cid: int) -> str:
    return f"{cid}:rules_list:{DEV_ID}"


@Client.on_message(filters.text & filters.group, group=51)
async def advanced_rules_commands(c: Client, m: Message):
    if not m.from_user:
        return
    cid, uid = m.chat.id, m.from_user.id
    if not group_enabled(cid):
        return
    text = resolve_text(m.text, cid)
    k = botkey()

    # ── اضف قانون [نص] ──
    add_m = re.fullmatch(r"اضف قانون\s+(.+)", text, re.DOTALL)
    if add_m:
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        rule_text = add_m.group(1).strip()[:300]
        await ar.rpush(_rules_list_key(cid), rule_text)
        count = await ar.llen(_rules_list_key(cid))
        return await m.reply(
            f"╔══ {k} ══╗\n"
            f"┃ تم إضافة القانون رقم {count} ✅\n"
            f"╚══════════╝"
        )

    # ── حذف قانون [رقم] ──
    del_m = re.fullmatch(r"حذف قانون\s+(\d+)", text)
    if del_m:
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        idx = int(del_m.group(1)) - 1
        rules = await ar.lrange(_rules_list_key(cid), 0, -1)
        if idx < 0 or idx >= len(rules):
            return await m.reply(f"‼️ {k} رقم القانون غير صحيح")
        # نحذف بتعيين قيمة مؤقتة ثم إزالتها
        await ar.lset(_rules_list_key(cid), idx, "__DELETED__")
        await ar.lrem(_rules_list_key(cid), 1, "__DELETED__")
        return await m.reply(
            f"╔══ {k} ══╗\n┃ تم حذف القانون رقم {idx + 1} 🗑️\n╚══════════╝"
        )

    # ── قوانين المجموعة (مرقّمة) ──
    if text == "قوانين المجموعة":
        rules = await ar.lrange(_rules_list_key(cid), 0, -1)
        if not rules:
            # fallback على القوانين المخزنة في welcome.py
            fallback = await ar.get(f"{cid}:CustomRules:{DEV_ID}")
            if fallback:
                return await m.reply(
                    f"╔══ {k} ══╗\n"
                    f"┃ 📜 قوانين المجموعة:\n"
                    f"┃ ─────────\n"
                    f"{fallback}\n"
                    f"╚══════════╝",
                    disable_web_page_preview=True
                )
            return await m.reply(f"✨ {k} لم تُضف قوانين بعد")
        lines = [f"╔══ {k} ══╗", f"┃ 📜 قوانين المجموعة:"]
        for i, rule in enumerate(rules, 1):
            lines.append(f"┃ {i}. {rule}")
        lines.append("╚══════════╝")
        return await m.reply("\n".join(lines), disable_web_page_preview=True)

    # ── القوانين رقم [رقم] ──
    rule_m = re.fullmatch(r"القوانين رقم\s+(\d+)", text)
    if rule_m:
        idx = int(rule_m.group(1)) - 1
        rules = await ar.lrange(_rules_list_key(cid), 0, -1)
        if idx < 0 or idx >= len(rules):
            return await m.reply(f"‼️ {k} رقم القانون غير صحيح")
        return await m.reply(
            f"╔══ {k} ══╗\n"
            f"┃ 📜 القانون رقم {idx + 1}:\n"
            f"┃ {rules[idx]}\n"
            f"╚══════════╝"
        )

    # ── مسح كل القوانين المضافة ──
    if text == "مسح جميع القوانين":
        if not is_mod(uid, cid):
            return await m.reply(f"‼️ {k} هذا الأمر للمدير وفوق فقط")
        await ar.delete(_rules_list_key(cid))
        return await m.reply(
            f"╔══ {k} ══╗\n┃ تم مسح جميع القوانين 🗑️\n╚══════════╝"
        )
