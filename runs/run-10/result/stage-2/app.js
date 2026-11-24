"use strict";
const root = document.querySelector("#main");
const account = document.querySelector("#account");
const fields = {
  legal_name: "Legal name", hq_city: "Headquarters city", ceo: "Chief executive",
  founded_year: "Founded", headcount_range: "Headcount", funding_total: "Total equity funding"
};
const labels = {own:"Company website", filing:"Filing", news:"News", aggregator:"Aggregator"};
const esc = value => String(value ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
const attr = id => 'data-testid="'+esc(id)+'"';
const byId = id => document.getElementById(id);
const cleanDomain = text => text.trim().toLowerCase().replace(/\.$/,"").replace(/^www\./,"");
const titleCase = text => text.slice(0,1).toUpperCase()+text.slice(1);
const quote = text => '<blockquote>“'+esc(text)+'”</blockquote>';
const pageLink = domain => "/dossiers/"+encodeURIComponent(domain);
const empty = (id,title,extra="") => '<div '+attr(id)+' class="empty"><b>'+esc(title)+'</b>'+esc(extra)+'</div>';
const note = (kind,text,id="") => '<p role="status" '+(id?attr(id):"")+' class="notice '+kind+'">'+esc(text)+'</p>';
const pill = (text,kind,id="") => '<span class="pill '+esc(kind)+'" '+(id?attr(id):"")+'>'+esc(text)+'</span>';
function display(field,value) {
  if(field==="funding_total") return new Intl.NumberFormat("en-US",{style:"currency",currency:"USD",maximumFractionDigits:0}).format(value);
  if(field==="headcount_range") return String(value).replace(/\d+/g,n=>Number(n).toLocaleString("en-US")).replace("-","–");
  return String(value);
}
function dateText(stamp) {
  if(!stamp) return "Undated";
  const d = new Date(stamp);
  return Number.isFinite(d.valueOf()) ? new Intl.DateTimeFormat("en-US",{dateStyle:"medium",timeStyle:"short",timeZone:"UTC"}).format(d)+" UTC" : stamp;
}
function external(url) {
  try {
    const parsed=new URL(url);
    if(["https:","http:"].includes(parsed.protocol))
      return '<a href="'+esc(url)+'" target="_blank" rel="noopener noreferrer">'+esc(parsed.host)+' ↗</a>';
  } catch {}
  return esc(url);
}
let session;
try {session=JSON.parse(localStorage.getItem("dossier.session"))} catch {}
const path=location.pathname;
const isAuth=path==="/login"||path==="/signup";
function safeNext() {
  const target=new URLSearchParams(location.search).get("next")||"/";
  return target.startsWith("/")&&!target.startsWith("//")&&!target.includes("\\")?target:"/";
}
function signOut() {
  localStorage.removeItem("dossier.session");
  location.assign("/login");
}
if(session?.token){
  account.innerHTML='<span '+attr("current-user")+'>'+esc(session.display_name)+'</span><button '+attr("logout-button")+' type="button">Log out</button>';
  account.querySelector("button").onclick=signOut;
} else {
  account.innerHTML='<a class="authlink" href="/login">Log in</a>';
}
class Refusal extends Error { constructor(status,message){super(message);this.status=status;} }
async function api(url,opts={}){
  const headers={Accept:"application/json",...opts.headers};
  if(session?.token)headers.Authorization="Bearer "+session.token;
  if(opts.body!==undefined)headers["Content-Type"]="application/json";
  const response=await fetch(url,{cache:"no-store",...opts,headers});
  if(!response.ok){
    const error=await response.json().catch(()=>({}));
    if(response.status>=500)throw new Error("Service response unavailable");
    throw new Refusal(response.status,error.error?.message||"This request was refused.");
  }
  // Read large JSON integers from the original token, before binary rounding.
  return JSON.parse(await response.text(), (key, value, context) => {
    if (typeof value === "number" && !Number.isSafeInteger(value) && /^-?\d+$/.test(context.source))
      return BigInt(context.source);
    return value;
  });
}
async function allDossiers(q=""){
  const items=[];
  for(let offset=0;;offset+=200){
    const result=await api("/dossiers?"+new URLSearchParams({q,limit:"200",offset}));
    items.push(...result.dossiers);
    if(!result.has_more)return items;
  }
}
function heading(title,sub=""){
  document.title=title+" · Dossier";
  return '<div class="heading"><h1>'+esc(title)+'</h1>'+(sub?'<p class="sub">'+esc(sub)+'</p>':"")+'</div>';
}
function authScreen(){
  const signup=path==="/signup", action=signup?"signup":"login", title=signup?"Create an account":"Log in";
  const input=(key,label,type,auto)=>'<label for="'+key+'">'+label+'</label><input id="'+key+'" '+attr(action+"-"+key)+' type="'+type+'" autocomplete="'+auto+'">';
  root.innerHTML='<section class="auth">'+heading(title,signup?"Create your research workspace account.":"Open your research workspace.")+
    '<form id="authform" novalidate>'+input("email","Email","email","email")+input("password","Password","password",signup?"new-password":"current-password")+
    (signup?input("display-name","Display name","text","name"):"")+'<button class="primary" '+attr(action+"-submit")+'>'+title+'</button></form><div id="authmsg"></div><a href="/'+
    (signup?"login":"signup")+location.search+'">'+(signup?"Log in to an existing account":"Create an account")+'</a></section>';
  byId("authform").onsubmit=async e=>{
    e.preventDefault();const button=e.target.querySelector("button");button.disabled=true;
    const payload={email:byId("email").value,password:byId("password").value};
    if(signup)payload.display_name=byId("display-name").value;
    try {
      const user=await api("/auth/"+action,{method:"POST",body:JSON.stringify(payload)});
      localStorage.setItem("dossier.session",JSON.stringify(user));location.assign(safeNext());
    }catch(err){byId("authmsg").innerHTML=note("error",err.message,"auth-error");button.disabled=false}
  };
}
function writer(kind,button,feedback,url,payload,success){
  let pending=null;
  return async event=>{
    event.preventDefault();
    if(button.disabled)return;
    const body=payload();
    if(!pending||pending.body!==body)pending={body,key:Array.from(crypto.getRandomValues(new Uint32Array(4)),n=>n.toString(16).padStart(8,"0")).join("")};
    button.disabled=true;feedback.innerHTML=note("loading",kind==="research"?"Opening dossier…":"Requesting a refresh…");
    try {
      const result=await api(url,{method:"POST",body:pending.body,headers:{"Idempotency-Key":pending.key}});
      if(!result?.domain)throw new Error("Missing write confirmation");
      pending=null;feedback.innerHTML=note("success",kind==="research"?"Dossier opened.":"Refresh accepted.");
      await success(result);
    }catch(err){
      if(err instanceof Refusal){pending=null;feedback.innerHTML=note("error",err.message,kind+"-error")}
      else feedback.innerHTML=note("uncertain","The response was lost. Retry to confirm this same request.",kind+"-uncertain");
    }finally{button.disabled=false}
  };
}
function home(){
  byId("nav-list").setAttribute("aria-current","page");
  root.innerHTML=heading("Company dossiers","Research a company and review the sources behind its profile.")+
    '<section class="panel research"><div><h2>Research a company</h2><p class="sub">Enter its website domain to open or build a dossier.</p></div>'+
    '<form id="researchform" novalidate><label for="domain">Company domain</label><div class="formline"><input '+attr("research-domain")+' id="domain" placeholder="example.com" autocapitalize="none"><button class="primary" '+attr("research-submit")+'>Research</button></div><div id="writemsg"></div></form></section>'+
    '<div class="sectionhead"><h2>Dossier library</h2><div class="search"><label for="search">Search dossiers</label><input type="search" '+attr("dossier-search")+' id="search" placeholder="Domain or legal name"></div></div><div id="items"></div>';
  byId("researchform").onsubmit=writer("research",byId("researchform").querySelector("button"),byId("writemsg"),"/dossiers",
    ()=>JSON.stringify({domain:byId("domain").value}),result=>location.assign(pageLink(result.domain)));
  let generation=0;
  async function read(){
    const id=++generation;
    byId("items").innerHTML=note("loading","Loading dossiers…");
    try {
      const rows=await allDossiers(byId("search").value);
      if(id!==generation)return;
      byId("items").innerHTML=rows.length?'<div '+attr("dossier-list")+' class="list">'+rows.map(d=>
        '<a class="row" '+attr("dossier-item-"+d.domain)+' data-state="'+esc(d.state)+'" href="'+pageLink(d.domain)+'"><div><strong>'+esc(d.domain)+'</strong>'+
        (d.legal_name?'<small>'+esc(d.legal_name)+'</small>':"")+'</div>'+pill(d.state,d.state)+'</a>').join("")+'</div>':
        empty("empty-dossiers",byId("search").value?"No matching dossiers":"Your library is empty",byId("search").value?"Try another domain or legal name.":"Research a company to start your library.");
    }catch(err){if(id===generation)byId("items").innerHTML=note("error",err.message)}
  }
  byId("search").oninput=read;read();
}
function citations(key,items){
  return '<div class="sources" '+attr("field-citations-"+key)+'>'+items.map((c,i)=>
    '<div class="citation" '+attr("citation-"+key+"-"+(i+1))+' data-provider="'+esc(c.provider)+'">'+quote(c.excerpt)+
    external(c.url)+' <small class="dim">· '+esc(titleCase(c.provider))+'</small></div>').join("")+
    (items.length?"":'<small class="dim">No supporting citation</small>')+'</div>';
}
function fieldCard(key,f){
  return '<section class="field" '+attr("field-"+key)+' data-status="'+esc(f.status)+'"><div><div class="fieldtop"><h2 class="fieldname">'+fields[key]+'</h2>'+
    pill(titleCase(f.status),f.status,f.status==="contested"?"field-contested-"+key:"")+'</div>'+
    (f.value===null?'<p class="value dim">Unknown</p>':'<p class="value" '+attr("field-value-"+key)+' data-value="'+esc(f.value)+'">'+esc(display(key,f.value))+'</p>')+
    '</div>'+citations(key,f.citations)+'</section>';
}
function candidateCard(key,c,i){
  return '<article class="candidate" '+attr("candidate-"+key+"-"+(i+1))+' data-value="'+esc(c.value)+'" data-provider="'+esc(c.provider)+
    '" data-kind="'+esc(c.kind)+'" data-url="'+esc(c.url)+'" data-published-at="'+esc(c.published_at)+'" data-selected="'+String(c.selected)+'">'+
    '<div class="fieldtop"><strong>'+esc(display(key,c.value))+'</strong>'+(c.selected?pill("Selected","selected"):"")+'</div>'+quote(c.excerpt)+
    '<div class="meta">'+external(c.url)+'<span>'+esc(labels[c.kind]||"Unrecorded source type")+'</span><span>'+esc(titleCase(c.provider))+
    '</span><span>'+esc(dateText(c.published_at))+'</span></div></article>';
}
function dossier(domain,evidence){
  const link=pageLink(domain);
  document.title=(evidence?"Evidence for ":"")+domain+" · Dossier";
  root.innerHTML='<a class="crumb" href="'+(evidence?link:"/")+'">← '+(evidence?esc(domain):"Dossiers")+'</a>'+
    (evidence?heading("Source evidence",domain):'<h1 '+attr("dossier-domain")+'>'+esc(domain)+'</h1>')+
    '<div id="metrics"></div><div id="actions" class="actions">'+(evidence?"":'<button id="refresh" class="primary" '+attr("dossier-refresh")+'>Refresh research</button>'+
    '<button id="reload" '+attr("dossier-reload")+'>Reload</button><a class="btn" '+attr("dossier-evidence-link")+' href="'+link+'/evidence">View evidence →</a>')+
    '</div><div id="writemsg"></div><div id="content">'+note("loading","Loading dossier…")+'</div>';
  let generation=0,poll=null;
  function tracking(building){
    if(building&&!poll)poll=setInterval(read,1200);
    if(!building&&poll){clearInterval(poll);poll=null}
  }
  async function read(){
    const id=++generation;
    try{
      const d=await api(link);
      if(id!==generation)return;
      tracking(d.state==="building");
      byId("metrics").innerHTML='<div class="meta">'+pill(d.state,d.state,"dossier-state")+
        '<span '+attr("dossier-spent")+' data-units="'+d.spent_units+'">'+Number(d.spent_units).toLocaleString()+" research units</span>"+
        (d.researched_at?'<span '+attr("dossier-researched-at")+' title="'+esc(d.researched_at)+'">Researched '+esc(dateText(d.researched_at))+'</span>':"")+'</div>';
      byId("content").innerHTML=evidence?Object.keys(fields).map(k=>'<section class="group"><h2>'+fields[k]+'</h2><div class="stack" '+attr("evidence-"+k)+'>'+
        (d.fields[k].candidates.length?d.fields[k].candidates.map((c,i)=>candidateCard(k,c,i)).join(""):empty("evidence-empty-"+k,"No candidates"))+'</div></section>').join(""):
        '<div class="stack">'+Object.keys(fields).map(k=>fieldCard(k,d.fields[k])).join("")+'</div>';
    }catch(err){
      if(id!==generation)return;
      if(err.status===404){tracking(false);byId("metrics").innerHTML="";byId("content").innerHTML=empty("dossier-not-found","Dossier not found","Research this domain from the dossier library.")}
      else byId("content").innerHTML=note("error",err.message);
    }
  }
  if(!evidence){
    byId("reload").onclick=read;
    byId("refresh").onclick=writer("refresh",byId("refresh"),byId("writemsg"),link+"/refresh",()=>undefined,()=>read());
  }
  read();
}
async function contested(){
  byId("nav-disputes").setAttribute("aria-current","page");
  root.innerHTML=heading("Contested fields","Compare competing values and follow each one back to its source.")+'<div id="items">'+note("loading","Checking dossiers…")+'</div>';
  try{
    const items=await allDossiers();
    const cards=[];
    for(let start=0;start<items.length;start+=20){
      const details=await Promise.all(items.slice(start,start+20).map(d=>api(pageLink(d.domain))));
      for(const d of details)for(const [k,label] of Object.entries(fields)){
        const f=d.fields[k];
        if(f.status!=="contested")continue;
        const values=[...new Set(f.candidates.map(c=>c.value))].map(v=>esc(display(k,v)));
        cards.push('<article class="row dispute" '+attr("contested-item-"+d.domain+"-"+k)+' data-value="'+esc(f.value)+'"><small>'+
          esc(d.domain)+' · '+esc(k)+'</small><strong><a href="'+pageLink(d.domain)+'/evidence">'+label+'</a></strong><p>'+values.join(" · ")+'</p></article>');
      }
    }
    byId("items").innerHTML=cards.length?'<div class="list" '+attr("contested-list")+'>'+cards.join("")+'</div>':empty("empty-contested","No contested fields","Fields appear here when sources support different values.");
  }catch(err){byId("items").innerHTML=note("error",err.message)}
}
if(isAuth)authScreen();
else if(!session?.token)location.replace("/login?next="+encodeURIComponent(location.pathname+location.search));
else if(path==="/")home();
else if(path==="/contested")contested();
else {
  const m=path.match(/^\/dossiers\/(.+?)(\/evidence)?$/);
  if(m){
    const domain=cleanDomain(decodeURIComponent(m[1]));
    const canonical=pageLink(domain)+(m[2]||"");
    if(path!==canonical)history.replaceState(null,"",canonical+location.search);
    dossier(domain,Boolean(m[2]));
  }else location.replace("/");
}
