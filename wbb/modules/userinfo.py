from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from wbb import app, db
from wbb.utils.dbfunctions import (
    get_name_history,
    get_user_groups,
    get_join_leave_history,
    get_avg_messages_per_day,
    get_user_global,
    int_to_alpha,
    _trust_badge,
    _score_bar,
    _ts,
    _days_ago,
    record_name_if_changed,
    update_user_group,
    record_join_leave,
)

warnsdb  = db.warns
karmadb  = db.karma
gbansdb  = db.gban
namehistorydb = db.name_history

__MODULE__ = "Userinfo"
__HELP__ = """
/userinfo - Show info about a user.
Reply to a message or pass @username / user ID.
Works in groups and DMs.
"""


@app.on_message(filters.command("userinfo"))
async def userinfo_command(_, message: Message):
    is_dm   = message.chat.type.value == "private"
    chat_id = message.chat.id

    target_id    = None
    target_name  = None
    target_uname = None

    if message.reply_to_message and message.reply_to_message.from_user:
        u = message.reply_to_message.from_user
        target_id    = u.id
        target_name  = u.full_name
        target_uname = f"@{u.username}" if u.username else None
    elif len(message.command) > 1:
        raw = message.command[1].lstrip("@")
        try:
            target_id = int(raw)
        except ValueError:
            doc = await namehistorydb.find_one({"history.username": f"@{raw}"})
            if doc:
                target_id = doc["user_id"]
                last = doc["history"][-1]
                target_name  = last.get("full_name")
                target_uname = last.get("username")
            else:
                await message.reply(f"No data found for @{raw}.")
                return
    else:
        u = message.from_user
        target_id    = u.id
        target_name  = u.full_name
        target_uname = f"@{u.username}" if u.username else None

    if not target_id:
        await message.reply("Reply to a message or pass @username / user ID.")
        return

    if not is_dm:
        karma_key = await int_to_alpha(target_id)
        karmas    = await karmadb.find_one({"chat_id": chat_id})
        karma_val = 0
        if karmas and karma_key in karmas.get("karma", {}):
            karma_val = karmas["karma"][karma_key].get("karma", 0)

        warn_doc = await warnsdb.find_one({"chat_id": chat_id})
        warn_val = 0
        if warn_doc:
            for w in warn_doc.get("warns", {}).values():
                if w.get("user_id") == target_id:
                    warn_val = w.get("warns", 0)
                    break

        is_gbanned = bool(await gbansdb.find_one({"user_id": target_id}))

        jl      = await get_join_leave_history(target_id, chat_id)
        avg_msg = await get_avg_messages_per_day(target_id, chat_id)

        groups = await get_user_groups(target_id)
        grp    = next((g for g in groups if g["chat_id"] == chat_id), None)
        first_seen_here = grp["first_seen"] if grp else None
        last_seen_here  = grp["last_seen"]  if grp else None
        msg_count_here  = grp["msg_count"]  if grp else 0

        badge = _trust_badge(karma_val)
        bar   = _score_bar(karma_val)
        name  = target_name or "Unknown"
        uname = target_uname or "—"

        timeline_lines = []
        visit = 0
        for ev in jl:
            dt = _ts(ev["ts"])
            if ev["event_type"] == "join":
                visit += 1
                timeline_lines.append(f"  Joined  — `{dt}`  _(visit #{visit})_")
            else:
                timeline_lines.append(f"  Left    — `{dt}`")
        timeline = "\n".join(timeline_lines) if timeline_lines else "  _No join/leave recorded_"

        gban_line = "\nGlobally banned: `Yes`" if is_gbanned else ""

        text = (
            f"**{name}**\n"
            f"{uname}  |  `{target_id}`\n\n"
            f"Trust: **{badge}**\n"
            f"Karma: `{karma_val}` `[{bar}]`\n\n"
            f"**Group History**\n"
            f"{timeline}\n\n"
            f"**Activity in this group**\n"
            f"Messages: `{msg_count_here}`\n"
            f"Avg/day:  `{avg_msg}` messages\n"
            f"First seen: `{_ts(first_seen_here)}`\n"
            f"Last seen:  `{_days_ago(last_seen_here)}`\n\n"
            f"**Moderation**\n"
            f"Warns: `{warn_val}`"
            f"{gban_line}"
        )

        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("Full Log", callback_data=f"uinfo_log:{chat_id}:{target_id}"),
        ]])
        await message.reply(text, reply_markup=kb)

    else:
        global_data = await get_user_global(target_id)
        name_hist   = await get_name_history(target_id, limit=8)
        groups      = await get_user_groups(target_id)

        name  = global_data["full_name"]  or target_name  or "Unknown"
        uname = global_data["username"]   or target_uname or "—"

        if name_hist:
            hist_lines = []
            for i, h in enumerate(name_hist):
                u  = h.get("username") or "—"
                fn = h["full_name"]
                dt = _ts(h["changed_at"])
                marker = "current" if i == 0 else "  prev"
                hist_lines.append(f"{marker}: `{fn}` ({u}) — _{dt}_")
            hist_text = "\n".join(hist_lines)
        else:
            hist_text = "_No history recorded_"

        if groups:
            group_lines = []
            for g in groups[:10]:
                title = g.get("chat_title") or f"`{g['chat_id']}`"
                fs   = _ts(g["first_seen"])
                ls   = _days_ago(g["last_seen"])
                msgs = g.get("msg_count", 0)
                group_lines.append(f"- **{title}**\n  First: `{fs}` · Last: `{ls}` · Msgs: `{msgs}`")
            groups_text = "\n".join(group_lines)
            if len(groups) > 10:
                groups_text += f"\n_...and {len(groups) - 10} more_"
        else:
            groups_text = "_No common groups_"

        score = global_data["total_karma"]
        badge = _trust_badge(score)
        bar   = _score_bar(score)
        gban_line = "\nGlobally banned: `Yes`" if global_data["is_gbanned"] else ""

        text = (
            f"**{name}**\n"
            f"{uname}  |  `{target_id}`\n\n"
            f"First seen: `{_ts(global_data['first_seen'])}`\n"
            f"Last seen:  `{_days_ago(global_data['last_seen'])}`\n\n"
            f"**Name & Username History**\n"
            f"{hist_text}\n\n"
            f"**Common Groups with this bot** ({global_data['groups_count']})\n"
            f"{groups_text}\n\n"
            f"Trust: **{badge}**\n"
            f"Global Karma: `{score}` `[{bar}]`\n\n"
            f"**Global Stats**\n"
            f"Total messages: `{global_data['total_msgs']}`\n"
            f"Total warns:    `{global_data['total_warns']}`"
            f"{gban_line}"
        )
        await message.reply(text)


@app.on_message(filters.group & ~filters.service, group=98)
async def track_message(_, message: Message):
    if not message.from_user or message.from_user.is_bot:
        return
    u = message.from_user
    uname = f"@{u.username}" if u.username else None
    await record_name_if_changed(u.id, uname, u.full_name)
    await update_user_group(u.id, message.chat.id, message.chat.title)


@app.on_message(filters.new_chat_members, group=98)
async def track_join(_, message: Message):
    for member in message.new_chat_members:
        if member.is_bot:
            continue
        uname = f"@{member.username}" if member.username else None
        await record_name_if_changed(member.id, uname, member.full_name)
        await update_user_group(member.id, message.chat.id, message.chat.title)
        await record_join_leave(member.id, message.chat.id, "join")


@app.on_message(filters.left_chat_member, group=98)
async def track_leave(_, message: Message):
    member = message.left_chat_member
    if not member or member.is_bot:
        return
    uname = f"@{member.username}" if member.username else None
    await record_name_if_changed(member.id, uname, member.full_name)
    await record_join_leave(member.id, message.chat.id, "leave")