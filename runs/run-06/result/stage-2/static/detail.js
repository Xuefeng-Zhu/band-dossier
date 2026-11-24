import {api, Refusal} from "./api.js";
import {writer} from "./actions.js";
import {el, badge, button, title, crumbs, urlFor, fields, formatValue, kinds, dateNode, quote, notice, empty} from "./ui.js";

function overviewRow(name, item) {
  const status = badge(item.status, item.status === "contested" ? "field-contested-" + name : null);
  const citations = el("div",{class:"quotes", test:"field-citations-" + name},
    ...item.citations.map((c, i) => quote(c, "citation-" + name + "-" + (i + 1))));
  return el("section", {class:"field-row",test:"field-" + name, "data-status":item.status},
    el("h2",{class:"field-name"},fields[name]),
    el("div",{class:"field-core"}, item.value === null
      ? el("span",{class:"unavailable"},"No supported value")
      : el("span",{class:"field-value",test:"field-value-" + name,"data-value":item.value},formatValue(name,item.value)),
      status), citations);
}

function evidenceRow(name, item) {
  const list = el("div",{class:"candidate-list",test:"evidence-" + name});
  for (const [i, c] of item.candidates.entries()) {
    list.append(el("article",{
      class:"candidate" + (c.selected ? " selected" : ""),test:"candidate-" + name + "-" + (i + 1),
      "data-value":c.value,"data-provider":c.provider,"data-kind":c.kind ?? "",
      "data-url":c.url,"data-published-at":c.published_at ?? "","data-selected":String(c.selected)
    },
    el("div",{class:"candidate-main"}, el("strong",{class:"field-value"},formatValue(name,c.value)),
      c.selected && el("span",{class:"badge known"},"Selected")),
    el("div",{class:"candidate-other"}, quote(c),
      el("div",{class:"candidate-meta"}, el("span",{},kinds[c.kind] || "Source kind unavailable"),
        c.published_at ? el("span",{},"Published ",dateNode(c.published_at)) : el("span",{},"Publication date unavailable"),
        el("span",{},"Retrieved ",dateNode(c.retrieved_at))))));
  }
  if (!item.candidates.length) list.append(el("p",{class:"muted",test:"evidence-empty-" + name},"No supporting sources."));
  return el("section",{class:"evidence-field"},el("h2",{},fields[name]),list);
}

export function detail(main, inputDomain, evidence) {
  const path = urlFor(inputDomain);
  const feedback = el("div",{class:"feedback","aria-live":"polite"});
  const readFeedback = el("div",{class:"feedback","aria-live":"polite"});
  const domainTitle = el("h1",{test:"dossier-domain"}, inputDomain);
  const stateBox = el("div",{class:"state-box"});
  const meta = el("div",{class:"metadata"});
  const content = el("div",{class:evidence ? "evidence-rows" : "field-rows"});
  const tabs = el("nav",{class:"tabs","aria-label":"Dossier sections"});
  const reload = button("Reload","dossier-reload",() => read(),"secondary","reload");
  const refresh = button("Refresh","dossier-refresh",() => write(),"primary","refresh");
  let readID = 0, lastApplied = 0, manualFloor = 0, timer, previous;
  title(inputDomain);
  main.replaceChildren(crumbs(["Dossiers","/"], evidence ? "Company evidence" : "Company dossier"),
    el("div",{class:"title-bar"},
      el("div",{class:"title-info"},el("div",{class:"title-line"},domainTitle,stateBox),meta),
      el("div",{class:"actions"},refresh,reload)),
    feedback, readFeedback, tabs, content);
  function schedule(state) {
    if (state === "building" && !timer) timer = setInterval(() => read(false),950);
    if (state !== "building" && timer) { clearInterval(timer); timer = null; }
  }
  const write = writer("refresh", () => ({path:path + "/refresh"}), refresh, feedback, async () => {
    notice(feedback, "ok", null, "Refresh requested.");
    await read();
  });
  function show(dossier) {
    const domain = dossier.domain;
    const canonical = urlFor(domain, evidence);
    if (location.pathname !== canonical) history.replaceState(null, "", canonical);
    title(evidence ? "Evidence · " + domain : domain);
    domainTitle.textContent = domain;
    stateBox.replaceChildren(badge(dossier.state,"dossier-state"));
    meta.replaceChildren();
    if (dossier.researched_at) meta.append(el("span",{},"Researched ",dateNode(dossier.researched_at,"dossier-researched-at")));
    meta.append(el("span",{test:"dossier-spent","data-units":dossier.spent_units},dossier.spent_units.toLocaleString() + " units spent"));
    tabs.replaceChildren(el("a",{href:urlFor(domain),"aria-current":evidence ? null : "page"},"Overview"),
      el("a",{href:urlFor(domain,true),test:"dossier-evidence-link","aria-current":evidence ? "page" : null},"Evidence"));
    content.replaceChildren(...Object.keys(fields).map(k => evidence ? evidenceRow(k,dossier.fields[k]) : overviewRow(k,dossier.fields[k])));
    schedule(dossier.state);
  }
  async function read(manual = true) {
    const sequence = ++readID;
    // An explicit read supersedes earlier requests immediately. A poll may
    // publish while a newer poll is pending, but never after a newer reply.
    if (manual) manualFloor = sequence;
    const superseded = () => sequence < manualFloor || sequence <= lastApplied;
    readFeedback.replaceChildren();
    try {
      const dossier = await api(path);
      if (superseded()) return;
      lastApplied = sequence;
      const snapshot = JSON.stringify(dossier);
      if (snapshot !== previous) { show(dossier); previous = snapshot; }
    } catch (err) {
      if (superseded()) return;
      lastApplied = sequence;
      if (err instanceof Refusal && err.status === 404) {
        schedule(null);
        content.replaceChildren(empty("Dossier not found","Research this domain from the dossier list.","dossier-not-found"));
        meta.replaceChildren(); stateBox.replaceChildren(); tabs.replaceChildren();
        previous = null;
      } else {
        notice(readFeedback,"error",null,err.message || "The dossier could not be loaded. Try Reload.");
      }
    }
  }
  content.append(el("p",{class:"loading",role:"status"},"Loading dossier…"));
  read();
}
