"use strict";

const fieldNames = {
  legal_name: "Legal name",
  hq_city: "Headquarters",
  ceo: "Chief executive",
  founded_year: "Founded",
  headcount_range: "Headcount",
  funding_total: "Total equity funding",
};
const statusNames = {known: "Known", unknown: "Unknown", contested: "Contested"};
const providerNames = {nimble: "Nimble", tavily: "Tavily", kernel: "Kernel", browserbase: "Browserbase"};
const kindNames = {own: "Company site", filing: "Filing", news: "News", aggregator: "Aggregator"};
const screen = document.body.dataset.screen;
const domain = document.body.dataset.domain;
const main = document.querySelector("#main");
const sessionKey = "dossier.session";
const integer = new Intl.NumberFormat("en-US");
const dollars = new Intl.NumberFormat("en-US", {style: "currency", currency: "USD", maximumFractionDigits: 0});
const calendar = new Intl.DateTimeFormat("en-US", {
  dateStyle: "medium", timeStyle: "short", timeZone: "UTC",
});
const entities = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
const escapeText = value => String(value ?? "").replace(/[&<>"']/g, char => entities[char]);
const readTest = id => document.querySelector(`[data-testid="${id}"]`);
const route = company => `/dossiers/${encodeURIComponent(company.startsWith("www.") ? "www." + company : company)}`;

function sessionFromStorage() {
  try {
    const session = JSON.parse(localStorage.getItem(sessionKey));
    return session && typeof session.token === "string" && typeof session.displayName === "string"
      ? session : null;
  } catch {
    return null;
  }
}

let session = sessionFromStorage();

function setSession(next) {
  session = next;
  if (next) localStorage.setItem(sessionKey, JSON.stringify(next));
  else localStorage.removeItem(sessionKey);
}

function renderSession() {
  const account = document.querySelector("#session");
  if (session) {
    account.innerHTML = `<span class="account-name" data-testid="current-user">${escapeText(session.displayName)}</span>
      <button class="link-button" type="button" data-testid="logout-button">Sign out</button>`;
    readTest("logout-button").addEventListener("click", () => {
      setSession(null);
      location.assign("/login");
    });
  } else {
    account.innerHTML = '<a href="/login">Log in</a><a class="join-link" href="/signup">Sign up</a>';
  }
  const active = document.querySelector(screen === "contested" ? "#contested-nav" : "#workspace-nav");
  if (!["login", "signup"].includes(screen)) active.setAttribute("aria-current", "page");
}

class Refusal extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

async function api(path, method = "GET", options = {}) {
  const headers = {"Accept": "application/json"};
  if (session) headers.Authorization = `Bearer ${session.token}`;
  if (options.key) headers["Idempotency-Key"] = options.key;
  let body;
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }
  const response = await fetch(path, {method, headers, body, cache: "no-store"});
  if (response.status >= 400 && response.status < 500) {
    const error = await response.json().catch(() => ({}));
    throw new Refusal(response.status, error.error?.message || "The server refused this request.");
  }
  if (!response.ok) throw new Error("The server did not confirm the request.");
  return response.json();
}

function pageTitle(title) {
  document.title = title === "Company dossiers" ? "Dossier — Company research" : `${title} · Dossier`;
}

function mount(html) {
  main.innerHTML = html;
  main.removeAttribute("aria-busy");
}

function notice(text, tone = "", testId = "") {
  const id = testId ? ` data-testid="${testId}"` : "";
  return `<p class="notice ${tone}"${id} role="${tone === "error" ? "alert" : "status"}">${escapeText(text)}</p>`;
}

function loadError(error) {
  if (error instanceof Refusal && error.status === 401) {
    setSession(null);
    renderSession();
    return notice("Your session ended. Log in to continue.", "error");
  }
  return notice("The data could not be loaded. Try again.", "error");
}

function signedOut() {
  return `<div class="empty signed-out"><h2>Log in to your workspace</h2>
    <p>Open existing dossiers or start research by company domain.</p>
    <a class="button primary" href="/login">Log in</a></div>`;
}

function buildState(state) {
  return `<span data-testid="dossier-state" class="tag state ${escapeText(state)}">${escapeText(state)}</span>`;
}

function formatValue(field, value) {
  if (field === "funding_total") return dollars.format(value);
  if (field === "headcount_range") {
    return value.split("-").map(limit => integer.format(Number.parseInt(limit, 10)))
      .join("–") + (value.endsWith("+") ? "+" : "");
  }
  return String(value);
}

function formatTime(value) {
  if (!value) return "Date unavailable";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : `${calendar.format(date)} UTC`;
}

function sourceLink(url) {
  const address = new URL(url, location.origin);
  if (!["http:", "https:"].includes(address.protocol)) return "";
  return `<a class="source-link" href="${escapeText(url)}" target="_blank" rel="noopener noreferrer">${escapeText(address.hostname)}<span aria-hidden="true"> ↗</span></a>`;
}

function citation(cite, field, index, source) {
  return `<div class="citation" data-testid="citation-${field}-${index + 1}" data-provider="${escapeText(cite.provider)}">
    <blockquote>“${escapeText(cite.excerpt)}”</blockquote>
    <div class="source-meta">${sourceLink(cite.url)}<span>${escapeText(providerNames[cite.provider])}</span>
      ${source ? `<span>${escapeText(kindNames[source.kind] || "Unclassified source")}</span>
        <span>${escapeText(formatTime(source.published_at))}</span>` : ""}</div>
  </div>`;
}

function fieldsMarkup(fields) {
  const core = Object.entries(fieldNames).map(([field, name]) => {
    const item = fields[field];
    const status = item.status;
    const supporting = item.candidates.filter(candidate => candidate.value === item.value);
    const contested = status === "contested" ? ` data-testid="field-contested-${field}"` : "";
    const value = item.value === null ? '<p class="field-value no-value">—</p>' :
      `<p class="field-value" data-testid="field-value-${field}" data-value="${escapeText(item.value)}">${escapeText(formatValue(field, item.value))}</p>`;
    return `<article class="field-row" data-testid="field-${field}" data-status="${status}">
      <div class="field-summary"><h3>${name}</h3>${value}
        <span class="tag ${status}"${contested}>${statusNames[status]}</span></div>
      <div class="citations" data-testid="field-citations-${field}">
        ${item.citations.map((cite, index) => citation(cite, field, index, supporting[index])).join("")}
      </div>
    </article>`;
  }).join("");
  return core + executivesMarkup(fields.executives) + investorsMarkup(fields.investors);
}

function investorsMarkup(item) {
  if (!item?.value) return "";
  const candidates = item.candidates.filter(candidate => candidate.selected);
  return `<article class="field-row">
    <div class="field-summary"><h3>Investors</h3>
      <span class="tag ${item.corroborated ? 'known' : 'unknown'}">${item.corroborated ? "Corroborated" : "Known"}</span></div>
    <div class="citations">${item.value.map(name => `<div class="citation">
      <h4 class="executive-name">${escapeText(name)}</h4>
      ${candidates.filter(source => source.value === name).map(source =>
        `<blockquote>“${escapeText(source.excerpt)}”</blockquote>
          <div class="source-meta">${sourceLink(source.url)}<span>${escapeText(kindNames[source.kind] || "Unclassified source")}</span>
            <span>${escapeText(source.origin)}</span></div>`).join("")}</div>`).join("")}</div>
  </article>`;
}

function executivesMarkup(item) {
  if (!item?.value) return "";
  return `<article class="field-row" data-status="${item.status}">
    <div class="field-summary"><h3>Other executives</h3>
      <span class="tag ${item.status}">${statusNames[item.status]}</span></div>
    <div class="citations">${item.value.map(member => {
      const sources = item.candidates.filter(candidate => candidate.title === member.title
        && candidate.value === member.name);
      return `<div class="citation"><h4 class="executive-name">${member.title.toUpperCase()} · ${escapeText(member.name)}</h4>
        ${sources.map(source => `<blockquote>“${escapeText(source.excerpt)}”</blockquote>
          <div class="source-meta">${sourceLink(source.url)}<span>${escapeText(providerNames[source.provider])}</span>
            <span>${escapeText(kindNames[source.kind] || "Unclassified source")}</span>
            <span>${escapeText(formatTime(source.published_at))}</span>
          </div>`).join("")}</div>`;
    }).join("")}</div>
  </article>`;
}

function candidateMarkup(item, field, index) {
  return `<article class="candidate ${item.selected ? "is-selected" : ""}"
      data-testid="candidate-${field}-${index + 1}" data-value="${escapeText(item.value)}"
      data-provider="${escapeText(item.provider)}" data-kind="${escapeText(item.kind)}"
      data-url="${escapeText(item.url)}" data-published-at="${escapeText(item.published_at)}"
      data-selected="${String(item.selected)}">
    <div class="candidate-top"><strong>${escapeText(formatValue(field, item.value))}</strong>
      ${item.selected ? '<span class="tag known">Selected</span>' : ""}</div>
    <blockquote>“${escapeText(item.excerpt)}”</blockquote>
    <div class="source-meta">${sourceLink(item.url)}
      <span>${escapeText(providerNames[item.provider])}</span>
      <span>${escapeText(kindNames[item.kind] || "Unclassified source")}</span>
      <span>${escapeText(formatTime(item.published_at))}</span></div>
  </article>`;
}

function evidenceMarkup(fields) {
  return Object.entries(fieldNames).map(([field, name]) => {
    const candidates = fields[field].candidates;
    return `<section class="evidence-field"><h2>${name}</h2>
      <div class="evidence-items" data-testid="evidence-${field}">
        ${candidates.length ? candidates.map((item, index) => candidateMarkup(item, field, index)).join("")
          : notice("No supporting evidence", "", `evidence-empty-${field}`)}
      </div>
    </section>`;
  }).join("");
}

function stableKey() {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return Array.from(crypto.getRandomValues(new Uint8Array(18)),
    byte => byte.toString(16).padStart(2, "0")).join("");
}

function bindWrite({form, button, message, prefix, action, path, body, onSuccess, input}) {
  let pending = null;
  let sending = false;
  const send = async event => {
    event.preventDefault();
    if (sending) return;
    if (!pending) pending = {key: stableKey(), body: body?.()};
    sending = true;
    button.disabled = true;
    button.textContent = action === "Research" ? "Sending…" : "Requesting refresh…";
    message.innerHTML = notice("Waiting for confirmation…", "loading");
    if (input) input.readOnly = true;
    try {
      const result = await api(path, "POST", pending);
      if (typeof result.domain !== "string" || typeof result.dossier_id !== "string") {
        throw new Error("Missing write confirmation");
      }
      pending = null;
      message.innerHTML = action === "Refresh" ? notice("Refresh accepted.", "success") : "";
      onSuccess(result);
    } catch (error) {
      if (error instanceof Refusal) {
        pending = null;
        message.innerHTML = notice(error.message, "error", `${prefix}-error`);
      } else {
        message.innerHTML = notice(
          "The request may have succeeded. Retry to confirm its outcome.", "uncertain", `${prefix}-uncertain`,
        );
      }
    } finally {
      sending = false;
      button.disabled = false;
      button.textContent = pending ? `Retry ${action.toLowerCase()}` : action;
      if (input) input.readOnly = Boolean(pending);
    }
  };
  if (form) form.addEventListener("submit", send);
  else button.addEventListener("click", send);
}

async function allDossiers(query = "") {
  const dossiers = [];
  let more;
  do {
    const params = new URLSearchParams({q: query, offset: String(dossiers.length), limit: "200"});
    const page = await api(`/dossiers?${params}`);
    dossiers.push(...page.dossiers);
    more = page.has_more;
  } while (more);
  return dossiers;
}

function listMarkup(dossiers, query) {
  if (!dossiers.length) {
    return `<div class="empty" data-testid="empty-dossiers"><h3>${query ? "No matching dossiers" : "No dossiers yet"}</h3>
      <p>${query ? "Try another domain or company name." : "Research a domain to start your first dossier."}</p></div>`;
  }
  return `<ul class="dossier-list" data-testid="dossier-list">${dossiers.map(item =>
    `<li><a class="dossier-item" href="${route(item.domain)}" data-testid="dossier-item-${escapeText(item.domain)}"
      data-state="${item.state}"><div><strong>${escapeText(item.domain)}</strong>
      ${item.legal_name ? `<span>${escapeText(item.legal_name)}</span>` : ""}</div>
      <span class="tag state ${item.state}">${item.state}</span><span class="row-arrow" aria-hidden="true">↗</span></a></li>`,
  ).join("")}</ul>`;
}

function showList() {
  pageTitle("Company dossiers");
  if (!session) {
    mount(`<header class="page-heading"><h1>Company dossiers</h1></header>${signedOut()}`);
    return;
  }
  mount(`<header class="page-heading"><h1>Company dossiers</h1>
    <p>Look up a company and read the sources behind its profile.</p></header>
    <div class="list-layout">
      <section class="research-panel">
        <h2>Research a company</h2>
        <form id="research-form">
          <label for="research-domain">Company domain</label>
          <input id="research-domain" data-testid="research-domain" name="domain" placeholder="example.com"
            inputmode="url" autocapitalize="none" spellcheck="false">
          <button class="button primary" type="submit" data-testid="research-submit">Research</button>
        </form>
        <div id="research-feedback"></div>
      </section>
      <section class="directory">
        <div class="directory-bar"><h2>Dossiers</h2>
          <div class="search-control"><label for="dossier-search">Filter dossiers</label>
            <input id="dossier-search" data-testid="dossier-search" type="search" placeholder="Domain or company name"></div>
        </div>
        <div id="directory-results">${notice("Loading dossiers…", "loading")}</div>
      </section>
    </div>`);
  const search = readTest("dossier-search");
  const results = document.querySelector("#directory-results");
  let revision = 0;
  const read = async () => {
    const request = ++revision;
    const query = search.value;
    try {
      const dossiers = await allDossiers(query);
      if (request === revision) results.innerHTML = listMarkup(dossiers, query);
    } catch (error) {
      if (request === revision) results.innerHTML = loadError(error);
    }
  };
  search.addEventListener("input", read);
  const input = readTest("research-domain");
  bindWrite({
    form: document.querySelector("#research-form"), button: readTest("research-submit"), input,
    message: document.querySelector("#research-feedback"), prefix: "research", action: "Research",
    path: "/dossiers", body: () => ({domain: input.value}),
    onSuccess: result => location.assign(route(result.domain)),
  });
  read();
}

function showDossier(evidenceOnly) {
  pageTitle(evidenceOnly ? `Evidence for ${domain}` : domain);
  const url = route(domain);
  const heading = `<a class="back-link" href="${evidenceOnly ? url : "/"}">← ${evidenceOnly ? "Dossier" : "Dossiers"}</a>
    <header class="page-heading dossier-heading">
      <div><h1 data-testid="dossier-domain">${escapeText(domain)}</h1>
        ${evidenceOnly ? "<p>Source evidence for each field, in rank order.</p>" : ""}
      </div>
      ${evidenceOnly || !session ? "" : `<div class="actions">
        <button class="button secondary" type="button" data-testid="dossier-reload">Reload</button>
        <button class="button primary" type="button" data-testid="dossier-refresh">Refresh</button>
      </div>`}
    </header>`;
  if (!session) {
    mount(heading + signedOut());
    return;
  }
  mount(`${heading}<div id="refresh-feedback"></div>
    <div id="read-feedback" aria-live="polite"></div>
    <div id="dossier-content">${notice(evidenceOnly ? "Loading evidence…" : "Loading dossier…", "loading")}</div>`);
  const content = document.querySelector("#dossier-content");
  const readFeedback = document.querySelector("#read-feedback");
  let issued = 0;
  let applied = 0;
  let polling = 0;
  let lastState;
  function watch(state) {
    if (state === "building" && !polling) polling = setInterval(read, 1450);
    if (state !== "building" && polling) {
      clearInterval(polling);
      polling = 0;
    }
  }
  async function read() {
    const request = ++issued;
    try {
      const dossier = await api(url);
      if (request < applied) return;
      applied = request;
      readFeedback.replaceChildren();
      if (dossier.state !== lastState) {
        readFeedback.textContent = dossier.state === "building" ? "Research in progress" : `Dossier ${dossier.state}`;
        readFeedback.classList.add("visually-hidden");
      }
      lastState = dossier.state;
      watch(dossier.state);
      if (evidenceOnly) {
        content.innerHTML = evidenceMarkup(dossier.fields);
        return;
      }
      const time = dossier.researched_at
        ? `<span data-testid="dossier-researched-at"><time datetime="${escapeText(dossier.researched_at)}">${escapeText(formatTime(dossier.researched_at))}</time></span>` : "";
      content.innerHTML = `<div class="dossier-meta">${buildState(dossier.state)}
        <span class="spend" data-testid="dossier-spent" data-units="${dossier.spent_units}">${integer.format(dossier.spent_units)} research units</span>
        ${time}<a class="evidence-link" data-testid="dossier-evidence-link" href="${url}/evidence">View evidence →</a></div>
        ${dossier.state === "failed" ? notice("Research failed. Any previously verified evidence remains below.", "error") : ""}
        <section class="profile"><header><h2>Company profile</h2></header>${fieldsMarkup(dossier.fields)}</section>`;
    } catch (error) {
      if (request < applied) return;
      applied = request;
      if (error instanceof Refusal && error.status === 404) {
        watch(null);
        content.innerHTML = notice("No dossier exists for this domain.", "", "dossier-not-found");
      } else {
        if (error instanceof Refusal && error.status === 401) watch(null);
        if (!lastState) content.replaceChildren();
        readFeedback.classList.remove("visually-hidden");
        readFeedback.innerHTML = loadError(error);
      }
    }
  }
  if (!evidenceOnly) {
    readTest("dossier-reload").addEventListener("click", read);
    bindWrite({
      button: readTest("dossier-refresh"), message: document.querySelector("#refresh-feedback"),
      prefix: "refresh", action: "Refresh", path: `${url}/refresh`, onSuccess: read,
    });
  }
  read();
}

async function showContested() {
  pageTitle("Contested fields");
  mount(`<header class="page-heading"><h1>Contested fields</h1>
    <p>Compare values where sources disagree.</p></header><div id="contested-content">
    ${session ? notice("Loading contested fields…", "loading") : signedOut()}</div>`);
  if (!session) return;
  const content = document.querySelector("#contested-content");
  try {
    const list = await allDossiers();
    const details = [];
    for (let start = 0; start < list.length; start += 12) {
      const batch = list.slice(start, start + 12);
      details.push(...await Promise.all(batch.map(item => api(route(item.domain)))));
    }
    const rows = details.flatMap(dossier => Object.entries(fieldNames).flatMap(([field, name]) => {
      const item = dossier.fields[field];
      if (item.status !== "contested") return [];
      const alternatives = [...new Set(item.candidates.map(candidate => candidate.value))];
      return [`<li class="contest-row" data-testid="contested-item-${escapeText(dossier.domain)}-${field}"
        data-value="${escapeText(item.value)}"><a href="${route(dossier.domain)}/evidence">
        <div class="contest-name"><span>${escapeText(dossier.domain)}</span><strong>${name}</strong></div>
        <div class="alternatives">${alternatives.map(value =>
          `<span class="tag ${value === item.value ? "known" : "contested"}">${escapeText(formatValue(field, value))}${value === item.value ? " · Selected" : ""}</span>`,
        ).join("")}</div><span class="row-arrow" aria-hidden="true">↗</span>
      </a></li>`];
    }));
    content.innerHTML = rows.length ? `<ul class="contested-list" data-testid="contested-list">${rows.join("")}</ul>`
      : `<div class="empty" data-testid="empty-contested"><h2>No contested fields</h2>
          <p>Fields with competing candidate values will appear here.</p></div>`;
  } catch (error) {
    content.innerHTML = loadError(error);
  }
}

function showAuth() {
  const signup = screen === "signup";
  const title = signup ? "Create your account" : "Log in";
  pageTitle(title);
  mount(`<section class="auth-panel">
    <a class="back-link" href="/">← Dossiers</a>
    <header class="page-heading"><h1>${title}</h1></header>
    <form id="auth-form" class="auth-form" novalidate>
      ${signup ? `<label for="signup-display-name">Display name</label>
        <input id="signup-display-name" name="display_name" data-testid="signup-display-name" autocomplete="name">` : ""}
      <label for="${screen}-email">Email</label>
      <input id="${screen}-email" name="email" type="email" data-testid="${screen}-email" autocomplete="email">
      <label for="${screen}-password">Password</label>
      <input id="${screen}-password" name="password" type="password" data-testid="${screen}-password"
        autocomplete="${signup ? "new-password" : "current-password"}"${signup ? ' aria-describedby="password-hint"' : ""}>
      ${signup ? '<small id="password-hint">Use at least eight characters.</small>' : ""}
      <div id="auth-feedback"></div>
      <button class="button primary" type="submit" data-testid="${screen}-submit">${signup ? "Sign up" : "Log in"}</button>
    </form>
    <p class="auth-switch">${signup ? 'Already have an account? <a href="/login">Log in</a>'
      : 'New to Dossier? <a href="/signup">Create an account</a>'}</p>
  </section>`);
  const form = document.querySelector("#auth-form");
  const feedback = document.querySelector("#auth-feedback");
  const submit = readTest(`${screen}-submit`);
  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (submit.disabled) return;
    submit.disabled = true;
    feedback.innerHTML = notice("Submitting…", "loading");
    try {
      const data = await api(`/auth/${screen}`, "POST", {body: Object.fromEntries(new FormData(form))});
      setSession({token: data.token, displayName: data.display_name});
      location.assign("/");
    } catch (error) {
      feedback.innerHTML = notice(error instanceof Refusal ? error.message : "Could not connect. Try again.",
        "error", "auth-error");
    } finally {
      submit.disabled = false;
    }
  });
}

renderSession();
if (screen === "detail" || screen === "evidence") showDossier(screen === "evidence");
else if (screen === "contested") showContested();
else if (screen === "signup" || screen === "login") showAuth();
else showList();
