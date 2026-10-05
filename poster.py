"""Core logic: pick media (new ones first, then random old ones) and copy them
to the target channel with copy_message (no 'Forwarded from' tag)."""
import asyncio
import logging
import random
import time

from pyrogram.errors import (
    ChannelInvalid,
    ChannelPrivate,
    ChatAdminRequired,
    ChatWriteForbidden,
    FloodWait,
    PeerIdInvalid,
)

import db
from config import Config

log = logging.getLogger("poster")

LOCK = asyncio.Lock()
SEND_DELAY = 1.5      # seconds between two copies
MAX_ROUNDS = 40       # max random-fetch rounds per batch
FATAL = (ChatWriteForbidden, ChatAdminRequired, ChannelPrivate, PeerIdInvalid, ChannelInvalid)
MEDIA_ATTRS = ("photo", "video", "document", "audio", "animation", "voice", "video_note")


class FatalPostError(Exception):
    pass


def is_media(m):
    if m is None or getattr(m, "empty", False) or getattr(m, "service", None):
        return False
    return any(getattr(m, a, None) for a in MEDIA_ATTRS)


async def fetch(client, chat, ids):
    """Fetch messages by ID (200 per call). Returns {id: message}."""
    found = {}
    ids = list(ids)
    for i in range(0, len(ids), 200):
        part = ids[i:i + 200]
        res = None
        for _ in range(3):
            try:
                res = await client.get_messages(chat, part)
                break
            except FloodWait as e:
                await asyncio.sleep(e.value + 1)
            except FATAL as e:
                raise FatalPostError(
                    f"Source channel access error ({e.__class__.__name__}). "
                    "Bot source channel me admin hai?"
                )
            except Exception as e:
                log.warning("get_messages failed: %s", e)
                await asyncio.sleep(2)
        if res is None:
            continue
        if not isinstance(res, list):
            res = [res]
        for m in res:
            if m is not None:
                found[m.id] = m
    return found


async def send_one(client, source, target, mid):
    for _ in range(3):
        try:
            await client.copy_message(chat_id=target, from_chat_id=source, message_id=mid)
            return True
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
        except FATAL as e:
            raise FatalPostError(
                f"Channel access error ({e.__class__.__name__}). "
                "Bot target channel me admin hai (post permission ke saath)?"
            )
        except Exception as e:
            log.warning("copy_message %s failed: %s", mid, e)
            return False
    return False


async def run_batch(client):
    async with LOCK:
        return await _run_batch(client)


async def _run_batch(client):
    s = db.get_settings()
    source, target, count = s["source"], s["target"], s["count"]
    if not source or not target:
        raise FatalPostError("Source ya target set nahi hai.")

    res = {"sent": 0, "failed": 0, "reset": False, "from_queue": 0}
    need = count
    failed_ids = set()

    # ---- 1) NEW media (queue) first ----
    while need > 0:
        qids = await db.queue_first(need)
        if not qids:
            break
        done = await db.used_ids(qids, "sent")
        todo = [i for i in qids if i not in done]
        msgs = await fetch(client, source, todo)
        for mid in todo:
            m = msgs.get(mid)
            if not is_media(m):
                continue
            if await send_one(client, source, target, mid):
                await db.mark([mid], "sent")
                need -= 1
                res["sent"] += 1
                res["from_queue"] += 1
                await asyncio.sleep(SEND_DELAY)
            else:
                res["failed"] += 1
        # examined items always leave the queue (failed ones can still come back via random)
        await db.queue_remove(qids)

    # ---- 2) RANDOM old media ----
    used_total = await db.used_count()
    used_all = None  # lazily loaded set, only for the end of a round
    rounds = 0
    while need > 0 and rounds < MAX_ROUNDS:
        rounds += 1
        last = db.get_settings()["last_id"]
        if last <= 0:
            break

        remaining = last - used_total
        if remaining <= 0:
            if res["reset"]:
                break
            await db.reset_sent()
            res["reset"] = True
            used_all = None
            used_total = await db.used_count()
            remaining = last - used_total
            if remaining <= 0:
                break

        chunk = min(200, max(40, need * 8))
        if remaining <= max(1000, last // 20):
            # near the end of a round: pick from the exact list of unused IDs
            if used_all is None:
                used_all = await db.all_used_ids()
            pool = [i for i in range(1, last + 1) if i not in used_all and i not in failed_ids]
            cands = random.sample(pool, min(chunk, len(pool)))
        else:
            cands = random.sample(range(1, last + 1), min(chunk, last))
            seen = await db.used_ids(cands)
            cands = [i for i in cands if i not in seen and i not in failed_ids]
        if not cands:
            continue

        msgs = await fetch(client, source, cands)
        bad = []
        for mid in cands:
            m = msgs.get(mid)
            if m is None:
                continue
            if not is_media(m):
                bad.append(mid)      # deleted / text / service -> never pick again
                continue
            if need <= 0:
                continue
            if await send_one(client, source, target, mid):
                await db.mark([mid], "sent")
                used_total += 1
                if used_all is not None:
                    used_all.add(mid)
                need -= 1
                res["sent"] += 1
                await asyncio.sleep(SEND_DELAY)
            else:
                failed_ids.add(mid)
                res["failed"] += 1
        if bad:
            await db.mark(bad, "bad")
            used_total += len(bad)
            if used_all is not None:
                used_all.update(bad)

    return res


async def notify(client, text):
    for uid in Config.OWNER_IDS:
        try:
            await client.send_message(uid, text)
        except Exception:
            pass


async def scheduler(client):
    """Checks every 5 s whether it's time for the next batch."""
    await asyncio.sleep(5)
    while True:
        try:
            s = db.get_settings()
            if s["enabled"] and s["source"] and s["target"] and time.time() >= s["next_run"]:
                await db.set_settings(next_run=time.time() + s["interval"])
                try:
                    res = await run_batch(client)
                    log.info("Batch done: %s", res)
                    if res["reset"]:
                        await notify(
                            client,
                            "♻️ Source ki saari media ek round me post ho gayi. "
                            "List reset ho gayi, ab dobara shuru hoga.",
                        )
                except FatalPostError as e:
                    await db.set_settings(enabled=False)
                    await notify(client, f"⚠️ Auto-posting band ho gayi: {e}\nFix karke /startpost chalao.")
        except Exception:
            log.exception("scheduler error")
        await asyncio.sleep(5)
