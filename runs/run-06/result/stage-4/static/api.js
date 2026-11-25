const sessionKey = "dossier.session";
export function session() {
  try { return JSON.parse(localStorage.getItem(sessionKey)); }
  catch { return null; }
}
export function saveSession(user) {
  if (user) localStorage.setItem(sessionKey, JSON.stringify(user));
  else localStorage.removeItem(sessionKey);
}
export class Refusal extends Error {
  constructor(status, body) {
    super(body?.error?.message || "The request was refused.");
    this.status = status;
    this.code = body?.error?.code;
  }
}
export async function api(path, options = {}) {
  const user = session();
  const headers = {Accept:"application/json", ...options.headers};
  if (user?.token) headers.Authorization = "Bearer " + user.token;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const result = await fetch(path, {cache:"no-store", ...options, headers});
  let data;
  try {
    const raw = await result.text();
    data = JSON.parse(raw, (key, value, context) => {
      if (Number.isInteger(value) && !Number.isSafeInteger(value) && context?.source && /^\d+$/.test(context.source)) return context.source;
      return value;
    });
  } catch {
    if (result.ok || result.status >= 500) throw new Error("The response was incomplete.");
  }
  if (!result.ok) {
    if (result.status >= 500) throw new Error("The service could not confirm the outcome.");
    throw new Refusal(result.status, data);
  }
  return data;
}
export async function listAll(query = "") {
  const rows = [];
  for (;;) {
    const params = new URLSearchParams({q:query,limit:"200",offset:String(rows.length)});
    const page = await api("/dossiers?" + params);
    rows.push(...page.dossiers);
    if (!page.has_more || !page.dossiers.length) return rows;
  }
}
export function key() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2,"0")).join("");
}
