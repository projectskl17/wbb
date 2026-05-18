
import codecs
import pickle
from string import ascii_lowercase
from typing import Dict, List, Union

from wbb import db
import time
from datetime import datetime, timezone

# SOME THINGS ARE FUCKED UP HERE, LIKE TOGGLEABLES HAVE THEIR OWN COLLECTION
# (SHOULD FIX IT WITH SOMETHING LIKE TOGGLEDB), MOST OF THE CODE IS BAD AF
# AND NEEDS TO BE REWRITTEN, BUT I WON'T, AS IT WILL TAKE
# TOO MUCH TIME AND WILL BE BAD FOR ALREADY STORED DATA


notesdb = db.notes
filtersdb = db.filters
warnsdb = db.warns
karmadb = db.karma
chatsdb = db.chats
usersdb = db.users
gbansdb = db.gban
coupledb = db.couple
captchadb = db.captcha
solved_captcha_db = db.solved_captcha
captcha_cachedb = db.captcha_cache
antiservicedb = db.antiservice
pmpermitdb = db.pmpermit
welcomedb = db.welcome_text
blacklist_filtersdb = db.blacklistFilters
pipesdb = db.pipes
sudoersdb = db.sudoers
blacklist_chatdb = db.blacklistChat
restart_stagedb = db.restart_stage
flood_toggle_db = db.flood_toggle
rssdb = db.rss
rulesdb = db.rules
chatbotdb = db.chatbot

namehistorydb  = db.name_history
usergroupsdb   = db.user_groups
useractivitydb = db.user_activity
 
def obj_to_str(obj):
    if not obj:
        return False
    string = codecs.encode(pickle.dumps(obj), "base64").decode()
    return string


def str_to_obj(string: str):
    obj = pickle.loads(codecs.decode(string.encode(), "base64"))
    return obj


async def get_notes_count() -> dict:
    chats_count = 0
    notes_count = 0
    async for chat in notesdb.find({"chat_id": {"$exists": 1}}):
        notes_name = await get_note_names(chat["chat_id"])
        notes_count += len(notes_name)
        chats_count += 1
    return {"chats_count": chats_count, "notes_count": notes_count}


async def _get_notes(chat_id: int) -> Dict[str, int]:
    _notes = await notesdb.find_one({"chat_id": chat_id})
    if not _notes:
        return {}
    return _notes["notes"]


async def get_note_names(chat_id: int) -> List[str]:
    _notes = []
    for note in await _get_notes(chat_id):
        _notes.append(note)
    return _notes


async def get_note(chat_id: int, name: str) -> Union[bool, dict]:
    name = name.lower().strip()
    _notes = await _get_notes(chat_id)
    if name in _notes:
        return _notes[name]
    return False


async def save_note(chat_id: int, name: str, note: dict):
    name = name.lower().strip()
    _notes = await _get_notes(chat_id)
    _notes[name] = note

    await notesdb.update_one(
        {"chat_id": chat_id}, {"$set": {"notes": _notes}}, upsert=True
    )


async def delete_note(chat_id: int, name: str) -> bool:
    notesd = await _get_notes(chat_id)
    name = name.lower().strip()
    if name in notesd:
        del notesd[name]
        await notesdb.update_one(
            {"chat_id": chat_id},
            {"$set": {"notes": notesd}},
            upsert=True,
        )
        return True
    return False


async def deleteall_notes(chat_id: int):
    return await notesdb.delete_one({"chat_id": chat_id})


async def get_filters_count() -> dict:
    chats_count = 0
    filters_count = 0
    async for chat in filtersdb.find({"chat_id": {"$lt": 0}}):
        filters_name = await get_filters_names(chat["chat_id"])
        filters_count += len(filters_name)
        chats_count += 1
    return {
        "chats_count": chats_count,
        "filters_count": filters_count,
    }


async def _get_filters(chat_id: int) -> Dict[str, int]:
    _filters = await filtersdb.find_one({"chat_id": chat_id})
    if not _filters:
        return {}
    return _filters["filters"]


async def get_filters_names(chat_id: int) -> List[str]:
    _filters = []
    for _filter in await _get_filters(chat_id):
        _filters.append(_filter)
    return _filters


async def get_filter(chat_id: int, name: str) -> Union[bool, dict]:
    name = name.lower().strip()
    _filters = await _get_filters(chat_id)
    if name in _filters:
        return _filters[name]
    return False


async def save_filter(chat_id: int, name: str, _filter: dict):
    name = name.lower().strip()
    _filters = await _get_filters(chat_id)
    _filters[name] = _filter
    await filtersdb.update_one(
        {"chat_id": chat_id},
        {"$set": {"filters": _filters}},
        upsert=True,
    )


async def delete_filter(chat_id: int, name: str) -> bool:
    filtersd = await _get_filters(chat_id)
    name = name.lower().strip()
    if name in filtersd:
        del filtersd[name]
        await filtersdb.update_one(
            {"chat_id": chat_id},
            {"$set": {"filters": filtersd}},
            upsert=True,
        )
        return True
    return False


async def deleteall_filters(chat_id: int):
    return await filtersdb.delete_one({"chat_id": chat_id})


async def get_rules(chat_id: int):
    chat = await rulesdb.find_one({"chat_id": chat_id})
    if not chat:
        return ""
    rules = chat.get("rules", "")
    return rules


async def set_chat_rules(chat_id: int, rules: str):
    await rulesdb.update_one(
        {"chat_id": chat_id},
        {"$set": {"rules": rules}},
        upsert=True,
    )


async def delete_rules(chat_id: int):
    return await rulesdb.delete_one({"chat_id": chat_id})


async def int_to_alpha(user_id: int) -> str:
    alphabet = list(ascii_lowercase)[:10]
    text = ""
    user_id = str(user_id)
    for i in user_id:
        text += alphabet[int(i)]
    return text


async def alpha_to_int(user_id_alphabet: str) -> int:
    alphabet = list(ascii_lowercase)[:10]
    user_id = ""
    for i in user_id_alphabet:
        index = alphabet.index(i)
        user_id += str(index)
    user_id = int(user_id)
    return user_id


async def get_warns_count() -> dict:
    chats_count = 0
    warns_count = 0
    async for chat in warnsdb.find({"chat_id": {"$lt": 0}}):
        for user in chat["warns"]:
            warns_count += chat["warns"][user]["warns"]
        chats_count += 1
    return {"chats_count": chats_count, "warns_count": warns_count}


async def get_warns(chat_id: int) -> Dict[str, int]:
    warns = await warnsdb.find_one({"chat_id": chat_id})
    if not warns:
        return {}
    return warns["warns"]


async def get_warn(chat_id: int, name: str) -> Union[bool, dict]:
    name = name.lower().strip()
    warns = await get_warns(chat_id)
    if name in warns:
        return warns[name]


async def add_warn(chat_id: int, name: str, warn: dict):
    name = name.lower().strip()
    warns = await get_warns(chat_id)
    warns[name] = warn

    await warnsdb.update_one(
        {"chat_id": chat_id}, {"$set": {"warns": warns}}, upsert=True
    )


async def remove_warns(chat_id: int, name: str) -> bool:
    warnsd = await get_warns(chat_id)
    name = name.lower().strip()
    if name in warnsd:
        del warnsd[name]
        await warnsdb.update_one(
            {"chat_id": chat_id},
            {"$set": {"warns": warnsd}},
            upsert=True,
        )
        return True
    return False


async def get_karmas_count() -> dict:
    chats_count = 0
    karmas_count = 0
    async for chat in karmadb.find({"chat_id": {"$lt": 0}}):
        for i in chat["karma"]:
            karma_ = chat["karma"][i]["karma"]
            if karma_ > 0:
                karmas_count += karma_
        chats_count += 1
    return {"chats_count": chats_count, "karmas_count": karmas_count}


async def user_global_karma(user_id) -> int:
    total_karma = 0
    async for chat in karmadb.find({"chat_id": {"$lt": 0}}):
        karma = chat["karma"].get(await int_to_alpha(user_id))
        if karma and (int(karma["karma"]) > 0):
            total_karma += int(karma["karma"])
    return total_karma


async def get_karmas(chat_id: int) -> Dict[str, int]:
    karma = await karmadb.find_one({"chat_id": chat_id})
    if not karma:
        return {}
    return karma["karma"]


async def get_karma(chat_id: int, name: str) -> Union[bool, dict]:
    name = name.lower().strip()
    karmas = await get_karmas(chat_id)
    if name in karmas:
        return karmas[name]


async def update_karma(chat_id: int, name: str, karma: dict):
    name = name.lower().strip()
    karmas = await get_karmas(chat_id)
    karmas[name] = karma
    await karmadb.update_one(
        {"chat_id": chat_id}, {"$set": {"karma": karmas}}, upsert=True
    )


async def is_karma_on(chat_id: int) -> bool:
    chat = await karmadb.find_one({"chat_id_toggle": chat_id})
    if not chat:
        return True
    return False


async def karma_on(chat_id: int):
    is_karma = await is_karma_on(chat_id)
    if is_karma:
        return
    return await karmadb.delete_one({"chat_id_toggle": chat_id})


async def karma_off(chat_id: int):
    is_karma = await is_karma_on(chat_id)
    if not is_karma:
        return
    return await karmadb.insert_one({"chat_id_toggle": chat_id})


async def is_served_chat(chat_id: int) -> bool:
    chat = await chatsdb.find_one({"chat_id": chat_id})
    if not chat:
        return False
    return True


async def get_served_chats() -> list:
    chats_list = []
    async for chat in chatsdb.find({"chat_id": {"$lt": 0}}):
        chats_list.append(chat)
    return chats_list


async def add_served_chat(chat_id: int):
    is_served = await is_served_chat(chat_id)
    if is_served:
        return
    return await chatsdb.insert_one({"chat_id": chat_id})


async def remove_served_chat(chat_id: int):
    is_served = await is_served_chat(chat_id)
    if not is_served:
        return
    return await chatsdb.delete_one({"chat_id": chat_id})


async def is_served_user(user_id: int) -> bool:
    user = await usersdb.find_one({"user_id": user_id})
    if not user:
        return False
    return True


async def get_served_users() -> list:
    users_list = []
    async for user in usersdb.find({"user_id": {"$gt": 0}}):
        users_list.append(user)
    return users_list


async def add_served_user(user_id: int):
    is_served = await is_served_user(user_id)
    if is_served:
        return
    return await usersdb.insert_one({"user_id": user_id})


async def get_gbans_count() -> int:
    return len([i async for i in gbansdb.find({"user_id": {"$gt": 0}})])


async def is_gbanned_user(user_id: int) -> bool:
    user = await gbansdb.find_one({"user_id": user_id})
    if not user:
        return False
    return True


async def add_gban_user(user_id: int):
    is_gbanned = await is_gbanned_user(user_id)
    if is_gbanned:
        return
    return await gbansdb.insert_one({"user_id": user_id})


async def remove_gban_user(user_id: int):
    is_gbanned = await is_gbanned_user(user_id)
    if not is_gbanned:
        return
    return await gbansdb.delete_one({"user_id": user_id})


async def _get_lovers(chat_id: int):
    lovers = await coupledb.find_one({"chat_id": chat_id})
    if not lovers:
        return {}
    return lovers["couple"]


async def get_couple(chat_id: int, date: str):
    lovers = await _get_lovers(chat_id)
    if date in lovers:
        return lovers[date]
    return False


async def save_couple(chat_id: int, date: str, couple: dict):
    lovers = await _get_lovers(chat_id)
    lovers[date] = couple
    await coupledb.update_one(
        {"chat_id": chat_id},
        {"$set": {"couple": lovers}},
        upsert=True,
    )


async def is_captcha_on(chat_id: int) -> bool:
    chat = await captchadb.find_one({"chat_id": chat_id})
    if not chat:
        return False
    return True


async def captcha_on(chat_id: int):
    is_captcha = await is_captcha_on(chat_id)
    if is_captcha:
        return
    return await captchadb.insert_one({"chat_id": chat_id})


async def captcha_off(chat_id: int):
    is_captcha = await is_captcha_on(chat_id)
    if not is_captcha:
        return
    return await captchadb.delete_one({"chat_id": chat_id})


async def has_solved_captcha_once(chat_id: int, user_id: int):
    has_solved = await solved_captcha_db.find_one(
        {"chat_id": chat_id, "user_id": user_id}
    )
    return bool(has_solved)


async def save_captcha_solved(chat_id: int, user_id: int):
    return await solved_captcha_db.update_one(
        {"chat_id": chat_id},
        {"$set": {"user_id": user_id}},
        upsert=True,
    )


async def is_antiservice_on(chat_id: int) -> bool:
    chat = await antiservicedb.find_one({"chat_id": chat_id})
    if not chat:
        return True
    return False


async def antiservice_on(chat_id: int):
    is_antiservice = await is_antiservice_on(chat_id)
    if is_antiservice:
        return
    return await antiservicedb.delete_one({"chat_id": chat_id})


async def antiservice_off(chat_id: int):
    is_antiservice = await is_antiservice_on(chat_id)
    if not is_antiservice:
        return
    return await antiservicedb.insert_one({"chat_id": chat_id})


async def is_pmpermit_approved(user_id: int) -> bool:
    user = await pmpermitdb.find_one({"user_id": user_id})
    if not user:
        return False
    return True


async def approve_pmpermit(user_id: int):
    is_pmpermit = await is_pmpermit_approved(user_id)
    if is_pmpermit:
        return
    return await pmpermitdb.insert_one({"user_id": user_id})


async def disapprove_pmpermit(user_id: int):
    is_pmpermit = await is_pmpermit_approved(user_id)
    if not is_pmpermit:
        return
    return await pmpermitdb.delete_one({"user_id": user_id})


async def get_welcome(chat_id: int) -> (str, str, str):
    data = await welcomedb.find_one({"chat_id": chat_id})
    if not data:
        return "", "", ""

    welcome = data.get("welcome", "")
    raw_text = data.get("raw_text", "")
    file_id = data.get("file_id", "")

    return welcome, raw_text, file_id


async def set_welcome(chat_id: int, welcome: str, raw_text: str, file_id: str):
    update_data = {
        "welcome": welcome,
        "raw_text": raw_text,
        "file_id": file_id,
    }

    return await welcomedb.update_one(
        {"chat_id": chat_id}, {"$set": update_data}, upsert=True
    )


async def del_welcome(chat_id: int):
    return await welcomedb.delete_one({"chat_id": chat_id})


async def update_captcha_cache(captcha_dict):
    pickle = obj_to_str(captcha_dict)
    await captcha_cachedb.delete_one({"captcha": "cache"})
    if not pickle:
        return
    await captcha_cachedb.update_one(
        {"captcha": "cache"},
        {"$set": {"pickled": pickle}},
        upsert=True,
    )


async def get_captcha_cache():
    cache = await captcha_cachedb.find_one({"captcha": "cache"})
    if not cache:
        return []
    return str_to_obj(cache["pickled"])


async def get_blacklist_filters_count() -> dict:
    chats_count = 0
    filters_count = 0
    async for chat in blacklist_filtersdb.find({"chat_id": {"$lt": 0}}):
        filters = await get_blacklisted_words(chat["chat_id"])
        filters_count += len(filters)
        chats_count += 1
    return {
        "chats_count": chats_count,
        "filters_count": filters_count,
    }


async def get_blacklisted_words(chat_id: int) -> List[str]:
    _filters = await blacklist_filtersdb.find_one({"chat_id": chat_id})
    if not _filters:
        return []
    return _filters["filters"]


async def save_blacklist_filter(chat_id: int, word: str):
    word = word.lower().strip()
    _filters = await get_blacklisted_words(chat_id)
    _filters.append(word)
    await blacklist_filtersdb.update_one(
        {"chat_id": chat_id},
        {"$set": {"filters": _filters}},
        upsert=True,
    )


async def delete_blacklist_filter(chat_id: int, word: str) -> bool:
    filtersd = await get_blacklisted_words(chat_id)
    word = word.lower().strip()
    if word in filtersd:
        filtersd.remove(word)
        await blacklist_filtersdb.update_one(
            {"chat_id": chat_id},
            {"$set": {"filters": filtersd}},
            upsert=True,
        )
        return True
    return False


async def activate_pipe(from_chat_id: int, to_chat_id: int, fetcher: str):
    pipes = await show_pipes()
    pipe = {
        "from_chat_id": from_chat_id,
        "to_chat_id": to_chat_id,
        "fetcher": fetcher,
    }
    pipes.append(pipe)
    return await pipesdb.update_one(
        {"pipe": "pipe"}, {"$set": {"pipes": pipes}}, upsert=True
    )


async def deactivate_pipe(from_chat_id: int, to_chat_id: int):
    pipes = await show_pipes()
    if not pipes:
        return
    for pipe in pipes:
        if (
            pipe["from_chat_id"] == from_chat_id
            and pipe["to_chat_id"] == to_chat_id
        ):
            pipes.remove(pipe)
    return await pipesdb.update_one(
        {"pipe": "pipe"}, {"$set": {"pipes": pipes}}, upsert=True
    )


async def is_pipe_active(from_chat_id: int, to_chat_id: int) -> bool:
    for pipe in await show_pipes():
        if (
            pipe["from_chat_id"] == from_chat_id
            and pipe["to_chat_id"] == to_chat_id
        ):
            return True


async def show_pipes() -> list:
    pipes = await pipesdb.find_one({"pipe": "pipe"})
    if not pipes:
        return []
    return pipes["pipes"]


async def get_sudoers() -> list:
    sudoers = await sudoersdb.find_one({"sudo": "sudo"})
    if not sudoers:
        return []
    return sudoers["sudoers"]


async def add_sudo(user_id: int) -> bool:
    sudoers = await get_sudoers()
    sudoers.append(user_id)
    await sudoersdb.update_one(
        {"sudo": "sudo"}, {"$set": {"sudoers": sudoers}}, upsert=True
    )
    return True


async def remove_sudo(user_id: int) -> bool:
    sudoers = await get_sudoers()
    sudoers.remove(user_id)
    await sudoersdb.update_one(
        {"sudo": "sudo"}, {"$set": {"sudoers": sudoers}}, upsert=True
    )
    return True


async def blacklisted_chats() -> list:
    blacklist_chat = []
    async for chat in blacklist_chatdb.find({"chat_id": {"$lt": 0}}):
        blacklist_chat.append(chat["chat_id"])
    return blacklist_chat


async def blacklist_chat(chat_id: int) -> bool:
    if not await blacklist_chatdb.find_one({"chat_id": chat_id}):
        await blacklist_chatdb.insert_one({"chat_id": chat_id})
        return True
    return False


async def whitelist_chat(chat_id: int) -> bool:
    if await blacklist_chatdb.find_one({"chat_id": chat_id}):
        await blacklist_chatdb.delete_one({"chat_id": chat_id})
        return True
    return False


async def start_restart_stage(chat_id: int, message_id: int):
    await restart_stagedb.update_one(
        {"something": "something"},
        {
            "$set": {
                "chat_id": chat_id,
                "message_id": message_id,
            }
        },
        upsert=True,
    )


async def clean_restart_stage() -> dict:
    data = await restart_stagedb.find_one({"something": "something"})
    if not data:
        return {}
    await restart_stagedb.delete_one({"something": "something"})
    return {
        "chat_id": data["chat_id"],
        "message_id": data["message_id"],
    }


async def is_flood_on(chat_id: int) -> bool:
    chat = await flood_toggle_db.find_one({"chat_id": chat_id})
    if not chat:
        return False
    return True


async def flood_on(chat_id: int):
    is_flood = await is_flood_on(chat_id)
    if is_flood:
        return
    return await flood_toggle_db.insert_one({"chat_id": chat_id})


async def flood_off(chat_id: int):
    is_flood = await is_flood_on(chat_id)
    if not is_flood:
        return
    return await flood_toggle_db.delete_one({"chat_id": chat_id})


async def add_rss_feed(chat_id: int, url: str, last_title: str):
    return await rssdb.update_one(
        {"chat_id": chat_id},
        {"$set": {"url": url, "last_title": last_title}},
        upsert=True,
    )


async def remove_rss_feed(chat_id: int):
    return await rssdb.delete_one({"chat_id": chat_id})


async def update_rss_feed(chat_id: int, last_title: str):
    return await rssdb.update_one(
        {"chat_id": chat_id},
        {"$set": {"last_title": last_title}},
        upsert=True,
    )


async def is_rss_active(chat_id: int) -> bool:
    return await rssdb.find_one({"chat_id": chat_id})


async def get_rss_feeds() -> list:
    data = []
    async for feed in rssdb.find({"chat_id": {"$exists": 1}}):
        data.append(
            dict(
                chat_id=feed["chat_id"],
                url=feed["url"],
                last_title=feed["last_title"],
            )
        )
    return data


async def get_rss_feeds_count() -> int:
    return len([i async for i in rssdb.find({"chat_id": {"$exists": 1}})])


async def check_chatbot():
    return await chatbotdb.find_one({"chatbot": "chatbot"}) or {
        "bot": [],
        "userbot": [],
    }


async def add_chatbot(chat_id: int, is_userbot: bool = False):
    list_id = await check_chatbot()
    if is_userbot:
        list_id["userbot"].append(chat_id)
    else:
        list_id["bot"].append(chat_id)
    await chatbotdb.update_one(
        {"chatbot": "chatbot"}, {"$set": list_id}, upsert=True
    )


async def rm_chatbot(chat_id: int, is_userbot: bool = False):
    list_id = await check_chatbot()
    if is_userbot:
        list_id["userbot"].remove(chat_id)
    else:
        list_id["bot"].remove(chat_id)
    await chatbotdb.update_one(
        {"chatbot": "chatbot"}, {"$set": list_id}, upsert=True
    )

 
def _trust_badge(score: int) -> str:
    levels = [
        (500, "Legendary"),
        (200, "Respected"),
        (100, "Trusted"),
        (30,  "Known"),
        (0,   "New"),
    ]
    for threshold, label in levels:
        if score >= threshold:
            return label
    return "New"
 
 
def _score_bar(score: int, max_score: int = 500) -> str:
    filled = min(10, int((score / max(max_score, 1)) * 10))
    return "█" * filled + "░" * (10 - filled)
 
 
def _ts(ts: int) -> str:
    if not ts:
        return "Never"
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M UTC")
 
 
def _days_ago(ts: int) -> str:
    if not ts:
        return "?"
    diff = int(time.time()) - ts
    if diff < 3600:
        return f"{diff // 60}m ago"
    if diff < 86400:
        return f"{diff // 3600}h ago"
    return f"{diff // 86400}d ago"
 
 
async def record_name_if_changed(user_id: int, username: str, full_name: str):
    doc = await namehistorydb.find_one({"user_id": user_id})
    history = doc["history"] if doc else []
    if not history or history[-1]["full_name"] != full_name or history[-1].get("username") != username:
        history.append({
            "full_name": full_name,
            "username": username,
            "changed_at": int(time.time()),
        })
        await namehistorydb.update_one(
            {"user_id": user_id},
            {"$set": {"history": history}},
            upsert=True,
        )
 
 
async def get_name_history(user_id: int, limit: int = 8) -> list:
    doc = await namehistorydb.find_one({"user_id": user_id})
    if not doc:
        return []
    return list(reversed(doc["history"]))[:limit]
 
 
async def update_user_group(user_id: int, chat_id: int, chat_title: str):
    doc = await usergroupsdb.find_one({"user_id": user_id})
    groups = doc["groups"] if doc else {}
    key = str(chat_id)
    now = int(time.time())
    if key not in groups:
        groups[key] = {
            "chat_id": chat_id,
            "chat_title": chat_title,
            "first_seen": now,
            "last_seen": now,
            "msg_count": 1,
        }
    else:
        groups[key]["last_seen"] = now
        groups[key]["msg_count"] = groups[key].get("msg_count", 0) + 1
        if chat_title:
            groups[key]["chat_title"] = chat_title
    await usergroupsdb.update_one(
        {"user_id": user_id},
        {"$set": {"groups": groups}},
        upsert=True,
    )
 
 
async def get_user_groups(user_id: int) -> list:
    doc = await usergroupsdb.find_one({"user_id": user_id})
    if not doc:
        return []
    return sorted(doc["groups"].values(), key=lambda x: x["last_seen"], reverse=True)
 
 
async def record_join_leave(user_id: int, chat_id: int, event_type: str):
    doc = await useractivitydb.find_one({"user_id": user_id, "chat_id": chat_id})
    events = doc["events"] if doc else []
    events.append({"event_type": event_type, "ts": int(time.time())})
    await useractivitydb.update_one(
        {"user_id": user_id, "chat_id": chat_id},
        {"$set": {"events": events}},
        upsert=True,
    )
 
 
async def get_join_leave_history(user_id: int, chat_id: int) -> list:
    doc = await useractivitydb.find_one({"user_id": user_id, "chat_id": chat_id})
    if not doc:
        return []
    return [e for e in doc["events"] if e["event_type"] in ("join", "leave")]
 
 
async def get_avg_messages_per_day(user_id: int, chat_id: int) -> float:
    groups = await get_user_groups(user_id)
    for g in groups:
        if g["chat_id"] == chat_id:
            first = g.get("first_seen")
            msgs  = g.get("msg_count", 0)
            if not first:
                return float(msgs)
            days = max(1, (int(time.time()) - first) / 86400)
            return round(msgs / days, 1)
    return 0.0
 
 
async def get_user_global(user_id: int) -> dict:
    groups   = await get_user_groups(user_id)
    name_doc = await namehistorydb.find_one({"user_id": user_id})
    gban_doc = await gbansdb.find_one({"user_id": user_id})
 
    total_msgs = sum(g.get("msg_count", 0) for g in groups)
    all_times  = [g["first_seen"] for g in groups if g.get("first_seen")]
    last_times = [g["last_seen"]  for g in groups if g.get("last_seen")]
    first_seen = min(all_times)  if all_times  else None
    last_seen  = max(last_times) if last_times else None
 
    total_karma = 0
    async for chat in karmadb.find({"chat_id": {"$lt": 0}}):
        k = chat["karma"].get(await int_to_alpha(user_id))
        if k and int(k["karma"]) > 0:
            total_karma += int(k["karma"])
 
    total_warns = 0
    async for chat in warnsdb.find({"chat_id": {"$lt": 0}}):
        w = chat.get("warns", {})
        for name_key in w:
            if w[name_key].get("user_id") == user_id:
                total_warns += w[name_key].get("warns", 0)
 
    current_name  = ""
    current_uname = ""
    if name_doc and name_doc.get("history"):
        last = name_doc["history"][-1]
        current_name  = last.get("full_name", "")
        current_uname = last.get("username", "")
 
    return {
        "full_name":    current_name,
        "username":     current_uname,
        "first_seen":   first_seen,
        "last_seen":    last_seen,
        "total_msgs":   total_msgs,
        "total_karma":  total_karma,
        "total_warns":  total_warns,
        "is_gbanned":   bool(gban_doc),
        "groups_count": len(groups),
    }
