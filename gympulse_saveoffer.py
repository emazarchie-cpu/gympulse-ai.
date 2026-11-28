"""GymPulse AI · "Stay with us" discount when a member asks to cancel.

Member app → Me → Cancel my membership: the member says why, and (when the gym has switched it on and the member
qualifies) sees a one-time offer from the gym, e.g. 50% off their next month. If they keep their membership, the
discount comes off their next renewal automatically (pay link and card renewals, gympulse_memberpay.py). If not,
it becomes a cancellation notice with a save call in the Action Centre, like a notice taken at the front desk.

Rules that stop members gaming it (checked the same way for the app and for staff on the phone):
  - once per member in 12 months (any offer, taken or not)
  - only members who joined 60+ days ago and have paid at least once
  - only while their plan is current
  - one month only, used once, on the next renewal; lost 45 days after the current plan ends
Database: sql/phase53_save_offers.sql. Settings: the owner's profile settings["save_offer"].
"""
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import streamlit as st

import gympulse_workspaces as gw

DEFAULTS = {"on": False, "percent": 50, "min_days": 60, "once_months": 12, "expire_days": 45}
REASONS = ["Price or money", "Moving or travelling", "No time", "Injury or health", "Not seeing results",
           "Unhappy with the gym", "Other"]


def cfg(prof):
    raw = dict(((prof or {}).get("settings") or {}).get("save_offer") or {})
    return {**DEFAULTS, **raw}


def _naira(x):
    return f"₦{float(x or 0):,.0f}"


def _date(v):
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def monthly_fee(sc, member_id):
    try:
        a = sc.table("member_activity").select("monthly_fee").eq("member_id", member_id).limit(1).execute().data
        return float((a or [{}])[0].get("monthly_fee") or 0)
    except Exception:
        return 0.0


def _offers(sc, member_id):
    try:
        return (sc.table("save_offers").select("*").eq("member_id", member_id).order("created_at", desc=True)
                .limit(20).execute().data or [])
    except Exception:
        return []


def pending(sc, member_id, today=None):
    """The accepted, unused, unexpired offer for this member, or None."""
    today = today or gw.today_local()
    for o in _offers(sc, member_id):
        if o.get("accepted") and not o.get("used_at") and (_date(o.get("expires_on")) or today) >= today:
            return o
    return None


def eligible(sc, member_id, prof, today=None):
    """(ok, reason when not, discount in naira, monthly fee)."""
    today = today or gw.today_local()
    c = cfg(prof)
    if not c["on"]:
        return False, "The save offer is switched off.", 0.0, 0.0
    try:
        m = (sc.table("members").select("id, gym_id, membership_end, created_at, last_payment, archived")
             .eq("id", member_id).limit(1).execute().data or [None])[0]
    except Exception:
        m = None
    if not m or m.get("archived"):
        return False, "Not a current member.", 0.0, 0.0
    end = _date(m.get("membership_end"))
    if not end or end < today:
        return False, "Their plan has already ended.", 0.0, 0.0
    joined = pd.to_datetime(m.get("created_at"), errors="coerce", utc=True)
    if pd.isna(joined) or (today - joined.tz_convert(gw.APP_TZ).date()).days < int(c["min_days"]):
        return False, f"They joined less than {int(c['min_days'])} days ago.", 0.0, 0.0
    paid = float(m.get("last_payment") or 0) > 0
    if not paid:
        try:
            paid = bool(sc.table("payments").select("id").eq("member_id", member_id).limit(1).execute().data)
        except Exception:
            paid = False
    if not paid:
        return False, "No payment from them is recorded yet.", 0.0, 0.0
    window = today - timedelta(days=int(c["once_months"]) * 30)
    for o in _offers(sc, member_id):
        made = pd.to_datetime(o.get("created_at"), errors="coerce", utc=True)
        if not pd.isna(made) and made.tz_convert(gw.APP_TZ).date() >= window:
            return False, f"They already had an offer on {made.tz_convert(gw.APP_TZ):%d %b %Y}.", 0.0, 0.0
    fee = monthly_fee(sc, member_id)
    if fee <= 0:
        return False, "Their monthly fee isn't recorded, so there's nothing to discount.", 0.0, 0.0
    return True, "", round(fee * int(c["percent"]) / 100, 2), fee


def record(sc, gym_id, member_id, prof, discount, channel, reason, accepted, staff=None):
    c = cfg(prof)
    try:
        end = _date((sc.table("members").select("membership_end").eq("id", member_id).limit(1).execute().data
                     or [{}])[0].get("membership_end"))
    except Exception:
        end = None
    expires = (end or gw.today_local()) + timedelta(days=int(c["expire_days"]))
    sc.table("save_offers").insert({"gym_id": gym_id, "member_id": member_id, "percent": int(c["percent"]),
                                    "discount": float(discount), "channel": channel, "reason": reason,
                                    "accepted": bool(accepted), "expires_on": expires.isoformat(),
                                    "staff": staff}).execute()


def mark_used(sc, offer_id, ref):
    sc.table("save_offers").update({"used_at": datetime.now(timezone.utc).isoformat(), "used_ref": str(ref)[:80]}) \
        .eq("id", offer_id).is_("used_at", "null").execute()


def _cancel_notice(sc, m, reason):
    """The member's request to cancel: a notice on their record and a save call for the team."""
    end = _date(m.get("membership_end"))
    eff = end if end and end >= gw.today_local() else gw.today_local()
    sc.table("members").update({"cancel_notice_at": datetime.now(timezone.utc).isoformat(),
                                "cancel_effective": eff.isoformat(), "cancel_reason": reason,
                                "cancel_status": "pending"}).eq("id", m["id"]).execute()
    try:
        gw._create_action(sc, m["gym_id"], m["id"], "Personal call", 0,
                          note=f"Asked to cancel in the member app ({reason}). Leaving {eff:%d %b}: call them.")
    except Exception:
        pass
    return eff


# ================================================================== member app (Me tab)
def render_member_cancel(sc, m, gym_name, prof):
    key = f"so_step_{m['id']}"
    try:
        cur = (sc.table("members").select("cancel_status, cancel_effective, membership_end").eq("id", m["id"])
               .limit(1).execute().data or [{}])[0]
    except Exception:
        cur = {}
    st.divider()
    if cur.get("cancel_status") == "pending":
        eff = _date(cur.get("cancel_effective"))
        st.caption(f"You asked to cancel. Your membership stays active until "
                   f"{eff:%d %B %Y}." if eff else "You asked to cancel.")
        st.caption(f"Changed your mind? Tell the team at {gym_name}.")
        return
    step = st.session_state.get(key, 0)
    if step == 0:
        if st.button("Cancel my membership", type="tertiary", key=f"so_open_{m['id']}"):
            st.session_state[key] = 1
            st.rerun()
        return
    m = {**m, **cur}
    with st.container(border=True):
        if step == 1:
            st.markdown("**Sorry to see you go. Can you tell us why?**")
            reason = st.radio("Reason", REASONS, index=None, key=f"so_reason_{m['id']}",
                              label_visibility="collapsed")
            c1, c2 = st.columns(2)
            if c1.button("Continue", type="primary", disabled=not reason, use_container_width=True,
                         key=f"so_next_{m['id']}"):
                st.session_state[f"so_r_{m['id']}"] = reason
                st.session_state[key] = 2
                st.rerun()
            if c2.button("Never mind", use_container_width=True, key=f"so_back_{m['id']}"):
                st.session_state[key] = 0
                st.rerun()
            return
        reason = st.session_state.get(f"so_r_{m['id']}") or "Other"
        ok, _why, disc, fee = eligible(sc, m["id"], prof)
        if ok:
            pct = int(cfg(prof)["percent"])
            st.markdown(f"**A message from {gw._esc(gym_name)}**")
            st.markdown(f"We'd love you to stay. Keep your membership and get **{pct}% off your next month**: "
                        f"{_naira(fee - disc)} instead of {_naira(fee)}.")
            st.caption("A one-time offer. It comes off your next renewal.")
            c1, c2 = st.columns(2)
            if c1.button(f"Keep my membership, {pct}% off", type="primary", use_container_width=True,
                         key=f"so_keep_{m['id']}"):
                record(sc, m["gym_id"], m["id"], prof, disc, "app", reason, True)
                st.session_state[key] = 0
                st.session_state["mp_flash"] = (f"Thank you for staying! Your next month is {pct}% off. "
                                                "It comes off your next renewal.")
                st.rerun()
            if c2.button("No thanks, cancel", use_container_width=True, key=f"so_go_{m['id']}"):
                record(sc, m["gym_id"], m["id"], prof, disc, "app", reason, False)
                eff = _cancel_notice(sc, m, reason)
                st.session_state[key] = 0
                st.session_state["mp_flash"] = (f"Your request to cancel has been sent to {gym_name}. Your membership "
                                                f"stays active until {eff:%d %B %Y}.")
                st.rerun()
        else:
            end = _date(m.get("membership_end"))
            st.markdown("**Send your request to cancel?**")
            st.caption(f"{gym_name} will be in touch. "
                       + (f"Your membership stays active until {end:%d %B %Y}." if end and end >= gw.today_local()
                          else ""))
            c1, c2 = st.columns(2)
            if c1.button("Send my request", type="primary", use_container_width=True, key=f"so_send_{m['id']}"):
                eff = _cancel_notice(sc, m, reason)
                st.session_state[key] = 0
                st.session_state["mp_flash"] = f"Your request to cancel has been sent to {gym_name}."
                st.rerun()
            if c2.button("Never mind", use_container_width=True, key=f"so_back2_{m['id']}"):
                st.session_state[key] = 0
                st.rerun()


# ================================================================== owner settings and staff (Cancellations)
def render_settings(supabase, prof):
    """Owner only: switch the offer on and choose the percentage."""
    import gympulse_grow as gg
    c = cfg(prof)
    with st.expander("Discount to stay (member app)", expanded=False):
        st.caption("When a member taps Cancel in the member app, they see a one-time offer from your gym first. "
                   "Each member can get it once in 12 months, only after 60 days with you and at least one "
                   "payment, and only on one month.")
        with st.form("save_offer_form", border=False):
            on = st.toggle("Offer a discount before they cancel", value=bool(c["on"]))
            pct = st.select_slider("Discount on their next month", options=[10, 20, 25, 30, 40, 50],
                                   value=int(c["percent"]) if int(c["percent"]) in (10, 20, 25, 30, 40, 50) else 50,
                                   format_func=lambda v: f"{v}%")
            if st.form_submit_button("Save", type="primary"):
                gg._save_settings(supabase, (prof or {}).get("id"),
                                  {"save_offer": {**c, "on": bool(on), "percent": int(pct)}},
                                  "Discount to stay saved.")
                st.rerun()


def render_staff_offer(supabase, gym_id, member_id, name, prof, staff):
    """On a cancellation notice: staff offered the discount on the phone and the member said yes."""
    ok, why, disc, fee = eligible(supabase, member_id, prof)
    pct = int(cfg(prof)["percent"])
    if not cfg(prof)["on"]:
        return False
    if not ok:
        st.caption(f"Discount to stay: not available. {why}")
        return False
    if st.button(f"They accepted {pct}% off next month ({_naira(disc)} off)", key=f"so_staff_{member_id}"):
        record(supabase, gym_id, member_id, prof, disc, "staff", "Phone or front desk", True, staff)
        supabase.table("members").update({"cancel_status": "saved"}).eq("id", member_id).eq("gym_id", gym_id).execute()
        gw.bump_data_version(gym_id)
        st.session_state["cn_flash"] = f"{name.split(' ')[0]} is staying with {pct}% off their next month."
        st.rerun()
    return True


def render_profile_note(supabase, gym_id, member_id):
    """Member profile: an unused discount the member accepted, so the front desk applies it at renewal."""
    o = pending(supabase, member_id)
    if not o:
        return
    with st.container(border=True):
        c1, c2 = st.columns([3, 1], vertical_alignment="center")
        c1.markdown(f"**Discount to stay:** {int(o['percent'])}% off their next month ({_naira(o['discount'])} off). "
                    f"Online payments apply it by themselves. Use by {_date(o.get('expires_on')):%d %b %Y}.")
        if c2.button("Used at the desk", key=f"so_used_{o['id']}",
                     help="Press after they renewed at the front desk with the discount."):
            mark_used(supabase, o["id"], "front desk")
            st.session_state["profile_flash"] = "Discount marked as used."
            st.rerun()
