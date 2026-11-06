"""GymPulse AI · WhatsApp channel (WhatsApp Business Platform, Cloud API).

Automatic messages (renewal reminders, we missed you, new-member check-ins,
celebrations, happiness check) can go out on WhatsApp as well as email. Outside
the 24-hour chat window WhatsApp only allows pre-approved *templates*, so each
kind of message has one template below. Each template has reply buttons; what a
button does is prepared here when the message is sent and saved with it
(messages.meta), and the webhook (supabase/functions/whatsapp-webhook) carries
it out when the member taps:
  * "Renew now"     -> sends the member the gym's payment options
  * "Talk to us"    -> lands in the Follow-ups inbox for the team
  * happiness taps  -> saved as their answer (Grow -> Happiness)
  * "STOP"          -> no more WhatsApp messages to that member

Settings (Render environment + GitHub secrets, never in the code):
  WHATSAPP_TOKEN          permanent System User access token
  WHATSAPP_PHONE_ID       phone number ID that sends
  WHATSAPP_WABA_ID        WhatsApp Business Account ID (templates)
  WHATSAPP_APP_SECRET     app secret (the webhook checks every call with it)
  WHATSAPP_VERIFY_TOKEN   any passphrase, also typed into Meta's webhook settings
  WHATSAPP_API_VERSION    optional, default below
Database: sql/phase17_whatsapp.sql. Setup: docs/WHATSAPP.md.
"""
import os
import re
from datetime import datetime, timezone

import streamlit as st

import gympulse_workspaces as gw

API_VERSION_DEFAULT = "v21.0"
LANG = "en"
MODES = {"email": "Email only",
         "whatsapp_first": "WhatsApp first (email if they're not on WhatsApp)",
         "both": "WhatsApp and email"}

# name, category, body (positional {{n}}), example values, quick-reply button titles
TEMPLATES = {
    "gp_renewal_reminder": {
        "category": "UTILITY",
        "body": "Hi {{1}}, your {{2}} membership at {{3}} {{4}}. Tap Renew now to see how to pay, or Talk to us "
                "if you have a question.",
        "example": ["Ada", "monthly", "Pulse Fitness Lekki", "ends on Fri 14 Nov"],
        "buttons": ["Renew now", "Talk to us"],
    },
    "gp_we_miss_you": {
        "category": "MARKETING",
        "body": "Hi {{1}}, we've missed you at {{2}}! It's been {{3}} days since your last visit. Shall we see you "
                "this week?",
        "example": ["Ada", "Pulse Fitness Lekki", "12"],
        "buttons": ["Yes, I'll come in", "Pause my membership"],
    },
    "gp_new_member_checkin": {
        "category": "MARKETING",
        "body": "Hi {{1}}, how are your first weeks at {{2}} going? If there's anything we can help with, from your "
                "programme to class times, just tap below.",
        "example": ["Ada", "Pulse Fitness Lekki"],
        "buttons": ["Going great", "I'd like some help"],
    },
    "gp_celebration": {
        "category": "MARKETING",
        "body": "Hi {{1}}, a quick note from {{2}}: {{3}} Keep up the great work! 🎉",
        "example": ["Ada", "Pulse Fitness Lekki", "you trained 14 times in October."],
        "buttons": ["Thank you!"],
    },
    "gp_happiness_check": {
        "category": "MARKETING",
        "body": "Hi {{1}}, one quick question from {{2}}: how happy are you with the gym at the moment? Tap an "
                "answer, it goes straight to the team.",
        "example": ["Ada", "Pulse Fitness Lekki"],
        "buttons": ["Love it", "Happy", "It's okay", "Not happy"],
    },
    "gp_member_portal": {
        "category": "UTILITY",
        "body": "Hi {{1}}, here is your private link to your {{2}} membership page: renew, see your check-in code, "
                "visits, rewards and classes. Tap the button below to open it.",
        "example": ["Ada", "Pulse Fitness Lekki"],
        "buttons": [],
        "url_button": {"text": "Open my membership", "base": "https://usegympulseai.com/?me=",
                       "example": "https://usegympulseai.com/?me=3f6c1d2e-8a4b-4c1f-9d2e-5b7a8c9d0e1f"},
    },
}
KIND_TEMPLATE = {"renewal": "gp_renewal_reminder", "missed": "gp_we_miss_you", "week1": "gp_new_member_checkin",
                 "welcome": "gp_new_member_checkin", "milestone": "gp_celebration", "level": "gp_celebration",
                 "reward": "gp_celebration", "progress": "gp_celebration", "pulse": "gp_happiness_check"}
STOP_WORDS = {"stop", "unsubscribe", "stop all", "opt out", "optout"}


# ------------------------------------------------------------------ settings
def _secret(name, default=""):
    v = os.environ.get(name)
    if v:
        return v.strip()
    try:
        return str(st.secrets.get(name, default) or default).strip()
    except Exception:
        return default


def ready():
    """True when GymPulse can send WhatsApp messages (token and number are set)."""
    return bool(_secret("WHATSAPP_TOKEN") and _secret("WHATSAPP_PHONE_ID"))


def setup_status():
    return {k: bool(_secret(k)) for k in ("WHATSAPP_TOKEN", "WHATSAPP_PHONE_ID", "WHATSAPP_WABA_ID",
                                          "WHATSAPP_APP_SECRET", "WHATSAPP_VERIFY_TOKEN")}


def _graph(path):
    return f"https://graph.facebook.com/{_secret('WHATSAPP_API_VERSION', API_VERSION_DEFAULT)}/{path}"


def _headers():
    return {"Authorization": f"Bearer {_secret('WHATSAPP_TOKEN')}"}


def gym_mode(profile=None):
    """How this gym's automatic messages go out: email / whatsapp_first / both."""
    p = profile if profile is not None else (st.session_state.get("user_profile") or {})
    mode = dict((p.get("settings") or {}).get("whatsapp") or {}).get("mode", "email")
    return mode if mode in MODES else "email"


SCOPES = {"renewals": "Renewal reminders only (cheapest: about ₦10 each)",
          "all": "All automatic messages (promotional ones cost about ₦80 each)"}
DEFAULT_LIMIT = 400
RATES_USD = {"UTILITY": 0.0067, "MARKETING": 0.0516}     # Meta's Nigeria prices per message (check WhatsApp Manager)


def wa_settings(profile=None):
    """The gym's WhatsApp choices: mode, scope (renewals / all) and monthly limit (0 = no limit)."""
    p = profile if profile is not None else (st.session_state.get("user_profile") or {})
    w = dict((p.get("settings") or {}).get("whatsapp") or {})
    scope = w.get("scope", "renewals")
    try:
        limit = max(0, int(w.get("limit", DEFAULT_LIMIT)))
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    return {"mode": gym_mode(p), "scope": scope if scope in SCOPES else "renewals", "limit": limit}


def allowed(kind, settings):
    """May this kind of automatic message go on WhatsApp under the gym's choice?"""
    return kind == "renewal" or settings.get("scope") == "all"


def naira_per_usd():
    try:
        return float(_secret("WHATSAPP_NAIRA_PER_USD", "1550") or 1550)
    except ValueError:
        return 1550.0


def month_usage(supabase, gym_id=None, since=None):
    """WhatsApp messages sent this month (one gym, or every gym with gym_id=None) and the estimated cost.
    Returns {"count", "utility", "marketing", "usd", "naira", "by_gym": {gym_id: {...}}}."""
    since = since or datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    q = supabase.table("messages").select("gym_id, meta").eq("channel", "whatsapp").eq("direction", "out") \
        .gte("created_at", since.isoformat())
    if gym_id:
        q = q.eq("gym_id", gym_id)
    try:
        rows = gw.fetch_all(q.order("created_at"))
    except Exception:
        rows = []
    rate = naira_per_usd()
    by = {}
    for r in rows:
        tpl = (r.get("meta") or {}).get("template") if isinstance(r.get("meta"), dict) else None
        cat = TEMPLATES.get(tpl, {}).get("category", "UTILITY")       # replies are charged as utility
        g = by.setdefault(r.get("gym_id"), {"count": 0, "utility": 0, "marketing": 0, "usd": 0.0})
        g["count"] += 1
        g["marketing" if cat == "MARKETING" else "utility"] += 1
        g["usd"] += RATES_USD.get(cat, RATES_USD["UTILITY"])
    for g in by.values():
        g["naira"] = g["usd"] * rate
    tot = {k: sum(g[k] for g in by.values()) for k in ("count", "utility", "marketing", "usd")}
    tot["naira"] = tot["usd"] * rate
    tot["by_gym"] = by
    return tot


def to_digits(phone):
    d = gw.whatsapp_digits(phone)
    return d if 10 <= len(d) <= 15 else ""


# ------------------------------------------------------------------ sending
def _post(payload):
    import requests
    r = requests.post(_graph(f"{_secret('WHATSAPP_PHONE_ID')}/messages"), json=payload, timeout=20,
                      headers=_headers())
    if r.status_code >= 300:
        try:
            err = r.json().get("error", {})
            text = f"{err.get('code', r.status_code)}: {err.get('message', '')}"
        except Exception:
            text = r.text[:160]
        raise RuntimeError(f"WhatsApp was not sent ({text[:200]})")
    return (r.json().get("messages") or [{}])[0].get("id", "")


def template_payload(digits, name, params, payloads=(), url_suffix=None):
    comps = [{"type": "body", "parameters": [{"type": "text", "text": _clean(p)} for p in params]}]
    for i, pl in enumerate(payloads):
        comps.append({"type": "button", "sub_type": "quick_reply", "index": str(i),
                      "parameters": [{"type": "payload", "payload": pl}]})
    if url_suffix is not None:
        comps.append({"type": "button", "sub_type": "url", "index": str(len(payloads)),
                      "parameters": [{"type": "text", "text": str(url_suffix)}]})
    return {"messaging_product": "whatsapp", "to": digits, "type": "template",
            "template": {"name": name, "language": {"code": LANG}, "components": comps}}


def _clean(text):
    # Template values can't contain new lines, tabs or more than 4 spaces in a row
    return re.sub(r"\s+", " ", str(text or "")).strip()[:900] or "-"


def send_template(digits, name, params, payloads=(), url_suffix=None):
    return _post(template_payload(digits, name, params, payloads, url_suffix))


def send_text(digits, body):
    return _post({"messaging_product": "whatsapp", "to": digits, "type": "text",
                  "text": {"body": str(body)[:4096], "preview_url": True}})


def _first(name):
    return (str(name or "").split() or ["there"])[0]


def build(kind, m, ref, subject, body, buttons, biz, owner, pay=None, today=None):
    """The WhatsApp version of one automatic message: (template, params, payloads, actions).
    actions = {payload: {"reply": text, "feedback": {...}, "inbox": bool}} for the webhook."""
    import gympulse_grow as gg
    today = today or gw.today_local()
    first = _first(m.get("full_name"))
    name = KIND_TEMPLATE[kind]
    thanks = f"Thanks {first}! Someone from {biz} will reply here shortly."
    if kind == "renewal":
        end = m.get("end") if gg._has_date(m.get("end")) else None
        plan, amount = gg.plan_price(m)
        days = (end - today).days if end else None
        when = ("is due for renewal" if days is None else "ends today" if days == 0 else
                f"ends on {end:%a %d %b}" if days > 0 else f"ended on {end:%d %b}")
        pay_text = gg.renewal_text(m.get("full_name"), amount, plan, end, dict(pay or {}),
                                   gw.member_code(m["id"]), None)
        return (name, [first, gw.plan_phrase(plan).lower(), biz, when], ["renew", "talk"],
                {"renew": {"reply": pay_text, "inbox": True}, "talk": {"reply": thanks, "inbox": True}})
    if kind == "missed":
        try:
            last = datetime.fromisoformat(ref.split(":", 1)[1]).date()
            days = (today - last).days
        except Exception:
            days = 14
        return (name, [first, biz, str(days)], ["coming", "pause"],
                {"coming": {"reply": f"Brilliant, {first}! See you soon 💪 {biz}", "inbox": True},
                 "pause": {"reply": f"No problem, {first}. Someone from {biz} will message you here about pausing "
                                    "your membership.", "inbox": True}})
    if kind in ("week1", "welcome"):
        return (name, [first, biz], ["great", "help"],
                {"great": {"reply": f"Love to hear it, {first}! Keep going 💪 {biz}", "inbox": False},
                 "help": {"reply": thanks, "inbox": True}})
    if kind == "pulse":
        import urllib.parse as up
        q = {}
        for _, url in buttons or []:
            q = dict(up.parse_qsl(up.urlparse(url).query))
            if q.get("fb"):
                break
        acts = {}
        for score, title in zip((4, 3, 2, 1), TEMPLATES[name]["buttons"]):
            reply = (f"Thank you, {first}! 🙏" if score >= 3 else
                     f"Thank you for telling us, {first}. Someone from {biz} will be in touch to make it right.")
            acts[f"pulse{score}"] = {"reply": reply, "inbox": score <= 2,
                                     "feedback": {"token": q.get("fb"), "round": q.get("r"), "score": score}}
        return name, [first, biz], list(acts), acts
    # celebrations: milestone, level, reward, progress
    line = _celebration_line(subject, first, biz)
    return (name, [first, biz, line], ["thanks"], {"thanks": {"reply": f"🙌 {biz}", "inbox": False}})


def _celebration_line(subject, first, biz):
    s = str(subject or "")
    s = re.sub(rf"^{re.escape(first)},\s*", "", s)
    s = re.sub(rf",?\s*{re.escape(first)}[!?.]*$", "", s)
    s = re.sub(rf"\s*at {re.escape(biz)}", "", s).strip(" ,")
    s = s[:1].upper() + s[1:] if s else "you're doing brilliantly."
    return s if s.endswith((".", "!", "?")) else s + "."


def opt_outs(supabase, gym_id, ids):
    """Members who replied STOP on WhatsApp (empty before phase 17 is run)."""
    try:
        rows = (supabase.table("members").select("id, whatsapp_opt_out").eq("gym_id", gym_id)
                .in_("id", list(ids)[:1000]).execute().data or [])
        return {r["id"] for r in rows if r.get("whatsapp_opt_out")}
    except Exception:
        return set()


def send_member(supabase, gym_id, m, kind, ref, subject, body, buttons, profile=None):
    """Send one automatic message on WhatsApp and log it. Returns (ok, info)."""
    if not ready():
        return False, "WhatsApp isn't set up"
    digits = to_digits(m.get("phone"))
    if not digits:
        return False, "no WhatsApp number"
    import gympulse_grow as gg
    biz, owner = gg._biz()
    pay = dict(((profile or st.session_state.get("user_profile") or {}).get("settings") or {}).get("collect") or {})
    name, params, payloads, actions = build(kind, m, ref, subject, body, buttons, biz, owner, pay)
    try:
        wamid = send_template(digits, name, params, payloads)
    except Exception as error:
        return False, str(error)
    text = TEMPLATES[name]["body"]
    for i, p in enumerate(params, 1):
        text = text.replace("{{%d}}" % i, _clean(p))
    log(supabase, gym_id, m["id"], text, wamid, digits, {"kind": kind, "template": name, "actions": actions})
    return True, wamid


def log(supabase, gym_id, member_id, body, wamid, digits, meta):
    row = {"gym_id": gym_id, "member_id": member_id, "channel": "whatsapp", "direction": "out", "body": body,
           "status": "sent", "provider_id": wamid or None, "is_read": True, "wa_to": digits, "meta": meta}
    for _ in range(3):
        try:
            supabase.table("messages").insert(row).execute()
            return True
        except Exception as error:
            gone = re.search(r"'(\w+)' column", str(error))
            if gone and gone.group(1) in row and gone.group(1) in ("wa_to", "meta"):
                row.pop(gone.group(1))
                continue
            return False
    return False


# ------------------------------------------------------------------ templates (admin)
def template_definition(name):
    t = TEMPLATES[name]
    comps = [{"type": "BODY", "text": t["body"], "example": {"body_text": [t["example"]]}}]
    buttons = [{"type": "QUICK_REPLY", "text": b} for b in t["buttons"]]
    if t.get("url_button"):
        u = t["url_button"]
        buttons.append({"type": "URL", "text": u["text"], "url": u["base"] + "{{1}}", "example": [u["example"]]})
    if buttons:
        comps.append({"type": "BUTTONS", "buttons": buttons})
    return {"name": name, "language": LANG, "category": t["category"], "components": comps}


def template_statuses():
    """{name: status} from Meta (APPROVED, PENDING, REJECTED…), or None if it can't be read."""
    import requests
    waba = _secret("WHATSAPP_WABA_ID")
    if not (waba and _secret("WHATSAPP_TOKEN")):
        return None
    try:
        r = requests.get(_graph(f"{waba}/message_templates"), params={"fields": "name,status,language",
                                                                    "limit": 200},
                         headers=_headers(), timeout=20)
        r.raise_for_status()
        return {t["name"]: t.get("status", "") for t in r.json().get("data", []) if t.get("language") == LANG}
    except Exception:
        return None


def submit_template(name):
    import requests
    r = requests.post(_graph(f"{_secret('WHATSAPP_WABA_ID')}/message_templates"), json=template_definition(name),
                      headers=_headers(), timeout=20)
    if r.status_code >= 300:
        try:
            msg = r.json().get("error", {}).get("error_user_msg") or r.json().get("error", {}).get("message")
        except Exception:
            msg = r.text[:200]
        raise RuntimeError(msg or f"HTTP {r.status_code}")
    return r.json().get("status", "PENDING")


def render_admin_setup():
    """Founder's WhatsApp page (Admin): connection, templates, a test message."""
    gw.intro("WhatsApp", ":material/chat:",
             "GymPulse sends automatic messages on WhatsApp from your WhatsApp Business number. Each kind of "
             "message uses a template Meta approves once. Setup steps: docs/WHATSAPP.md.")
    stt = setup_status()
    webhook_only = {"WHATSAPP_APP_SECRET", "WHATSAPP_VERIFY_TOKEN"}     # used by the Supabase webhook, not here
    gw.table([{"Setting": k, "Status": "Set" if v else ("Webhook only" if k in webhook_only else "Missing")}
              for k, v in stt.items()],
             pills={"Status": {"Set": "lime", "Missing": "amber", "Webhook only": "grey"}},
             caption="Add the first three in Render (Environment) and GitHub (Settings → Secrets). The app secret and "
                     "verify token only go in GitHub: the Deploy WhatsApp webhook action saves them on Supabase. "
                     "Never paste them in chat.")
    if not ready():
        st.info("WhatsApp is off until WHATSAPP_TOKEN and WHATSAPP_PHONE_ID are set. Email keeps working as normal.")
        return
    _render_usage()
    statuses = template_statuses()
    st.markdown('<div class="section-label">TEMPLATES</div>', unsafe_allow_html=True)
    gw.table([{"Template": n, "Type": t["category"].title(), "Buttons": ", ".join(t["buttons"] + ([t["url_button"]["text"] + " (link)"] if t.get("url_button") else [])),
               "Status": (statuses or {}).get(n, "Not submitted" if statuses is not None else "Unknown").title()}
              for n, t in TEMPLATES.items()],
             pills={"Status": {"Approved": "lime", "Pending": "amber", "Rejected": "red", "Not Submitted": "grey"}},
             wide=("Buttons",),
             caption="Utility = reminders about a membership; Marketing = everything else (Meta's rules and prices).")
    missing = [n for n in TEMPLATES if statuses is not None and n not in statuses]
    if missing and st.button(f"Submit {len(missing)} template(s) to Meta for approval", type="primary",
                             key="wa_submit"):
        done, errs = 0, []
        for n in missing:
            try:
                submit_template(n)
                done += 1
            except Exception as error:
                errs.append(f"{n}: {error}")
        st.success(f"{done} submitted. Meta usually reviews them within minutes to a day.") if done else None
        for e in errs:
            st.error(e)
    with st.form("wa_test", border=True):
        st.markdown("**Send a test message**")
        c1, c2 = st.columns([2, 1])
        num = c1.text_input("WhatsApp number", placeholder="0803 000 0000")
        tpl = c2.selectbox("Template", list(TEMPLATES))
        if st.form_submit_button("Send test"):
            d = to_digits(num)
            if not d:
                st.error("Enter a full phone number.")
            else:
                ex = TEMPLATES[tpl]["example"]
                url = TEMPLATES[tpl].get("url_button")
                try:
                    wamid = send_template(d, tpl, ex, url_suffix=url["example"].split("=")[-1] if url else None)
                    st.success(f"Sent. Check the phone. (Message ID {wamid[:24]}…)")
                except Exception as error:
                    st.error(str(error))


def _render_usage():
    """Founder's view: WhatsApp messages and estimated Meta cost per gym this month."""
    import gympulse_admin as gadm
    sc = gadm.service_client()
    if sc is None:
        return
    u = month_usage(sc)
    st.markdown('<div class="section-label">THIS MONTH</div>', unsafe_allow_html=True)
    gw.kpi_row([("WhatsApp messages", f"{u['count']:,}", "cyan", f"{u['utility']:,} utility · {u['marketing']:,} marketing"),
                ("Estimated Meta cost", f"₦{u['naira']:,.0f}", "amber", f"about ${u['usd']:,.2f}"),
                ("Gyms using WhatsApp", f"{len(u['by_gym']):,}", "lime", "")])
    if u["by_gym"]:
        names = {}
        try:
            for g in sc.table("gyms").select("id, business_name").in_("id", list(u["by_gym"])).execute().data or []:
                names[g["id"]] = g.get("business_name") or "Gym"
        except Exception:
            pass
        gw.table([{"Gym": names.get(gid, "Gym"), "Messages": v["count"], "Marketing": v["marketing"],
                   "Est. cost (₦)": f"{v['naira']:,.0f}"}
                  for gid, v in sorted(u["by_gym"].items(), key=lambda x: -x[1]["usd"])],
                 caption=f"Estimated at ${RATES_USD['UTILITY']} (utility) and ${RATES_USD['MARKETING']} (marketing) per "
                         f"message and ₦{naira_per_usd():,.0f} per dollar (WHATSAPP_NAIRA_PER_USD). Meta's actual bill "
                         "is in WhatsApp Manager.")


def render_gym_setting(supabase, owner_id, gym_id=None):
    """The gym's choices: channel and which messages use WhatsApp; the plan's included WhatsApp messages."""
    cfg = wa_settings()
    with st.container(border=True):
        st.markdown("##### :material/chat: How messages go out")
        if not ready():
            st.caption("WhatsApp sending is coming soon. Until then automatic messages go by email, and you can "
                       "send any message on WhatsApp yourself from Follow-ups.")
            return
        allow = {"wa_renew": 0, "wa_promo": 0, "plan": ""}
        if gym_id:
            import gympulse_billing as gbill
            allow = gbill.wa_allowance(supabase, gym_id)
        staff = st.session_state.get("role") == "staff"
        scopes = dict(SCOPES)
        scopes["renewals"] = "Renewal reminders only"
        scopes["all"] = (f"All automatic messages (uses your {allow['wa_promo']:,} promotional messages)"
                         if allow["wa_promo"] else "All automatic messages (your plan sends promotional ones by email)")
        with st.form("wa_settings_form", border=False):
            mode = st.radio("Channel", list(MODES), index=list(MODES).index(cfg["mode"]), format_func=MODES.get,
                            key="wa_mode")
            scope = st.radio("Which messages can use WhatsApp", list(scopes), index=list(scopes).index(cfg["scope"]),
                             format_func=scopes.get, key="wa_scope")
            save = st.form_submit_button("Save", type="primary", disabled=staff)
        if save:
            import gympulse_grow as gg
            gg._save_settings(supabase, owner_id, {"whatsapp": {"mode": mode, "scope": scope}}, "WhatsApp settings saved.")
            st.rerun()
        if gym_id and cfg["mode"] != "email":
            u = month_usage(supabase, gym_id)
            st.markdown(f"**Included in your {gw._esc(allow['plan'] or 'plan')} this month** · no extra charges")
            st.progress(min(1.0, u["utility"] / allow["wa_renew"]) if allow["wa_renew"] else 1.0,
                        text=f"Renewal reminders and replies: {u['utility']:,} of {allow['wa_renew']:,}")
            if allow["wa_promo"]:
                st.progress(min(1.0, u["marketing"] / allow["wa_promo"]),
                            text=f"Promotional messages: {u['marketing']:,} of {allow['wa_promo']:,}")
            st.caption("When a WhatsApp allowance is used up, those messages go by email until next month. "
                       "Need more? A bigger plan includes more WhatsApp messages.")
        st.caption("Members who reply STOP never get WhatsApp messages again. Replies and button taps appear in "
                   "Follow-ups.")
