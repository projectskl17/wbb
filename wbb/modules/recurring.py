import re
import logging
from pyrogram import filters, enums
from pyrogram.enums import ChatMemberStatus, ChatType
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from wbb import app
from wbb import db

logger = logging.getLogger(__name__)

recurringdb = db.recurring
rec_linksdb = db.recurring_links

scheduler = AsyncIOScheduler()
scheduler.start()

MIN_INTERVAL_SECONDS = 60

_pending: dict[int, dict] = {}
_connecting: set[int] = set()


async def _get(chat_id: int) -> dict:
    doc = await recurringdb.find_one({"chat_id": chat_id})
    return doc or {}


async def _set(chat_id: int, updates: dict):
    await recurringdb.update_one(
        {"chat_id": chat_id}, {"$set": updates}, upsert=True
    )


async def _init(chat_id: int):
    await recurringdb.update_one(
        {"chat_id": chat_id},
        {"$setOnInsert": {
            "chat_id": chat_id,
            "active": False,
            "text": "",
            "media": None,
            "buttons": [],
            "interval": 3600,
            "pin": False,
            "delete_prev": False,
            "last_msg_id": None,
        }},
        upsert=True,
    )

async def _link_add(user_id: int, chat_id: int):
    await rec_linksdb.update_one(
        {"user_id": user_id},
        {"$addToSet": {"chats": chat_id}},
        upsert=True,
    )


async def _link_remove(user_id: int, chat_id: int):
    await rec_linksdb.update_one(
        {"user_id": user_id},
        {"$pull": {"chats": chat_id}},
    )


async def _link_get(user_id: int) -> list[int]:
    doc = await rec_linksdb.find_one({"user_id": user_id})
    return doc.get("chats", []) if doc else []


def _parse_interval(raw: str):
    raw = raw.strip().lower()
    try:
        if raw.endswith("s"):
            return int(raw[:-1])
        if raw.endswith("m"):
            return int(raw[:-1]) * 60
        if raw.endswith("h"):
            return int(raw[:-1]) * 3600
        return int(raw)
    except ValueError:
        return None


def _build_buttons(data: dict):
    rows = data.get("buttons", [])
    if not rows:
        return None
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(b["text"], url=b["url"]) for b in row] for row in rows]
    )


def _fmt_interval(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    return f"{seconds // 3600}h"

async def _is_admin(client, chat_id: int, user_id: int) -> bool:
    try:
        m = await client.get_chat_member(chat_id, user_id)
        return m.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception:
        return False


async def _bot_is_admin(client, chat_id: int) -> bool:
    try:
        me = await client.get_me()
        m = await client.get_chat_member(chat_id, me.id)
        return m.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception:
        return False

def _remove_job(chat_id: int):
    try:
        scheduler.remove_job(str(chat_id))
    except Exception:
        pass


def _add_job(client, chat_id: int, interval: int):
    async def _job():
        data = await _get(chat_id)
        if not data or not data.get("active"):
            return

        if data.get("delete_prev") and data.get("last_msg_id"):
            try:
                await client.delete_messages(chat_id, data["last_msg_id"])
            except Exception:
                pass

        text   = data.get("text") or "📢 Recurring message"
        media  = data.get("media")
        markup = _build_buttons(data)

        try:
            if media:
                send_fn = {
                    "photo":    client.send_photo,
                    "video":    client.send_video,
                    "document": client.send_document,
                }.get(media["type"])
                if send_fn:
                    sent = await send_fn(
                        chat_id, media["file_id"],
                        caption=text, reply_markup=markup,
                        disable_notification=True,
                        parse_mode=enums.ParseMode.HTML,
                    )
                else:
                    sent = await client.send_message(
                        chat_id, text, reply_markup=markup,
                        disable_notification=True,
                        parse_mode=enums.ParseMode.HTML,
                    )
            else:
                sent = await client.send_message(
                    chat_id, text, reply_markup=markup,
                    disable_notification=True,
                    parse_mode=enums.ParseMode.HTML,
                )

            if data.get("pin"):
                try:
                    await client.pin_chat_message(chat_id, sent.id, disable_notification=True)
                except Exception:
                    pass

            await _set(chat_id, {"last_msg_id": sent.id})

        except Exception as e:
            logger.error(f"[recurring] job error chat {chat_id}: {e}")

    _remove_job(chat_id)
    scheduler.add_job(
        _job, "interval", seconds=interval,
        id=str(chat_id), replace_existing=True,
    )


async def load_all_recurring_jobs(client):
    async for doc in recurringdb.find({"active": True}):
        _add_job(client, doc["chat_id"], doc.get("interval", 3600))

async def _main_menu(chat_id: int, chat_title: str, pm: bool = False) -> tuple[str, InlineKeyboardMarkup]:
    data    = await _get(chat_id)
    active  = data.get("active", False)
    pin     = data.get("pin", False)
    delprev = data.get("delete_prev", False)
    ivl     = _fmt_interval(data.get("interval", 3600))
    suffix  = f":{chat_id}"

    status_icon = "🟢" if active else "🔴"
    text = (
        f"<b>🔁 Recurring — {chat_title}</b>\n\n"
        f"Status: {status_icon} {'Active' if active else 'Inactive'}\n"
        f"Interval: <code>{ivl}</code>\n"
        f"Text: {'✅' if data.get('text') else '❌'}  "
        f"Media: {'✅' if data.get('media') else '❌'}  "
        f"Buttons: {'✅' if data.get('buttons') else '❌'}\n"
        f"Pin: {'✅' if pin else '❌'}  "
        f"Auto-delete prev: {'✅' if delprev else '❌'}"
    )

    back_row = (
        [[InlineKeyboardButton("🔙 My Chats", callback_data="rec_mychats")]]
        if pm else
        [[InlineKeyboardButton("❌ Close", callback_data=f"rec_close{suffix}")]]
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "🚫 Deactivate" if active else "✅ Activate",
            callback_data=f"rec_toggle{suffix}",
        )],
        [
            InlineKeyboardButton("📝 Text",     callback_data=f"rec_settext{suffix}"),
            InlineKeyboardButton("🖼 Media",    callback_data=f"rec_setmedia{suffix}"),
        ],
        [
            InlineKeyboardButton("🔗 Buttons",  callback_data=f"rec_setbtns{suffix}"),
            InlineKeyboardButton("⏱ Interval",  callback_data=f"rec_setfreq{suffix}"),
        ],
        [
            InlineKeyboardButton(
                f"📌 Pin: {'ON' if pin else 'OFF'}",
                callback_data=f"rec_pin{suffix}",
            ),
            InlineKeyboardButton(
                f"🗑 Auto-Del: {'ON' if delprev else 'OFF'}",
                callback_data=f"rec_del{suffix}",
            ),
        ],
        [
            InlineKeyboardButton("👁 Preview",  callback_data=f"rec_preview{suffix}"),
            InlineKeyboardButton("🔄 Reset",    callback_data=f"rec_reset{suffix}"),
        ],
        *back_row,
    ])
    return text, keyboard


async def _mychats_menu(client, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    chat_ids = await _link_get(user_id)
    if not chat_ids:
        return (
            "<b>🔁 Recurring Messages</b>\n\nNo chats connected yet.",
            InlineKeyboardMarkup([[
                InlineKeyboardButton("➕ Connect a Chat", callback_data="rec_connect"),
            ]]),
        )

    rows = []
    for cid in chat_ids:
        try:
            chat  = await client.get_chat(cid)
            label = chat.title or str(cid)
        except Exception:
            label = str(cid)
        doc  = await _get(cid)
        icon = "🟢" if doc.get("active") else "🔴"
        rows.append([
            InlineKeyboardButton(f"{icon} {label}", callback_data=f"rec_open:{cid}"),
            InlineKeyboardButton("🗑", callback_data=f"rec_unlink:{cid}"),
        ])

    rows.append([InlineKeyboardButton("➕ Connect a Chat", callback_data="rec_connect")])

    return (
        "<b>🔁 Recurring — My Chats</b>\n\nSelect a chat to configure:",
        InlineKeyboardMarkup(rows),
    )

@app.on_message(filters.command("recurring") & filters.group)
async def recurring_group(client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply("<b>Admins only.</b>", parse_mode=enums.ParseMode.HTML)
    await _init(message.chat.id)
    try:
        title = (await client.get_chat(message.chat.id)).title or str(message.chat.id)
    except Exception:
        title = str(message.chat.id)
    text, kb = await _main_menu(message.chat.id, title, pm=False)
    await message.reply(text, reply_markup=kb, parse_mode=enums.ParseMode.HTML)


@app.on_message(filters.command("recurring") & filters.private)
async def recurring_pm(client, message: Message):
    text, kb = await _mychats_menu(client, message.from_user.id)
    await message.reply(text, reply_markup=kb, parse_mode=enums.ParseMode.HTML)


@app.on_callback_query(filters.regex(r"^rec_"))
async def recurring_callbacks(client, cb: CallbackQuery):
    raw     = cb.data
    user_id = cb.from_user.id
    is_pm   = cb.message.chat.type == ChatType.PRIVATE

    if raw == "rec_mychats":
        text, kb = await _mychats_menu(client, user_id)
        return await cb.edit_message_text(text, reply_markup=kb, parse_mode=enums.ParseMode.HTML)

    if raw == "rec_connect":
        _connecting.add(user_id)
        return await cb.edit_message_text(
            "<b>➕ Connect a Chat</b>\n\n"
            "Send me the <b>group/channel ID</b> or <b>forward any message</b> from it.\n\n"
            "The bot must already be an <b>admin</b> in that chat.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="rec_mychats"),
            ]]),
            parse_mode=enums.ParseMode.HTML,
        )

    if ":" not in raw:
        return await cb.answer("Unknown action.")

    cmd_part, chat_id_str = raw.split(":", 1)
    try:
        chat_id = int(chat_id_str)
    except ValueError:
        return await cb.answer("Bad data.", show_alert=True)

    if cmd_part == "rec_unlink":
        await _link_remove(user_id, chat_id)
        await cb.answer("Disconnected.", show_alert=True)
        text, kb = await _mychats_menu(client, user_id)
        return await cb.edit_message_text(text, reply_markup=kb, parse_mode=enums.ParseMode.HTML)

    if cmd_part == "rec_open":
        if not await _is_admin(client, chat_id, user_id):
            return await cb.answer("You're no longer admin there.", show_alert=True)
        await _init(chat_id)
        try:
            title = (await client.get_chat(chat_id)).title or str(chat_id)
        except Exception:
            title = str(chat_id)
        text, kb = await _main_menu(chat_id, title, pm=True)
        return await cb.edit_message_text(text, reply_markup=kb, parse_mode=enums.ParseMode.HTML)

    if not await _is_admin(client, chat_id, user_id):
        return await cb.answer("Admins only.", show_alert=True)

    try:
        title = (await client.get_chat(chat_id)).title or str(chat_id)
    except Exception:
        title = str(chat_id)

    # ── local helpers ─────────────────────────────────────────────────────────
    async def refresh_menu():
        t, kb = await _main_menu(chat_id, title, pm=is_pm)
        await cb.edit_message_text(t, reply_markup=kb, parse_mode=enums.ParseMode.HTML)

    async def ask_input(field: str, prompt: str):
        _pending[user_id] = {
            "chat_id":     chat_id,
            "field":       field,
            "menu_msg_id": cb.message.id,
            "pm":          is_pm,
        }
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Back", callback_data=f"rec_back:{chat_id}"),
        ]])
        await cb.edit_message_text(
            f"<b>{prompt}</b>\n\n"
            + ("Send your reply here in PM." if is_pm else "Send your reply in the group."),
            reply_markup=kb,
            parse_mode=enums.ParseMode.HTML,
        )

    if cmd_part == "rec_toggle":
        doc       = await _get(chat_id)
        new_state = not doc.get("active", False)
        await _set(chat_id, {"active": new_state})
        if new_state:
            _add_job(client, chat_id, doc.get("interval", 3600))
            await cb.answer("✅ Activated!", show_alert=True)
        else:
            _remove_job(chat_id)
            await cb.answer("🚫 Deactivated!", show_alert=True)
        await refresh_menu()

    elif cmd_part == "rec_pin":
        doc = await _get(chat_id)
        await _set(chat_id, {"pin": not doc.get("pin", False)})
        await refresh_menu()

    elif cmd_part == "rec_del":
        doc = await _get(chat_id)
        await _set(chat_id, {"delete_prev": not doc.get("delete_prev", False)})
        await refresh_menu()

    elif cmd_part == "rec_settext":
        await ask_input("text", "📝 Send the new recurring message text.\nHTML formatting supported.")

    elif cmd_part == "rec_setmedia":
        await ask_input("media", "🖼 Send a photo, video, or document.")

    elif cmd_part == "rec_setbtns":
        await ask_input(
            "buttons",
            "🔗 Send buttons in format:\n"
            "<code>Button Label - https://example.com</code>\n\n"
            "One button per line. Empty line = new row.",
        )

    elif cmd_part == "rec_setfreq":
        await ask_input(
            "freq",
            f"⏱ Send interval. Min <code>{MIN_INTERVAL_SECONDS}s</code>.\n"
            "Examples: <code>30m</code>, <code>2h</code>, <code>90s</code>",
        )

    elif cmd_part == "rec_preview":
        doc    = await _get(chat_id)
        text   = doc.get("text") or "📢 Recurring message"
        media  = doc.get("media")
        markup = _build_buttons(doc)
        try:
            if media:
                send_fn = {
                    "photo":    client.send_photo,
                    "video":    client.send_video,
                    "document": client.send_document,
                }.get(media["type"])
                if send_fn:
                    await send_fn(user_id, media["file_id"], caption=text,
                                  reply_markup=markup, parse_mode=enums.ParseMode.HTML)
                else:
                    await client.send_message(user_id, text, reply_markup=markup,
                                              parse_mode=enums.ParseMode.HTML)
            else:
                await client.send_message(user_id, text, reply_markup=markup,
                                          parse_mode=enums.ParseMode.HTML)
            await cb.answer("Preview sent to your PM!", show_alert=True)
        except Exception as e:
            logger.error(f"[recurring] preview error: {e}")
            await cb.answer("Failed — start the bot in PM first.", show_alert=True)

    elif cmd_part == "rec_reset":
        await recurringdb.delete_one({"chat_id": chat_id})
        _remove_job(chat_id)
        await _init(chat_id)
        await cb.answer("Reset done.", show_alert=True)
        await refresh_menu()

    elif cmd_part == "rec_back":
        _pending.pop(user_id, None)
        await refresh_menu()

    elif cmd_part == "rec_close":
        await cb.message.delete()

    else:
        await cb.answer("Unknown action.")


@app.on_message(filters.private & ~filters.bot)
async def pm_handler(client, message: Message):
    user_id = message.from_user.id

    if user_id in _connecting:
        chat_id = None

        if message.forward_origin:
            try:
                fwd_chat = getattr(message.forward_origin, "chat", None)
                if fwd_chat:
                    chat_id = fwd_chat.id
            except Exception:
                pass

        if chat_id is None and message.text:
            raw = message.text.strip()
            try:
                chat_id = int(raw)
            except ValueError:
                try:
                    chat_id = (await client.get_chat(raw)).id
                except Exception:
                    pass

        if chat_id is None:
            return await message.reply(
                "❌ Couldn't resolve. Send a numeric ID or forward a message from the chat.",
                parse_mode=enums.ParseMode.HTML,
            )

        if not await _bot_is_admin(client, chat_id):
            return await message.reply(
                "❌ Bot is not an admin in that chat. Add the bot as admin first.",
                parse_mode=enums.ParseMode.HTML,
            )

        if not await _is_admin(client, chat_id, user_id):
            return await message.reply(
                "❌ You are not an admin in that chat.",
                parse_mode=enums.ParseMode.HTML,
            )

        _connecting.discard(user_id)
        await _init(chat_id)
        await _link_add(user_id, chat_id)

        try:
            title = (await client.get_chat(chat_id)).title or str(chat_id)
        except Exception:
            title = str(chat_id)

        return await message.reply(
            f"✅ <b>{title}</b> connected!\n\nChoose what to do:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⚙️ Configure", callback_data=f"rec_open:{chat_id}"),
                InlineKeyboardButton("🔙 My Chats",  callback_data="rec_mychats"),
            ]]),
            parse_mode=enums.ParseMode.HTML,
        )

    state = _pending.get(user_id)
    if not state or not state.get("pm"):
        return

    chat_id     = state["chat_id"]
    field       = state["field"]
    menu_msg_id = state["menu_msg_id"]
    _pending.pop(user_id, None)

    try:
        title = (await client.get_chat(chat_id)).title or str(chat_id)
    except Exception:
        title = str(chat_id)

    error_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 Back", callback_data=f"rec_back:{chat_id}"),
    ]])

    async def update_menu():
        t, kb = await _main_menu(chat_id, title, pm=True)
        await client.edit_message_text(
            user_id, menu_msg_id, t, reply_markup=kb, parse_mode=enums.ParseMode.HTML
        )

    if field == "text":
        if not message.text:
            return await client.edit_message_text(
                user_id, menu_msg_id, "❌ Send plain/HTML text.",
                reply_markup=error_kb, parse_mode=enums.ParseMode.HTML,
            )
        await _set(chat_id, {"text": message.text.html})
        await update_menu()

    elif field == "media":
        media = None
        if message.photo:
            media = {"type": "photo",    "file_id": message.photo.file_id}
        elif message.video:
            media = {"type": "video",    "file_id": message.video.file_id}
        elif message.document:
            media = {"type": "document", "file_id": message.document.file_id}
        if not media:
            return await client.edit_message_text(
                user_id, menu_msg_id, "❌ Send a photo, video, or document.",
                reply_markup=error_kb, parse_mode=enums.ParseMode.HTML,
            )
        await _set(chat_id, {"media": media})
        await update_menu()

    elif field == "buttons":
        if not message.text:
            return await client.edit_message_text(
                user_id, menu_msg_id, "❌ Send text in <code>Button - URL</code> format.",
                reply_markup=error_kb, parse_mode=enums.ParseMode.HTML,
            )
        btns = []
        for block in message.text.strip().split("\n\n"):
            row = []
            for line in block.strip().split("\n"):
                if " - " in line:
                    label, url = line.split(" - ", 1)
                    label, url = label.strip(), url.strip()
                    if label and re.match(r"^https?://", url):
                        row.append({"text": label, "url": url})
            if row:
                btns.append(row)
        await _set(chat_id, {"buttons": btns})
        await update_menu()

    elif field == "freq":
        if not message.text:
            return await client.edit_message_text(
                user_id, menu_msg_id, "❌ Send interval like <code>30m</code>.",
                reply_markup=error_kb, parse_mode=enums.ParseMode.HTML,
            )
        seconds = _parse_interval(message.text.strip())
        if not seconds or seconds < MIN_INTERVAL_SECONDS:
            return await client.edit_message_text(
                user_id, menu_msg_id,
                f"❌ Invalid or too short. Min is <code>{MIN_INTERVAL_SECONDS}s</code>.",
                reply_markup=error_kb, parse_mode=enums.ParseMode.HTML,
            )
        await _set(chat_id, {"interval": seconds})
        doc = await _get(chat_id)
        if doc.get("active"):
            _add_job(client, chat_id, seconds)
        await update_menu()

@app.on_message(
    filters.group & ~filters.bot
    & (filters.text | filters.photo | filters.video | filters.document)
)
async def group_input_handler(client, message: Message):
    user_id = message.from_user.id
    state   = _pending.get(user_id)
    if not state or state.get("pm"):
        return
    if message.chat.id != state["chat_id"]:
        return

    chat_id     = state["chat_id"]
    field       = state["field"]
    menu_msg_id = state["menu_msg_id"]
    _pending.pop(user_id, None)

    try:
        await message.delete()
    except Exception:
        pass

    try:
        title = (await client.get_chat(chat_id)).title or str(chat_id)
    except Exception:
        title = str(chat_id)

    error_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 Back", callback_data=f"rec_back:{chat_id}"),
    ]])

    async def update_menu():
        t, kb = await _main_menu(chat_id, title, pm=False)
        await client.edit_message_text(
            chat_id, menu_msg_id, t, reply_markup=kb, parse_mode=enums.ParseMode.HTML
        )

    if field == "text":
        if not message.text:
            return await client.edit_message_text(
                chat_id, menu_msg_id, "❌ Send plain/HTML text.",
                reply_markup=error_kb, parse_mode=enums.ParseMode.HTML,
            )
        await _set(chat_id, {"text": message.text.html})
        await update_menu()

    elif field == "media":
        media = None
        if message.photo:
            media = {"type": "photo",    "file_id": message.photo.file_id}
        elif message.video:
            media = {"type": "video",    "file_id": message.video.file_id}
        elif message.document:
            media = {"type": "document", "file_id": message.document.file_id}
        if not media:
            return await client.edit_message_text(
                chat_id, menu_msg_id, "❌ Send a photo, video, or document.",
                reply_markup=error_kb, parse_mode=enums.ParseMode.HTML,
            )
        await _set(chat_id, {"media": media})
        await update_menu()

    elif field == "buttons":
        if not message.text:
            return await client.edit_message_text(
                chat_id, menu_msg_id, "❌ Send text in <code>Button - URL</code> format.",
                reply_markup=error_kb, parse_mode=enums.ParseMode.HTML,
            )
        btns = []
        for block in message.text.strip().split("\n\n"):
            row = []
            for line in block.strip().split("\n"):
                if " - " in line:
                    label, url = line.split(" - ", 1)
                    label, url = label.strip(), url.strip()
                    if label and re.match(r"^https?://", url):
                        row.append({"text": label, "url": url})
            if row:
                btns.append(row)
        await _set(chat_id, {"buttons": btns})
        await update_menu()

    elif field == "freq":
        if not message.text:
            return await client.edit_message_text(
                chat_id, menu_msg_id, "❌ Send interval like <code>30m</code>.",
                reply_markup=error_kb, parse_mode=enums.ParseMode.HTML,
            )
        seconds = _parse_interval(message.text.strip())
        if not seconds or seconds < MIN_INTERVAL_SECONDS:
            return await client.edit_message_text(
                chat_id, menu_msg_id,
                f"❌ Too short. Min is <code>{MIN_INTERVAL_SECONDS}s</code>.",
                reply_markup=error_kb, parse_mode=enums.ParseMode.HTML,
            )
        await _set(chat_id, {"interval": seconds})
        doc = await _get(chat_id)
        if doc.get("active"):
            _add_job(client, chat_id, seconds)
        await update_menu()

__MODULE__ = "Recurring"
__HELP__ = """
<b>🔁 Recurring Messages</b>

Automatically send a message in a group/channel at a set interval.

<b>In a group (admin only):</b>
• /recurring — Open settings for that group

<b>In PM:</b>
• /recurring — See all your connected chats
• Tap <b>➕ Connect a Chat</b> → send a group/channel ID or forward any message from it
• Bot must be admin in the chat, and so must you

<b>Settings menu:</b>
• <b>Activate / Deactivate</b> — Start or stop the job
• <b>Set Text</b> — Message text (HTML supported)
• <b>Set Media</b> — Photo, video, or document
• <b>Set Buttons</b> — Inline URL buttons (<code>Label - URL</code>, empty line = new row)
• <b>Set Interval</b> — How often to send. Min 60s. E.g. <code>30m</code>, <code>2h</code>
• <b>Pin</b> — Pin each sent message
• <b>Auto-Delete</b> — Delete previous message before sending new one
• <b>Preview</b> — Send preview to your PM
• <b>Reset</b> — Wipe all settings for that chat
• <b>🗑 (chat list)</b> — Disconnect that chat from your account
"""