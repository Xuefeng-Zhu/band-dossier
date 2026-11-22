"use strict";

const FIELDS = [
  ["legal_name", "Legal name"], ["hq_city", "Headquarters"], ["ceo", "Chief executive"],
  ["founded_year", "Founded"], ["headcount_range", "Headcount"], ["funding_total", "Total equity funding"],
];
const TITLES = [["cfo", "Chief financial officer"], ["coo", "Chief operating officer"],
  ["cto", "Chief technology officer"]];
const PROVIDER = { nimble: "Nimble", tavily: "Tavily", kernel: "Kernel", browserbase: "Browserbase" };
const KIND = { own: "Company site", filing: "Filing registry", news: "News", aggregator: "Aggregator" };
const LABEL = { known: "Known", unknown: "Unknown", contested: "Contested",
  building: "Building", ready: "Ready", failed: "Failed" };
const SESSION_KEY = "dossier.account";
const main = document.getElementById("content");
const accountArea = document.getElementById("account");
const navigation = document.getElementById("navigation");
const path = location.pathname;
const dateFormat = new Intl.DateTimeFormat("en-US", {
  year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: "UTC",
});
const usdFormat = new Intl.NumberFormat("en-US", {
  style: "currency", currency: "USD", maximumFractionDigits: 0,
});
const integerFormat = new Intl.NumberFormat("en-US");

function node(tag, attributes = {}, ...children) {
  const element = document.createElement(tag);
  for (const [key, value] of Object.entries(attributes)) {
    if (value !== null && value !== undefined) element.setAttribute(key, String(value));
  }
  element.append(...children.flat().filter(child => child !== null && child !== undefined));
  return element;
}

function test(id) {
  return { "data-testid": id };
}

function button(text, id, primary = false) {
  return node("button", { type: "button", class: primary ? "button primary" : "button", ...test(id) }, text);
}

function link(text, href, attributes = {}) {
  return node("a", { href, ...attributes }, text);
}

function domainPath(domain, evidence = false) {
  return "/dossiers/" + encodeURIComponent(domain) + (evidence ? "/evidence" : "");
}

function normalizeDomain(segment) {
  try {
    return decodeURIComponent(segment).trim().toLowerCase().replace(/\.$/, "").replace(/^www\./, "");
  } catch {
    return segment;
  }
}

function normalizedPath(segment, evidence) {
  const domain = normalizeDomain(segment);
  const url = domainPath(domain, evidence);
  if (url !== path) history.replaceState(null, "", url + location.search + location.hash);
  return domain;
}

function heading(title, description, titleAttributes = {}) {
  document.title = title + " · Dossier";
  return node("div", { class: "page-heading" }, node("h1", titleAttributes, title),
    description && node("p", { class: "intro" }, description));
}

function notice(message, mood = "neutral", id) {
  return node("p", { class: "notice " + mood, role: mood === "error" ? "alert" : "status",
    ...(id ? test(id) : {}) }, message);
}

function badge(state, id, exact = false) {
  return node("span", { class: "badge " + state, ...(id ? test(id) : {}) }, exact ? state : LABEL[state] ?? state);
}

function timestamp(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : dateFormat.format(date) + " UTC";
}

function displayValue(field, value) {
  if (field === "funding_total") return usdFormat.format(value);
  if (field === "headcount_range") return value.replace("-", "–");
  return String(value);
}

function sourceLink(url) {
  try {
    const parsed = new URL(url);
    if (["http:", "https:"].includes(parsed.protocol)) {
      return link(parsed.hostname + (parsed.pathname === "/" ? "" : parsed.pathname), url,
        { class: "source-link", target: "_blank", rel: "noopener noreferrer" });
    }
  } catch {
    // A malformed URL can still appear as plain source text.
  }
  return node("span", { class: "source-link" }, url);
}

function currentAccount() {
  try {
    const value = JSON.parse(localStorage.getItem(SESSION_KEY));
    return value && typeof value.token === "string" && typeof value.display_name === "string" ? value : null;
  } catch {
    return null;
  }
}

let account = currentAccount();

function rememberAccount(value) {
  account = value;
  if (value) localStorage.setItem(SESSION_KEY, JSON.stringify(value));
  else localStorage.removeItem(SESSION_KEY);
}

class ApiFailure extends Error {
  constructor(status, message) {
    super(message || "The service could not complete the request.");
    this.status = status;
  }

  get refused() {
    return this.status >= 400 && this.status < 500;
  }
}

function parseJSON(raw) {
  // Parse large API integers before their decimal digits can be rounded by JavaScript.
  const items = /("(?:[^"\\]|\\.)*")|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g;
  const integers = [];
  const tracked = raw.replace(items, (item, quoted, number) => {
    if (quoted || !/^-?\d{16,}$/.test(number) || Number.isSafeInteger(Number(number))) return item;
    const index = integers.push(number) - 1;
    return '{"__dossierInteger":' + index + "}";
  });
  return JSON.parse(tracked, (_, value) => {
    if (value && typeof value === "object" && Object.keys(value).length === 1 &&
        Number.isInteger(value.__dossierInteger) && integers[value.__dossierInteger] !== undefined) {
      return BigInt(integers[value.__dossierInteger]);
    }
    return value;
  });
}

async function api(url, options = {}) {
  const { body, key, timeout, ...request } = options;
  const headers = { Accept: "application/json" };
  if (account) headers.Authorization = "Bearer " + account.token;
  if (key) headers["Idempotency-Key"] = key;
  if (body !== undefined) headers["Content-Type"] = "application/json; charset=utf-8";
  const response = await fetch(url, {
    cache: "no-store", ...request, headers, body,
    ...(timeout ? { signal: AbortSignal.timeout(timeout) } : {}),
  });
  const raw = await response.text();
  let value;
  try {
    value = parseJSON(raw);
  } catch (error) {
    if (response.ok) throw error;
  }
  if (!response.ok) throw new ApiFailure(response.status, value?.error?.message);
  return value;
}

function requestKey() {
  return Array.from(crypto.getRandomValues(new Uint8Array(16)),
    byte => byte.toString(16).padStart(2, "0")).join("");
}

function updateNavigation() {
  const home = link("Dossiers", "/", path === "/" ? { "aria-current": "page" } : {});
  const disputed = link("Contested", "/contested", path === "/contested" ? { "aria-current": "page" } : {});
  navigation.replaceChildren(home, disputed);
  if (account) {
    const logout = button("Log out", "logout-button");
    logout.classList.add("compact");
    logout.addEventListener("click", () => {
      rememberAccount(null);
      location.assign("/login");
    });
    accountArea.replaceChildren(node("span", { class: "current-user", ...test("current-user") },
      account.display_name), logout);
  } else {
    accountArea.replaceChildren(link("Log in", "/login"), link("Sign up", "/signup", { class: "button compact" }));
  }
}

function loginRequired() {
  rememberAccount(null);
  updateNavigation();
  main.replaceChildren(heading("Sign in to Dossier", "Your account gives you access to the shared dossier library."),
    node("div", { class: "actions" }, link("Log in", "/login", { class: "button primary" }),
      link("Create account", "/signup", { class: "button" })));
}

function labeledInput(id, label, options = {}) {
  const input = node("input", { id, ...test(id), ...options });
  return [node("div", { class: "input-group" }, node("label", { for: id }, label), input), input];
}

function showAuth(signup) {
  const mode = signup ? "signup" : "login";
  const [email, emailInput] = labeledInput(mode + "-email", "Email", {
    type: "email", autocomplete: "email", required: true,
  });
  const [password, passwordInput] = labeledInput(mode + "-password", "Password", {
    type: "password", autocomplete: signup ? "new-password" : "current-password", required: true,
  });
  const [displayName, nameInput] = labeledInput("signup-display-name", "Display name", {
    type: "text", autocomplete: "name", required: true,
  });
  const submit = button(signup ? "Create account" : "Log in", mode + "-submit", true);
  submit.type = "submit";
  const feedback = node("div");
  const form = node("form", { class: "auth-form", novalidate: true },
    signup ? displayName : null, email, password, submit, feedback);
  form.addEventListener("submit", async event => {
    event.preventDefault();
    feedback.replaceChildren();
    submit.disabled = true;
    try {
      const data = { email: emailInput.value, password: passwordInput.value };
      if (signup) data.display_name = nameInput.value;
      const user = await api("/auth/" + mode, { method: "POST", body: JSON.stringify(data), timeout: 7000 });
      rememberAccount(user);
      location.assign("/");
    } catch (error) {
      feedback.replaceChildren(notice(error instanceof ApiFailure ? error.message : "Could not reach the service. Try again.",
        "error", "auth-error"));
      submit.disabled = false;
    }
  });
  const title = signup ? "Create an account" : "Log in";
  main.replaceChildren(node("div", { class: "auth-layout" },
    heading(title, signup ? "Research companies by domain and follow the sources behind each value." : "Open the shared library of company dossiers."),
    node("section", { class: "form-panel", "aria-label": title }, form,
      node("p", { class: "auth-switch" }, signup ? "Already have an account? " : "New to Dossier? ",
        signup ? link("Log in", "/login") : link("Create an account", "/signup")))));
}

async function dossierList(query = "") {
  const dossiers = [];
  let hasMore = true;
  while (hasMore) {
    const queryParams = new URLSearchParams({ q: query, offset: String(dossiers.length), limit: "200" });
    const page = await api("/dossiers?" + queryParams);
    dossiers.push(...page.dossiers);
    hasMore = page.has_more && page.dossiers.length > 0;
  }
  return dossiers;
}

function writeAction({ button: submit, feedback, path: url, body, prefix, success, input }) {
  let pending;
  let writing = false;
  return async () => {
    if (writing) return;
    pending ??= { body: body(), key: requestKey() };
    writing = true;
    submit.disabled = true;
    submit.setAttribute("aria-busy", "true");
    if (input) input.readOnly = true;
    const action = prefix === "research" ? "Research" : "Refresh";
    submit.textContent = prefix === "research" ? "Submitting…" : "Requesting…";
    feedback.replaceChildren(notice("Sending request…", "loading"));
    let result;
    try {
      result = await api(url, { method: "POST", ...pending, timeout: 7000 });
      if (!result || typeof result.domain !== "string") throw new Error("Incomplete write response");
    } catch (error) {
      if (error instanceof ApiFailure && error.refused) {
        feedback.replaceChildren(notice(error.message, "error", prefix + "-error"));
        pending = undefined;
        submit.textContent = action;
        if (input) input.readOnly = false;
      } else {
        feedback.replaceChildren(notice(
          "The service response was lost. Retry to check the same request without starting another build.",
          "uncertain", prefix + "-uncertain"));
        submit.textContent = "Retry " + action.toLowerCase();
      }
      writing = false;
      submit.disabled = false;
      submit.removeAttribute("aria-busy");
      return;
    }
    feedback.replaceChildren(notice("Request accepted.", "success"));
    pending = undefined;
    writing = false;
    submit.disabled = false;
    submit.removeAttribute("aria-busy");
    submit.textContent = action;
    if (input) input.readOnly = false;
    success(result);
  };
}

function showList() {
  const [domainField, domain] = labeledInput("research-domain", "Company domain", {
    type: "text", spellcheck: "false", autocapitalize: "none", autocomplete: "off", placeholder: "example.com",
  });
  const submit = button("Research", "research-submit", true);
  submit.type = "submit";
  const feedback = node("div", { class: "action-feedback" });
  const form = node("form", { class: "research-form" }, node("div", { class: "form-row" }, domainField, submit), feedback);
  const write = writeAction({ button: submit, feedback, path: "/dossiers",
    body: () => JSON.stringify({ domain: domain.value }), prefix: "research", input: domain,
    success: item => location.assign(domainPath(item.domain)) });
  form.addEventListener("submit", event => { event.preventDefault(); void write(); });

  const [searchField, search] = labeledInput("dossier-search", "Search dossiers", {
    type: "search", autocomplete: "off", placeholder: "Domain or legal name",
  });
  const collection = node("div", { class: "collection", "aria-live": "polite" });
  main.replaceChildren(heading("Company dossiers", "Research a domain or revisit the evidence behind an existing dossier."),
    node("section", { class: "research-panel" }, node("h2", {}, "Research a company"), form),
    node("section", { class: "list-panel" }, node("div", { class: "section-toolbar" },
      node("h2", {}, "Dossier library"), searchField), collection));
  let revision = 0;
  async function read() {
    const ticket = ++revision;
    if (!collection.firstChild) collection.replaceChildren(notice("Loading dossiers…", "loading"));
    try {
      const items = await dossierList(search.value);
      if (ticket !== revision) return;
      if (!items.length) {
        collection.replaceChildren(notice(search.value ? "No dossiers match this search." : "No dossiers yet. Research a company to get started.",
          "neutral", "empty-dossiers"));
        return;
      }
      collection.replaceChildren(node("div", { class: "rows", ...test("dossier-list") },
        items.map(item => node("a", { href: domainPath(item.domain), class: "dossier-row",
          ...test("dossier-item-" + item.domain), "data-state": item.state },
        node("span", { class: "row-name" }, node("strong", {}, item.domain),
          item.legal_name && node("small", {}, item.legal_name)), badge(item.state)))));
    } catch (error) {
      if (ticket !== revision) return;
      if (error.status === 401) loginRequired();
      else collection.replaceChildren(notice("Dossiers could not be loaded. Change the search or reload the page to try again.", "error"));
    }
  }
  search.addEventListener("input", () => void read());
  void read();
}

function citationView(field, citation, index) {
  return node("li", { class: "citation", ...(field ? test("citation-" + field + "-" + (index + 1)) : {}),
    "data-provider": citation.provider },
  node("blockquote", {}, "“", citation.excerpt, "”"),
  node("div", { class: "source-meta" }, sourceLink(citation.url), node("span", {}, PROVIDER[citation.provider] ?? citation.provider)));
}

function fieldView(field, label, data) {
  const title = node("div", { class: "field-value" }, node("h2", {}, label),
    data.value === null
      ? node("p", { class: "unknown-text" }, "No supported value")
      : node("p", { class: "value", ...test("field-value-" + field), "data-value": data.value },
        displayValue(field, data.value)),
    badge(data.status, data.status === "contested" ? "field-contested-" + field : null));
  return node("section", { class: "field", ...test("field-" + field), "data-status": data.status },
    title, node("ul", { class: "citations", ...test("field-citations-" + field) },
      data.citations.map((citation, index) => citationView(field, citation, index))));
}

function candidateView(field, candidate, index) {
  return node("li", {
    class: candidate.selected ? "candidate chosen" : "candidate",
    ...(field ? test("candidate-" + field + "-" + (index + 1)) : {}),
    "data-value": candidate.value, "data-provider": candidate.provider, "data-kind": candidate.kind ?? "",
    "data-url": candidate.url, "data-published-at": candidate.published_at ?? "", "data-selected": candidate.selected,
  }, node("div", { class: "candidate-value" }, node("strong", {}, displayValue(field, candidate.value)),
    candidate.selected ? node("span", { class: "badge known" }, "Selected") : null),
  node("blockquote", {}, "“", candidate.excerpt, "”"),
  node("div", { class: "source-meta" }, sourceLink(candidate.url),
    node("span", {}, PROVIDER[candidate.provider] ?? candidate.provider),
    node("span", {}, KIND[candidate.kind] ?? "Kind unrecorded"),
    candidate.published_at ? node("time", { datetime: candidate.published_at }, timestamp(candidate.published_at))
      : node("span", {}, "Publication date unavailable")));
}

function evidenceView(field, label, data) {
  return node("section", { class: "evidence-field" }, node("h2", {}, label),
    node("ol", { class: "candidates", ...test("evidence-" + field) },
      data.candidates.length ? data.candidates.map((candidate, index) => candidateView(field, candidate, index))
        : node("li", {}, notice("No candidates for this field.", "neutral", "evidence-empty-" + field))));
}

function executiveView(data, evidence) {
  if (!data) return null;
  if (evidence) {
    return node("section", { class: "evidence-field executives" }, node("h2", {}, "Executives"),
      TITLES.map(([title, label]) => {
        const candidates = data.candidates.filter(candidate => candidate.title === title);
        return node("section", { class: "executive-group" }, node("h3", {}, label),
          candidates.length ? node("ol", { class: "candidates" },
            candidates.map((candidate, index) => candidateView(null, candidate, index)))
            : notice("No candidates for this title."));
      }));
  }
  const members = data.value ?? [];
  return node("section", { class: "field executives" + (data.status === "contested" ? " divided" : "") },
    node("div", { class: "field-value" }, node("h2", {}, "Executives"),
      badge(data.status),
      members.length ? node("dl", { class: "executive-names" }, members.flatMap(member => [
        node("dt", {}, TITLES.find(([title]) => title === member.title)?.[1] ?? member.title.toUpperCase()),
        node("dd", {}, member.name),
      ])) : node("p", { class: "unknown-text" }, "No supported executives")),
    node("ul", { class: "citations" }, data.citations.map((citation, index) => citationView(null, citation, index))));
}

function investorView(data, evidence) {
  if (!data) return null;
  if (evidence) {
    return node("section", { class: "evidence-field executives" }, node("h2", {}, "Investors"),
      data.candidates.length
        ? node("ol", { class: "candidates" }, data.candidates.map((candidate, index) => candidateView(null, candidate, index)))
        : notice("No investor candidates."));
  }
  return node("section", { class: "field executives" },
    node("div", { class: "field-value" }, node("h2", {}, "Investors"), badge(data.status),
      data.value ? node("ul", { class: "investor-names" }, data.value.map(name => node("li", {}, name)))
        : node("p", { class: "unknown-text" }, "No supported investors")),
    node("ul", { class: "citations" }, data.citations.map((citation, index) => citationView(null, citation, index))));
}

function showDossier(domain, evidence) {
  const readFeedback = node("div", { class: "action-feedback" });
  const writeFeedback = node("div", { class: "action-feedback" });
  const content = node("div", { class: "records" });
  const summary = node("div", { class: "dossier-summary", "aria-live": "polite" });
  const reload = button("Reload", "dossier-reload");
  const refresh = button("Refresh", "dossier-refresh", true);
  const navigationLink = evidence ? link("Back to dossier", domainPath(domain))
    : link("View evidence", domainPath(domain, true), { ...test("dossier-evidence-link") });
  const title = heading(evidence ? "Evidence for " + domain : domain, null,
    evidence ? {} : test("dossier-domain"));
  const actions = evidence ? node("div", { class: "actions" }, navigationLink)
    : node("div", { class: "actions" }, navigationLink, reload, refresh);
  main.replaceChildren(node("p", { class: "breadcrumbs" }, link("Dossiers", "/"), " / ", evidence ? "Evidence" : "Company profile"),
    node("div", { class: "detail-toolbar" }, title, actions), summary, writeFeedback, readFeedback, content);
  let issued = 0;
  let applied = 0;
  let invalidBefore = 0;
  let timer;

  function poll(building) {
    if (building && !timer) timer = setInterval(() => void read(), 1500);
    else if (!building && timer) {
      clearInterval(timer);
      timer = undefined;
    }
  }

  function render(dossier) {
    summary.replaceChildren(
      badge(dossier.state, "dossier-state", true),
      node("span", { class: "metric" }, node("span", {}, "Research spend"),
        node("strong", { ...test("dossier-spent"), "data-units": dossier.spent_units },
          integerFormat.format(dossier.spent_units) + " units")),
      dossier.researched_at ? node("span", { class: "metric" }, node("span", {}, "Last researched"),
        node("time", { ...test("dossier-researched-at"), datetime: dossier.researched_at }, timestamp(dossier.researched_at))) : null);
    const rows = FIELDS.map(([field, label]) => evidence
      ? evidenceView(field, label, dossier.fields[field]) : fieldView(field, label, dossier.fields[field]));
    const executives = executiveView(dossier.fields.executives, evidence);
    if (executives) rows.push(executives);
    const investors = investorView(dossier.fields.investors, evidence);
    if (investors) rows.push(investors);
    content.replaceChildren(...rows);
    readFeedback.replaceChildren(
      ...(dossier.state === "building" ? [notice("Research is running. This page will update when it finishes.", "loading")]
        : dossier.state === "failed" ? [notice("The last build failed. Any previously researched values appear below.", "error")] : []));
    if (!refresh.hasAttribute("aria-busy")) refresh.disabled = false;
    poll(dossier.state === "building");
  }

  async function read() {
    const ticket = ++issued;
    try {
      const dossier = await api(domainPath(domain));
      if (ticket < applied || ticket <= invalidBefore) return;
      applied = ticket;
      render(dossier);
    } catch (error) {
      if (ticket < applied || ticket <= invalidBefore) return;
      applied = ticket;
      if (error.status === 401) {
        poll(false);
        loginRequired();
      } else if (error.status === 404 || error.status === 422) {
        poll(false);
        summary.replaceChildren();
        content.replaceChildren(notice("No dossier exists for this domain.", "neutral", "dossier-not-found"));
        readFeedback.replaceChildren();
        refresh.disabled = true;
      } else {
        readFeedback.replaceChildren(notice("This dossier could not be loaded. Try reloading it.", "error"));
      }
    }
  }

  reload.addEventListener("click", () => void read());
  const write = writeAction({ button: refresh, feedback: writeFeedback, path: domainPath(domain) + "/refresh",
    body: () => undefined, prefix: "refresh",
    success: result => {
      invalidBefore = issued;
      if (result.state === "building") poll(true);
      void read();
    } });
  refresh.addEventListener("click", () => void write());
  readFeedback.replaceChildren(notice("Loading dossier…", "loading"));
  void read();
}

async function showContested() {
  const content = node("div", { class: "records" }, notice("Loading contested fields…", "loading"));
  main.replaceChildren(heading("Contested fields", "Compare values when the sources disagree."), content);
  try {
    const items = await dossierList();
    const dossiers = [];
    for (let start = 0; start < items.length; start += 12) {
      dossiers.push(...await Promise.all(items.slice(start, start + 12).map(item => api(domainPath(item.domain)))));
    }
    const contested = [];
    for (const dossier of dossiers) {
      for (const [field, label] of FIELDS) {
        const data = dossier.fields[field];
        if (data.status !== "contested") continue;
        const values = [...new Set(data.candidates.map(candidate => candidate.value))];
        contested.push(node("article", { class: "dispute",
          ...test("contested-item-" + dossier.domain + "-" + field), "data-value": data.value },
        node("div", {}, node("h2", {}, label), node("p", { class: "domain-label" }, dossier.domain),
          link("View evidence", domainPath(dossier.domain, true))),
        node("ul", {}, values.map(value => node("li", {}, displayValue(field, value),
          value === data.value ? node("span", { class: "badge known" }, "Selected") : null)))));
      }
    }
    content.replaceChildren(contested.length
      ? node("div", { class: "disputes", ...test("contested-list") }, contested)
      : notice("No contested fields across the dossier library.", "neutral", "empty-contested"));
  } catch (error) {
    if (error.status === 401) loginRequired();
    else content.replaceChildren(notice("Contested fields could not be loaded. Reload the page to try again.", "error"));
  }
}

updateNavigation();
if (path === "/login" || path === "/signup") {
  showAuth(path === "/signup");
} else if (!account) {
  loginRequired();
} else if (path === "/contested") {
  void showContested();
} else {
  const match = path.match(/^\/dossiers\/([^/]+)(\/evidence)?$/);
  if (match) showDossier(normalizedPath(match[1], Boolean(match[2])), Boolean(match[2]));
  else showList();
}
