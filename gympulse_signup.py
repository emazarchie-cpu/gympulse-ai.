"""GymPulse AI · Member sign-up link.

The gym shares usegympulseai.com/?join=<code> on WhatsApp or as a QR code at the
front desk. Members fill in their own name, phone, email, goal and age, agree to
the gym storing their details, and appear in the gym's member list (marked
"joined via link"). The owner adds their plan afterwards, or imports plans from
their old system. Database: sql/phase14_member_signup.sql (+ phase15 for the
optional photo).
"""
import io
import secrets

import pandas as pd
import streamlit as st

import gympulse_workspaces as gw

GOALS = ["Weight loss", "Muscle gain", "General fitness", "Strength", "Endurance", "Sports performance"]
SQL_HINT = ("The sign-up link needs a one-time setup: open Supabase, go to SQL Editor, paste in the file "
            "sql/phase14_member_signup.sql and press Run.")


def link_for(code):
    return f"{gw.APP_URL}/?join={code}"


# ------------------------------------------------------------------ public page
def render_public(supabase, code):
    import gympulse_booking as gb
    gb._header()
    col = gw.center("signup", 640)
    with col:
        try:
            info = supabase.rpc("gp_join_info", {"p_code": str(code)}).execute().data or []
        except Exception:
            info = []
        gym = (info[0] if isinstance(info, list) and info else {}).get("business_name") if info else None
        if not gym:
            st.error("This sign-up link isn't active. Please ask your gym for a new one.")
            return
        import gympulse_billing as gbill
        if gbill.gym_locked(gbill.gym_by("gyms", "join_code", code)):
            gbill.render_gym_locked(gym)
            return
        done = st.session_state.pop("join_done", None)      # shown once: the next visit starts a fresh form
        if done and st.session_state.pop("join_done_code", None) != str(code):
            done = None
        if done:
            if done == "created":
                gw._md(f'<div class="bk-title">You\'re in! 🎉</div><div class="bk-sub">Welcome to '
                       f'{gw._esc(gym)}. One last step: please sign your membership agreement.</div>')
                link = _waiver_link(code, st.session_state.pop("join_contact", None))
                if link:
                    st.link_button("Sign my membership agreement", link, type="primary",
                                   icon=":material/draw:", use_container_width=True)
                else:
                    st.caption("The front desk will ask you to sign your membership agreement on your first visit.")
            else:
                gw._md(f'<div class="bk-title">You\'re already a member 👋</div><div class="bk-sub">'
                       f'{gw._esc(gym)} already has a member with this phone number or email, so nothing new '
                       'was added. If your details have changed, let the front desk know.</div>')
            return
        gw._md(f'<div class="bk-title">Join {gw._esc(gym)}</div>'
               '<div class="bk-sub">Add your details so the team can keep track of your membership and help you '
               'reach your goal. It takes 30 seconds.</div>')
        with st.form("join_form"):
            name = st.text_input("Full name")
            c1, c2 = st.columns(2)
            phone = c1.text_input("Phone (WhatsApp)", placeholder="e.g. 0803 000 0000")
            email = c2.text_input("Email (optional)")
            c3, c4 = st.columns(2)
            goal = c3.selectbox("Your main goal", GOALS, index=2)
            age = c4.number_input("Age (optional)", min_value=0, max_value=110, value=0, step=1)
            photo = st.file_uploader("Your photo (optional, helps the front desk greet you)",
                                     type=["jpg", "jpeg", "png", "webp", "heic", "heif"])
            consent = st.checkbox(f"I agree that {gym} can store my details and contact me about my membership. "
                                  "They are kept private, never sold, and I can ask for them to be deleted.")
            go = st.form_submit_button("Join", type="primary", use_container_width=True)
        if go:
            digits = "".join(ch for ch in phone if ch.isdigit())
            if len(name.strip()) < 2:
                st.error("Please enter your full name.")
            elif len(digits) < 7 and "@" not in email:
                st.error("Please add your phone number (or an email).")
            elif not consent:
                st.error("Please tick the box to agree, so the gym can keep your details.")
            else:
                args = {"p_code": str(code), "p_name": name.strip(), "p_phone": phone.strip(),
                        "p_email": email.strip(), "p_goal": goal, "p_age": int(age) or None, "p_consent": True}
                pic = None
                if photo is not None:
                    try:
                        pic = gw.process_photo(photo.getvalue())
                    except Exception:
                        pic = None
                rows, problem = [], ""
                try:
                    if pic:
                        rows = supabase.rpc("gp_member_join", {**args, "p_photo": pic}).execute().data or []
                except Exception:
                    rows = []                    # photo step not set up yet: join without it
                if not rows:
                    try:
                        rows = supabase.rpc("gp_member_join", args).execute().data or []
                    except Exception as error:
                        rows, problem = [], str(error)
                r = rows[0] if isinstance(rows, list) and rows else None
                if "GP_MEMBER_LIMIT" in problem:       # the gym's plan is full: not the member's fault
                    st.warning("The gym can't take new sign-ups online right now. Please see the front desk "
                               "and they'll add you.")
                elif not r or r.get("status") not in ("created", "exists"):
                    import gympulse_monitoring as gmon
                    gmon.capture(RuntimeError(f"member sign-up link failed: {problem or rows}"), "member sign-up")
                    st.error("Sorry, your details couldn't be saved. Please try again, or ask the front desk."
                             + (f" (Details for the gym: {problem[:160]})" if problem else ""))
                else:
                    if r.get("status") == "created" and st.query_params.get("ref"):
                        import gympulse_referrals as gref          # invited by a member: credit them
                        gref.record_from_signup(supabase, code, st.query_params.get("ref"), name.strip(),
                                                phone.strip(), email.strip())
                    st.session_state["join_done"] = r["status"]
                    st.session_state["join_contact"] = (phone.strip(), email.strip())
                    st.session_state["join_done_code"] = str(code)
                    st.rerun()


def _waiver_link(code, contact):
    """The new member's personal signing link (found by the phone or email they just gave), or None."""
    if not contact:
        return None
    try:
        import gympulse_admin as gadm
        sc = gadm.service_client()
        g = sc.table("gyms").select("id").eq("join_code", str(code)).limit(1).execute().data
        rows = sc.table("members").select("portal_token, phone, email, created_at").eq("gym_id", g[0]["id"]) \
            .order("created_at", desc=True).limit(50).execute().data or []
    except Exception:
        return None
    phone, email = contact
    digits = "".join(ch for ch in phone or "" if ch.isdigit())[-10:]
    for r in rows:
        r_digits = "".join(ch for ch in gw._text(r.get("phone")) if ch.isdigit())[-10:]
        if (len(digits) >= 7 and r_digits == digits) or (email and gw._text(r.get("email")).lower() == email.lower()):
            if r.get("portal_token"):
                return f"{gw.APP_URL}/?waiver={r['portal_token']}"
    return None


# ------------------------------------------------------------------ owner tools
def _gym(supabase, gym_id):
    try:
        rows = supabase.table("gyms").select("id, business_name, join_code, join_enabled").eq("id", gym_id) \
            .limit(1).execute().data or []
        return rows[0] if rows else None
    except Exception:
        return None


def _qr_png(url):
    import qrcode
    img = qrcode.make(url, box_size=12, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def render_owner(supabase, gym_id):
    import gympulse_reports as rp
    gw.intro("Member sign-up link", ":material/qr_code_2:",
             "Share one link or QR code and let members add their own details: perfect when your members are on "
             "paper or a WhatsApp list. New sign-ups appear in your member list straight away.")
    g = _gym(supabase, gym_id)
    if not g or "join_code" not in g or not g.get("join_code"):
        st.info(SQL_HINT)
        return
    if st.session_state.get("role") == "staff":
        st.caption("Only the gym owner can switch the link off or make a new one.")
    import gympulse_billing as gbill
    _ok, _why = gbill.can_add_members(supabase, gym_id)
    if not _ok:
        st.warning(_why + " Switch the sign-up link off until you upgrade, so new members aren't left waiting.")
    url = link_for(g["join_code"])
    on = bool(g.get("join_enabled", True))
    c1, c2 = st.columns([2, 1])
    with c1:
        st.markdown("**Your link**")
        st.code(url, language=None)
        msg = (f"Hi everyone 👋 We're moving our member records to GymPulse AI so we can serve you better "
               f"(renewal reminders, progress updates and rewards). Please take 30 seconds to add your details "
               f"here: {url}\nThank you! {g.get('business_name') or ''}")
        st.markdown("**Message for your members' WhatsApp group**")
        st.code(msg, language=None, wrap_lines=True)
        if st.session_state.get("role") != "staff":
            b1, b2 = st.columns(2)
            if b1.button("Switch the link off" if on else "Switch the link on", use_container_width=True,
                         key="join_toggle"):
                supabase.table("gyms").update({"join_enabled": not on}).eq("id", gym_id).execute()
                st.rerun()
            if b2.button("Make a new link", use_container_width=True, key="join_new",
                         help="The old link stops working. Use this if the link was shared somewhere it shouldn't be."):
                supabase.table("gyms").update({"join_code": secrets.token_hex(5)}).eq("id", gym_id).execute()
                st.rerun()
        if not on:
            st.warning("The link is switched off: members who open it see that it isn't active.")
    with c2:
        png = _qr_png(url)
        st.image(png, caption="Print this for your front desk", use_container_width=True)
        rp.download_link("Download QR code", png, "gympulse-member-signup-qr.png", "image/png", "join_qr")
    _render_signups(supabase, gym_id)


def _ago(stamp):
    t = pd.to_datetime(stamp, errors="coerce", utc=True)
    if pd.isna(t):
        return ""
    days = (gw.today_local() - t.tz_convert(gw.APP_TZ).date()).days
    return "today" if days <= 0 else "yesterday" if days == 1 else f"{days} days ago"


def _render_signups(supabase, gym_id):
    """Members who joined through the link: photo, name (opens their profile), contact, when, plan."""
    try:
        rows = gw.fetch_all(supabase.table("members").select("id, full_name, phone, email, photo, created_at")
                            .eq("gym_id", gym_id).eq("joined_via", "link").order("created_at", desc=True))
    except Exception:
        rows = []
    st.markdown('<div class="section-label">SIGNED UP THROUGH THE LINK</div>', unsafe_allow_html=True)
    if not rows:
        st.caption("No sign-ups yet. Share your link to get started.")
        return
    try:
        acts = supabase.table("member_activity").select("member_id, membership_type").eq("gym_id", gym_id) \
            .in_("member_id", [r["id"] for r in rows[:200]]).execute().data or []
        has_plan = {x["member_id"] for x in acts if x.get("membership_type")}
    except Exception:
        has_plan = set()
    no_plan = sum(1 for r in rows if r["id"] not in has_plan)
    st.caption(f"{len(rows)} member{'s' if len(rows) != 1 else ''} so far"
               + (f", {no_plan} still need a plan. Tap a name to open their profile and add it." if no_plan else
                  ". Tap a name to open their profile."))
    limit = st.session_state.get("join_list_limit", 10)
    with st.container(border=True, key="card_join_list"):
        for r in rows[:limit]:
            a, b, c = st.columns([0.7, 4.3, 2], vertical_alignment="center")
            gw._md(gw.avatar_html(r["full_name"], r.get("photo"), 44, "row-tight"), a)
            with b:
                st.button(str(r["full_name"]), key=f"join_open_{r['id']}", type="tertiary",
                          on_click=gw.open_profile, args=(r["id"], "Member Management"))
                contact = " · ".join(x for x in (gw._text(r.get("phone")), gw._text(r.get("email"))) if x)
                gw._md(f'<div class="why" style="padding:0 0 6px;margin-top:-14px">{gw._esc(contact or "No contact details")}'
                       f' · joined {_ago(r.get("created_at"))}</div>')
            gw._md(gw.chip("Plan added", "lime") if r["id"] in has_plan else gw.chip("Needs a plan", "amber"), c)
    if len(rows) > limit:
        st.button(f"Show more ({len(rows) - limit} left)", type="tertiary", key="join_more",
                  on_click=lambda: st.session_state.update(join_list_limit=limit + 10))
