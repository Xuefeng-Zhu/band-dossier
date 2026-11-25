import asyncio
import json
import os
import re
import secrets
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from aiohttp import web

from database import Database
from timestamps import calendar_date
from research import Build, Providers
from state import ApiError, Store, domain_name, instant, member, opaque_id, password_hash, password_matches, require


ASSETS = Path(__file__).with_name("static")


def response(body=None, status=200):
    if status == 204:
        return web.Response(status=204)
    return web.json_response(body, status=status, content_type="application/json")


def reject_constant(value):
    raise ValueError(value)


async def read_object(request):
    try:
        value = json.loads(await request.read(), parse_constant=reject_constant)
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise ApiError(400, "malformed_request", "Expected a JSON object") from None


def check_email(email):
    require(re.fullmatch(r"[^\s@]+@[^\s@]+", email), "Invalid email")


def page_number(query, name, default, minimum, maximum=None):
    raw = query.get(name, str(default))
    require(re.fullmatch(r"[0-9]+", raw), "Expected decimal digits")
    significant = raw.lstrip("0")
    # Offsets beyond the possible size of a Python sequence always yield an empty page.
    value = int(significant[:20] or "0")
    require(value >= minimum and (maximum is None or value <= maximum))
    return value


@web.middleware
async def errors(request, handler):
    try:
        return await handler(request)
    except ApiError as exc:
        return response({"error": {"code": exc.code, "message": exc.message}}, exc.status)
    except web.HTTPException as exc:
        return response({"error": {"code": "not_found", "message": exc.reason}}, 404)


class Service:
    def __init__(self):
        self.database = Database(os.getenv("DOSSIER_DB", "dossier.sqlite3"))
        self.store = self.database.load()
        self.providers = Providers()
        self.hashers = ThreadPoolExecutor(max_workers=4)

    def user_id(self, request):
        match = re.fullmatch(r"Bearer ([^\s]+)", request.headers.get("Authorization", ""), flags=re.I)
        uid = match and self.store.tokens.get(match[1])
        if not uid:
            raise ApiError(401, "unauthenticated")
        return uid

    def replace(self, fresh):
        self.database.replace(fresh)
        for build in self.store.running.values():
            build.task.cancel()
        self.store = fresh

    async def hash(self, fn, *args):
        return await asyncio.get_running_loop().run_in_executor(self.hashers, fn, *args)

    async def auth(self, request):
        body = await read_object(request)
        email = member(body, "email")
        password = member(body, "password")
        signup = request.path == "/auth/signup"
        check_email(email)
        if signup:
            name = member(body, "display_name")
            require(1 <= len(name) <= 100 and len(password) >= 8)
            hashed = await self.hash(password_hash, password)
            if email in self.store.users:
                raise ApiError(409, "email_taken")
            user = {"id": opaque_id("u_"), "display_name": name, "hash": hashed}
            self.store.users[email] = user
        else:
            while True:
                user = self.store.users.get(email)
                if user is None:
                    raise ApiError(401, "unauthenticated")
                valid = await self.hash(password_matches, password, user["hash"])
                if user is self.store.users.get(email):
                    break
            if not valid:
                raise ApiError(401, "unauthenticated")
        token = secrets.token_urlsafe(32)
        self.store.tokens[token] = user["id"]
        self.database.account(email, user, token)
        return response({"user_id": user["id"], "display_name": user["display_name"], "token": token}, 201 if signup else 200)

    async def reset(self, request):
        body = await read_object(request)
        fresh = Store()
        fresh.clock = member(body, "now").upper()
        instant(fresh.clock)
        users = member(body, "users", list) if "users" in body else []
        identities = set()
        passwords = []
        for user in users:
            if not isinstance(user, dict):
                raise ApiError(400, "malformed_request")
            uid, email, password, name = (member(user, k) for k in ("id", "email", "password", "display_name"))
            require(email not in fresh.users and 1 <= len(uid) <= 64 and uid not in identities)
            identities.add(uid)
            fresh.users[email] = {"id": uid, "display_name": name}
            passwords.append(password)
        hashes = await asyncio.gather(*(self.hash(password_hash, p) for p in passwords))
        for user, hashed in zip(fresh.users.values(), hashes):
            user["hash"] = hashed
        self.replace(fresh)
        return response(status=204)

    async def control(self, request):
        if request.path == "/_test/export":
            return response(self.store.snapshot())
        body = await read_object(request)
        if request.path == "/_test/import":
            fresh = Store.restore(body)
            fresh.clock = self.store.clock
            self.replace(fresh)
        else:
            now = member(body, "now").upper()
            require(instant(now) >= instant(self.store.now()), "Clock cannot move backwards")
            self.database.clock(now)
            self.store.clock = now
        return response(status=204)

    def start(self, domain, batch_id=None):
        store = self.store
        timestamp = store.now()
        def checkpoint():
            if self.store is store and store.running.get(domain) is build:
                self.database.checkpoint(domain, build)

        remaining = (lambda: store.batch_remaining(batch_id)) if batch_id else None
        build = Build(domain, self.providers, timestamp, batch_id, remaining, checkpoint)
        store.running[domain] = build

        async def run():
            try:
                await build.run()
            except asyncio.CancelledError:
                return
            except Exception as exc:
                # Record just the exception class. Provider messages may contain credentials.
                build.record["error"] = type(exc).__name__
            if store is not self.store:
                return
            feed_start = len(store.feed)
            store.finish(domain, build, timestamp)
            self.database.finish(domain, store, feed_start, batch_id)

        build.task = asyncio.create_task(run())

    async def write(self, request):
        self.user_id(request)
        refresh = "domain" in request.match_info
        key = request.headers.get("Idempotency-Key", "")
        if not key:
            raise ApiError(400, "missing_idempotency_key")
        require(len(key) <= 255)
        body = {} if refresh else await read_object(request)
        uid = self.user_id(request)
        scope = (uid, request.method, request.rel_url.raw_path, key)
        batch = request.path == "/batches"
        keys = ("domains", "budget_units") if batch else ("domain",)
        known = {k: body[k] for k in keys if k in body}
        previous = self.store.replays.get(scope)
        if previous:
            if known != previous[0] or (batch and type(known.get("budget_units")) is bool):
                raise ApiError(409, "idempotency_key_reuse")
            return response(previous[1])
        started = []
        batch_id = None
        if batch:
            raw = member(body, "domains", list)
            require(1 <= len(raw) <= 50)
            domains = [domain_name(value) for value in raw]
            require(len(set(domains)) == len(domains), "Duplicate company domain")
            budget = body.get("budget_units")
            require(type(budget) is int and 1 <= budget <= 100000, "Invalid batch budget")
            batch_id = opaque_id("b_")
            self.store.batches[batch_id] = {"owner": uid, "domains": domains, "budget_units": budget, "spent_units": 0}
            for domain in domains:
                if domain not in self.store.dossiers:
                    self.store.new_dossier(domain)
                    self.start(domain, batch_id)
                    started.append(domain)
            summary = self.store.batch_view(batch_id)
            status = 202
        else:
            domain = domain_name(request.match_info["domain"] if refresh else member(body, "domain"))
            created = domain not in self.store.dossiers
            if created:
                if refresh:
                    raise ApiError(404, "not_found")
                self.store.new_dossier(domain)
            if (created or refresh) and domain not in self.store.running:
                self.start(domain)
                started.append(domain)
            view = self.store.view(domain)
            summary = {k: view[k] for k in ("dossier_id", "domain", "state")}
            status = 202 if created or refresh else 200
        self.store.replays[scope] = (known, summary)
        self.database.write(self.store, scope, started, batch_id)
        return response(summary, status)

    async def batch(self, request):
        uid = self.user_id(request)
        batch_id = request.match_info["id"]
        batch = self.store.batches.get(batch_id)
        if batch is None or batch["owner"] != uid:
            raise ApiError(404, "not_found")
        return response(self.store.batch_view(batch_id))

    async def read(self, request):
        if "domain" in request.match_info and "text/html" in request.headers.get("Accept", "").lower():
            return await self.screen(request)
        self.user_id(request)
        if "domain" in request.match_info:
            domain = domain_name(request.match_info["domain"])
            if "as_of" in request.query:
                return response(self.store.at(domain, request.query["as_of"]))
            return response(self.store.view(domain))
        query = request.query
        limit = page_number(query, "limit", 50, 1, 200)
        offset = page_number(query, "offset", 0, 0)
        term = query.get("q", "").casefold()
        rows = []
        for domain in sorted(self.store.dossiers):
            view = self.store.view(domain)
            legal = view.pop("fields")["legal_name"]["value"]
            if term in domain.casefold() or (legal and term in legal.casefold()):
                rows.append({**view, "legal_name": legal})
        return response({"dossiers": rows[offset:offset + limit], "has_more": len(rows) > offset + limit})

    async def temporal(self, request):
        self.user_id(request)
        domain = domain_name(request.match_info["domain"])
        if request.path.endswith("/history"):
            self.store.view(domain)
            return response({"domain": domain, "fields": self.store.entries[domain]})
        try:
            date = calendar_date(request.query.get("true_at"))
        except ValueError:
            raise ApiError(422, "validation_failed", "Expected true_at as a calendar date") from None
        when = request.query.get("as_of", self.store.now())
        return response(self.store.at(domain, when, date))

    async def changes(self, request):
        self.user_id(request)
        since = page_number(request.query, "since", 0, 0)
        limit = page_number(request.query, "limit", 50, 1, 200)
        # The feed is append-only and our sequence numbers start at one.
        return response({"changes": self.store.feed[since:since + limit], "has_more": since + limit < len(self.store.feed)})

    async def health(self, request):
        return response({"status": "ok"})

    async def screen(self, request):
        return web.FileResponse(ASSETS / "index.html", headers={"Cache-Control": "no-cache", "Vary": "Accept"})

    async def missing(self, request):
        self.user_id(request)
        raise ApiError(404, "not_found")

    async def close(self, app):
        builds = [b.task for b in self.store.running.values()]
        for task in builds:
            task.cancel()
        await asyncio.gather(*builds, return_exceptions=True)
        await self.providers.close()
        self.hashers.shutdown()
        self.database.close()

    def app(self):
        app = web.Application(middlewares=[errors], client_max_size=0)
        app.router.add_static("/assets/", ASSETS, show_index=False)
        app.add_routes([
            web.get("/", self.screen), web.get("/contested", self.screen),
            web.get("/signup", self.screen), web.get("/login", self.screen),
            web.get("/dossiers/{domain}/evidence", self.screen),
            web.get("/health", self.health), web.post("/_test/reset", self.reset),
            web.post("/_test/clock", self.control), web.get("/_test/export", self.control),
            web.post("/_test/import", self.control), web.post("/auth/signup", self.auth),
            web.post("/batches", self.write), web.get("/batches/{id}", self.batch),
            web.post("/auth/login", self.auth), web.post("/dossiers", self.write),
            web.post("/dossiers/{domain}/refresh", self.write), web.get("/dossiers", self.read),
            web.get("/dossiers/{domain}/values", self.temporal), web.get("/dossiers/{domain}/history", self.temporal),
            web.get("/changes", self.changes), web.get("/dossiers/{domain}", self.read), web.route("*", "/{path:.*}", self.missing),
        ])
        app.on_cleanup.append(self.close)
        return app


if __name__ == "__main__":
    web.run_app(Service().app(), host="0.0.0.0", port=int(os.getenv("PORT", "8080")), access_log=None)
