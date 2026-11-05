"""GymPulse AI · Class invites.

Members who only use the equipment cancel more often than members who take
group classes (they have fewer friends and coaches at the gym). This lists
members who trained recently but have never been checked in to a class, with
a friendly invitation to an upcoming class.
"""
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

import gympulse_workspaces as gw

WINDOW_DAYS = 120         # look back this far for any class check-in
MIN_VISITS = 3            # only members who are actually training (last 60 days)


def equipment_only(members, ck, today):
    """[{m, visits}] for members with 3+ visit days in 60 days and no class check-in in 120 days."""
    if ck is None or not len(ck) or "class_id" not in ck.columns:
        return []
    recent = ck[ck["day"] >= pd.Timestamp(today - timedelta(days=60))].drop_duplicates(["member_id", "day"])
    visits = recent.groupby("member_id").size()
    in_class = set(ck[ck["class_id"].notna()]["member_id"])
    out = []
    for _, m in members.iterrows():
        end = m.get("end")
        if end is not None and not pd.isna(end) and end < today:
            continue
        n = int(visits.get(m["id"], 0))
        if n >= MIN_VISITS and m["id"] not in in_class:
            out.append({"m": m, "visits": n})
    return sorted(out, key=lambda r: -r["visits"])


def invite_text(m, classes, biz, owner):
    first = gw._text(m.get("full_name")).split(" ")[0] or "there"
    if classes:
        names = ", ".join(f"{c.get('name', 'a class')} ({c['_start']:%a %d %b, %-I:%M%p})".replace(":00", "")
                          for c in classes[:3])
        offer = f"Coming up soon: {names}. "
    else:
        offer = ""
    return (f"Hi {first},\n\nYou've been putting in great work at {biz} lately. Have you tried one of our group "
            f"classes yet? They're a fun way to mix up your training, and you'll get to know the coaches and other "
            f"members. {offer}Just reply with the one you'd like and we'll save you a spot.\n\n{owner}\n{biz}")


def render_class_invites(supabase, gym_id):
    import gympulse_grow as gg
    gw.intro("Class invites", ":material/groups:", "Members who only use the equipment are more likely to cancel than members who join group classes: "
               "classes give them friends and a coach who notices them. These members train regularly but haven't "
               "been to a class yet.")
    classes = gw.load_classes(supabase, gym_id)
    ck = gg._checkins(supabase, gym_id, WINDOW_DAYS)
    has_class_checkins = len(ck) and "class_id" in ck.columns and ck["class_id"].notna().any()
    if not classes and not has_class_checkins:
        st.info("You don't have any classes in GymPulse yet. Add them on the Check-in page, and check members in to "
                "a class, then this shows who hasn't tried one.")
        return
    members = gg._members(supabase, gym_id)
    today = gw.today_local()
    rows = equipment_only(members, ck, today)
    now = datetime.now(gw.APP_TZ).replace(tzinfo=None)
    upcoming = [c for c in classes if c["_start"] >= now and c["_start"] <= now + timedelta(days=10)]
    upcoming.sort(key=lambda c: c["_start"])
    gw.kpi_row([("Never been to a class", str(len(rows)), "amber", f"trained {MIN_VISITS}+ times in 60 days"),
                ("Classes in the next 10 days", str(len(upcoming)), "cyan",
                 "add more on the Check-in page" if not upcoming else "")])
    if not rows:
        st.success("Everyone who trains regularly has been to a class. 👏")
        return
    biz, owner = gg._biz()
    for r in rows[:40]:
        m = r["m"]
        with st.expander(f"{m['full_name']} · {r['visits']} visits in 60 days, no classes yet"):
            k = f"ci_msg_{m['id']}"
            st.session_state.setdefault(k, invite_text(m, upcoming, biz, owner))
            st.text_area("Message", key=k, height=170, label_visibility="collapsed")
            gg.send_row(k, m, f"ci_send_{m['id']}", f"Join a class at {biz}, {gg._first(m['full_name'])}?",
                        supabase=supabase, gym_id=gym_id)
    if len(rows) > 40:
        st.caption(f"Showing the 40 most regular of {len(rows)}.")
