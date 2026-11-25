"""SQLite commit boundaries mirror the serialized operations on the HTTP event loop."""
import json
import sqlite3

from state import Store
from temporal import empty_history


def encode(value):
    return json.dumps(value, allow_nan=False, separators=(",", ":"))


class Database:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS records (
                category TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,
                PRIMARY KEY(category, key));
            CREATE TABLE IF NOT EXISTS builds (
                domain TEXT NOT NULL, position INTEGER NOT NULL, value TEXT NOT NULL,
                PRIMARY KEY(domain, position));
            CREATE TABLE IF NOT EXISTS active (domain TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS feed (seq INTEGER PRIMARY KEY, value TEXT NOT NULL);
        """)

    def put(self, category, key, value):
        self.db.execute("INSERT OR REPLACE INTO records VALUES (?, ?, ?)", (category, key, encode(value)))

    def put_build(self, domain, position, build):
        self.db.execute("INSERT INTO builds VALUES (?, ?, ?)", (domain, position, encode(build)))

    def put_changes(self, changes):
        self.db.executemany("INSERT INTO feed VALUES (?, ?)", ((item["seq"], encode(item)) for item in changes))

    def replace(self, store):
        with self.db:
            for table in ("records", "builds", "feed", "active"):
                self.db.execute("DELETE FROM " + table)
            for category in ("users", "tokens", "dossiers", "entries", "batches"):
                for key, value in getattr(store, category).items():
                    self.put(category, key, value)
            for scope, result in store.replays.items():
                self.put("replays", encode(scope), result)
            self.put("system", "clock", store.clock)
            for domain, builds in store.history.items():
                for position, build in enumerate(builds):
                    self.put_build(domain, position, build)
            self.put_changes(store.feed)

    def load(self):
        store = Store()
        for category, key, value in self.db.execute("SELECT category,key,value FROM records"):
            parsed = json.loads(value)
            if category == "system":
                store.clock = parsed
            elif category == "replays":
                store.replays[tuple(json.loads(key))] = parsed
            else:
                getattr(store, category)[key] = parsed
        for domain in store.dossiers:
            store.history[domain] = []
            store.entries.setdefault(domain, empty_history())
        for domain, value in self.db.execute("SELECT domain,value FROM builds ORDER BY domain, position"):
            store.history[domain].append(json.loads(value))
        for domain in store.dossiers:
            store.rebuild_seen(domain)
            store.rebuild_standing(domain)
        store.feed = [json.loads(value) for value, in self.db.execute("SELECT value FROM feed ORDER BY seq")]
        # No provider response can arrive in this process for a prior process's
        # requests. Charge its durable reservations and close the build once.
        for domain, encoded in self.db.execute("SELECT domain,value FROM active").fetchall():
            pending = json.loads(encoded)
            calls = pending["calls"]
            for call in calls:
                if call["outcome"] == "in_flight":
                    call["outcome"] = "interrupted"
            spent = pending["units"]
            store.history[domain].append({"time": pending["time"], "units": spent, "calls": calls,
                                          "pages": [], "research": [], "interrupted": True})
            dossier = store.dossiers[domain]
            dossier["state"] = "failed"
            dossier["spent_units"] += spent
            batch_id = pending["batch_id"]
            if batch_id:
                store.history[domain][-1]["batch_id"] = batch_id
                store.batches[batch_id]["spent_units"] += spent
            self.finish(domain, store, len(store.feed), batch_id)
        return store

    def account(self, email, user, token):
        with self.db:
            self.put("users", email, user)
            self.put("tokens", token, user["id"])

    def clock(self, value):
        with self.db:
            self.put("system", "clock", value)

    def put_active(self, domain, build):
        pending = {"time": build.book.time, "batch_id": build.batch_id, "units": build.spent + build.reserved,
                   "calls": build.record["calls"]}
        self.db.execute("INSERT OR REPLACE INTO active VALUES (?, ?)", (domain, encode(pending)))

    def checkpoint(self, domain, build):
        with self.db:
            self.put_active(domain, build)

    def write(self, store, scope, started, batch_id=None):
        with self.db:
            for domain in started:
                self.put("dossiers", domain, store.dossiers[domain])
                self.put_active(domain, store.running[domain])
            if batch_id:
                self.put("batches", batch_id, store.batches[batch_id])
            self.put("replays", encode(scope), store.replays[scope])

    def finish(self, domain, store, feed_start, batch_id):
        builds = store.history[domain]
        with self.db:
            self.put_build(domain, len(builds) - 1, builds[-1])
            self.put("dossiers", domain, store.dossiers[domain])
            self.put("entries", domain, store.entries[domain])
            self.put_changes(store.feed[feed_start:])
            if batch_id:
                self.put("batches", batch_id, store.batches[batch_id])
            self.db.execute("DELETE FROM active WHERE domain=?", (domain,))

    def close(self):
        self.db.close()
