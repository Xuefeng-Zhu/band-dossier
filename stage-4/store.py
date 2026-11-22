"""Atomic storage for the service state and test clock."""

import json
import sqlite3


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("PRAGMA synchronous = FULL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS service_state "
            "(id INTEGER PRIMARY KEY CHECK (id = 1), payload TEXT NOT NULL)"
        )

    def load(self):
        row = self.db.execute("SELECT payload FROM service_state WHERE id = 1").fetchone()
        return json.loads(row[0]) if row else None

    def save(self, state, clock):
        payload = json.dumps({"state": state, "clock": clock}, separators=(",", ":"))
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO service_state (id, payload) VALUES (1, ?)", (payload,))
