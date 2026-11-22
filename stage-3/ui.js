"use strict";

const fields = [
  ["legal_name", "Legal name"], ["hq_city", "Headquarters"], ["ceo", "CEO"],
  ["founded_year", "Founded"], ["headcount_range", "Headcount"], ["funding_total", "Equity funding"],
];
const dossierFields = [...fields, ["executives", "Executives"]];
const kindNames = { own: "Company site", filing: "Filing", news: "News", aggregator: "Aggregator" };
const providerNames = { nimble: "Nimble", tavily: "Tavily", kernel: "Kernel", browserbase: "Browserbase" };
const main = document.querySelector("#main");
const storageKey = "dossier-session";
const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const dates = new Intl.DateTimeFormat("en-US", {
  dateStyle: "medium", timeStyle: "short", timeZone: "UTC",
});
const digits = new Intl.NumberFormat("en-US", { useGrouping: false, maximumFractionDigits: 0 });

function readSession() {
  try { return JSON.parse(localStorage.getItem(storageKey)); }
  catch { return null; }
}

let session = readSession();

function node(tag, text, options = {}) {
  const element = document.createElement(tag);
  if (text != null) element.textContent = text;
  if (options.className) element.className = options.className;
  if (options.id) element.dataset.testid = options.id;
  if (options.href) element.href = options.href;
  return element;
}

function button(text, id, primary = false, type = "button") {
  const element = node("button", text, { className: primary ? "button primary" : "button", id });
  element.type = type;
  return element;
}

function input(label, id, { type = "text", autocomplete = "", placeholder = "" } = {}) {
  const group = node("div", null, { className: "input-group" });
  const caption = node("label", label);
  const control = node("input", null, { id });
  control.id = id;
  control.type = type;
  control.autocomplete = autocomplete;
  control.placeholder = placeholder;
  caption.htmlFor = id;
  group.append(caption, control);
  return { group, control };
}

function feedback(text, tone, id) {
  const element = node("p", text, { className: "feedback is-" + tone, id });
  element.setAttribute("role", tone === "error" ? "alert" : "status");
  return element;
}

function badge(label, tone, id) {
  return node("span", label, { className: "badge is-" + tone, id });
}

function back(label, href) {
  return node("a", "← " + label, { className: "back", href });
}

function intro(title, detail) {
  const section = node("div", null, { className: "intro" });
  section.append(node("h1", title));
  if (detail) section.append(node("p", detail, { className: "lede" }));
  return section;
}

function empty(text, id) {
  return node("p", text, { className: "panel empty", id });
}

function pageTitle(title) {
  document.title = title + " · Dossier";
}

function domainPath(domain) {
  return "/dossiers/" + encodeURIComponent(domain);
}

function normalizeDomain(text) {
  return text.trim().toLowerCase().replace(/\.$/, "").replace(/^www\./, "");
}

function dataValue(value) {
  return typeof value === "number" ? digits.format(value) : String(value);
}

function displayValue(field, value) {
  if (value == null) return "Unknown";
  if (field === "funding_total") return money.format(value);
  if (field === "headcount_range") return value.replace("-", "–");
  if (field === "executives" && Array.isArray(value)) {
    return value.map((member) => member.title.toUpperCase() + " " + member.name).join(" · ");
  }
  return String(value);
}

function dateText(value) {
  return dates.format(new Date(value)) + " UTC";
}

function displayHost(url) {
  try { return new URL(url).hostname; }
  catch { return url; }
}

function source(citation, details = []) {
  const row = node("p", null, { className: "source-meta" });
  const link = node("a", displayHost(citation.url));
  try {
    const parsed = new URL(citation.url);
    if (parsed.protocol === "https:" || parsed.protocol === "http:") {
      link.href = citation.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
    }
  } catch { /* A link is omitted for unavailable URLs. */ }
  row.append(link, document.createTextNode(" · " + [providerNames[citation.provider] || citation.provider, ...details].join(" · ")));
  return row;
}

function quote(excerpt) {
  return node("blockquote", "“" + excerpt + "”");
}

function authLink(destination, route = "/login") {
  return route + "?next=" + encodeURIComponent(destination);
}

function afterAuth() {
  const target = new URLSearchParams(location.search).get("next");
  if (target?.startsWith("/")) {
    try {
      const url = new URL(target, location.href);
      if (url.origin === location.origin) return url.pathname + url.search + url.hash;
    } catch { /* The default destination is the dossier list. */ }
  }
  return "/";
}

function account() {
  const area = document.querySelector("#account");
  if (!session?.token) {
    area.replaceChildren(node("a", "Sign in", { href: "/login" }), node("a", "Sign up", { href: "/signup" }));
    return;
  }
  const displayName = node("span", session.display_name, { id: "current-user", className: "account-name" });
  displayName.title = session.display_name;
  const logout = node("button", "Sign out", { id: "logout-button" });
  logout.type = "button";
  logout.addEventListener("click", () => {
    localStorage.removeItem(storageKey);
    location.assign("/login");
  });
  area.replaceChildren(displayName, logout);
}

class Refused extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

async function api(path, { method = "GET", body, key, signal } = {}) {
  const headers = { Accept: "application/json" };
  if (session?.token) headers.Authorization = "Bearer " + session.token;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (key) headers["Idempotency-Key"] = key;
  const response = await fetch(path, {
    method, headers, signal, cache: "no-store",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status >= 500) throw new Error("The server could not confirm the result.");
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Refused(response.status, detail?.error?.message || "The request was refused.");
  }
  return response.json();
}

function readProblem(error, box) {
  if (error instanceof Refused && error.status === 401) {
    localStorage.removeItem(storageKey);
    location.replace(authLink(location.pathname + location.search));
    return;
  }
  box.replaceChildren(feedback(error instanceof Refused ? error.message : "Could not load this data. Try again.", "error"));
}

function newKey() {
  return Array.from(crypto.getRandomValues(new Uint8Array(24)), value => value.toString(16).padStart(2, "0")).join("");
}

function writeAction({ submit, messages, label, prefix, takeBody, path, done, lockInput }) {
  let pending = null;
  let busy = false;
  return async (event) => {
    event.preventDefault();
    if (busy) return;
    if (!pending) pending = { key: newKey(), body: takeBody?.() };
    busy = true;
    submit.disabled = true;
    submit.dataset.submitting = "true";
    submit.textContent = prefix === "refresh" ? "Requesting…" : "Submitting…";
    if (lockInput) lockInput.disabled = true;
    messages.replaceChildren(feedback("Waiting for Dossier…", "loading"));
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 6000);
    try {
      const result = await api(path, { method: "POST", ...pending, signal: controller.signal });
      if (!result?.domain || !result.dossier_id) throw new Error("Incomplete write response");
      pending = null;
      messages.replaceChildren();
      done(result);
    } catch (error) {
      if (error instanceof Refused) {
        pending = null;
        messages.replaceChildren(feedback(error.message, "error", prefix + "-error"));
      } else {
        messages.replaceChildren(feedback(
          "Dossier could not confirm this request. Retry to check the same request.",
          "uncertain", prefix + "-uncertain",
        ));
      }
    } finally {
      clearTimeout(timer);
      busy = false;
      submit.disabled = false;
      delete submit.dataset.submitting;
      submit.textContent = pending ? "Retry " + label.toLowerCase() : label;
      if (lockInput) lockInput.disabled = Boolean(pending);
    }
  };
}

function authScreen(signup) {
  const heading = signup ? "Create an account" : "Sign in";
  pageTitle(heading);
  const prefix = signup ? "signup" : "login";
  const screen = node("section", null, { className: "auth" });
  const form = node("form", null, { className: "panel auth-form" });
  form.noValidate = true;
  const email = input("Email", prefix + "-email", { type: "email", autocomplete: "email" });
  const password = input("Password", prefix + "-password", {
    type: "password", autocomplete: signup ? "new-password" : "current-password",
  });
  const name = signup ? input("Display name", "signup-display-name", { autocomplete: "name" }) : null;
  const submit = button(heading, prefix + "-submit", true, "submit");
  const messages = node("div");
  form.append(email.group, password.group);
  if (name) form.append(name.group);
  form.append(submit, messages);
  const alternate = node("p", signup ? "Already have an account? " : "New to Dossier? ", { className: "auth-footer" });
  alternate.append(node("a", signup ? "Sign in" : "Create an account", {
    href: authLink(afterAuth(), signup ? "/login" : "/signup"),
  }));
  screen.append(intro(heading), form, alternate);
  main.replaceChildren(screen);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (submit.disabled) return;
    submit.disabled = true;
    messages.replaceChildren(feedback("Contacting Dossier…", "loading"));
    const body = { email: email.control.value, password: password.control.value };
    if (name) body.display_name = name.control.value;
    try {
      session = await api("/auth/" + prefix, { method: "POST", body });
      localStorage.setItem(storageKey, JSON.stringify(session));
      location.assign(afterAuth());
    } catch (error) {
      messages.replaceChildren(feedback(error.message, "error", "auth-error"));
    } finally {
      submit.disabled = false;
    }
  });
}

async function dossiers(query = "") {
  const rows = [];
  let offset = 0;
  while (true) {
    const params = new URLSearchParams({ q: query, limit: "200", offset: String(offset) });
    const result = await api("/dossiers?" + params);
    rows.push(...result.dossiers);
    if (!result.has_more || !result.dossiers.length) return rows;
    offset += result.dossiers.length;
  }
}

function listScreen() {
  pageTitle("Dossiers");
  const research = node("form", null, { className: "panel research" });
  const row = node("div", null, { className: "form-row" });
  const domain = input("Company domain", "research-domain", { placeholder: "example.com", autocomplete: "off" });
  domain.control.spellcheck = false;
  const launch = button("Research", "research-submit", true, "submit");
  const messages = node("div");
  row.append(domain.group, launch);
  research.append(row, messages);
  research.addEventListener("submit", writeAction({
    submit: launch, messages, label: "Research", prefix: "research", path: "/dossiers",
    takeBody: () => ({ domain: domain.control.value }), lockInput: domain.control,
    done: (result) => location.assign(domainPath(result.domain)),
  }));
  const toolbar = node("div", null, { className: "list-toolbar" });
  const search = input("Search dossiers", "dossier-search", { placeholder: "Domain or legal name" });
  toolbar.append(node("h2", "Company dossiers"), search.group);
  const results = node("div");
  main.replaceChildren(intro("Dossiers", "Research a company by domain and read the sources behind its profile."), research, toolbar, results);
  let latest = 0;
  async function load() {
    const sequence = ++latest;
    results.replaceChildren(feedback("Loading dossiers…", "loading"));
    try {
      const rows = await dossiers(search.control.value);
      if (sequence !== latest) return;
      if (!rows.length) {
        results.replaceChildren(empty(search.control.value ? "No dossiers match this search." : "No dossiers yet.", "empty-dossiers"));
        return;
      }
      const list = node("div", null, { className: "panel", id: "dossier-list" });
      for (const dossier of rows) {
        const item = node("article", null, { className: "list-row", id: "dossier-item-" + dossier.domain });
        item.dataset.state = dossier.state;
        item.append(node("a", dossier.domain, { href: domainPath(dossier.domain) }), badge(dossier.state, dossier.state));
        if (dossier.legal_name) item.append(node("p", dossier.legal_name, { className: "data-summary" }));
        list.append(item);
      }
      results.replaceChildren(list);
    } catch (error) {
      if (sequence === latest) readProblem(error, results);
    }
  }
  search.control.addEventListener("input", load);
  load();
}

function detailFields(dossier) {
  const panel = node("div", null, { className: "panel fields" });
  for (const [field, label] of dossierFields) {
    const item = dossier.fields[field];
    if (!item) continue;
    const executives = field === "executives";
    const row = node("section", null, { className: "field", id: executives ? null : "field-" + field });
    if (!executives) row.dataset.status = item.status;
    const statement = node("div", null, { className: "value-line" });
    if (item.value !== null) {
      const value = node("span", displayValue(field, item.value), {
        id: executives ? null : "field-value-" + field, className: "field-value",
      });
      if (!executives) value.dataset.value = dataValue(item.value);
      statement.append(value);
    }
    const status = item.status[0].toUpperCase() + item.status.slice(1);
    statement.append(badge(status, item.status, !executives && item.status === "contested" ? "field-contested-" + field : null));
    const citations = node("ul", null, { className: "citations", id: executives ? null : "field-citations-" + field });
    item.citations.forEach((citation, index) => {
      const entry = node("li", null, { id: executives ? null : "citation-" + field + "-" + (index + 1) });
      entry.dataset.provider = citation.provider;
      const candidate = item.candidates?.find((candidate) => candidate.url === citation.url && candidate.excerpt === citation.excerpt);
      const extra = candidate ? [kindNames[candidate.kind] || "Unclassified", candidate.published_at ? dateText(candidate.published_at) : "Publication date unavailable"] : [];
      entry.append(quote(citation.excerpt), source(citation, extra));
      citations.append(entry);
    });
    row.append(node("h2", label), statement, citations);
    panel.append(row);
  }
  return panel;
}

function detailScreen(domain) {
  pageTitle(domain);
  const path = domainPath(domain);
  const heading = node("h1", domain, { id: "dossier-domain" });
  const title = node("div", null, { className: "title-line" });
  title.append(heading);
  const meta = node("div", null, { className: "meta" });
  const overview = node("div");
  overview.append(title, meta);
  const actions = node("div", null, { className: "actions" });
  const reload = button("Reload", "dossier-reload");
  const refresh = button("Refresh", "dossier-refresh", true);
  refresh.disabled = true;
  actions.append(node("a", "View evidence", { className: "button", id: "dossier-evidence-link", href: path + "/evidence" }), reload, refresh);
  const header = node("div", null, { className: "detail-top" });
  header.append(overview, actions);
  const messages = node("div");
  const readMessages = node("div");
  const result = node("div");
  main.replaceChildren(back("Back to dossiers", "/"), header, messages, readMessages, result);

  let issued = 0;
  let applied = 0;
  let minimumRead = 0;
  let poll = null;
  function stopPolling() {
    clearInterval(poll);
    poll = null;
  }
  async function load() {
    const sequence = ++issued;
    if (!result.firstChild) readMessages.replaceChildren(feedback("Loading dossier…", "loading"));
    try {
      const dossier = await api(path);
      if (sequence < applied || sequence < minimumRead) return;
      applied = sequence;
      readMessages.replaceChildren();
      heading.textContent = dossier.domain;
      title.replaceChildren(heading, badge(dossier.state, dossier.state, "dossier-state"));
      const spent = node("span", dossier.spent_units.toLocaleString("en-US") + " research units", { id: "dossier-spent" });
      spent.dataset.units = String(dossier.spent_units);
      meta.replaceChildren();
      if (dossier.researched_at) {
        const time = node("time", dateText(dossier.researched_at), { id: "dossier-researched-at" });
        time.dateTime = dossier.researched_at;
        meta.append(time);
      }
      meta.append(spent);
      refresh.disabled = refresh.dataset.submitting === "true";
      result.replaceChildren(detailFields(dossier));
      if (dossier.state === "building") {
        if (poll === null) poll = setInterval(load, 1350);
      } else {
        stopPolling();
      }
    } catch (error) {
      if (sequence < applied || sequence < minimumRead) return;
      applied = sequence;
      if (error instanceof Refused && error.status === 404) {
        stopPolling();
        title.replaceChildren(heading);
        meta.replaceChildren();
        readMessages.replaceChildren();
        refresh.disabled = true;
        result.replaceChildren(empty("No dossier exists for this domain.", "dossier-not-found"));
      } else {
        readProblem(error, readMessages);
      }
    }
  }
  reload.addEventListener("click", load);
  refresh.addEventListener("click", writeAction({
    submit: refresh, messages, label: "Refresh", prefix: "refresh", path: path + "/refresh",
    done: () => {
      minimumRead = issued + 1;
      messages.append(feedback("Refresh requested.", "success"));
      load();
    },
  }));
  window.addEventListener("pagehide", stopPolling);
  load();
}

function evidenceScreen(domain) {
  pageTitle("Evidence for " + domain);
  const path = domainPath(domain);
  const result = node("div");
  result.append(feedback("Loading evidence…", "loading"));
  main.replaceChildren(back("Back to " + domain, path), intro("Evidence", domain), result);
  api(path).then((dossier) => {
    const panel = node("div", null, { className: "panel fields" });
    for (const [field, label] of dossierFields) {
      if (!dossier.fields[field]) continue;
      const executives = field === "executives";
      const row = node("section", null, { className: "evidence-row" });
      const candidates = node("div", null, { className: "candidates", id: executives ? null : "evidence-" + field });
      const records = dossier.fields[field].candidates || [];
      records.forEach((candidate, index) => {
        const item = node("article", null, { className: "candidate",
          id: executives ? null : "candidate-" + field + "-" + (index + 1) });
        Object.assign(item.dataset, {
          value: dataValue(candidate.value), provider: candidate.provider, kind: candidate.kind || "",
          url: candidate.url, publishedAt: candidate.published_at || "", selected: String(candidate.selected),
        });
        const headline = node("div", null, { className: "value-line" });
        const value = executives ? candidate.title.toUpperCase() + " " + candidate.value : displayValue(field, candidate.value);
        headline.append(node("span", value, { className: "field-value" }));
        if (candidate.selected) headline.append(badge("Selected", "known"));
        item.append(headline, quote(candidate.excerpt), source(candidate, [
          kindNames[candidate.kind] || "Unclassified",
          candidate.published_at ? dateText(candidate.published_at) : "Publication date unavailable",
        ]));
        candidates.append(item);
      });
      if (!records.length) candidates.append(node("p", "No supported evidence.", {
        className: "muted", id: executives ? null : "evidence-empty-" + field,
      }));
      row.append(node("h2", label), candidates);
      panel.append(row);
    }
    result.replaceChildren(panel);
  }).catch((error) => readProblem(error, result));
}

async function contestedScreen() {
  pageTitle("Contested fields");
  const result = node("div");
  result.append(feedback("Loading contested fields…", "loading"));
  main.replaceChildren(intro("Contested fields", "Compare the values that credible sources report differently."), result);
  try {
    const rows = await dossiers();
    const list = node("div", null, { className: "panel", id: "contested-list" });
    for (let offset = 0; offset < rows.length; offset += 12) {
      const profiles = await Promise.all(rows.slice(offset, offset + 12).map((row) => api(domainPath(row.domain))));
      for (const dossier of profiles) {
        for (const [field, label] of fields) {
          const data = dossier.fields[field];
          if (data.status !== "contested") continue;
          const item = node("article", null, { className: "list-row", id: "contested-item-" + dossier.domain + "-" + field });
          item.dataset.value = dataValue(data.value);
          item.append(node("a", dossier.domain + " · " + label, { href: domainPath(dossier.domain) + "/evidence" }), badge("Contested", "contested"));
          const values = [...new Set(data.candidates.map((candidate) => candidate.value))];
          item.append(node("p", values.map((value) => displayValue(field, value)).join(" · "), { className: "data-summary" }));
          list.append(item);
        }
      }
    }
    result.replaceChildren(list.childElementCount ? list : empty("No fields are contested.", "empty-contested"));
  } catch (error) {
    readProblem(error, result);
  }
}

function start() {
  account();
  const path = location.pathname;
  if (path === "/signup" || path === "/login") {
    authScreen(path === "/signup");
    return;
  }
  if (!session?.token) {
    location.replace(authLink(path + location.search));
    return;
  }
  if (path === "/contested") {
    document.querySelector("#nav-contested").setAttribute("aria-current", "page");
    contestedScreen();
  } else if (path.startsWith("/dossiers/")) {
    document.querySelector("#nav-dossiers").setAttribute("aria-current", "location");
    const evidence = path.endsWith("/evidence");
    const raw = path.slice("/dossiers/".length, evidence ? -"/evidence".length : undefined);
    let domain;
    try { domain = normalizeDomain(decodeURIComponent(raw)); }
    catch { domain = raw; }
    if (evidence) evidenceScreen(domain);
    else detailScreen(domain);
  } else {
    document.querySelector("#nav-dossiers").setAttribute("aria-current", "page");
    listScreen();
  }
}

start();
