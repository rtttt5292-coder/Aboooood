"""
الهمسة - نظام الرسائل السرية عبر inline
الاستخدام: @البوت همستك @username
"""
import random
import string
import pytz
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import (
    InlineQuery, InlineQueryResultArticle, InputTextMessageContent,
    InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery,
)

from config import r, ar


def _gen_id(n=8) -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=n))


def _time_now(tz_name="Asia/Riyadh") -> str:
    tz  = pytz.timezone(tz_name)
    now = datetime.now(tz)
    return now.strftime("%I:%M %p")


def _is_whisper_query(q: str) -> bool:
    """
    تحقق دقيق: همسة صحيحة تعني:
    - لا تحتوي على #SOUND أو #AUDIO أو #VOICE أو SOUND
    - تحتوي على @ بعد نص
    - الجزء بعد @ لا يحتوي على مسافة (username واحد)
    """
    if not q:
        return False
    for marker in ("SOUND", "#AUDIO", "#VOICE", "#MUSIC"):
        if marker in q:
            return False
    if "@" not in q:
        return False
    parts = q.split("@", 1)
    msg_text = parts[0].strip()
    target   = parts[1].strip()
    # لا بد من وجود نص قبل @ وكلمة واحدة بعده
    if not msg_text or not target or " " in target:
        return False
    return True


# ─────────────── inline query — همسة ────────────────────────────────────

@Client.on_inline_query(group=0)
async def inline_router(c: Client, query: InlineQuery):
    """
    نقطة دخول وحيدة لكل inline queries.
    نوجّه هنا بدلاً من handlers متعارضة.
    """
    q = query.query.strip()

    if _is_whisper_query(q):
        await _handle_whisper(c, query, q)
    else:
        await _handle_help(c, query, q)


async def _handle_whisper(c: Client, query: InlineQuery, raw: str):
    parts    = raw.split("@", 1)
    msg_text = parts[0].strip()
    target_raw = parts[1].strip()

    sender_id = query.from_user.id

    if target_raw.lower() == "all":
        target_id = "all"
        display   = "الجميع 🎊"
        label     = "🎊 مفاجأة للجميع"
    else:
        try:
            u         = await c.get_users(target_raw)
            target_id = u.id
            display   = u.first_name
            label     = f"همسة لـ {display}"
        except Exception:
            await query.answer(
                results=[],
                switch_pm_text="❌ يوزر غير موجود",
                switch_pm_parameter="whisper_help",
                cache_time=1,
            )
            return

    wid = _gen_id()
    await ar.set(f"w:{wid}", f"{sender_id}+{target_id}&msg={msg_text}", ex=86400)

    if target_id == "all":
        card_text = "🎊 همسة للجميع — اضغط لعرضها"
    else:
        card_text = f"🔒 همسة سرية لـ {display} — فقط هو يقدر يشوفها 🕵️"

    markup  = InlineKeyboardMarkup([[
        InlineKeyboardButton("📪 عرض الهمسة", callback_data=f"w:{wid}")
    ]])
    timenow = "🕐 " + _time_now()

    await query.answer(
        switch_pm_text="• كيف أستخدم الهمسة؟",
        switch_pm_parameter="whisper_help",
        results=[
            InlineQueryResultArticle(
                title=label,
                description=timenow,
                input_message_content=InputTextMessageContent(
                    card_text, parse_mode=ParseMode.MARKDOWN
                ),
                reply_markup=markup,
                thumb_url="https://i.imgur.com/7UaXuJt.png",
                thumb_width=64,
                thumb_height=64,
            )
        ],
        cache_time=1,
    )


async def _handle_help(c: Client, query: InlineQuery, q: str):
    """رد افتراضي — يظهر فقط للـ queries التي ليست همسة ولا ساوند كلاود"""
    # queries الساوند كلاود يعالجها downloader — نتجاهلها هنا
    for marker in ("SOUND", "#AUDIO", "#VOICE"):
        if marker in q:
            return

    await query.answer(
        switch_pm_text="• اكتب همستك + @username",
        switch_pm_parameter="whisper_help",
        results=[
            InlineQueryResultArticle(
                title="🔒 طريقة الاستخدام",
                description="@البوت  همستك  @username",
                input_message_content=InputTextMessageContent(
                    "`@البوت  همستك  @username`",
                    parse_mode=ParseMode.MARKDOWN,
                ),
                thumb_url="https://i.imgur.com/7UaXuJt.png",
                thumb_width=64,
                thumb_height=64,
            )
        ],
        cache_time=60,
    )


# ─────────────── callback: عرض الهمسة ───────────────────────────────────

@Client.on_callback_query(filters.regex(r"^w:"))
async def show_whisper(c: Client, cb: CallbackQuery):
    wid  = cb.data.split(":", 1)[1]
    data = await ar.get(f"w:{wid}")
    if not data:
        return await cb.answer("⏰ انتهت صلاحية الهمسة", show_alert=True)

    ids_part, msg_part = data.split("&msg=", 1)
    sender_id, target_id = ids_part.split("+", 1)

    viewer = cb.from_user.id

    if target_id == "all":
        await ar.delete(f"w:{wid}")
        return await cb.answer(f"🎊 {msg_part[:200]}", show_alert=True)

    if str(viewer) == sender_id or str(viewer) == target_id:
        if str(viewer) == target_id:
            await ar.delete(f"w:{wid}")
            try:
                await cb.message.edit_reply_markup(
                    InlineKeyboardMarkup([[
                        InlineKeyboardButton("📭 تم فتح الهمسة", callback_data=f"wx:{wid}")
                    ]])
                )
            except Exception:
                pass
        return await cb.answer(f"🔓 {msg_part[:200]}", show_alert=True)

    return await cb.answer("🔒 هذه الهمسة مو لك", show_alert=True)


@Client.on_callback_query(filters.regex(r"^wx:"))
async def whisper_opened_noop(c: Client, cb: CallbackQuery):
    """زر 'تم فتح الهمسة' بعد قراءتها — لا يفعل شيء"""
    await cb.answer("📭 تمت القراءة", show_alert=False)
