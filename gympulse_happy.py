"""GymPulse AI · Member happiness check.

Every 3 months (or every month), members get a one-question email:
"How happy are you with <gym>?" with four buttons. One tap records the answer
on a small public page (no sign-in), where they can add a comment. Unhappy
answers are emailed to the gym owner straight away, so they can fix things
before the member quits. Answers: member_feedback (sql/phase11_happiness.sql).
"""
from datetime import date

import pandas as pd
import streamlit as st

import gympulse_workspaces as gw

SQL_HINT = ("This needs a one-time setup: open Supabase, go to SQL Editor, paste in the file "
            "sql/phase11_happiness.sql and press Run.")
SCORES = {4: ("😍", "Love it"), 3: ("🙂", "Happy"), 2: ("😐", "It's okay"), 1: ("😞", "Not happy")}


def round_for(today, freq="quarter"):
    return f"{today:%Y-%m}" if freq == "month" else f"{today.year}-Q{(today.month - 1) // 3 + 1}"


def round_label(r):
    if "-Q" in r:
        y, q = r.split("-Q")
        return f"{['Jan–Mar', 'Apr–Jun', 'Jul–Sep', 'Oct–Dec'][int(q) - 1]} {y}"
    try:
        return date.fromisoformat(r + "-01").strftime("%B %Y")
    except Exception:
        return r


def link(token, rnd, score):
    return f"{gw.APP_URL}/?fb={token}&r={rnd}&s={score}"


def pulse_letter(m, token, rnd):
    import gympulse_grow as gg
    biz, owner = gg._biz()
    first = gg._first(m.get("full_name"))
    subject = f"{first}, how are we doing at {biz}?"
    body = (f"Hi {first},\n\nOne quick question, and it takes a single tap: how happy are you with {biz} at the "
            "moment?\n\nYour honest answer goes straight to us and helps us make the gym better for you.\n\n"
            f"Thank you,\n{owner}\n{biz}")
    buttons = [(f"{e} {label}", link(token, rnd, s)) for s, (e, label) in SCORES.items()]
    return subject, body, buttons


# ------------------------------------------------------------------ the public page
def _tell_owner(gym_id, gym_name, member, score, comment):
    """Email the gym owner about an unhappy answer (server key + Resend)."""
    import requests
    import gympulse_admin as gadm
    sc, key = gadm.service_client(), gadm._env("RESEND_API_KEY")
    if not (sc and key):
        return
    try:
        g = sc.table("gyms").select("owner_id").eq("id", gym_id).limit(1).execute().data
        user = getattr(sc.auth.admin.get_user_by_id(g[0]["owner_id"]), "user", None) if g else None
        to = getattr(user, "email", "") if user else ""
        if "@" not in (to or ""):
            return
        e, label = SCORES[score]
        text = (f"{member} just answered your GymPulse happiness check: {label}.\n\n"
                + (f"What they said: \"{comment}\"\n\n" if comment else "They didn't leave a comment.\n\n")
                + "A quick, personal message from you today can turn this around. "
                  "See all answers in GymPulse AI → Grow → Happiness.\n\nGymPulse AI")
        requests.post("https://api.resend.com/emails", timeout=20, headers={"Authorization": f"Bearer {key}"},
                      json={"from": gadm._env("REPORTS_FROM", gadm.REPORTS_FROM_DEFAULT), "to": [to],
                            "subject": f"{gym_name}: {member} isn't happy", "text": text})
    except Exception as error:
        try:
            import gympulse_monitoring as gmon
            gmon.capture(error, "happiness owner email")
        except Exception:
            pass


def _save(supabase, token, rnd, score, comment=None):
    try:
        rows = supabase.rpc("gp_member_feedback", {"p_token": str(token), "p_round": rnd, "p_score": int(score),
                                                    "p_comment": comment}).execute().data or []
    except Exception:
        return None
    return rows[0] if isinstance(rows, list) and rows else (rows or None)


def render_public(supabase, params):
    """?fb=<member link code>&r=<round>&s=<1-4>: save the answer, thank them, invite a comment."""
    import gympulse_booking as gb
    gb._header()
    token, rnd = params.get("fb"), params.get("r", "")
    try:
        score = int(params.get("s", 0))
    except ValueError:
        score = 0
    col = gw.center("happy", 720)
    with col:
        if score not in SCORES:
            st.error("This link isn't complete. Please tap one of the faces in the email again.")
            return
        key = f"fb_saved_{token}_{rnd}"
        if key not in st.session_state:
            r = _save(supabase, token, rnd, score)
            if not r:
                st.error("This link isn't valid any more. Just reply to the email instead, thank you!")
                return
            st.session_state[key] = r
            if score <= 2:
                _tell_owner(r["gym_id"], r.get("business_name") or "Your gym", r.get("member_name") or "A member",
                            score, None)
        r = st.session_state[key]
        biz = r.get("business_name") or "the gym"
        e, label = SCORES[score]
        gw._md(f'<div class="bk-title">{e} Thank you!</div>'
               f'<div class="bk-sub">We\'ve saved your answer for {gw._esc(biz)}: <b>{label}</b>.</div>')
        if st.session_state.get(key + "_c"):
            st.success("Thanks for telling us. The team will read it.")
            return
        with st.form("fb_comment"):
            prompt = ("What's one thing we could do better?" if score <= 2 else
                      "Anything we could do even better? (optional)")
            text = st.text_area(prompt, max_chars=1000)
            if st.form_submit_button("Send", type="primary") and text.strip():
                _save(supabase, token, rnd, score, text.strip())
                if score <= 2:
                    _tell_owner(r["gym_id"], biz, r.get("member_name") or "A member", score, text.strip())
                st.session_state[key + "_c"] = True
                st.rerun()


# ------------------------------------------------------------------ the owner's view
def load(supabase, gym_id):
    try:
        return pd.DataFrame(supabase.table("member_feedback").select("*").eq("gym_id", gym_id)
                            .order("created_at", desc=True).execute().data or [])
    except Exception:
        return None


def render_happiness(supabase, gym_id):
    import gympulse_grow as gg
    import gympulse_loyalty as gl
    gw.intro("Member happiness", ":material/sentiment_satisfied:", "A one-tap question by email: \"How happy are you with the gym?\" Unhappy answers are emailed to you "
               "straight away, so you can fix things before a member quits. Switch it on in Automatic messages.")
    if not gl.auto_cfg()["pulse"]["on"]:
        st.info("The happiness check is off. Turn it on in Grow → Automatic messages.")
    df = load(supabase, gym_id)
    if df is None:
        st.info(SQL_HINT)
        return
    if not df.empty:
        df["comment"] = df["comment"].apply(lambda x: "" if x is None or (isinstance(x, float) and x != x) else str(x))
    if df.empty:
        st.info("No answers yet. They appear here as members reply.")
        return
    names = {r["id"]: r for _, r in gg._members(supabase, gym_id).iterrows()}
    rounds = sorted(df["round"].unique(), reverse=True)
    cur = df[df["round"] == rounds[0]]
    happy = (cur["score"] >= 3).mean() * 100
    gw.kpi_row([("Happy or love it", f"{happy:.0f}%", "lime", round_label(rounds[0])),
                ("Answers", str(len(cur)), "cyan", round_label(rounds[0])),
                ("Not happy or just okay", str(int((cur["score"] <= 2).sum())), "red", "reach out to them"),
                ("Comments", str(int(cur["comment"].fillna("").astype(str).str.len().gt(0).sum())), "grey", "")])
    unhappy = cur[cur["score"] <= 2]
    if len(unhappy):
        st.markdown('<div class="section-label">REACH OUT TO THESE MEMBERS</div>', unsafe_allow_html=True)
        for _, r in unhappy.iterrows():
            m = names.get(r["member_id"], {})
            name = gw._text(m.get("full_name") if hasattr(m, "get") else None, "Member")
            e, label = SCORES[int(r["score"])]
            with st.expander(f"{e} {name} · {label}", expanded=bool(r["comment"])):
                if r["comment"]:
                    st.markdown(f"> {gw._esc(r['comment'])}")
                msg = (f"Hi {gg._first(name)}, thank you for your honest answer. I'm sorry the gym hasn't been "
                       "great for you lately. Could you tell me a bit more? I'd really like to put it right. "
                       f"\n{gg._biz()[1]}")
                c1, c2 = st.columns(2)
                c1.link_button("Message on WhatsApp", gg.wa_url(m.get("phone") if hasattr(m, "get") else "", msg),
                               icon=":material/chat:", use_container_width=True)
                c2.button("Open profile", key=f"hp_prof_{r['member_id']}", icon=":material/person:",
                          use_container_width=True, on_click=gw.open_profile, args=(r["member_id"], "Grow"))
    comments = cur[cur["comment"].fillna("").astype(str).str.len() > 0]
    if len(comments):
        with st.expander(f"All comments ({len(comments)})"):
            for _, r in comments.iterrows():
                m = names.get(r["member_id"], {})
                st.markdown(f"{SCORES[int(r['score'])][0]} **{gw._esc(gw._text(m.get('full_name') if hasattr(m, 'get') else None, 'Member'))}:** "
                            f"{gw._esc(r['comment'])}")
    if len(rounds) > 1:
        trend = df.groupby("round")["score"].apply(lambda s: round((s >= 3).mean() * 100)).sort_index()
        st.markdown("**Happy members over time**")
        gw.table(pd.DataFrame({"Period": [round_label(r) for r in trend.index],
                               "Happy or love it": [f"{v}%" for v in trend.values],
                               "Answers": df.groupby("round").size().sort_index().values}))
