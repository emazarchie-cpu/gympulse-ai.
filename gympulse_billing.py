"""GymPulse AI · Free trial, plans and subscriptions.

Every gym gets a 30-day free trial from the day it signs up (gyms that existed
before billing was switched on get 30 days from that day). The trial includes
every feature. When it ends there are no extra days: an Upgrade pop-up lists
the plans and the gym sees only the Subscription page until it pays. Its data
is kept, never deleted.

Plans (name, prices, who it's for, which features) are set by the founder in
Admin → Billing. Higher plans unlock more pages (PAGE_LEVEL). Gyms pay online
with Paystack (PAYSTACK_SECRET_KEY): the payment is checked with Paystack and
the subscription switches on by itself. Bank transfer stays as a fallback; the
founder confirms those in Admin.
Tables: sql/phase10_billing.sql. If the SQL hasn't been run, nothing is locked.
"""
import json
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

import pandas as pd
import streamlit as st

import gympulse_workspaces as gw

TRIAL_DAYS = 30
GRACE_DAYS = 0          # locks the moment the 30th day ends (owners get emails before that)
ALWAYS_OPEN = ("Subscription", "Settings", "FAQs", "Admin")
PAYSTACK_API = "https://api.paystack.co"

# Feature levels. A plan's "access" picks one; higher plans include everything below.
LEVELS = {1: "Essentials", 2: "Growth tools", 3: "Everything"}
FEATURES = {
    1: ["Member records, plans and spreadsheet import",
        "Front-desk and QR check-in",
        "Payments and renewal tracking",
        "Risk Radar: see who has stopped coming, and why",
        "Follow-ups board for your staff",
        "Automatic renewal reminder emails with your logo",
        "Monthly report of members and money kept"],
    2: ["Action Centre: the best next step for every member",
        "Grow: campaigns, loyalty points, referrals and challenges",
        "Automatic \"we missed you\", first-week, milestone and reward emails",
        "Happiness check-ins: hear from unhappy members before they quit",
        "Business Insights: revenue, renewals and trends"],
    3: ["Archie, your AI retention assistant",
        "Model insights: why each member was flagged"],
}
SUPPORT = {"standard": "Standard help", "priority": "Priority help", "dedicated": "Dedicated account manager"}
SERVICE_LEVEL = [   # (service, lowest support level that includes it)
    ("Priority WhatsApp support from the GymPulse team", "priority"),
    ("We import your members and set everything up with you", "priority"),
    ("A dedicated account manager", "dedicated"),
    ("Staff training and a monthly review call", "dedicated"),
]
SERVICES = [x for x, _ in SERVICE_LEVEL]
GRACE_OVER_LIMIT = 30          # days to upgrade after going over the plan's member limit
HEADROOM = 0.10                # during those days, up to 10% more members can be added (same as the database)


def _support_rank(level):
    return list(SUPPORT).index(level) if level in SUPPORT else 0
PAGE_LEVEL = {"Action Centre": 2, "Grow": 2, "Business Insights": 2,
              "Archie": 3, "Model Insights": 3, "About the Model": 3}

DEFAULT_PLANS = [   # every plan has every feature; price follows gym size and the WhatsApp messages included
    {"name": "Starter", "access": 3, "monthly": 20000, "yearly": 200000, "for_who": "Up to 150 members",
     "members": 150, "wa_renew": 250, "wa_promo": 0, "archie": 100, "support": "standard",
     "tagline": "Every feature, sized for a small gym.", "popular": False},
    {"name": "Growth", "access": 3, "monthly": 45000, "yearly": 450000, "for_who": "Up to 500 members",
     "members": 500, "wa_renew": 700, "wa_promo": 0, "archie": 300, "support": "standard",
     "tagline": "Every feature, for a busy neighbourhood gym.", "popular": True},
    {"name": "Pro", "access": 3, "monthly": 100000, "yearly": 1000000, "for_who": "Up to 1,500 members",
     "members": 1500, "wa_renew": 2000, "wa_promo": 150, "archie": 1000, "support": "priority",
     "tagline": "Every feature, WhatsApp promotions and priority help.", "popular": False},
    {"name": "Business", "access": 3, "monthly": 280000, "yearly": 2800000, "for_who": "Up to 5,000 members",
     "members": 5000, "wa_renew": 6500, "wa_promo": 400, "archie": 3000, "support": "dedicated",
     "tagline": "For big gyms and multi-branch brands.", "popular": False},
    {"name": "Enterprise", "access": 3, "monthly": 750000, "yearly": 7500000, "for_who": "Up to 20,000 members",
     "members": 20000, "wa_renew": 24000, "wa_promo": 1000, "archie": 0, "support": "dedicated",
     "tagline": "For gym chains, with WhatsApp at scale.", "popular": False},
]
TRIAL_ALLOWANCE = {"wa_renew": 300, "wa_promo": 30, "archie": 100}    # free trial and pilot mode
DEFAULT_PRICING = {"plans": [], "monthly": None, "yearly": None, "currency": "NGN", "pay_link": "",
                   "bank_name": "", "bank_account": "", "bank_holder": "",
                   "contact_whatsapp": "", "contact_email": "emmanuel@usegympulseai.com",
                   "note": "Founding gyms keep their price for life."}


def _num(x):
    try:
        v = float(x)
        return v if v == v and v > 0 else None
    except (TypeError, ValueError):
        return None


def plans(p):
    """The plans from Admin → Billing (or the starting plans): name, access, monthly, yearly, for_who, tagline, popular."""
    raw = [x for x in (p.get("plans") or []) if gw._text(x.get("name")) and (_num(x.get("monthly")) or _num(x.get("yearly")))]
    if not raw and _num(p.get("monthly")):           # a single price set before plans existed
        raw = [{"name": "Standard", "monthly": p["monthly"], "yearly": p.get("yearly"), "access": 3}]
    if not raw:
        raw = DEFAULT_PLANS
    out = []
    for i, x in enumerate(raw):
        mo, yr = _num(x.get("monthly")), _num(x.get("yearly"))
        access = 3                                # every plan includes every feature; price is by gym size
        who = gw._text(x.get("for_who")).strip()
        members = _int(x.get("members"))
        if members is None:                       # older saved plans: read "Up to 300 members"
            m = re.search(r"([\d,]+)", who) if "up to" in who.lower() else None
            members = int(m.group(1).replace(",", "")) if m else 0
        wa_renew = _int(x.get("wa_renew"))
        if wa_renew is None:
            wa_renew = round(members * 1.3, -1) if members else 300
        out.append({"name": gw._text(x.get("name")).strip(), "access": access, "monthly": mo,
                    "yearly": yr or (mo * 10 if mo else None), "for_who": who,
                    "members": members, "wa_renew": int(wa_renew), "wa_promo": int(_int(x.get("wa_promo")) or 0),
                    "support": (x.get("support") if x.get("support") in SUPPORT
                                else "priority" if x.get("priority") or (x.get("priority") is None
                                                                         and (members == 0 or members >= 1500))
                                else "standard"),
                    "archie": int(_int(x.get("archie")) if _int(x.get("archie")) is not None
                                  else (0 if not members else max(100, members * 2))),
                    "tagline": gw._text(x.get("tagline")).strip(), "popular": bool(x.get("popular"))})
    return out


def _int(x):
    try:
        v = float(str(x).replace(",", ""))
        return int(v) if v == v and v >= 0 else None
    except (TypeError, ValueError):
        return None


def plan_lines(plan):
    """The plan's own size and WhatsApp benefits, in plain words."""
    lines = [f"Up to {plan['members']:,} members" if plan.get("members") else "Unlimited members"]
    if plan.get("wa_renew"):
        lines.append(f"{plan['wa_renew']:,} WhatsApp renewal reminders and replies a month, included")
    if plan.get("wa_promo"):
        lines.append(f"{plan['wa_promo']:,} WhatsApp promotional messages a month, included")
    lines.append(f"Archie AI: {plan['archie']:,} questions a month" if plan.get("archie") else "Archie AI: unlimited questions")
    lines.append("Unlimited emails and member app")
    lines.append("No extra charges: if WhatsApp messages run out, they go by email")
    rank = _support_rank(plan.get("support"))
    lines += [svc for svc, lv in SERVICE_LEVEL if rank >= _support_rank(lv)]
    return lines


def features(ps, i):
    """(heading, [benefits]) for plan i: its own level, with 'Everything in X, plus' for higher plans."""
    level = ps[i]["access"]
    below = [x for x in ps[:i] if x["access"] < level]
    if below and level > 1:
        return (f"Everything in {below[-1]['name']}, plus:",
                plan_lines(ps[i]) + sum((FEATURES[l] for l in range(below[-1]["access"] + 1, level + 1)), []))
    return "What's included:", plan_lines(ps[i]) + sum((FEATURES[l] for l in range(1, level + 1)), [])


def yearly_saving(ps):
    """'2 months free' style label for the yearly option."""
    months = [12 - x["yearly"] / x["monthly"] for x in ps if x.get("monthly") and x.get("yearly")]
    if not months or min(months) <= 0.4:
        return ""
    m = round(min(months))
    return f"{m} month{'s' if m != 1 else ''} free" if m >= 1 else ""


def price_for(plan, period):
    return plan.get("yearly") if period == "yearly" else plan.get("monthly")


def _money(x):
    return f"₦{float(x):,.0f}" if x not in (None, "") else "–"


# ------------------------------------------------------------------ data
def pricing(supabase):
    def fetch():
        try:
            rows = supabase.table("platform_settings").select("value").eq("key", "pricing").limit(1).execute().data
            return {**DEFAULT_PRICING, **(rows[0]["value"] if rows else {})}
        except Exception:
            return dict(DEFAULT_PRICING)
    return gw._cached(("billing_pricing",), fetch, ttl=300)


def billing_on(p):
    """False during pilot mode (Admin → Billing): nobody is locked or asked to pay."""
    return p.get("billing_on", True) is not False


def subscription(supabase, gym_id):
    """The gym's subscription row, or None when billing tables aren't set up or pilot mode is on
    (never lock then)."""
    if not billing_on(pricing(supabase)):
        return None

    def fetch():
        try:
            rows = supabase.table("gym_subscriptions").select("*").eq("gym_id", gym_id).limit(1).execute().data
            return rows[0] if rows else {}
        except Exception:
            return None
    return gw._cached(("billing_sub", gym_id), fetch, ttl=120)


def _d(value):
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except Exception:
        return None


def state(sub, today=None):
    """{"status", "days_left", "ends", "locked", "label"} for a subscription row."""
    today = today or gw.today_local()
    if sub is None:                                   # billing not set up: never lock
        return {"status": "off", "days_left": None, "ends": None, "locked": False, "label": ""}
    status = sub.get("status") or "trial"
    if status == "free":
        return {"status": "free", "days_left": None, "ends": None, "locked": False, "label": "Free access"}
    paid_until = _d(sub.get("paid_until"))
    if status == "active" and paid_until and paid_until >= today:
        return {"status": "active", "days_left": (paid_until - today).days, "ends": paid_until, "locked": False,
                "label": f"Subscribed until {paid_until:%d %b %Y}"}
    trial_end = _d(sub.get("trial_ends_on")) or (today + timedelta(days=TRIAL_DAYS))
    if status == "trial" and trial_end >= today:
        left = (trial_end - today).days
        return {"status": "trial", "days_left": left, "ends": trial_end, "locked": False,
                "label": f"Free trial: {left} day{'s' if left != 1 else ''} left"}
    ended = paid_until if status == "active" and paid_until else trial_end
    over = (today - ended).days
    return {"status": "expired", "days_left": -over, "ends": ended, "locked": over > GRACE_DAYS,
            "label": ("Your free trial has ended" if status == "trial" else "Your subscription has ended")}


def is_admin_account():
    try:
        import gympulse_admin as gadm
        return gadm.is_admin()
    except Exception:
        return False


# ------------------------------------------------------------------ in the app
def render_banner(supabase, gym_id):
    """No line at the top: owners are reminded by email. Shows the Upgrade pop-up once the trial is over."""
    s = state(subscription(supabase, gym_id))
    if s["locked"] and not is_admin_account() and not st.session_state.get("_upgrade_shown"):
        st.session_state["_upgrade_shown"] = True
        sub = subscription(supabase, gym_id) or {}
        (renew_dialog if sub.get("status") == "active" else upgrade_dialog)(pricing(supabase), s)
    return s


def _saving(plan):
    if plan.get("monthly") and plan.get("yearly"):
        saved = plan["monthly"] * 12 - plan["yearly"]
        return saved if saved > 0 else 0
    return 0


def compare_rows(ps):
    """[(benefit, [True/False per plan])], cheapest level first."""
    size = [("Members", [f"Up to {x['members']:,}" if x.get("members") else "Unlimited" for x in ps]),
            ("WhatsApp renewal reminders and replies / month", [f"{x['wa_renew']:,}" if x.get("wa_renew") else "–" for x in ps]),
            ("WhatsApp promotional messages / month", [f"{x['wa_promo']:,}" if x.get("wa_promo") else "By email" for x in ps]),
            ("Emails and member app", ["Unlimited" for _ in ps]),
            ("Extra charges", ["None" for _ in ps])]
    size.insert(3, ("Archie AI questions / month", [f"{x['archie']:,}" if x.get("archie") else "Unlimited" for x in ps]))
    size += [(svc, [_support_rank(x.get("support")) >= _support_rank(lv) for x in ps]) for svc, lv in SERVICE_LEVEL]
    return size + [(f, [x["access"] >= lv for x in ps]) for lv in (1, 2, 3) for f in FEATURES[lv]]


def _cell(ok, yes_html):
    if isinstance(ok, str):
        return gw._esc(ok)
    return yes_html if ok else ""


def compare_table_html(ps, light=False):
    """A plain table: one row per benefit, a tick under each plan that includes it."""
    line = "rgba(15,23,42,0.1)" if light else "rgba(255,255,255,0.08)"
    yes = "#4D7C0F" if light else "#B7F34A"
    head = "".join(f'<th style="padding:10px 8px;text-align:center;font-weight:700;white-space:nowrap">'
                   f'{gw._esc(x["name"])}</th>' for x in ps)
    rows = "".join(
        f'<tr style="border-top:1px solid {line}"><td style="padding:9px 8px;text-align:left">{gw._esc(f)}</td>'
        + "".join(f'<td style="padding:9px 8px;text-align:center;color:{yes};font-weight:800;white-space:nowrap">'
                  f'{_cell(ok, "✓")}</td>' for ok in marks) + "</tr>" for f, marks in compare_rows(ps))
    return (f'<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:13.5px">'
            f'<thead><tr><th style="padding:10px 8px;text-align:left;font-weight:600;opacity:.7">What you get</th>{head}'
            f'</tr></thead><tbody>{rows}</tbody></table></div>')


def _plan_cards(p, pay=None, key="pc"):
    """Plan tiles inside the app: monthly and yearly price side by side, then the comparison table."""
    ps = plans(p)
    cols = st.columns(len(ps) if len(ps) <= 3 else 3)
    for i, plan in enumerate(ps):
        with cols[i % len(cols)].container(border=True):
            title = gw._esc(plan["name"]) + ("  ·  :green[Recommended]" if plan.get("popular") else "")
            st.markdown(f"**{title}**")
            if plan.get("for_who"):
                st.caption(f"For gyms with {gw._esc(plan['for_who'][0].lower() + plan['for_who'][1:])}")
            if plan.get("monthly"):
                st.markdown(f"<span style='font-size:26px;font-weight:800'>{_money(plan['monthly'])}</span> "
                            f"<span style='opacity:.7'>per month</span>", unsafe_allow_html=True)
            if plan.get("yearly"):
                saved = _saving(plan)
                st.caption(f"Or {_money(plan['yearly'])} for the whole year"
                           + (f" (you keep {_money(saved)})" if saved else ""))
            gw._md("<div style='font-size:13px;line-height:1.7'>"
                   + "".join(f"<div>✓ {gw._esc(x)}</div>" for x in plan_lines(plan)[:3]) + "</div>")
            if pay:
                pay(plan, "monthly", i)
                pay(plan, "yearly", i)
    with st.expander("Compare what each plan includes", expanded=pay is not None):
        gw._md(compare_table_html(ps, light=st.session_state.get("theme") == "light"))


def _upgrade_body(p, s):
    st.markdown("Choose a plan to carry on. **Your members, check-ins and reports are all still here**, "
                "exactly as you left them.")
    _plan_cards(p, key="upg")
    if st.button("Choose a plan", type="primary", use_container_width=True, icon=":material/rocket_launch:"):
        st.session_state["navigate_to"] = "Subscription"
        st.rerun()


@st.dialog("Your free trial has ended", width="large")
def upgrade_dialog(p, s):
    _upgrade_body(p, s)


@st.dialog("Your plan has ended", width="large")
def renew_dialog(p, s):
    _upgrade_body(p, s)


# ------------------------------------------------------------------ plan levels
def access_level(sub, ps):
    """Which features a gym can use: 3 (everything) on trial or free access, the plan's level when paying."""
    s = state(sub)
    if s["status"] != "active":
        return 3
    name = gw._text((sub or {}).get("plan")).split(" · ")[0].strip().lower()
    hit = next((x for x in ps if x["name"].lower() == name), None)
    return hit["access"] if hit else 3


def plan_limits(supabase, gym_id):
    """What a gym's plan includes this month: {"wa_renew", "wa_promo", "archie", "members", "plan", "status"}.
    Paying gyms get their plan; trial, free access and pilot mode get TRIAL_ALLOWANCE (no member limit)."""
    p = pricing(supabase)
    ps = plans(p)
    sub = subscription(supabase, gym_id)
    s = state(sub)
    if s["status"] == "active":
        name = gw._text((sub or {}).get("plan")).split(" · ")[0].strip().lower()
        hit = next((x for x in ps if x["name"].lower() == name), None)
        if hit:
            return {"wa_renew": hit["wa_renew"], "wa_promo": hit["wa_promo"], "archie": hit["archie"],
                    "members": hit["members"], "plan": hit["name"], "status": "active"}
    if s["status"] == "expired":
        return {"wa_renew": 0, "wa_promo": 0, "archie": 0, "members": 0, "plan": "", "status": "expired"}
    t = {**TRIAL_ALLOWANCE, **dict(p.get("trial_allowance") or {})}
    return {"wa_renew": int(t["wa_renew"]), "wa_promo": int(t["wa_promo"]), "archie": int(t.get("archie") or 0),
            "members": 0, "plan": "Free trial" if s["status"] == "trial" else "Pilot", "status": s["status"]}


def wa_allowance(supabase, gym_id):
    return plan_limits(supabase, gym_id)


# ------------------------------------------------------------------ member limit (gentle)
def member_limit_status(supabase, gym_id, today=None):
    """None when the gym is within its plan; otherwise {"members", "limit", "plan", "since", "days_left",
    "blocked"}. A paying gym over its member limit has GRACE_OVER_LIMIT days to upgrade; after that it can't add
    new members (everything else keeps working). The first day over is kept in gym_subscriptions.over_limit_since."""
    today = today or gw.today_local()
    lim = plan_limits(supabase, gym_id)
    if lim["status"] != "active" or not lim["members"]:
        return None
    try:
        n = len(gw.fetch_members(supabase, gym_id, archived=False, include_photo=False)[0])
    except Exception:
        return None
    sub = subscription(supabase, gym_id) or {}
    since = _d(sub.get("over_limit_since"))
    if n <= lim["members"]:
        if since:
            _set_over_since(gym_id, None)
        return None
    if not since:
        since = today
        _set_over_since(gym_id, since)
    left = GRACE_OVER_LIMIT - (today - since).days
    return {"members": n, "limit": lim["members"], "plan": lim["plan"], "since": since,
            "days_left": max(0, left), "blocked": left <= 0}


def _set_over_since(gym_id, day):
    sc = _service()
    if sc is None:
        return
    try:
        sc.table("gym_subscriptions").update({"over_limit_since": day.isoformat() if day else None}) \
            .eq("gym_id", gym_id).execute()
        st.session_state.get("_cache", {}).pop(("billing_sub", gym_id), None)
    except Exception:
        pass                                          # phase 20 not run yet: reminder still shows


def billable_members(supabase, gym_id):
    """Members that count towards a plan: active members plus anyone archived in the last 30 days, so a gym
    can't archive most of its members, buy a smaller plan and bring them back."""
    try:
        n = supabase.rpc("gp_billable_members", {"p_gym": gym_id}).execute().data
        if isinstance(n, list):
            n = n[0] if n and not isinstance(n[0], dict) else (list(n[0].values())[0] if n else None)
        if n is not None:
            return int(n)
    except Exception:
        pass                                          # phase 38 not run yet
    try:
        return len(gw.fetch_members(supabase, gym_id, archived=False, include_photo=False)[0])
    except Exception:
        return 0


def plan_fits(plan, members):
    """A plan can be chosen only if it covers the gym's members (0 = no limit)."""
    return not plan.get("members") or int(members) <= int(plan["members"])


def member_room(supabase, gym_id, today=None):
    """How many more active members the gym can add now, or None when there's no limit (trial, free, pilot).
    Same rule as the database: up to the limit, plus 10% extra room for 30 days after first going over."""
    today = today or gw.today_local()
    lim = plan_limits(supabase, gym_id)
    if lim["status"] != "active" or not lim["members"]:
        return None
    try:
        n = len(gw.fetch_members(supabase, gym_id, archived=False, include_photo=False)[0])
    except Exception:
        return None
    since = _d((subscription(supabase, gym_id) or {}).get("over_limit_since"))
    in_grace = since is None or (today - since).days < GRACE_OVER_LIMIT
    ceiling = lim["members"] + (max(int(-(-lim["members"] * HEADROOM // 1)), 1) if in_grace else 0)
    return max(ceiling - n, 0)


def limit_message(error=None, plan=None, limit=None):
    """Plain words for the database's GP_MEMBER_LIMIT refusal."""
    m = re.search(r"up to (\d+) members", str(error or ""))
    limit = limit or (int(m.group(1)) if m else None)
    return ((f"Your {plan + ' ' if plan else ''}plan covers up to {limit:,} members. " if limit else
             "This would take you past your plan's member limit. ")
            + "Upgrade your plan in Subscription to add more members.")


def can_add_members(supabase, gym_id, adding=1):
    """(ok, message): whether `adding` new members fit the gym's plan right now."""
    if is_admin_account():
        return True, ""
    room = member_room(supabase, gym_id)
    if room is None or adding <= room:
        return True, ""
    lim = plan_limits(supabase, gym_id)
    if room <= 0:
        return False, (f"Your {lim['plan']} plan covers up to {lim['members']:,} members and you're at the limit. "
                       "Upgrade your plan to add new members. Everything else keeps working.")
    return False, (f"Your {lim['plan']} plan covers up to {lim['members']:,} members, so you can add "
                   f"{room:,} more right now, not {adding:,}. Upgrade your plan to add them all.")


def render_limit_banner(supabase, gym_id):
    """A friendly reminder at the top of the app when a paying gym has outgrown its plan."""
    m = member_limit_status(supabase, gym_id)
    if not m:
        return
    nxt = fits(plans(pricing(supabase)), m["members"])
    up = f" **{nxt['name']}** covers up to {nxt['members']:,} members." if nxt and nxt.get("members") else ""
    msg = (f"You have **{m['members']:,} members** and your **{m['plan']}** plan covers up to {m['limit']:,}.{up} ")
    if m["blocked"]:
        st.error(msg + "Upgrade to add new members. Everything else keeps working.", icon=":material/group_add:")
    else:
        st.warning(msg + f"Please upgrade within **{m['days_left']} day{'s' if m['days_left'] != 1 else ''}**; "
                         "after that, new members can't be added until you do.", icon=":material/trending_up:")
    if st.button("See plans", key="limit_plans", icon=":material/rocket_launch:"):
        st.session_state["navigate_to"] = "Subscription"
        st.rerun()


# ------------------------------------------------------------------ Archie questions
def _month():
    return f"{gw.today_local():%Y-%m}"


def archie_used(supabase, gym_id):
    try:
        rows = supabase.table("archie_usage").select("questions").eq("gym_id", gym_id).eq("month", _month()) \
            .limit(1).execute().data or []
        return int(rows[0]["questions"]) if rows else 0
    except Exception:
        return 0


def archie_allowed(supabase, gym_id):
    """(ok, used, limit, message). limit 0 = unlimited."""
    lim = plan_limits(supabase, gym_id)["archie"]
    if is_admin_account():
        return True, 0, 0, ""
    used = archie_used(supabase, gym_id)
    if plan_limits(supabase, gym_id)["status"] == "expired":
        return False, used, lim, "Archie is part of your GymPulse plan. Renew your plan to keep asking Archie."
    if lim and used >= lim:
        first = (gw.today_local().replace(day=1) + timedelta(days=32)).replace(day=1)
        return False, used, lim, (f"You've used all {lim:,} Archie questions in your plan this month. They reset on "
                                  f"{first:%d %B}. A bigger plan includes more questions.")
    return True, used, lim, ""


def archie_count(supabase, gym_id):
    try:
        supabase.rpc("gp_archie_bump", {"p_gym": gym_id, "p_month": _month()}).execute()
    except Exception:
        pass


def fits(ps, members):
    """The smallest plan whose member limit covers this many members."""
    for x in ps:
        if not x.get("members") or x["members"] >= members:
            return x
    return ps[-1] if ps else None


def page_allowed(supabase, gym_id, page):
    need = PAGE_LEVEL.get(page, 1)
    if need <= 1 or is_admin_account():
        return True
    return access_level(subscription(supabase, gym_id), plans(pricing(supabase))) >= need


def render_upsell(supabase, gym_id, page):
    """Shown instead of a page that the gym's plan doesn't include."""
    ps = plans(pricing(supabase))
    need = PAGE_LEVEL.get(page, 1)
    plan = next((x for x in ps if x["access"] >= need), None)
    gw.page_header(page, "Not included in your current plan.", "Upgrade")
    with st.container(border=True):
        st.markdown(f"#### {gw._esc(page)} is part of the {gw._esc(plan['name']) if plan else 'higher'} plan")
        st.markdown("Upgrade to unlock it. Everything else keeps working, and your data stays as it is.")
        st.markdown("  \n".join(f":green[✓] {gw._esc(f)}" for f in FEATURES[need]))
        if st.button("See plans and upgrade", type="primary", icon=":material/rocket_launch:", key="upsell_go"):
            st.session_state["navigate_to"] = "Subscription"
            st.rerun()


# ------------------------------------------------------------------ website
def public_pricing():
    """Prices for the signed-out website (read with the server key, kept 5 minutes)."""
    def fetch():
        try:
            sc = _service()
            rows = sc.table("platform_settings").select("value").eq("key", "pricing").limit(1).execute().data if sc else []
            return {**DEFAULT_PRICING, **(rows[0]["value"] if rows else {})}
        except Exception:
            return dict(DEFAULT_PRICING)
    return gw._cached(("public_pricing",), fetch, ttl=300)


def landing_cards_html(ps, icon):
    tiles = []
    for plan in ps:
        saved = _saving(plan)
        tiles.append(
            f'<div class="lx-tier{" rec" if plan.get("popular") else ""}">'
            + ('<span class="lx-tier-rec">Recommended</span>' if plan.get("popular") else "")
            + f'<div class="lx-tier-name">{gw._esc(plan["name"])}</div>'
            + (f'<div class="lx-tier-who">{gw._esc(plan["for_who"])}</div>' if plan.get("for_who") else "")
            + (f'<div class="lx-tier-line">{gw._esc(plan["tagline"])}</div>' if plan.get("tagline") else "")
            + '<div class="lx-tier-line" style="opacity:.9">' + "<br>".join(f"✓ {gw._esc(x)}" for x in plan_lines(plan)[1:3])
            + '</div>'
            + '<div class="lx-tier-prices">'
            + (f'<div><b>{_money(plan["monthly"])}</b><span>per month</span></div>' if plan.get("monthly") else "")
            + (f'<div><b>{_money(plan["yearly"])}</b><span>per year'
               + (f' · keep {_money(saved)}' if saved else "") + '</span></div>' if plan.get("yearly") else "")
            + "</div></div>")
    head = "".join(f"<th>{gw._esc(x['name'])}</th>" for x in ps)
    rows = "".join(f"<tr><td>{gw._esc(f)}</td>" + "".join(
        f"<td>{_cell(ok, icon('check', 16)) or '<i>–</i>'}</td>" for ok in marks) + "</tr>"
        for f, marks in compare_rows(ps))
    return (f'<div class="lx-tiers" style="--n:{min(len(ps), 3)}">' + "".join(tiles) + "</div>"
            + f'<div class="lx-compare"><table><thead><tr><th>What you get</th>{head}</tr></thead>'
              f'<tbody>{rows}</tbody></table></div>')


def render_landing_pricing(icon):
    p = public_pricing()
    ps = plans(p)
    gw._md("""<div class="lx-sec" id="pricing" style="padding-bottom:0">
      <div class="lx-kicker">Plans and prices</div>
      <div class="lx-h2">Your first 30 days are on us</div>
      <div class="lx-sub" style="margin-bottom:22px">Sign up and use every part of GymPulse AI free for a month,
        with no card. After that, choose the plan that fits your gym and pay month by month, or for the whole year
        and spend less.</div></div>""")
    gw._md(landing_cards_html(ps, icon)
           + '<div class="lx-demo-cta" style="margin-top:22px"><a class="lx-btn lx-btn-primary" href="#get-started">'
             'Start your free month</a></div>'
           + f'<div class="lx-plan-foot">All prices in naira. Card, bank transfer or USSD through Paystack. '
             f'{gw._esc(p.get("note") or "")}</div>')


def must_lock(supabase, gym_id):
    return state(subscription(supabase, gym_id))["locked"] and not is_admin_account()


# ------------------------------------------------------------------ members and public pages of a locked gym
def gym_locked(gym_id):
    """For member and public pages (member app, sign-up link, HMO check-in, machine guides, trainer pages):
    True when this gym's plan has ended. Uses the server key; never locks when billing isn't set up."""
    if not gym_id:
        return False
    import gympulse_admin as gadm
    sc = gadm.service_client()
    if sc is None:
        return False
    try:
        return bool(state(subscription(sc, gym_id))["locked"])
    except Exception:
        return False


def gym_by(table, column, value):
    """The gym id behind a public code or link (join code, guide id, trainer link), or None."""
    import gympulse_admin as gadm
    sc = gadm.service_client()
    if sc is None or not value:
        return None
    try:
        rows = sc.table(table).select("gym_id" if table != "gyms" else "id").eq(column, str(value)) \
            .limit(1).execute().data or []
    except Exception:
        return None
    return (rows[0].get("gym_id") or rows[0].get("id")) if rows else None


def render_gym_locked(gym_name=""):
    """What members and visitors see when their gym's GymPulse AI plan has ended."""
    who = gw._esc(gym_name) if gym_name else "your gym"
    gw._md(f'''<div class="mp-card" style="text-align:center;padding:28px 18px">
      <div style="font-size:40px">⏸️</div>
      <div class="bk-title" style="margin:8px 0 6px">Not available right now</div>
      <p>This service from {who} is paused. Please contact {who} (the front desk or the gym manager).</p>
    </div>''')


def locked_gyms(sc):
    """{gym_id} whose plan has ended, for the scheduled jobs (none when billing isn't set up)."""
    try:
        rows = sc.table("platform_settings").select("value").eq("key", "pricing").limit(1).execute().data
        p = {**DEFAULT_PRICING, **(rows[0]["value"] if rows else {})}
        if not billing_on(p):
            return set()
        subs = sc.table("gym_subscriptions").select("*").execute().data or []
    except Exception:
        return set()
    return {r["gym_id"] for r in subs if state(r)["locked"]}


def _email_founder(subject, text, reply_to=None, to=None):
    import gympulse_admin as gadm
    import requests
    key = gadm._env("RESEND_API_KEY")
    if not key:
        return False
    try:
        r = requests.post("https://api.resend.com/emails", timeout=20, headers={"Authorization": f"Bearer {key}"},
                          json={"from": gadm._env("REPORTS_FROM", gadm.REPORTS_FROM_DEFAULT),
                                "to": [to or "emmanuel@usegympulseai.com"], "reply_to": reply_to or None,
                                "subject": subject, "text": text})
        return r.status_code < 300
    except Exception:
        return False


# ------------------------------------------------------------------ Paystack
def paystack_key():
    import gympulse_admin as gadm
    return gadm._env("PAYSTACK_SECRET_KEY")


def _paystack(method, path, **kw):
    import requests
    r = requests.request(method, PAYSTACK_API + path, timeout=25,
                         headers={"Authorization": f"Bearer {paystack_key()}"}, **kw)
    try:
        return r.json()
    except Exception:
        return {"status": False, "message": f"Paystack error {r.status_code}"}


PAY_CHANNELS = {"pay_transfer": ["bank_transfer"], "pay_card": ["card", "ussd", "bank"]}


def start_payment(gym_id, plan, period, email, reference=None, invoice_id=None, channels=None):
    """Create a Paystack checkout. Returns (url, reference) or (None, error)."""
    import gympulse_email as ge
    amount = price_for(plan, period)
    if not (paystack_key() and amount and email):
        return None, "Online payment isn't set up yet."
    ref = reference or f"gp-{str(gym_id)[:8]}-{uuid.uuid4().hex[:12]}"
    r = _paystack("POST", "/transaction/initialize", json={
        "email": email, "amount": int(round(amount * 100)), "currency": "NGN", "reference": ref,
        "callback_url": f"{ge.SITE}/?paystack=1", **({"channels": channels} if channels else {}),
        "metadata": {"source": "gympulse", "gym_id": str(gym_id), "plan": plan["name"], "period": period,
                     "invoice_id": invoice_id, "cancel_action": f"{ge.SITE}/"}})
    if r.get("status") and (r.get("data") or {}).get("authorization_url"):
        return r["data"]["authorization_url"], ref
    return None, r.get("message") or "Couldn't start the payment. Please try again."


def _service():
    import gympulse_admin as gadm
    return gadm.service_client()


def owner_email(sc, gym_id):
    try:
        g = sc.table("gyms").select("owner_id").eq("id", gym_id).limit(1).execute().data
        user = getattr(sc.auth.admin.get_user_by_id(g[0]["owner_id"]), "user", None) if g else None
        return getattr(user, "email", "") or ""
    except Exception:
        return ""


def activate(sc, gym_id, plan_name, period, months, amount, note):
    """Switch a plan on after a confirmed payment. A renewal continues after the current
    paid period, and paying during the free trial keeps the rest of the trial.
    Returns (first day, last day)."""
    today = gw.today_local()
    sub = (sc.table("gym_subscriptions").select("*").eq("gym_id", gym_id).limit(1).execute().data or [{}])[0]
    base = today
    if sub.get("status") == "active" and _d(sub.get("paid_until")):
        base = max(base, _d(sub.get("paid_until")))
    elif sub.get("status") == "trial" and _d(sub.get("trial_ends_on")):
        base = max(base, _d(sub.get("trial_ends_on")))
    start = base if base == today else base + timedelta(days=1)
    until = base + timedelta(days=365 if period == "yearly" else 30 * int(months or 1))
    label = "Yearly" if period == "yearly" else ("Monthly" if int(months or 1) == 1 else f"{months} months")
    row = {"gym_id": gym_id, "status": "active", "paid_until": until.isoformat(), "plan": f"{plan_name} · {label}",
           "price": round(float(amount) / (12 if period == "yearly" else int(months or 1)), 2), "note": note,
           "updated_at": datetime.now(timezone.utc).isoformat()}
    row.update(_limit_fields(sc, gym_id, plan_name))
    try:
        sc.table("gym_subscriptions").upsert(row, on_conflict="gym_id").execute()
    except Exception:                                  # phase 38 not run yet
        sc.table("gym_subscriptions").upsert({k: v for k, v in row.items() if k != "member_limit"},
                                             on_conflict="gym_id").execute()
    try:
        st.session_state.pop("_cache", None)
    except Exception:
        pass
    return start, until


def _limit_fields(sc, gym_id, plan_name):
    """member_limit for the database, and when the gym already has more members than the plan covers (e.g. a
    payment that went through for a plan that's too small), no 30 days of grace: adding is blocked at once."""
    try:
        rows = sc.table("platform_settings").select("value").eq("key", "pricing").limit(1).execute().data
        p = {**DEFAULT_PRICING, **(rows[0]["value"] if rows else {})}
    except Exception:
        p = dict(DEFAULT_PRICING)
    plan = next((x for x in plans(p) if x["name"].lower() == gw._text(plan_name).split(" · ")[0].strip().lower()), None)
    if not plan or not plan.get("members"):
        return {"member_limit": None}
    out = {"member_limit": int(plan["members"])}
    n = billable_members(sc, gym_id)
    if n > plan["members"]:
        out["over_limit_since"] = (gw.today_local() - timedelta(days=GRACE_OVER_LIMIT)).isoformat()
        _email_founder(f"Plan too small for gym {gym_id}",
                       f"Gym {gym_id} paid for {plan['name']} (up to {plan['members']:,} members) but has {n:,} "
                       "members. Adding members is blocked until they upgrade. Check it in Admin → Billing.")
    return out


def apply_payment(reference, sc=None):
    """Check a payment with Paystack, switch the gym's plan on, mark the invoice paid and email
    the receipt. Safe to call many times. Returns (ok, message, invoice or None).

    The amount must match the plan's current price, and each payment is used once
    (billing_events ref paystack:<reference>)."""
    import gympulse_invoices as gi
    sc = sc or _service()
    if not (sc and paystack_key() and reference):
        return False, "We couldn't check the payment right now. If you paid, it will show within a day.", None
    r = _paystack("GET", f"/transaction/verify/{quote(str(reference), safe='')}")
    d = r.get("data") or {}
    if not r.get("status") or d.get("status") != "success":
        return False, "That payment hasn't gone through yet. If money left your account, it will show here shortly.", None
    md = d.get("metadata") or {}
    if isinstance(md, str):
        try:
            md = json.loads(md)
        except Exception:
            md = {}
    gid, period = md.get("gym_id"), "yearly" if md.get("period") == "yearly" else "monthly"
    if md.get("source") != "gympulse" or not gid:
        return False, "That payment isn't for a GymPulse AI plan.", None
    rows = sc.table("platform_settings").select("value").eq("key", "pricing").limit(1).execute().data
    p = {**DEFAULT_PRICING, **(rows[0]["value"] if rows else {})}
    plan = next((x for x in plans(p) if x["name"] == md.get("plan")), None)
    paid = (d.get("amount") or 0) / 100
    expected = price_for(plan, period) if plan else None
    inv = gi.by_reference(sc, reference)
    if d.get("currency") != "NGN" or not expected or paid + 0.5 < expected:
        _email_founder(f"Paystack payment to check: {reference}",
                       f"A payment of ₦{paid:,.0f} ({md.get('plan')}, {period}) for gym {gid} didn't match the "
                       f"current price ({_money(expected)}). Check it in Paystack, then use Mark as paid in Admin.")
        return False, "We've received your payment and the team will confirm it shortly.", inv
    try:
        sc.table("billing_events").insert({"gym_id": gid, "kind": "paystack", "ref": f"paystack:{reference}"}).execute()
    except Exception:
        return True, "Payment received. Your plan is active.", inv          # already applied
    try:
        start, until = activate(sc, gid, plan["name"], period, 12 if period == "yearly" else 1, paid,
                                f"Paystack {reference}")
    except Exception:
        sc.table("billing_events").delete().eq("gym_id", gid).eq("ref", f"paystack:{reference}").execute()
        raise
    email = (d.get("customer") or {}).get("email", "")
    if not inv:
        inv = gi.create(sc, gid, plan["name"], period, paid, {"billing_email": email}, "paystack", reference)
    inv = gi.update(sc, inv, status="paid", paid_at=datetime.now(timezone.utc).isoformat(), amount=paid,
                    period_start=start.isoformat(), period_end=until.isoformat())
    auth = d.get("authorization") or {}
    channel = d.get("channel") or auth.get("channel") or ""
    if channel == "card" and auth.get("last4"):
        inv["pay_detail"] = f"{gw._text(auth.get('card_type'), 'Card').strip().title()} ending {auth['last4']}"
    elif channel in ("bank_transfer", "dedicated_nuban"):
        inv["pay_detail"] = "Bank transfer" + (f" · {auth['bank']}" if auth.get("bank") else "")
    elif channel:
        inv["pay_detail"] = channel.replace("_", " ").capitalize()
    gi.send_receipt(sc, inv, extra_to=owner_email(sc, gid))         # a copy also goes to GymPulse AI
    return True, f"Your {plan['name']} plan is active until {until:%d %B %Y}.", inv


def confirm_transfer(sc, inv, confirmed_by="admin"):
    """The founder confirmed a bank transfer: switch the plan on, mark the invoice paid, send the receipt."""
    import gympulse_invoices as gi
    start, until = activate(sc, inv["gym_id"], inv["plan"], inv["period"], inv.get("months") or 1, inv["amount"],
                            f"Transfer {gi.number(inv)} confirmed by {confirmed_by}")
    inv = gi.update(sc, inv, status="paid", paid_at=datetime.now(timezone.utc).isoformat(),
                    period_start=start.isoformat(), period_end=until.isoformat())
    gi.send_receipt(sc, inv, extra_to=owner_email(sc, inv["gym_id"]))
    return inv, until


def reconcile_paystack(sc, days=3, log=print):
    """Apply any successful Paystack payments from the last few days that weren't applied yet."""
    if not paystack_key():
        log("PAYSTACK_SECRET_KEY not set: skipped")
        return 0
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00Z")
    r = _paystack("GET", "/transaction", params={"status": "success", "from": since, "perPage": 100})
    done = {x["ref"] for x in sc.table("billing_events").select("ref").eq("kind", "paystack").execute().data or []}
    n = 0
    for t in r.get("data") or []:
        md = t.get("metadata") or {}
        if isinstance(md, str):
            try:
                md = json.loads(md)
            except Exception:
                md = {}
        if md.get("source") != "gympulse" or f"paystack:{t.get('reference')}" in done:
            continue
        ok, msg, _ = apply_payment(t.get("reference"), sc)
        log(f"  {t.get('reference')}: {msg}")
        n += ok
    return n


# ------------------------------------------------------------------ the page Paystack returns to
def render_return_page(params):
    """?paystack=1&reference=...: a public confirmation page (works even if the owner isn't signed in)."""
    import gympulse_booking as gb
    import gympulse_invoices as gi
    gb._header()
    ref = params.get("reference") or params.get("trxref")
    key = f"_pay_return_{ref}"
    if key not in st.session_state:
        try:
            st.session_state[key] = apply_payment(ref)
        except Exception as error:
            st.session_state[key] = (False, "We couldn't confirm the payment just now. If you paid, your plan will "
                                            "switch on within a day and your receipt will be emailed.", None)
            try:
                import gympulse_monitoring as gmon
                gmon.capture(error, "paystack return")
            except Exception:
                pass
        st.session_state.pop("_cache", None)
        st.session_state.pop("_upgrade_shown", None)
    ok, msg, inv = st.session_state[key]
    col = gw.center("billing", 640)
    with col:
        if ok:
            rows = "".join(f'<div class="co-row"><span>{a}</span><b>{gw._esc(b)}</b></div>' for a, b in [
                ("Receipt", gi.number(inv) if inv else "–"),
                ("Plan", f"{(inv or {}).get('plan', '')} · {'Yearly' if (inv or {}).get('period') == 'yearly' else 'Monthly'}"
                 if inv else "–"),
                ("Amount paid", gi.money((inv or {}).get("amount"))),
                ("Receipt sent to", (inv or {}).get("billing_email") or "your email")])
            gw._md(f'''<div class="co-done"><div class="co-tick">✓</div>
                <div class="co-title">Payment successful</div>
                <div class="co-sub">Thank you. {gw._esc(msg)} A receipt is on its way to your inbox.</div>
                <div class="co-card">{rows}</div></div>''')
            if inv:
                import gympulse_reports as rp
                rp.download_link("Download receipt (PDF)", gi.receipt_pdf(inv),
                                 f"GymPulse-AI-receipt-{gi.number(inv)}.pdf", rp.PDF, "co_rcpt")
        else:
            gw._md(f'''<div class="co-done"><div class="co-tick co-wait">…</div>
                <div class="co-title">We're confirming your payment</div>
                <div class="co-sub">{gw._esc(msg)}</div></div>''')
        gw._md('<div style="text-align:center;margin-top:18px"><a class="lx-btn lx-btn-primary" href="/" '
               'target="_self">Continue to GymPulse AI</a></div>')


# ------------------------------------------------------------------ subscription page
CO_CSS = """
.co-head { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; }
.co-plan { border:1px solid var(--gp-line); border-radius:20px; padding:22px; background:var(--gp-s1); }
.co-status { display:flex; gap:28px; flex-wrap:wrap; border:1px solid var(--gp-line); border-radius:20px;
    padding:20px 24px; background:var(--gp-s1); margin:4px 0 22px; }
.co-status div span { display:block; font-size:11px; letter-spacing:1px; text-transform:uppercase; color:var(--gp-muted);
    font-weight:700; }
.co-status div b { display:block; font-size:20px; margin-top:4px; color:var(--gp-text); }
.co-sum { border:1px solid var(--gp-line); border-radius:20px; padding:24px; background:var(--gp-s1); position:sticky; top:12px; }
.co-sum h4 { margin:0 0 2px; font-size:13px; letter-spacing:1px; text-transform:uppercase; color:var(--gp-muted); }
.co-sum .co-name { font-size:24px; font-weight:800; color:var(--gp-text); margin:6px 0 2px; }
.co-sum .co-tag { color:var(--gp-muted); font-size:13.5px; margin-bottom:16px; }
.co-row { display:flex; justify-content:space-between; gap:12px; padding:10px 0; border-top:1px solid var(--gp-line);
    font-size:14px; color:var(--gp-muted); }
.co-row b { color:var(--gp-text); font-weight:600; text-align:right; }
.co-total { display:flex; justify-content:space-between; align-items:baseline; padding:14px 0 4px;
    border-top:1px solid var(--gp-line-2); margin-top:4px; }
.co-total span { font-weight:700; color:var(--gp-text); }
.co-total b { font-size:28px; font-weight:800; color:var(--gp-text); letter-spacing:-.5px; }
.co-note { color:var(--gp-muted); font-size:12.5px; line-height:1.6; margin-top:12px; }
.co-feat { margin-top:14px; padding-top:12px; border-top:1px solid var(--gp-line); font-size:13px; color:var(--gp-muted); }
.co-feat div { padding:3px 0; } .co-feat div::before { content:"✓  "; color:var(--gp-lime); font-weight:800; }
.co-sec { font-size:12px; font-weight:800; letter-spacing:1.4px; text-transform:uppercase; color:var(--gp-muted);
    margin:6px 0 2px; }
.co-done { text-align:center; padding:26px 0 6px; }
.co-tick { width:64px; height:64px; border-radius:50%; margin:0 auto 14px; display:grid; place-items:center; font-size:30px;
    font-weight:800; color:#0A0F1E; background:var(--gp-grad); }
.co-tick.co-wait { background:var(--gp-s3); color:var(--gp-text); }
.co-title { font-size:28px; font-weight:800; color:var(--gp-text); letter-spacing:-.6px; }
.co-sub { color:var(--gp-muted); font-size:14.5px; line-height:1.6; margin:8px auto 18px; max-width:520px; }
.co-card { text-align:left; border:1px solid var(--gp-line); border-radius:16px; padding:6px 18px; background:var(--gp-s1); }
.co-card .co-row:first-child { border-top:0; }
.co-bank { border:1px solid var(--gp-line); border-radius:20px; padding:8px 22px; background:var(--gp-s1); }
.co-bank .co-row b { font-size:16px; }
.co-pay { display:flex; flex-direction:column; align-items:stretch; gap:10px; margin-top:14px; }
.co-pay a { text-align:center; }
.co-lock { color:var(--gp-muted); font-size:12.5px; text-align:center; }
"""


def _summary_html(plan, period, sub_state, ps):
    import gympulse_invoices as gi
    amount = price_for(plan, period)
    today = gw.today_local()
    if sub_state["status"] == "trial" and sub_state.get("ends"):
        starts = sub_state["ends"] + timedelta(days=1)
        start_note = f"Your free trial continues until {sub_state['ends']:%d %B}. Your paid plan starts {starts:%d %B %Y}."
    elif sub_state["status"] == "active" and sub_state.get("ends"):
        starts = sub_state["ends"] + timedelta(days=1)
        start_note = f"This adds to your current plan, which runs until {sub_state['ends']:%d %B %Y}."
    else:
        starts = today
        start_note = "Your plan starts as soon as your payment is confirmed."
    renews = starts + timedelta(days=365 if period == "yearly" else 30)
    i = next((n for n, x in enumerate(ps) if x["name"] == plan["name"]), 0)
    _, items = features(ps, i)
    saved = _saving(plan) if period == "yearly" else 0
    rows = [("Plan", plan["name"]), ("Billing", "Yearly" if period == "yearly" else "Monthly"),
            ("Starts", f"{starts:%d %b %Y}"), ("Renews", f"{renews:%d %b %Y}")]
    if saved:
        rows.append(("You save", gi.money(saved)))
    return (f'<div class="co-sum"><h4>Order summary</h4><div class="co-name">GymPulse AI {gw._esc(plan["name"])}</div>'
            f'<div class="co-tag">{gw._esc(plan.get("tagline") or plan.get("for_who") or "")}</div>'
            + "".join(f'<div class="co-row"><span>{a}</span><b>{gw._esc(b)}</b></div>' for a, b in rows)
            + f'<div class="co-row"><span>VAT</span><b>₦0</b></div>'
            + f'<div class="co-total"><span>Total</span><b>{gi.money(amount)}</b></div>'
            + f'<div class="co-note">{gw._esc(start_note)} Cancel any time: your plan simply won\'t renew.</div>'
            + '<div class="co-feat">' + "".join(f"<div>{gw._esc(f)}</div>" for f in items[:5]) + "</div></div>")


def _notify_transfer(inv):
    import gympulse_invoices as gi
    ok = _email_founder(f"Transfer to confirm: {gi.number(inv)} · {gi.money(inv.get('amount'))}",
                        f"{inv.get('business_name')} ({inv.get('billing_name')}, {inv.get('billing_email')}, "
                        f"{inv.get('billing_phone')}) says they've sent a bank transfer.\n\n"
                        f"Invoice: {gi.number(inv)}\nPlan: {inv.get('plan')} ({inv.get('period')})\n"
                        f"Amount: {gi.money(inv.get('amount'))}\n\nNothing is switched on yet. When the money is in your "
                        "account, confirm it in Admin → Billing → Bank transfers to confirm: the plan switches on and "
                        "the receipt is emailed to the gym and to you automatically.",
                        reply_to=inv.get("billing_email"))
    return ok


def _view(v, **kw):
    st.session_state["sub_view"] = v
    for k, val in kw.items():
        st.session_state[k] = val


def render_subscription_page(supabase, gym_id):
    import gympulse_invoices as gi
    gw._md(f"<style>{CO_CSS}</style>")
    view = st.session_state.get("sub_view", "plans")
    s = state(subscription(supabase, gym_id))
    p = pricing(supabase)
    ps = plans(p)
    if s["status"] == "off":
        gw.page_header("Subscription", "Your GymPulse AI plan.", "Account")
        st.success("You're part of the GymPulse AI pilot: every feature is free for now. We'll let you know well "
                   "before anything changes.")
        return
    if view in ("checkout", "pay", "transfer", "sent") and st.session_state.get("sub_plan") in [x["name"] for x in ps]:
        plan = next(x for x in ps if x["name"] == st.session_state["sub_plan"])
        period = st.session_state.get("sub_period", "monthly")
        if view == "checkout":
            return _render_checkout(supabase, gym_id, plan, period, s, p, ps)
        if view == "pay":
            return _render_pay(plan, period, s, ps)
        return _render_transfer(supabase, gym_id, plan, period, s, p, ps)
    _render_plans(supabase, gym_id, s, p, ps)


def _render_plans(supabase, gym_id, s, p, ps):
    import gympulse_invoices as gi
    gw.page_header("Subscription", "Your plan, payments and receipts.", "Account")
    flash = st.session_state.pop("bill_flash", None)
    if flash:
        (st.success if st.session_state.pop("bill_flash_ok", True) else st.warning)(flash)
    sub = subscription(supabase, gym_id) or {}
    if s["locked"]:
        st.error(("Your free trial has ended." if sub.get("status") != "active" else "Your plan has ended.")
                 + " Choose a plan to keep using GymPulse AI. Everything you added is safe, and you'll pick up "
                   "right where you left off.")
    status = {"trial": "Free trial", "active": "Active", "free": "Free access", "expired": "Ended"}[s["status"]]
    tone = {"trial": "cyan", "active": "lime", "free": "cyan", "expired": "red"}[s["status"]]
    plan_name = gw._text(sub.get("plan"), "Free trial" if s["status"] == "trial" else "–")
    ends_label = {"trial": "Trial ends", "active": "Renews", "expired": "Ended", "free": "Ends"}[s["status"]]
    gw._md(f'''<div class="co-status">
        <div><span>Current plan</span><b>{gw._esc(plan_name)}</b></div>
        <div><span>Status</span><b><span class="gp-pill gp-pill-{tone}" style="font-size:13px">{status}</span></b></div>
        <div><span>{ends_label}</span><b>{f"{s['ends']:%d %b %Y}" if s.get("ends") else "–"}</b></div>
        </div>''')
    if s["status"] == "free":
        st.success("Your gym has free access to GymPulse AI. Nothing to pay.")
    else:
        st.markdown('<div class="section-label">CHOOSE A PLAN</div>', unsafe_allow_html=True)
        n_members = billable_members(supabase, gym_id)
        best = fits(ps, n_members) if n_members else None
        if best:
            st.caption(f"You have **{n_members:,} members**, so **{best['name']}** fits your gym. Every plan includes "
                       "WhatsApp messages: no extra charges, ever.")
        cols = st.columns(len(ps) if len(ps) <= 3 else 3)
        for i, plan in enumerate(ps):
            with cols[i % len(cols)].container(border=True):
                if best and plan["name"] == best["name"]:
                    gw._md('<span class="gp-pill gp-pill-lime">Fits your gym</span>')
                elif plan.get("popular") and not best:
                    gw._md('<span class="gp-pill gp-pill-lime">Recommended</span>')
                else:
                    gw._md('<span class="gp-pill" style="visibility:hidden">Recommended</span>')
                st.markdown(f"### {gw._esc(plan['name'])}")
                if plan.get("for_who"):
                    st.caption(f"For gyms with {gw._esc(plan['for_who'][0].lower() + plan['for_who'][1:])}")
                if plan.get("monthly"):
                    gw._md(f"<div style='font-size:30px;font-weight:800;letter-spacing:-.6px'>{_money(plan['monthly'])}"
                           f"<span style='font-size:14px;font-weight:500;opacity:.7'> / month</span></div>")
                if plan.get("yearly"):
                    saved = _saving(plan)
                    st.caption(f"or {_money(plan['yearly'])} a year" + (f", save {_money(saved)}" if saved else ""))
                if plan.get("tagline"):
                    st.markdown(f"<div style='font-size:13.5px;opacity:.8;min-height:40px'>{gw._esc(plan['tagline'])}</div>",
                                unsafe_allow_html=True)
                gw._md("<div style='font-size:13px;line-height:1.7;margin:4px 0 10px'>"
                       + "".join(f"<div>✓ {gw._esc(x)}</div>" for x in plan_lines(plan)) + "</div>")
                small = not plan_fits(plan, n_members)
                st.button(f"Choose {plan['name']}", key=f"co_choose_{i}", use_container_width=True, disabled=small,
                          type="primary" if (best and plan["name"] == best["name"]) or (not best and plan.get("popular"))
                          else "secondary",
                          on_click=_view, args=("checkout",), kwargs={"sub_plan": plan["name"], "sub_period": "monthly"})
                if small:
                    st.caption(f"Too small for your {n_members:,} members")
        with st.expander("Compare what each plan includes"):
            gw._md(compare_table_html(ps, light=st.session_state.get("theme") == "light"))
        if p.get("note"):
            st.caption(p["note"])

    invoices = gi.for_gym(supabase, gym_id)
    st.markdown('<div class="section-label">BILLING HISTORY</div>', unsafe_allow_html=True)
    if invoices is None:
        st.caption("Receipts appear here once billing history is switched on.")
    else:
        shown = [x for x in invoices if x.get("status") != "cancelled"]
        gw.table([{"Receipt": gi.number(x), "Date": str(x.get("paid_at") or x.get("created_at"))[:10],
                   "Plan": f"{x.get('plan')} · {'Yearly' if x.get('period') == 'yearly' else 'Monthly'}",
                   "Amount": gi.money(x.get("amount")),
                   "Status": {"paid": "Paid", "pending": "Awaiting payment"}.get(x.get("status"), x.get("status"))}
                  for x in shown], pills={"Status": {"Paid": "lime", "Awaiting payment": "amber"}},
                 empty="No payments yet. Your receipts will appear here.")
        paid = [x for x in shown if x.get("status") == "paid"]
        if paid:
            import gympulse_reports as rp
            pick = st.selectbox("Download a receipt", range(len(paid)), key="co_rc_pick",
                                format_func=lambda j: f"{gi.number(paid[j])} · {gi.money(paid[j].get('amount'))}")
            rp.download_link("Download receipt (PDF)", gi.receipt_pdf(paid[pick]),
                             f"GymPulse-AI-receipt-{gi.number(paid[pick])}.pdf", rp.PDF, f"co_rc_{pick}")
    contact = [x for x in (p.get("contact_whatsapp") and f"WhatsApp {p['contact_whatsapp']}", p.get("contact_email")) if x]
    if contact:
        st.caption("Questions about billing? " + " · ".join(contact))


def _render_checkout(supabase, gym_id, plan, period, s, p, ps):
    import gympulse_invoices as gi
    st.button("Back to plans", icon=":material/arrow_back:", type="tertiary", key="co_back",
              on_click=_view, args=("plans",))
    gw.page_header("Checkout", f"GymPulse AI {plan['name']}. Secure payment, receipt by email.", "Subscription")
    n_members = billable_members(supabase, gym_id)
    if not plan_fits(plan, n_members):
        best = fits(ps, n_members)
        st.error(f"The {plan['name']} plan covers up to {plan['members']:,} members and your gym has "
                 f"{n_members:,} (members archived in the last 30 days count too)."
                 + (f" **{best['name']}** fits your gym." if best and plan_fits(best, n_members) else ""))
        return
    flash = st.session_state.pop("bill_flash", None)
    if flash:
        st.warning(flash)
    options = [x for x in ("monthly", "yearly") if price_for(plan, x)]
    if len(options) > 1:
        saved = _saving(plan)
        pick = st.segmented_control("Billing", options, default=period, key="co_cycle", label_visibility="collapsed",
                                    format_func=lambda v: f"Monthly · {_money(plan['monthly'])}" if v == "monthly"
                                    else f"Yearly · {_money(plan['yearly'])}" + (f" (save {_money(saved)})" if saved else ""))
        if pick and pick != period:
            st.session_state["sub_period"] = pick
            st.rerun()
    online, bank = bool(paystack_key()), bool(p.get("bank_account"))
    left, right = st.columns([1.35, 1], gap="large")
    with right:
        gw._md(_summary_html(plan, period, s, ps))
    with left:
        prof = st.session_state.get("user_profile") or {}
        prev = st.session_state.get("co_details") or gi.last_details(supabase, gym_id)
        email0 = (st.session_state.get("auth_user") or {}).get("email", "")
        if not (online or bank):
            st.info("Online payment is being set up. Contact us and we'll activate your plan: "
                    + (p.get("contact_email") or "emmanuel@usegympulseai.com"))
            return
        import gympulse_legal as glegal
        signed_before = glegal.latest_signature(supabase, gym_id, prof)
        if signed_before:
            when = pd.to_datetime(signed_before.get("signed_at"), errors="coerce", utc=True)
            st.success(f"Subscription Agreement signed by {signed_before.get('signer_name')}"
                       + ("" if pd.isna(when) else f" on {when.tz_convert(gw.APP_TZ):%d %B %Y}")
                       + ". You don't need to sign again. You can cancel at any time.",
                       icon=":material/verified:")
        if st.button("Read the Subscription Agreement", key="co_read_sa", icon=":material/contract:",
                     type="tertiary"):
            glegal.show_subscription()
        with st.form("co_form", border=False):
            gw._md('<div class="co-sec">Billing details</div>')
            biz = st.text_input("Business name", prev.get("business_name") or prof.get("business_name") or "")
            c1, c2 = st.columns(2)
            name = c1.text_input("Full name", prev.get("billing_name") or prof.get("full_name") or "")
            phone = c2.text_input("Phone number", prev.get("billing_phone") or "", placeholder="e.g. 0803 000 0000")
            email = st.text_input("Email for receipts", prev.get("billing_email") or email0)
            gw._md('<div class="co-sec" style="margin-top:10px">Billing address</div>')
            addr = st.text_input("Street address", prev.get("address") or "", placeholder="e.g. 12 Admiralty Way")
            c3, c4 = st.columns(2)
            city = c3.text_input("City", prev.get("city") or "", placeholder="e.g. Lekki")
            states = gi.NG_STATES
            state_ = c4.selectbox("State", states, index=states.index(prev["state"]) if prev.get("state") in states
                                  else states.index("Lagos"))
            gw._md('<div class="co-sec" style="margin-top:10px">Payment method</div>')
            methods = ["pay_transfer", "pay_card"] if online else (["transfer"] if bank else [])
            method = st.radio("Payment method", methods, label_visibility="collapsed", format_func=lambda m: {
                "pay_transfer": "Bank transfer · confirmed instantly, your plan switches on straight away",
                "pay_card": "Card or USSD · secured by Paystack",
                "transfer": "Bank transfer · your plan switches on when the money arrives"}[m])
            if signed_before:
                signed, role = signed_before.get("signer_name"), signed_before.get("signer_role")
                agree = st.checkbox("I authorise this payment.")
            else:
                gw._md('<div class="co-sec" style="margin-top:10px">Sign the agreement (once)</div>')
                st.caption("Before your first payment, please sign the GymPulse AI Subscription Agreement (link "
                           "above). It's month to month, you can cancel at any time, and it's already signed by "
                           "GymPulse AI. You only sign once.")
                s1, s2 = st.columns([1.4, 1])
                signed = s1.text_input("Type your full name to sign", placeholder="Same as your full name above")
                role = s2.selectbox("Your role", glegal.SIGNER_ROLES)
                agree = st.checkbox(f"I have read and agree to the Subscription Agreement (version "
                                    f"{glegal.SUBSCRIPTION_VERSION}), the Terms of Service, Privacy Policy and Data "
                                    "Processing Agreement. I am authorised to sign for this business, and I "
                                    "authorise this payment.")
            go = st.form_submit_button(f"Continue · {_money(price_for(plan, period))}", type="primary",
                                       use_container_width=True)
        if go:
            details = {"business_name": biz, "billing_name": name, "billing_phone": phone, "billing_email": email,
                       "address": addr, "city": city, "state": state_}
            st.session_state["co_details"] = details
            problems = [m for ok, m in [(biz.strip(), "your business name"), (name.strip(), "your full name"),
                                        ("@" in email and "." in email.split("@")[-1], "a valid email"),
                                        (len("".join(ch for ch in phone if ch.isdigit())) >= 10, "a phone number"),
                                        (signed_before or _same_name(signed, name),
                                         "your signature (type your full name exactly as above)"),
                                        (agree, "to accept the agreement")] if not ok]
            if problems:
                st.error("Please add " + ", ".join(problems) + ".")
                return
            sc = _service()
            if not sc:
                st.error("Checkout isn't available right now. Please try again shortly.")
                return
            amount = price_for(plan, period)
            signature = {"signer_name": " ".join(signed.split()), "signer_role": role, "plan": plan["name"],
                         "period": period, "amount": amount}
            if method in PAY_CHANNELS:
                ref = f"gp-{str(gym_id)[:8]}-{uuid.uuid4().hex[:12]}"
                inv = gi.create(sc, gym_id, plan["name"], period, amount, details, "paystack", ref)
                if not signed_before:
                    record_signature(sc, gym_id, details, {**signature, "invoice_id": inv.get("id")})
                url, msg = start_payment(gym_id, plan, period, email.strip(), ref, inv.get("id"),
                                         PAY_CHANNELS[method])
                st.session_state["co_channel"] = method
                if not url:
                    gi.update(sc, inv, status="cancelled")
                    st.session_state["bill_flash"] = msg
                    st.rerun()
                _view("pay", co_url=url, co_inv=inv)
            else:
                inv = gi.create(sc, gym_id, plan["name"], period, amount, details, "transfer")
                if not signed_before:
                    record_signature(sc, gym_id, details, {**signature, "invoice_id": inv.get("id")})
                if inv.get("number"):
                    inv = gi.update(sc, inv, reference=gi.number(inv))
                _view("transfer", co_inv=inv)
            st.rerun()


def _same_name(signed, name):
    norm = lambda x: " ".join(gw._text(x).lower().split())
    return bool(norm(signed)) and norm(signed) == norm(name)


def record_signature(sc, gym_id, details, sig):
    """Keep the signed Subscription Agreement (who, for which business, when, from where, which exact text)
    and email a signed copy to the gym and to GymPulse AI. Never blocks the payment."""
    import gympulse_legal as glegal
    text = glegal.subscription_text()
    now = datetime.now(timezone.utc)
    try:
        ip = st.context.ip_address
        agent = (st.context.headers or {}).get("User-Agent")
    except Exception:
        ip = agent = None
    row = {"gym_id": gym_id, "document": "subscription", "version": glegal.SUBSCRIPTION_VERSION,
           "text_sha256": glegal.fingerprint(text), "business_name": details.get("business_name"),
           "signer_name": sig["signer_name"], "signer_role": sig.get("signer_role"),
           "signer_email": details.get("billing_email"), "signed_at": now.isoformat(), "ip": ip,
           "user_agent": (agent or "")[:300] or None, "plan": sig.get("plan"), "period": sig.get("period"),
           "amount": sig.get("amount"), "invoice_id": sig.get("invoice_id")}
    try:
        sc.table("agreement_signatures").insert(row).execute()
    except Exception:                                  # phase 40 not run yet: keep it on the owner's profile
        try:
            g = sc.table("gyms").select("owner_id").eq("id", gym_id).limit(1).execute().data
            prof = sc.table("profiles").select("settings").eq("id", g[0]["owner_id"]).limit(1).execute().data
            settings = dict((prof[0] if prof else {}).get("settings") or {})
            settings["agreements"] = (list(settings.get("agreements") or []) + [row])[-20:]
            sc.table("profiles").update({"settings": settings}).eq("id", g[0]["owner_id"]).execute()
        except Exception:
            pass
    send_signed_copy(row)
    return row


def send_signed_copy(row):
    """Email the signed agreement (PDF with both signatures) to the gym, with a copy to GymPulse AI."""
    import base64
    import requests
    import gympulse_admin as gadm
    import gympulse_email as ge
    import gympulse_legal as glegal
    key = gadm._env("RESEND_API_KEY")
    to = gw._text(row.get("signer_email")).strip()
    if not (key and "@" in to):
        return False
    when = pd.to_datetime(row.get("signed_at"), errors="coerce", utc=True)
    when = "" if pd.isna(when) else f"{when.tz_convert(gw.APP_TZ):%d %B %Y at %H:%M} (Lagos time)"
    first = gw._text(row.get("signer_name")).split(" ")[0] or "there"
    body = (f'<p style="margin:0 0 10px">Hi {ge.esc(first)},</p>'
            '<p style="margin:0 0 10px">Thank you for choosing GymPulse AI. Your signed Subscription Agreement is '
            "attached, signed by you and by GymPulse AI. It's month to month and you can cancel at any time. "
            "You only sign it once.</p>"
            + ge.details([("Business", ge.esc(row.get("business_name") or "–")),
                          ("Signed by", ge.esc(f"{row.get('signer_name')} ({row.get('signer_role')})")),
                          ("Signed on", ge.esc(when)),
                          ("For GymPulse AI", ge.esc(f"{glegal.FOUNDER}, {glegal.FOUNDER_TITLE}")),
                          ("Agreement version", ge.esc(row.get("version")))]))
    try:
        pdf = glegal.agreement_pdf(row)
        safe = re.sub(r"[^A-Za-z0-9]+", "-", gw._text(row.get("business_name")) or "gym").strip("-")
        r = requests.post("https://api.resend.com/emails", timeout=25, headers={"Authorization": f"Bearer {key}"},
                          json={"from": gadm._env("BILLING_FROM", "GymPulse AI <billing@usegympulseai.com>"),
                                "to": [to], "bcc": ["emmanuel@usegympulseai.com"],
                                "reply_to": "emmanuel@usegympulseai.com",
                                "subject": f"Your signed GymPulse AI Subscription Agreement ({row.get('business_name')})",
                                "html": ge.layout("Agreement signed", body, preheader="Your signed agreement is attached"),
                                "text": (f"Hi {first},\n\nYour signed GymPulse AI Subscription Agreement is attached. "
                                         "It's month to month and you can cancel at any time.\n\n" + ge.SITE),
                                "attachments": [{"filename": f"GymPulse-AI-Subscription-Agreement-{safe}.pdf",
                                                 "content": base64.b64encode(pdf).decode()}]})
        return r.status_code < 300
    except Exception as error:
        import gympulse_monitoring as gmon
        gmon.capture(error, "signed agreement email")
        return False


def _render_pay(plan, period, s, ps):
    import gympulse_invoices as gi
    inv = st.session_state.get("co_inv") or {}
    st.button("Change details", icon=":material/arrow_back:", type="tertiary", key="co_back2",
              on_click=_view, args=("checkout",))
    by_transfer = st.session_state.get("co_channel") == "pay_transfer"
    gw.page_header("Review and pay", "One last step: pay securely with Paystack.", "Checkout")
    left, right = st.columns([1.35, 1], gap="large")
    with right:
        gw._md(_summary_html(plan, period, s, ps))
    with left:
        gw._md(f'''<div class="co-card">
            <div class="co-row"><span>Business</span><b>{gw._esc(inv.get("business_name"))}</b></div>
            <div class="co-row"><span>Billed to</span><b>{gw._esc(inv.get("billing_name"))}</b></div>
            <div class="co-row"><span>Receipt to</span><b>{gw._esc(inv.get("billing_email"))}</b></div>
            <div class="co-row"><span>Invoice</span><b>{gw._esc(gi.number(inv))}</b></div></div>
            <div class="co-pay"><a class="lx-btn lx-btn-primary" href="{gw._esc(st.session_state.get("co_url", "#"))}"
            target="_self">{"Get transfer details" if by_transfer else "Pay"} · {gi.money(price_for(plan, period))}</a>
            <div class="co-lock">🔒 {("Paystack gives you an account number for this payment. Transfer the exact "
            "amount from any bank app; Paystack confirms it in seconds and you come straight back here.")
            if by_transfer else "You'll pay on Paystack's secure page by card or USSD, then come straight back here."}
            Your plan switches on as soon as the payment is confirmed, and your receipt is emailed to
            {gw._esc(inv.get("billing_email"))}.</div></div>''')


def _render_transfer(supabase, gym_id, plan, period, s, p, ps):
    import gympulse_invoices as gi
    import gympulse_reports as rp
    inv = st.session_state.get("co_inv") or {}
    sent = st.session_state.get("sub_view") == "sent"
    if not sent:
        st.button("Change details", icon=":material/arrow_back:", type="tertiary", key="co_back3",
                  on_click=_view, args=("checkout",))
    gw.page_header("Bank transfer" if not sent else "Waiting for your transfer",
                   "Send the exact amount with your invoice number as the reference." if not sent
                   else "Your plan switches on as soon as the money arrives.", "Checkout")
    left, right = st.columns([1.35, 1], gap="large")
    with right:
        gw._md(_summary_html(plan, period, s, ps))
    with left:
        if sent:
            gw._md(f'''<div class="co-done"><div class="co-tick co-wait">…</div>
                <div class="co-title">Waiting for your transfer</div>
                <div class="co-sub">Invoice {gw._esc(gi.number(inv))} · {gi.money(inv.get("amount"))}. As soon as the money
                arrives, your {gw._esc(plan["name"])} plan switches on and your receipt is emailed to
                {gw._esc(inv.get("billing_email"))}. You can see its status under Billing history.</div></div>''')
            st.button("Back to Subscription", key="co_done_back", on_click=_view, args=("plans",),
                      use_container_width=True)
            return
        gw._md(f'''<div class="co-bank">
            <div class="co-row"><span>Bank</span><b>{gw._esc(p.get("bank_name"))}</b></div>
            <div class="co-row"><span>Account number</span><b>{gw._esc(p.get("bank_account"))}</b></div>
            <div class="co-row"><span>Account name</span><b>{gw._esc(p.get("bank_holder"))}</b></div>
            <div class="co-row"><span>Amount</span><b>{gi.money(inv.get("amount"))}</b></div>
            <div class="co-row"><span>Reference</span><b>{gw._esc(gi.number(inv))}</b></div></div>''')
        st.caption("Use the reference so we can match your payment. Your plan switches on as soon as we confirm it.")
        c1, c2 = st.columns(2)
        if c1.button("I've made the transfer", type="primary", use_container_width=True, key="co_sent"):
            _notify_transfer(inv)
            _view("sent")
            st.rerun()
        with c2:
            rp.download_link("Download invoice (PDF)", gi.receipt_pdf(inv, paid=False),
                             f"GymPulse-AI-invoice-{gi.number(inv)}.pdf", rp.PDF, "co_inv_pdf")


# ------------------------------------------------------------------ admin
def admin_set(sc, gym_id, **fields):
    if fields.get("plan") and "member_limit" not in fields:
        fields["member_limit"] = _limit_fields(sc, gym_id, fields["plan"]).get("member_limit")
    row = {"gym_id": gym_id, **fields, "updated_at": datetime.now(timezone.utc).isoformat()}
    try:
        sc.table("gym_subscriptions").upsert(row, on_conflict="gym_id").execute()
    except Exception:                                  # phase 38 not run yet
        sc.table("gym_subscriptions").upsert({k: v for k, v in row.items() if k != "member_limit"},
                                             on_conflict="gym_id").execute()
    st.session_state.pop("_cache", None)


def _render_usage_table(sc, gyms, p):
    """One row per gym: plan, members against the limit, Archie and WhatsApp used this month."""
    import gympulse_whatsapp as gwa
    ps = {x["name"].lower(): x for x in plans(p)}
    try:
        subs = {r["gym_id"]: r for r in sc.table("gym_subscriptions").select("*").execute().data or []}
    except Exception:
        subs = {}
    try:
        arch = {r["gym_id"]: r["questions"] for r in sc.table("archie_usage").select("gym_id, questions")
                .eq("month", _month()).execute().data or []}
    except Exception:
        arch = {}
    wa = gwa.month_usage(sc)["by_gym"]
    counts = {}
    try:
        for r in gw.fetch_all(sc.table("members").select("gym_id").eq("archived", False).order("gym_id")):
            counts[r["gym_id"]] = counts.get(r["gym_id"], 0) + 1
    except Exception:
        pass
    rows = []
    for e in gyms:
        gid = e["gym"]["id"]
        sub = subs.get(gid) or {}
        plan = ps.get(gw._text(sub.get("plan")).split(" · ")[0].strip().lower()) if sub.get("status") == "active" else None
        n = counts.get(gid, 0)
        lim = plan["members"] if plan else 0
        over = bool(lim and n > lim)
        rows.append({"Gym": e["name"], "Plan": plan["name"] if plan else gw._text(sub.get("status"), "trial").title(),
                     "Members": f"{n:,}" + (f" / {lim:,}" if lim else ""),
                     "Archie": f"{arch.get(gid, 0):,}" + (f" / {plan['archie']:,}" if plan and plan["archie"] else ""),
                     "WhatsApp": f"{wa.get(gid, {}).get('count', 0):,}",
                     "Status": "Over limit" if over else "OK"})
    gw.table(sorted(rows, key=lambda r: r["Status"] != "Over limit"), pills={"Status": {"OK": "lime", "Over limit": "amber"}},
             caption="Gyms over their member limit see a reminder and have 30 days to upgrade before new members are "
                     "paused. Archie and WhatsApp reset on the 1st.")


def render_admin_billing(sc, gyms, audit):
    """Admin → Billing: prices, payment details, and each gym's plan."""
    today = gw.today_local()
    try:
        subs = {r["gym_id"]: r for r in sc.table("gym_subscriptions").select("*").execute().data or []}
        rows = sc.table("platform_settings").select("value").eq("key", "pricing").limit(1).execute().data
        p = {**DEFAULT_PRICING, **(rows[0]["value"] if rows else {})}
    except Exception:
        st.info("Run sql/phase10_billing.sql in Supabase to switch on free trials and subscriptions.")
        return
    with st.container(border=True):
        on = billing_on(p)
        c1, c2 = st.columns([3, 1.3], vertical_alignment="center")
        c1.markdown("**Billing is ON**: trials end after 30 days and gyms pay to continue." if on else
                    "**Pilot mode is ON**: every gym uses all features free. Nobody is locked, asked to pay or "
                    "sent trial emails.")
        new = c2.toggle("Charge gyms", value=on, key="adm_billing_on",
                        help="Turn off during your pilot. Turn on when you're ready to start charging.")
        if new != on:
            sc.table("platform_settings").upsert({"key": "pricing", "value": {**{k: v for k, v in p.items()
                                                                            if k in DEFAULT_PRICING or k == "plans"},
                                                                         "billing_on": bool(new)},
                                                  "updated_at": datetime.now(timezone.utc).isoformat()},
                                                 on_conflict="key").execute()
            audit(sc, "billing_switched_on" if new else "pilot_mode_on", {"gym": {"id": None}, "name": "All gyms",
                                                                          "email": None})
            st.session_state.pop("_cache", None)
            st.session_state["adm_flash"] = ("Billing is on. Give everyone a fresh trial below if your pilot gyms "
                                             "shouldn't be locked yet." if new else
                                             "Pilot mode is on: every gym is free until you switch billing back on.")
            st.rerun()
        if on:
            restart = st.button("Give every gym a fresh 30-day trial from today", key="adm_fresh_trials",
                                help="For gyms still on a trial or whose trial ended. Paying and free-access gyms "
                                     "are not changed.")
            if restart:
                end = (today + timedelta(days=TRIAL_DAYS - 1)).isoformat()
                n = 0
                for g in gyms:
                    sub_ = subs.get(g["gym"]["id"], {})
                    if sub_.get("status") in (None, "trial"):
                        admin_set(sc, g["gym"]["id"], status="trial", trial_ends_on=end)
                        n += 1
                audit(sc, "fresh_trials", {"gym": {"id": None}, "name": "All gyms", "email": None}, {"gyms": n})
                st.session_state["adm_flash"] = f"{n} gym{'s' if n != 1 else ''} now have 30 days free from today."
                st.rerun()
    states = {g["gym"]["id"]: state(subs.get(g["gym"]["id"], {}), today) for g in gyms}
    gw.kpi_row([("On free trial", str(sum(s["status"] == "trial" for s in states.values())), "cyan", f"{TRIAL_DAYS} days"),
                ("Paying", str(sum(s["status"] == "active" for s in states.values())), "lime", ""),
                ("Ended, not paid", str(sum(s["status"] == "expired" for s in states.values())), "red", "follow up"),
                ("Monthly income", _money(sum(float(subs.get(gid, {}).get("price") or 0) for gid, s in states.items()
                                              if s["status"] == "active")), "amber", "from paying gyms")])

    with st.expander("Usage this month: members, Archie and WhatsApp per gym"):
        _render_usage_table(sc, gyms, p)

    with st.expander("Plans, prices and how gyms pay", expanded=not plans(p)):
        saved = [x for x in (p.get("plans") or []) if gw._text(x.get("name"))]
        if saved and any(x.get("wa_renew") in (None, "") for x in saved):
            st.warning("Your saved plans don't set WhatsApp messages yet, so they're estimated from the member numbers. "
                       "Edit the WhatsApp columns below, or start from the recommended plans.")
        a, b = st.columns([2, 3], vertical_alignment="center")
        if a.button("Use the recommended plans", key="adm_default_plans",
                    help="Starter, Growth, Pro, Business and Enterprise by gym size: every feature, WhatsApp included. "
                         "You can still change every price after."):
            value = {**p, "plans": DEFAULT_PLANS, "monthly": None, "yearly": None}
            sc.table("platform_settings").upsert({"key": "pricing", "value": value,
                                                  "updated_at": datetime.now(timezone.utc).isoformat()},
                                                 on_conflict="key").execute()
            st.session_state["adm_flash"] = "Recommended plans saved. Check the prices below and adjust if you like."
            st.rerun()
        b.caption("Starter ≤150 · Growth ≤500 · Pro ≤1,500 · Business ≤5,000 · Enterprise ≤20,000 members, "
                  "each with WhatsApp messages included.")
        with st.form("adm_pricing"):
            st.markdown("**Your plans.** One row per plan, cheapest first. Gyms see these on the website, in the "
                        "Upgrade pop-up and on their Subscription page. **Features** sets what each plan unlocks; "
                        "the benefits list is written for you. Leave the yearly price blank for 2 months free.")
            level_names = {1: "1 · Essentials", 2: "2 · + Growth tools", 3: "3 · Everything"}
            start_rows = [{**x, "access": level_names[x["access"]]} for x in plans(p)]
            plan_rows = st.data_editor(
                pd.DataFrame(start_rows, columns=["name", "access", "monthly", "yearly", "members", "wa_renew", "wa_promo",
                                                  "archie", "support", "for_who", "tagline", "popular"]),
                num_rows="dynamic", use_container_width=True, key="adm_plans",
                column_config={"name": st.column_config.TextColumn("Plan name", required=True),
                               "access": st.column_config.SelectboxColumn("Features", options=list(level_names.values()),
                                                                          required=True),
                               "monthly": st.column_config.NumberColumn("Monthly (₦)", min_value=0, step=1000),
                               "yearly": st.column_config.NumberColumn("Yearly (₦)", min_value=0, step=5000),
                               "members": st.column_config.NumberColumn("Members (0 = no limit)", min_value=0, step=50),
                               "wa_renew": st.column_config.NumberColumn("WhatsApp renewals/month", min_value=0, step=50,
                                                                         help="Renewal reminders and replies (utility price)"),
                               "wa_promo": st.column_config.NumberColumn("WhatsApp promo/month", min_value=0, step=10,
                                                                         help="We missed you, celebrations… (marketing price)"),
                               "archie": st.column_config.NumberColumn("Archie questions/month (0 = unlimited)",
                                                                       min_value=0, step=50),
                               "support": st.column_config.SelectboxColumn("Help", options=list(SUPPORT),
                                                                           help="standard · priority (WhatsApp support, "
                                                                                "setup done for them) · dedicated "
                                                                                "(+ account manager, training, review calls)"),
                               "for_who": st.column_config.TextColumn("Who it's for"),
                               "tagline": st.column_config.TextColumn("One-line description"),
                               "popular": st.column_config.CheckboxColumn("Recommended")})
            st.caption("  \n".join(f"**{label}**{' adds' if lv > 1 else ''}: " + "; ".join(FEATURES[lv])
                                   for lv, label in level_names.items()))
            import gympulse_whatsapp as gwa
            fx = gwa.naira_per_usd()
            u_cost, m_cost = gwa.RATES_USD["UTILITY"] * fx, gwa.RATES_USD["MARKETING"] * fx
            gw.table([{"Plan": x["name"], "Price / month": _money(x.get("monthly")),
                       "WhatsApp cost if fully used": _money(x["wa_renew"] * u_cost + x["wa_promo"] * m_cost),
                       "Share of price": (f"{(x['wa_renew'] * u_cost + x['wa_promo'] * m_cost) / x['monthly']:.0%}"
                                          if x.get("monthly") else "–")} for x in plans(p)],
                     caption=f"Cost check at ₦{u_cost:,.0f} per renewal message and ₦{m_cost:,.0f} per promotional "
                             "message. Keep WhatsApp under about 40% of the price so there's profit after hosting.")
            link = st.text_input("Online payment link (optional)", p.get("pay_link") or "",
                                 placeholder="e.g. your Paystack payment page")
            c3, c4, c5 = st.columns(3)
            bank = c3.text_input("Bank", p.get("bank_name") or "")
            acct = c4.text_input("Account number", p.get("bank_account") or "")
            holder = c5.text_input("Account name", p.get("bank_holder") or "")
            c6, c7 = st.columns(2)
            wa = c6.text_input("Your WhatsApp for questions", p.get("contact_whatsapp") or "")
            em = c7.text_input("Email for payment notices", p.get("contact_email") or "")
            note = st.text_input("Short note under the price (optional)", p.get("note") or "")
            if st.form_submit_button("Save prices", type="primary"):
                plan_list = []
                for _, r in plan_rows.iterrows():
                    name = gw._text(r.get("name")).strip()
                    mo = float(r["monthly"]) if pd.notna(r.get("monthly")) and r.get("monthly") else None
                    yr = float(r["yearly"]) if pd.notna(r.get("yearly")) and r.get("yearly") else None
                    lv = next((k for k, v in level_names.items() if v == r.get("access")), 1)
                    if name and (mo or yr):
                        num = lambda k: int(r[k]) if pd.notna(r.get(k)) and r.get(k) not in ("", None) else 0
                        plan_list.append({"name": name, "access": lv, "monthly": mo, "yearly": yr,
                                          "members": num("members"), "wa_renew": num("wa_renew"),
                                          "wa_promo": num("wa_promo"),
                                          "archie": num("archie"),
                                          "support": r.get("support") if r.get("support") in SUPPORT else "standard",
                                          "for_who": gw._text(r.get("for_who")).strip(),
                                          "tagline": gw._text(r.get("tagline")).strip(),
                                          "popular": bool(r.get("popular")) if pd.notna(r.get("popular")) else False})
                value = {"plans": plan_list, "monthly": None, "yearly": None, "currency": "NGN",
                         "pay_link": link.strip(), "bank_name": bank.strip(), "bank_account": acct.strip(),
                         "bank_holder": holder.strip(), "contact_whatsapp": wa.strip(),
                         "contact_email": em.strip(), "note": note.strip(), "billing_on": billing_on(p)}
                sc.table("platform_settings").upsert({"key": "pricing", "value": value,
                                                      "updated_at": datetime.now(timezone.utc).isoformat()},
                                                     on_conflict="key").execute()
                st.session_state["adm_flash"] = "Plans saved. They now show on the website and in the app."
                st.rerun()

    with st.expander("Online payments (Paystack)"):
        if paystack_key():
            mode = "test mode" if paystack_key().startswith("sk_test") else "live"
            st.success(f"Paystack is connected ({mode}). Gyms can pay by card, transfer or USSD, and their plan "
                       "switches on by itself. Money goes to the bank account in your Paystack dashboard.")
            if st.button("Check Paystack for missed payments", key="adm_ps_sync"):
                n = reconcile_paystack(sc, days=14, log=lambda *_: None)
                st.session_state["adm_flash"] = f"Checked Paystack: {n} payment{'s' if n != 1 else ''} switched on."
                st.rerun()
        else:
            st.info("Not connected yet. Add your Paystack secret key as PAYSTACK_SECRET_KEY in Render "
                    "(Environment) and in GitHub (Settings → Secrets → Actions). See docs/BILLING.md.")

    order = {"expired": 0, "trial": 1, "active": 2, "free": 3, "off": 4}
    ordered = sorted(gyms, key=lambda g: (order[states[g["gym"]["id"]]["status"]],
                                          states[g["gym"]["id"]].get("days_left") or 0))
    status_word = {"trial": "Free trial", "active": "Paying", "free": "Free access", "expired": "Ended", "off": "–"}

    def _d_txt(v):
        d = _d(v)
        return f"{d:%d %b %Y}" if d else "–"

    import gympulse_invoices as gi
    pend = gi.pending_transfers(sc)
    names = {g["gym"]["id"]: g["name"] for g in gyms}
    if pend:
        st.markdown('<div class="section-label">BANK TRANSFERS TO CONFIRM</div>', unsafe_allow_html=True)
        gw.table([{"Invoice": gi.number(x), "Gym": names.get(x["gym_id"], x.get("business_name") or "–"),
                   "Plan": f"{x.get('plan')} · {'Yearly' if x.get('period') == 'yearly' else 'Monthly'}",
                   "Amount": gi.money(x.get("amount")), "Created": str(x.get("created_at"))[:10],
                   "Status": "Awaiting payment"} for x in pend], pills={"Status": {"Awaiting payment": "amber"}})
        c1, c2, c3 = st.columns([2, 1, 1])
        pk = c1.selectbox("Transfer", range(len(pend)), key="bill_tr_pick", label_visibility="collapsed",
                          format_func=lambda j: f"{gi.number(pend[j])} · {names.get(pend[j]['gym_id'], '')} · "
                                                f"{gi.money(pend[j].get('amount'))}")
        if c2.button("Confirm received", type="primary", use_container_width=True, key="bill_tr_ok"):
            inv, until = confirm_transfer(sc, pend[pk], (st.session_state.get("auth_user") or {}).get("email", "admin"))
            audit(sc, "billing_transfer_confirmed", next((g for g in gyms if g["gym"]["id"] == inv["gym_id"]), {}),
                  {"invoice": gi.number(inv), "until": until.isoformat()})
            st.session_state["adm_flash"] = f"Confirmed {gi.number(inv)}. Plan active until {until:%d %b %Y}, receipt emailed."
            st.rerun()
        if c3.button("Cancel invoice", use_container_width=True, key="bill_tr_no"):
            gi.update(sc, pend[pk], status="cancelled")
            st.session_state["adm_flash"] = f"Cancelled {gi.number(pend[pk])}."
            st.rerun()
    st.markdown('<div class="section-label">ALL GYMS</div>', unsafe_allow_html=True)
    gw.table([{"Gym": g["name"], "Owner": g.get("email") or "–",
               "Status": status_word.get(states[g["gym"]["id"]]["status"], "–"),
               "Plan": gw._text(subs.get(g["gym"]["id"], {}).get("plan"), "–"),
               "Trial ends": _d_txt(subs.get(g["gym"]["id"], {}).get("trial_ends_on")),
               "Paid until": _d_txt(subs.get(g["gym"]["id"], {}).get("paid_until")),
               "Monthly": _money(subs.get(g["gym"]["id"], {}).get("price"))
               if subs.get(g["gym"]["id"], {}).get("price") else "–"} for g in ordered],
             pills={"Status": {"Free trial": "cyan", "Paying": "lime", "Free access": "grey", "Ended": "red"}},
             max_height=460)
    if not ordered:
        return
    ids = [g["gym"]["id"] for g in ordered]
    pick = st.selectbox("Manage a gym's subscription", ids, key="bill_pick_gym",
                        format_func=lambda i: next(f"{g['name']} · {states[i]['label'] or 'no plan yet'}"
                                                   for g in ordered if g["gym"]["id"] == i))
    for g in [x for x in ordered if x["gym"]["id"] == pick]:
        gid = g["gym"]["id"]
        s, sub = states[gid], subs.get(gid, {})
        tone = {"trial": "cyan", "active": "lime", "free": "grey", "expired": "red"}.get(s["status"], "grey")
        with st.container(border=True):
            gw._md(f'<div style="font-size:18px;font-weight:700;margin-bottom:6px">{gw._esc(g["name"])}</div>')
            gw._md(gw.chip(s["status"], tone, dot=True) + (gw.chip("admin", "cyan") if (g.get("email") or "").lower()
                                                          in __import__("gympulse_admin").admin_emails() else ""))
            st.caption(f"Trial ends {sub.get('trial_ends_on') or '–'} · paid until {sub.get('paid_until') or '–'} · "
                       f"price {_money(sub.get('price'))}")
            ps = plans(p)
            names = [x["name"] for x in ps] or ["Standard"]
            current = gw._text(sub.get("plan")).split(" · ")[0]
            c0, c1, c2, c3 = st.columns(4)
            plan_name = c0.selectbox("Plan", names, index=names.index(current) if current in names else 0,
                                     key=f"bill_plan_{gid}")
            chosen = next((x for x in ps if x["name"] == plan_name), {})
            months = c1.selectbox("Paid for", [1, 3, 6, 12], key=f"bill_m_{gid}",
                                  format_func=lambda m: f"{m} month{'s' if m != 1 else ''}")
            price = c2.number_input("Monthly price for this gym (₦)", 0.0, step=1000.0,
                                    value=float(chosen.get("monthly") or sub.get("price") or 0),
                                    key=f"bill_p_{gid}_{plan_name}")
            send_rc = st.checkbox("Email a receipt to the owner", value=bool(g.get("email")), key=f"bill_rc_{gid}",
                                  disabled=not g.get("email"))
            if c3.button("Mark as paid", key=f"bill_paid_{gid}", type="primary", use_container_width=True):
                import gympulse_invoices as gi
                total = float(price or 0) * months
                start, until = activate(sc, gid, plan_name, "monthly", months, total, "Marked as paid in Admin")
                inv = gi.create(sc, gid, plan_name, "monthly", total,
                                {"business_name": g["name"], "billing_name": g.get("owner"),
                                 "billing_email": g.get("email")}, "admin", months=months)
                inv = gi.update(sc, inv, status="paid", paid_at=datetime.now(timezone.utc).isoformat(),
                                period_start=start.isoformat(), period_end=until.isoformat())
                sent = gi.send_receipt(sc, inv) if send_rc and total else False
                audit(sc, "billing_paid", g, {"months": months, "until": until.isoformat(), "price": price,
                                              "receipt": gi.number(inv)})
                st.session_state["adm_flash"] = (f"{g['name']} is subscribed until {until:%d %b %Y}."
                                                 + (f" Receipt {gi.number(inv)} emailed." if sent else ""))
                st.rerun()
            d1, d2, d3 = st.columns(3)
            if d1.button("Extend trial 14 days", key=f"bill_ext_{gid}", use_container_width=True):
                base = max(_d(sub.get("trial_ends_on")) or today, today)
                admin_set(sc, gid, status="trial", trial_ends_on=(base + timedelta(days=14)).isoformat())
                audit(sc, "billing_trial_extended", g, {"days": 14})
                st.session_state["adm_flash"] = f"{g['name']}'s trial now ends {(base + timedelta(days=14)):%d %b}."
                st.rerun()
            if d2.button("Give free access", key=f"bill_free_{gid}", use_container_width=True,
                         help="For test accounts, partners or friends. They are never asked to pay."):
                admin_set(sc, gid, status="free")
                audit(sc, "billing_free", g)
                st.session_state["adm_flash"] = f"{g['name']} now has free access."
                st.rerun()
            if s["status"] in ("active", "free") and d3.button("End subscription", key=f"bill_end_{gid}",
                                                              use_container_width=True):
                admin_set(sc, gid, status="trial", trial_ends_on=(today - timedelta(days=1)).isoformat(),
                          paid_until=None)
                audit(sc, "billing_ended", g)
                st.session_state["adm_flash"] = f"{g['name']}'s subscription has ended."
                st.rerun()


def gym_levels(sc):
    """{gym_id: feature level} for the scheduled jobs (3 when billing isn't set up)."""
    try:
        subs = sc.table("gym_subscriptions").select("*").execute().data or []
        rows = sc.table("platform_settings").select("value").eq("key", "pricing").limit(1).execute().data
        p = {**DEFAULT_PRICING, **(rows[0]["value"] if rows else {})}
        ps = plans(p)
    except Exception:
        return {}
    if not billing_on(p):
        return {}                                     # pilot mode: every gym gets everything
    return {r["gym_id"]: access_level(r, ps) for r in subs}


# ------------------------------------------------------------------ reminders (scheduled)
def trial_reminders(sc, gyms, dry_run=False, log=print):
    """Email owners 7, 3 and 1 days before their trial ends and the day after; paying gyms 3 and 1 days
    before their plan ends and the day after. Once each."""
    import gympulse_admin as gadm
    import gympulse_email as ge
    import requests
    today = gw.today_local()
    try:
        subs = {r["gym_id"]: r for r in sc.table("gym_subscriptions").select("*").execute().data or []}
        done = {(r["gym_id"], r["ref"]) for r in sc.table("billing_events").select("gym_id, ref").execute().data or []}
        rows = sc.table("platform_settings").select("value").eq("key", "pricing").limit(1).execute().data
        p = {**DEFAULT_PRICING, **(rows[0]["value"] if rows else {})}
    except Exception:
        log("billing tables missing: run sql/phase10_billing.sql")
        return 0
    if not billing_on(p):
        log("pilot mode: no trial or renewal emails")
        return 0
    key, sent = gadm._env("RESEND_API_KEY"), 0
    for g in gyms:
        gid, sub = g["gym"]["id"], subs.get(g["gym"]["id"])
        if not sub or sub.get("status") not in ("trial", "active") or "@" not in (g.get("email") or ""):
            continue
        if (g.get("email") or "").lower() in gadm.admin_emails():
            continue
        paying = sub.get("status") == "active"
        end = _d(sub.get("paid_until") if paying else sub.get("trial_ends_on"))
        if not end:
            continue
        left = (end - today).days
        stage = ({3: "3days", 1: "1day", -1: "ended"} if paying else {7: "7days", 3: "3days", 1: "1day", -1: "ended"}).get(left)
        kind = "renew" if paying else "trial"
        if not stage or (gid, f"{kind}:{stage}:{end}") in done:
            continue
        first = gw._text(g["owner"]).split(" ")[0] or "there"
        ps = plans(p)
        price = "Plans: " + "; ".join(f"{x['name']} {_money(x['monthly'])} a month" for x in ps if x.get("monthly")) + "."
        if paying:
            plan_name = gw._text(sub.get("plan"), "GymPulse AI").split(" · ")[0]
            price = ""
            if stage == "ended":
                subject, title = f"{g['name']}: your GymPulse AI plan has ended", "Your plan has ended"
                lead = (f"Your {plan_name} plan ended on {end:%A %d %B}. Your members, check-ins and reports are "
                        "all saved. Renew to pick up right where you left off.")
            else:
                days = {"3days": "3 days", "1day": "1 day"}[stage]
                subject, title = f"{g['name']}: your GymPulse AI plan ends in {days}", f"Your plan ends in {days}"
                lead = (f"Your {plan_name} plan ends on {end:%A %d %B}. Renew in a minute from the Subscription "
                        "page to keep your reminders, Risk Radar and reports running.")
        elif stage == "ended":
            subject, title = f"{g['name']}: your GymPulse AI free trial has ended", "Your free trial has ended"
            lead = ("Your 30-day free trial of GymPulse AI has ended. Your members, check-ins and reports are all "
                    "saved. Upgrade to pick up right where you left off.")
        else:
            days = {"7days": "7 days", "3days": "3 days", "1day": "1 day"}[stage]
            subject, title = f"{g['name']}: {days} left in your GymPulse AI trial", f"{days} left in your free trial"
            lead = (f"Your free trial of GymPulse AI ends on {end:%A %d %B}. Subscribe to keep your renewal "
                    "reminders, Risk Radar and monthly reports running without a break.")
        body = (f"<p style=\"margin:0 0 10px\">Hi {gw._esc(first)},</p><p style=\"margin:0 0 12px\">{gw._esc(lead)}</p>"
                + (f"<p style=\"margin:0 0 12px\">{gw._esc(price)}</p>" if price else "")
                + ge.button("Renew now" if paying else "See plans and upgrade", f"{ge.SITE}/?p=Subscription"))
        if dry_run:
            log(f"  would email {g['name']} <{g['email']}>: {subject}")
            sent += 1
            continue
        if not key:
            log("RESEND_API_KEY missing")
            return sent
        try:
            r = requests.post("https://api.resend.com/emails", timeout=20, headers={"Authorization": f"Bearer {key}"},
                              json={"from": gadm._env("REPORTS_FROM", gadm.REPORTS_FROM_DEFAULT), "to": [g["email"]],
                                    "reply_to": p.get("contact_email") or "emmanuel@usegympulseai.com",
                                    "subject": subject, "html": ge.layout(title, body, preheader=subject),
                                    "text": f"Hi {first},\n\n{lead}\n\n{price}\n\n{ge.SITE}"})
            if r.status_code < 300:
                sc.table("billing_events").insert({"gym_id": gid, "kind": f"{kind}_reminder",
                                                   "ref": f"{kind}:{stage}:{end}"}).execute()
                sent += 1
                log(f"  sent {kind} {stage} -> {g['name']}")
        except Exception as error:
            log(f"  failed {kind} {stage} -> {g['name']}: {error}")
    return sent
