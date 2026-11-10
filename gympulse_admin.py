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


def clean_url(url):
    """Accept the project URL however it was copied: with /rest/v1, a trailing slash or spaces."""
    import re
    url = (url or "").strip().strip('"').strip("'").rstrip("/")
    return re.sub(r"/(rest|auth|storage)/v\d+.*$", "", url)


def service_client():
    """A Supabase client that can read every gym (server-side only)."""
    url, key = clean_url(_env("SUPABASE_URL")), _env("SUPABASE_SERVICE_ROLE_KEY")
    if not (url and key):
        return None
    from supabase import create_client
    try:                                   # reuse one client per admin session
        cached = st.session_state.get("_svc_client")
        if cached and cached[0] == url:
            return cached[1]
        client = create_client(url, key)
        st.session_state["_svc_client"] = (url, client)
        return client
    except Exception:
        return create_client(url, key)


# ------------------------------------------------------------------ data
def all_gyms(sc, fresh=False):
    """Every gym with its owner's profile, email and WhatsApp number (kept for 2 minutes)."""
    hit = None if fresh else st.session_state.get("_adm_gyms")
    if hit and (datetime.now(timezone.utc) - hit[0]).seconds < 120:
        return hit[1]
    out = _all_gyms(sc)
    try:
        st.session_state["_adm_gyms"] = (datetime.now(timezone.utc), out)
    except Exception:
        pass
    return out


def _all_gyms(sc):
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
        email, user = "", None
        try:
            user = getattr(sc.auth.admin.get_user_by_id(g["owner_id"]), "user", None)
            email = getattr(user, "email", "") or ""
        except Exception:
            pass
        out.append({"gym": g, "profile": p, "email": email,
                    "signed_up": getattr(user, "created_at", None) or g.get("created_at"),
                    "last_login": getattr(user, "last_sign_in_at", None),
                    "banned_until": getattr(user, "banned_until", None),
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


def report_data(sc, entry, start, end):
    """One gym's report numbers, kept for 10 minutes so reopening it is instant."""
    key = (entry["gym"]["id"], str(start), str(end))
    store = st.session_state.setdefault("_adm_reports", {})
    hit = store.get(key)
    if hit and (datetime.now(timezone.utc) - hit[0]).seconds < 600:
        return hit[1]
    import gympulse_grow as gg
    with as_gym(entry):
        d = gg.monthly_data(sc, entry["gym"]["id"], None, start, end)
    store[key] = (datetime.now(timezone.utc), d)
    return d


def report_pdf(entry, d):
    import gympulse_grow as gg
    with as_gym(entry):
        return gg.monthly_pdf(d)


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
            ("Retention rate", (f"{d['retention']['rate']:.0f}% ({d['retention']['kept']} of {d['retention']['base']} "
                                f"members kept; industry average about 97% a month)")
             if (d.get("retention") or {}).get("rate") is not None else "Not enough members yet"),
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
    flags = gym_flags(sc) or {}
    import gympulse_billing as gbill
    locked = gbill.locked_gyms(sc) if not only else set()      # plan ended: no report (you can still send one)
    sent = skipped = failed = 0
    for entry in all_gyms(sc, fresh=True):
        gid = entry["gym"]["id"]
        if only and gid not in only:
            continue
        if gid in locked:
            skipped += 1
            log(f"plan ended {entry['name']}")
            continue
        if flags.get(gid, {}).get("reports_paused"):
            skipped += 1
            log(f"paused {entry['name']}")
            continue
        if (gid, "email") in done:
            skipped += 1
            continue
        try:
            d, pdf = gym_report(sc, entry, start, end)
            send_report_email(entry, d, pdf)
            del pdf
            log_sent(sc, gid, period, "email", sent_by)
            sent += 1
            log(f"sent   {entry['name']} -> {entry['email']}")
        except Exception as error:
            failed += 1
            log(f"failed {entry['name']}: {error}")
            import gympulse_monitoring as gmon
            gmon.capture(error, "monthly report")
    import gc
    gc.collect()
    return sent, skipped, failed


# ------------------------------------------------------------------ page
def render_admin():
    if not is_admin():
        st.error("This page is only for GymPulse AI admins.")
        return
    import gympulse_grow as gg
    import gympulse_reports as rp
    gw.page_header("Admin", "Every gym on GymPulse AI: accounts, activity and monthly reports.", "Founder")
    sc = service_client()
    if sc is None:
        st.warning("Add SUPABASE_SERVICE_ROLE_KEY on Render (Supabase → Project Settings → API → service_role) "
                   "so this page can read every gym. Keep it secret: it bypasses row-level security.")
        return
    flash = st.session_state.pop("adm_flash", None)
    if flash:
        (st.error if flash.startswith("Could not") else st.success)(flash)
    section = st.segmented_control("Admin section", ["Gyms", "Billing", "WhatsApp", "Monthly reports", "Admin log"],
                                   key="adm_section",
                                   default="Gyms", label_visibility="collapsed") or "Gyms"
    if section == "Gyms":
        render_gyms(sc)
    elif section == "Billing":
        import gympulse_billing as gb
        gb.render_admin_billing(sc, all_gyms(sc), audit)
    elif section == "WhatsApp":
        import gympulse_whatsapp as gwa
        gwa.render_admin_setup()
    elif section == "Admin log":
        render_log(sc)
    else:
        render_reports(sc)


def render_reports(sc):
    import gympulse_grow as gg
    import gympulse_reports as rp
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
    flags = gym_flags(sc) or {}
    emailed = sum((g["gym"]["id"], "email") in log for g in gyms)
    gw.kpi_row([("Gyms", str(len(gyms)), "cyan", "on GymPulse AI"),
                ("Emailed", f"{emailed}/{len(gyms)}", "lime", start.strftime("%B report")),
                ("WhatsApp sent", str(sum((g["gym"]["id"], "whatsapp") in log for g in gyms)), "amber", "by you"),
                ("Automatic", "1st of month", "grey", "8am Lagos, GitHub Actions")])
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

    gw.table([{"Gym": e["name"], "Owner": e["owner"], "Email": e["email"] or "–",
               "Report": "Sent" if (e["gym"]["id"], "email") in log else "Not sent",
               "WhatsApp": "Sent" if (e["gym"]["id"], "whatsapp") in log else "–",
               "Monthly reports": "Paused" if (flags.get(e["gym"]["id"]) or {}).get("reports_paused") else "On"}
              for e in gyms], pills=("Report", "WhatsApp", "Monthly reports"), max_height=420)
    if not gyms:
        return
    ids = [e["gym"]["id"] for e in gyms]
    pick = st.selectbox("Open a gym's report", ids, key="adm_pick_rep",
                        format_func=lambda i: next(f"{e['name']} · {e['owner'] or 'owner'}" for e in gyms if e["gym"]["id"] == i))
    for entry in [e for e in gyms if e["gym"]["id"] == pick]:
        gid = entry["gym"]["id"]
        chips = (gw.chip("emailed", "lime") if (gid, "email") in log else gw.chip("not emailed", "grey"))
        chips += gw.chip("reports paused", "amber") if (flags.get(gid) or {}).get("reports_paused") else ""
        chips += gw.chip("WhatsApp sent", "cyan") if (gid, "whatsapp") in log else ""
        with st.container(border=True):
            gw._md(f'<div style="font-size:18px;font-weight:700;margin-bottom:6px">{gw._esc(entry["name"])}</div>'
                   f'<div class="chip-row">{chips}</div>')
            # Reports are built only for the gym you open, and kept for this session:
            # building every gym's report on every click used too much memory.
            if not st.toggle("Show this gym's report", key=f"adm_show_{gid}_{period}"):
                continue
            st.session_state["adm_rep_open"] = gid
            try:
                d = report_data(sc, entry, start, end)
            except Exception as error:
                st.error(f"Could not build this report: {error}")
                continue
            gw.kpi_row([("Members kept", str(d["kept_n"]), "lime", ""),
                        ("Money kept", _money(d["credited"]), "cyan", ""),
                        ("Collected", _money(d["collected"]), "amber", ""),
                        ("New members", str(d["joined"]), "grey", "")])
            c1, c2, c3 = st.columns(3)
            pdf_key = f"_adm_pdf_{gid}_{period}"
            with c1:
                if st.session_state.get(pdf_key):
                    rp.download_link("Download PDF", st.session_state[pdf_key],
                                     f"{gg.safe_name(entry['name'])}-{period}-retention-report.pdf", rp.PDF, f"adm_pdf_{gid}")
                elif st.button("Prepare PDF", key=f"adm_mk_{gid}", use_container_width=True):
                    for k in [k for k in st.session_state.keys() if str(k).startswith("_adm_pdf_")]:
                        del st.session_state[k]            # keep only one PDF in memory
                    st.session_state[pdf_key] = report_pdf(entry, d)
                    st.rerun()
            if c2.button("Email report", key=f"adm_em_{gid}", type="primary", icon=":material/mail:",
                         use_container_width=True, disabled=not entry["email"]):
                try:
                    send_report_email(entry, d, report_pdf(entry, d))
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


# ================================================================== gym management
# Child tables first, so nothing is left behind and no foreign key blocks the delete.
GYM_TABLES = ["gym_staff", "billing_invoices", "member_feedback", "billing_events", "gym_subscriptions", "loyalty_redemptions", "auto_messages", "challenge_entries", "challenges", "referrals", "progress_logs", "member_freezes", "exit_reasons",
              "onboarding_steps", "payment_requests", "payments", "messages", "reminder_log", "checkins",
              "retention_actions", "member_activity", "classes", "trainers", "members", "companies",
              "platform_reports", "platform_gym_flags"]
BAN_FOREVER = "876000h"     # 100 years: Supabase's way to block a login


def _actor():
    return (st.session_state.get("auth_user") or {}).get("email", "admin")


def audit(sc, action, entry, detail=None):
    try:
        sc.table("admin_audit").insert({"actor": _actor(), "action": action, "gym_id": entry["gym"]["id"],
                                        "gym_name": entry["name"], "owner_email": entry["email"] or None,
                                        "detail": detail or {}}).execute()
    except Exception:
        pass


def gym_flags(sc):
    """{gym_id: {"reports_paused": bool, "note": str}} or None before sql/phase7_admin_tools.sql."""
    try:
        return {r["gym_id"]: r for r in sc.table("platform_gym_flags").select("*").execute().data or []}
    except Exception:
        return None


def set_flag(sc, gym_id, **fields):
    sc.table("platform_gym_flags").upsert({"gym_id": gym_id, **fields,
                                          "updated_at": datetime.now(timezone.utc).isoformat()},
                                         on_conflict="gym_id").execute()


def _count(sc, table, gym_id, since=None, col="checked_in_at"):
    try:
        q = sc.table(table).select("id", count="exact").eq("gym_id", gym_id)
        if since:
            q = q.gte(col, since)
        res = q.limit(1).execute()
        if res.count is not None:
            return res.count
        q = sc.table(table).select("id").eq("gym_id", gym_id)      # clients without counts
        return len((q.gte(col, since) if since else q).execute().data or [])
    except Exception:
        return None


def _last(sc, table, gym_id, col):
    try:
        rows = sc.table(table).select(col).eq("gym_id", gym_id).order(col, desc=True).limit(1).execute().data or []
        return rows[0][col] if rows else None
    except Exception:
        return None


def gym_stats(sc, gym_id):
    key = ("adm_stats", gym_id)
    hit = st.session_state.get("_adm_stats", {}).get(key)
    if hit and (datetime.now(timezone.utc) - hit[0]).seconds < 120:
        return hit[1]
    since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    out = {"members": _count(sc, "members", gym_id), "checkins_30d": _count(sc, "checkins", gym_id, since),
           "plays": _count(sc, "retention_actions", gym_id), "payments": _count(sc, "payments", gym_id),
           "last_checkin": _last(sc, "checkins", gym_id, "checked_in_at")}
    st.session_state.setdefault("_adm_stats", {})[key] = (datetime.now(timezone.utc), out)
    return out


def _when(value):
    if not value:
        return "never"
    try:
        t = pd.to_datetime(value, utc=True).tz_convert(gw.APP_TZ)
        days = (pd.Timestamp.now(tz=gw.APP_TZ) - t).days
        return f"{t:%d %b %Y}" + (" (today)" if days == 0 else f" ({days}d ago)" if days < 60 else "")
    except Exception:
        return str(value)[:10]


def _is_banned(entry):
    b = entry.get("banned_until")
    if not b:
        return False
    try:
        return pd.to_datetime(b, utc=True) > pd.Timestamp.now(tz="UTC")
    except Exception:
        return False


def is_protected(entry):
    """Admin accounts can't be suspended or deleted from here (so you can't lock yourself out)."""
    return (entry.get("email") or "").lower() in admin_emails()


def gym_backup(sc, entry):
    """An Excel file with the gym's members, check-ins, plays and payments, made before a delete."""
    import gympulse_reports as rp
    gid = entry["gym"]["id"]
    sheets = []
    for table, title in (("members", "Members"), ("member_activity", "Plans"), ("payments", "Payments"),
                         ("retention_actions", "Plays"), ("checkins", "Check-ins"), ("trainers", "Trainers")):
        try:
            rows = sc.table(table).select("*").eq("gym_id", gid).limit(20000).execute().data or []
        except Exception:
            rows = []
        df = pd.DataFrame(rows)
        if "photo" in df.columns:
            df = df.drop(columns=["photo"])
        sheets.append((title, df if len(df) else pd.DataFrame({"Note": ["No rows"]}), {}))
    return rp.build_xlsx(sheets, f"{entry['name']} backup", gym=entry["name"])


def delete_gym(sc, entry, delete_login=True):
    """Permanently remove a gym, all its data, its images and (optionally) the owner's login."""
    gid, owner = entry["gym"]["id"], entry["gym"].get("owner_id")
    st.session_state.pop("_adm_gyms", None)
    done, problems = [], []
    try:                                    # staff logins for this gym go too
        for r in sc.table("gym_staff").select("user_id").eq("gym_id", gid).execute().data or []:
            if r.get("user_id"):
                try:
                    sc.auth.admin.delete_user(r["user_id"])
                except Exception as error:
                    problems.append(f"staff login: {str(error)[:60]}")
    except Exception:
        pass
    for table in GYM_TABLES:
        try:
            sc.table(table).delete().eq("gym_id", gid).execute()
            done.append(table)
        except Exception as error:
            msg = str(error)
            if "does not exist" not in msg and "PGRST205" not in msg and "42P01" not in msg:
                problems.append(f"{table}: {msg[:80]}")
    try:                                    # logos, photos and banners in storage
        store = sc.storage.from_("email-assets")
        paths = []
        for folder in ("", "brand", "banners", "trainers"):
            prefix = f"{gid}/{folder}".rstrip("/")
            for f in store.list(prefix) or []:
                if f.get("id"):
                    paths.append(f"{prefix}/{f['name']}")
        if paths:
            store.remove(paths)
    except Exception:
        pass
    try:
        sc.table("gyms").delete().eq("id", gid).execute()
    except Exception as error:
        problems.append(f"gyms: {str(error)[:120]}")
        return False, problems
    if delete_login and owner:
        try:
            sc.table("profiles").delete().eq("id", owner).execute()
        except Exception as error:
            problems.append(f"profiles: {str(error)[:80]}")
        try:
            sc.auth.admin.delete_user(owner)
        except Exception as error:
            problems.append(f"login: {str(error)[:80]}")
    return True, problems


def set_suspended(sc, entry, suspend):
    st.session_state.pop("_adm_gyms", None)
    sc.auth.admin.update_user_by_id(entry["gym"]["owner_id"], {"ban_duration": BAN_FOREVER if suspend else "none"})


# ------------------------------------------------------------------ gyms tab
def render_gyms(sc):
    import gympulse_reports as rp
    try:
        gyms = all_gyms(sc)
    except Exception as error:
        st.error(f"Could not load gyms: {error}")
        return
    flags = gym_flags(sc)
    if flags is None:
        st.info("Run sql/phase7_admin_tools.sql in Supabase to switch on pausing reports and the admin log.")
        flags = {}
    stats = {g["gym"]["id"]: gym_stats(sc, g["gym"]["id"]) for g in gyms}
    total_members = sum(s["members"] or 0 for s in stats.values())
    active = sum(1 for s in stats.values() if (s["checkins_30d"] or 0) > 0)
    week = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=7)
    new_week = sum(1 for g in gyms if g.get("signed_up") and pd.to_datetime(g["signed_up"], utc=True) >= week)
    gw.kpi_row([("Gyms", str(len(gyms)), "cyan", f"{new_week} joined this week"),
                ("Active gyms", str(active), "lime", "check-ins in the last 30 days"),
                ("Members", f"{total_members:,}", "amber", "across all gyms"),
                ("Suspended", str(sum(_is_banned(g) for g in gyms)), "grey", "login blocked")])

    c1, c2 = st.columns([3, 1])
    q = c1.text_input("Search", placeholder="Gym, owner or email", key="adm_q", label_visibility="collapsed")
    order = c2.selectbox("Sort", ["Newest", "Most members", "Least active", "Name"], key="adm_sort",
                         label_visibility="collapsed")
    view = [g for g in gyms if not q or q.lower() in f"{g['name']} {g['owner']} {g['email']}".lower()]
    if order == "Newest":
        view.sort(key=lambda g: str(g.get("signed_up") or ""), reverse=True)
    elif order == "Most members":
        view.sort(key=lambda g: -(stats[g["gym"]["id"]]["members"] or 0))
    elif order == "Least active":
        view.sort(key=lambda g: stats[g["gym"]["id"]]["checkins_30d"] or 0)

    table = pd.DataFrame([{"Gym": g["name"], "Owner": g["owner"], "Email": g["email"],
                           "Signed up": _when(g.get("signed_up")), "Last login": _when(g.get("last_login")),
                           "Members": stats[g["gym"]["id"]]["members"],
                           "Check-ins (30d)": stats[g["gym"]["id"]]["checkins_30d"],
                           "Status": "Suspended" if _is_banned(g) else "Active",
                           "Reports": "Paused" if flags.get(g["gym"]["id"], {}).get("reports_paused") else "On"}
                          for g in view])
    try:
        rp.download_link("Export gyms (Excel)", rp.build_xlsx([("Gyms", table, {})], "GymPulse AI gyms",
                                                              gym="GymPulse AI"), "gympulse-gyms.xlsx", rp.XLSX
                         if hasattr(rp, "XLSX") else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                         "adm_export")
    except Exception:
        pass

    gw.table(table, pills=("Status", "Reports"), max_height=460,
             caption=f"{len(view)} gym{'s' if len(view) != 1 else ''}. Pick one below to manage it.")
    if not view:
        return
    ids = [g["gym"]["id"] for g in view]
    if st.session_state.get("adm_open") in ids and "adm_pick_gym" not in st.session_state:
        st.session_state["adm_pick_gym"] = st.session_state["adm_open"]
    pick = st.selectbox("Manage a gym", ids, key="adm_pick_gym",
                        format_func=lambda i: next(f"{g['name']} · {g['owner'] or 'no name'} · {g['email'] or 'no email'}"
                                                   for g in view if g["gym"]["id"] == i))
    for g in [x for x in view if x["gym"]["id"] == pick]:
        gid = g["gym"]["id"]
        s = stats[gid]
        f = flags.get(gid, {})
        banned = _is_banned(g)
        chips = (gw.chip("suspended", "red", dot=True) if banned else gw.chip("active", "lime", dot=True))
        chips += gw.chip("reports paused", "amber") if f.get("reports_paused") else ""
        chips += gw.chip("admin", "cyan") if is_protected(g) else ""
        with st.container(border=True):
            gw._md(f'<div style="font-size:18px;font-weight:700;margin-bottom:6px">{gw._esc(g["name"])}</div>'
                   f'<div class="chip-row">{chips}</div>')
            gw.kpi_row([("Members", str(s["members"] if s["members"] is not None else "–"), "cyan", ""),
                        ("Check-ins (30d)", str(s["checkins_30d"] if s["checkins_30d"] is not None else "–"), "lime",
                         f"last {_when(s['last_checkin'])}"),
                        ("Plays", str(s["plays"] if s["plays"] is not None else "–"), "amber", ""),
                        ("Payments", str(s["payments"] if s["payments"] is not None else "–"), "grey", "")])
            st.caption(f"Signed up {_when(g.get('signed_up'))} · last login {_when(g.get('last_login'))}"
                       + (f" · WhatsApp {g['phone']}" if g["phone"] else ""))
            note = st.text_input("Private note (only admins see this)", f.get("note") or "", key=f"adm_note_{gid}",
                                 placeholder="e.g. pilot gym, paid until March, test account")
            c1, c2, c3 = st.columns(3)
            if note != (f.get("note") or "") and c1.button("Save note", key=f"adm_ns_{gid}", use_container_width=True):
                try:
                    set_flag(sc, gid, note=note.strip() or None)
                    audit(sc, "note", g, {"note": note.strip()})
                    st.session_state["adm_flash"] = f"Note saved for {g['name']}."
                    st.session_state["adm_open"] = gid
                except Exception as error:
                    st.session_state["adm_flash"] = f"Could not save the note: {error}"
                st.session_state["adm_open"] = gid
                st.rerun()
            paused = bool(f.get("reports_paused"))
            if c2.button("Resume monthly reports" if paused else "Pause monthly reports", key=f"adm_rp_{gid}",
                         use_container_width=True):
                try:
                    set_flag(sc, gid, reports_paused=not paused)
                    audit(sc, "reports_resumed" if paused else "reports_paused", g)
                    st.session_state["adm_flash"] = (f"Monthly reports {'resumed' if paused else 'paused'} "
                                                     f"for {g['name']}.")
                except Exception as error:
                    st.session_state["adm_flash"] = f"Could not change reports: {error}"
                st.session_state["adm_open"] = gid
                st.rerun()
            if g.get("email") and c3.button("Send password reset", key=f"adm_pw_{gid}", use_container_width=True):
                try:
                    sc.auth.reset_password_for_email(g["email"])
                    audit(sc, "password_reset", g)
                    st.session_state["adm_flash"] = f"Password reset email sent to {g['email']}."
                except Exception as error:
                    st.session_state["adm_flash"] = f"Could not send the reset: {error}"
                st.session_state["adm_open"] = gid
                st.rerun()

            if is_protected(g):
                st.caption("This is an admin account, so it can't be suspended or deleted here.")
                continue
            st.markdown("**Access**")
            if st.button("Restore access" if banned else "Suspend access", key=f"adm_ban_{gid}",
                         type="secondary", use_container_width=True,
                         help="Suspending blocks the owner from logging in. Their data stays, and you can restore it."):
                try:
                    set_suspended(sc, g, not banned)
                    audit(sc, "restored" if banned else "suspended", g)
                    st.session_state["adm_flash"] = f"{g['name']} {'can log in again' if banned else 'is suspended'}."
                except Exception as error:
                    st.session_state["adm_flash"] = f"Could not change access: {error}"
                st.session_state["adm_open"] = gid
                st.rerun()

            if st.toggle("Delete this gym…", key=f"adm_dt_{gid}"):
                st.warning(f"This permanently deletes **{g['name']}**: {s['members'] or 0} members, their check-ins, "
                           "plays, payments, messages, trainers, images and reports. It can't be undone.")
                try:
                    rp.download_link("Download a backup first (Excel)", gym_backup(sc, g),
                                     f"{gw._text(g['name']).replace(' ', '-')}-backup.xlsx",
                                     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                     f"adm_bk_{gid}")
                except Exception as error:
                    st.caption(f"Backup unavailable: {error}")
                also = st.checkbox("Also delete the owner's login, so they can't sign in again with it",
                                   value=True, key=f"adm_dl_{gid}")
                typed = st.text_input(f'Type "{g["name"]}" to confirm', key=f"adm_dc_{gid}")
                if st.button("Delete permanently", key=f"adm_del_{gid}", type="primary",
                             disabled=typed.strip() != g["name"].strip(), use_container_width=True):
                    with st.spinner("Deleting…"):
                        ok, problems = delete_gym(sc, g, also)
                    audit(sc, "deleted", g, {"login_deleted": bool(also), "problems": problems})
                    st.session_state.pop("_adm_stats", None)
                    st.session_state["adm_flash"] = (
                        (f"{g['name']} was deleted." if ok else f"Could not delete {g['name']}.")
                        + (" Notes: " + "; ".join(problems) if problems else ""))
                    st.session_state["adm_open"] = gid
                    st.rerun()


def render_log(sc):
    try:
        rows = sc.table("admin_audit").select("*").order("at", desc=True).limit(200).execute().data or []
    except Exception:
        st.info("Run sql/phase7_admin_tools.sql in Supabase to keep a log of admin actions.")
        return
    if not rows:
        st.caption("No admin actions yet.")
        return
    gw.table([{"When": _when(r.get("at") or r.get("created_at")), "Action": gw._text(r.get("action")).replace("_", " ").capitalize(),
               "Gym": r.get("gym_name"), "Owner": r.get("owner_email"), "Admin": r.get("actor")} for r in rows],
             max_height=640)
