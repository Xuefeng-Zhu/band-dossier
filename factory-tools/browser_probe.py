"""Capture the inherited Dossier screens against an isolated organizer mock."""

import argparse
import json
from pathlib import Path
import re
import secrets
import time
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from playwright.sync_api import Error as BrowserError, expect, sync_playwright


DOMAIN = "halvorsen-robotics.test"
DOSSIER = f"/dossiers/{DOMAIN}"
VIEWPORTS = ((375, 812), (1440, 900))
PUBLIC_SCREENS = (
    ("signup", "/signup", "signup-submit", ("signup-email", "signup-password", "signup-display-name")),
    ("login", "/login", "login-submit", ("login-email", "login-password")),
)
SIGNED_IN_SCREENS = (
    ("list", "/", "dossier-list", ("research-domain", "dossier-search")),
    ("dossier", DOSSIER, "dossier-state", ()),
    ("evidence", f"{DOSSIER}/evidence", "candidate-hq_city-1", ()),
    ("contested", "/contested", f"contested-item-{DOMAIN}-hq_city", ()),
)
LABELS = """input => {
    const references = (input.getAttribute('aria-labelledby') || '').split(/\\s+/);
    const labels = [...(input.labels || []), ...references.map(id => document.getElementById(id))];
    return labels.some(label => label && (label.innerText || label.textContent).trim() &&
        label.getBoundingClientRect().width > 1 && label.getBoundingClientRect().height > 1 &&
        label.checkVisibility({opacityProperty: true, visibilityProperty: true}));
}"""
FOCUS = """capture => {
    const candidates = [...document.querySelectorAll(
        'a[href], button, input, select, textarea, summary, [tabindex], [contenteditable]')];
    const signature = node => {
        if (!(node instanceof Element)) return {};
        const css = getComputedStyle(node);
        const painted = color => color !== 'transparent' && !/rgba\\([^)]*,\\s*0\\)$/.test(color);
        const border = ['Top', 'Right', 'Bottom', 'Left'].map(side =>
            parseFloat(css[`border${side}Width`]) && painted(css[`border${side}Color`])
                ? `${css[`border${side}Width`]} ${css[`border${side}Color`]}` : '');
        return {
            outline: !['none', 'hidden'].includes(css.outlineStyle) &&
                parseFloat(css.outlineWidth) && painted(css.outlineColor)
                    ? `${css.outlineStyle} ${css.outlineWidth} ${css.outlineColor}` : '',
            shadow: css.boxShadow !== 'none' ? css.boxShadow : '',
            border: border.some(Boolean) ? border.join('|') : '',
            background: painted(css.backgroundColor) ? css.backgroundColor : '',
            color: painted(css.color) ? css.color : '',
            decoration: css.textDecorationLine !== 'none' ? css.textDecorationLine : ''
        };
    };
    const styles = node => [signature(node), signature(node.parentElement)];
    if (capture) return candidates.map(styles);
    const node = document.activeElement;
    if (!node || node === document.body || node === document.documentElement) return null;
    const rect = node.getBoundingClientRect();
    const css = getComputedStyle(node);
    return { index: candidates.indexOf(node), element: (node.getAttribute('data-testid') || node.tagName).slice(0, 120),
        canSee: rect.width > 0 && rect.height > 0 && rect.right > 0 && rect.bottom > 0 &&
            rect.left < innerWidth && rect.top < innerHeight && css.visibility === 'visible' &&
            node.checkVisibility({opacityProperty: true, visibilityProperty: true}),
        focusVisible: node.matches(':focus-visible'), styles: styles(node) };
}"""


class ProbeFailure(Exception):
    """The service or browser did not satisfy a preflight check."""


def require_status(response, expected):
    if response.status_code != expected:
        request = response.request
        raise ProbeFailure(f"{request.method} {request.url.path} returned {response.status_code}, expected {expected}")
    return response


def require_object(response, expected):
    payload = require_status(response, expected).json()
    if not isinstance(payload, dict):
        raise ProbeFailure(f"{response.request.url.path} did not return a JSON object")
    return payload


def seed_service(base_url, user):
    with httpx.Client(base_url=base_url, timeout=5, trust_env=False) as api:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                health = api.get("/health", timeout=2)
                if health.status_code == 200 and health.json() == {"status": "ok"}:
                    break
            except (httpx.RequestError, ValueError):
                pass
            time.sleep(0.25)
        else:
            raise ProbeFailure("/health did not become ready within 60 seconds")

        reset = {"now": "2026-03-01T09:00:00+00:00", "users": [user]}
        require_status(api.post("/_test/reset", json=reset, timeout=10), 204)
        login = {key: user[key] for key in ("email", "password")}
        token = require_object(api.post("/auth/login", json=login), 200).get("token")
        if not isinstance(token, str) or not token:
            raise ProbeFailure("Fixture login did not return a bearer token")
        api.headers["Authorization"] = f"Bearer {token}"
        require_status(api.post("/dossiers", json={"domain": DOMAIN},
                                headers={"Idempotency-Key": uuid4().hex}), 202)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            dossier = require_object(api.get(DOSSIER), 200)
            state = dossier.get("state")
            if state == "ready":
                fields = dossier.get("fields")
                headquarters = fields.get("hq_city") if isinstance(fields, dict) else None
                if not isinstance(headquarters, dict) or headquarters.get("status") != "contested":
                    raise ProbeFailure("Mock company did not produce the contested headquarters fixture")
                return
            if state != "building":
                raise ProbeFailure("Mock company research ended without a ready dossier")
            time.sleep(0.1)
        raise ProbeFailure("Mock company research did not settle within 30 seconds")


def inspect_focus(page):
    baseline = page.evaluate(FOCUS, True)
    stops = []
    for _ in range(8):
        page.keyboard.press("Tab")
        node = page.evaluate(FOCUS, False)
        if node is None:
            break
        index = node["index"]
        prior = baseline[index] if 0 <= index < len(baseline) else ({}, {})
        indicators = sorted({name for after, before in zip(node["styles"], prior)
                             for name, value in after.items() if value and value != before.get(name)})
        stops.append({"element": node["element"], "visible": node["canSee"],
                      "focus_visible": node["focusVisible"], "changed_styles": indicators})
    return stops


def inspect_screen(page, screen, viewport, output, *, signed_in):
    name, route, anchor, inputs = screen
    width, height = viewport
    result = {"route": route, "width": width, "height": height, "passed": False, "errors": []}
    errors = result["errors"]
    try:
        response = page.goto(route, wait_until="load", timeout=10_000)
        if response is None or response.status != 200:
            raise ProbeFailure("The route did not render with HTTP 200")
        if urlsplit(page.url).path.rstrip("/") != route.rstrip("/"):
            raise ProbeFailure("The browser navigated away from the requested route")
        expect(page.get_by_test_id(anchor)).to_be_visible(timeout=8_000)
        if signed_in:
            expect(page.get_by_test_id("current-user")).to_be_visible(timeout=5_000)
        if name == "dossier":
            expect(page.get_by_test_id("dossier-state")).to_have_text("ready", timeout=5_000)
        dimensions = page.evaluate("""() => ({
            viewport: innerWidth,
            visible: document.documentElement.clientWidth,
            content: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth)
        })""")
        result["dimensions"] = dimensions
        if dimensions["viewport"] != width:
            errors.append("Chromium did not use the requested viewport width")
        if dimensions["content"] > dimensions["visible"]:
            errors.append("The page extends past the viewport horizontally")
        labels = {}
        for test_id in inputs:
            control = page.get_by_test_id(test_id)
            expect(control).to_be_visible(timeout=5_000)
            labels[test_id] = control.evaluate(LABELS)
            if not labels[test_id]:
                errors.append(f"No visible label for {test_id}")
        result["visible_labels"] = labels
        screenshot = f"{name}-{width}.png"
        page.screenshot(path=output / screenshot, animations="disabled", timeout=7_000)
        result["screenshot"] = screenshot
        focus = inspect_focus(page)
        result["sampled_tab_stops"] = focus
        if not focus or any(not stop["visible"] or not stop["changed_styles"] for stop in focus):
            errors.append("At least one sampled tab stop lacked a visible focus indicator")
        focused = f"{name}-{width}-focus.png"
        page.screenshot(path=output / focused, animations="disabled", timeout=7_000)
        result["focus_screenshot"] = focused
    except ProbeFailure as error:
        errors.append(str(error))
    except (BrowserError, AssertionError) as error:
        errors.append(f"Unable to verify the required screen or control ({type(error).__name__})")
    result["passed"] = not errors
    return result


def verify_viewport(browser, base_url, width, height, user, output):
    with browser.new_context(base_url=base_url, viewport={"width": width, "height": height},
                             device_scale_factor=1, service_workers="block") as context:
        def local_requests_only(route):
            parts = urlsplit(route.request.url)
            if f"{parts.scheme}://{parts.netloc}" == base_url:
                route.continue_()
            else:
                route.abort()

        context.route("**/*", local_requests_only)
        page = context.new_page()
        for screen in PUBLIC_SCREENS:
            yield inspect_screen(page, screen, (width, height), output, signed_in=False)

        try:
            page.goto("/login", timeout=10_000)
            page.get_by_test_id("login-email").fill(user["email"], timeout=5_000)
            page.get_by_test_id("login-password").fill(user["password"], timeout=5_000)
            page.get_by_test_id("login-submit").click(timeout=5_000)
            expect(page.get_by_test_id("current-user")).to_be_visible(timeout=8_000)
        except (BrowserError, AssertionError):
            for _, route, _, _ in SIGNED_IN_SCREENS:
                yield {"route": route, "width": width, "height": height, "passed": False,
                       "errors": ["The synthetic user could not sign in through the browser"]}
            return
        for screen in SIGNED_IN_SCREENS:
            yield inspect_screen(page, screen, (width, height), output, signed_in=True)


def service_origin(value):
    parts = urlsplit(value)
    if (parts.scheme != "http" or not parts.hostname or parts.username or parts.password
            or parts.path not in ("", "/") or parts.query or parts.fragment):
        raise argparse.ArgumentTypeError("Use the disposable service's HTTP origin")
    return f"http://{parts.netloc}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, type=service_origin)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.revision):
        parser.error("Use a full lowercase Git revision")

    args.output.mkdir(parents=True, exist_ok=True)
    report = {"revision": args.revision, "state": "error", "passed": False,
              "fixture": "organizer sample mock and synthetic account", "screens": []}
    user = {"id": "u_browser_audit", "email": "browser-audit@example.com",
            "password": secrets.token_urlsafe(24), "display_name": "Browser Audit"}
    try:
        seed_service(args.base_url, user)
        with sync_playwright() as playwright:
            # Full Chromium honors the same internal-origin flag as the organizer harness.
            browser = playwright.chromium.launch(channel="chromium", args=[
                f"--unsafely-treat-insecure-origin-as-secure={args.base_url}"])
            try:
                report["browser"] = browser.version
                for width, height in VIEWPORTS:
                    report["screens"].extend(verify_viewport(browser, args.base_url, width, height,
                                                            user, args.output))
            finally:
                browser.close()
        report["state"] = "completed"
        report["passed"] = len(report["screens"]) == 12 and all(
            screen["passed"] for screen in report["screens"])
    except ProbeFailure as error:
        report["error"] = str(error)
    except (BrowserError, httpx.HTTPError, KeyError, ValueError) as error:
        report["error"] = f"Fixture or browser setup failed ({type(error).__name__})"

    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Chromium passed {sum(screen['passed'] for screen in report['screens'])}/12 route and viewport checks.")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
