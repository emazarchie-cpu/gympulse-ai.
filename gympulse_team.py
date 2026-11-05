"""GymPulse AI · Owner and staff access.

The gym owner adds staff in Owner → Team & access. Each staff member gets their
own login (created with the server key and emailed to them with a temporary
password) and works in the owner's gym: members, check-in, renewals, plays,
follow-ups and the Grow tools. Owner-only: the Owner page (business insights,
team, monthly report, subscription and billing), Archie, Subscription, and
gym settings such as email branding and payment details.

Database: sql/phase13_staff.sql (gym_staff, gp_is_gym_owner, gp_staff_context,
gp_owns_gym extended to active staff).
"""
import secrets
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

import gympulse_workspaces as gw

SQL_HINT = ("Staff logins need a one-time setup: open Supabase, go to SQL Editor, paste in the file "
            "sql/phase13_staff.sql and press Run.")
OWNER_ONLY = {"Owner", "Business Insights", "Archie", "Subscription", "Model Insights", "About the Model", "Admin"}
OWNER_ONLY_GROW = {"Monthly report", "Team"}
STAFF_CAN = ["Dashboard: today's priorities and follow-ups (no revenue figures)",
             "Members, member profiles and check-in", "Payments & Renewals: record payments and renewals",
             "Risk Radar and Action Centre: run and record plays", "Follow-ups and messages to members",
             "Grow tools: renewals, automatic messages, gym updates, loyalty, new members, classes and more"]
OWNER_ONLY_LIST = ["Owner page: business insights, revenue and retention rate", "Team & access",
                   "Monthly report", "Subscription, billing and receipts", "Archie, the AI assistant",
                   "Gym settings: email branding, payment details, automation and loyalty settings"]


def is_staff():
    return st.session_state.get("role") == "staff"


def staff_context(supabase):
    """The gym this login works in as staff, or None (owners, or before the SQL is run)."""
    try:
        data = supabase.rpc("gp_staff_context", {}).execute().data
    except Exception:
        return None
    if isinstance(data, list):
        data = data[0] if data else None
    if isinstance(data, dict) and "gp_staff_context" in data:
        data = data["gp_staff_context"]
    return data if isinstance(data, dict) and data.get("gym") else None


def enter_staff_mode(ctx, own_profile):
    """Make this session work in the owner's gym, under the staff member's own name."""
    owner = ctx.get("owner") or {}
    staff = ctx.get("staff") or {}
    st.session_state["role"] = "staff"
    st.session_state["staff"] = {**staff, "own_profile": own_profile}
    st.session_state["user_profile"] = {
        "id": owner.get("id"), "full_name": owner.get("full_name"),
        "business_name": owner.get("business_name") or (ctx.get("gym") or {}).get("business_name"),
        "settings": owner.get("settings") or {}, "theme": (own_profile or {}).get("theme"),
        "avatar": (own_profile or {}).get("avatar")}


def staff_name():
    return gw._text((st.session_state.get("staff") or {}).get("full_name"), "Team member")


def owner_only_message(what="this"):
    st.info(f"Only the gym owner can change {what}. Ask them if something needs updating.")


# ------------------------------------------------------------------ managing staff (owner)
def _service():
    import gympulse_admin as gadm
    return gadm.service_client()


def load_staff(supabase, gym_id):
    try:
        return supabase.table("gym_staff").select("*").eq("gym_id", gym_id).order("created_at").execute().data or []
    except Exception:
        return None


def _temp_password():
    return "GP-" + secrets.token_urlsafe(9).replace("_", "x").replace("-", "y")


def _send_invite(name, email, password, gym_name, owner_name):
    import requests
    import gympulse_admin as gadm
    import gympulse_email as ge
    key = gadm._env("RESEND_API_KEY")
    if not key:
        return False
    first = gw._text(name).split(" ")[0] or "there"
    body = (f'<p style="margin:0 0 10px">Hi {ge.esc(first)},</p>'
            f'<p style="margin:0 0 6px">{ge.esc(owner_name or "Your gym owner")} has added you to '
            f'<b>{ge.esc(gym_name)}</b> on GymPulse AI, so you can help with members, check-ins and renewals.</p>'
            + ge.details([("Sign in at", ge.esc(ge.SITE.replace("https://", ""))), ("Email", ge.esc(email)),
                          ("Temporary password", f"<code>{ge.esc(password)}</code>")])
            + '<p style="margin:0 0 12px">Please change your password after you sign in (Settings → Password).</p>'
            + ge.button("Sign in to GymPulse AI", ge.SITE))
    try:
        r = requests.post("https://api.resend.com/emails", timeout=20, headers={"Authorization": f"Bearer {key}"},
                          json={"from": gadm._env("REPORTS_FROM", gadm.REPORTS_FROM_DEFAULT), "to": [email],
                                "subject": f"You've been added to {gym_name} on GymPulse AI",
                                "html": ge.layout("Welcome to the team", body,
                                                  preheader=f"Your login for {gym_name} on GymPulse AI"),
                                "text": (f"Hi {first},\n\n{owner_name or 'Your gym owner'} added you to {gym_name} on "
                                         f"GymPulse AI.\n\nSign in: {ge.SITE}\nEmail: {email}\nTemporary password: "
                                         f"{password}\n\nPlease change your password after you sign in.")})
        return r.status_code < 300
    except Exception:
        return False


def add_staff(gym_id, name, email, gym_name, owner_name):
    """Create the staff login and email it to them. Returns (ok, message, password or None)."""
    sc = _service()
    if not sc:
        return False, "Adding staff isn't available right now (server key missing).", None
    email = email.strip().lower()
    password = _temp_password()
    try:
        res = sc.auth.admin.create_user({"email": email, "password": password, "email_confirm": True,
                                         "user_metadata": {"full_name": name.strip(), "gympulse_staff_of": gym_id}})
        user = getattr(res, "user", None)
    except Exception as error:
        text = str(error).lower()
        if "already" in text or "registered" in text or "exists" in text:
            return False, ("That email already has a GymPulse AI login, so it can't be added as staff. "
                           "Use a different email (e.g. a work email)."), None
        return False, f"Could not create the login: {error}", None
    try:
        sc.table("gym_staff").insert({"gym_id": gym_id, "user_id": str(user.id), "email": email,
                                      "full_name": name.strip()}).execute()
    except Exception as error:
        try:
            sc.auth.admin.delete_user(str(user.id))
        except Exception:
            pass
        return False, f"{SQL_HINT} ({error})", None
    sent = _send_invite(name, email, password, gym_name, owner_name)
    return True, (f"{name} can now sign in. " + ("We've emailed them their login." if sent else
                                                 "Share the login below with them.")), password


def set_status(gym_id, row, status):
    sc = _service()
    sc.table("gym_staff").update({"status": status}).eq("id", row["id"]).eq("gym_id", gym_id).execute()


def remove_staff(gym_id, row):
    sc = _service()
    if row.get("user_id"):
        try:
            sc.auth.admin.delete_user(row["user_id"])        # also removes the gym_staff row (cascade)
        except Exception:
            pass
    sc.table("gym_staff").delete().eq("id", row["id"]).eq("gym_id", gym_id).execute()


def render_team(supabase, gym_id):
    profile = st.session_state.get("user_profile") or {}
    rows = load_staff(supabase, gym_id)
    if rows is None:
        st.info(SQL_HINT)
        return
    gw.intro("Team & access", ":material/badge:", "Give your team their own login. Staff can run the gym day to day, while business numbers, "
               "billing and settings stay with you.")
    c1, c2 = st.columns(2)
    with c1.container(border=True):
        st.markdown("**Staff can use**")
        st.markdown("\n".join(f"- {x}" for x in STAFF_CAN))
    with c2.container(border=True):
        st.markdown("**Only you (the owner)**")
        st.markdown("\n".join(f"- {x}" for x in OWNER_ONLY_LIST))

    st.markdown('<div class="section-label">YOUR TEAM</div>', unsafe_allow_html=True)
    gw.table([{"Name": r.get("full_name") or "–", "Email": r.get("email"),
               "Access": "Active" if r.get("status") == "active" else "Off",
               "Added": str(r.get("created_at"))[:10],
               "Last seen": str(r.get("last_seen_at") or "")[:16].replace("T", " ") or "Not yet"} for r in rows],
             pills={"Access": {"Active": "lime", "Off": "grey"}},
             empty="No staff yet. Add your first team member below.")

    new_pw = st.session_state.pop("team_new_pw", None)
    if new_pw:
        st.success(new_pw[0])
        st.code(f"Sign in at usegympulseai.com\nEmail: {new_pw[1]}\nTemporary password: {new_pw[2]}", language=None)
        st.caption("This password is shown once. They should change it after signing in.")

    with st.expander("Add a staff member", expanded=not rows):
        with st.form("team_add", clear_on_submit=True):
            a1, a2 = st.columns(2)
            name = a1.text_input("Full name", placeholder="e.g. Ada Obi")
            email = a2.text_input("Email", placeholder="ada@example.com")
            go = st.form_submit_button("Add and send their login", type="primary")
        if go:
            if not name.strip() or "@" not in email:
                st.error("Please enter their name and email.")
            else:
                ok, msg, pw = add_staff(gym_id, name, email, profile.get("business_name") or "your gym",
                                        profile.get("full_name"))
                if ok:
                    st.session_state["team_new_pw"] = (msg, email.strip().lower(), pw)
                    st.rerun()
                st.error(msg)

    if rows:
        st.markdown('<div class="section-label">MANAGE ACCESS</div>', unsafe_allow_html=True)
        pick = st.selectbox("Team member", range(len(rows)), key="team_pick", label_visibility="collapsed",
                            format_func=lambda i: f"{rows[i].get('full_name') or rows[i]['email']} · {rows[i]['email']}")
        r = rows[pick]
        b1, b2, b3 = st.columns(3)
        active = r.get("status") == "active"
        if b1.button("Turn access off" if active else "Turn access on", use_container_width=True, key="team_toggle"):
            set_status(gym_id, r, "disabled" if active else "active")
            st.session_state["team_flash"] = f"{r.get('full_name')}'s access is {'off' if active else 'on'}."
            st.rerun()
        if b2.button("Send password reset", use_container_width=True, key="team_reset"):
            try:
                _service().auth.reset_password_for_email(r["email"])
                st.session_state["team_flash"] = f"Password reset email sent to {r['email']}."
            except Exception as error:
                st.session_state["team_flash"] = f"Could not send the reset: {error}"
            st.rerun()
        if b3.button("Remove from team", use_container_width=True, key="team_remove"):
            st.session_state["team_confirm"] = r["id"]
        if st.session_state.get("team_confirm") == r["id"]:
            st.warning(f"Remove {r.get('full_name')}? Their login is deleted. Members and records they added stay.")
            if st.button("Yes, remove", type="primary", key="team_remove_yes"):
                remove_staff(gym_id, r)
                st.session_state.pop("team_confirm", None)
                st.session_state["team_flash"] = f"{r.get('full_name')} was removed."
                st.rerun()
    flash = st.session_state.pop("team_flash", None)
    if flash:
        st.toast(flash)


# ------------------------------------------------------------------ the Owner page
OWNER_SECTIONS = ["Business insights", "Team & access", "Monthly report", "Subscription & billing"]


def render_owner_hub(supabase, gym_id, assess_fn, owner_id):
    import gympulse_billing as gbill
    import gympulse_grow as gg
    gw.page_header("Owner", "Your business at a glance: numbers, team, reports and billing.", "Owner only")
    if "owner_section" not in st.session_state:
        st.session_state["owner_section"] = st.session_state.get("_owner_last", OWNER_SECTIONS[0])
    section = st.segmented_control("Owner section", OWNER_SECTIONS, key="owner_section",
                                   label_visibility="collapsed") or OWNER_SECTIONS[0]
    st.session_state["_owner_last"] = section
    if section == "Business insights":
        gw.render_business_insights(supabase, gym_id, assess_fn, header=False)
    elif section == "Team & access":
        render_team(supabase, gym_id)
    elif section == "Monthly report":
        gg.render_monthly(supabase, gym_id, assess_fn, owner_id)
    else:
        s = gbill.state(gbill.subscription(supabase, gym_id))
        sub = gbill.subscription(supabase, gym_id) or {}
        status = {"trial": "Free trial", "active": "Active", "free": "Free access", "expired": "Ended",
                  "off": "Not switched on"}[s["status"]]
        gw.kpi_row([("Plan", gw._text(sub.get("plan"), status), "lime", status),
                    ({"trial": "Trial ends", "active": "Renews"}.get(s["status"], "Ends"),
                     f"{s['ends']:%d %b %Y}" if s.get("ends") else "–", "cyan", "")])
        st.button("Manage subscription, payments and receipts", type="primary", icon=":material/credit_card:",
                  on_click=gw._go, args=("Subscription",))


# ------------------------------------------------------------------ settings for staff
def render_staff_settings(supabase, user_id, log_out):
    gw.page_header("Settings", "Your login and preferences.", "Account")
    flash = st.session_state.pop("settings_flash", None)
    if flash:
        st.success(flash)
    me = st.session_state.get("staff") or {}
    gw._md(f'<div class="profile-hero">{gw.avatar_html(staff_name(), None, 72, "avatar-ring")}<div>'
           f'<div class="profile-name">{gw._esc(staff_name())}</div><div class="chip-row">'
           f'{gw.chip("Staff", "cyan")}{gw.chip((st.session_state.get("user_profile") or {}).get("business_name") or "", "grey")}'
           f'{gw.chip(me.get("email") or "", "grey")}</div></div></div>')
    with st.form("staff_pw"):
        st.markdown("**Change your password**")
        p1 = st.text_input("New password", type="password")
        p2 = st.text_input("Type it again", type="password")
        if st.form_submit_button("Save new password", type="primary"):
            if len(p1) < 8:
                st.error("Use at least 8 characters.")
            elif p1 != p2:
                st.error("The two passwords don't match.")
            else:
                try:
                    supabase.auth.update_user({"password": p1})
                    st.session_state["settings_flash"] = "Password changed."
                    st.rerun()
                except Exception as error:
                    st.error(f"Could not change it: {error}")
    st.caption("Gym settings (branding, payment details, automation) are managed by the gym owner.")
    st.button("Sign out", on_click=log_out, icon=":material/logout:")


def touch_last_seen():
    """Record when a staff member was last in (once per session)."""
    if st.session_state.get("_seen_done") or not is_staff():
        return
    st.session_state["_seen_done"] = True
    try:
        sc = _service()
        sid = (st.session_state.get("staff") or {}).get("id")
        if sc and sid:
            sc.table("gym_staff").update({"last_seen_at": datetime.now(timezone.utc).isoformat()}).eq("id", sid).execute()
    except Exception:
        pass
