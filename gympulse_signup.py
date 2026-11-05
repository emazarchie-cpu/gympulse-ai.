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
    _, col, _ = st.columns([1, 2.2, 1])
    with col:
        try:
            info = supabase.rpc("gp_join_info", {"p_code": str(code)}).execute().data or []
        except Exception:
            info = []
        gym = (info[0] if isinstance(info, list) and info else {}).get("business_name") if info else None
        if not gym:
            st.error("This sign-up link isn't active. Please ask your gym for a new one.")
            return
        done = st.session_state.pop("join_done", None)      # shown once: the next visit starts a fresh form
        if done and st.session_state.pop("join_done_code", None) != str(code):
            done = None
        if done:
            if done == "created":
                gw._md(f'<div class="bk-title">You\'re in! 🎉</div><div class="bk-sub">Welcome to '
                       f'{gw._esc(gym)}. See you at the gym!</div>')
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
                if not r or r.get("status") not in ("created", "exists"):
                    import gympulse_monitoring as gmon
                    gmon.capture(RuntimeError(f"member sign-up link failed: {problem or rows}"), "member sign-up")
                    st.error("Sorry, your details couldn't be saved. Please try again, or ask the front desk."
                             + (f" (Details for the gym: {problem[:160]})" if problem else ""))
                else:
                    st.session_state["join_done"] = r["status"]
                    st.session_state["join_done_code"] = str(code)
                    st.rerun()


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
    try:
        rows = gw.fetch_all(supabase.table("members").select("full_name, phone, email, created_at")
                            .eq("gym_id", gym_id).eq("joined_via", "link").order("created_at", desc=True))
    except Exception:
        rows = []
    st.markdown('<div class="section-label">SIGNED UP THROUGH THE LINK</div>', unsafe_allow_html=True)
    gw.table([{"Member": r["full_name"], "Phone": r.get("phone") or "–", "Email": r.get("email") or "–",
               "Joined": str(r.get("created_at"))[:10]} for r in rows[:50]],
             empty="No sign-ups yet. Share your link to get started.",
             caption=(f"{len(rows)} member{'s' if len(rows) != 1 else ''} so far. Add their plan and end date on the "
                      "Risk Radar (members without a plan are listed there), or import plans from your old system."
                      if rows else None))
