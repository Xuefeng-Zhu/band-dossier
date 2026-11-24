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
            for table in ("records", "builds", "feed"):
                self.db.execute("DELETE FROM " + table)
            for category in ("users", "tokens", "dossiers", "entries"):
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
        store.feed = [json.loads(value) for value, in self.db.execute("SELECT value FROM feed ORDER BY seq")]
        return store

    def account(self, email, user, token):
        with self.db:
            self.put("users", email, user)
            self.put("tokens", token, user["id"])

    def clock(self, value):
        with self.db:
            self.put("system", "clock", value)

    def write(self, domain, store, scope, created):
        with self.db:
            if created:
                self.put("dossiers", domain, store.dossiers[domain])
            self.put("replays", encode(scope), store.replays[scope])

    def finish(self, domain, store, feed_start):
        builds = store.history[domain]
        with self.db:
            self.put_build(domain, len(builds) - 1, builds[-1])
            self.put("dossiers", domain, store.dossiers[domain])
            self.put("entries", domain, store.entries[domain])
            self.put_changes(store.feed[feed_start:])

    def close(self):
        self.db.close()
