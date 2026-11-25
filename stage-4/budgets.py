"""Atomically reserve each in-flight call before contacting a provider."""

import copy


BUILD_LIMIT = 80


class BuildLedger:
    def __init__(self, store, dossier, entry):
        self.store = store
        self.dossier = dossier
        self.entry = entry
        self.domain = dossier["domain"]

    def current(self):
        return self.store.active.get(self.domain) is self.entry

    def batch(self):
        return self.store.state["batches"].get(self.entry["batch_id"])

    def capacity(self, *, include_reservations=True):
        with self.store.lock:
            if not self.current():
                return -1
            uncharged = sum(self.entry["reserved"].values()) if include_reservations else 0
            free = BUILD_LIMIT - self.entry["record"]["spent_units"] - uncharged
            batch = self.batch()
            if batch is None:
                return free
            held = (sum(sum(item["reserved"].values()) for item in self.store.active.values()
                        if item["batch_id"] == batch["batch_id"]) if include_reservations else 0)
            return min(free, batch["budget_units"] - batch["spent_units"] - held)

    def save(self, record):
        self.entry["record"] = copy.deepcopy(record)
        self.store.persist_progress(self.entry)

    def reserve(self, index, cost, record):
        with self.store.lock:
            if self.capacity() < cost:
                return False
            self.entry["reserved"][str(index)] = cost
            self.save(record)
            return True

    def settle(self, index, charged, record):
        with self.store.lock:
            if not self.current():
                return
            self.entry["reserved"].pop(str(index))
            self.dossier["spent_units"] += charged
            batch = self.batch()
            if batch is not None:
                batch["spent_units"] += charged
            self.save(record)

    def checkpoint(self, record):
        with self.store.lock:
            if self.current():
                self.save(record)
