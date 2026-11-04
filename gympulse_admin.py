"""GymPulse AI · founder admin: monthly reports for every gym.

Only people listed in the GYMPULSE_ADMINS environment variable (comma-separated
emails) see the Admin page. It reads every gym with the Supabase service-role
key (SUPABASE_SERVICE_ROLE_KEY), which never leaves the server.

The same functions run on the 1st of every month from
scripts/send_monthly_reports.py (a Render Cron Job), so reports go out on their
own. Each send is logged in platform_reports (sql/phase6_admin.sql), so no gym
gets the same month twice.
"""
import os
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import streamlit as st

import gympulse_workspaces as gw

REPORTS_FROM_DEFAULT = "GymPulse AI <reports@usegympulseai.com>"
_MISSING = object()


# ------------------------------------------------------------------ settings
def _env(name, default=""):
    value = os.environ.get(name)
    if value:
        return value.strip()
    try:
        return str(st.secrets.get(name, default) or default).strip()
    except Exception:
        return default


def admin_emails():
    return {e.strip().lower() for e in _env("GYMPULSE_ADMINS").split(",") if e.strip()}


def is_admin():
    email = ((st.session_state.get("auth_user") or {}).get("email") or "").lower()
    return bool(email) and email in admin_emails()


def service_client():
    """A Supabase client that can read every gym (server-side only)."""
    url, key = _env("SUPABASE_URL"), _env("SUPABASE_SERVICE_ROLE_KEY")
    if not (url and key):
        return None
    from supabase import create_client
    return create_client(url, key)


# ------------------------------------------------------------------ data
def all_gyms(sc):
    """Every gym with its owner's profile, email and WhatsApp number."""
    gyms = sc.table("gyms").select("id, owner_id, business_name, created_at").execute().data or []
    owners = [g["owner_id"] for g in gyms if g.get("owner_id")]
    profiles = {}
    if owners:
        for p in sc.table("profiles").select("*").in_("id", owners).execute().data or []:
            profiles[p["id"]] = p
    out = []
    for g in gyms:
        p = profiles.get(g.get("owner_id")) or {"id": g.get("owner_id"), "business_name": g.get("business_name")}
        s = dict(p.get("settings") or {})
        brand = dict(s.get("email_brand") or {})
        email = ""
        try:
            u = sc.auth.admin.get_user_by_id(g["owner_id"])
            email = getattr(getattr(u, "user", None), "email", "") or ""
        except Exception:
            pass
        out.append({"gym": g, "profile": p, "email": email,
                    "phone": gw._text(s.get("biz_phone") or brand.get("whatsapp")),
                    "name": gw._text(p.get("business_name") or g.get("business_name"), "Gym"),
                    "owner": gw._text(p.get("full_name"))})
    return sorted(out, key=lambda x: x["name"].lower())


def sent_log(sc, period):
    try:
        rows = sc.table("platform_reports").select("*").eq("period", period).execute().data or []
        return {(r["gym_id"], r["channel"]): r for r in rows}
    except Exception:
        return None


def log_sent(sc, gym_id, period, channel, sent_by):
    try:
        sc.table("platform_reports").insert({"gym_id": gym_id, "period": period, "channel": channel,
                                             "sent_by": sent_by}).execute()
    except Exception:
        pass


@contextmanager
def as_gym(entry):
    """Compute a gym's report as if its owner were signed in, then restore the admin's session."""
    keys = ["user_profile", "auth_user", "_cache", "_pdf_brand", "_logo_tone", "_dv"]
    saved = {k: st.session_state.get(k, _MISSING) for k in keys}
    try:
        st.session_state["user_profile"] = entry["profile"]
        st.session_state["auth_user"] = {"id": entry["gym"].get("owner_id"), "email": entry["email"]}
        st.session_state["_cache"] = {}
        st.session_state.pop("_pdf_brand", None)
        st.session_state.pop("_logo_tone", None)
        yield
    finally:
        for k, v in saved.items():
            if v is _MISSING:
                st.session_state.pop(k, None)
            else:
                st.session_state[k] = v


def gym_report(sc, entry, start, end):
    """(data, pdf bytes) for one gym and month."""
    import gympulse_grow as gg
    with as_gym(entry):
        d = gg.monthly_data(sc, entry["gym"]["id"], None, start, end)
        pdf = gg.monthly_pdf(d)
    return d, pdf


# ------------------------------------------------------------------ messages
def _money(x):
    return f"₦{float(x or 0):,.0f}"


def report_rows(d):
    rows = [("Members kept", f"{d['kept_n']}" + (f", worth {_money(d['credited'])}" if d["kept_n"] else "")),
            ("Collected", _money(d["collected"]) + (f" (incl. {_money(d['recovered'])} won back)" if d["recovered"] else "")),
            ("New members", str(d["joined"])), ("Memberships ended", str(d["lapsed"])),
            ("Visits", f"{d['visits']} from {d['active']} active members")]
    if d.get("top_staff"):
        rows.append(("Top of the team", d["top_staff"]))
    if d.get("top_reason"):
        rows.append(("Main reason members left", d["top_reason"]))
    return rows


def report_email(entry, d):
    import gympulse_email as ge
    month = d["start"].strftime("%B %Y")
    hello = f"Hi {gw._text(entry['owner']).split(' ')[0] or 'there'},"
    lead = (f"GymPulse AI helped {gw._esc(entry['name'])} keep <b>{d['kept_n']} member"
            f"{'s' if d['kept_n'] != 1 else ''}</b> in {month}, worth <b>{_money(d['credited'])}</b>."
            if d["kept_n"] else f"Here is how {gw._esc(entry['name'])} did in {month}.")
    body = (f"<p style=\"margin:0 0 10px\">{gw._esc(hello)}</p><p style=\"margin:0 0 6px\">{lead}</p>"
            + ge.details([(k, gw._esc(v)) for k, v in report_rows(d)])
            + "<p style=\"margin:10px 0 14px\">The full report is attached as a PDF. Open GymPulse AI to see "
              "who needs you this week.</p>"
            + ge.button("Open GymPulse AI", ge.SITE))
    subject = f"{entry['name']}: your {month} retention report"
    text = (f"{hello}\n\n" + "\n".join(f"{k}: {v}" for k, v in report_rows(d))
            + f"\n\nThe full report is attached. Open GymPulse AI: {ge.SITE}")
    return subject, ge.layout(f"Your {month} report", body, preheader=subject), text


def report_whatsapp(entry, d):
    month = d["start"].strftime("%B")
    first = gw._text(entry["owner"]).split(" ")[0] or "there"
    lines = [f"Hi {first}, it's Emmanuel from GymPulse AI. Here's {entry['name']}'s {month} report:"]
    lines += [f"- {k}: {v}" for k, v in report_rows(d)]
    lines += ["", "I've emailed you the full PDF too. Open GymPulse AI to see who needs you this week: "
                  "https://usegympulseai.com"]
    return "\n".join(lines)


def send_report_email(entry, d, pdf):
    import base64
    import requests
    import gympulse_grow as gg
    key = _env("RESEND_API_KEY")
    if not key:
        raise RuntimeError("RESEND_API_KEY is not set.")
    if "@" not in entry["email"]:
        raise RuntimeError("This gym owner has no email address.")
    subject, html, text = report_email(entry, d)
    payload = {"from": _env("REPORTS_FROM", REPORTS_FROM_DEFAULT), "to": [entry["email"]],
               "subject": subject, "html": html, "text": text,
               "reply_to": _env("REPORTS_REPLY_TO", "emmanuel@usegympulseai.com"),
               "attachments": [{"filename": f"{gg.safe_name(entry['name'])}-{d['start']:%Y-%m}-retention-report.pdf",
                                "content": base64.b64encode(pdf).decode()}]}
    r = requests.post("https://api.resend.com/emails", json=payload, timeout=30,
                      headers={"Authorization": f"Bearer {key}"})
    if r.status_code >= 300:
        raise RuntimeError(f"Resend said {r.status_code}: {r.text[:200]}")
    return r.json().get("id", "")


def send_all(sc, start, end, sent_by="auto", only=None, log=print):
    """Email every gym its report for the month, skipping any already sent. Returns (sent, skipped, failed)."""
    period = f"{start:%Y-%m}"
    done = sent_log(sc, period) or {}
    sent = skipped = failed = 0
    for entry in all_gyms(sc):
        gid = entry["gym"]["id"]
        if only and gid not in only:
            continue
        if (gid, "email") in done:
            skipped += 1
            continue
        try:
            d, pdf = gym_report(sc, entry, start, end)
            send_report_email(entry, d, pdf)
            log_sent(sc, gid, period, "email", sent_by)
            sent += 1
            log(f"sent   {entry['name']} -> {entry['email']}")
        except Exception as error:
            failed += 1
            log(f"failed {entry['name']}: {error}")
    return sent, skipped, failed


# ------------------------------------------------------------------ page
def render_admin():
    if not is_admin():
        st.error("This page is only for GymPulse AI admins.")
        return
    import gympulse_grow as gg
    import gympulse_reports as rp
    gw.page_header("Admin", "Monthly reports for every gym on GymPulse AI.", "Founder")
    sc = service_client()
    if sc is None:
        st.warning("Add SUPABASE_SERVICE_ROLE_KEY on Render (Supabase → Project Settings → API → service_role) "
                   "so this page can read every gym. Keep it secret: it bypasses row-level security.")
        return
    today = gw.today_local()
    months = []
    y, m = today.year, today.month
    for _ in range(6):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        months.append(date(y, m, 1))
    first = st.selectbox("Month", months, format_func=lambda d: d.strftime("%B %Y"), key="adm_month")
    start, end = first, date(first.year + (first.month == 12), first.month % 12 + 1, 1) - timedelta(days=1)
    period = f"{start:%Y-%m}"
    log = sent_log(sc, period)
    if log is None:
        st.info("Run sql/phase6_admin.sql in Supabase to keep a log of sent reports (it stops a gym getting the "
                "same month twice).")
        log = {}
    try:
        gyms = all_gyms(sc)
    except Exception as error:
        st.error(f"Could not load gyms: {error}")
        return
    emailed = sum((g["gym"]["id"], "email") in log for g in gyms)
    gw.kpi_row([("Gyms", str(len(gyms)), "cyan", "on GymPulse AI"),
                ("Emailed", f"{emailed}/{len(gyms)}", "lime", start.strftime("%B report")),
                ("WhatsApp sent", str(sum((g["gym"]["id"], "whatsapp") in log for g in gyms)), "amber", "by you"),
                ("Automatic", "1st of month", "grey", "Render Cron Job")])
    flash = st.session_state.pop("adm_flash", None)
    if flash:
        st.success(flash)
    if emailed < len(gyms) and st.button(f"Email all {len(gyms) - emailed} unsent reports", type="primary",
                                         icon=":material/mail:"):
        with st.spinner("Sending…"):
            lines = []
            s_, k_, f_ = send_all(sc, start, end, sent_by=(st.session_state.get("auth_user") or {}).get("email", "admin"),
                                  log=lines.append)
        st.session_state["adm_flash"] = f"Sent {s_}, already sent {k_}, failed {f_}."
        if f_:
            st.session_state["adm_flash"] += " " + " · ".join(l for l in lines if l.startswith("failed"))
        st.rerun()

    for entry in gyms:
        gid = entry["gym"]["id"]
        chips = (gw.chip("emailed", "lime") if (gid, "email") in log else gw.chip("not emailed", "grey"))
        chips += gw.chip("WhatsApp sent", "cyan") if (gid, "whatsapp") in log else ""
        with st.expander(f"{entry['name']} · {entry['owner'] or 'owner'} · {entry['email'] or 'no email'}"):
            gw._md(f'<div class="chip-row">{chips}</div>')
            try:
                d, pdf = gym_report(sc, entry, start, end)
            except Exception as error:
                st.error(f"Could not build this report: {error}")
                continue
            gw.kpi_row([("Members kept", str(d["kept_n"]), "lime", ""),
                        ("Money kept", _money(d["credited"]), "cyan", ""),
                        ("Collected", _money(d["collected"]), "amber", ""),
                        ("New members", str(d["joined"]), "grey", "")])
            c1, c2, c3 = st.columns(3)
            with c1:
                rp.download_link("Download PDF", pdf, f"{gg.safe_name(entry['name'])}-{period}-retention-report.pdf",
                                 rp.PDF, f"adm_pdf_{gid}")
            if c2.button("Email report", key=f"adm_em_{gid}", type="primary", icon=":material/mail:",
                         use_container_width=True, disabled=not entry["email"]):
                try:
                    send_report_email(entry, d, pdf)
                    log_sent(sc, gid, period, "email", (st.session_state.get("auth_user") or {}).get("email", "admin"))
                    st.session_state["adm_flash"] = f"Report emailed to {entry['email']}."
                except Exception as error:
                    st.session_state["adm_flash"] = f"Could not email {entry['name']}: {error}"
                st.rerun()
            if entry["phone"]:
                c3.link_button("WhatsApp the owner", gg.wa_url(entry["phone"], report_whatsapp(entry, d)),
                               icon=":material/chat:", use_container_width=True)
                if st.button("I sent it on WhatsApp", key=f"adm_wa_{gid}", type="tertiary"):
                    log_sent(sc, gid, period, "whatsapp", (st.session_state.get("auth_user") or {}).get("email", "admin"))
                    st.rerun()
            else:
                c3.caption("No WhatsApp number in this gym's settings.")
