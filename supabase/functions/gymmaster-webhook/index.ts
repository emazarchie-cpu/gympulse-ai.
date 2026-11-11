// GymPulse AI · GymMaster check-in webhook (Supabase Edge Function)
//
// While a gym runs GymPulse AI side by side with GymMaster, GymMaster's Webhook Manager
// (Settings -> Integrations) posts each member check-in here:
//   https://<project>.supabase.co/functions/v1/gymmaster-webhook?gym=<gym id>&key=<secret>
// The gym's link (with its own secret) is shown in GymPulse AI: Member Management -> Import ->
// Running side by side -> Automatic check-ins from GymMaster.
//
// The function only passes the message on: gp_gm_checkin() (sql/phase39_gymmaster_checkins.sql)
// checks the secret, finds the member and saves the visit once. JSON, form posts and query
// strings are all accepted, since GymMaster doesn't publish its format.
// Deploy with JWT verification OFF (GymMaster can't send a Supabase login):
// .github/workflows/deploy-gymmaster-webhook.yml.

import { createClient } from "https://esm.sh/@supabase/supabase-js@2.45.4";

const sb = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function reply(body: Record<string, unknown>, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

async function readBody(req: Request): Promise<Record<string, unknown>> {
  const raw = await req.text();
  if (!raw.trim()) return {};
  try {
    const j = JSON.parse(raw);
    return typeof j === "object" && j !== null ? j : { value: j };
  } catch {
    const form = new URLSearchParams(raw);
    const out: Record<string, unknown> = {};
    for (const [k, v] of form) out[k] = v;
    return Object.keys(out).length ? out : { raw: raw.slice(0, 4000) };
  }
}

Deno.serve(async (req) => {
  const url = new URL(req.url);
  const gym = url.searchParams.get("gym") ?? "";
  const key = url.searchParams.get("key") ?? "";
  if (req.method === "GET" && !url.searchParams.has("memberid")) {
    return reply({ ok: true, service: "GymPulse AI · GymMaster check-ins" });   // GymMaster's "test URL"
  }
  if (!UUID.test(gym) || key.length < 16) return reply({ ok: false, error: "bad link" }, 401);
  const payload: Record<string, unknown> = req.method === "GET" ? {} : await readBody(req);
  for (const [k, v] of url.searchParams) {                                      // values sent in the address
    if (k !== "gym" && k !== "key" && !(k in payload)) payload[k] = v;
  }
  const { data, error } = await sb.rpc("gp_gm_checkin", { p_gym: gym, p_secret: key, p_payload: payload });
  if (error) {
    console.error("gp_gm_checkin failed", error.message);
    return reply({ ok: false, error: "not saved" }, 500);                       // GymMaster may retry
  }
  if (data === "bad_key") return reply({ ok: false, error: "bad link" }, 401);
  return reply({ ok: true, result: data });
});
