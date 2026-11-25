export const fields = {
  legal_name: "Legal name", hq_city: "Headquarters", ceo: "Chief executive",
  founded_year: "Founded", headcount_range: "Employees", funding_total: "Equity funding"
};
export const kinds = {own: "Company site", filing: "Regulatory filing", news: "News", aggregator: "Data aggregator"};
const icons = {
  refresh: '<path d="M19 7a8 8 0 1 0 1 8M19 3v5h-5"/>',
  reload: '<path d="M4 8a8 8 0 0 1 14-2l2 2m0-5v5h-5M20 16a8 8 0 0 1-14 2l-2-2m0 5v-5h5"/>',
  arrow: '<path d="M5 12h14m-5-5 5 5-5 5"/>',
  link: '<path d="M13 4h7v7m0-7L10 14M8 6H5a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-3"/>',
  search: '<circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/>',
  folder: '<path d="M3 6a2 2 0 0 1 2-2h5l3 3h6a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  check: '<path d="m5 12 4 4L19 6"/>'
};
export function icon(name) {
  const span = document.createElement("span");
  span.className = "icon";
  span.setAttribute("aria-hidden", "true");
  span.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">' + icons[name] + '</svg>';
  return span;
}
export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "test") node.dataset.testid = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child !== null && child !== undefined && child !== false) node.append(child);
  }
  return node;
}
export const title = text => { document.title = text + " · Dossier"; };
export const button = (label, test, action, type = "secondary", symbol) =>
  el("button", {class: type, type: "button", test, onclick: action}, symbol && icon(symbol), label);
export const badge = (status, test) => el("span", {class: "badge " + status, test}, status);
export const urlFor = (domain, evidence = false) => "/dossiers/" + encodeURIComponent(domain) + (evidence ? "/evidence" : "");
export function crumbs(...items) {
  return el("nav", {class:"crumbs", "aria-label":"Breadcrumb"},
    ...items.map((item, i) => Array.isArray(item)
      ? el("a", {href:item[1]}, item[0])
      : el("span", {"aria-current": i === items.length - 1 ? "page" : null}, item)));
}
export function input(label, test, options = {}) {
  const control = el("input", {id:test, test, ...options});
  return {control, group:el("div", {class:"input-group"}, el("label", {for:test}, label), control)};
}
export function empty(heading, message, test) {
  return el("div", {class:"empty", test}, el("span",{class:"empty-mark"}, icon("folder")),
    el("h2",{},heading), el("p",{},message));
}
export function notice(parent, style, test, message) {
  parent.replaceChildren(el("div", {class:"notice " + style, test, role:style === "ok" ? "status" : "alert"}, message));
}
export const formatValue = (field, value) => field === "funding_total"
  ? new Intl.NumberFormat("en-US",{style:"currency",currency:"USD",maximumFractionDigits:0}).format(BigInt(value))
  : field === "headcount_range" ? String(value).replace("-", "–") : String(value);
export function dateNode(raw, test) {
  const d = new Date(raw);
  const text = Number.isNaN(d.getTime()) ? raw : new Intl.DateTimeFormat("en", {
    month:"short",day:"numeric",year:"numeric",hour:"2-digit",minute:"2-digit",hour12:false,timeZone:"UTC",timeZoneName:"short"
  }).format(d);
  return el("time", {datetime:raw,title:raw,test}, text);
}
export function external(url) {
  let host = url;
  let href;
  try {
    const parsed = new URL(url);
    if (["http:","https:"].includes(parsed.protocol)) {
      href = parsed.href;
      host = parsed.hostname.replace(/^www\./,"");
    }
  } catch { /* Unlinkable provenance still has a readable source label. */ }
  return el("a", {href:href ? url : null,target:"_blank",rel:"noopener noreferrer",class:"source"}, host, icon("link"));
}
export function quote(c, test) {
  return el("div", {class:"quote",test,"data-provider":c.provider},
    el("blockquote",{},c.excerpt),
    el("div",{class:"attribution"}, external(c.url), el("span",{}, "Via " + c.provider)));
}
