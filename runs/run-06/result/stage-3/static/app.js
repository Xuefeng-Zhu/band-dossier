import {api, listAll, saveSession, session} from "./api.js";
import {writer} from "./actions.js";
import {el, badge, button, title, crumbs, input, icon, empty, notice, fields, formatValue, urlFor} from "./ui.js";
import {detail} from "./detail.js";

const main = document.querySelector("main");
const user = session();
const path = location.pathname;
const nav = document.querySelector("#nav");
const account = document.querySelector("#account");
function header() {
  if (user) {
    nav.append(el("a",{href:"/","aria-current":path === "/" || path.startsWith("/dossiers/") ? "page" : null},"Dossiers"),
      el("a",{href:"/contested","aria-current":path === "/contested" ? "page" : null},"Contested"));
    account.append(el("span",{class:"user",test:"current-user"}, user.display_name),
      button("Sign out","logout-button",() => { saveSession(null); location.assign("/login"); },"text-button"));
  } else {
    account.append(el("a",{href:path === "/signup" ? "/login" : "/signup",class:"general-link"},
      path === "/signup" ? "Log in" : "Sign up"));
  }
}
function auth(signup) {
  const prefix = signup ? "signup" : "login";
  const heading = signup ? "Create an account" : "Log in";
  title(heading);
  const email = input("Email",prefix + "-email",{type:"email",autocomplete:"email",required:true,placeholder:"you@company.com"});
  const password = input("Password",prefix + "-password",{type:"password",autocomplete:signup ? "new-password" : "current-password",required:true});
  const name = signup && input("Display name","signup-display-name",{autocomplete:"name",maxlength:"100",required:true});
  const submit = el("button",{type:"submit",class:"primary",test:prefix + "-submit"},heading);
  const feedback = el("div",{class:"feedback"});
  const form = el("form",{class:"auth-form",novalidate:true},name && name.group,email.group,password.group,submit,feedback);
  form.addEventListener("submit",async event => {
    event.preventDefault();
    if (submit.disabled) return;
    submit.disabled = true; feedback.replaceChildren();
    try {
      const body = {email:email.control.value,password:password.control.value};
      if (signup) body.display_name = name.control.value;
      const signedIn = await api("/auth/" + prefix,{method:"POST",body:JSON.stringify(body)});
      saveSession(signedIn);
      const next = new URLSearchParams(location.search).get("next");
      location.assign(next && /^\/(?:dossiers\/|contested(?:$|\?)|$)/.test(next) ? next : "/");
    } catch (err) {
      notice(feedback,"error","auth-error",err.message);
    } finally { submit.disabled = false; }
  });
  const alternate = "/"+(signup ? "login" : "signup")+location.search;
  main.replaceChildren(el("section",{class:"auth-sheet"},
    el("h1",{},heading),form,el("p",{class:"auth-alternate"}, signup ? "Already have an account? " : "New to Dossier? ",
    el("a",{href:alternate},signup ? "Log in" : "Create an account"))));
}
function directory() {
  title("Dossiers");
  const name = input("Company domain","research-domain",{placeholder:"company.com",autocapitalize:"none",spellcheck:"false",autocomplete:"off"});
  const submit = el("button",{class:"primary",type:"submit",test:"research-submit"},icon("search"),"Research");
  const feedback = el("div",{class:"feedback","aria-live":"polite"});
  const form = el("form",{class:"research-form",novalidate:true},name.group,submit);
  const write = writer("research",() => ({path:"/dossiers",body:JSON.stringify({domain:name.control.value})}),submit,feedback,
    reply => location.assign(urlFor(reply.domain)));
  form.addEventListener("submit",event => { event.preventDefault(); write(); });
  const search = input("Search dossiers","dossier-search",{type:"search",placeholder:"Domain or legal name",autocomplete:"off"});
  const results = el("div",{class:"directory-results","aria-live":"polite"});
  const scope = el("div",{class:"directory-title"},el("h1",{},"Dossiers"));
  main.replaceChildren(scope,el("div",{class:"directory-layout"},
    el("aside",{class:"research-panel"},el("h2",{},"Research a company"),form,feedback),
    el("section",{class:"directory-index"},el("div",{class:"index-tools"},search.group),results)));
  let latest = 0;
  async function load() {
    const version = ++latest;
    const q = search.control.value;
    try {
      const rows = await listAll(q);
      if (version !== latest) return;
      if (!rows.length) {
        results.replaceChildren(empty(q ? "No matching dossiers" : "No dossiers yet",
          q ? "Try another domain or company name." : "Research a company domain to add its first dossier.","empty-dossiers"));
        return;
      }
      const list = el("div",{class:"dossier-list",test:"dossier-list"});
      for (const row of rows) {
        list.append(el("a",{href:urlFor(row.domain),class:"dossier-item",test:"dossier-item-" + row.domain,"data-state":row.state},
          el("div",{class:"item-name"},el("strong",{},row.domain),row.legal_name && el("span",{},row.legal_name)),
          badge(row.state),icon("arrow")));
      }
      results.replaceChildren(list);
    } catch (err) { if (version === latest) notice(results,"error",null,err.message); }
  }
  search.control.addEventListener("input",load);
  results.append(el("p",{class:"loading",role:"status"},"Loading dossiers…"));
  load();
}
async function contested() {
  title("Contested fields");
  const body = el("div",{class:"contested-results"});
  main.replaceChildren(crumbs(["Dossiers","/"],"Contested"),el("h1",{},"Contested fields"),body);
  body.append(el("p",{class:"loading",role:"status"},"Checking dossiers…"));
  try {
    const rows = await listAll();
    const list = el("div",{class:"contested-list",test:"contested-list"});
    for (let i = 0; i < rows.length; i += 12) {
      const group = await Promise.all(rows.slice(i,i+12).map(row => api(urlFor(row.domain))));
      for (const d of group) for (const [field,label] of Object.entries(fields)) {
        const item = d.fields[field];
        if (item.status !== "contested") continue;
        const values = [...new Set(item.candidates.map(c => c.value))];
        list.append(el("article",{class:"contested-row",test:"contested-item-" + d.domain + "-" + field,"data-value":item.value},
          el("div",{},el("p",{class:"muted"},d.domain),el("h2",{},label),badge("contested")),
          el("div",{},el("strong",{class:"field-value"},formatValue(field,item.value)),
            el("p",{class:"alternatives"},"Also reported: " + values.filter(v=>v!==item.value).map(v=>formatValue(field,v)).join(", "))),
          el("a",{class:"evidence-action",href:urlFor(d.domain,true)},"View evidence",icon("arrow"))));
      }
    }
    body.replaceChildren(list.children.length ? list : empty("No contested fields","Fields with conflicting source values will appear here.","empty-contested"));
  } catch (err) { notice(body,"error",null,err.message); }
}
header();
if (path === "/login" || path === "/signup") auth(path === "/signup");
else if (!user) location.replace("/login?next=" + encodeURIComponent(path + location.search));
else if (path === "/") directory();
else if (path === "/contested") contested();
else {
  const match = path.match(/^\/dossiers\/([^/]+)(\/evidence)?$/);
  if (match) detail(main,decodeURIComponent(match[1]),Boolean(match[2]));
  else main.replaceChildren(empty("Page not found","Return to Dossiers to browse your research."));
}
