import re
import time

from pyrogram import filters
from pyrogram.enums import ChatMemberStatus, ParseMode

import db
import poster
from config import Config

HELP = """🤖 Random Media Forward Bot

Setup:
/setsource <id | @username | post link>
/settarget <id | @username>
/setlast <last post link | number>

Control:
/setinterval 10m | 1h | 2h
/setcount 5
/startpost - auto-posting ON
/stoppost - auto-posting OFF
/postnow - ek batch abhi bhejo
/status - settings aur stats
/resetsent - bheji hui list reset

Bot ko dono channels me admin banao."""


async def say(m, text):
    return await m.reply_text(text, parse_mode=ParseMode.DISABLED)


def parse_chat_link(arg):
    """Returns (chat, msg_id). Either can be None."""
    arg = arg.strip()
    if arg.lstrip("-").isdigit():
        return int(arg), None
    mt = re.search(r"t\.me/c/(\d+)/(?:\d+/)?(\d+)", arg)
    if mt:
        return int("-100" + mt.group(1)), int(mt.group(2))
    mt = re.search(r"t\.me/c/(\d+)/?$", arg)
    if mt:
        return int("-100" + mt.group(1)), None
    mt = re.search(r"t\.me/([A-Za-z0-9_]{4,})/(\d+)", arg)
    if mt:
        return mt.group(1), int(mt.group(2))
    mt = re.search(r"t\.me/([A-Za-z0-9_]{4,})/?$", arg)
    if mt:
        return mt.group(1), None
    return arg.lstrip("@"), None


def parse_duration(t):
    mt = re.fullmatch(r"(\d+)\s*([mhd])", t.strip().lower())
    if not mt:
        return None
    return int(mt.group(1)) * {"m": 60, "h": 3600, "d": 86400}[mt.group(2)]


def fmt_dur(sec):
    sec = int(sec)
    d, r = divmod(sec, 86400)
    h, r = divmod(r, 3600)
    mi, s = divmod(r, 60)
    parts = []
    if d:
        parts.append(f"{d}d")
    if h:
        parts.append(f"{h}h")
    if mi:
        parts.append(f"{mi}m")
    if s and not parts:
        parts.append(f"{s}s")
    return " ".join(parts) or "0s"


def arg_of(m):
    parts = (m.text or "").split(None, 1)
    return parts[1].strip() if len(parts) > 1 else ""


def register(app):
    owner = filters.private & filters.user(Config.OWNER_IDS)

    @app.on_message(filters.command(["start", "help"]) & filters.private)
    async def start_cmd(client, m):
        if m.from_user and m.from_user.id in Config.OWNER_IDS:
            await say(m, HELP)
        else:
            await say(m, "🔒 Ye private bot hai.")

    @app.on_message(filters.command("setsource") & owner)
    async def set_source(client, m):
        arg = arg_of(m)
        if not arg:
            return await say(m, "Use: /setsource -1001234567890  (ya @username, ya kisi post ka link)")
        chat_ref, msg_id = parse_chat_link(arg)
        try:
            chat = await client.get_chat(chat_ref)
        except Exception as e:
            return await say(m, f"❌ Channel nahi mila: {e}\nBot us channel me admin hai?")
        s = db.get_settings()
        if s["source"] != chat.id:
            await db.clear_all()
            await db.set_settings(source=chat.id, last_id=0, next_run=0)
        if msg_id:
            await db.bump_last_id(msg_id)
        extra = (
            f"\nLast ID: {db.get_settings()['last_id']}"
            if msg_id
            else "\nAb /setlast se source ki sabse last post ka link do."
        )
        await say(m, f"✅ Source set: {chat.title} ({chat.id}){extra}")

    @app.on_message(filters.command("settarget") & owner)
    async def set_target(client, m):
        arg = arg_of(m)
        if not arg:
            return await say(m, "Use: /settarget -1001234567890  (ya @username)")
        chat_ref, _ = parse_chat_link(arg)
        try:
            chat = await client.get_chat(chat_ref)
        except Exception as e:
            return await say(m, f"❌ Channel nahi mila: {e}\nBot us channel me admin hai?")
        if chat.id == db.get_settings()["source"]:
            return await say(m, "❌ Source aur target same nahi ho sakte.")
        warn = ""
        try:
            me = await client.get_chat_member(chat.id, "me")
            if me.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
                warn = "\n⚠️ Bot yaha admin nahi lag raha. Admin banao (post permission ke saath)."
        except Exception:
            warn = "\n⚠️ Bot ka admin status check nahi ho paya. Admin banana mat bhoolna."
        await db.set_settings(target=chat.id)
        await say(m, f"✅ Target set: {chat.title} ({chat.id}){warn}")

    @app.on_message(filters.command("setlast") & owner)
    async def set_last(client, m):
        arg = arg_of(m)
        if not arg:
            return await say(
                m,
                "Use: /setlast https://t.me/c/1234567890/20000\n"
                "ya /setlast 20000\n(source channel ki sabse last post ka link ya ID)",
            )
        if arg.isdigit():
            msg_id = int(arg)
        else:
            _, msg_id = parse_chat_link(arg)
        if not msg_id:
            return await say(m, "❌ Link me message ID nahi mili. Kisi post ka link do (Copy Link).")
        await db.set_settings(last_id=msg_id)
        await say(m, f"✅ Last ID set: {msg_id}")

    @app.on_message(filters.command("setinterval") & owner)
    async def set_interval(client, m):
        sec = parse_duration(arg_of(m)) if arg_of(m) else None
        if not sec:
            return await say(m, "Use: /setinterval 10m  |  1h  |  2h  |  1d  (minimum 1m)")
        await db.set_settings(interval=sec, next_run=time.time() + sec)
        await say(m, f"✅ Interval: {fmt_dur(sec)}\nAgla batch {fmt_dur(sec)} baad.")

    @app.on_message(filters.command("setcount") & owner)
    async def set_count(client, m):
        a = arg_of(m)
        if not a.isdigit() or not (1 <= int(a) <= 50):
            return await say(m, "Use: /setcount 5  (1 se 50)")
        await db.set_settings(count=int(a))
        await say(m, f"✅ Ek baar me {int(a)} media jayegi.")

    @app.on_message(filters.command("startpost") & owner)
    async def start_post(client, m):
        s = db.get_settings()
        if not s["source"] or not s["target"]:
            return await say(m, "❌ Pehle /setsource aur /settarget set karo.")
        note = ""
        if s["last_id"] <= 0:
            note = "\n⚠️ /setlast set nahi hai, isliye sirf naya media jayega."
        await db.set_settings(enabled=True, next_run=0)
        await say(m, f"▶️ Auto-posting ON. Pehla batch abhi, phir har {fmt_dur(s['interval'])}.{note}")

    @app.on_message(filters.command("stoppost") & owner)
    async def stop_post(client, m):
        await db.set_settings(enabled=False)
        await say(m, "⏹ Auto-posting OFF.")

    @app.on_message(filters.command("postnow") & owner)
    async def post_now(client, m):
        msg = await say(m, "⏳ Post ho raha hai...")
        try:
            res = await poster.run_batch(client)
        except poster.FatalPostError as e:
            return await msg.edit_text(f"⚠️ {e}", parse_mode=ParseMode.DISABLED)
        except Exception as e:
            return await msg.edit_text(f"❌ Error: {e}", parse_mode=ParseMode.DISABLED)
        text = f"✅ {res['sent']} media bheji"
        if res["from_queue"]:
            text += f" (naya: {res['from_queue']})"
        if res["failed"]:
            text += f"\n⚠️ {res['failed']} fail hui"
        if res["reset"]:
            text += "\n♻️ Saari media post ho chuki thi, list reset hui."
        if res["sent"] == 0:
            text += "\nKoi media nahi mili. /setlast sahi hai? Bot source me admin hai?"
        await msg.edit_text(text, parse_mode=ParseMode.DISABLED)

    @app.on_message(filters.command("resetsent") & owner)
    async def reset_sent(client, m):
        await db.reset_sent()
        await say(m, "♻️ Bheji hui list reset. Ab saari media dobara aa sakti hai.")

    @app.on_message(filters.command("status") & owner)
    async def status(client, m):
        s = db.get_settings()
        sent, queued = await db.counts()
        if s["enabled"]:
            left = max(0, s["next_run"] - time.time())
            nxt = f"{fmt_dur(left)} baad" if left else "abhi"
        else:
            nxt = "-"
        await say(
            m,
            "📊 Status\n\n"
            f"Auto-post: {'ON ✅' if s['enabled'] else 'OFF ⛔'}\n"
            f"Source: {s['source'] or 'set nahi'}\n"
            f"Target: {s['target'] or 'set nahi'}\n"
            f"Interval: {fmt_dur(s['interval'])}\n"
            f"Ek baar me: {s['count']} media\n"
            f"Last ID: {s['last_id']}\n"
            f"Is round me bheji: {sent}\n"
            f"Naya media queue me: {queued}\n"
            f"Agla batch: {nxt}",
        )

    # ---- new posts in the source channel ----
    @app.on_message(filters.channel)
    async def on_channel_post(client, m):
        s = db.get_settings()
        if not s["source"] or m.chat.id != s["source"]:
            return
        await db.bump_last_id(m.id)
        if poster.is_media(m):
            await db.add_queue(m.id)
