"""MongoDB layer (motor). Settings are cached in memory (single process)."""
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne

from config import Config

_settings = None  # collection: one doc {_id: "main", ...}
_used = None      # collection: {_id: msg_id, kind: "sent" | "bad"}
_queue = None     # collection: {_id: msg_id}  (new media waiting to be posted)

DEFAULTS = {
    "source": None,
    "target": None,
    "interval": 3600,   # seconds
    "count": 5,
    "enabled": False,
    "last_id": 0,
    "next_run": 0,
}
_cache = dict(DEFAULTS)


async def init():
    global _settings, _used, _queue
    client = AsyncIOMotorClient(Config.DATABASE_URI)
    database = client[Config.DATABASE_NAME]
    _settings = database["settings"]
    _used = database["used"]
    _queue = database["queue"]
    doc = await _settings.find_one({"_id": "main"}) or {}
    _cache.update({k: v for k, v in doc.items() if k != "_id"})


# ---------- settings ----------
def get_settings():
    return _cache


async def set_settings(**kw):
    _cache.update(kw)
    await _settings.update_one({"_id": "main"}, {"$set": kw}, upsert=True)


async def bump_last_id(n):
    if n > _cache["last_id"]:
        await set_settings(last_id=n)


# ---------- queue (new media) ----------
async def add_queue(msg_id):
    await _queue.update_one({"_id": msg_id}, {"$setOnInsert": {"ok": 1}}, upsert=True)


async def queue_first(n):
    return [d["_id"] async for d in _queue.find({}).sort("_id", 1).limit(n)]


async def queue_remove(ids):
    if ids:
        await _queue.delete_many({"_id": {"$in": list(ids)}})


# ---------- used (sent / bad) ----------
async def used_ids(ids, kind=None):
    q = {"_id": {"$in": list(ids)}}
    if kind:
        q["kind"] = kind
    return {d["_id"] async for d in _used.find(q, {"_id": 1})}


async def all_used_ids():
    return {d["_id"] async for d in _used.find({}, {"_id": 1})}


async def mark(ids, kind):
    ids = list(ids)
    if not ids:
        return
    ops = [UpdateOne({"_id": i}, {"$set": {"kind": kind}}, upsert=True) for i in ids]
    await _used.bulk_write(ops, ordered=False)


async def used_count():
    return await _used.count_documents({})


async def reset_sent():
    """Start a new round: forget 'sent', keep 'bad' (deleted/text posts)."""
    await _used.delete_many({"kind": "sent"})


async def clear_all():
    await _used.delete_many({})
    await _queue.delete_many({})


async def counts():
    sent = await _used.count_documents({"kind": "sent"})
    queued = await _queue.count_documents({})
    return sent, queued
