const fields = {
  legal_name: "Legal name", hq_city: "Headquarters city", ceo: "Chief executive",
  founded_year: "Founded", headcount_range: "Headcount", funding_total: "Total equity funding"
};
const kindNames = {own:"Company website", filing:"Filing registry", news:"News report", aggregator:"Data aggregator"};
const main = document.querySelector("main");
const session = JSON.parse(localStorage.getItem("dossier.session") || "null");
const path = location.pathname;
const safe = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const by = id => document.querySelector('[data-testid="'+CSS.escape(id)+'"]');
const attr = (key, value) => ' data-'+key+'="'+safe(value)+'"';
const test = id => attr("testid", id);
const normalize = s => s.trim().toLowerCase().replace(/\.$/,"").replace(/^www\./,"");
const dossierPath = d => "/dossiers/"+encodeURIComponent(d);
function sourceUrl(s) { try {const url = new URL(s);return ["http:","https:"].includes(url.protocol)?s:"#";} catch {return "#";} }
function hostName(s) { try {return new URL(s).host;} catch {return s;} }
function valueText(f,v) {
  if (f === "funding_total") return "$"+BigInt(v).toLocaleString("en-US");
  if (f === "headcount_range") return String(v).split("-").map(n=>n.endsWith("+")?Number(n.slice(0,-1)).toLocaleString("en-US")+"+":Number(n).toLocaleString("en-US")).join("–");
  return String(v);
}
function dateText(s) {return new Intl.DateTimeFormat("en",{dateStyle:"medium",timeStyle:"short",timeZone:"UTC"}).format(new Date(s))+" UTC";}
function stateChip(s, id="") {return '<span class="badge '+safe(s)+'"'+(id?test(id):"")+'>'+safe(s)+'</span>';}
function empty(title, message,id) {return '<div class="empty"'+(id?test(id):"")+'><strong>'+safe(title)+'</strong>'+safe(message)+'</div>';}
function notice(text, kind, id="") {return '<div role="'+(kind==="loading"?"status":"alert")+'" class="notice '+kind+'"'+(id?test(id):"")+'>'+safe(text)+'</div>';}
function input(id,label,type="text",extra="") {return '<label>'+label+'<input '+test(id)+' type="'+type+'" '+extra+'></label>';}
function submit(id,label,primary=true){return '<button type="submit" class="'+(primary?"primary":"")+'"'+test(id)+'>'+label+'</button>';}
class Refusal extends Error {constructor(status,code,message){super(message);this.status=status;this.code=code;}}
const messages = {email_taken:"This email is already registered.",unauthenticated:"Check your email and password or sign in again.",validation_failed:"Check the entered value and try again.",not_found:"The requested dossier could not be found."};
function parseJSON(text) {
  // Preserve integer-valued fields beyond the precision of JavaScript Number.
  const tokens= /"(?:\\.|[^"\\])*"|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/g;
  return JSON.parse(text.replace(tokens,t=>/^-?\d{16,}$/.test(t)?'"'+t+'"':t));
}
async function api(url,method="GET",body,key) {
  const headers = {"Accept":"application/json"};
  if(session) headers.Authorization="Bearer "+session.token;
  if(key) headers["Idempotency-Key"]=key;
  if(body!==undefined) headers["Content-Type"]="application/json";
  const res=await fetch(url,{method,headers,body:body===undefined?undefined:JSON.stringify(body),cache:"no-store"});
  if(!res.ok){ const error=await res.json().catch(()=>({}));throw new Refusal(res.status,error.error?.code,messages[error.error?.code]||error.error?.message||"The request was refused.");}
  return parseJSON(await res.text());
}
const navLink = (url,label,current) => '<a href="'+url+'"'+(current?' aria-current="page"':'')+'>'+label+'</a>';
function header() {
  document.querySelector("header").innerHTML='<div class="bar"><a class="brand" href="/"><i class="brandmark" aria-hidden="true"></i>Dossier</a>'+
    (session?'<nav aria-label="Main navigation">'+navLink("/","Dossiers",path!=="/contested")+navLink("/contested","Contested fields",path==="/contested")+'</nav><div class="identity"><span'+test("current-user")+'>'+safe(session.display_name)+'</span><button'+test("logout-button")+'>Log out</button></div>':'')+'</div>';
  by("logout-button")?.addEventListener("click",()=>{localStorage.removeItem("dossier.session");location.assign("/login");});
}
function auth(signup){
  const mode=signup?"signup":"login", label=signup?"Create account":"Log in";
  document.title=label+" · Dossier";
  main.innerHTML='<section class="authbox"><h1>'+label+'</h1><form class="form" novalidate>'+
    (signup?input(mode+"-display-name","Display name","text",'autocomplete="name"'):"")+
    input(mode+"-email","Email address","email",'autocomplete="email"')+input(mode+"-password","Password","password",signup?'autocomplete="new-password"':'autocomplete="current-password"')+
    '<div id="feedback"></div>'+submit(mode+"-submit",label)+'</form><p class="muted">'+(signup?'Already have an account? <a href="/login">Log in</a>':'New to Dossier? <a href="/signup">Create an account</a>')+'</p></section>';
  main.querySelector("form").onsubmit=async e=>{
    e.preventDefault();const button=by(mode+"-submit");button.disabled=true;
    try{
      const body={email:by(mode+"-email").value,password:by(mode+"-password").value};
      if(signup)body.display_name=by(mode+"-display-name").value;
      localStorage.setItem("dossier.session",JSON.stringify(await api("/auth/"+mode,"POST",body)));
      const back=new URLSearchParams(location.search).get("next");location.assign(back?.startsWith("/")&&!back.startsWith("//")?back:"/");
    }catch(err){document.querySelector("#feedback").innerHTML=notice(err.message,"error","auth-error");button.disabled=false;}
  };
}
async function allRows(q=""){
  const rows=[];let page;
  do {page=await api("/dossiers?q="+encodeURIComponent(q)+"&limit=200&offset="+rows.length);rows.push(...page.dossiers);}while(page.has_more);
  return rows;
}
function bindWrite(form,mode,get,success) {
  let pending=null,busy=false;
  form.onsubmit=async e=>{
    e.preventDefault();if(busy)return;
    const request=get(),signature=JSON.stringify(request);
    if(!pending||pending.signature!==signature)pending={signature,key:globalThis.crypto.randomUUID?.() || Date.now().toString(36)+Math.random().toString(36).slice(2)};
    const button=form.querySelector("button[type=submit]"), feedback=document.getElementById(mode+"-feedback");
    busy=true;button.disabled=true;feedback.innerHTML=notice("Sending request…","loading");
    let result;
    try{result=await api(request.url,"POST",request.body,pending.key);}
    catch(err){
      if(err instanceof Refusal && err.status<500){feedback.innerHTML=notice(err.message,"error",mode+"-error");pending=null;}
      else feedback.innerHTML=notice("The response was lost. Retry to confirm the original request.","uncertain",mode+"-uncertain");
      return;
    }finally{busy=false;button.disabled=false;}
    pending=null;feedback.textContent="";await success(result);
  };
}
function readFailure(err){return notice(err instanceof Refusal?err.message:"Could not load data. Please try again.","error");}
function home(){
  document.title="Company dossiers · Dossier";
  main.innerHTML='<div class="heading"><h1>Company dossiers</h1></div><div class="layout"><section class="library"><div class="section-title"><h2>Research library</h2></div>'+
    input("dossier-search","Search dossiers","search",'placeholder="Domain or legal name"')+'<div class="results" id="results"></div></section>'+
    '<section class="researchbox"><h2>Research a company</h2><form class="form" novalidate>'+input("research-domain","Company domain","text",'placeholder="company.com" autocapitalize="none" spellcheck="false"')+
    submit("research-submit","Research domain")+'<div id="research-feedback"></div></form></section></div>';
  let sequence=0;
  async function list(){
    const id=++sequence, target=document.querySelector("#results"), q=by("dossier-search").value;
    target.innerHTML=notice("Loading dossiers…","loading");
    try {
      const rows=await allRows(q);if(id!==sequence)return;
      target.innerHTML=rows.length?'<div'+test("dossier-list")+'>'+rows.map(r=>'<a class="row"'+test("dossier-item-"+r.domain)+attr("state",r.state)+' href="'+dossierPath(r.domain)+'"><span><strong>'+safe(r.domain)+'</strong>'+(r.legal_name?'<small>'+safe(r.legal_name)+'</small>':'')+'</span><span class="actions">'+stateChip(r.state)+'<span class="arrow" aria-hidden="true">↗</span></span></a>').join("")+'</div>':empty(q?"No matches":"No dossiers yet",q?"Try another domain or legal name.":"Research a company domain to start your library.","empty-dossiers");
    }catch(err){if(id===sequence)target.innerHTML=readFailure(err);}
  }
  by("dossier-search").oninput=list;
  bindWrite(main.querySelector("form"),"research",()=>({url:"/dossiers",body:{domain:by("research-domain").value}}),r=>location.assign(dossierPath(r.domain)));
  list();
}
function citation(c,id) {
  return '<blockquote class="quote"'+(id?test(id)+attr("provider",c.provider):"")+'><p>“'+safe(c.excerpt)+'”</p><div class="source"><a rel="noopener noreferrer" target="_blank" href="'+safe(sourceUrl(c.url))+'">'+safe(hostName(c.url))+' ↗</a><span>via '+safe(c.provider)+'</span></div></blockquote>';
}
function tabs(domain,evidence) {
  const url=dossierPath(domain);
  return '<nav class="tabs" aria-label="Dossier views">'+navLink(url,"Overview",!evidence)+'<a'+test("dossier-evidence-link")+' href="'+url+'/evidence"'+(evidence?' aria-current="page"':'')+'>Evidence</a></nav>';
}
const back='<a class="crumb" href="/">← Company dossiers</a>';
function fieldBlock(f,ans){
  return '<article class="field"'+test("field-"+f)+attr("status",ans.status)+'><div><div class="field-head"><h2>'+fields[f]+'</h2>'+stateChip(ans.status,ans.status==="contested"?"field-contested-"+f:"")+'</div>'+
    (ans.value===null?'<p class="muted">No supported value</p>':'<p class="value"'+test("field-value-"+f)+attr("value",ans.value)+'>'+safe(valueText(f,ans.value))+'</p>')+
    '</div><div'+test("field-citations-"+f)+'>'+ans.citations.map((c,i)=>citation(c,"citation-"+f+"-"+(i+1))).join("")+'</div></article>';
}
function detail(domain){
  const url=dossierPath(domain);document.title=domain+" · Dossier";
  main.innerHTML=back+'<div class="heading"><div><h1'+test("dossier-domain")+'>'+safe(domain)+'</h1><div id="metadata" class="meta"></div></div><div class="controls">'+
    '<button type="button"'+test("dossier-reload")+'>Reload</button><form id="refresh-form">'+submit("dossier-refresh","Refresh dossier")+'</form></div></div><div id="refresh-feedback"></div>'+
    tabs(domain,false)+'<section id="values">'+notice("Loading dossier…","loading")+'</section>';
  let seq=0,timer;
  async function load(){
    const id=++seq;clearTimeout(timer);
    try {
      const d=await api(url);if(id!==seq)return;
      document.querySelector("#metadata").innerHTML=stateChip(d.state,"dossier-state")+'<div class="metrics"><span'+test("dossier-spent")+attr("units",d.spent_units)+'>'+Number(d.spent_units).toLocaleString()+" units spent</span>"+
        (d.researched_at?'<time'+test("dossier-researched-at")+' datetime="'+safe(d.researched_at)+'">Researched '+safe(dateText(d.researched_at))+'</time>':'')+'</div>';
      document.querySelector("#values").innerHTML=Object.entries(fields).map(([f])=>fieldBlock(f,d.fields[f])).join("");
      if(d.state==="building")timer=setTimeout(load,700);
    }catch(err){if(id!==seq)return;document.querySelector("#values").innerHTML=err.status===404?empty("Dossier not found","Return to the library to research this domain.","dossier-not-found"):readFailure(err);}
  }
  by("dossier-reload").onclick=load;
  bindWrite(document.querySelector("#refresh-form"),"refresh",()=>({url:url+"/refresh"}),async ()=>{document.getElementById("refresh-feedback").innerHTML=notice("Refresh accepted.","success");await load();});
  load();
}
function candidate(f,c,i){
  return '<article class="candidate"'+test("candidate-"+f+"-"+(i+1))+attr("value",c.value)+attr("provider",c.provider)+attr("kind",c.kind||"")+attr("url",c.url)+attr("published-at",c.published_at||"")+attr("selected",c.selected)+'><div class="candidate-top"><strong class="candidate-value">'+safe(valueText(f,c.value))+'</strong>'+(c.selected?'<span class="badge known">Selected</span>':'')+'</div><div class="meta"><span>'+safe(kindNames[c.kind]||"Source type unavailable")+'</span><span>'+safe(c.published_at?"Published "+dateText(c.published_at):"Publication date unavailable")+'</span></div>'+citation(c)+'</article>';
}
async function evidence(domain){
  document.title=domain+" evidence · Dossier";
  main.innerHTML=back+'<div class="heading"><div><h1>Company evidence</h1><p>'+safe(domain)+'</p></div></div>'+tabs(domain,true)+'<div id="evidence">'+notice("Loading evidence…","loading")+'</div>';
  const target=document.querySelector("#evidence");
  try {
    const doc=await api(dossierPath(domain));
    target.innerHTML=Object.entries(fields).map(([f,label])=>{
      const items=doc.fields[f].candidates;
      return '<section class="group"><h2>'+label+'</h2><div'+test("evidence-"+f)+'>'+(items.length?items.map((c,i)=>candidate(f,c,i)).join(""):empty("No evidence","No source supports a value for this field.","evidence-empty-"+f))+'</div></section>';
    }).join("");
  }catch(err){target.innerHTML=readFailure(err);}
}
async function contested(){
  document.title="Contested fields · Dossier";main.innerHTML='<div class="heading"><h1>Contested fields</h1></div><div id="disputes">'+notice("Checking dossiers for competing values…","loading")+'</div>';
  const target=document.querySelector("#disputes");
  try{
    const rows=await allRows(),items=[];
    for(let i=0;i<rows.length;i+=10){
      const docs=await Promise.all(rows.slice(i,i+10).map(r=>api(dossierPath(r.domain))));
      for(const d of docs) for(const [f,label] of Object.entries(fields)){
        const a=d.fields[f];if(a.status!=="contested")continue;
        const vals=[...new Set(a.candidates.map(c=>c.value))];
        items.push('<article class="contest-row"'+test("contested-item-"+d.domain+"-"+f)+attr("value",a.value)+'><h2>'+safe(d.domain)+'</h2><strong>'+label+'</strong><p>'+vals.map(v=>safe(valueText(f,v))).join(" · ")+'</p><a href="'+dossierPath(d.domain)+'/evidence">Compare evidence →</a></article>');
      }
    }
    target.innerHTML=items.length?'<div'+test("contested-list")+'>'+items.join("")+'</div>':empty("No contested fields","Fields appear here when sources support competing values.","empty-contested");
  }catch(err){target.innerHTML=readFailure(err);}
}
header();
if(path==="/signup"||path==="/login")auth(path==="/signup");
else if(!session)location.replace("/login?next="+encodeURIComponent(path));
else if(path==="/")home();
else if(path==="/contested")contested();
else {
  const pieces=path.split("/"),domain=normalize(decodeURIComponent(pieces[2])),showEvidence=pieces[3]==="evidence";
  const canonical=dossierPath(domain)+(showEvidence?"/evidence":"");
  if(path!==canonical)history.replaceState(null,"",canonical);
  if(showEvidence)evidence(domain);else detail(domain);
}
