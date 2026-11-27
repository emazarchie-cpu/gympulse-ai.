// GymPulse AI · Door access (Supabase Edge Function)
//
// For door controllers and readers that can call a web address. They send the member's code; the answer
// says whether to open:
//   https://<project>.supabase.co/functions/v1/door-access?key=<gym device key>&code=<member code>
//   -> {"ok": true, "allow": true, "reason": "Membership active", "name": "...", "until": "2027-01-29"}
//   add &format=text to get just OPEN or DENY (for simple controllers)
//   add &door=<name> to say which door, for the log
// door_check() (sql/phase45_door_access.sql) decides and logs every attempt. When the member is let in and
// the gym has saved a door opener link, this function also calls that link to release the lock.
// Deploy with JWT verification OFF (controllers can't send a Supabase login):
// .github/workflows/deploy-door-access.yml.

import { createClient } from "https://esm.sh/@supabase/supabase-js@2.45.4";

const sb = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);

async function params(req: Request, url: URL): Promise<Record<string, string>> {
  const out: Record<string, string> = {};
  for (const [k, v] of url.searchParams) out[k] = v;
  if (req.method === "POST") {
    const raw = await req.text();
    try {
      const j = JSON.parse(raw);
      if (j && typeof j === "object") for (const [k, v] of Object.entries(j)) out[k] ??= String(v);
    } catch {
      for (const [k, v] of new URLSearchParams(raw)) out[k] ??= v;
    }
  }
  return out;
}

Deno.serve(async (req) => {
  const url = new URL(req.url);
  const p = await params(req, url);
  const text = (p.format ?? "").toLowerCase() === "text";
  const send = (body: Record<string, unknown>, status = 200) =>
    text ? new Response(body.allow ? "OPEN" : "DENY", { status, headers: { "Content-Type": "text/plain" } })
         : new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  const key = p.key ?? "";
  const code = p.code ?? p.card ?? p.member ?? p.id ?? "";
  if (key.length < 16) return send({ ok: false, allow: false, error: "bad link" }, 401);
  if (!code) return send({ ok: true, allow: false, reason: "No code sent" });
  const { data, error } = await sb.rpc("door_check", { p_device_key: key, p_code: code, p_door: p.door ?? "Door" });
  if (error) {
    console.error("door_check failed", error.message);
    return send({ ok: false, allow: false, error: "unavailable" }, 500);
  }
  const res = (data ?? {}) as Record<string, unknown>;
  if (res.ok === false) return send({ ok: false, allow: false, error: "bad link" }, 401);
  const opener = res.opener as string | null;
  delete res.opener;                                       // never shown to the device
  if (res.allow && opener && opener.toLowerCase().startsWith("https://")) {
    try {
      await fetch(opener, { signal: AbortSignal.timeout(4000) });
    } catch (e) {
      console.error("door opener did not answer", String(e));
    }
  }
  return send(res);
});
