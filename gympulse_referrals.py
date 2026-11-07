"""GymPulse AI · Automatic bring-a-friend.

* Every member has a personal invite link: usegympulseai.com/?join=<gym code>&ref=<member code>. It's on their
  member app (with a WhatsApp share button) and in the "bring a friend" emails.
* A friend who signs up through it is recorded straight away against the member who invited them
  (sql/phase28_referrals_hmo.sql, gp_referral_link). Nobody types anything.
* The owner approves every reward in one tap. When the reward is free time ("1 free week", "10 free days",
  "1 free month"), the days are added to the member's membership automatically and they get a thank-you.
* "Ask everyone": one tap emails active members their own invite link (100 at a time, never the same month twice).
"""
import re
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

import gympulse_workspaces as gw

ASK_BATCH = 100


def reward_days(text):
    """Free days in a reward like '1 free week', '10 free days', '1 free month' (0 if it isn't free time)."""
    t = gw._text(text).lower()
    m = re.search(r"(\d+|a|one|two|three)\s*(?:free\s*)?(day|week|month)s?", t)
    if not m or "free" not in t:
        return 0
    n = {"a": 1, "one": 1, "two": 2, "three": 3}.get(m.group(1)) or int(m.group(1))
    return n * {"day": 1, "week": 7, "month": 30}[m.group(2)]


def invite_link(join_code, member_id):
    return f"{gw.APP_URL}/?join={join_code}&ref={gw.member_code(member_id)}"


def record_from_signup(supabase, code, ref, name, phone, email):
    """Called by the sign-up page when a friend joins through a member's link."""
    if not ref:
        return None
    try:
        return supabase.rpc("gp_referral_link", {"p_code": str(code), "p_ref": str(ref)[:8], "p_name": name,
                                                 "p_phone": phone, "p_email": email or None}).execute().data
    except Exception:
        return None                                   # phase 28 not run yet: the friend still joins


def invite_text(first, gym, reward, link):
    return (f"Hi! {first} here 👋 I train at {gym} and I think you'd love it. Join with my link and we can "
            f"train together 💪 {link}")


# ------------------------------------------------------------------ member app card
def render_member_card(sc, m, gym_name, profile):
    try:
        g = sc.table("gyms").select("join_code, join_enabled").eq("id", m["gym_id"]).limit(1).execute().data or []
    except Exception:
        return
    if not g or not g[0].get("join_code") or g[0].get("join_enabled") is False:
        return
    reward = dict((profile or {}).get("settings") or {}).get("referral_reward") or "1 free week"
    link = invite_link(g[0]["join_code"], m["id"])
    first = gw._text(m.get("full_name"), "A friend").split()[0]
    from urllib.parse import quote
    with st.container(border=True, key="mp_invite"):
        gw._md(f'<div style="font-weight:800;font-size:16px">Bring a friend 🎁</div>'
               f'<div class="why">When a friend joins {gw._esc(gym_name)} with your link, you get '
               f'<b>{gw._esc(reward)}</b>. They\'re added to your name automatically.</div>')
        st.link_button("Share on WhatsApp", f"https://wa.me/?text={quote(invite_text(first, gym_name, reward, link))}",
                       icon=":material/share:", use_container_width=True, type="primary")
        st.code(link, language=None)


# ------------------------------------------------------------------ owner: the automatic part of Referrals
def render_owner_auto(supabase, gym_id, rows, df, names, reward, biz):
    """Top of Grow → Referrals: how it runs itself, rewards to approve in one tap, and ask everyone."""
    import gympulse_signup as gsign
    g = gsign._gym(supabase, gym_id) or {}
    code = g.get("join_code")
    days = reward_days(reward)
    with st.container(border=True, key="ref_auto"):
        gw._md('<div style="font-weight:800;font-size:16px">Runs by itself</div><div class="why">Every member has '
               'their own invite link in their member app. When a friend signs up with it, the referral is recorded '
               'here automatically. You only approve the rewards.'
               + (f' Rewards of free time (<b>{days} days</b>) are added to the member\'s membership for you.'
                  if days else ' Tip: make the reward free time, e.g. "1 free week", and GymPulse adds it for you.')
               + '</div>')
        if not code:
            st.caption("Switch on the member sign-up link (Member Management) to give every member an invite link.")
    owed = [r for r in rows if r.get("status") == "joined"]
    if owed:
        if st.button(f"Approve {len(owed)} reward{'s' if len(owed) != 1 else ''}"
                     + (f" (+{days} days each)" if days else ""), type="primary", icon=":material/redeem:",
                     key="ref_approve_all", use_container_width=True):
            n, extended = approve_all(supabase, gym_id, owed, df, reward, biz)
            st.session_state["grow_flash"] = (f"{n} reward{'s' if n != 1 else ''} approved"
                                              + (f", {extended} membership{'s' if extended != 1 else ''} extended by "
                                                 f"{days} days" if extended else "") + ". Members were thanked.")
            st.rerun()
    if code:
        _ask_everyone(supabase, gym_id, df, code, reward, biz)
    auto = sum(1 for r in rows if r.get("source") == "link")
    if auto:
        st.caption(f"{auto} referral{'s' if auto != 1 else ''} recorded automatically from invite links.")


def approve_all(supabase, gym_id, owed, df, reward, biz):
    import gympulse_campaigns as gcamp
    days = reward_days(reward)
    by_id = {r["id"]: r for r in df.to_dict("records")} if not df.empty else {}
    today = gw.today_local()
    n = extended = 0
    for r in owed:
        m = by_id.get(r.get("referrer_id"))
        try:
            if days and m is not None:
                end = pd.to_datetime(m.get("membership_end"), errors="coerce")
                base = max(today, end.date()) if not pd.isna(end) else today
                new_end = base + timedelta(days=days)
                supabase.table("members").update({"membership_end": new_end.isoformat()}).eq("id", m["id"]).execute()
                m["membership_end"] = new_end.isoformat()          # two friends: add both rewards
                extended += 1
            supabase.table("referrals").update({"status": "rewarded", "reward": r.get("reward") or reward,
                                                "rewarded_at": datetime.now(timezone.utc).isoformat()}) \
                .eq("id", r["id"]).execute()
            n += 1
        except Exception:
            continue
        if m is not None and "@" in gw._text(m.get("email")) and gcamp.ready():
            first = gw._text(m.get("full_name"), "there").split()[0]
            body = (f"Hi {first}! 🎁 {r.get('friend_name') or 'Your friend'} just joined {biz} thanks to you. "
                    + (f"We've added {days} free days to your membership. " if days else f"Your reward: {reward}. ")
                    + "Thank you for bringing them along! 🙏")
            try:
                gcamp.email_member(supabase, gym_id, m, "Thank you for bringing a friend", body)
                time.sleep(0.55)
            except Exception:
                pass
    gw.bump_data_version()
    return n, extended


def _ask_everyone(supabase, gym_id, df, code, reward, biz):
    """Email active members their own invite link, 100 at a time, once a month each."""
    import gympulse_campaigns as gcamp
    import gympulse_loyalty as gl
    if df.empty:
        return
    today = gw.today_local()
    ref = f"refask:{today:%Y-%m}"
    try:
        done = {r["member_id"] for r in (supabase.table("auto_messages").select("member_id").eq("gym_id", gym_id)
                                         .eq("kind", "refask").eq("ref", ref).execute().data or [])}
    except Exception:
        done = set()
    end = pd.to_datetime(df.get("membership_end"), errors="coerce")
    active = df[(end.dt.date >= today).fillna(False)] if "membership_end" in df.columns else df
    todo = [m for m in active.to_dict("records") if "@" in gw._text(m.get("email")) and m["id"] not in done]
    if not todo:
        if done:
            st.caption(f"This month's bring-a-friend email went to {len(done)} member{'s' if len(done) != 1 else ''}.")
        return
    batch = todo[:ASK_BATCH]
    label = f"Ask {len(batch)} members to bring a friend" + (f" ({len(todo)} left this month)" if len(todo) > len(batch) else "")
    if not gcamp.ready():
        st.caption("Switch on email sending to ask every member to bring a friend in one tap.")
        return
    if st.button(label, icon=":material/campaign:", key="ref_ask_all", use_container_width=True):
        bar = st.progress(0.0, text="Sending…")
        sent = 0
        for i, m in enumerate(batch, 1):
            first = gw._text(m.get("full_name"), "there").split()[0]
            link = invite_link(code, m["id"])
            body = (f"Hi {first}! 🙌 Training is better with a friend. Invite someone to {biz} with your own link "
                    f"below. When they join, you get {reward}, added to your name automatically.\n\n{link}\n\n"
                    "Just forward it on WhatsApp. 💪")
            try:
                ok, _ = gcamp.email_member(supabase, gym_id, m, f"Bring a friend to {biz} 🎁", body)
            except Exception:
                ok = False
            gl._log(supabase, gym_id, m["id"], "refask", ref, "sent" if ok else "failed")
            sent += bool(ok)
            bar.progress(i / len(batch), text=f"Sending… {i} of {len(batch)}")
            time.sleep(0.55)
        bar.empty()
        st.session_state["grow_flash"] = f"Asked {sent} member{'s' if sent != 1 else ''} to bring a friend."
        st.rerun()
