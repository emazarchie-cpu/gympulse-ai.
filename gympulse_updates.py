"""GymPulse AI · Gym updates.

A quick, honest note to members when something at the gym isn't right (power,
air conditioning, water, equipment, opening hours, anything) and again when
it's fixed, so members don't quietly stop coming after one bad visit.

Sent by email with the gym's logo (respecting unsubscribes), plus one ready
message for the gym's WhatsApp Status or members' group, so nobody gets
flooded with individual WhatsApp messages. Each send is logged in
auto_messages (kind "update") so it shows in the history.
"""
import time
import zlib
import uuid
from datetime import timedelta

import pandas as pd
import streamlit as st

import gympulse_workspaces as gw

TOPICS = {
    # topic: (short name, problem sentence, fixed sentence)
    "Power / generator": ("power", "we're having a power problem at the gym",
                          "the power is back and everything is running normally"),
    "Air conditioning": ("air conditioning", "the air conditioning isn't working properly",
                         "the air conditioning is fixed and the gym is cool again"),
    "Water / showers": ("water", "there's a water problem, so showers and toilets may not be available",
                        "the water is back, so showers and toilets are working again"),
    "Equipment": ("equipment", "some of our equipment is out of order",
                  "the equipment has been fixed and is ready to use"),
    "Opening hours / closed": ("opening hours", "our opening hours are changing",
                               "we're back to our normal opening hours"),
    "Something else": ("an update", "", ""),
}
STATUS = ["There's a problem now", "It's fixed"]
WHO = ["Members who came in the last 30 days", "Everyone with a running membership"]


def draft(topic, fixed, detail, biz, owner):
    """(subject, body) in plain, calm language."""
    short, problem, done = TOPICS[topic]
    detail = (detail or "").strip()
    if detail and detail[-1] not in ".!?":
        detail += "."
    if fixed:
        back = {"power": "the power is back", "air conditioning": "the AC is fixed", "water": "the water is back",
                "equipment": "the equipment is fixed", "opening hours": "normal hours are back"}.get(short)
        subject = f"Good news from {biz}" + (f": {back}" if back else "")
        lead = f"Good news: {done}." if done else "Good news from the gym."
        body = (f"Hi {{first}},\n\n{lead}" + (f" {detail}" if detail else "")
                + "\n\nThanks for your patience. Come in any time, we'd love to see you.\n\n"
                f"{owner}\n{biz}")
    else:
        subject = f"A quick update from {biz}" + (f" about the {short}" if problem and short != "an update" else "")
        lead = f"A quick heads-up: {problem}." if problem else "A quick heads-up from the gym."
        body = (f"Hi {{first}},\n\n{lead}" + (f" {detail}" if detail else "")
                + "\n\nWe're on it, and we'll let you know as soon as it's sorted. Sorry for the trouble, "
                  "and thank you for bearing with us.\n\n"
                f"{owner}\n{biz}")
    return subject, body.replace("\n\n\n", "\n\n")


def audience(supabase, gym_id, who):
    import gympulse_grow as gg
    df = gg._members(supabase, gym_id)
    if df.empty:
        return df
    today = gw.today_local()
    running = df["end"].apply(lambda e: not gg._has_date(e) or e >= today)
    df = df[running]
    if who == WHO[0]:
        ck = gg._checkins(supabase, gym_id, 31)
        recent = set(ck["member_id"]) if len(ck) else set()
        df = df[df["id"].isin(recent)]
    return df


def _history(supabase, gym_id):
    try:
        since = (pd.Timestamp.now(tz="UTC") - timedelta(days=60)).isoformat()
        rows = supabase.table("auto_messages").select("ref, sent_at, status").eq("gym_id", gym_id) \
            .eq("kind", "update").gte("sent_at", since).execute().data or []
    except Exception:
        return []
    groups = {}
    for r in rows:
        g = groups.setdefault(r["ref"], {"when": str(r["sent_at"])[:16].replace("T", " "), "sent": 0})
        g["sent"] += r.get("status") == "sent"
    out = []
    for ref, g in groups.items():
        parts = ref.split(":")
        out.append({"When": g["when"], "About": parts[2] if len(parts) > 2 else "",
                    "Type": "Fixed" if len(parts) > 3 and parts[3] == "fixed" else "Problem", "Emails sent": g["sent"]})
    return sorted(out, key=lambda x: x["When"], reverse=True)


def _send(supabase, gym_id, members, subject, body, ref):
    import gympulse_campaigns as gcamp
    sent = skipped = failed = 0
    bar = st.progress(0.0, text="Sending...")
    for i, (_, m) in enumerate(members.iterrows()):
        md = dict(m)
        text = body.replace("{first}", gw._text(md.get("full_name")).split(" ")[0] or "there")
        if "@" not in gw._text(md.get("email")):
            skipped += 1
        else:
            ok, msg = gcamp.email_member(supabase, gym_id, md, subject, text)
            status = "sent" if ok else "skipped" if ("unsubscribed" in msg or "no email" in msg) else "failed"
            sent += ok
            skipped += status == "skipped"
            failed += status == "failed"
            try:
                supabase.table("auto_messages").insert({"gym_id": gym_id, "member_id": md["id"], "kind": "update",
                                                        "ref": ref, "status": status}).execute()
            except Exception:
                pass
            time.sleep(0.55)            # stay under the email service's rate limit
        bar.progress((i + 1) / len(members), text=f"Sending... {i + 1} of {len(members)}")
    bar.empty()
    return sent, skipped, failed


def render_updates(supabase, gym_id):
    import gympulse_grow as gg
    import gympulse_campaigns as gcamp
    gw.intro("Gym updates", ":material/campaign:", "Power out, AC down, no water, or anything else? Tell your members straight away, then again "
               "when it's fixed. One bad visit with no explanation is how members quietly stop coming.")
    biz, owner = gg._biz()
    c1, c2 = st.columns(2)
    topic = c1.selectbox("What is it about?", list(TOPICS), key="gu_topic")
    status = c2.radio("Update", STATUS, horizontal=True, key="gu_status")
    fixed = status == STATUS[1]
    detail = st.text_input("Anything to add? (optional)", key="gu_detail",
                           placeholder="e.g. The generator is being repaired and should be running by 4pm."
                           if not fixed else "e.g. We've also serviced the treadmills.")
    subject, body = draft(topic, fixed, detail, biz, owner)
    k = f"gu_{zlib.crc32(repr((topic, fixed, detail)).encode()) % 100000}"
    subj = st.text_input("Subject", subject, key=f"{k}_s")
    text = st.text_area("Email", body, height=210, key=f"{k}_b",
                        help="{first} becomes each member's first name.")
    who = st.radio("Who should get it?", WHO, horizontal=True, key="gu_who",
                   help="Members who came recently are the ones a problem affects most.")
    people = audience(supabase, gym_id, who)
    with_email = int(people["email"].fillna("").astype(str).str.contains("@").sum()) if len(people) else 0
    with st.expander("Preview the email"):
        import streamlit.components.v1 as components
        components.html(gcamp.render_message(gcamp.brand(), subj, text.replace("{first}", "Ada"), "#", None),
                        height=560, scrolling=True)
    c3, c4 = st.columns([2, 1])
    go = c3.button(f"Email {with_email} member{'s' if with_email != 1 else ''}", type="primary",
                   icon=":material/campaign:", use_container_width=True, disabled=not with_email or not subj.strip(),
                   key="gu_send")
    c4.caption(f"{len(people) - with_email} without an email" if len(people) - with_email else "")
    if with_email > 100:
        st.caption("Over 100 emails: the free email plan sends 100 a day, so some may go tomorrow.")
    if go:
        ref = f"update:{gw.today_local().isoformat()}:{TOPICS[topic][0]}:{'fixed' if fixed else 'problem'}:" \
              f"{uuid.uuid4().hex[:6]}"
        s, sk, f = _send(supabase, gym_id, people, subj.strip(), text, ref)
        st.session_state["grow_flash" if not f else "grow_error"] = (
            f"Update emailed to {s} member{'s' if s != 1 else ''}" + (f", {sk} skipped" if sk else "")
            + (f", {f} failed. Check your email settings." if f else ".") )
        st.rerun()

    st.markdown("**For WhatsApp**")
    st.caption("Post this once on your WhatsApp Status or members' group, instead of messaging everyone one by one.")
    wa = text.replace("Hi {first},\n\n", "").replace("{first}", "everyone")
    st.code(f"{'✅' if fixed else '⚠️'} {wa}", language=None, wrap_lines=True)

    hist = _history(supabase, gym_id)
    if hist:
        with st.expander(f"Updates sent in the last 60 days ({len(hist)})"):
            gw.table(hist, pills={"Type": {"Fixed": "lime", "Problem": "amber"}})
