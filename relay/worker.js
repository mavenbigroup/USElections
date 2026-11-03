// Cloudflare Worker: relays "Refresh" clicks from the public page to GitHub's workflow_dispatch.
// Secrets (set in the Worker's Settings → Variables): GH_TOKEN (fine-grained, Actions: write on this repo).
// Rate-limited to one dispatch per 60 s so a shared link can't spam the Action.
const REPO = "MavenBIGroup/USElections";
const WORKFLOW = "refresh.yml";
const ALLOW_ORIGIN = "https://mavenbigroup.github.io";
let last = 0;

export default {
  async fetch(req, env) {
    const cors = {
      "Access-Control-Allow-Origin": ALLOW_ORIGIN,
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    };
    if (req.method === "OPTIONS") return new Response(null, { headers: cors });
    if (req.method !== "POST") return new Response("POST only", { status: 405, headers: cors });
    const now = Date.now();
    if (now - last < 60000) {
      return new Response(JSON.stringify({ ok: true, skipped: true, wait: Math.ceil((60000 - (now - last)) / 1000) }), { headers: { ...cors, "Content-Type": "application/json" } });
    }
    const r = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${env.GH_TOKEN}`,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
        "User-Agent": "election-desk-relay",
      },
      body: JSON.stringify({ ref: "main" }),
    });
    if (r.status === 204) last = now;
    return new Response(JSON.stringify({ ok: r.status === 204, status: r.status }), { headers: { ...cors, "Content-Type": "application/json" } });
  },
};
