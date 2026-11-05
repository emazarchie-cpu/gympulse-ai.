// GymPulse AI · WhatsApp webhook (Supabase Edge Function)
//
// Meta calls this when a message is sent, delivered or read, and when a member
// replies or taps a button. It:
//   * checks every call really comes from Meta (X-Hub-Signature-256 + app secret)
//   * updates the message's ticks (sent -> delivered -> read, or failed)
//   * saves replies in the Follow-ups inbox (messages table)
//   * carries out reply buttons, using what GymPulse saved with the message
//     (messages.meta.actions): send a reply, save a happiness answer
//   * STOP / START switches WhatsApp messages off / on for that member
//
// Secrets (Supabase -> Edge Functions -> Secrets): WHATSAPP_TOKEN,
// WHATSAPP_APP_SECRET, WHATSAPP_VERIFY_TOKEN, optional WHATSAPP_API_VERSION.
// SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are provided by Supabase.
// Deploy with JWT verification OFF (Meta can't send a Supabase login).
// Setup: docs/WHATSAPP.md.

import { createClient } from "https://esm.sh/@supabase/supabase-js@2.45.4";

const sb = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
const TOKEN = Deno.env.get("WHATSAPP_TOKEN") ?? "";
const APP_SECRET = Deno.env.get("WHATSAPP_APP_SECRET") ?? "";
const VERIFY = Deno.env.get("WHATSAPP_VERIFY_TOKEN") ?? "";
const VERSION = Deno.env.get("WHATSAPP_API_VERSION") ?? "v21.0";
const RANK: Record<string, number> = { sent: 1, delivered: 2, read: 3, failed: 4 };

async function validSignature(raw: string, header: string | null): Promise<boolean> {
  if (!APP_SECRET || !header?.startsWith("sha256=")) return false;
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(APP_SECRET),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const mac = new Uint8Array(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(raw)));
  const hex = [...mac].map((b) => b.toString(16).padStart(2, "0")).join("");
  const got = header.slice(7);
  if (got.length !== hex.length) return false;
  let diff = 0;
  for (let i = 0; i < hex.length; i++) diff |= hex.charCodeAt(i) ^ got.charCodeAt(i);
  return diff === 0;
}

async function sendText(phoneId: string, to: string, body: string): Promise<string | null> {
  const r = await fetch(`https://graph.facebook.com/${VERSION}/${phoneId}/messages`, {
    method: "POST",
    headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" },
    body: JSON.stringify({ messaging_product: "whatsapp", to, type: "text", text: { body: body.slice(0, 4096) } }),
  });
  if (!r.ok) {
    console.error("reply not sent", r.status, (await r.text()).slice(0, 300));
    return null;
  }
  const j = await r.json();
  return j?.messages?.[0]?.id ?? null;
}

async function reply(phoneId: string, to: string, gymId: string, memberId: string | null, body: string) {
  const wamid = await sendText(phoneId, to, body);
  await sb.from("messages").insert({
    gym_id: gymId, member_id: memberId, channel: "whatsapp", direction: "out", body,
    status: wamid ? "sent" : "failed", provider_id: wamid, is_read: true, wa_to: to,
  });
}

async function onStatus(s: any) {
  const status = String(s.status ?? "");
  if (!RANK[status] || !s.id) return;
  const { data } = await sb.from("messages").select("id, status").eq("provider_id", s.id).limit(1);
  const row = data?.[0];
  if (!row || (RANK[row.status] ?? 0) >= RANK[status]) return;     // never go back from read to delivered
  await sb.from("messages").update({ status, updated_at: new Date().toISOString() }).eq("id", row.id);
}

async function onMessage(msg: any, phoneId: string) {
  const from = String(msg.from ?? "");
  if (!from || !msg.id) return;
  const { data: dup } = await sb.from("messages").select("id").eq("provider_id", msg.id).limit(1);
  if (dup?.length) return;                                           // Meta retried this call

  let text = "";
  let payload = "";
  if (msg.type === "text") text = msg.text?.body ?? "";
  else if (msg.type === "button") { text = msg.button?.text ?? ""; payload = msg.button?.payload ?? ""; }
  else if (msg.type === "interactive") {
    const r = msg.interactive?.button_reply ?? msg.interactive?.list_reply ?? {};
    text = r.title ?? ""; payload = r.id ?? "";
  } else text = `[${msg.type} message]`;

  // Which gym and member: the message they replied to, else the latest gym that messaged them
  let gymId = "", memberId: string | null = null, actions: Record<string, any> = {};
  if (msg.context?.id) {
    const { data } = await sb.from("messages").select("gym_id, member_id, meta")
      .eq("provider_id", msg.context.id).limit(1);
    if (data?.length) {
      gymId = data[0].gym_id; memberId = data[0].member_id; actions = data[0].meta?.actions ?? {};
    }
  }
  if (!gymId) {
    const { data } = await sb.rpc("gp_wa_route", { p_digits: from });
    if (data?.length) { gymId = data[0].gym_id; memberId = data[0].member_id; }
  }
  if (!gymId) { console.log("message from an unknown number"); return; }

  const action = payload ? actions[payload] : undefined;
  const word = text.trim().toLowerCase();
  const stop = ["stop", "unsubscribe", "stop all", "opt out", "optout"].includes(word);
  const start = ["start", "subscribe", "unstop"].includes(word);

  await sb.from("messages").insert({
    gym_id: gymId, member_id: memberId, channel: "whatsapp", direction: "in", body: text || "(no text)",
    status: "received", provider_id: msg.id, wa_to: from,
    is_read: stop || start || (action ? !action.inbox : false),
    meta: payload ? { payload } : null,
  });

  if ((stop || start) && memberId) {
    await sb.from("members").update({ whatsapp_opt_out: stop }).eq("id", memberId);
    const { data: g } = await sb.from("gyms").select("business_name").eq("id", gymId).limit(1);
    const gym = g?.[0]?.business_name ?? "your gym";
    await reply(phoneId, from, gymId, memberId, stop
      ? `Done. You won't get WhatsApp messages from ${gym} through GymPulse AI any more. Reply START to turn them back on.`
      : `Welcome back! You'll get WhatsApp messages from ${gym} again. Reply STOP at any time.`);
    return;
  }
  if (action?.feedback?.token) {
    const f = action.feedback;
    const { error } = await sb.rpc("gp_member_feedback",
      { p_token: f.token, p_round: f.round, p_score: f.score, p_comment: null });
    if (error) console.error("feedback not saved", error.message);
  }
  if (action?.reply) await reply(phoneId, from, gymId, memberId, String(action.reply));
}

Deno.serve(async (req) => {
  const url = new URL(req.url);
  if (req.method === "GET") {                                       // Meta's one-time check
    const ok = url.searchParams.get("hub.mode") === "subscribe" && VERIFY &&
      url.searchParams.get("hub.verify_token") === VERIFY;
    return ok ? new Response(url.searchParams.get("hub.challenge") ?? "", { status: 200 })
      : new Response("forbidden", { status: 403 });
  }
  if (req.method !== "POST") return new Response("method not allowed", { status: 405 });
  const raw = await req.text();
  if (!(await validSignature(raw, req.headers.get("x-hub-signature-256")))) {
    return new Response("bad signature", { status: 401 });
  }
  let body: any;
  try { body = JSON.parse(raw); } catch { return new Response("bad json", { status: 400 }); }
  for (const entry of body.entry ?? []) {
    for (const change of entry.changes ?? []) {
      const v = change.value ?? {};
      const phoneId = v.metadata?.phone_number_id ?? "";
      for (const s of v.statuses ?? []) {
        try { await onStatus(s); } catch (e) { console.error("status", e); }
      }
      for (const m of v.messages ?? []) {
        try { await onMessage(m, phoneId); } catch (e) { console.error("message", e); }
      }
    }
  }
  return new Response("ok", { status: 200 });                       // always 200 so Meta doesn't retry forever
});
