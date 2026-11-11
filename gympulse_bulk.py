"""GymPulse AI · Bulk actions for the Action Centre: one tap for the whole to-do list.

* Send all: every play that hasn't been sent yet gets its message, on WhatsApp where that's set up and
  allowed (plan allowance, the gym's WhatsApp choice, member hasn't opted out), otherwise by email.
  Each play then moves to Contacted with its follow-up date, so staff only watch replies and follow-ups.
* Share out: unassigned plays are shared evenly between the staff names in the automation settings.

Staff stay in charge: nothing is sent until someone presses Send, they see the numbers first, and members
without a phone or email are listed for a call.
"""
import time

import pandas as pd
import streamlit as st

import gympulse_workspaces as gw

RENEWAL_DAYS = 14


def pending(actions):
    """Open plays not sent yet (To start / In progress without a contact)."""
    if actions is None or actions.empty:
        return []
    rows = actions.to_dict("records")
    return [a for a in rows if gw._blank(a.get("archived_at"))
            and gw.action_stage(a) in ("Started", "In progress")]


def _channels(supabase, gym_id, plays, members):
    """[(play, member, channel or None, kind)] and a summary."""
    import gympulse_campaigns as gcamp
    import gympulse_whatsapp as gwa
    wcfg = gwa.wa_settings()
    wa_on = wcfg["mode"] != "email" and gwa.ready()
    ids = [a["member_id"] for a in plays]
    opted = gwa.opt_outs(supabase, gym_id, ids) if wa_on and ids else set()
    left = {"UTILITY": 0, "MARKETING": 0}
    if wa_on:
        import gympulse_billing as gbill
        allow = gbill.wa_allowance(supabase, gym_id)
        used = gwa.month_usage(supabase, gym_id)
        left = {"UTILITY": allow["wa_renew"] - used["utility"], "MARKETING": allow["wa_promo"] - used["marketing"]}
    mail_on = gcamp.ready()
    out = []
    for a in plays:
        m = members.get(a["member_id"])
        if m is None:
            continue
        end = m.get("end")
        renewing = not gw.is_hmo(m) and (a["action_type"] == "Renewal offer" or (
            end is not None and not pd.isna(end) and (end - gw.today_local()).days <= RENEWAL_DAYS))
        kind = "renewal" if renewing else "missed"
        cat = gwa.TEMPLATES[gwa.KIND_TEMPLATE[kind]]["category"]
        channel = None
        if (wa_on and gwa.to_digits(m.get("phone")) and m["id"] not in opted and gwa.allowed(kind, wcfg)
                and left[cat] > 0):
            channel = "WhatsApp"
            left[cat] -= 1
        elif mail_on and "@" in gw._text(m.get("email")):
            channel = "Email"
        out.append((a, m, channel, kind))
    return out


def _members(supabase, gym_id):
    """Member records with plan and end date, plus the facts a message may use (from the Action Centre)."""
    import gympulse_grow as gg
    df = gg._members(supabase, gym_id)
    facts = (st.session_state.get("_play_ctx") or {}).get("contacts") or {}
    out = {}
    for m in (df.to_dict("records") if not df.empty else []):
        f = facts.get(m["id"]) or {}
        m["days_since_last_visit"] = f.get("days_away")
        m["_ctx"] = f or gw.member_message_ctx(m)
        out[m["id"]] = m
    return out


def render_bar(supabase, gym_id, actions):
    """The bulk bar above the board."""
    plays = pending(actions)
    import gympulse_automation as ga
    staff = ga.staff_list()
    unassigned = [a for a in plays if not ga.assigned_to(a)] if staff else []
    if not plays:
        return
    with st.container(border=True, key="bulk_bar"):
        gw._md(f'<div style="font-weight:800;font-size:16px">{len(plays)} play{"s" if len(plays) != 1 else ""} '
               f'ready to send</div><div class="why">Send them all in one go. Each member gets their message, the '
               f'play moves to Contacted, and GymPulse reminds your team when a follow-up is due.</div>')
        c1, c2 = st.columns(2)
        if c1.button(f"Send all {len(plays)}", type="primary", icon=":material/send:", key="bulk_send",
                     use_container_width=True):
            send_dialog(supabase, gym_id, [a["id"] for a in plays])
        if staff and unassigned:
            if c2.button(f"Share {len(unassigned)} between staff", icon=":material/group:", key="bulk_share",
                         use_container_width=True):
                n = share_out(supabase, unassigned, staff)
                st.session_state["ac_flash"] = f"Shared {n} play{'s' if n != 1 else ''} between {', '.join(staff)}."
                st.rerun()
        elif not staff:
            c2.caption("Add staff names in Settings → Automation to share plays out between them.")


def share_out(supabase, plays, staff):
    import gympulse_automation as ga
    load = {s: 0 for s in staff}
    n = 0
    for a in plays:
        who = min(load, key=load.get)
        try:
            ga.assign(supabase, a["id"], who, gw._text(a.get("note")))
            load[who] += 1
            n += 1
        except Exception:
            continue
    gw.bump_data_version()
    return n


@st.dialog("Send all plays", width="large")
def send_dialog(supabase, gym_id, ids):
    actions = gw.load_actions(supabase, gym_id, include_archived=True)
    plays = [a for a in pending(actions) if a["id"] in set(ids)]
    if not plays:
        st.info("These plays have already been sent.")
        return
    jobs = _channels(supabase, gym_id, plays, _members(supabase, gym_id))
    wa = [j for j in jobs if j[2] == "WhatsApp"]
    em = [j for j in jobs if j[2] == "Email"]
    none = [j for j in jobs if j[2] is None]
    gw.kpi_row([("WhatsApp", len(wa), "lime", "from your gym's name"), ("Email", len(em), "cyan", "with your logo"),
                ("Call instead", len(none), "amber", "no phone or email we can use")])
    if none:
        st.caption("Not sent (no WhatsApp number or email, they opted out, or this month's WhatsApp allowance is "
                   "used): " + ", ".join(gw._text(j[1].get("full_name")) for j in none[:8])
                   + ("…" if len(none) > 8 else "") + ". Their plays stay on the board for a call.")
    if not (wa or em):
        st.warning("Nothing can be sent automatically yet. Switch on WhatsApp or email sending, or add phone "
                   "numbers and emails to these members.")
        return
    ctx = gw._biz_ctx()
    a0, m0, ch0, _ = (wa or em)[0]
    with st.expander("See an example message"):
        st.write(gw.play_message(a0["action_type"], m0["_ctx"], None, ctx, a0.get("details")
                                 if isinstance(a0.get("details"), dict) else None))
        st.caption("WhatsApp uses your approved message templates; email sends the full message above, "
                   "written for each member.")
    st.caption("Your team then watches replies in Follow-ups and the follow-ups due on the board.")
    if st.button(f"Send {len(wa) + len(em)} messages now", type="primary", icon=":material/send:",
                 key="bulk_go", use_container_width=True):
        sent, failed = _send(supabase, gym_id, wa + em, ctx)
        gw.bump_data_version()
        msg = f"Sent {sent} message{'s' if sent != 1 else ''}."
        if failed:
            msg += f" {len(failed)} couldn't be sent ({'; '.join(failed[:3])}). Their plays stay on the board."
        if none:
            msg += f" {len(none)} need a call: they're still in To start."
        st.session_state["ac_flash"] = msg
        st.rerun()


def _send(supabase, gym_id, jobs, ctx):
    import gympulse_campaigns as gcamp
    import gympulse_whatsapp as gwa
    bar = st.progress(0.0, text="Sending…")
    sent, failed = 0, []
    for i, (a, m, channel, kind) in enumerate(jobs, 1):
        name = gw._text(m.get("full_name"), "member")
        details = a.get("details") if isinstance(a.get("details"), dict) else None
        text = gw.play_message(a["action_type"], m["_ctx"], None, ctx, details)
        ok, why = False, ""
        try:
            if channel == "WhatsApp":
                last = gw.today_local() - pd.Timedelta(days=int(pd.to_numeric(m.get("days_since_last_visit"), errors="coerce") or 14))
                end = m.get("end")
                ref = (f"end:{end.isoformat()}" if kind == "renewal" and end is not None and not pd.isna(end)
                       else f"last:{last.isoformat()}")
                ok, why = gwa.send_member(supabase, gym_id, m, kind, ref, f"A note from {ctx['biz']}", text, [])
                if not ok and "@" in gw._text(m.get("email")) and gcamp.ready():
                    channel = "Email"                      # WhatsApp didn't go: try email
            if channel == "Email" and not ok:
                ok, why = gcamp.email_member(supabase, gym_id, m, f"A note from {ctx['biz']}", text)
                time.sleep(0.55)                          # stay inside the email service's rate limit
        except Exception as error:
            ok, why = False, str(error)
        if ok:
            try:
                gw.mark_contacted(supabase, a["id"], channel, play=a["action_type"])
            except Exception:
                pass
            sent += 1
        else:
            failed.append(f"{name}: {why}"[:80])
        bar.progress(i / len(jobs), text=f"Sending… {i} of {len(jobs)}")
    bar.empty()
    return sent, failed
