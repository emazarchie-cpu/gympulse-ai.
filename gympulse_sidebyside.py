"""GymPulse AI · Side-by-side: run GymPulse AI next to GymMaster (or other software) during a pilot.

Most gyms won't switch software overnight. While they test GymPulse AI, the front desk keeps working in
GymMaster and the owner uploads a fresh GymMaster export now and then (weekly is enough). Re-importing is
safe: members are matched and updated, and visits are never counted twice (each visit has a fingerprint).

While side-by-side is on:
  * a reminder appears on the Dashboard and Member Management when the last export is over 7 days old;
  * GymPulse AI doesn't send its own renewal reminders (GymMaster already does), unless the owner says so,
    so members don't get two;
  * the risk list, follow-ups and reports work from the imported data as usual.

When the owner is convinced, the "Switch fully" checklist walks through cutover (best on a weekend):
a final import, check-ins on GymPulse AI, automatic messages on, member links shared, then "We've switched".

Stored in the owner's profile settings: settings.side_by_side = {on, source, since, gympulse_renewals,
switched_on}.
"""
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

import gympulse_workspaces as gw

STALE_DAYS = 7
SOURCES = ["GymMaster", "Mindbody", "Glofox", "Excel / Google Sheets", "Other software"]


def cfg(profile=None):
    p = profile if profile is not None else (st.session_state.get("user_profile") or {})
    raw = dict(dict(p.get("settings") or {}).get("side_by_side") or {})
    return {"on": bool(raw.get("on")), "source": raw.get("source") or "GymMaster", "since": raw.get("since"),
            "gympulse_renewals": bool(raw.get("gympulse_renewals")), "switched_on": raw.get("switched_on")}


def skips_renewals(profile=None):
    """True while running side by side and the old software still sends renewal reminders."""
    c = cfg(profile)
    return c["on"] and not c["gympulse_renewals"]


def last_import(supabase, gym_id):
    """When members were last brought in from a file (not undone), or None."""
    try:
        rows = (supabase.table("member_imports").select("created_at, undone_at, file_name").eq("gym_id", gym_id)
                .is_("undone_at", "null").order("created_at", desc=True).limit(1).execute().data or [])
    except Exception:
        return None
    if not rows:
        return None
    t = pd.to_datetime(rows[0]["created_at"], errors="coerce", utc=True, format="ISO8601")
    return None if pd.isna(t) else t.to_pydatetime()


def _days_ago(t):
    return (datetime.now(timezone.utc) - t).days if t else None


def _save(supabase, patch, message):
    if st.session_state.get("role") == "staff":
        st.error("Only the gym owner can change this.")
        return
    profile = st.session_state.get("user_profile") or {}
    owner_id = (st.session_state.get("auth_user") or {}).get("id") or profile.get("id")
    s = dict(profile.get("settings") or {})
    s["side_by_side"] = {**dict(s.get("side_by_side") or {}), **patch}
    try:
        supabase.table("profiles").update({"settings": s}).eq("id", owner_id).execute()
        profile["settings"] = s
        st.session_state["user_profile"] = profile
        st.session_state["gm_flash"] = message
        st.rerun()
    except Exception as error:
        if type(error).__name__ in ("RerunException", "StopException"):
            raise
        st.error(f"Could not save: {error}")


def _when(t):
    d = _days_ago(t)
    return "never" if d is None else "today" if d == 0 else "yesterday" if d == 1 else f"{d} days ago"


# ------------------------------------------------------------------ the reminder at the top of the app
def render_banner(supabase, gym_id):
    c = cfg()
    if not c["on"]:
        return
    t = last_import(supabase, gym_id)
    d = _days_ago(t)
    if d is not None and d <= STALE_DAYS:
        return
    st.info(f"You're running GymPulse AI alongside **{c['source']}**. Last update from {c['source']}: "
            f"**{_when(t)}**. Upload this week's export so the risk list stays accurate.",
            icon=":material/sync:")
    if st.button(f"Update from {c['source']}", key="sbs_update", icon=":material/upload_file:"):
        st.session_state["gm_open"] = True
        st.session_state["navigate_to"] = "Member Management"
        st.rerun()


# ------------------------------------------------------------------ the panel on the import screen
def render_panel(supabase, gym_id):
    c = cfg()
    owner = st.session_state.get("role") != "staff"
    with st.container(border=True):
        if not c["on"]:
            st.markdown("**Testing GymPulse AI first? Run it side by side.**")
            st.caption("Keep using GymMaster (or your current software) at the front desk while you try GymPulse "
                       "AI. Upload a fresh export once a week: members are updated, never duplicated, and visits are "
                       "never counted twice. When you're convinced, switch fully in one evening.")
            if owner:
                c1, c2 = st.columns([2, 1])
                src = c1.selectbox("We're still using", SOURCES, key="sbs_src", label_visibility="collapsed")
                if c2.button("Run side by side", key="sbs_on", type="primary", use_container_width=True):
                    _save(supabase, {"on": True, "source": src, "since": gw.today_local().isoformat(),
                                     "gympulse_renewals": False, "switched_on": None},
                          f"Side by side with {src} is on. Upload a fresh export once a week.")
            if c.get("switched_on"):
                st.caption(f"You switched fully to GymPulse AI on {c['switched_on']}.")
            return
        t = last_import(supabase, gym_id)
        st.markdown(f"**Running side by side with {c['source']}**")
        st.caption(f"Since {c['since'] or '–'} · last export uploaded {_when(t)}. Keep checking members in on "
                   f"{c['source']} for now, and upload a fresh export here once a week (more often is fine).")
        try:
            upto = gw.data_as_of(gw.load_checkins(supabase, gym_id))
        except Exception:
            upto = None
        if upto:
            st.caption(f"Risk scores count visits up to **{upto:%d %b}** (your latest upload), so members aren't "
                       "flagged just because the export is a few days old. Daily uploads make them sharper.")
        if owner:
            ren = st.checkbox(f"GymPulse AI sends renewal reminders too ({c['source']} may already send them)",
                              value=c["gympulse_renewals"], key="sbs_ren",
                              help="Off by default, so members don't get the same reminder twice.")
            if ren != c["gympulse_renewals"]:
                _save(supabase, {"gympulse_renewals": ren},
                      "GymPulse AI renewal reminders " + ("on." if ren else "off while running side by side."))
        _render_webhook(supabase, gym_id, c["source"], owner)
        with st.expander("Ready to switch fully? Checklist", icon=":material/task_alt:"):
            d = _days_ago(t)
            fresh = d is not None and d <= 1
            st.markdown(("✅" if fresh else "⬜") + f" **1. Final import:** upload today's {c['source']} export, "
                        "with visit history, after the gym closes." + ("" if fresh else f" (last one: {_when(t)})"))
            st.markdown("⬜ **2. Check-ins:** from tomorrow, the front desk checks members in on GymPulse AI "
                        "(Member Management or the QR code), not on " + c["source"] + ".")
            st.markdown("⬜ **3. Messages:** switch on renewal reminders and \"we missed you\" in "
                        "Grow → Automatic messages, and switch them off in " + c["source"] + ".")
            st.markdown("⬜ **4. Members:** share the sign-up link or each member's personal link, so they can see "
                        "their visits and renew.")
            st.markdown("⬜ **5. Keep " + c["source"] + " read-only for a month**, just in case, then cancel it.")
            if owner and st.button("We've switched fully", key="sbs_done", type="primary",
                                   icon=":material/rocket_launch:", disabled=not fresh,
                                   help=None if fresh else "Upload today's final export first."):
                _save(supabase, {"on": False, "switched_on": gw.today_local().isoformat(), "gympulse_renewals": True},
                      f"Welcome fully to GymPulse AI. {c['source']} can stay read-only for a month, just in case.")
        if owner and st.button("Stop running side by side", key="sbs_off", type="tertiary"):
            _save(supabase, {"on": False}, "Side by side is off.")


# ------------------------------------------------------------------ automatic check-ins (GymMaster webhook)
def _integration(supabase, gym_id):
    """The gym's GymMaster webhook row, {} when not set up, or None when phase 39 hasn't been run."""
    try:
        rows = supabase.table("gym_integrations").select("*").eq("gym_id", gym_id).eq("kind", "gymmaster") \
            .limit(1).execute().data or []
        return rows[0] if rows else {}
    except Exception:
        return None


def webhook_url(gym_id, secret):
    import gympulse_admin as gadm
    base = gadm.clean_url(gadm._env("SUPABASE_URL")).rstrip("/")
    return f"{base}/functions/v1/gymmaster-webhook?gym={gym_id}&key={secret}"


def _render_webhook(supabase, gym_id, source, owner):
    with st.expander(f"Automatic check-ins from {source}", icon=":material/sync_alt:"):
        st.caption(f"Instead of uploading exports, {source} can send each check-in to GymPulse AI the moment it "
                   "happens, so the risk list is always up to date. Your front desk keeps checking in on "
                   f"{source} as usual.")
        row = _integration(supabase, gym_id)
        if row is None:
            st.info("This needs a one-time setup: open Supabase, go to SQL Editor, paste in the file "
                    "sql/phase39_gymmaster_checkins.sql and press Run.")
            return
        if not row:
            if owner and st.button("Create my connection link", key="gmw_make", type="primary",
                                   icon=":material/link:"):
                import secrets
                try:
                    supabase.table("gym_integrations").upsert({"gym_id": gym_id, "kind": "gymmaster",
                                                               "secret": secrets.token_urlsafe(24)}).execute()
                    st.session_state["gm_flash"] = "Connection link created. Paste it into GymMaster's Webhook Manager."
                    st.rerun()
                except Exception as error:
                    if type(error).__name__ in ("RerunException", "StopException"):
                        raise
                    st.error(f"Could not create the link: {error}")
            return
        url = webhook_url(gym_id, row["secret"])
        st.markdown("**1.** In GymMaster, open **Settings → Integrations → Webhook Manager**.")
        st.markdown("**2.** Add a webhook for **member check-in**, with this as the target URL:")
        st.code(url, language=None, wrap_lines=True)
        st.markdown("**3.** Check a member in on GymMaster. Within a minute it shows below.")
        st.caption("Keep this link private: anyone with it could add check-ins to your gym.")
        n, ok = int(row.get("events") or 0), int(row.get("matched") or 0)
        if not n:
            st.caption("Waiting for the first check-in from GymMaster…")
        else:
            when = pd.to_datetime(row.get("last_event_at"), errors="coerce", utc=True)
            last = "" if pd.isna(when) else f", last one {when.tz_convert(gw.APP_TZ):%d %b %H:%M}"
            res = {"saved": "saved ✅", "duplicate": "already counted ✅", "no_match": "member not found ⚠️"}
            st.markdown(f"**{n:,}** check-in message{'s' if n != 1 else ''} received, **{ok:,}** matched to a "
                        f"member{last} · latest: {res.get(row.get('last_result'), row.get('last_result') or '–')}")
            if row.get("last_unmatched"):
                st.warning("Some check-ins couldn't be matched to a member. Usually the member isn't imported "
                           "yet, or their GymMaster member ID wasn't in the import file. Re-import with the "
                           "member ID column, or send the message below to GymPulse AI support.")
                with st.popover("Last message we couldn't match"):
                    st.json(row["last_unmatched"])
        if owner and st.button("Make a new link (the old one stops working)", key="gmw_new", type="tertiary"):
            import secrets
            supabase.table("gym_integrations").update({"secret": secrets.token_urlsafe(24)}) \
                .eq("gym_id", gym_id).eq("kind", "gymmaster").execute()
            st.session_state["gm_flash"] = "New link made. Paste it into GymMaster again."
            st.rerun()
