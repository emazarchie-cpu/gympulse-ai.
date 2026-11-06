"""GymPulse AI: Risk Radar, Retention Action Centre, Payments & Renewals,
Business Insights, Archie, Check-in, Settings.
"""
import base64
import io
import os
import re
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from html import escape as _html_escape
from urllib.parse import quote
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

ARCHIE_MODEL = "claude-sonnet-5-5"
APP_TZ = ZoneInfo("Africa/Lagos")

PHOTO_TYPES = ["jpg", "jpeg", "png", "heic", "heif", "webp"]

ACTIVITY_COLS = [
    "membership_type", "days_since_last_visit", "visits_previous_30_days",
    "visits_last_30_days", "renewal_due_days", "pt_sessions_attended",
]
PILLARS = {
    "Customer experience": {"icon": "chat", "tone": "cyan",
        "blurb": "Clear, warm communication so every member feels looked after.",
        "plays": ["Personal call", "WhatsApp check-in", "Feedback request", "Renewal offer"]},
    "Trainer relationship": {"icon": "user", "tone": "lime",
        "blurb": "Members stay for people. Connect each one with a trainer.",
        "plays": ["Free PT session", "Trainer intro", "Goal review"]},
    "Community": {"icon": "users", "tone": "amber",
        "blurb": "Belonging beats discounts. Bring members together.",
        "plays": ["Class invite", "Group challenge", "Bring-a-friend invite"]},
    "Culture": {"icon": "heart", "tone": "red",
        "blurb": "Celebrate wins and make every return feel special.",
        "plays": ["Milestone shout-out", "Welcome-back note"]},
}
ACTION_TYPES = [p for info in PILLARS.values() for p in info["plays"]]
STATUSES = ["To do", "In progress", "Done"]
OUTCOMES = ["Retained", "Cancelled", "No response"]
SUGGEST_COOLDOWN_DAYS = 30
DONE_RETENTION_HOURS = 24
PURGE_INTERVAL_SECONDS = 600
MOBILE_PARTS = {
    "base": """
@media (max-width: 640px) {
    .block-container {
        padding-left: 0.9rem !important;
        padding-right: 0.9rem !important;
        padding-top: 0.6rem !important;
    }
    .hero { padding: 18px !important; }
    .hero-title { font-size: 26px !important; }
    input, textarea, [data-baseweb="select"] input { font-size: 16px !important; }
    .block-container .stButton > button { min-height: 44px; }
}
""",
    "nav": """
@media (max-width: 640px) {
    .login-brand .nav-tagline {
        display: block !important;
        white-space: normal !important;
        font-size: 11px !important;
    }
    .st-key-top_nav div[role="radiogroup"] {
        flex-wrap: wrap !important;
        gap: 4px !important;
    }
    .st-key-top_nav div[role="radiogroup"] label {
        padding: 8px 10px !important;
    }
}
""",
    "brand": """
@media (max-width: 640px) {
    .st-key-top_nav [data-testid="stColumn"]:first-child [data-testid="stHorizontalBlock"] {
        flex-direction: row !important;
        flex-wrap: nowrap !important;
    }
    .st-key-top_nav [data-testid="stColumn"]:first-child [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
        min-width: 0 !important;
    }
}
""",
    "metrics": """
@media (max-width: 640px) {
    [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) {
        flex-wrap: wrap !important;
        gap: 0.6rem !important;
    }
    [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) > [data-testid="stColumn"] {
        flex: 1 1 calc(50% - 0.6rem) !important;
        min-width: calc(50% - 0.6rem) !important;
    }
    [data-testid="stMetric"] { padding: 14px !important; }
    [data-testid="stMetricValue"] { font-size: 22px !important; }
}
""",
}


def _mobile_css(off=()):
    keep = "".join(css for name, css in MOBILE_PARTS.items() if name not in off)
    return "<style>" + keep + "</style>"


MOBILE_CSS = _mobile_css()


def apply_mobile_styles():
    off = ()
    try:
        params = st.query_params
        raw = str(params.get("off", ""))
        off = tuple(MOBILE_PARTS) if raw == "all" else tuple(
            x.strip() for x in raw.split(",") if x.strip())
    except Exception:
        pass
    st.markdown(_mobile_css(off), unsafe_allow_html=True)

TONES = {
    "lime": "#B7F34A", "red": "#FF6B6B", "amber": "#FFC44D",
    "cyan": "#35D6ED", "white": "#F4F7FB", "grey": "#9AA8BD",
}
# Membership plans, shortest first. "Annual" is the old name for Yearly and is
# still read from existing records.
PLAN_DAYS = {"Daily": 1, "Weekly": 7, "2 weeks": 14, "Monthly": 30, "2 months": 60,
             "Quarterly": 90, "6 months": 180, "Yearly": 365, "Annual": 365}
PLAN_MONTHS = {p: (round(d / 30, 4) if d < 30 else {30: 1, 60: 2, 90: 3, 180: 6, 365: 12}[d])
               for p, d in PLAN_DAYS.items()}
PLANS = ["Daily", "Weekly", "2 weeks", "Monthly", "2 months", "Quarterly", "6 months", "Yearly"]
PLAN_PHRASE = {"Daily": "daily", "Weekly": "weekly", "2 weeks": "two-week", "Monthly": "monthly",
               "2 months": "two-month", "Quarterly": "quarterly", "6 months": "six-month",
               "Yearly": "yearly", "Annual": "yearly"}


def plan_name(value):
    """A plan from the list above ('Annual' reads as Yearly; anything unknown as Monthly)."""
    v = str(value or "").strip()
    if v == "Annual":
        return "Yearly"
    return v if v in PLAN_DAYS else "Monthly"


def plan_phrase(value):
    """'Weekly' -> 'weekly', '2 weeks' -> 'two-week' (for 'your two-week membership')."""
    return PLAN_PHRASE.get(plan_name(value), "monthly")


def model_plan(value):
    """The risk model was trained on Monthly, Quarterly and Annual plans: short plans
    score like Monthly, 6 months like Quarterly, and Yearly like Annual."""
    days = PLAN_DAYS.get(plan_name(value), 30)
    return "Monthly" if days <= 60 else "Quarterly" if days <= 180 else "Annual"
PHOTO_SIZE = 192
GOALS = ["Weight loss", "Muscle gain", "General fitness", "Strength",
         "Endurance", "Sports performance"]
CHART_MUTED = "#9AA8BD"

def _esc(value):
    return _html_escape("" if value is None else str(value), quote=True)

def _md(markup, target=None):
    flat = " ".join(line.strip() for line in str(markup).splitlines() if line.strip())
    (target if target is not None else st).markdown(flat, unsafe_allow_html=True)

def center(name, max_px=640):
    """A centred column of at most max_px that is always full width on phones.

    Replaces the old st.columns([1, w, 1]) trick: Safari on iPhone sometimes kept those three columns side by
    side, which squeezed the middle one into a third of the screen."""
    key = f"center_{name}"
    st.markdown(f"<style>.st-key-{key} {{ max-width: {int(max_px)}px; width: 100% !important; margin: 0 auto; }}</style>",
                unsafe_allow_html=True)
    return st.container(key=key)


def _text(value, default=""):
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    return str(value)

def today_local():
    return datetime.now(APP_TZ).date()


def apply_live_dates(df):
    """Move 'days since last visit' and 'days until renewal' forward to today."""
    df = df.copy()
    today = pd.Timestamp(today_local())

    stamp = None
    for col in ("updated_at", "created_at"):
        if col in df.columns:
            s = pd.to_datetime(df[col], errors="coerce", utc=True, format="ISO8601")
            s = s.dt.tz_convert(APP_TZ).dt.tz_localize(None).dt.normalize()
            stamp = s if stamp is None else stamp.fillna(s)
    if stamp is None:
        return df

    elapsed = (today - stamp).dt.days.fillna(0).clip(lower=0)

    visits = pd.to_numeric(df["days_since_last_visit"], errors="coerce").fillna(0)
    df["days_since_last_visit"] = (visits + elapsed).astype(int)

    renewal = pd.to_numeric(df["renewal_due_days"], errors="coerce").fillna(0)
    fallback = (renewal - elapsed).clip(lower=0)
    if "membership_end" in df.columns:
        end = pd.to_datetime(df["membership_end"], errors="coerce").dt.normalize()
        from_end = (end - today).dt.days.clip(lower=0)
        fallback = from_end.where(end.notna(), fallback)
    df["renewal_due_days"] = fallback.astype(int)
    return df


def _num(value, default):
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default

# ---------------------------------------------------------------- photos
def process_photo(raw_bytes, size=PHOTO_SIZE):
    from PIL import Image, ImageOps
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except Exception:
        pass
    img = Image.open(io.BytesIO(raw_bytes))
    img = ImageOps.exif_transpose(img).convert("RGB")
    img = ImageOps.fit(img, (size, size), method=Image.LANCZOS, centering=(0.5, 0.4))
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=80, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()

def initials(name):
    parts = [p for p in str(name or "").replace("-", " ").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()

def has_photo(photo):
    return isinstance(photo, str) and photo.startswith("data:image")

def avatar_html(name, photo=None, size=44, extra=""):
    cls = ("avatar " + extra).strip()
    base = (f"width:{size}px;height:{size}px;"
            f"min-width:{size}px;flex-shrink:0;")
    if has_photo(photo):
        style = (base + f"background-image:url('{photo}');"
                 "background-size:cover;background-position:center;"
                 "background-repeat:no-repeat;")
        return (f'<div class="{cls}" style="{style}" role="img" '
                f'aria-label="{_esc(name)}"></div>')
    style = base + f"font-size:{max(11, int(size * 0.38))}px;"
    return f'<div class="{cls}" style="{style}">{_esc(initials(name))}</div>'

def whatsapp_digits(phone):
    digits = re.sub(r"\D", "", str(phone or ""))
    if digits.startswith("00"):
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = "234" + digits[1:]
    return digits

def member_code(member_id):
    """Short code for a member. Printed on QR codes, cards and key fobs."""
    return str(member_id).replace("-", "")[:8].upper()


def qr_data_uri(text):
    try:
        import qrcode
        img = qrcode.make(text)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""

# ----------------------------------------------------------- components
def page_header(title, subtitle="", eyebrow=""):
    parts = []
    if eyebrow:
        parts.append(f'<div class="pg-eyebrow">{_esc(eyebrow)}</div>')
    parts.append(f'<div class="pg-title">{_esc(title)}</div>')
    if subtitle:
        parts.append(f'<div class="pg-sub">{_esc(subtitle)}</div>')
    parts.append(f'<div class="pg-date">{today_local():%A, %d %B %Y}</div>')
    _md('<div class="pg-head">' + "".join(parts) + "</div>")

def chip(text, tone="grey", dot=False, href=None):
    cls = f"chip chip-{tone}" + (" chip-dot" if dot else "")
    if href:
        return (f'<a class="{cls}" href="{_esc(href)}" target="_blank" '
                f'rel="noopener">{_esc(text)}</a>')
    return f'<span class="{cls}">{_esc(text)}</span>'

RISK_TONE = {"High": "red", "Medium": "amber", "Low": "lime"}

def risk_chip(level, prob=None):
    text = str(level).upper() if prob is None else f"{str(level).upper()} · {prob:.0%}"
    return chip(text, RISK_TONE.get(level, "grey"), dot=True)

def kpi_card(label, value, tone="lime", hint=""):
    colour = TONES.get(tone, tone)
    hint_html = f'<div class="kpi-hint">{_esc(hint)}</div>' if hint else ""
    return (f'<div class="kpi" style="--tone:{colour}">'
            f'<div class="kpi-label">{_esc(label)}</div>'
            f'<div class="kpi-value">{_esc(value)}</div>{hint_html}</div>')

PILL_TONES = {
    # common status words → colour, so tables look the same everywhere
    "active": "lime", "paid": "lime", "paying": "lime", "sent": "lime", "kept": "lime", "on": "lime",
    "yes": "lime", "done": "lime", "hit": "lime", "fixed": "lime", "free": "cyan", "free access": "cyan",
    "trial": "cyan", "free trial": "cyan", "new member": "cyan", "invited": "cyan", "staff": "cyan",
    "owner": "lime", "pending": "amber", "paused": "amber", "skipped": "amber", "waiting": "amber",
    "problem": "amber", "medium": "amber", "expired": "red", "ended": "red", "suspended": "red",
    "failed": "red", "lost": "red", "high": "red", "cancelled": "red", "not seen": "grey", "off": "grey",
}


def _cell(value):
    if value is None:
        return "–"
    try:
        if pd.isna(value):
            return "–"
    except (TypeError, ValueError):
        pass
    if isinstance(value, float):
        return f"{value:,.0f}" if value == int(value) else f"{value:,.2f}"
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value:,}"
    return str(value)


def _is_num(text):
    t = text.replace(",", "").replace("₦", "").replace("%", "").replace("–", "").strip()
    try:
        float(t)
        return bool(t)
    except ValueError:
        return False


def table_html(rows, pills=(), wide=(), max_height=520, empty="Nothing here yet."):
    """A clean, modern table. rows: list of dicts or a DataFrame. pills: columns shown as
    status pills (colour from PILL_TONES, or a {column: {value: tone}} dict)."""
    if isinstance(rows, pd.DataFrame):
        rows = rows.to_dict("records")
    rows = list(rows or [])
    if not rows:
        return f'<div class="gp-tbl-empty">{_esc(empty)}</div>'
    cols = list(rows[0].keys())
    texts = [{c: _cell(r.get(c)) for c in cols} for r in rows]
    numeric = {c for c in cols if c not in pills and any(t[c] != "–" for t in texts)
               and all(_is_num(t[c]) or t[c] == "–" for t in texts)}
    tone_map = pills if isinstance(pills, dict) else {}
    head = "".join(f'<th class="{"num" if c in numeric else ""}">{_esc(c)}</th>' for c in cols)
    body = []
    for t in texts:
        cells = []
        for i, c in enumerate(cols):
            v = t[c]
            if c in pills and v != "–":
                tone = (tone_map.get(c) or {}).get(v) or PILL_TONES.get(v.lower(), "grey")
                inner = f'<span class="gp-pill gp-pill-{tone}">{_esc(v)}</span>'
            else:
                inner = _esc(v)
            cls = " ".join(x for x in ("num" if c in numeric else "", "first" if i == 0 else "",
                                       "wide" if c in wide else "") if x)
            cells.append(f'<td class="{cls}">{inner}</td>')
        body.append("<tr>" + "".join(cells) + "</tr>")
    return (f'<div class="gp-tbl-wrap" style="max-height:{int(max_height)}px"><table class="gp-tbl">'
            f'<thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>')


def table(rows, pills=(), wide=(), max_height=520, empty="Nothing here yet.", caption=None, target=None):
    _md(table_html(rows, pills, wide, max_height, empty), target)
    if caption:
        (target or st).caption(caption)


def intro(title, icon, text):
    """The header card at the top of a tool: icon, title and one line on what it's for."""
    key = "intro_" + "".join(ch for ch in title.lower() if ch.isalnum())
    with st.container(key=key):
        st.markdown(f"**{icon} {title}**" if icon else f"**{title}**")
        st.markdown(f"<div class='gp-intro-s'>{_esc(text)}</div>", unsafe_allow_html=True)


def kpi_row(cards):
    cols = st.columns(len(cards))
    for col, card in zip(cols, cards):
        _md(kpi_card(*card), col)

def prob_bar(prob, level):
    colour = TONES[RISK_TONE.get(level, "grey")]
    width = max(0, min(100, round(float(prob) * 100)))
    return (f'<div class="pct">{width}%</div><div class="pbar">'
            f'<span style="width:{width}%;--tone:{colour}"></span></div>')

ICON_PATHS = {
    "chat": '<path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/>',
    "user": '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    "users": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
    "heart": '<path d="M19 14c1.5-1.5 3-3.2 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.8 0-3 .5-4.5 2-1.5-1.5-2.7-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4 3 5.5l7 7Z"/>',
}

def ic(name, size=22):
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
            'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
            f'stroke-linejoin="round">{ICON_PATHS[name]}</svg>')

def _ibtn(target, label, icon=None, **kw):
    if icon:
        try:
            return target.button(label, icon=icon, **kw)
        except TypeError:
            pass
    return target.button(label, **kw)

def _bump(key, default, step):
    st.session_state[key] = st.session_state.get(key, default) + step

# ------------------------------------------------- membership status
def membership_state(end, today=None):
    today = today or date.today()
    try:
        stamp = pd.to_datetime(end)
    except Exception:
        stamp = None
    if stamp is None or pd.isna(stamp):
        return {"key": "none", "label": "No plan set", "tone": "grey",
                "detail": "Record a renewal to set one", "end": None, "days": None}
    d = stamp.date()
    days = (d - today).days
    if days < 0:
        return {"key": "inactive", "label": "Inactive", "tone": "red",
                "detail": f"Expired {abs(days)} day{'s' if abs(days) != 1 else ''} ago",
                "end": d, "days": days}
    if days == 0:
        detail = "Expires today"
    elif days == 1:
        detail = "Expires tomorrow"
    else:
        detail = f"{days} days left"
    return {"key": "active", "label": "Active", "tone": "lime",
            "detail": detail, "end": d, "days": days}

def membership_chip(state):
    return chip(state["label"], state["tone"], dot=True)

def due_chip(due, status):
    if status == "Done":
        return ""
    try:
        d = date.fromisoformat(str(due)[:10])
    except ValueError:
        return ""
    delta = (d - date.today()).days
    if delta < 0:
        return chip(f"Overdue {abs(delta)}d", "red")
    if delta == 0:
        return chip("Due today", "amber")
    if delta == 1:
        return chip("Due tomorrow", "cyan")
    return chip(f"Due {d:%d %b}", "grey")

OUTCOME_TONE = {"Retained": "lime", "Cancelled": "red", "No response": "grey"}

def outcome_chip(outcome):
    if not outcome or (isinstance(outcome, float) and pd.isna(outcome)):
        return chip("No outcome", "grey")
    return chip(str(outcome), OUTCOME_TONE.get(str(outcome), "grey"), dot=True)

@contextmanager
def _section(title, use_expander=True, expanded=False):
    if use_expander:
        with st.expander(title, expanded=expanded):
            yield
    else:
        yield

# ---------------------------------------------------------------- charts
def _style_chart(chart):
    return (chart.configure(background="rgba(0,0,0,0)")
            .configure_axis(labelColor=CHART_MUTED, titleColor=CHART_MUTED,
                            gridColor="rgba(255,255,255,0.07)",
                            domainColor="rgba(255,255,255,0.15)",
                            tickColor="rgba(255,255,255,0.15)")
            .configure_legend(labelColor="#F4F7FB", titleColor=CHART_MUTED)
            .configure_view(strokeWidth=0))

def _show_chart(chart):
    try:
        st.altair_chart(chart, use_container_width=True, theme=None)
    except TypeError:
        st.altair_chart(chart, use_container_width=True)


def modern_line_chart(df):
    """Line chart of cancellation estimate vs days since last visit."""
    data = df[["days_since_last_visit", "cancellation_probability"]].copy()
    data["days_since_last_visit"] = pd.to_numeric(
        data["days_since_last_visit"], errors="coerce")
    data["cancellation_probability"] = pd.to_numeric(
        data["cancellation_probability"], errors="coerce")
    data = data.dropna()
    try:
        import altair as alt
        line = (
            alt.Chart(data)
            .mark_line(color="#B7F34A", strokeWidth=3, interpolate="monotone",
                       point=alt.OverlayMarkDef(color="#B7F34A", size=70, filled=True))
            .encode(
                x=alt.X("days_since_last_visit:Q", title="Days since last visit",
                        axis=alt.Axis(tickMinStep=1, format="d")),
                y=alt.Y("cancellation_probability:Q", title="Cancellation estimate",
                        scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format="%")),
                tooltip=[
                    alt.Tooltip("days_since_last_visit:Q", title="Days away"),
                    alt.Tooltip("cancellation_probability:Q", title="Estimate", format=".0%"),
                ],
            )
        )
        rules = (
            alt.Chart(pd.DataFrame({"y": [0.3, 0.5]}))
            .mark_rule(strokeDash=[5, 5], color="rgba(255,255,255,0.28)")
            .encode(y=alt.Y("y:Q", scale=alt.Scale(domain=[0, 1])))
        )
        _show_chart(_style_chart(alt.layer(rules, line).properties(height=320)))
    except Exception:
        st.line_chart(data.set_index("days_since_last_visit"))


def data_card(rows, cols, key_prefix, tone="cyan", empty="Nothing here yet."):
    if not rows:
        st.caption(empty)
        return
    with st.container(border=True, key=f"card_{key_prefix}"):
        for i, row in enumerate(rows):
            divider = ('<hr style="border:none;border-top:1px solid '
                       'rgba(255,255,255,0.07);margin:6px 0;">') if i else ""
            kv = "".join(
                f'<div class="kv"><span>{_esc(label)}</span>'
                f'<b>{_esc(row.get(field, "—"))}</b></div>'
                for field, label in cols
            )
            _md(divider + f'<div class="panel" style="margin:0 0 4px;'
                f'border-top:3px solid {TONES[tone]};padding:12px 16px;">'
                f'{kv}</div>')

# ------------------------------------------------------------------ CSS
UI_CSS = """
.pg-head { margin: 2px 0 20px; }
.pg-eyebrow { color: var(--lime); font-size: 11px; font-weight: 800;
    letter-spacing: 2px; text-transform: uppercase; margin-bottom: 6px; }
.pg-title { font-size: 32px; font-weight: 800; letter-spacing: -1.2px;
    color: #F4F7FB; line-height: 1.12; }
.pg-date { color: #9AA8BD; font-size: 12px; font-weight: 600; margin-top: 8px; letter-spacing: .3px; }
.pg-sub { color: #9AA8BD; font-size: 14px; line-height: 1.6; margin-top: 6px; max-width: 760px; }

.kpi { position: relative; overflow: hidden; height: 100%;
    background: linear-gradient(160deg, #1A2540 0%, #141C30 100%);
    border: 1px solid rgba(255,255,255,0.09); border-radius: 18px;
    padding: 16px 18px 15px 22px; }
.kpi::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0;
    width: 5px; background: var(--tone); }
.kpi::after { content: ""; position: absolute; right: -30px; top: -30px;
    width: 90px; height: 90px; border-radius: 50%;
    background: radial-gradient(circle, var(--tone), transparent 70%); opacity: 0.12; }
.kpi-label { font-size: 11px; font-weight: 800; letter-spacing: 1.2px;
    text-transform: uppercase; color: #9AA8BD; }
.kpi-value { font-size: 30px; font-weight: 800; letter-spacing: -1px;
    color: var(--tone); margin-top: 4px; line-height: 1.1; }
.kpi-hint { font-size: 12px; color: #9AA8BD; margin-top: 4px; }

.chip-row { display: flex; flex-wrap: wrap; gap: 6px; margin: 6px 0; }
.chip { display: inline-flex; align-items: center; gap: 6px; padding: 4px 11px;
    border-radius: 999px; font-size: 11px; font-weight: 800; letter-spacing: 0.3px;
    text-decoration: none !important; white-space: nowrap; }
.chip-dot::before { content: ""; width: 7px; height: 7px; border-radius: 50%;
    background: currentColor; }
.chip-lime { background: rgba(183,243,74,0.16); color: #B7F34A !important; }
.chip-red { background: rgba(255,107,107,0.16); color: #FF8A8A !important; }
.chip-amber { background: rgba(255,196,77,0.16); color: #FFC44D !important; }
.chip-cyan { background: rgba(53,214,237,0.14); color: #35D6ED !important; }
.chip-grey { background: rgba(154,168,189,0.16); color: #D5DDEA !important; }
a.chip:hover { filter: brightness(1.25); }

.avatar { border-radius: 50%; object-fit: cover; display: grid; place-items: center;
    background: linear-gradient(145deg, #B7F34A, #35D6ED); color: #10182A;
    font-weight: 800; border: 2px solid rgba(255,255,255,0.12); box-sizing: border-box; }
.avatar-ring { border: 3px solid #B7F34A;
    box-shadow: 0 0 0 5px rgba(183,243,74,0.14), 0 14px 40px rgba(0,0,0,0.45); }

[class*="st-key-mrow_"] button {
    background: transparent !important; border: none !important;
    box-shadow: none !important; min-height: 0 !important;
    padding: 6px 8px !important; justify-content: flex-start !important; }
[class*="st-key-mrow_"] button p {
    color: #F4F7FB !important; font-size: 15px !important;
    font-weight: 700 !important; text-align: left !important; }
[class*="st-key-mrow_"] button:hover { background: rgba(183,243,74,0.10) !important; }
[class*="st-key-mrow_"] button:hover p { color: #B7F34A !important; text-decoration: underline; }
.why { color: #9AA8BD; font-size: 12px; line-height: 1.4; padding: 0 8px; }
.pct { font-size: 13px; font-weight: 800; color: #F4F7FB; }
.pbar { height: 8px; border-radius: 99px; background: rgba(255,255,255,0.08);
    overflow: hidden; margin-top: 4px; }
.pbar > span { display: block; height: 100%; border-radius: 99px; background: var(--tone); }
.th { font-size: 11px; font-weight: 800; letter-spacing: 1.2px; color: #9AA8BD;
    text-transform: uppercase; padding: 0 4px 6px; }
.money { font-weight: 700; color: #F4F7FB; font-size: 14px; }

[class*="st-key-card_"] {
    background: linear-gradient(160deg, rgba(27,38,59,0.78), rgba(20,28,46,0.92));
    border: 1px solid rgba(255,255,255,0.09) !important;
    border-radius: 16px !important; transition: border-color .2s ease; }
[class*="st-key-card_"]:hover { border-color: rgba(183,243,74,0.35) !important; }

.profile-hero { display: flex; align-items: center; gap: 24px; padding: 24px 26px;
    border-radius: 24px; border: 1px solid rgba(255,255,255,0.09); margin: 10px 0 18px;
    background: radial-gradient(circle at 0% 0%, rgba(183,243,74,0.14), transparent 45%),
                linear-gradient(120deg, #17243A, #121B2E); }
.profile-hero .avatar { flex-shrink: 0; }
.profile-name { font-size: 30px; font-weight: 800; letter-spacing: -1px; color: #F4F7FB; }
.panel { background: #141C30; border: 1px solid rgba(255,255,255,0.09);
    border-radius: 18px; padding: 18px 20px; margin: 8px 0 14px; }
.panel h4 { margin: 0 0 8px; font-size: 15px; color: #F4F7FB; }
.panel p, .panel div { color: #D5DDEA; }
.kv { display: flex; justify-content: space-between; gap: 12px; padding: 9px 0;
    border-bottom: 1px solid rgba(255,255,255,0.07); font-size: 14px; }
.kv:last-child { border-bottom: none; }
.kv span { color: #9AA8BD; }
.kv b { color: #F4F7FB; text-align: right; }
.status-big { display: flex; align-items: center; gap: 14px; padding: 16px 18px;
    border-radius: 16px; margin-bottom: 12px; border: 1px solid var(--tone);
    background: rgba(255,255,255,0.03); }
.status-big .sb-title { font-size: 22px; font-weight: 800; color: var(--tone); }
.status-big .sb-sub { color: #BCC8D8; font-size: 13px; }

.kb-head { display: flex; justify-content: space-between; align-items: center;
    padding: 10px 14px; border-radius: 14px; margin-bottom: 10px;
    background: rgba(255,255,255,0.04); border-top: 3px solid var(--tone);
    font-weight: 800; color: #F4F7FB; }
.kb-head b { background: var(--tone); color: #10182A; border-radius: 999px;
    padding: 1px 10px; font-size: 12px; }
.kb-empty { border: 1px dashed rgba(255,255,255,0.14); border-radius: 14px;
    padding: 18px; text-align: center; color: #9AA8BD; font-size: 13px; }
.board-progress { padding: 16px 18px; border-radius: 18px; margin: 4px 0 6px;
    background: linear-gradient(160deg, #1A2540, #141C30);
    border: 1px solid rgba(255,255,255,0.09); }
.bp-top { display: flex; justify-content: space-between; color: #F4F7FB;
    font-weight: 800; font-size: 14px; }
.bp-top b { color: #B7F34A; }
.bp-sub { color: #9AA8BD; font-size: 12px; margin-top: 8px; }
.board-progress .pbar { height: 10px; }

.archie-hero { position: relative; overflow: hidden; display: flex; align-items: center;
    gap: 26px; padding: 24px 28px; border-radius: 26px; margin: 4px 0 16px;
    border: 1px solid rgba(255,255,255,0.09);
    background: radial-gradient(circle at 0% 0%, rgba(183,243,74,0.16), transparent 42%),
                radial-gradient(circle at 100% 100%, rgba(53,214,237,0.12), transparent 40%),
                linear-gradient(120deg, #0D1424, #141C30); }
.archie-orb { width: 150px; height: 150px; flex-shrink: 0; }
.archie-meta { min-width: 0; }
.archie-name { font-size: 30px; font-weight: 800; letter-spacing: -1px; color: #F4F7FB; }
.archie-role { color: #BCC8D8; font-size: 14px; margin-top: 2px; }
.archie-status { display: flex; align-items: center; gap: 8px; margin-top: 12px;
    color: #B7F34A; font-size: 12px; font-weight: 800; letter-spacing: .4px; }
.archie-status .dot { width: 8px; height: 8px; border-radius: 50%; background: #B7F34A;
    animation: lp-pulse 1.8s infinite; }
.archie-wave { display: inline-flex; align-items: flex-end; gap: 3px; height: 18px; margin-left: 6px; }
.archie-wave i { width: 3px; height: 5px; border-radius: 3px; background: #B7F34A;
    animation: arch-wave 1.1s ease-in-out infinite; }
.archie-wave i:nth-child(2) { animation-delay: .15s; }
.archie-wave i:nth-child(3) { animation-delay: .30s; }
.archie-wave i:nth-child(4) { animation-delay: .45s; }
.archie-wave i:nth-child(5) { animation-delay: .60s; }
.thinking-on .archie-wave i { background: #35D6ED; animation-duration: .55s; }
.typing { display: inline-flex; gap: 5px; padding: 6px 2px; }
.typing i { width: 8px; height: 8px; border-radius: 50%; background: #B7F34A;
    animation: arch-type 1s ease-in-out infinite; }
.typing i:nth-child(2) { animation-delay: .15s; }
.typing i:nth-child(3) { animation-delay: .30s; }
@keyframes arch-wave { 0%,100% { height: 5px; } 50% { height: 18px; } }
@keyframes arch-type { 0%,100% { transform: translateY(0); opacity: .4; }
    50% { transform: translateY(-5px); opacity: 1; } }
[class*="st-key-ap_"] button {
    background: rgba(255,255,255,0.04) !important; border: 1px solid rgba(255,255,255,0.12) !important;
    border-radius: 14px !important; min-height: 64px; }
[class*="st-key-ap_"] button p { color: #F4F7FB !important; font-weight: 700 !important;
    font-size: 13px !important; line-height: 1.35 !important; }
[class*="st-key-ap_"] button:hover { background: rgba(183,243,74,0.12) !important;
    border-color: #B7F34A !important; }
[class*="st-key-ap_"] button:hover p { color: #B7F34A !important; }

.archie-bot { width: 100%; height: 100%; overflow: visible;
    animation: bot-float 4s ease-in-out infinite;
    filter: drop-shadow(0 14px 26px rgba(183,243,74,.30)); }
.archie-bot * { transform-box: fill-box; }
.bot-halo { transform-origin: center; animation: bot-halo 3s ease-in-out infinite; }
.bot-eye { transform-origin: center; animation: bot-blink 4.5s ease-in-out infinite; }
.bot-eye2 { animation-delay: .05s; }
.bot-mouth { transform-origin: center; animation: bot-talk 3.4s ease-in-out infinite; }
.bot-ball { transform-origin: center; animation: bot-glow 1.6s ease-in-out infinite; }
.thinking .bot-halo { animation-duration: .9s; }
.thinking .bot-eye { animation: bot-look 1s ease-in-out infinite; }
.thinking .bot-mouth { animation-duration: .4s; }
.archie-hero.thinking-on { border-color: rgba(183,243,74,.55);
    box-shadow: 0 0 44px rgba(183,243,74,.16); }
@keyframes bot-float { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-9px); } }
@keyframes bot-halo { 0%,100% { transform: scale(.94); opacity: .22; } 50% { transform: scale(1.06); opacity: .45; } }
@keyframes bot-blink { 0%,44%,50%,100% { transform: scaleY(1); } 47% { transform: scaleY(.08); } }
@keyframes bot-look { 0%,100% { transform: translateX(-5px); } 50% { transform: translateX(5px); } }
@keyframes bot-glow { 0%,100% { opacity: .55; transform: scale(.85); } 50% { opacity: 1; transform: scale(1.25); } }
@keyframes bot-talk { 0%,100% { transform: scaleY(1); } 50% { transform: scaleY(1.8) translateY(1px); } }
@keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
.think-label { font-size: 13px; font-weight: 700; color: transparent;
    background: linear-gradient(90deg, #9AA8BD, #F4F7FB, #9AA8BD); background-size: 200% 100%;
    -webkit-background-clip: text; background-clip: text; animation: shimmer 1.6s linear infinite; }
.skel i { display: block; height: 10px; border-radius: 6px; margin-top: 9px;
    background: linear-gradient(90deg, rgba(255,255,255,.06), rgba(183,243,74,.30), rgba(255,255,255,.06));
    background-size: 200% 100%; animation: shimmer 1.4s linear infinite; }
.skel i:nth-child(1) { width: 92%; } .skel i:nth-child(2) { width: 78%; } .skel i:nth-child(3) { width: 55%; }

.bubble-in, .bubble-out { padding: 10px 14px; font-size: 14px; line-height: 1.55;
    color: #F4F7FB; white-space: pre-wrap; margin-top: 6px; max-width: 760px; }
.bubble-in { background: rgba(255,255,255,0.06); border-radius: 4px 16px 16px 16px; }
.bubble-out { background: rgba(183,243,74,0.13); border: 1px solid rgba(183,243,74,.28);
    border-radius: 16px 4px 16px 16px; }
.pillar { height: 100%; padding: 16px 16px 14px; border-radius: 18px;
    background: linear-gradient(160deg, #1A2540, #141C30); border: 1px solid rgba(255,255,255,0.09);
    border-top: 3px solid var(--tone); }
.pillar-ic { color: var(--tone); margin-bottom: 8px; }
.pillar h4 { margin: 0 0 4px; font-size: 15px; color: #F4F7FB; }
.pillar p { margin: 0 0 8px; font-size: 12px; line-height: 1.5; color: #9AA8BD; }
.pillar .pn { font-size: 11px; color: #9AA8BD; margin-top: 6px; }
[class*="st-key-follow_"] button {
    background: transparent !important; border: 1px solid rgba(183,243,74,.6) !important;
    border-radius: 999px !important; min-height: 34px !important; box-shadow: none !important; }
[class*="st-key-follow_"] button p { color: #B7F34A !important; font-size: 12px !important; }
[class*="st-key-follow_"] button:hover { background: #B7F34A !important; }
[class*="st-key-follow_"] button:hover p { color: #10182A !important; }
.lp-archie { display: grid; grid-template-columns: 220px 1fr; gap: 28px; align-items: center;
    padding: 28px; border-radius: 26px; border: 1px solid rgba(255,255,255,0.09);
    background: radial-gradient(circle at 0% 0%, rgba(183,243,74,0.14), transparent 45%),
                linear-gradient(120deg, #17243A, #121B2E); }
.lp-archie-bot { width: 190px; height: 190px; margin: 0 auto; }
.lp-archie-bot .archie-bot { animation: bot-float 4s ease-in-out infinite; }
.lp-chat { display: flex; flex-direction: column; gap: 10px; }
.lp-msg { max-width: 560px; padding: 11px 15px; border-radius: 16px; font-size: 14px; line-height: 1.55; }
.lp-msg.me { align-self: flex-end; background: #B7F34A; color: #10182A; font-weight: 700; border-radius: 16px 16px 4px 16px; }
.lp-msg.ai { align-self: flex-start; background: rgba(255,255,255,0.07); color: #F4F7FB; border-radius: 16px 16px 16px 4px; }
.lp-send { align-self: flex-start; font-size: 12px; font-weight: 800; letter-spacing: .6px; color: #B7F34A; }

.boot-overlay { position: fixed; inset: 0; z-index: 99999; display: flex;
    flex-direction: column; align-items: center; justify-content: center; gap: 16px;
    background: #0B1020; color: #F4F7FB; font-weight: 700; font-size: 15px; }
.boot-spin { width: 46px; height: 46px; border-radius: 50%;
    border: 4px solid rgba(183,243,74,.2); border-top-color: #B7F34A;
    animation: boot-spin .9s linear infinite; }
@keyframes boot-spin { to { transform: rotate(360deg); } }

.stApp { background:
    radial-gradient(1100px 560px at 8% -8%, rgba(183,243,74,0.07), transparent 60%),
    radial-gradient(900px 480px at 100% 0%, rgba(53,214,237,0.06), transparent 55%), #0B1020 !important; }
[data-stale="true"] { opacity: 1 !important; transition: none !important; }
.lp-hero::before, .lp-hero::after { filter: none !important; }
.lp-radar, .lp-pill, .st-key-auth_card { backdrop-filter: none !important; }
div[data-baseweb="input"]:focus-within, div[data-baseweb="select"]:focus-within > div,
textarea:focus { border-color: #B7F34A !important; box-shadow: 0 0 0 2px rgba(183,243,74,.22) !important; }
::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,.14); border-radius: 8px; }
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { animation-duration: .01ms !important;
        animation-iteration-count: 1 !important; transition-duration: .01ms !important; }
}
@media (max-width: 800px) { .lp-archie { grid-template-columns: 1fr; } }

[class*="st-key-qa_"] button {
    background: linear-gradient(160deg, #1A2540, #141C30) !important;
    border: 1px solid rgba(255,255,255,0.10) !important; border-radius: 16px !important;
    min-height: 74px; justify-content: flex-start !important; padding: 12px 16px !important; }
[class*="st-key-qa_"] button p { color: #F4F7FB !important; font-weight: 800 !important;
    font-size: 15px !important; text-align: left !important; }
[class*="st-key-qa_"] button:hover { border-color: #B7F34A !important;
    background: rgba(183,243,74,0.10) !important; }
[class*="st-key-qa_"] button:hover p { color: #B7F34A !important; }

[data-testid="stExpander"] { border: 1px solid rgba(255,255,255,0.09) !important;
    border-radius: 16px !important; background: rgba(21,29,48,0.6); }
button[data-baseweb="tab"] p { font-weight: 700; }
button[data-baseweb="tab"][aria-selected="true"] p { color: #B7F34A !important; }
[data-baseweb="tab-highlight"] { background-color: #B7F34A !important; }
span[data-baseweb="tag"] { background: rgba(183,243,74,0.16) !important; }
span[data-baseweb="tag"] span { color: #B7F34A !important; }

@media (max-width: 640px) {
    .pg-title { font-size: 26px; }
    .profile-hero, .archie-hero { flex-direction: column; text-align: center; }
    .chip-row { justify-content: center; }
    [data-testid="stHorizontalBlock"]:has(.kpi) { flex-wrap: wrap !important; gap: .6rem !important; }
    [data-testid="stHorizontalBlock"]:has(.kpi) > [data-testid="stColumn"] {
        flex: 1 1 calc(50% - .6rem) !important; min-width: calc(50% - .6rem) !important; }
    [data-testid="stHorizontalBlock"]:has(.row-tight) { flex-wrap: nowrap !important; }
    [data-testid="stHorizontalBlock"]:has(.row-tight) > [data-testid="stColumn"] { min-width: 0 !important; }
}
"""

MOBILE_ROWS_CSS = """
.avatar { border-radius: 50% !important; overflow: hidden; }

@media (max-width: 640px) {
    [data-testid="stHorizontalBlock"]:has(.th) { display: none !important; }

    [data-testid="stHorizontalBlock"]:has(.row-tight):not(:has(.kb-head)) {
        flex-wrap: wrap !important;
        gap: 0.4rem 0.6rem !important;
        align-items: center !important;
    }
    [data-testid="stHorizontalBlock"]:has(.row-tight):not(:has(.kb-head)) > [data-testid="stColumn"] {
        flex: 1 1 calc(50% - 0.6rem) !important;
        width: auto !important;
        min-width: calc(50% - 0.6rem) !important;
    }
    [data-testid="stHorizontalBlock"]:has(.row-tight):not(:has(.kb-head)) > [data-testid="stColumn"]:nth-child(1) {
        flex: 0 0 56px !important;
        width: 56px !important;
        min-width: 56px !important;
    }
    [data-testid="stHorizontalBlock"]:has(.row-tight):not(:has(.kb-head)) > [data-testid="stColumn"]:nth-child(2) {
        flex: 1 1 calc(100% - 72px) !important;
        width: calc(100% - 72px) !important;
        min-width: 0 !important;
    }
    [data-testid="stHorizontalBlock"]:has(.kb-head) {
        flex-wrap: wrap !important;
    }
    [data-testid="stHorizontalBlock"]:has(.kb-head) > [data-testid="stColumn"] {
        flex: 1 1 100% !important;
        width: 100% !important;
        min-width: 100% !important;
    }
}
"""

# Payments & Renewals keeps this grid layout (it looks good on phones).
ALL_ROWS_MOBILE_CSS = """
@media (max-width: 768px) {
    [class*="st-key-card_pay_"] [data-testid="stHorizontalBlock"]:has(.row-tight) {
        display: grid !important;
        grid-template-columns: 52px minmax(0, 1fr) minmax(0, 1fr) !important;
        column-gap: 12px !important;
        row-gap: 6px !important;
        align-items: center !important;
        padding: 6px 0 10px !important;
    }
    [class*="st-key-card_pay_"] [data-testid="stHorizontalBlock"]:has(.row-tight) > [data-testid="stColumn"] {
        width: auto !important;
        min-width: 0 !important;
        flex: none !important;
    }
    [class*="st-key-card_pay_"] [data-testid="stHorizontalBlock"]:has(.row-tight) > [data-testid="stColumn"]:nth-child(1) {
        grid-column: 1 !important;
        grid-row: 1 / span 4 !important;
        align-self: start !important;
    }
    [class*="st-key-card_pay_"] [data-testid="stHorizontalBlock"]:has(.row-tight) > [data-testid="stColumn"]:nth-child(2) {
        grid-column: 2 / -1 !important;
        grid-row: 1 !important;
    }
    [class*="st-key-card_pay_"] [class*="st-key-mrow_"] button {
        justify-content: flex-start !important;
        text-align: left !important;
        padding-left: 0 !important;
    }
    [class*="st-key-card_pay_"] [class*="st-key-mrow_"] button p { text-align: left !important; }
    [class*="st-key-card_pay_"] .why {
        padding: 0 !important;
        text-align: left !important;
        white-space: normal !important;
    }
    [class*="st-key-card_pay_"] [data-testid="stHorizontalBlock"]:has(.row-tight) > [data-testid="stColumn"]:nth-child(3) { grid-column: 2 !important; grid-row: 2 !important; }
    [class*="st-key-card_pay_"] [data-testid="stHorizontalBlock"]:has(.row-tight) > [data-testid="stColumn"]:nth-child(4) { grid-column: 3 !important; grid-row: 2 !important; }
    [class*="st-key-card_pay_"] [data-testid="stHorizontalBlock"]:has(.row-tight) > [data-testid="stColumn"]:nth-child(5) { grid-column: 2 / -1 !important; grid-row: 3 !important; }
    [class*="st-key-card_pay_"] [data-testid="stColumn"] [data-testid="stMarkdownContainer"] {
        display: flex !important;
        flex-wrap: wrap !important;
        gap: 6px !important;
    }
}
"""


def _mobile():
    try:
        ua = st.context.headers.get("User-Agent", "").lower()
    except Exception:
        return False
    return any(w in ua for w in ("iphone", "android", "mobile"))


def mobile_member_card(r, key, why="", chips="", bar="", meta="", actions=()):
    """One stacked card per member for phones. No columns, so nothing overlaps."""
    with st.container(border=True, key=f"card_m_{key}_{r['id']}"):
        head = (
            '<div style="display:flex;align-items:center;gap:12px;">'
            + avatar_html(r["full_name"], r.get("photo"), 48)
            + '<div style="min-width:0;">'
            + f'<div style="font-weight:800;color:#F4F7FB;font-size:16px;">{_esc(r["full_name"])}</div>'
            + (f'<div class="why" style="padding:2px 0 0;">{_esc(why)}</div>' if why else "")
            + "</div></div>"
        )
        _md(head)
        if chips:
            _md(f'<div class="chip-row">{chips}</div>')
        if bar:
            _md(bar)
        if meta:
            _md(meta)
        for label, k, callback, args in actions:
            st.button(label, key=f"{k}_{r['id']}", on_click=callback,
                      args=args, use_container_width=True)


CHAT_CSS = """
[class*="st-key-pp_"] button {
    background: rgba(255,255,255,0.05) !important;
    border: 1px solid rgba(255,255,255,0.14) !important;
    border-radius: 999px !important; min-height: 32px !important;
    box-shadow: none !important; margin-top: 4px;
}
[class*="st-key-pp_"] button p { font-size: 12px !important; font-weight: 700 !important; color: #F4F7FB !important; }
[class*="st-key-pp_"] button:hover { background: #B7F34A !important; border-color: #B7F34A !important; }
[class*="st-key-pp_"] button:hover p { color: #10182A !important; }
[class*="st-key-mention_"] button {
    background: rgba(183,243,74,0.12) !important;
    border: 1px solid rgba(183,243,74,0.45) !important;
    border-radius: 999px !important;
    min-height: 36px !important;
    padding: 0 16px 0 8px !important;
    box-shadow: none !important;
    justify-content: flex-start !important;
}
[class*="st-key-mention_"] button p {
    color: #B7F34A !important;
    font-size: 13px !important;
    font-weight: 800 !important;
}
[class*="st-key-mention_"] button:hover { background: #B7F34A !important; }
[class*="st-key-mention_"] button:hover p { color: #10182A !important; }
[data-testid="stChatMessage"] {
    background: linear-gradient(160deg, rgba(27,38,59,0.85), rgba(16,24,42,0.95)) !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-left: 3px solid #B7F34A !important;
    border-radius: 6px 22px 22px 22px !important;
    padding: 14px 18px !important;
    gap: 14px !important;
    margin-bottom: 10px !important;
    max-width: 880px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.25);
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
    flex-direction: row-reverse !important;
    margin-left: auto !important;
    max-width: 82%;
    background: linear-gradient(160deg, rgba(183,243,74,0.16), rgba(53,214,237,0.08)) !important;
    border: 1px solid rgba(183,243,74,0.30) !important;
    border-radius: 22px 6px 22px 22px !important;
}
[data-testid="stChatMessageContent"] { min-width: 0; }
[data-testid="stChatMessageAvatarAssistant"],
[data-testid="stChatMessageAvatarUser"] {
    width: 44px !important; height: 44px !important; min-width: 44px !important;
    border-radius: 50% !important; background: transparent !important;
    overflow: visible !important;
}
[data-testid="stChatMessageAvatarAssistant"] {
    box-shadow: 0 0 24px rgba(183,243,74,0.35) !important;
    animation: bot-float 4s ease-in-out infinite !important;
}
[data-testid="stChatMessageAvatarAssistant"] *,
[data-testid="stChatMessageAvatarUser"] * { opacity: 1 !important; }
[data-testid="stChatMessageAvatarAssistant"] img,
[data-testid="stChatMessageAvatarUser"] img {
    width: 100% !important; height: 100% !important;
    border-radius: 50% !important; object-fit: cover !important;
}
.chat-who { display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
    margin-bottom: 4px; font-size: 13px; color: #F4F7FB; }
.chat-who b { font-weight: 800; }
.chat-who-user { justify-content: flex-end; }
.chat-tag { font-size: 10px; font-weight: 800; letter-spacing: .6px;
    text-transform: uppercase; padding: 2px 9px; border-radius: 999px;
    background: rgba(183,243,74,0.16); color: #B7F34A; }
.chat-gym { background: rgba(53,214,237,0.14); color: #35D6ED; }
[data-testid="stChatInput"] { border-radius: 999px !important;
    background: #111B2D !important; border: 1px solid rgba(255,255,255,0.14) !important; }
[data-testid="stChatInput"]:focus-within { border-color: #B7F34A !important;
    box-shadow: 0 0 0 2px rgba(183,243,74,0.22) !important; }
[class*="st-key-ap_"] button p { white-space: normal !important;
    overflow: visible !important; text-overflow: clip !important; }

@media (max-width: 768px) {
    [data-testid="stChatMessage"] { padding: 12px 14px !important; gap: 10px !important; }
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) { max-width: 94%; }
    [data-testid="stChatMessageAvatarAssistant"],
    [data-testid="stChatMessageAvatarUser"] {
        width: 36px !important; height: 36px !important; min-width: 36px !important;
    }
    .chat-who { font-size: 12px; }
}
"""


DESIGN_CSS = """
/* =====================================================================
   GymPulse design system
   Tokens, button hierarchy, typography, spacing, accessibility
   ===================================================================== */
:root {
    --fs-xs: 12px; --fs-sm: 13px; --fs-md: 15px; --fs-lg: 18px;
    --fs-xl: 24px; --fs-2xl: 28px;
    --sp-1: 4px; --sp-2: 8px; --sp-3: 12px; --sp-4: 16px; --sp-5: 24px; --sp-6: 32px;
    --surface-1: #121A2C; --surface-2: #151D30;
    --line: rgba(255,255,255,0.09); --line-strong: rgba(255,255,255,0.30);
    --text: #F4F7FB; --text-muted: #9AA8BD; --accent: #B7F34A;
}

/* ---------- 1. Layout and rhythm ---------- */
html body .block-container { max-width: 1320px; padding-bottom: 4rem; }
html body .stApp { background: #0B1020 !important; }
html body h1, html body h2, html body h3 { font-weight: 700 !important; letter-spacing: -0.3px; }

/* ---------- 2. Typography scale ---------- */
html body .pg-head { margin: 4px 0 var(--sp-5); }
html body .pg-eyebrow { color: var(--text-muted); font-size: var(--fs-xs); font-weight: 600;
    letter-spacing: 1.2px; margin-bottom: var(--sp-2); }
html body .pg-title { font-size: var(--fs-2xl); font-weight: 700; letter-spacing: -0.6px;
    line-height: 1.2; }
html body .pg-sub { font-size: 14px; line-height: 1.55; color: var(--text-muted); max-width: 680px; }
html body .pg-date { font-size: var(--fs-xs); color: var(--text-muted); font-weight: 500; }
html body .section-label { color: var(--text-muted); font-size: var(--fs-xs); font-weight: 600;
    letter-spacing: 1.1px; margin: var(--sp-6) 0 var(--sp-3); }
html body .kpi-label { font-size: var(--fs-xs); font-weight: 600; letter-spacing: .6px; }
html body .kpi-value { font-size: 26px; font-weight: 700; letter-spacing: -0.6px;
    color: var(--text); }
html body .kpi-hint { font-size: var(--fs-xs); }
html body .why { font-size: var(--fs-sm); line-height: 1.5; }
html body .chip { font-size: var(--fs-xs); font-weight: 600; letter-spacing: .2px; }
html body .profile-name, html body .archie-name { font-weight: 700; letter-spacing: -0.5px; }
html body .kv { font-size: 14px; }

/* ---------- 3. Calmer surfaces: one accent, fewer glows ---------- */
html body .kpi { background: var(--surface-1); padding: var(--sp-4) var(--sp-4) var(--sp-4) 20px; }
html body .kpi::after { display: none; }
html body .panel { background: var(--surface-1); padding: var(--sp-4) 20px; }
html body .avatar-ring { box-shadow: none; border-width: 2px; }
html body .archie-bot { filter: none; }
html body [class*="st-key-card_"]:hover { border-color: var(--line-strong) !important; }
html body [data-testid="stChatMessage"] {
    background: var(--surface-1) !important; box-shadow: none !important;
    border: 1px solid var(--line) !important; border-radius: 16px !important; }
html body [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
    background: rgba(183,243,74,0.07) !important; border: 1px solid rgba(183,243,74,0.2) !important; }
html body [data-testid="stChatMessageAvatarAssistant"] { box-shadow: none !important;
    animation: none !important; }
html body [class*="st-key-mention_"] button {
    background: rgba(255,255,255,0.05) !important;
    border: 1px solid var(--line-strong) !important; }
html body [class*="st-key-mention_"] button p { color: var(--text) !important; font-weight: 600 !important; }
html body [class*="st-key-mention_"] button:hover { background: rgba(255,255,255,0.1) !important; }
html body [class*="st-key-mention_"] button:hover p { color: var(--text) !important; }
html body [class*="st-key-pp_"] button { border-color: var(--line-strong) !important; }
html body [class*="st-key-pp_"] button:hover { background: rgba(255,255,255,0.08) !important;
    border-color: var(--line-strong) !important; }
html body [class*="st-key-pp_"] button:hover p { color: var(--text) !important; }
html body [class*="st-key-ap_"] button:hover { background: rgba(255,255,255,0.07) !important;
    border-color: var(--line-strong) !important; }
html body [class*="st-key-ap_"] button:hover p { color: var(--text) !important; }
html body [class*="st-key-qa_"] button:hover { background: rgba(255,255,255,0.06) !important;
    border-color: var(--line-strong) !important; }
html body [class*="st-key-qa_"] button:hover p { color: var(--text) !important; }

/* ---------- 4. Top bar buttons: same size, no stray space ---------- */
html body .st-key-top_msg button, html body .st-key-top_menu button,
html body .st-key-top_profile button {
    width: 42px !important; height: 42px !important; min-height: 42px !important;
    min-width: 42px !important; padding: 0 !important; gap: 0 !important;
    display: inline-flex !important; align-items: center !important;
    justify-content: center !important; border-radius: 12px !important;
    background: rgba(255,255,255,0.07) !important; border: 1px solid var(--line-strong) !important; }
html body .st-key-top_msg button p, html body .st-key-top_menu button p {
    margin: 0 !important; line-height: 1 !important; }
html body .st-key-top_profile button { border-radius: 50% !important; overflow: hidden !important; }
html body .st-key-top_profile button > * { display: none !important; }
html body .st-key-top_profile button::before {
    width: 100% !important; height: 100% !important; margin: 0 !important;
    border: 0 !important; border-radius: 50% !important; }
html body .st-key-top_msg button:hover, html body .st-key-top_menu button:hover,
html body .st-key-top_profile button:hover { background: rgba(255,255,255,0.10) !important;
    border-color: rgba(255,255,255,0.40) !important; }

/* ---------- 4b. Pressed state: the only moment a secondary button is highlighted ---------- */
html body .stButton > button:active:not([data-testid^="stBaseButton-primary"]):not([class*="st-key-brand_home"] *),
html body .stFormSubmitButton > button:active:not([data-testid^="stBaseButton-primary"]),
html body .stDownloadButton > button:active:not([data-testid^="stBaseButton-primary"]),
html body .stLinkButton > a:active,
html body .st-key-top_msg button:active, html body .st-key-top_menu button:active,
html body .st-key-top_profile button:active {
    background-color: rgba(183,243,74,0.20) !important;
    border-color: var(--accent) !important;
    color: var(--text) !important; }
html body .stButton > button[data-testid^="stBaseButton-primary"]:active,
html body .stFormSubmitButton > button[data-testid^="stBaseButton-primary"]:active {
    background: #9FD83A !important; border-color: #9FD83A !important; }

/* ---------- 4c. Button labels: always readable ---------- */
body .stButton:where(:not([class*="st-key-brand_home"] *, [class*="st-key-to_signup"] *, [class*="st-key-to_login"] *, [class*="st-key-to_forgot"] *, [class*="st-key-back_to_login"] *, [class*="st-key-reset_other"] *, [class*="st-key-open_terms"] *, [class*="st-key-open_privacy"] *)) > button:where(:not([data-testid^="stBaseButton-primary"]):not([data-testid^="stBaseButton-tertiary"])) p,
body .stFormSubmitButton:where(:not([class*="st-key-brand_home"] *, [class*="st-key-to_signup"] *, [class*="st-key-to_login"] *, [class*="st-key-to_forgot"] *, [class*="st-key-back_to_login"] *, [class*="st-key-reset_other"] *, [class*="st-key-open_terms"] *, [class*="st-key-open_privacy"] *)) > button:where(:not([data-testid^="stBaseButton-primary"]):not([data-testid^="stBaseButton-tertiary"])) p,
body .stDownloadButton:where(:not([class*="st-key-brand_home"] *, [class*="st-key-to_signup"] *, [class*="st-key-to_login"] *, [class*="st-key-to_forgot"] *, [class*="st-key-back_to_login"] *, [class*="st-key-reset_other"] *, [class*="st-key-open_terms"] *, [class*="st-key-open_privacy"] *)) > button:where(:not([data-testid^="stBaseButton-primary"]):not([data-testid^="stBaseButton-tertiary"])) p,
body .stLinkButton:where(:not([class*="st-key-brand_home"] *, [class*="st-key-to_signup"] *, [class*="st-key-to_login"] *, [class*="st-key-to_forgot"] *, [class*="st-key-back_to_login"] *, [class*="st-key-reset_other"] *, [class*="st-key-open_terms"] *, [class*="st-key-open_privacy"] *)) > a:where(:not([data-testid^="stBaseButton-primary"]):not([data-testid^="stBaseButton-tertiary"])) p,
body .stButton:where(:not([class*="st-key-brand_home"] *, [class*="st-key-to_signup"] *, [class*="st-key-to_login"] *, [class*="st-key-to_forgot"] *, [class*="st-key-back_to_login"] *, [class*="st-key-reset_other"] *, [class*="st-key-open_terms"] *, [class*="st-key-open_privacy"] *)) > button:where(:not([data-testid^="stBaseButton-primary"]):not([data-testid^="stBaseButton-tertiary"])):hover p,
body .stFormSubmitButton:where(:not([class*="st-key-brand_home"] *, [class*="st-key-to_signup"] *, [class*="st-key-to_login"] *, [class*="st-key-to_forgot"] *, [class*="st-key-back_to_login"] *, [class*="st-key-reset_other"] *, [class*="st-key-open_terms"] *, [class*="st-key-open_privacy"] *)) > button:where(:not([data-testid^="stBaseButton-primary"]):not([data-testid^="stBaseButton-tertiary"])):hover p,
body .stDownloadButton:where(:not([class*="st-key-brand_home"] *, [class*="st-key-to_signup"] *, [class*="st-key-to_login"] *, [class*="st-key-to_forgot"] *, [class*="st-key-back_to_login"] *, [class*="st-key-reset_other"] *, [class*="st-key-open_terms"] *, [class*="st-key-open_privacy"] *)) > button:where(:not([data-testid^="stBaseButton-primary"]):not([data-testid^="stBaseButton-tertiary"])):hover p,
body .stLinkButton:where(:not([class*="st-key-brand_home"] *, [class*="st-key-to_signup"] *, [class*="st-key-to_login"] *, [class*="st-key-to_forgot"] *, [class*="st-key-back_to_login"] *, [class*="st-key-reset_other"] *, [class*="st-key-open_terms"] *, [class*="st-key-open_privacy"] *)) > a:where(:not([data-testid^="stBaseButton-primary"]):not([data-testid^="stBaseButton-tertiary"])):hover p { color: #F4F7FB !important; font-weight: 600 !important; }
body .stButton:where(:not([class*="st-key-brand_home"] *, [class*="st-key-to_signup"] *, [class*="st-key-to_login"] *, [class*="st-key-to_forgot"] *, [class*="st-key-back_to_login"] *, [class*="st-key-reset_other"] *, [class*="st-key-open_terms"] *, [class*="st-key-open_privacy"] *)) > button[data-testid^="stBaseButton-tertiary"] p,
body .stButton:where(:not([class*="st-key-brand_home"] *, [class*="st-key-to_signup"] *, [class*="st-key-to_login"] *, [class*="st-key-to_forgot"] *, [class*="st-key-back_to_login"] *, [class*="st-key-reset_other"] *, [class*="st-key-open_terms"] *, [class*="st-key-open_privacy"] *)) > button[data-testid^="stBaseButton-tertiary"]:hover p,
body .stFormSubmitButton:where(:not([class*="st-key-brand_home"] *, [class*="st-key-to_signup"] *, [class*="st-key-to_login"] *, [class*="st-key-to_forgot"] *, [class*="st-key-back_to_login"] *, [class*="st-key-reset_other"] *, [class*="st-key-open_terms"] *, [class*="st-key-open_privacy"] *)) > button[data-testid^="stBaseButton-tertiary"] p,
body .stFormSubmitButton:where(:not([class*="st-key-brand_home"] *, [class*="st-key-to_signup"] *, [class*="st-key-to_login"] *, [class*="st-key-to_forgot"] *, [class*="st-key-back_to_login"] *, [class*="st-key-reset_other"] *, [class*="st-key-open_terms"] *, [class*="st-key-open_privacy"] *)) > button[data-testid^="stBaseButton-tertiary"]:hover p { color: #C3CEDD !important; }

/* ---------- 4d. Profile menu ---------- */
html body [data-testid="stPopoverBody"] { min-width: 280px; padding: 16px; }
.pm-id { display: flex; align-items: center; gap: 12px; padding-bottom: 12px;
    border-bottom: 1px solid var(--line); margin-bottom: 4px; }
.pm-name { font-weight: 700; font-size: 15px; color: var(--text); line-height: 1.25; }
.pm-gym { font-size: 12px; color: var(--text-muted); margin-top: 2px; }
.pm-label { font-size: 11px; font-weight: 600; letter-spacing: 1px; text-transform: uppercase;
    color: var(--text-muted); margin: 14px 0 6px; }
html body [class*="st-key-pm_item"] button {
    justify-content: flex-start !important; background: transparent !important;
    border-color: transparent !important; min-height: 42px; padding: 0 10px !important; }
html body [class*="st-key-pm_item"] button:hover { background: rgba(255,255,255,0.07) !important; }
html body [data-testid="stButtonGroup"] { flex-wrap: wrap; }

/* ---------- 4e. Top bar: brand | pages | actions ---------- */
html body .st-key-top_nav [data-testid="stHorizontalBlock"] {
    flex-wrap: nowrap !important; align-items: center !important; gap: 12px !important; }
html body .st-key-top_nav [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    min-width: 0 !important; width: auto !important; }
html body .st-key-top_nav [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(1) {
    flex: 0 0 190px !important; }
html body .st-key-top_nav [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(2) {
    flex: 1 1 0 !important; display: block !important; }
html body .st-key-top_nav [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(3) {
    flex: 0 0 auto !important; display: flex !important; justify-content: flex-end !important; }
html body .st-key-top_actions { flex-wrap: nowrap !important; align-items: center !important;
    gap: 8px !important; width: auto !important; }
html body .st-key-top_actions > * { flex: 0 0 auto !important; width: auto !important; }
@media (min-width: 1101px) { html body .st-key-pop_main { display: none !important; } }
@media (max-width: 1100px) {
    html body .st-key-top_nav [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(2) {
        display: none !important; }
    html body .st-key-top_nav [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(1) {
        flex: 1 1 auto !important; }
    html body .st-key-pop_main { display: block !important; }
}
html body .st-key-global_back { margin: 0 0 var(--sp-2); }
html body .st-key-global_back button { min-height: 36px; padding: 0 14px; }

/* ---------- 4f. Logo mark (wider than the old one) ---------- */
html body .st-key-top_nav .nav-brand-logo,
html body .login-brand .nav-brand-logo { width: 84px !important; height: auto !important;
    margin: 0 auto 6px auto !important; }
@media (max-width: 640px) {
    html body .st-key-top_nav .nav-brand-logo,
    html body .login-brand .nav-brand-logo { width: 72px !important; }
}

/* ---------- 4g. Logo lockup: landing page and top bar ---------- */
html body .gp-lockup { text-align: center; padding: 36px 0 8px; }
html body .gp-lockup img { width: min(460px, 84vw); height: auto; }
html body .gp-tagline { margin-top: 14px; color: var(--text-muted); font-size: 15px;
    letter-spacing: .2px; }
html body .st-key-brand_home button {
    background-color: transparent !important; background-repeat: no-repeat !important;
    background-position: left center !important; background-size: contain !important;
    border: 0 !important; box-shadow: none !important;
    width: min(190px, 100%) !important; height: 58px !important; min-height: 58px !important;
    padding: 0 !important; display: block !important; }
html body .st-key-brand_home button > * { display: none !important; }
html body .st-key-brand_home button:hover { opacity: .9; }
html body .st-key-top_nav .nav-tagline { text-align: left !important; margin: 6px 0 0 !important;
    font-size: 11px !important; white-space: normal !important; }
html body .st-key-top_nav { padding-bottom: 14px; margin-bottom: 20px; }
@media (max-width: 640px) { html body .gp-lockup { padding-top: 20px; } }

/* ---------- 5. Accessibility ---------- */
button, [role="button"], [role="radio"], [role="tab"], a.chip, label, summary { cursor: pointer; }
button:disabled { cursor: not-allowed; opacity: .5; }
html body .stButton > button:focus-visible,
html body .stDownloadButton > button:focus-visible,
html body .stFormSubmitButton > button:focus-visible,
html body [data-testid="stPopover"] button:focus-visible,
html body [data-baseweb="tab"]:focus-visible,
html body a.chip:focus-visible,
html body [class*="st-key-"] button:focus-visible {
    outline: 2px solid var(--accent) !important; outline-offset: 2px !important;
    box-shadow: none !important; }
html body input:focus-visible, html body textarea:focus-visible {
    outline: 2px solid var(--accent) !important; outline-offset: 1px !important; }
@media (pointer: coarse) {
    html body .stButton > button, html body .stDownloadButton > button,
    html body .stFormSubmitButton > button, html body .stLinkButton > a {
        min-height: 44px !important; }
    html body [data-baseweb="tab"] { min-height: 44px; }
    html body div[role="radiogroup"] label { min-height: 40px; }
}
.chip { white-space: normal; line-height: 1.25; max-width: 100%; }
.chip-row { min-width: 0; }
.why, .kv b, .kpi-hint, .profile-name, .pg-sub, .chat-who { overflow-wrap: anywhere; }
.pg-title, .kpi-value { overflow-wrap: anywhere; text-wrap: balance; }
::selection { background: rgba(183,243,74,0.35); color: #fff; }

@media (max-width: 640px) {
    html body .pg-title { font-size: 24px; }
    html body .kpi-value { font-size: 22px; }
    html body .section-label { margin-top: var(--sp-5); }
}
"""


def apply_ui_styles():
    st.markdown("<style>" + UI_CSS + "</style>", unsafe_allow_html=True)
    st.markdown("<style>" + MOBILE_ROWS_CSS + "</style>", unsafe_allow_html=True)
    st.markdown("<style>" + ALL_ROWS_MOBILE_CSS + "</style>", unsafe_allow_html=True)
    st.markdown("<style>" + CHAT_CSS + "</style>", unsafe_allow_html=True)
    st.markdown("<style>" + DESIGN_CSS + "</style>", unsafe_allow_html=True)


def apply_theme(theme):
    """Light mode uses its own palette (gympulse_design.LIGHT_CSS), not an inverted dark theme."""
    if theme == "light":
        import gympulse_design as gd
        gd.apply_light()

# ------------------------------------------------------------ speed & caching
# Tables whose rows belong to one gym. Every read, update and delete on them is
# limited to the signed-in owner's gym here, in one place, so no screen can touch
# another gym's records even by mistake. Row Level Security in the database
# (sql/phase1_foundation.sql) is the second, server-side lock.
GYM_SCOPED_TABLES = {"members", "member_activity", "retention_actions", "checkins",
                     "classes", "trainers", "messages", "reminder_log", "payments"}


def _current_gym():
    try:
        return st.session_state.get("gym_id")
    except Exception:
        return None


class _TrackedTable:
    def __init__(self, table, name=""):
        self._t = table
        self._name = name
    def __getattr__(self, name):
        attr = getattr(self._t, name)
        scoped = self._name in GYM_SCOPED_TABLES
        if name in ("insert", "upsert"):
            def write(payload, *args, **kwargs):
                st.session_state["_dv"] = st.session_state.get("_dv", 0) + 1
                gid = _current_gym() if scoped else None
                if gid:
                    rows = payload if isinstance(payload, list) else [payload]
                    for row in rows:
                        if isinstance(row, dict):
                            if row.get("gym_id") not in (None, gid):
                                raise PermissionError("Refused to write a record for another gym.")
                            row["gym_id"] = gid
                return attr(payload, *args, **kwargs)
            return write
        if name in ("update", "delete", "select"):
            def scoped_query(*args, **kwargs):
                if name != "select":
                    st.session_state["_dv"] = st.session_state.get("_dv", 0) + 1
                query = attr(*args, **kwargs)
                gid = _current_gym() if scoped else None
                return query.eq("gym_id", gid) if gid else query
            return scoped_query
        return attr

class TrackedClient:
    def __init__(self, client):
        self._client = client
    def __getattr__(self, name):
        return getattr(self._client, name)
    def table(self, name):
        return _TrackedTable(self._client.table(name), name)

def _clone(value):
    if isinstance(value, pd.DataFrame):
        return value.copy()
    if isinstance(value, tuple):
        return tuple(_clone(v) for v in value)
    return value

def _cached(key, fn, ttl=60, skip_empty=False):
    store = st.session_state.get("_cache")
    if not isinstance(store, dict):
        store = {}
        st.session_state["_cache"] = store
    version = st.session_state.get("_dv", 0)
    hit = store.get(key)
    now = time.time()
    if hit and hit[1] == version and now - hit[0] < ttl:
        return _clone(hit[2])
    value = fn()
    if not (skip_empty and (value is None or value == [])):
        store[key] = (now, version, _clone(value))
    return value

cached = _cached

def show_boot_overlay():
    st.markdown('<div class="boot-overlay"><div class="boot-spin"></div>'
                '<div>Loading your workspace…</div></div>', unsafe_allow_html=True)
    time.sleep(0.2)

# ---------------------------------------------------------------- data
MEMBER_BASE = ["id", "full_name", "email", "phone", "age", "weight_kg",
               "height_cm", "fitness_goal", "created_at", "archived"]
MEMBER_SUSPEND = ["suspended"]
MEMBER_PROFILE = ["photo", "membership_end", "last_renewed_on", "last_payment"]
MEMBER_PROFILE_LIGHT = ["membership_end", "last_renewed_on", "last_payment"]

def fetch_all(query, page=1000, cap=50000):
    """Every row of a query, page by page. Supabase returns at most 1,000 rows per request,
    so gyms with thousands of members would otherwise see only the first 1,000."""
    rows, start = [], 0
    while True:
        chunk = query.range(start, start + page - 1).execute().data or []
        rows += chunk
        if len(chunk) < page or len(rows) >= cap:
            return rows
        start += page


def _fetch_members_uncached(supabase, gym_id, archived=None, include_photo=True):
    profile = MEMBER_PROFILE if include_photo else MEMBER_PROFILE_LIGHT
    attempts = [MEMBER_BASE + MEMBER_SUSPEND + profile,
                MEMBER_BASE + MEMBER_SUSPEND,
                MEMBER_BASE]
    rows, used, last_error = None, None, None
    for columns in attempts:
        try:
            query = (supabase.table("members").select(", ".join(columns))
                     .eq("gym_id", gym_id))
            if archived is not None:
                query = query.eq("archived", archived)
            rows = fetch_all(query.order("created_at", desc=True).order("id"))
            used = columns
            break
        except Exception as error:
            last_error = error
    if rows is None:
        raise last_error or RuntimeError("Could not load members.")
    df = pd.DataFrame(rows)
    if df.empty:
        df = pd.DataFrame(columns=MEMBER_BASE + MEMBER_SUSPEND + MEMBER_PROFILE)
    for column in MEMBER_SUSPEND + MEMBER_PROFILE:
        if column not in df.columns:
            df[column] = None
    df["archived"] = df["archived"].fillna(False).astype(bool)
    df["suspended"] = df["suspended"].fillna(False).astype(bool)
    features = {"suspend_ready": "suspended" in used,
                "profile_ready": "membership_end" in used}
    return df, features

def _load_roster_uncached(supabase, gym_id, assess_fn, with_photos=True):
    members_all, _ = fetch_members(supabase, gym_id, archived=False, include_photo=with_photos)
    members = members_all[~members_all["suspended"]]

    keep = ["id", "full_name", "email", "phone", "fitness_goal",
            "membership_end", "last_payment", "last_renewed_on"]
    if with_photos:
        keep.append("photo")
    members = members[[c for c in keep if c in members.columns]].reset_index(drop=True)

    activity = pd.DataFrame(
        fetch_all(supabase.table("member_activity").select("*").eq("gym_id", gym_id).order("member_id"))
    )
    # Real check-ins override typed-in attendance numbers
    stats = checkin_stats(load_checkins(supabase, gym_id))
    if not stats.empty and not activity.empty and "member_id" in activity.columns:
        activity = activity.merge(stats, on="member_id", how="left")
        live = activity["ck_days"].notna()
        typed_days = pd.to_numeric(activity["days_since_last_visit"], errors="coerce").astype(float)
        typed_recent = pd.to_numeric(activity["visits_last_30_days"], errors="coerce").astype(float)
        typed_prev = pd.to_numeric(activity["visits_previous_30_days"], errors="coerce").astype(float)
        activity["days_since_last_visit"] = typed_days.where(~live, activity["ck_days"])
        activity["visits_last_30_days"] = typed_recent.where(~live, activity["ck_recent"])
        baseline = activity["ck_base"].where(activity["ck_base"].notna(), typed_recent)
        activity["visits_previous_30_days"] = typed_prev.where(~live, baseline)
        if "updated_at" not in activity.columns:
            activity["updated_at"] = None
        activity["updated_at"] = activity["updated_at"].astype(object)
        activity.loc[live, "updated_at"] = datetime.now(timezone.utc).isoformat()
        activity = activity.drop(columns=["ck_days", "ck_recent", "ck_base"])
    return build_roster(members, activity, assess_fn)

def build_roster(members, activity, assess_fn):
    if members.empty:
        return pd.DataFrame(), pd.DataFrame()
    if activity.empty:
        return pd.DataFrame(), members
    df = members.merge(activity, left_on="id", right_on="member_id", how="left")
    has = df["membership_type"].notna()
    missing = df.loc[~has, members.columns]
    scored = df[has].copy()
    if scored.empty:
        return pd.DataFrame(), missing
    scored["monthly_fee"] = pd.to_numeric(scored["monthly_fee"]).fillna(0)
    scored = apply_live_dates(scored)
    real_days = pd.to_numeric(scored["days_since_last_visit"], errors="coerce").fillna(0)
    if "usual_gap_days" in scored.columns:
        # A break matters more for someone who trains daily than for someone who trains monthly
        gap = pd.to_numeric(scored["usual_gap_days"], errors="coerce")
        scale = (7 / gap.clip(2, 14)).clip(0.6, 2.0).fillna(1.0)
        scored["days_since_last_visit"] = (real_days * scale).round().clip(0, 90).astype(int)
    scored = assess_fn(scored.reset_index(drop=True))
    scored["days_since_last_visit"] = real_days.values.astype(int)
    scored["attendance_change"] = (scored["visits_last_30_days"]
                                   - scored["visits_previous_30_days"])
    scored["revenue_at_risk"] = scored["cancellation_probability"] * scored["monthly_fee"]
    scored["drivers"] = scored.apply(drivers, axis=1)
    scored["suggested_action"] = scored.apply(suggest_action, axis=1)
    return scored.sort_values("cancellation_probability", ascending=False), missing

def _load_actions_uncached(supabase, gym_id, include_archived=False):
    query = (supabase.table("retention_actions").select("*").eq("gym_id", gym_id))
    if not include_archived:
        try:
            query = query.is_("archived_at", "null")
        except Exception:
            pass
    rows = fetch_all(query.order("created_at", desc=True).order("id"))
    return pd.DataFrame(rows)

def fetch_members(supabase, gym_id, archived=None, include_photo=True):
    return _cached(("members", gym_id, archived, include_photo),
                   lambda: _fetch_members_uncached(supabase, gym_id, archived, include_photo))

def load_roster(supabase, gym_id, assess_fn, with_photos=True):
    return _cached(("roster", gym_id, with_photos, today_local().isoformat()),
                   lambda: _load_roster_uncached(supabase, gym_id, assess_fn, with_photos))

def load_actions(supabase, gym_id, include_archived=False):
    return _cached(("actions", gym_id, include_archived),
                   lambda: _load_actions_uncached(supabase, gym_id, include_archived))

def purge_old_done_actions(supabase, gym_id, hours=DONE_RETENTION_HOURS):
    stamp_key = f"_purge_{gym_id}"
    last = st.session_state.get(stamp_key, 0)
    if time.time() - last < PURGE_INTERVAL_SECONDS:
        return 0
    st.session_state[stamp_key] = time.time()

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    try:
        rows = (supabase.table("retention_actions").select("id, completed_at")
                .eq("gym_id", gym_id).eq("status", "Done")
                .eq("outcome", "Retained").is_("archived_at", "null")
                .execute().data or [])
    except Exception:
        return 0
    stale = []
    for r in rows:
        try:
            stamp = pd.to_datetime(r.get("completed_at"), errors="coerce", utc=True)
            if pd.isna(stamp) or stamp.to_pydatetime() < cutoff:
                stale.append(r["id"])
        except Exception:
            stale.append(r["id"])
    if not stale:
        return 0
    try:
        for start in range(0, len(stale), 100):
            (supabase.table("retention_actions")
             .update({"archived_at": datetime.now(timezone.utc).isoformat()})
             .in_("id", stale[start:start + 100]).execute())
    except Exception:
        return 0
    return len(stale)

def open_profile(member_id, back_page="Member Management"):
    st.session_state["profile_member_id"] = member_id
    st.session_state["profile_back"] = back_page
    st.session_state["navigate_to"] = "Member Profile"

def open_followup(member_id, back_page="Risk Radar"):
    st.session_state["fu_member"] = member_id
    st.session_state["fu_view"] = "Compose"
    st.session_state["followup_back"] = back_page
    st.session_state["navigate_to"] = "Follow-ups"

# ------------------------------------------------------------- logic
def drivers(row):
    out = []
    if row["days_since_last_visit"] >= 14:
        out.append(f"{int(row['days_since_last_visit'])} days since last visit")
    change = row["visits_last_30_days"] - row["visits_previous_30_days"]
    if change <= -3:
        out.append("attendance dropping")
    if row["renewal_due_days"] <= 14:
        d = int(row["renewal_due_days"])
        out.append("renews today" if d == 0 else f"lapsed {-d} days ago" if d < 0
                   else f"renews in {d} day{'s' if d != 1 else ''}")
    if row["pt_sessions_attended"] == 0:
        out.append("no PT sessions")
    if PLAN_DAYS.get(plan_name(row["membership_type"]), 30) <= 30:
        out.append(f"{plan_phrase(row['membership_type'])} plan (easy to leave)")
    ug = row.get("usual_gap_days") if hasattr(row, "get") else None
    if ug is not None and not pd.isna(ug):
        days = int(row["days_since_last_visit"])
        n = max(1, round(float(ug)))
        if days > max(2 * float(ug), float(ug) + 3):
            out.insert(0, f"usually visits every {n} day{'s' if n != 1 else ''}, now {days} away")
        elif not out and days <= 1.5 * float(ug) + 1:
            return "visiting regularly"
    return ", ".join(out) or "no major warning signs"

def suggest_action(row):
    if row["renewal_due_days"] <= 14 and row["risk_category"] != "Low":
        return "Renewal offer"
    if row["days_since_last_visit"] >= 14:
        return "Personal call"
    if row["pt_sessions_attended"] == 0:
        return "Trainer intro"
    if row["risk_category"] == "Low":
        return "Goal review"
    return "WhatsApp check-in"

# ------------------------------------------------- retention plays
# What each play is for, how to deliver it, and when to follow up.
PLAY_INFO = {
    "Personal call":        {"objective": "Re-engage a member who is drifting", "channel": "Call", "follow": 2},
    "WhatsApp check-in":    {"objective": "Re-engage with a light touch", "channel": "WhatsApp", "follow": 3},
    "Feedback request":     {"objective": "Find out what is pushing them away", "channel": "WhatsApp", "follow": 5},
    "Renewal offer":        {"objective": "Secure the renewal", "channel": "Call", "follow": 2},
    "Free PT session":      {"objective": "Restore attendance with personal support", "channel": "WhatsApp", "follow": 4},
    "Trainer intro":        {"objective": "Build a personal connection", "channel": "In person", "follow": 5},
    "Goal review":          {"objective": "Reset goals and motivation", "channel": "In person", "follow": 7},
    "Class invite":         {"objective": "Restore the attendance habit", "channel": "WhatsApp", "follow": 3},
    "Group challenge":      {"objective": "Build belonging in the community", "channel": "WhatsApp", "follow": 7},
    "Bring-a-friend invite": {"objective": "Increase engagement and referrals", "channel": "WhatsApp", "follow": 7},
    "Milestone shout-out":  {"objective": "Reinforce a good habit", "channel": "WhatsApp", "follow": 14},
    "Welcome-back note":    {"objective": "Make the return stick", "channel": "WhatsApp", "follow": 7},
}
CONTACT_METHODS = ["WhatsApp", "Call", "Email", "In person", "SMS"]

# Lifecycle shown to the owner. `status` keeps its three stored values
# (To do, In progress, Done); the extra stages come from when the member
# was contacted and when the follow-up is due.
STAGE_TONE = {"Recommended": "grey", "Started": "cyan", "In progress": "amber",
              "Contacted": "cyan", "Follow-up due": "red", "Resolved": "lime",
              "Unsuccessful": "grey"}


def _blank(v):
    return v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() in ("", "NaT", "None", "nan")


def action_stage(a, today=None):
    status = a.get("status")
    if status == "Done":
        return "Resolved" if a.get("outcome") == "Retained" else "Unsuccessful"
    if status == "To do":
        return "Started"
    if _blank(a.get("contacted_at")):
        return "In progress"
    today = today or date.today()
    try:
        due = date.fromisoformat(str(a.get("follow_up_on") or a.get("due_date"))[:10])
    except ValueError:
        return "Contacted"
    return "Follow-up due" if due <= today else "Contacted"


def stage_chip(stage):
    return chip(stage, STAGE_TONE.get(stage, "grey"), dot=stage in ("Follow-up due", "Resolved"))


def mark_contacted(supabase, action_id, method, follow_days=None, play=None, note=""):
    """Record that the member was contacted and schedule the follow-up.
    Returns "full" (all details saved) or "basic" (saved without the Phase 2 columns)."""
    days = follow_days if follow_days is not None else PLAY_INFO.get(play or "", {}).get("follow", 3)
    follow_on = (today_local() + timedelta(days=int(days))).isoformat()
    now = datetime.now(timezone.utc).isoformat()
    base = {"status": "In progress", "due_date": follow_on}
    if note:
        base["note"] = note
    full = {**base, "contacted_at": now, "contact_method": method, "follow_up_on": follow_on}
    try:
        supabase.table("retention_actions").update(full).eq("id", action_id).execute()
        return "full"
    except Exception:
        stamp = f"Contacted by {method.lower()} on {today_local():%d %b}; follow up {follow_on}."
        base["note"] = (note + " · " if note else "") + stamp
        supabase.table("retention_actions").update(base).eq("id", action_id).execute()
        return "basic"


def close_action(supabase, action_id, outcome, note=None):
    row = {"status": "Done", "outcome": outcome,
           "completed_at": datetime.now(timezone.utc).isoformat()}
    if note is not None:
        row["note"] = note
    supabase.table("retention_actions").update(row).eq("id", action_id).execute()


def open_action_for(supabase, member_id):
    """The member's open play, if any (used by Follow-ups and reminders)."""
    try:
        rows = (supabase.table("retention_actions").select("*")
                .eq("member_id", member_id).neq("status", "Done")
                .order("created_at", desc=True).limit(1).execute().data or [])
        rows = [r for r in rows if _blank(r.get("archived_at"))]
        return rows[0] if rows else None
    except Exception:
        return None


def _plural(n, word, plural=None):
    return f"{n} {word if n == 1 else (plural or word + 's')}"


def risk_story(r):
    """Who, why, when and what next for one member, in plain words."""
    days = int(r.get("days_since_last_visit", 0) or 0)
    recent = int(r.get("visits_last_30_days", 0) or 0)
    before = int(r.get("visits_previous_30_days", 0) or 0)
    renew = int(r.get("renewal_due_days", 0) or 0)

    why = []
    if before - recent >= 3:
        why.append(f"visits fell from {before} to {recent} a month")
    ug = r.get("usual_gap_days")
    if ug is not None and not pd.isna(ug) and days > max(2 * float(ug), float(ug) + 3):
        n = max(1, round(float(ug)))
        why.append(f"usually trains every {_plural(n, 'day')}, now {days} away")
    elif days >= 10:
        why.append(f"no check-in for {days} days")
    if renew == 0:
        why.append("renews today")
    elif 0 < renew <= 30:
        why.append(f"renews in {_plural(renew, 'day')}")
    elif renew < 0:
        why.append(f"membership lapsed {_plural(-renew, 'day')} ago")
    if not why:
        why.append(str(r.get("drivers") or "early warning signs"))

    if before - recent >= 3:
        when = "the drop shows over the last 30 days"
    elif days:
        when = f"last check-in {_plural(days, 'day')} ago"
    else:
        when = "checked in today"

    urgent = r.get("risk_category") == "High" and renew <= 14
    play = str(r.get("suggested_action") or "Personal call")
    info = PLAY_INFO.get(play, {})
    nxt = f"<b>{_esc(play)}</b> {'today' if urgent else 'this week'}"
    if renew <= 14 and play != "Renewal offer":
        nxt += ", before the renewal date"
    if info.get("channel"):
        ch = info["channel"]
        nxt += f" · by {ch.lower() if ch in ('Call', 'In person') else ch}"
    return {"why": ", ".join(why[:3]), "when": when, "next": nxt, "play": play,
            "objective": info.get("objective", "")}


def story_html(r):
    st_ = risk_story(r)
    return (f'<dl class="cc-story"><dt>Why</dt><dd>{_esc(st_["why"])}</dd>'
            f'<dt>When</dt><dd>{_esc(st_["when"])}</dd>'
            f'<dt>Next</dt><dd>{st_["next"]}</dd></dl>')


def story_text(r):
    st_ = risk_story(r)
    nxt = re.sub("<[^>]+>", "", st_["next"])
    return f"Why: {st_['why']}. When: {st_['when']}. Next: {nxt}."


def members_to_contact(roster, actions, cooldown_days=SUGGEST_COOLDOWN_DAYS, today=None,
                       include_low=False):
    if roster.empty:
        return roster
    blocked = set()
    if not actions.empty:
        now = pd.Timestamp(today or date.today())
        open_mask = actions["status"] != "Done"
        blocked |= set(actions.loc[open_mask, "member_id"])
        done = actions[~open_mask].copy()
        when = pd.to_datetime(done["completed_at"], errors="coerce", utc=True, format="ISO8601")
        when = when.dt.tz_localize(None)
        recent = when.isna() | (when >= now - pd.Timedelta(days=cooldown_days))
        blocked |= set(done.loc[recent, "member_id"])
        blocked |= set(done.loc[done["outcome"] == "Cancelled", "member_id"])
    keep = ~roster["id"].isin(blocked)
    if not include_low:
        keep &= roster["risk_category"] != "Low"
    return roster[keep]

def _go(page, member=None):
    st.session_state["navigate_to"] = page
    if member is not None:
        st.session_state["focus_member"] = member

def kpis(roster, actions):
    n = len(roster)
    high = roster[roster["risk_category"] == "High"] if n else roster
    done = actions[actions["status"] == "Done"] if not actions.empty else actions
    retained = int((done["outcome"] == "Retained").sum()) if not done.empty else 0
    decided = int(done["outcome"].isin(["Retained", "Cancelled"]).sum()) if not done.empty else 0
    return {
        "members_scored": n,
        "high": len(high),
        "medium": int((roster["risk_category"] == "Medium").sum()) if n else 0,
        "monthly_revenue": float(roster["monthly_fee"].sum()) if n else 0.0,
        "high_risk_revenue": float(high["monthly_fee"].sum()) if n else 0.0,
        "expected_loss": float(roster["revenue_at_risk"].sum()) if n else 0.0,
        "renewals_30d_at_risk": int(((roster["renewal_due_days"] <= 30)
                                     & (roster["risk_category"] != "Low")).sum()) if n else 0,
        "open_actions": int((actions["status"] != "Done").sum()) if not actions.empty else 0,
        "saves": retained,
        "save_rate": (retained / decided) if decided else None,
        "revenue_saved": float(
            roster.set_index("id").reindex(
                done.loc[done["outcome"] == "Retained", "member_id"]
            )["monthly_fee"].sum()) if retained and n else 0.0,
    }

# ------------------------------------------------------- rendering
def _money(x):
    return f"{x:,.0f}"

def _activity_editor(supabase, gym_id, roster, missing, use_expander=True):
    names, current = {}, {}
    if not roster.empty:
        for _, r in roster.iterrows():
            names[r["id"]] = r["full_name"]
            current[r["id"]] = r
    if not missing.empty:
        for _, r in missing.iterrows():
            names[r["id"]] = r["full_name"]
    if not names:
        st.info("Register members in Member Management first.")
        return

    plans = PLANS

    with _section("Add or update member activity", use_expander,
                  expanded=roster.empty):
        member_id = st.selectbox(
            "Member", list(names),
            format_func=lambda i: names[i], key="act_member"
        )
        r = current.get(member_id)

        def val(col, default):
            return default if r is None else r[col]

        with st.form(f"activity_form_{member_id}"):
            c1, c2 = st.columns(2)
            mtype = c1.selectbox(
                "Membership type", plans,
                index=plans.index(plan_name(val("membership_type", "Monthly")))
            )
            fee = c2.number_input(
                "Monthly fee", min_value=0.0, step=500.0,
                value=float(val("monthly_fee", 0.0)),
                help="What the plan works out to per month (a 2-week plan at 15,000 is about 32,000 a month)."
            )
            d = c1.number_input(
                "Days since last visit", 0, 365,
                int(val("days_since_last_visit", 7))
            )
            prev = c2.number_input(
                "Visits, previous 30 days", 0, 100,
                int(val("visits_previous_30_days", 10))
            )
            last = c1.number_input(
                "Visits, last 30 days", 0, 100,
                int(val("visits_last_30_days", 8))
            )
            ren = c2.number_input(
                "Days until renewal", 0, 365,
                int(val("renewal_due_days", 30))
            )
            pt = c1.number_input(
                "PT sessions attended", 0, 100,
                int(val("pt_sessions_attended", 0))
            )
            if st.form_submit_button("Save activity", type="primary", use_container_width=True):
                supabase.table("member_activity").upsert({
                    "member_id": member_id, "gym_id": gym_id,
                    "membership_type": mtype, "monthly_fee": float(fee),
                    "days_since_last_visit": int(d),
                    "visits_previous_30_days": int(prev),
                    "visits_last_30_days": int(last),
                    "renewal_due_days": int(ren),
                    "pt_sessions_attended": int(pt),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }).execute()
                st.rerun()

    if not missing.empty:
        st.caption(f"{len(missing)} member(s) still need activity data.")

IMPORT_NUMERIC = {
    "days_since_last_visit": (0, 3650),
    "visits_previous_30_days": (0, 200),
    "visits_last_30_days": (0, 200),
    "renewal_due_days": (0, 730),
    "pt_sessions_attended": (0, 500),
}
IMPORT_PLANS = {"daily": "Daily", "day": "Daily", "weekly": "Weekly", "week": "Weekly",
                "2 weeks": "2 weeks", "two weeks": "2 weeks", "biweekly": "2 weeks", "fortnightly": "2 weeks",
                "monthly": "Monthly", "month": "Monthly", "2 months": "2 months", "two months": "2 months",
                "bimonthly": "2 months", "quarterly": "Quarterly", "3 months": "Quarterly",
                "6 months": "6 months", "six months": "6 months", "half-yearly": "6 months", "biannual": "6 months",
                "yearly": "Yearly", "annual": "Yearly", "12 months": "Yearly", "1 year": "Yearly"}
ISSUE_COLS = ["Row", "Member", "Problem", "Result"]

def parse_activity_csv(csv_df, members):
    df = csv_df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    empty = pd.DataFrame(columns=ISSUE_COLS)

    id_col = ("email" if "email" in df.columns
              else "full_name" if "full_name" in df.columns else None)
    fatal = []
    if id_col is None:
        fatal.append("Add an 'email' column (or 'full_name') so each row can "
                     "be matched to a registered member.")
    wanted = ["membership_type"] + list(IMPORT_NUMERIC)
    absent = [c for c in wanted if c not in df.columns]
    if absent:
        fatal.append("Missing column(s): " + ", ".join(absent))
    if fatal:
        return [], empty, fatal

    has_fee = "monthly_fee" in df.columns
    lookup = {}
    for _, m in members.iterrows():
        val = m.get(id_col)
        key = "" if pd.isna(val) else str(val).strip().lower()
        if key:
            lookup.setdefault(key, []).append(m["id"])

    issues, chosen = [], {}
    for i, r in df.iterrows():
        line = int(i) + 2
        raw_id = r[id_col]
        ident = "" if pd.isna(raw_id) else str(raw_id).strip()

        def skip(why, line=line, ident=ident):
            issues.append((line, ident, why, "Skipped"))

        if not ident:
            skip(f"Empty {id_col}")
            continue
        ids = lookup.get(ident.lower(), [])
        if not ids:
            skip(f"No registered member with this {id_col}")
            continue
        if len(ids) > 1:
            skip(f"More than one member has this {id_col}; use email instead")
            continue
        plan = IMPORT_PLANS.get(str(r["membership_type"]).strip().lower())
        if not plan:
            skip("membership_type must be one of: " + ", ".join(PLANS))
            continue

        row = {"member_id": ids[0], "membership_type": plan}
        problem = None
        for col, (lo, hi) in IMPORT_NUMERIC.items():
            v = pd.to_numeric(r[col], errors="coerce")
            if pd.isna(v) or v < lo or v > hi or v != int(v):
                problem = f"{col} must be a whole number from {lo} to {hi}"
                break
            row[col] = int(v)
        if problem is None and has_fee:
            v = pd.to_numeric(r["monthly_fee"], errors="coerce")
            if pd.isna(v) or v < 0:
                problem = "monthly_fee must be a number, 0 or more"
            else:
                row["monthly_fee"] = float(v)
        if problem:
            skip(problem)
            continue

        if ids[0] in chosen:
            issues.append((line, ident, "Appears more than once; this later row is used",
                           "Note"))
        chosen[ids[0]] = row

    issues_df = pd.DataFrame(issues, columns=ISSUE_COLS) if issues else empty
    return list(chosen.values()), issues_df, []

def render_csv_import(supabase, gym_id, use_expander=True):
    try:
        members = pd.DataFrame(
            supabase.table("members").select("id, full_name, email")
            .eq("gym_id", gym_id).eq("archived", False).execute().data or []
        )
    except Exception as e:
        st.error("Couldn't load members for import. Have you run schema_update_archive.sql?")
        with st.expander("Technical details"):
            st.code(str(e))
        return

    key = st.session_state.get("csv_up_key", 0)
    with _section("Import activity from CSV", use_expander):
        st.caption("One row per member. Members are matched by email (or full_name "
                   "if there is no email column). Existing activity is replaced; "
                   "members not in the file are left unchanged.")
        if members.empty:
            st.info("Register members in Member Management first.")
            return

        template = members[["email", "full_name"]].copy()
        for col in ["membership_type", "monthly_fee"] + list(IMPORT_NUMERIC):
            template[col] = ""
        import gympulse_reports as rp  # local import: gympulse_reports imports this module
        rp.download_link("Download a template with my members",
                         template.to_csv(index=False).encode("utf-8"),
                         "gympulse_activity_template.csv", "text/csv", "act_tpl")
        st.caption("Fill in the blank columns, then upload it below. "
                   "monthly_fee is optional; leave the column out to keep each "
                   "member's current fee.")

        up = st.file_uploader("CSV file", type="csv", key=f"csv_up_{key}")
        if up is None:
            return
        try:
            raw = pd.read_csv(up)
        except Exception:
            st.error("That file couldn't be read as a CSV.")
            return
        if len(raw) > 5000:
            st.error("Please upload 5,000 rows or fewer at a time.")
            return

        payload, issues, fatal = parse_activity_csv(raw, members)
        if fatal:
            for f in fatal:
                st.error(f)
            return

        skipped = int((issues["Result"] == "Skipped").sum()) if not issues.empty else 0
        c1, c2 = st.columns(2)
        c1.metric("Ready to import", len(payload))
        c2.metric("Skipped", skipped)
        if not issues.empty:
            table(issues, wide=tuple(issues.columns[-1:]))
        if not payload:
            return

        names = members.set_index("id")["full_name"]
        preview = pd.DataFrame(payload)
        preview.insert(0, "member", preview["member_id"].map(names))
        st.caption("Preview of the first 20 rows:")
        table(preview.drop(columns="member_id").head(20))

        if st.button(f"Import {len(payload)} member(s)", key="csv_import_go",
                     type="primary"):
            now = datetime.now(timezone.utc).isoformat()
            rows = [{**p, "gym_id": gym_id, "updated_at": now} for p in payload]
            try:
                for start in range(0, len(rows), 200):
                    supabase.table("member_activity").upsert(
                        rows[start:start + 200]).execute()
            except Exception as e:
                st.error("The import failed part-way. Nothing else was changed.")
                with st.expander("Technical details"):
                    st.code(str(e))
                return
            st.session_state["flash"] = (
                f"Imported activity for {len(rows)} member(s)"
                + (f"; {skipped} row(s) skipped." if skipped else "."))
            st.session_state["csv_up_key"] = key + 1
            st.rerun()

def save_membership(supabase, gym_id, member_id, plan, monthly_fee, membership_end, pt_sessions=0):
    """Give a member the plan details the Risk Radar needs. Attendance starts at
    zero and is replaced by real check-ins as soon as they arrive.
    Returns a short note if something could not be saved, else ""."""
    if not member_id:
        return "Add their plan in the Risk Radar's data tools to score them."
    end = pd.Timestamp(membership_end).date() if membership_end is not None else None
    renew = max(0, (end - today_local()).days) if end else 30
    try:
        supabase.table("member_activity").upsert({
            "member_id": member_id, "gym_id": gym_id,
            "membership_type": plan, "monthly_fee": float(monthly_fee or 0),
            "days_since_last_visit": 0, "visits_previous_30_days": 0,
            "visits_last_30_days": 0, "renewal_due_days": int(renew),
            "pt_sessions_attended": int(pt_sessions or 0),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception:
        return "Their plan could not be saved; add it in the Risk Radar's data tools."
    if end:
        try:
            supabase.table("members").update({"membership_end": end.isoformat()}) \
                .eq("id", member_id).execute()
        except Exception:
            pass
    return ""


def _set_archived(supabase, member_id, flag):
    supabase.table("members").update({
        "archived": flag,
        "archived_at": datetime.now(timezone.utc).isoformat() if flag else None,
    }).eq("id", member_id).execute()

def _member_manager(supabase, gym_id, roster, missing, use_expander=True):
    names = {}
    for df in (roster, missing):
        if not df.empty:
            for _, r in df.iterrows():
                names[r["id"]] = r["full_name"]
    try:
        archived = pd.DataFrame(
            supabase.table("members").select("id, full_name")
            .eq("gym_id", gym_id).eq("archived", True).execute().data or [])
    except Exception:
        archived = pd.DataFrame()

    with _section(f"Archive, restore or delete members ({len(archived)} archived)",
                  use_expander):
        st.caption("You can also suspend, reactivate, archive or delete members "
                   "from the Member Management page.")
        if names:
            pick = st.selectbox("Member", list(names),
                                format_func=lambda i: names[i], key="mgr_member")
            st.caption("Archive hides a member from the radar, Action Centre "
                       "and insights, and keeps their history. Delete removes "
                       "the member, their activity and their actions for good.")
            c1, c2 = st.columns(2)
            if c1.button("Archive member", key="mgr_archive", use_container_width=True):
                try:
                    _set_archived(supabase, pick, True)
                except Exception:
                    st.error("Couldn't archive. Have you run schema_update_archive.sql?")
                else:
                    st.session_state["flash"] = f"{names[pick]} archived."
                    st.rerun()
            if st.session_state.get("del_member") == pick:
                st.warning(f"Permanently delete {names[pick]}? This cannot be undone.")
                y, n = st.columns(2)
                if y.button("Yes, delete", key="mgr_del_yes", use_container_width=True):
                    try:
                        supabase.table("members").delete().eq("id", pick).execute()
                    except Exception:
                        st.error("Couldn't delete this member.")
                    else:
                        st.session_state.pop("del_member", None)
                        st.session_state["flash"] = f"{names[pick]} deleted."
                        st.rerun()
                if n.button("Cancel", key="mgr_del_no", use_container_width=True):
                    st.session_state.pop("del_member", None)
                    st.rerun()
            elif c2.button("Delete permanently", key="mgr_delete", use_container_width=True):
                st.session_state["del_member"] = pick
                st.rerun()
        else:
            st.caption("No active members.")

        if not archived.empty:
            st.markdown("**Archived members**")
            rows = [{"name": r["full_name"], "id": r["id"]}
                    for _, r in archived.iterrows()]
            data_card(rows, [("name", "Member"), ("id", "Reference")],
                      key_prefix="archived_members", tone="grey",
                      empty="No archived members.")
            for _, r in archived.iterrows():
                a, b = st.columns([4, 1])
                a.write(r["full_name"])
                if b.button("Restore", type="tertiary", key=f"rs_{r['id']}"):
                    _set_archived(supabase, r["id"], False)
                    st.session_state["flash"] = f"{r['full_name']} restored."
                    st.rerun()

def _delete_action_control(supabase, action_id):
    if st.session_state.get("del_action") == action_id:
        st.warning("Delete this action permanently?")
        y, n = st.columns(2)
        if y.button("Yes, delete", key=f"dy_{action_id}"):
            supabase.table("retention_actions").delete().eq("id", action_id).execute()
            st.session_state.pop("del_action", None)
            st.rerun()
        if n.button("Cancel", key=f"dn_{action_id}"):
            st.session_state.pop("del_action", None)
            st.rerun()
    elif st.button("Delete", key=f"dx_{action_id}"):
        st.session_state["del_action"] = action_id
        st.rerun()

def _has_open_action(supabase, member_id):
    rows = (supabase.table("retention_actions").select("id")
            .eq("member_id", member_id).neq("status", "Done").limit(1).execute().data)
    return bool(rows)

def _create_action(supabase, gym_id, member_id, action_type, renewal_days,
                   note="", trainer_id=None, details=None):
    due = date.today() + timedelta(days=1 if renewal_days <= 14 else 3)
    row = {"gym_id": gym_id, "member_id": member_id, "action_type": action_type,
           "due_date": due.isoformat(), "note": note}
    if trainer_id:
        row["trainer_id"] = trainer_id
    if details:
        row["details"] = details
    try:
        supabase.table("retention_actions").insert(row).execute()
    except Exception:
        if "details" in row:
            row.pop("details")
            supabase.table("retention_actions").insert(row).execute()
            st.session_state["ac_flash"] = ("Added, but the play details were not saved. "
                                            "Run the setup SQL to switch them on.")
        else:
            raise

# ------------------------------------------------- member directory
def render_member_directory(supabase, gym_id):
    flash = st.session_state.pop("mm_flash", None)
    if flash:
        st.success(flash)

    try:
        df, feat = fetch_members(supabase, gym_id)
    except Exception as error:
        st.error("Could not load members.")
        with st.expander("Technical details"):
            st.code(str(error))
        return

    if not feat["profile_ready"]:
        st.warning(
            "Photos and membership status need a one-time database update. "
            "Run member_profile_upgrade.sql in Supabase, then refresh this page."
        )
    if not feat["suspend_ready"]:
        st.warning(
            "Suspend is not switched on yet. Add the 'suspended' column in "
            "Supabase and refresh this page."
        )

    if df.empty:
        st.info("No members registered yet. Register your first member above.")
        return

    df["view_status"] = df.apply(
        lambda r: "Archived" if r["archived"]
        else "Suspended" if r["suspended"] else "Active",
        axis=1
    )
    counts = df["view_status"].value_counts()
    kpi_row([
        ("Active", int(counts.get("Active", 0)), "lime", "Members you are tracking"),
        ("Suspended", int(counts.get("Suspended", 0)), "amber", "Paused, history kept"),
        ("Archived", int(counts.get("Archived", 0)), "grey", "Hidden from your lists"),
    ])

    f1, f2 = st.columns([2, 3])
    view = f1.radio("Show", ["Active", "Suspended", "Archived"], horizontal=True,
                    key="mm_view", label_visibility="collapsed")
    search = f2.text_input("Search members", key="mm_search",
                           placeholder="Search by name or email",
                           label_visibility="collapsed")

    shown = df[df["view_status"] == view]
    if search.strip():
        needle = search.strip().lower()
        shown = shown[
            shown["full_name"].fillna("").str.lower().str.contains(needle, regex=False)
            | shown["email"].fillna("").str.lower().str.contains(needle, regex=False)
        ]

    if shown.empty:
        st.caption(f"No {view.lower()} members found.")
        return

    st.markdown('<div class="section-label">MEMBERS · CLICK A NAME TO OPEN THEIR PROFILE</div>',
                unsafe_allow_html=True)
    limit = st.session_state.get("mm_limit", 12)
    if _mobile():
        for _, r in shown.head(limit).iterrows():
            mobile_member_card(
                r, "dir", why=_text(r["email"]),
                actions=[("Open profile", "mopen_dir", open_profile,
                          (r["id"], "Member Management"))])
    else:
        with st.container(border=True, key="card_dir"):
            for _, r in shown.head(limit).iterrows():
                a, b = st.columns([0.7, 6], vertical_alignment="center")
                _md(avatar_html(r["full_name"], r["photo"], 48, "row-tight"), a)
                b.button(str(r["full_name"]), key=f"mrow_dir_{r['id']}",
                         on_click=open_profile, args=(r["id"], "Member Management"),
                         use_container_width=True)
    if len(shown) > limit:
        st.button(f"Show {min(12, len(shown) - limit)} more "
                  f"({len(shown) - limit} left)", type="tertiary", key="mm_more",
                  on_click=_bump, args=("mm_limit", 12, 12))

    st.markdown("#### Manage a member")
    names = dict(zip(shown["id"], shown["full_name"]))
    pick = st.selectbox("Select a member", list(names),
                        format_func=lambda member_id: names[member_id],
                        key=f"mm_pick_{view}")
    name = names[pick]
    now = datetime.now(timezone.utc).isoformat()

    def change(fields, message):
        try:
            (supabase.table("members").update(fields)
             .eq("id", pick).eq("gym_id", gym_id).execute())
        except Exception as error:
            st.error(f"Could not update this member: {error}")
            return
        st.session_state["mm_flash"] = message
        st.rerun()

    if view == "Active":
        a, b = st.columns(2)
        if a.button("Suspend member", key="mm_suspend", use_container_width=True,
                    disabled=not feat["suspend_ready"]):
            change({"suspended": True, "suspended_at": now}, f"{name} suspended.")
        if b.button("Archive member", key="mm_archive", use_container_width=True):
            change({"archived": True, "archived_at": now}, f"{name} archived.")
    elif view == "Suspended":
        a, b = st.columns(2)
        if a.button("Reactivate member", key="mm_reactivate", use_container_width=True):
            change({"suspended": False, "suspended_at": None}, f"{name} reactivated.")
        if b.button("Archive member", key="mm_archive", use_container_width=True):
            change({"archived": True, "archived_at": now}, f"{name} archived.")
    else:
        if st.button("Restore member", key="mm_restore", use_container_width=True):
            change({"archived": False, "archived_at": None}, f"{name} restored.")

    st.caption(
        "Suspend pauses a member and keeps their history. Archive hides them "
        "from your lists. Delete removes them, their activity and their "
        "actions for good."
    )

    if st.session_state.get("mm_delete_confirm") == pick:
        st.warning(f"Permanently delete {name}? This cannot be undone.")
        yes, no = st.columns(2)
        if yes.button("Yes, delete", key="mm_delete_yes", use_container_width=True):
            try:
                (supabase.table("members").delete()
                 .eq("id", pick).eq("gym_id", gym_id).execute())
            except Exception as error:
                st.error(f"Could not delete this member: {error}")
            else:
                st.session_state.pop("mm_delete_confirm", None)
                st.session_state["mm_flash"] = f"{name} deleted."
                st.rerun()
        if no.button("Cancel", key="mm_delete_no", use_container_width=True):
            st.session_state.pop("mm_delete_confirm", None)
            st.rerun()
    elif st.button("Delete permanently", key="mm_delete", use_container_width=True):
        st.session_state["mm_delete_confirm"] = pick
        st.rerun()

# --------------------------------------------------- member profile
def render_member_profile(supabase, gym_id, member_id, assess_fn):
    back = st.session_state.get("profile_back", "Member Management")
    st.button("Back", icon=":material/arrow_back:", key="profile_back_btn", on_click=_go, args=(back,))

    flash = st.session_state.pop("profile_flash", None)
    if flash:
        st.success(flash)

    if not member_id:
        st.info("Pick a member from Member Management or the Risk Radar "
                "to see their profile.")
        return

    try:
        df, feat = fetch_members(supabase, gym_id)
    except Exception as error:
        st.error("Could not load this member.")
        with st.expander("Technical details"):
            st.code(str(error))
        return

    match = df[df["id"] == member_id]
    if match.empty:
        st.warning("This member could not be found. They may have been deleted.")
        return
    m = match.iloc[0]
    name = _text(m["full_name"], "Member")

    try:
        rows = (supabase.table("member_activity").select("*")
                .eq("member_id", member_id).limit(1).execute().data or [])
    except Exception:
        rows = []
    act = rows[0] if rows else None

    scored, drivers_text, action_text = None, "", ""
    try:
        _ro, _ = load_roster(supabase, gym_id, assess_fn)
        _hit = _ro[_ro["id"] == member_id] if not _ro.empty else _ro
        if not _hit.empty:
            scored = _hit.iloc[0]
            drivers_text = scored["drivers"]
            action_text = scored["suggested_action"]
    except Exception:
        scored = None
    if scored is None and act:
        try:
            one = pd.DataFrame([{
                **{c: act.get(c) for c in ACTIVITY_COLS},
                "updated_at": act.get("updated_at"),
                "created_at": act.get("created_at"),
                "membership_end": m["membership_end"],
            }])
            one = apply_live_dates(one)
            scored = assess_fn(one).iloc[0].copy()
            drivers_text = drivers(scored)
            action_text = suggest_action(scored)
            scored["drivers"], scored["suggested_action"] = drivers_text, action_text
        except Exception:
            scored = None

    state = membership_state(m["membership_end"])
    email, phone = _text(m["email"]), _text(m["phone"])
    goal = _text(m["fitness_goal"])

    chips = [membership_chip(state)]
    if m["archived"]:
        chips.append(chip("Archived", "grey"))
    elif m["suspended"]:
        chips.append(chip("Suspended", "amber"))
    if scored is not None:
        chips.append(risk_chip(scored["risk_category"],
                               float(scored["cancellation_probability"])))
    if goal:
        chips.append(chip(goal, "cyan"))

    contact = []
    if email:
        contact.append(chip(email, "grey", href=f"mailto:{email}"))
    if phone:
        contact.append(chip(f"Call {phone}", "grey", href=f"tel:{phone}"))
        digits = whatsapp_digits(phone)
        if digits:
            contact.append(chip("WhatsApp", "lime", href=f"https://wa.me/{digits}"))

    _md(f"""
    <div class="profile-hero">
      {avatar_html(name, m["photo"], 112, "avatar-ring")}
      <div>
        <div class="profile-name">{_esc(name)}</div>
        <div class="chip-row">{"".join(chips)}</div>
        <div class="chip-row">{"".join(contact)}</div>
      </div>
    </div>
    """)

    tab_overview, tab_plan, tab_photo, tab_ck, tab_edit = st.tabs(
        ["Overview", "Membership", "Photo", "Check-in", "Edit details"])

    with tab_overview:
        age = _num(m["age"], None)
        weight = _num(m["weight_kg"], None)
        height = _num(m["height_cm"], None)
        kpi_row([
            ("Age", "—" if age is None else f"{age:.0f}", "cyan", "years"),
            ("Weight", "—" if weight is None else f"{weight:g} kg", "lime", ""),
            ("Height", "—" if height is None else f"{height:g} cm", "lime", ""),
            ("Fitness goal", goal or "—", "white", ""),
        ])
        fee = _num(act.get("monthly_fee") if act else None, None)
        kpi_row([
            ("Membership", state["label"], state["tone"], state["detail"]),
            ("Monthly fee", "—" if fee is None else f"{fee:,.0f}", "lime",
             _text(act.get("membership_type")) + " plan" if act else "No activity yet"),
            ("Renewal date",
             state["end"].strftime("%d %b %Y") if state["end"] else "—", "cyan", ""),
        ])
        if scored is not None:
            level = scored["risk_category"]
            prob = float(scored["cancellation_probability"])
            _md(f"""
            <div class="panel"><h4>Retention risk</h4>
              <div class="chip-row">{risk_chip(level, prob)}
                {chip("Suggested: " + action_text, "cyan")}</div>
              {prob_bar(prob, level)}
              {story_html(scored)}
            </div>
            """)
            if st.button("Create a follow-up action", key="prof_create"):
                if _has_open_action(supabase, member_id):
                    st.info(f"{name} already has an open action in the Action Centre.")
                else:
                    _create_action(supabase, gym_id, member_id, action_text,
                                   int(scored["renewal_due_days"]), note=story_text(scored))
                    st.success("Added to the Action Centre.")
        else:
            st.info("No activity data yet, so there is no risk estimate. "
                    "Add it from the Risk Radar under Data tools.")

    with tab_plan:
        if not feat["profile_ready"]:
            st.warning("Run member_profile_upgrade.sql in Supabase to turn on "
                       "membership dates, then refresh.")
        _md(f"""
        <div class="status-big" style="--tone:{TONES[state["tone"]]}">
          <div>
            <div class="sb-title">{_esc(state["label"])}</div>
            <div class="sb-sub">{_esc(state["detail"])}</div>
          </div>
        </div>
        """)
        fee = _num(act.get("monthly_fee") if act else None, None)
        renewed = _text(m["last_renewed_on"])[:10]
        try:                                    # plan name / member number from an import (phase 16)
            extra = (supabase.table("members").select("plan_name, member_no, member_since")
                     .eq("id", member_id).limit(1).execute().data or [{}])[0]
        except Exception:
            extra = {}
        plan_txt = _text(act.get("membership_type")) if act else "—"
        if _text(extra.get("plan_name")):
            plan_txt = f'{_text(extra.get("plan_name"))} ({plan_txt})' if act else _text(extra.get("plan_name"))
        extra_kv = "".join(f'<div class="kv"><span>{lbl}</span><b>{_esc(_text(extra.get(k))[:10] if k == "member_since" else _text(extra.get(k)))}</b></div>'
                           for k, lbl in (("member_no", "Member number"), ("member_since", "Member since"))
                           if _text(extra.get(k)))
        paid = _num(m["last_payment"], None)
        _md(f"""
        <div class="panel">
          <div class="kv"><span>Plan</span><b>{_esc(plan_txt)}</b></div>
          <div class="kv"><span>Monthly fee</span><b>{"—" if fee is None else f"{fee:,.0f}"}</b></div>
          <div class="kv"><span>Plan runs until</span><b>{state["end"].strftime("%d %b %Y") if state["end"] else "—"}</b></div>
          <div class="kv"><span>Last renewed</span><b>{_esc(renewed) if renewed else "—"}</b></div>
          <div class="kv"><span>Last payment</span><b>{"—" if paid is None else f"{paid:,.0f}"}</b></div>
          {extra_kv}
        </div>
        """)

        st.markdown("#### Record a renewal")
        plans = PLANS
        current_plan = plan_name(act.get("membership_type")) if act else "Monthly"
        r1, r2, r3 = st.columns(3)
        plan = r1.selectbox("Plan", plans, index=plans.index(current_plan),
                            key=f"renew_plan_{member_id}")
        current_end = state["end"]
        start_default = (current_end if current_end and current_end >= date.today()
                         else date.today())
        start = r2.date_input("Starts on", value=start_default,
                              key=f"renew_start_{member_id}_{plan}_{start_default}")
        amount = r3.number_input(
            "Amount paid", min_value=0.0, step=500.0,
            value=float((fee or 0.0) * PLAN_MONTHS[plan]),
            key=f"renew_amt_{member_id}_{plan}")
        new_end = start + timedelta(days=PLAN_DAYS[plan])
        st.caption(f"The plan will run until **{new_end:%d %b %Y}** "
                   f"({PLAN_DAYS[plan]} days).")
        update_fee = st.checkbox(
            "Also update the monthly fee from this payment", value=bool(act),
            key=f"renew_fee_{member_id}", disabled=not act)
        import gympulse_revenue as gr  # local import: gympulse_revenue imports this module
        guard_ok = gr.renewal_guard(supabase, gym_id, member_id, name, m["membership_end"],
                                    plan, "prof")
        if st.button("Save renewal", key="renew_save", type="primary",
                     disabled=not feat["profile_ready"] or not guard_ok):
            import gympulse_revenue as gr  # local import: gympulse_revenue imports this module
            try:
                msg = gr.record_payment(supabase, gym_id, member_id, name, amount, plan, start,
                                        current_end=m["membership_end"], act=act,
                                        update_fee=update_fee)
            except Exception as error:
                st.error(f"Could not save the renewal: {error}")
            else:
                st.session_state["profile_flash"] = msg
                st.rerun()

        with st.expander("Correct the end date"):
            st.caption("Fix a wrong date without recording a payment, for example a typo or a "
                       "member moved over from another system.")
            fix_end = st.date_input("Membership ends on", value=current_end or date.today(),
                                    min_value=date.today() - timedelta(days=730),
                                    key=f"fix_end_{member_id}")
            if st.button("Save end date", key=f"fix_end_save_{member_id}",
                         disabled=not feat["profile_ready"]):
                try:
                    supabase.table("members").update(
                        {"membership_end": fix_end.isoformat()}).eq("id", member_id).execute()
                    if act:
                        supabase.table("member_activity").update(
                            {"renewal_due_days": int(min(max((fix_end - date.today()).days, 0), 730))}
                        ).eq("member_id", member_id).execute()
                except Exception as error:
                    st.error(f"Could not save the date: {error}")
                else:
                    bump_data_version()
                    st.session_state["profile_flash"] = f"End date changed to {fix_end:%d %b %Y}."
                    st.rerun()

    with tab_photo:
        if not feat["profile_ready"]:
            st.warning("Run member_profile_upgrade.sql in Supabase to turn on "
                       "photos, then refresh.")
        c1, c2 = st.columns([1, 2])
        with c1:
            _md(avatar_html(name, m["photo"], 150, "avatar-ring"))
            st.caption("Current photo" if has_photo(m["photo"]) else "No photo yet")
        with c2:
            up = st.file_uploader("Upload a photo",
                                  type=PHOTO_TYPES,
                                  key=f"photo_up_{member_id}")
            if up is not None:
                try:
                    new_photo = process_photo(up.getvalue())
                except Exception:
                    new_photo = None
                    st.error("That image could not be read. Try a different photo.")
                if new_photo:
                    _md(avatar_html(name, new_photo, 110))
                    st.caption("Preview. It is cropped to a square.")
                    if st.button("Save photo", key="photo_save", type="primary",
                                 disabled=not feat["profile_ready"]):
                        try:
                            (supabase.table("members").update({"photo": new_photo})
                             .eq("id", member_id).eq("gym_id", gym_id).execute())
                        except Exception as error:
                            st.error(f"Could not save the photo: {error}")
                        else:
                            st.session_state["profile_flash"] = "Photo saved."
                            st.rerun()
            if has_photo(m["photo"]) and st.button("Remove photo", type="tertiary", key="photo_remove"):
                try:
                    (supabase.table("members").update({"photo": None})
                     .eq("id", member_id).eq("gym_id", gym_id).execute())
                except Exception as error:
                    st.error(f"Could not remove the photo: {error}")
                else:
                    st.session_state["profile_flash"] = "Photo removed."
                    st.rerun()

    with tab_ck:
        code = member_code(member_id)
        ck_all = load_checkins(supabase, gym_id)
        mine = (ck_all[ck_all["member_id"] == member_id]
                if ck_all is not None and not ck_all.empty else pd.DataFrame())
        k1, k2 = st.columns([1, 2])
        with k1:
            uri = qr_data_uri(code)
            if uri:
                _md(f'<img src="{uri}" style="width:170px;border-radius:12px;'
                    f'background:#fff;padding:8px;" alt="Member QR code">')
            st.caption(f"Member code: **{code}**")
        with k2:
            st.write("Print or share this QR code. A scanner, RFID reader or card "
                     "reader that types the code checks the member in automatically.")
            st.button("Check in now", key="prof_checkin", on_click=_do_checkin,
                      args=(supabase, gym_id, member_id, name))
            if mine.empty:
                st.caption("No check-ins yet.")
            else:
                last = mine.sort_values("at", ascending=False).iloc[0]["at"]
                st.caption(f"Last visit: {last:%a %d %b, %H:%M} · "
                           f"{mine['day'].nunique()} visit day(s) in the last 90 days")

    with tab_edit:
        with st.form(f"edit_member_{member_id}"):
            new_name = st.text_input("Full name", value=name)
            e1, e2 = st.columns(2)
            new_email = e1.text_input("Email address", value=email)
            new_phone = e2.text_input("Phone number", value=phone)
            g1, g2, g3 = st.columns(3)
            new_age = g1.number_input("Age", min_value=16, max_value=120,
                                      value=int(min(max(_num(m["age"], 25), 16), 120)))
            new_weight = g2.number_input("Weight (kg)", min_value=1.0, max_value=500.0,
                                         value=float(min(max(_num(m["weight_kg"], 70.0), 1.0), 500.0)),
                                         step=0.5)
            new_height = g3.number_input("Height (cm)", min_value=50.0, max_value=260.0,
                                         value=float(min(max(_num(m["height_cm"], 170.0), 50.0), 260.0)),
                                         step=0.5)
            goal_options = GOALS if goal in GOALS or not goal else [goal] + GOALS
            new_goal = st.selectbox(
                "Fitness goal", goal_options,
                index=goal_options.index(goal) if goal in goal_options else 2)
            saved = st.form_submit_button("Save changes", type="primary", use_container_width=True)
        if saved:
            if not new_name.strip():
                st.error("Please enter the member's full name.")
            else:
                try:
                    (supabase.table("members").update({
                        "full_name": new_name.strip(),
                        "email": new_email.strip() or None,
                        "phone": new_phone.strip() or None,
                        "age": int(new_age),
                        "weight_kg": float(new_weight),
                        "height_cm": float(new_height),
                        "fitness_goal": new_goal,
                    }).eq("id", member_id).eq("gym_id", gym_id).execute())
                except Exception as error:
                    st.error(f"Could not save the changes: {error}")
                else:
                    st.session_state["profile_flash"] = "Details saved."
                    st.rerun()

# --------------------------------------------------------- radar
def _radar_chart(view):
    cols = ["full_name", "days_since_last_visit", "cancellation_probability",
            "risk_category", "monthly_fee"]
    data = view[cols].copy()
    data["cancellation_probability"] = pd.to_numeric(
        data["cancellation_probability"], errors="coerce").fillna(0)
    data["days_since_last_visit"] = pd.to_numeric(
        data["days_since_last_visit"], errors="coerce").fillna(0)
    data["monthly_fee"] = pd.to_numeric(
        data["monthly_fee"], errors="coerce").fillna(0)

    try:
        import altair as alt
        x_max = max(14.0, float(data["days_since_last_visit"].max()) * 1.1)
        colours = alt.Scale(domain=["High", "Medium", "Low"],
                            range=["#FF6B6B", "#FFC44D", "#B7F34A"])
        points = (
            alt.Chart(data).mark_circle(opacity=0.9, stroke="#0B1020", strokeWidth=1.5)
            .encode(
                x=alt.X("days_since_last_visit:Q", title="Days since last visit",
                        scale=alt.Scale(domain=[0, x_max], zero=True),
                        axis=alt.Axis(tickMinStep=1, format="d")),
                y=alt.Y("cancellation_probability:Q", title="Cancellation estimate",
                        scale=alt.Scale(domain=[0, 1], zero=True),
                        axis=alt.Axis(format="%")),
                color=alt.Color("risk_category:N", title="Risk", scale=colours),
                size=alt.Size("monthly_fee:Q", legend=None,
                              scale=alt.Scale(range=[110, 460])),
                tooltip=[
                    alt.Tooltip("full_name:N", title="Member"),
                    alt.Tooltip("risk_category:N", title="Risk"),
                    alt.Tooltip("cancellation_probability:Q", title="Estimate", format=".0%"),
                    alt.Tooltip("days_since_last_visit:Q", title="Days away", format=".0f"),
                    alt.Tooltip("monthly_fee:Q", title="Monthly fee", format=",.0f"),
                ],
            )
        )
        lines = (
            alt.Chart(pd.DataFrame({"y": [0.3, 0.5]}))
            .mark_rule(strokeDash=[5, 5], color="rgba(255,255,255,0.28)")
            .encode(y=alt.Y("y:Q", scale=alt.Scale(domain=[0, 1])))
        )
        chart = alt.layer(lines, points).properties(height=340)
        _show_chart(_style_chart(chart))
        return
    except Exception:
        pass

    try:
        fallback = data.copy()
        fallback = fallback.dropna(subset=["days_since_last_visit",
                                           "cancellation_probability"])
        st.scatter_chart(
            fallback,
            x="days_since_last_visit",
            y="cancellation_probability",
            color="risk_category",
            height=340,
        )
    except Exception:
        st.warning("Couldn't draw the radar chart. Falling back to a table.")
        st.dataframe(
            data[["full_name", "risk_category",
                  "days_since_last_visit", "cancellation_probability"]],
            hide_index=True, use_container_width=True,
        )

PRIORITY_WIDTHS = [0.6, 2.4, 1.0, 1.5, 1.6, 0.9, 1.2]

def _priority_rows(view):
    if _mobile():
        limit = st.session_state.get("prio_limit", 10)
        for _, r in view.head(limit).iterrows():
            mobile_member_card(
                r, "prio", why=story_text(r),
                chips=risk_chip(r["risk_category"]) + chip(r["suggested_action"], "cyan"),
                bar=prob_bar(r["cancellation_probability"], r["risk_category"]),
                meta=f'<div class="money">{r["monthly_fee"]:,.0f} / mo</div>',
                actions=[
                    ("Open profile", "mopen_prio", open_profile, (r["id"], "Risk Radar")),
                    ("Follow up", "mfollow_prio", open_followup, (r["id"], "Risk Radar")),
                ])
        if len(view) > limit:
            st.button(f"Show more ({len(view) - limit} left)", type="tertiary", key="prio_more_m",
                      on_click=_bump, args=("prio_limit", 10, 10))
        return
    head = st.columns(PRIORITY_WIDTHS)
    for col, label in zip(head, ["", "MEMBER", "RISK", "PROBABILITY",
                                 "SUGGESTED ACTION", "FEE", "FOLLOW UP"]):
        _md(f'<div class="th">{label}</div>', col)

    limit = st.session_state.get("prio_limit", 10)
    with st.container(border=True, key="card_priority"):
        for i, (_, r) in enumerate(view.head(limit).iterrows()):
            if i:
                _md('<hr style="border:none;border-top:1px solid '
                    'rgba(255,255,255,0.07);margin:6px 0;">')
            c = st.columns(PRIORITY_WIDTHS, vertical_alignment="center")
            _md(avatar_html(r["full_name"], r.get("photo"), 42, "row-tight"), c[0])
            c[1].button(str(r["full_name"]), key=f"mrow_prio_{r['id']}",
                        on_click=open_profile, args=(r["id"], "Risk Radar"),
                        use_container_width=True)
            _md(story_html(r), c[1])
            _md(risk_chip(r["risk_category"]), c[2])
            _md(prob_bar(r["cancellation_probability"], r["risk_category"]), c[3])
            _md(chip(r["suggested_action"], "cyan"), c[4])
            _md(f'<div class="money">{r["monthly_fee"]:,.0f}</div>', c[5])
            c[6].button("Follow up", key=f"follow_prio_{r['id']}", on_click=open_followup,
                        args=(r["id"], "Risk Radar"), use_container_width=True)
    if len(view) > limit:
        st.button(f"Show more ({len(view) - limit} left)", type="tertiary", key="prio_more",
                  on_click=_bump, args=("prio_limit", 10, 10))

def render_risk_radar(supabase, gym_id, assess_fn):
    page_header("Member Risk Radar",
                "Every member, scored and ranked, with the reasons behind the flag.",
                "Retention intelligence")
    flash = st.session_state.pop("flash", None)
    if flash:
        st.success(flash)
    try:
        roster, missing = load_roster(supabase, gym_id, assess_fn)
    except Exception as e:
        st.error("Couldn't load the radar. Have you run schema.sql?")
        with st.expander("Technical details"):
            st.code(str(e))
        return

    def data_tools(expanded):
        with st.expander("Data tools · update activity, import a CSV, archive members",
                         expanded=expanded):
            t1, t2, t3 = st.tabs(["Update activity", "Import CSV", "Archive & delete"])
            with t1:
                _activity_editor(supabase, gym_id, roster, missing, use_expander=False)
            with t2:
                render_csv_import(supabase, gym_id, use_expander=False)
            with t3:
                _member_manager(supabase, gym_id, roster, missing, use_expander=False)

    if roster.empty:
        st.info("Add attendance data so the model can score your members.")
        data_tools(True)
        return

    k = kpis(roster, pd.DataFrame())
    low = k["members_scored"] - k["high"] - k["medium"]
    kpi_row([
        ("Members scored", k["members_scored"], "cyan", "Included in the radar"),
        ("High risk", k["high"], "red", "Need you first"),
        ("Medium risk", k["medium"], "amber", "Keep an eye on"),
        ("Low risk", low, "lime", "Looking healthy"),
        ("Renewals ≤30d at risk", k["renewals_30d_at_risk"], "white", "Renewing soon"),
    ])
    data_tools(False)

    st.markdown('<div class="section-label">FILTER</div>', unsafe_allow_html=True)
    f1, f2, f3 = st.columns([2, 2, 3])
    levels = f1.multiselect("Risk level", ["High", "Medium", "Low"], ["High", "Medium", "Low"])
    plans = f2.multiselect("Membership", PLANS, PLANS)
    search = f3.text_input("Search member", placeholder="Type a name")
    view = roster[roster["risk_category"].isin(levels) & roster["membership_type"].map(plan_name).isin(plans)]
    if search:
        view = view[view["full_name"].str.contains(search, case=False, na=False)]
    if view.empty:
        st.info("No members match these filters.")
        return

    st.markdown('<div class="section-label">THE RADAR</div>', unsafe_allow_html=True)
    st.caption("Right = longer absent. Up = higher cancellation estimate. "
               "Dashed lines mark Medium (30%) and High (50%).")
    _radar_chart(view)

    st.markdown('<div class="section-label">PRIORITY LIST · CLICK A NAME TO OPEN THEIR PROFILE</div>',
                unsafe_allow_html=True)
    _priority_rows(view)

    st.markdown('<div class="section-label">QUICK VIEW</div>', unsafe_allow_html=True)
    pick = st.selectbox("Select a member", view["full_name"], key="radar_pick")
    m = view[view["full_name"] == pick].iloc[0]
    d1, d2, d3 = st.columns(3)
    _md(kpi_card("Cancellation estimate", f"{m['cancellation_probability']:.0%}",
                 RISK_TONE.get(m["risk_category"], "lime"), m["risk_category"] + " risk"), d1)
    _md(kpi_card("Attendance change", f"{int(m['attendance_change']):+d}",
                 "cyan", "recent pace vs their usual"), d2)
    _md(kpi_card("Renews in", f"{int(m['renewal_due_days'])} days", "white", ""), d3)
    _md(f'<div class="panel"><div class="kv"><span>Why flagged</span><b>{_esc(m["drivers"])}</b></div>'
        f'<div class="kv"><span>Suggested</span><b>{_esc(m["suggested_action"])}</b></div></div>')
    b1, b3, b2 = st.columns(3)
    b1.button("Open full profile", key="radar_profile", on_click=open_profile,
              args=(m["id"], "Risk Radar"), use_container_width=True)
    b3.button("Message this member", key="radar_followup", on_click=open_followup,
              args=(m["id"], "Risk Radar"), use_container_width=True)
    if b2.button("Create follow-up action", key="radar_create", use_container_width=True):
        if not _has_open_action(supabase, m["id"]):
            _create_action(supabase, gym_id, m["id"], m["suggested_action"],
                           m["renewal_due_days"])
            st.session_state["ac_flash"] = f"Follow-up action added for {pick}."
        else:
            st.session_state["ac_flash"] = f"{pick} already has an open action. Here it is."
        st.session_state["navigate_to"] = "Action Centre"
        st.rerun()
    st.caption("Estimates come from a model trained on synthetic data. Use them "
               "to prioritise conversations, not to make decisions about members.")

# ------------------------------------------------- trainers & plays
TRAINER_PLAYS = {"Free PT session", "Trainer intro", "Goal review"}
APP_URL = os.environ.get("APP_URL", "https://usegympulseai.com").rstrip("/")


def trainer_link(t):
    token = _text((t or {}).get("share_token"))
    return f"{APP_URL}/?trainer={token}" if token else ""


def class_when(dt):
    return f"{dt:%a %d %b, %I:%M %p}"


def class_when_long(dt):
    return f"{dt:%A %d %B at %I:%M %p}"


PLAY_TEXT = {
    "Personal call": "Hi {first}, it's {owner} from {biz}.{missed} I'd love to give you a quick call to hear how your training is going{goal_part} and see how we can help. When is a good time for you?",
    "WhatsApp check-in": "Hi {first}! This is {owner} from {biz}.{missed} Just checking in to see how you're finding your workouts{goal_part}. Is there anything we can do to make your experience even better?",
    "Feedback request": "Hi {first}, your opinion matters a lot to us at {biz}. Could you spare a minute to tell us what we're doing well and what we could improve? Reply here and I'll read every word.",
    "Renewal offer": "Hi {first}, I have something special for you. Your membership at {biz} {renew_when}, and you can renew and {offer}.{deadline_part} Reply RENEW and I'll lock it in for you. Thank you for being part of {biz}!",
    "Renewal check-in": "Hi {first}, it's {owner} from {biz}. Your membership {renew_when}, and I'd love to keep helping you{goal_part}. Can I help you renew, or is there anything we could do better for you? Just reply here.",
    "Free PT session": "Hi {first}! {biz} would like to gift you a free personal training session with {tname}{tspec}. It's a great way to fine-tune your plan{goal_part}. Call or message {tphone} to book your slot, or reply here and I'll arrange it.{tprofile}",
    "Trainer intro": "Hi {first}, I'd like you to meet {tname}{tspec}, one of our trainers at {biz}. {tname} would love to support you{goal_part}. You can reach them on {tphone}, or reply here and I'll introduce you at the gym.{tprofile}",
    "Goal review": "Hi {first}! It's time for a quick goal review at {biz}{goal_part}. {tname}{tspec} can sit down with you for 15 minutes to check your progress and update your plan. Message {tphone} to book a time.{tprofile}",
    "Class invite": "Hi {first}! We'd love to see you at {title} at {biz}{when_part}{where_part}. It's a great way to train alongside other members and get back into your rhythm. Reply YES and I'll save your spot.",
    "Group challenge": "Hi {first}! {biz} is launching the {title}{when_part}{where_part}. {reward_line}It's a fun way to stay motivated alongside other members. Reply JOIN and I'll add you to the group before spots fill up.",
    "Bring-a-friend invite": "Hi {first}! Here's a reward just for you: bring a friend to {biz}{when_part} and {reward}. Your friend gets to try {biz}, and you both win. Reply with your friend's name and the day you'd like to come, and I'll set it up.",
    "Milestone shout-out": "Hi {first}! Congratulations from all of us at {biz}. Your consistency has really paid off and we're proud of your progress. Keep it up!",
    "Welcome-back note": "Hi {first}, it's so good to see you back at {biz}! We missed you, and we're here to help you get back into your rhythm. Let me know if you need anything.",
}


def member_message_ctx(r):
    """What a message may say about a member: only facts from their record."""
    get = r.get if hasattr(r, "get") else (lambda k, d=None: d)
    return {"name": _text(get("full_name")), "phone": _text(get("phone")),
            "email": _text(get("email")), "goal": _text(get("fitness_goal")),
            "renew_days": get("renewal_due_days"), "days_away": get("days_since_last_visit")}


def _biz_ctx():
    p = st.session_state.get("user_profile") or {}
    return {"biz": _text(p.get("business_name"), "our gym"),
            "owner": _text(p.get("full_name"), ""),
            "s": dict(p.get("settings") or {})}


def _signoff(ctx):
    return ctx["s"].get("signoff") or "\n".join(
        x for x in (ctx["owner"], ctx["biz"]) if x)


def play_message(play, member, trainer, ctx, details=None):
    d = details or {}
    s = ctx["s"]
    first = (member.get("name") or "").split(" ")[0] or "there"
    goal = member.get("goal") or ""
    tname = trainer["full_name"] if trainer else "one of our trainers"
    link = trainer_link(trainer) if trainer else ""
    when, where, reward = d.get("when") or "", d.get("where") or "", d.get("reward") or ""
    vals = dict(
        first=first, biz=ctx["biz"], owner=ctx["owner"] or "the team",
        tname=tname,
        tspec=f" ({trainer['specialty']})" if trainer and trainer.get("specialty") else "",
        tphone=(trainer.get("phone") if trainer and trainer.get("phone")
                else s.get("biz_phone") or "our front desk"),
        goal_part=_goal_phrase(goal),
        tprofile=(f"\n\nSee {tname}'s full profile and photo here: {link}" if link else ""),
        title=d.get("title") or "our next session",
        when_part=f" on {when}" if when else "",
        where_part=f" ({where})" if where else "",
        reward_line=f"The prize: {reward}. " if reward else "",
        reward=reward or "you both get a thank-you gift from us",
        offer=d.get("offer") or "",
        deadline_part=(f" This offer is open until {d['deadline']}." if d.get("deadline") else ""),
        renew_when=_renew_phrase(member.get("renew_days")),
        missed=(" It's been a little while since we've seen you, and we miss having you around."
                if _num(member.get("days_away"), 0) >= 10 else ""),
    )
    if play == "Renewal offer" and not d.get("offer"):
        play = "Renewal check-in"     # no gym-approved offer: never invent one
    text = PLAY_TEXT.get(
        play, "Hi {first}, it's {owner} from {biz}. Just checking in.").format(**vals)
    return text + "\n\n" + _signoff(ctx)


def _goal_phrase(goal):
    """'Weight loss' -> ' towards your goal of weight loss'; 'Lose weight' -> ' as you work to lose weight'."""
    g = _text(goal).strip().rstrip(".").lower()
    if not g:
        return ""
    if g.split()[0] in {"lose", "build", "stay", "train", "gain", "get", "improve", "run",
                        "tone", "increase", "reduce", "keep", "become", "prepare"}:
        return f" as you work to {g}"
    return f" towards your goal of {g}"


def _renew_phrase(days):
    d = _num(days, None)
    if d is None:
        return "is coming up for renewal"
    d = int(d)
    if d < 0:
        return f"ended {_plural(-d, 'day')} ago"
    if d == 0:
        return "is due for renewal today"
    if d == 1:
        return "is due for renewal tomorrow"
    return f"is due for renewal in {d} days"


def renewal_message(name, days, ctx):
    s = ctx["s"]
    first = (name or "").split(" ")[0] or "there"
    if days > 1:
        when = f"your membership with {ctx['biz']} is due for renewal in {days} days."
    elif days == 1:
        when = f"your membership with {ctx['biz']} is due for renewal tomorrow."
    elif days == 0:
        when = f"your membership with {ctx['biz']} is due for renewal today."
    else:
        n = abs(days)
        when = (f"your membership with {ctx['biz']} ended {n} day"
                f"{'s' if n != 1 else ''} ago.")
    phone = f" You can reach us on {s['biz_phone']}." if s.get("biz_phone") else ""
    return (f"Hi {first}, I hope you're doing well! Just a gentle note that {when} "
            f"We'd truly love to keep seeing you at {ctx['biz']}, and whenever it suits you "
            f"we're happy to help you renew or answer any questions.{phone} "
            f"No pressure at all, and thank you for being part of our family.\n\n"
            + _signoff(ctx))


def _fetch_trainers(supabase, gym_id):
    try:
        return (supabase.table("trainers").select("*").eq("gym_id", gym_id)
                .order("created_at").execute().data or [])
    except Exception:
        return []


def load_trainers(supabase, gym_id):
    return _cached(("trainers", gym_id), lambda: _fetch_trainers(supabase, gym_id))


def trainer_card_html(t):
    name = _text(t.get("full_name"), "Trainer")
    phone = _text(t.get("phone"))
    chips = chip(_text(t.get("specialty"), "Trainer"), "cyan")
    if phone:
        chips += chip(f"Call {phone}", "grey", href=f"tel:{phone}")
        digits = whatsapp_digits(phone)
        if digits:
            chips += chip("WhatsApp", "lime", href=f"https://wa.me/{digits}")
    bio = _text(t.get("bio"))
    bio_html = f'<div class="why" style="padding:6px 0 0;">{_esc(bio)}</div>' if bio else ""
    return (f'<div class="profile-hero" style="padding:16px 18px;margin:8px 0;">'
            f'{avatar_html(name, t.get("photo"), 76, "avatar-ring")}'
            f'<div><div class="profile-name" style="font-size:22px;">{_esc(name)}</div>'
            f'<div class="chip-row">{chips}</div>{bio_html}</div></div>')


def render_public_trainer(supabase, token):
    """Public, read-only trainer page opened from a private link."""
    data = None
    try:
        data = supabase.rpc("public_trainer", {"p_token": str(token)}).execute().data
    except Exception:
        data = None
    if isinstance(data, list):
        data = data[0] if data else None
    if not data:
        st.error("This profile link is not valid or has been switched off.")
        return
    gym = _text(data.get("gym"))
    _md(f'<div class="pg-head"><div class="pg-eyebrow">Meet your trainer</div>'
        f'<div class="pg-title">{_esc(_text(data.get("full_name"), "Trainer"))}</div>'
        + (f'<div class="pg-sub">at {_esc(gym)}</div>' if gym else "") + "</div>")
    _md(trainer_card_html(data))


def render_trainers_editor(supabase, gym_id):
    st.caption("Trainers you add here can be introduced to members from the "
               "Retention Pillars plays. Each trainer gets a private profile link.")
    trainers = load_trainers(supabase, gym_id)
    if not trainers:
        st.info("No trainers yet. Add your first one below.")
    for t in trainers:
        _md(trainer_card_html(t))
        link = trainer_link(t)
        with st.expander(f"Edit {t['full_name']} · private link"):
            if link:
                st.caption("Private profile link, sent to members with trainer messages:")
                st.code(link)
            else:
                st.caption("Run the trainers SQL to switch on private profile links.")
            with st.form(f"edit_tr_{t['id']}"):
                n = st.text_input("Full name", value=_text(t.get("full_name")))
                sp = st.text_input("Specialty", value=_text(t.get("specialty")))
                ph = st.text_input("Phone number", value=_text(t.get("phone")))
                bio = st.text_area("Short bio", value=_text(t.get("bio")))
                pic = st.file_uploader("New photo (optional)", type=PHOTO_TYPES,
                                       key=f"tr_pic_{t['id']}")
                ok = st.form_submit_button("Save trainer", type="primary", use_container_width=True)
            if ok and n.strip():
                fields = {"full_name": n.strip(), "specialty": sp.strip() or None,
                          "phone": ph.strip() or None, "bio": bio.strip() or None}
                if pic is not None:
                    try:
                        fields["photo"] = process_photo(pic.getvalue())
                    except Exception:
                        st.warning("The photo could not be read, so it was not changed.")
                (supabase.table("trainers").update(fields)
                 .eq("id", t["id"]).eq("gym_id", gym_id).execute())
                st.session_state["settings_flash"] = "Trainer saved."
                st.rerun()
            if st.button("Remove trainer", type="tertiary", key=f"tr_rm_{t['id']}"):
                (supabase.table("trainers").delete()
                 .eq("id", t["id"]).eq("gym_id", gym_id).execute())
                st.session_state["settings_flash"] = "Trainer removed."
                st.rerun()
    st.markdown("#### Add a trainer")
    with st.form("add_trainer", clear_on_submit=True):
        n = st.text_input("Full name")
        sp = st.text_input("Specialty", placeholder="e.g. Strength and conditioning")
        ph = st.text_input("Phone number")
        bio = st.text_area("Short bio (optional)")
        pic = st.file_uploader("Photo", type=PHOTO_TYPES, key="tr_new_pic")
        ok = st.form_submit_button("Add trainer", type="primary", use_container_width=True)
    if ok:
        if not n.strip():
            st.error("Please enter the trainer's name.")
        else:
            row = {"gym_id": gym_id, "full_name": n.strip(),
                   "specialty": sp.strip() or None, "phone": ph.strip() or None,
                   "bio": bio.strip() or None}
            if pic is not None:
                try:
                    row["photo"] = process_photo(pic.getvalue())
                except Exception:
                    st.warning("The photo could not be read, so the trainer was added without one.")
            try:
                supabase.table("trainers").insert(row).execute()
            except Exception as error:
                st.error(f"Could not add the trainer. Have you run the SQL? {error}")
            else:
                st.session_state["settings_flash"] = "Trainer added."
                st.rerun()


def _start_play(supabase, aid):
    try:
        (supabase.table("retention_actions").update({"status": "In progress"})
         .eq("id", aid).execute())
        st.session_state["ac_flash"] = "Play started. It is now In progress on your board."
    except Exception as error:
        st.session_state["ac_flash"] = f"Could not update: {error}"


def _sent_from_panel(supabase, a):
    play = a["action_type"]
    method = PLAY_INFO.get(play, {}).get("channel", "WhatsApp")
    method = "WhatsApp" if method in ("Call", "In person") else method
    try:
        mark_contacted(supabase, a["id"], method, play=play)
        days = PLAY_INFO.get(play, {}).get("follow", 3)
        st.session_state["ac_flash"] = f"Marked as contacted. Follow-up due in {_plural(days, 'day')}."
    except Exception as error:
        st.session_state["ac_flash"] = f"Could not update: {error}"


def pick_trainer(trainers, goal=""):
    """The trainer whose specialty best matches the member's goal."""
    if not trainers:
        return None
    words = {w for w in re.findall(r"[a-z]+", str(goal or "").lower()) if len(w) > 3}
    synonyms = {"weight": {"loss", "fat", "hiit", "conditioning", "cardio"},
                "muscle": {"strength", "bodybuilding", "hypertrophy"},
                "strength": {"strength", "powerlifting"},
                "endurance": {"cardio", "running", "conditioning"}}
    for w in list(words):
        words |= synonyms.get(w, set())
    best = max(trainers, key=lambda t: len(words & set(
        re.findall(r"[a-z]+", _text(t.get("specialty")).lower()))))
    return best


def next_class(classes):
    now = datetime.now(APP_TZ).replace(tzinfo=None)
    upcoming = sorted((c for c in classes if c.get("_start") and c["_start"] > now),
                      key=lambda c: c["_start"])
    return upcoming[0] if upcoming else None


def _message_from_play(aid, member_id):
    st.session_state["fu_prefill"] = st.session_state.get(f"pm_{aid}", "")
    open_followup(member_id, "Action Centre")


def _play_panel(supabase, a):
    ctx_play = st.session_state.get("_play_ctx") or {}
    member = (ctx_play.get("contacts") or {}).get(a["member_id"])
    if not member:
        return
    ctx = _biz_ctx()
    play = a["action_type"]
    trainers = ctx_play.get("trainers") or {}
    trainer = trainers.get(a.get("trainer_id")) if play in TRAINER_PLAYS else None
    if play in TRAINER_PLAYS and trainer is None and trainers:
        trainer = pick_trainer(list(trainers.values()), member.get("goal"))
    details = a.get("details")
    if not isinstance(details, dict):
        details = {}
    if play == "Class invite" and not details.get("title"):
        nxt = next_class(ctx_play.get("classes") or [])
        if nxt:
            details = {**details, "title": nxt["name"], "when": class_when_long(nxt["_start"])}
    with st.expander("Do this play"):
        if play in TRAINER_PLAYS:
            if trainer:
                _md(trainer_card_html(trainer))
                if trainer_link(trainer):
                    st.caption("A private link to this trainer's full profile is "
                               "included in the message.")
            elif trainers:
                st.caption("No trainer was chosen for this play.")
            else:
                st.caption("Add trainers in Settings → Trainers to attach a profile.")
        msg = st.text_area("Message", value=play_message(play, member, trainer, ctx, details),
                           key=f"pm_{a['id']}", height=170)
        c1, c2, c3 = st.columns(3)
        digits = whatsapp_digits(member.get("phone"))
        if digits:
            c1.link_button("WhatsApp", f"https://wa.me/{digits}?text={quote(msg)}",
                           use_container_width=True)
        if member.get("email"):
            c2.link_button("Email", f"mailto:{member['email']}?subject="
                           f"{quote('A note from ' + ctx['biz'])}&body={quote(msg)}",
                           use_container_width=True)
        if member.get("phone"):
            c3.link_button("Call", f"tel:{member['phone']}", use_container_width=True)
        if not (digits or member.get("email")):
            st.caption("This member has no phone or email yet. Add one on their profile.")
        if action_stage(a) in ("Started", "In progress"):
            st.button("I've sent it: mark contacted", key=f"ps_{a['id']}",
                      on_click=_sent_from_panel, args=(supabase, a),
                      use_container_width=True)


# ------------------------------------------------- renewal reminders
def _fetch_sent(supabase, gym_id):
    try:
        rows = (supabase.table("reminder_log").select("member_id, sent_at")
                .eq("gym_id", gym_id).eq("kind", "renewal").execute().data or [])
    except Exception:
        return None
    sent = {}
    for r in rows:
        t = pd.to_datetime(r.get("sent_at"), errors="coerce", utc=True)
        if pd.isna(t):
            continue
        t = t.tz_convert(APP_TZ).tz_localize(None).normalize()
        if r["member_id"] not in sent or t > sent[r["member_id"]]:
            sent[r["member_id"]] = t
    return sent


def load_sent(supabase, gym_id):
    sent = _cached(("sent", gym_id), lambda: _fetch_sent(supabase, gym_id))
    return ({}, False) if sent is None else (sent, True)


def renewal_queue(roster, sent, remind_days=7, max_lapsed_days=60):
    if roster is None or roster.empty or "membership_end" not in roster.columns:
        return []
    today = pd.Timestamp(today_local())
    end = pd.to_datetime(roster["membership_end"], errors="coerce").dt.normalize()
    left = (end - today).dt.days
    out = []
    for (_, r), d in zip(roster.iterrows(), left):
        if pd.isna(d):
            continue
        d = int(d)
        if d > remind_days or d < -max_lapsed_days:
            continue
        last = sent.get(r["id"])
        if last is not None and (today - last).days < 7:
            continue
        out.append((r, d, last))
    out.sort(key=lambda t: t[1])
    return out


def renewal_due_count(supabase, gym_id, roster):
    s = _biz_ctx()["s"]
    if not s.get("auto_reminders", True):
        return 0
    sent, _ = load_sent(supabase, gym_id)
    return len(renewal_queue(roster, sent, int(s.get("remind_days", 7))))


def _log_reminder(supabase, gym_id, member_id, name):
    try:
        supabase.table("reminder_log").insert(
            {"gym_id": gym_id, "member_id": member_id, "kind": "renewal"}).execute()
        st.session_state["pay_flash"] = f"Reminder to {name} marked as sent. Next one in 7 days."
        row = open_action_for(supabase, member_id)
        if row and row.get("action_type") in ("Renewal offer", "Personal call", "WhatsApp check-in"):
            mark_contacted(supabase, row["id"], "WhatsApp", play=row.get("action_type"))
            st.session_state["pay_flash"] += f" Their {row['action_type']} is marked contacted."
    except Exception:
        st.session_state["pay_flash"] = "Could not save. Have you run the reminder_log SQL?"


def render_renewal_reminders(supabase, gym_id, roster):
    ctx = _biz_ctx()
    s = ctx["s"]
    st.markdown('<div class="section-label">RENEWAL REMINDERS</div>',
                unsafe_allow_html=True)
    if not s.get("auto_reminders", True):
        st.caption("Automatic renewal reminders are switched off in Settings → Preferences.")
        return
    sent, ok = load_sent(supabase, gym_id)
    if not ok:
        st.warning("Reminder tracking needs the reminder_log table. Run the SQL setup, then refresh.")
    remind_days = int(s.get("remind_days", 7))
    queue = renewal_queue(roster, sent, remind_days)
    if not queue:
        st.success("No reminders due. Members who have paid are skipped automatically.")
        return
    st.caption(f"{len(queue)} member(s) are within {remind_days} days of renewal or lapsed. "
               "Each gets a gentle reminder from your business, repeated weekly until they pay.")
    for r, days, last in queue[:10]:
        name = _text(r["full_name"])
        with st.container(border=True, key=f"card_rem_{r['id']}"):
            if days > 0:
                when, tone = f"Due in {days} day{'s' if days != 1 else ''}", "cyan" if days > 3 else "amber"
            elif days == 0:
                when, tone = "Due today", "amber"
            else:
                when, tone = f"Lapsed {abs(days)} day{'s' if abs(days) != 1 else ''} ago", "red"
            extra = chip(f"Last reminded {last:%d %b}", "grey") if last is not None else ""
            _md(f'<div style="display:flex;align-items:center;gap:12px;">'
                f'{avatar_html(name, r.get("photo"), 44)}<div>'
                f'<div style="font-weight:800;color:#F4F7FB;">{_esc(name)}</div>'
                f'<div class="chip-row">{chip(when, tone)}{extra}</div></div></div>')
            msg = st.text_area("Message", value=renewal_message(name, days, ctx),
                               key=f"rm_{r['id']}", height=140)
            c1, c2, c3 = st.columns(3)
            digits = whatsapp_digits(r.get("phone"))
            email = _text(r.get("email"))
            if digits:
                c1.link_button("WhatsApp", f"https://wa.me/{digits}?text={quote(msg)}",
                               use_container_width=True)
            if email:
                c2.link_button("Email", f"mailto:{email}?subject="
                               f"{quote('A note from ' + ctx['biz'])}&body={quote(msg)}",
                               use_container_width=True)
            c3.button("Mark as sent", key=f"rms_{r['id']}", on_click=_log_reminder,
                      args=(supabase, gym_id, r["id"], name), use_container_width=True)
    if len(queue) > 10:
        st.caption(f"+{len(queue) - 10} more due.")

# ------------------------------------------------------- action centre
def _remove_from_board(supabase, a):
    aid = a["id"]
    done = a.get("status") == "Done"
    if st.session_state.get("rm_action") == aid:
        st.warning("Remove from the board?" + (" Its result stays in Business Insights." if done else ""))
        y, n = st.columns(2)
        if y.button("Yes, remove", key=f"ry_{aid}", use_container_width=True):
            if done:
                (supabase.table("retention_actions")
                 .update({"archived_at": datetime.now(timezone.utc).isoformat()})
                 .eq("id", aid).execute())
            else:
                supabase.table("retention_actions").delete().eq("id", aid).execute()
            st.session_state.pop("rm_action", None)
            st.rerun()
        if n.button("Cancel", key=f"rn_{aid}", use_container_width=True):
            st.session_state.pop("rm_action", None)
            st.rerun()
    elif st.button("Remove from board", type="tertiary", key=f"rx_{aid}", use_container_width=True):
        st.session_state["rm_action"] = aid
        st.rerun()


def _contact_line(a):
    if _blank(a.get("contacted_at")):
        return ""
    try:
        when = pd.Timestamp(a["contacted_at"]).tz_convert(APP_TZ)
        when_txt = f"{when:%d %b}"
    except Exception:
        when_txt = str(a["contacted_at"])[:10]
    method = _text(a.get("contact_method"), "message")
    follow = a.get("follow_up_on") or a.get("due_date")
    tail = f" · follow up {str(follow)[:10]}" if not _blank(follow) else ""
    return f"Contacted by {method.lower()} on {when_txt}{tail}"


def _lifecycle_controls(supabase, a, prefix):
    """Every step of a play, the same on the board, the list and phones."""
    aid, play = a["id"], a["action_type"]
    stage = action_stage(a)
    info = PLAY_INFO.get(play, {})
    note = a.get("note")
    note = note if isinstance(note, str) else ""
    if stage in ("Resolved", "Unsuccessful"):
        if note:
            st.caption(note)
        return
    new_note = st.text_area("Note", value=note, key=f"{prefix}_n_{aid}", height=92,
                            placeholder="Add a note…", label_visibility="collapsed")
    if stage == "Started":
        if st.button("Start this play", key=f"{prefix}_s_{aid}", type="primary",
                     use_container_width=True):
            (supabase.table("retention_actions")
             .update({"status": "In progress", "note": new_note}).eq("id", aid).execute())
            st.rerun()
    if stage in ("Started", "In progress"):
        with st.popover("Mark contacted", use_container_width=True):
            default = info.get("channel", "WhatsApp")
            method = st.selectbox("How did you reach them?", CONTACT_METHODS,
                                  index=CONTACT_METHODS.index(default) if default in CONTACT_METHODS else 0,
                                  key=f"{prefix}_cm_{aid}")
            days = st.number_input("Follow up in (days)", 1, 60, int(info.get("follow", 3)),
                                   key=f"{prefix}_fd_{aid}")
            if st.button("Save contact", key=f"{prefix}_cs_{aid}", type="primary",
                         use_container_width=True):
                saved = mark_contacted(supabase, aid, method, days, play, new_note)
                st.session_state["ac_flash"] = (
                    f"Contact recorded. Follow-up due in {_plural(int(days), 'day')}."
                    + ("" if saved == "full" else " Run sql/phase2_retention.sql to keep the "
                       "contact method and date as their own fields."))
                st.rerun()
    else:
        o1, o2 = st.columns([1.3, 1])
        outcome = o1.selectbox("Outcome", OUTCOMES, key=f"{prefix}_o_{aid}",
                               label_visibility="collapsed",
                               help="Retained: they renewed or came back. Cancelled: they left. "
                                    "No response: you couldn't reach them.")
        if o2.button("Record outcome", key=f"{prefix}_d_{aid}", type="primary",
                     use_container_width=True):
            close_action(supabase, aid, outcome, new_note)
            st.rerun()
        if st.button("Contacted again", key=f"{prefix}_ca_{aid}", type="tertiary",
                     use_container_width=True):
            mark_contacted(supabase, aid, _text(a.get("contact_method"), info.get("channel", "WhatsApp")),
                           info.get("follow", 3), play, new_note)
            st.rerun()


def _action_card(supabase, a, names, photos, status, prefix):
    member_id = a["member_id"]
    who = names.get(member_id, "Archived member")
    stage = action_stage(a)
    with st.container(border=True, key=f"card_{prefix}_{a['id']}"):
        ca, cb = st.columns([0.34, 1], vertical_alignment="center")
        _md(avatar_html(who, photos.get(member_id), 38, "row-tight"), ca)
        cb.button(str(who), key=f"mrow_{prefix}_{a['id']}", on_click=open_profile,
                  args=(member_id, "Action Centre"), use_container_width=True)
        chips = chip(a["action_type"], "cyan") + stage_chip(stage)
        if stage in ("Started", "In progress"):
            chips += due_chip(a.get("due_date"), status)
        if status == "Done":
            chips += outcome_chip(a.get("outcome"))
        _md(f'<div class="chip-row">{chips}</div>')
        objective = PLAY_INFO.get(a["action_type"], {}).get("objective")
        line = _contact_line(a)
        if objective or line:
            _md(f'<div class="why" style="padding:4px 0 2px">'
                + (f'Goal: {_esc(objective)}' if objective else "")
                + (f'<br>{_esc(line)}' if line else "") + "</div>")
        import gympulse_automation as ga  # local import: gympulse_automation imports this module
        ga.render_assign_control(supabase, a, prefix)
        if status != "Done":
            _play_panel(supabase, a)
            st.button("Message in Follow-ups", key=f"follow_{prefix}_{a['id']}",
                      on_click=_message_from_play, args=(a["id"], member_id),
                      use_container_width=True)
        _lifecycle_controls(supabase, a, prefix)
        _remove_from_board(supabase, a)

BOARD_TONES = {"To do": "cyan", "In progress": "amber", "Done": "lime"}
BOARD_COLUMNS = [
    ("To start", ("Started",), "cyan"),
    ("In progress", ("In progress",), "amber"),
    ("Contacted · follow up", ("Contacted", "Follow-up due"), "white"),
    ("Done", ("Resolved", "Unsuccessful"), "lime"),
]

def _visible_actions(actions):
    if actions.empty:
        return actions
    if "archived_at" in actions.columns:
        return actions[actions["archived_at"].isna()]
    return actions

def _with_stage(actions):
    if actions.empty:
        return actions.assign(stage=pd.Series(dtype=str))
    return actions.assign(stage=[action_stage(r) for r in actions.to_dict("records")])

def _kanban(supabase, actions, names, photos):
    actions = _with_stage(actions)
    cols = st.columns(len(BOARD_COLUMNS))
    for col, (title, stages, tone) in zip(cols, BOARD_COLUMNS):
        sub = actions[actions["stage"].isin(stages)]
        if "Done" in title and "completed_at" in sub.columns:
            sub = sub.sort_values("completed_at", ascending=False, na_position="last")
        elif "follow" in title:
            sub = sub.sort_values("due_date", na_position="last")
        with col:
            due_n = int((sub["stage"] == "Follow-up due").sum())
            _md(f'<div class="kb-head" style="--tone:{TONES[tone]}">'
                f'<span>{title}</span><b>{len(sub)}</b></div>'
                + (f'<div class="kb-empty" style="color:#FF6B6B">{due_n} follow-up(s) due</div>' if due_n else ""))
            if sub.empty:
                _md('<div class="kb-empty">Nothing here yet</div>')
            shown = sub.head(10) if "Done" in title else sub
            for _, a in shown.iterrows():
                _action_card(supabase, a, names, photos, a["status"], "kb")
            if "Done" in title and len(sub) > 10:
                st.caption(f"+{len(sub) - 10} older ones in the List view.")

def _list_board(supabase, actions, names, photos):
    actions = _with_stage(actions)
    tabs = st.tabs([f"{title} ({int(actions['stage'].isin(stages).sum())})"
                    for title, stages, _ in BOARD_COLUMNS])
    for tab, (title, stages, _) in zip(tabs, BOARD_COLUMNS):
        with tab:
            sub = actions[actions["stage"].isin(stages)]
            if sub.empty:
                st.caption("Nothing here.")
            for _, a in sub.iterrows():
                _action_card(supabase, a, names, photos, a["status"], "ls")


def _pick_play(pillar, play):
    st.session_state["play_type"] = (pillar, play)
    st.session_state["play_open"] = True


def _play_details_form(supabase, gym_id, pname):
    """Fields that make each message specific. Returns (details, problem)."""
    d = {}
    if pname == "Class invite":
        now = datetime.now(APP_TZ).replace(tzinfo=None)
        opts = {c["id"]: c for c in load_classes(supabase, gym_id) if c["_start"] > now}
        pick = st.selectbox(
            "Class", ["__other__"] + list(opts), key="pd_class",
            format_func=lambda k: "Another class (type it below)" if k == "__other__"
            else f'{opts[k]["name"]} · {class_when(opts[k]["_start"])}')
        if pick != "__other__":
            d["title"] = opts[pick]["name"]
            d["when"] = class_when_long(opts[pick]["_start"])
        else:
            d["title"] = st.text_input("Class name", key="pd_title",
                                       placeholder="e.g. Saturday Morning Yoga").strip()
            d["when"] = st.text_input("Date and time", key="pd_when",
                                      placeholder="e.g. Saturday 8 Nov, 9:00 am").strip()
        d["where"] = st.text_input("Where (optional)", key="pd_where",
                                   placeholder="e.g. Studio 2").strip()
        if not d["title"] or not d["when"]:
            return d, "Add the class name and when it happens."
    elif pname == "Group challenge":
        d["title"] = st.text_input("Challenge name", key="pd_title",
                                   placeholder="e.g. Marathon Race 5K, 30-Day Plank Challenge").strip()
        d["when"] = st.text_input("When does it start?", key="pd_when",
                                  placeholder="e.g. Monday 10 Nov, 6:00 am").strip()
        d["where"] = st.text_input("Where (optional)", key="pd_where").strip()
        d["reward"] = st.text_input("Prize or reward (optional)", key="pd_reward",
                                    placeholder="e.g. a free month for the winner").strip()
        if not d["title"]:
            return d, "Add the challenge name so members know what they are joining."
    elif pname == "Bring-a-friend invite":
        d["reward"] = st.text_input(
            "Reward for bringing a friend", key="pd_reward",
            placeholder="e.g. get one free week added to your membership").strip()
        d["when"] = st.text_input("Day or period (optional)", key="pd_when",
                                  placeholder="e.g. this weekend").strip()
        if not d["reward"]:
            return d, "Add a reward. Members invite more friends when there is something in it for them."
    elif pname == "Renewal offer":
        d["offer"] = st.text_input(
            "The offer", key="pd_offer",
            placeholder="e.g. get 10% off a 3-month plan").strip()
        deadline = st.date_input("Offer closes on", value=date.today() + timedelta(days=5),
                                 key="pd_deadline")
        d["deadline"] = f"{deadline:%A %d %B}"
        if not d["offer"]:
            return d, "Add the offer so the message gives members a reason to act now."
    return d, None


def _pillars_panel(supabase, gym_id, roster, actions):
    st.markdown('<div class="section-label">RETENTION PILLARS</div>', unsafe_allow_html=True)
    st.caption("Members stay when they feel part of something, know their trainer "
               "and feel looked after. Tap any play to start it.")
    cols = st.columns(len(PILLARS))
    for col, (name, info) in zip(cols, PILLARS.items()):
        own = actions[actions["action_type"].isin(info["plays"])] if not actions.empty else actions
        done_n = int((own["status"] == "Done").sum()) if len(own) else 0
        open_n = len(own) - done_n
        _md(f'<div class="pillar" style="--tone:{TONES[info["tone"]]}">'
            f'<div class="pillar-ic">{ic(info["icon"], 24)}</div><h4>{_esc(name)}</h4>'
            f'<p>{_esc(info["blurb"])}</p>'
            f'<div class="pn">{done_n} done · {open_n} open</div></div>', col)
        for p in info["plays"]:
            col.button(p, key=f"pp_{p}", on_click=_pick_play, args=(name, p),
                       use_container_width=True)
    with st.expander("Start a play for a member",
                     expanded=st.session_state.get("play_open", False)):
        names = roster.set_index("id")["full_name"].to_dict()
        ids = list(names)
        c1, c2 = st.columns(2)
        who = c1.selectbox("Member", ids, format_func=lambda i: names[i], key="play_member")
        plays = [(pn, p) for pn, info in PILLARS.items() for p in info["plays"]]
        play = c2.selectbox("Play", plays, format_func=lambda t: f"{t[0]} · {t[1]}",
                            key="play_type")
        trainer_id = None
        if play[1] in TRAINER_PLAYS:
            trainers = load_trainers(supabase, gym_id)
            if trainers:
                tmap = {t["id"]: t for t in trainers}
                trainer_id = st.selectbox(
                    "Trainer", list(tmap), key="play_trainer",
                    format_func=lambda i: f'{tmap[i]["full_name"]} · {_text(tmap[i].get("specialty"), "Trainer")}')
                _md(trainer_card_html(tmap[trainer_id]))
            else:
                st.info("Add your trainers in Settings → Trainers to introduce them to members.")
        details, problem = _play_details_form(supabase, gym_id, play[1])
        if st.button("Add to the board", key="play_add", type="primary"):
            if problem:
                st.error(problem)
            else:
                row = roster[roster["id"] == who].iloc[0]
                _create_action(supabase, gym_id, who, play[1],
                               int(row["renewal_due_days"]), trainer_id=trainer_id,
                               details=details or None)
                st.session_state.pop("play_open", None)
                st.session_state.setdefault(
                    "ac_flash", f"{play[1]} added for {names[who]}. "
                                "Open its card on the board and tap Do this play.")
                st.rerun()

def render_action_centre(supabase, gym_id, assess_fn):
    page_header("Retention Action Centre",
                "Turn risk into follow-ups, track them, and learn what works.",
                "Keep your members")
    flash = st.session_state.pop("ac_flash", None)
    if flash:
        st.success(flash)

    archived = purge_old_done_actions(supabase, gym_id)
    if archived:
        st.toast(f"{archived} completed positive follow-up(s) left the Done column")

    try:
        roster, _ = load_roster(supabase, gym_id, assess_fn)
        actions_all = load_actions(supabase, gym_id, include_archived=True)
    except Exception as e:
        st.error("Couldn't load actions. Have you run schema.sql?")
        with st.expander("Technical details"):
            st.code(str(e))
        return
    if roster.empty:
        st.info("Score your members in the Risk Radar first.")
        return
    names = roster.set_index("id")["full_name"].to_dict()
    photos = roster.set_index("id")["photo"].to_dict() if "photo" in roster.columns else {}
    k = kpis(roster, actions_all)
    st.session_state["_play_ctx"] = {
        "contacts": {r["id"]: member_message_ctx(r) for _, r in roster.iterrows()},
        "trainers": {t["id"]: t for t in load_trainers(supabase, gym_id)},
        "classes": load_classes(supabase, gym_id),
    }

    overdue = 0
    if not actions_all.empty:
        for _, a in actions_all[actions_all["status"] != "Done"].iterrows():
            try:
                if date.fromisoformat(str(a.get("due_date"))[:10]) < date.today():
                    overdue += 1
            except ValueError:
                pass
    kpi_row([
        ("Open actions", k["open_actions"], "cyan", "Still to finish"),
        ("Overdue", overdue, "red" if overdue else "lime", "Past their due date"),
        ("Members saved", k["saves"], "lime", "Retained after an action"),
        ("Save rate", "n/a" if k["save_rate"] is None else f"{k['save_rate']:.0%}",
         "white", "Retained vs cancelled"),
    ])

    visible_actions = _visible_actions(actions_all)
    total = len(visible_actions)
    done_n = int((visible_actions["status"] == "Done").sum()) if total else 0
    pct = (done_n / total) if total else 0
    _md(f"""
    <div class="board-progress">
      <div class="bp-top"><span>Board progress</span><b>{pct:.0%}</b></div>
      <div class="pbar"><span style="width:{pct * 100:.0f}%;--tone:#B7F34A"></span></div>
      <div class="bp-sub">{done_n} of {total} visible actions completed · {overdue} overdue</div>
    </div>
    """)

    todo = members_to_contact(roster, actions_all)
    st.markdown('<div class="section-label">SUGGESTED TODAY</div>', unsafe_allow_html=True)
    if todo.empty:
        st.success("Everyone who needs a follow-up has one in progress or was "
                   f"contacted in the last {SUGGEST_COOLDOWN_DAYS} days.")
    else:
        top = todo.head(5)
        if _mobile():
            for _, r in top.iterrows():
                mobile_member_card(
                    r, "sug", why=story_text(r),
                    chips=risk_chip(r["risk_category"], r["cancellation_probability"])
                          + chip(r["suggested_action"], "cyan"),
                    actions=[
                        ("Open profile", "mopen_sug", open_profile, (r["id"], "Action Centre")),
                        ("Start play", "madd_sug", _create_action,
                         (supabase, gym_id, r["id"], r["suggested_action"], r["renewal_due_days"],
                          story_text(r))),
                    ])
        else:
            with st.container(border=True, key="card_suggested"):
                for _, r in top.iterrows():
                    c = st.columns([0.6, 3.2, 1.6, 1.2], vertical_alignment="center")
                    _md(avatar_html(r["full_name"], r.get("photo"), 42, "row-tight"), c[0])
                    c[1].button(str(r["full_name"]), key=f"mrow_sug_{r['id']}",
                                on_click=open_profile, args=(r["id"], "Action Centre"),
                                use_container_width=True)
                    _md(story_html(r), c[1])
                    _md(risk_chip(r["risk_category"], r["cancellation_probability"])
                        + chip(r["suggested_action"], "cyan"), c[2])
                    if c[3].button("Start play", key=f"add_{r['id']}", type="primary",
                                   use_container_width=True):
                        _create_action(supabase, gym_id, r["id"], r["suggested_action"],
                                       r["renewal_due_days"], note=story_text(r))
                        st.rerun()
        if len(todo) > 1 and st.button("Start plays for all top 5", use_container_width=True):
            for _, r in top.iterrows():
                _create_action(supabase, gym_id, r["id"], r["suggested_action"],
                               r["renewal_due_days"], note=story_text(r))
            st.rerun()

    _pillars_panel(supabase, gym_id, roster, actions_all)

    import gympulse_automation as ga  # local import: gympulse_automation imports this module
    made = ga.run_automations(supabase, gym_id, roster, actions_all)
    if made:
        st.session_state["ac_flash"] = f"Your automation rules added {_plural(made, 'play')} to the board."
        st.rerun()
    ga.render_workload(visible_actions)

    st.markdown('<div class="section-label">YOUR BOARD</div>', unsafe_allow_html=True)
    if visible_actions.empty:
        st.info("No actions yet. Add one from the suggestions above.")
        return
    staff = ga.staff_list()
    v1, v2 = st.columns([1, 1.4])
    with v1:
        mode = st.radio("Board view", ["Board", "List"], horizontal=True,
                        key="ac_view", label_visibility="collapsed")
    if staff:
        who = v2.selectbox("Show plays for", ["Everyone"] + staff + ["Unassigned"],
                           key="ac_staff", label_visibility="collapsed")
        if who != "Everyone":
            want = "" if who == "Unassigned" else who
            visible_actions = visible_actions[[ga.assigned_to(a) == want
                                               for a in visible_actions.to_dict("records")]]
    if mode == "Board":
        _kanban(supabase, visible_actions, names, photos)
    else:
        _list_board(supabase, visible_actions, names, photos)

# ------------------------------------------------------ payments
def render_payments(supabase, gym_id, assess_fn):
    page_header(
        "Payments & Renewals",
        "What you are owed, what just renewed, and who is lapsing.",
        "Revenue"
    )
    flash = st.session_state.pop("pay_flash", None)
    if flash:
        st.success(flash)

    try:
        roster, _ = load_roster(supabase, gym_id, assess_fn)
    except Exception as e:
        st.error("Couldn't load payments. Have you run schema.sql?")
        with st.expander("Technical details"):
            st.code(str(e))
        return
    if roster.empty:
        st.info("Add members and activity data first.")
        return

    if "last_payment" not in roster.columns:
        roster["last_payment"] = None
    if "membership_end" not in roster.columns:
        roster["membership_end"] = None
    if "monthly_fee" not in roster.columns:
        roster["monthly_fee"] = 0.0

    today = date.today()
    end = pd.to_datetime(roster["membership_end"], errors="coerce")
    roster = roster.assign(
        _end=end.dt.date,
        _days_left=(end.dt.normalize() - pd.Timestamp(today)).dt.days,
    )

    active = roster[roster["_days_left"].fillna(-1) >= 0]
    lapsed = roster[roster["_days_left"].fillna(-1) < 0]
    renewing = active[active["_days_left"] <= 30]
    collected_total = pd.to_numeric(
        roster["last_payment"], errors="coerce").fillna(0).sum()

    kpi_row([
        ("Monthly run-rate", f"{active['monthly_fee'].sum():,.0f}", "cyan", "Active plans"),
        ("Renewing ≤30 days", len(renewing), "amber", "Time to reach out"),
        ("Lapsed", len(lapsed), "red", "Membership ended"),
        ("Last payment (total)", f"{collected_total:,.0f}", "lime",
         "Recorded on profiles"),
    ])

    st.markdown('<div class="section-label">RENEWAL PIPELINE</div>',
                unsafe_allow_html=True)
    buckets = [
        ("Overdue", lapsed, "red"),
        ("≤ 7 days", active[active["_days_left"].between(0, 7)], "amber"),
        ("8–30 days", active[active["_days_left"].between(8, 30)], "cyan"),
        ("31–90 days", active[active["_days_left"].between(31, 90)], "lime"),
        ("90+ days", active[active["_days_left"] > 90], "grey"),
    ]
    cols = st.columns(len(buckets))
    for col, (label, sub, tone) in zip(cols, buckets):
        with col:
            _md(kpi_card(label, len(sub), tone,
                         f"{sub['monthly_fee'].sum():,.0f} / mo"))

    import gympulse_revenue as gr  # local import: gympulse_revenue imports this module
    gr.render_record_payment(supabase, gym_id, roster)
    gr.render_recent_payments(supabase, gym_id, roster)

    render_renewal_reminders(supabase, gym_id, roster)

    st.markdown('<div class="section-label">WHO TO COLLECT FROM</div>',
                unsafe_allow_html=True)
    focus = pd.concat([lapsed, renewing]).drop_duplicates(subset="id")
    focus = focus.sort_values(["risk_category", "_days_left"])
    if focus.empty:
        st.success("No payments need chasing right now.")
        return

    for _, r in focus.head(20).iterrows():
        with st.container(border=True, key=f"card_pay_{r['id']}"):
            c = st.columns([0.6, 3.2, 1.4, 1.4, 1.6],
                           vertical_alignment="center")
            _md(avatar_html(r["full_name"], r.get("photo"), 40,
                            "row-tight"), c[0])
            c[1].button(str(r["full_name"]), key=f"mrow_pay_{r['id']}",
                        on_click=open_profile,
                        args=(r["id"], "Payments & Renewals"),
                        use_container_width=True)

            if pd.isna(r["_end"]):
                end_txt = "—"
            else:
                end_txt = r["_end"].strftime("%d %b %Y")

            days = r["_days_left"]
            days_txt = "—" if pd.isna(days) else f"{int(days):+d} days"

            _md(f'<div class="why">Renews {_esc(end_txt)} · {_esc(days_txt)}</div>',
                c[1])
            _md(f'<div class="money">{r["monthly_fee"]:,.0f} / mo</div>', c[2])
            _md(membership_chip(membership_state(r["membership_end"])), c[3])
            c[4].button("Message", key=f"pay_fu_{r['id']}",
                        on_click=open_followup,
                        args=(r["id"], "Payments & Renewals"),
                        use_container_width=True)

    st.caption("Record renewals above or from a member's profile → Membership tab. "
               "Each one updates the member's plan and, when it follows a retention play, "
               "credits that play.")

# ------------------------------------------------------- insights
def _insights_charts(roster):
    mix = (roster["risk_category"].value_counts()
           .reindex(["High", "Medium", "Low"]).fillna(0).astype(int))
    by_plan = roster.groupby("membership_type")["revenue_at_risk"].sum()
    left, right = st.columns(2)
    try:
        import altair as alt
        with left:
            st.markdown('<div class="section-label">RISK MIX</div>', unsafe_allow_html=True)
            mix_df = pd.DataFrame({"Risk": mix.index, "Members": mix.values})
            chart = (alt.Chart(mix_df).mark_bar(cornerRadiusTopLeft=8, cornerRadiusTopRight=8)
                     .encode(x=alt.X("Risk:N", sort=["High", "Medium", "Low"],
                                     axis=alt.Axis(labelAngle=0), title=None),
                             y=alt.Y("Members:Q", axis=alt.Axis(tickMinStep=1, format="d")),
                             color=alt.Color("Risk:N", legend=None, scale=alt.Scale(
                                 domain=["High", "Medium", "Low"],
                                 range=["#FF6B6B", "#FFC44D", "#B7F34A"])),
                             tooltip=["Risk", "Members"])
                     .properties(height=260))
            _show_chart(_style_chart(chart))
        with right:
            st.markdown('<div class="section-label">REVENUE AT RISK BY PLAN</div>',
                        unsafe_allow_html=True)
            plan_df = pd.DataFrame({"Plan": by_plan.index,
                                    "Revenue at risk": by_plan.values.round(0)})
            chart = (alt.Chart(plan_df).mark_bar(cornerRadiusTopLeft=8, cornerRadiusTopRight=8,
                                                 color="#B7F34A")
                     .encode(x=alt.X("Plan:N", axis=alt.Axis(labelAngle=0), title=None),
                             y=alt.Y("Revenue at risk:Q", axis=alt.Axis(format=",.0f")),
                             tooltip=["Plan", alt.Tooltip("Revenue at risk:Q", format=",.0f")])
                     .properties(height=260))
            _show_chart(_style_chart(chart))
    except Exception:
        with left:
            st.markdown('<div class="section-label">RISK MIX</div>', unsafe_allow_html=True)
            st.bar_chart(mix)
        with right:
            st.markdown('<div class="section-label">REVENUE AT RISK BY PLAN</div>',
                        unsafe_allow_html=True)
            st.bar_chart(by_plan)


def render_business_insights(supabase, gym_id, assess_fn, header=True):
    if header:
        page_header("Business Insights",
                    "What retention is worth, where it leaks, and what's working.",
                    "Numbers that matter")
    _flash = st.session_state.pop("ins_flash", None)
    if _flash:
        st.success(_flash)
    try:
        roster, _ = load_roster(supabase, gym_id, assess_fn)
        actions = load_actions(supabase, gym_id, include_archived=True)
    except Exception as e:
        st.error("Couldn't load insights. Have you run schema.sql?")
        with st.expander("Technical details"):
            st.code(str(e))
        return
    if roster.empty:
        st.info("Score your members in the Risk Radar first.")
        return
    k = kpis(roster, actions)
    kpi_row([
        ("Monthly revenue", _money(k["monthly_revenue"]), "cyan", "From scored members"),
        ("Expected monthly loss", _money(k["expected_loss"]), "red", "Estimate × monthly fee"),
        ("Held by high-risk", _money(k["high_risk_revenue"]), "amber", "Fees at stake"),
        ("Revenue saved", _money(k["revenue_saved"]), "lime", "From retained members"),
    ])
    st.caption("Expected loss = each member's estimate × their monthly fee. "
               "It is a planning figure from a synthetic-data model, not a forecast.")

    import gympulse_revenue as gr  # local import: gympulse_revenue imports this module
    import gympulse_pilot as gp  # local import: gympulse_pilot imports this module
    gr.render_revenue_outcomes(supabase, gym_id, roster)
    gp.render_operations(roster, actions)

    try:
        import gympulse_retention as gret  # local import: it imports this module
        gret.render_insights(supabase, gym_id)
    except Exception:
        pass
    _insights_charts(roster)

    st.markdown('<div class="section-label">RENEWAL PIPELINE</div>', unsafe_allow_html=True)
    labels = ["≤7d", "8-14d", "15-30d", "31-60d", "60d+"]
    bins = pd.cut(roster["renewal_due_days"], [-1, 7, 14, 30, 60, 10_000], labels=labels)
    pipe = roster.groupby(bins, observed=False).agg(
        members=("id", "count"), avg_risk=("cancellation_probability", "mean"),
        fees=("monthly_fee", "sum"))
    cols = st.columns(len(labels))
    for col, label in zip(cols, labels):
        row = pipe.loc[label]
        avg = 0.0 if pd.isna(row["avg_risk"]) else float(row["avg_risk"])
        tone = "red" if avg >= 0.5 else "amber" if avg >= 0.3 else "lime"
        _md(kpi_card(f"Renews {label}", int(row["members"]), tone,
                     f"{avg:.0%} avg risk · {row['fees']:,.0f}"), col)

    st.markdown('<div class="section-label">WHAT WORKS</div>', unsafe_allow_html=True)
    done = actions[actions["status"] == "Done"] if not actions.empty else actions
    if done.empty:
        st.info("Complete some actions with outcomes and this will show which "
                "tactics keep members.")
    else:
        rows = []
        for at, grp in done.groupby("action_type"):
            out = grp["outcome"].fillna("").astype(str)
            kept = int((out == "Retained").sum())
            lost = int((out == "Cancelled").sum())
            decided = kept + lost
            rows.append({
                "action": at, "done": len(grp), "retained": kept,
                "cancelled": lost, "open": len(grp) - decided,
                "rate": f"{kept / decided:.0%}" if decided else "n/a"})
        rows.sort(key=lambda r: r["done"], reverse=True)
        data_card(rows, [
            ("action", "Action"), ("done", "Completed"),
            ("retained", "Retained"), ("cancelled", "Cancelled"),
            ("open", "No response"), ("rate", "Save rate"),
        ], key_prefix="what_works", tone="lime")
        st.caption("Save rate = Retained ÷ (Retained + Cancelled). "
                   "No-response results are shown but not counted either way, "
                   "because the real outcome is unknown.")
        if len(done) < 20:
            st.caption("Small sample, so treat these as early signals only. "
                       "This table counts every completed action, including "
                       "cards that have since been archived from the board.")

    st.markdown('<div class="section-label">TO DO THIS WEEK</div>', unsafe_allow_html=True)
    need = members_to_contact(roster, actions)
    high = need[need["risk_category"] == "High"]
    if not high.empty:
        high = high.assign(_soon=high["renewal_due_days"] <= 30).sort_values(
            ["_soon", "cancellation_probability"], ascending=False)
        soon = int(high["_soon"].sum())
        line = f"Contact {'this high-risk member' if len(high) == 1 else 'these high-risk members'}"
        st.write(line + (f" ({soon} renewing within 30 days). Tap a name to open "
                         "their profile:" if soon else ". Tap a name to open their profile:"))
        if _mobile():
            for _, r in high.head(6).iterrows():
                mobile_member_card(
                    r, "todo",
                    chips=risk_chip(r["risk_category"], r["cancellation_probability"]),
                    actions=[("Open profile", "mopen_todo", open_profile,
                              (r["id"], "Business Insights"))])
        else:
            with st.container(border=True, key="card_todo_week"):
                for _, r in high.head(6).iterrows():
                    c = st.columns([0.6, 4, 1.6], vertical_alignment="center")
                    _md(avatar_html(r["full_name"], r.get("photo"), 40, "row-tight"), c[0])
                    c[1].button(str(r["full_name"]), key=f"mrow_todo_{r['id']}",
                                on_click=open_profile, args=(r["id"], "Business Insights"),
                                use_container_width=True)
                    _md(risk_chip(r["risk_category"], r["cancellation_probability"]), c[2])
        if len(high) > 6:
            st.caption(f"+{len(high) - 6} more in the Action Centre.")
    if k["open_actions"]:
        st.write(f"Close out **{k['open_actions']}** open action(s) and record the outcomes.")
        st.button("Open Action Centre", key="todo_open_ac", on_click=_go,
                  args=("Action Centre",))
    if high.empty and not k["open_actions"]:
        st.write("Nothing urgent. Run a goal review with a few Low-risk members.")

    import gympulse_automation as ga  # local import: gympulse_automation imports this module
    biz = _text((st.session_state.get("user_profile") or {}).get("business_name"), "Your gym")
    ga.render_report_section(supabase, gym_id, roster, actions, biz)
    gp.render_pilot(supabase, gym_id, roster, actions,
                    lambda settings, msg: gp.save_profile_settings(supabase, settings, msg))
    gp.render_export(supabase, gym_id, roster, actions)

# ------------------------------------------------------------ Archie
ARCHIE_PROMPTS = [
    "What should my staff prioritise today?",
    "Which renewals are at risk this month?",
    "Which retention plays are working?",
    "How much revenue did we retain this month?",
    "Why are members becoming inactive?",
    "Write a WhatsApp message for my top priority member",
]

ARCHIE_BOT_SVG = """
<svg class="archie-bot" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg">
  <circle class="bot-halo" cx="100" cy="100" r="94" fill="#35D6ED"/>
  <circle cx="100" cy="100" r="76" fill="#B7F34A"/>
  <circle cx="116" cy="124" r="62" fill="#27B35C" opacity=".28"/>
  <ellipse cx="74" cy="56" rx="30" ry="15" fill="#fff" opacity=".38" transform="rotate(-28 74 56)"/>
  <rect x="48" y="78" width="104" height="62" rx="31" fill="#0B1020"/>
  <g class="bot-eye"><ellipse cx="80" cy="106" rx="9" ry="14" fill="#B7F34A"/>
    <circle cx="83" cy="101" r="3.4" fill="#fff"/></g>
  <g class="bot-eye bot-eye2"><ellipse cx="120" cy="106" rx="9" ry="14" fill="#B7F34A"/>
    <circle cx="123" cy="101" r="3.4" fill="#fff"/></g>
  <path class="bot-mouth" d="M90 122 Q100 131 110 122" fill="none" stroke="#35D6ED" stroke-width="4" stroke-linecap="round"/>
  <circle class="bot-ball" cx="152" cy="52" r="9" fill="#35D6ED"/>
</svg>
"""

def _archie_hero(thinking=False):
    state = "thinking" if thinking else ""
    on = "thinking-on" if thinking else ""
    status = "Thinking…" if thinking else "Online · reading your live data"
    return f"""
    <div class="archie-hero {on}">
      <div class="archie-orb {state}">{ARCHIE_BOT_SVG}</div>
      <div class="archie-meta">
        <div class="archie-name">Archie</div>
        <div class="archie-role">Your retention analyst. Ask who needs you, why members are drifting, which plays work and what revenue you kept. Every answer shows the figures behind it.</div>
        <div class="archie-status"><span class="dot"></span>{status}
          <span class="archie-wave"><i></i><i></i><i></i><i></i><i></i></span></div>
      </div>
    </div>
    """

ARCHIE_ORB_AVATAR = "data:image/svg+xml;base64," + base64.b64encode("""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<defs><radialGradient id="g" cx="35%" cy="30%" r="75%">
<stop offset="0" stop-color="#F4FFD6"/><stop offset=".35" stop-color="#B7F34A"/>
<stop offset="1" stop-color="#1E9E55"/></radialGradient></defs>
<g><animateTransform attributeName="transform" type="translate"
values="0 1.5;0 -1.5;0 1.5" dur="3.2s" repeatCount="indefinite"/>
<circle cx="32" cy="32" r="26" fill="#35D6ED" opacity=".25"/>
<circle cx="32" cy="32" r="23" fill="url(#g)"/>
<rect x="17" y="25" width="30" height="17" rx="8.5" fill="#0B1020"/>
<ellipse cx="26" cy="33" rx="3" ry="4.4" fill="#B7F34A"/>
<ellipse cx="38" cy="33" rx="3" ry="4.4" fill="#B7F34A"/>
<path d="M29 39 Q32 41.5 35 39" stroke="#35D6ED" stroke-width="1.6" fill="none" stroke-linecap="round"/>
<circle cx="47" cy="17" r="3.2" fill="#35D6ED"/></g></svg>
""".strip().encode()).decode()


def _user_avatar(name):
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        '<defs><linearGradient id="u" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#B7F34A"/><stop offset="1" stop-color="#35D6ED"/>'
        '</linearGradient></defs><circle cx="32" cy="32" r="30" fill="url(#u)"/>'
        '<text x="32" y="32" text-anchor="middle" dominant-baseline="central" '
        'font-family="Inter,Arial,sans-serif" font-weight="800" font-size="24" '
        f'fill="#10182A">{_esc(initials(name))}</text></svg>'
    )
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


@contextmanager
def _chat_message(role):
    owner = st.session_state.get("_chat_owner") or "You"
    biz = st.session_state.get("_chat_biz") or ""
    if role == "assistant":
        try:
            box = st.chat_message("assistant", avatar=ARCHIE_ORB_AVATAR)
        except Exception:
            box = st.chat_message("assistant", avatar=":material/smart_toy:")
        who = ('<div class="chat-who"><b>Archie</b>'
               '<span class="chat-tag">AI assistant</span></div>')
    else:
        try:
            box = st.chat_message("user", avatar=_user_avatar(owner))
        except Exception:
            box = st.chat_message("user", avatar=":material/person:")
        who = (f'<div class="chat-who chat-who-user"><b>{_esc(owner)}</b>'
               + (f'<span class="chat-tag chat-gym">{_esc(biz)}</span>' if biz else "")
               + "</div>")
    with box:
        _md(who)
        yield

def _stream(slot, text):
    words = text.split(" ")
    step = max(1, len(words) // 40)
    for i in range(step, len(words), step):
        slot.markdown(" ".join(words[:i]) + " ▍")
        time.sleep(0.03)
    slot.markdown(text)


def archie_context(roster, actions, business_name, supabase=None, gym_id=None):
    """Everything Archie may use, labelled as RECORDED or ESTIMATE."""
    import gympulse_command as gc  # local import: gympulse_command imports this module

    today = today_local()
    L = [f"Gym business: {business_name}",
         f"Today: {today:%A %d %B %Y}",
         "Data period: attendance from front-desk check-ins over the last 90 days "
         "(typed-in activity where a member has no check-ins); outcomes over the last 30 days.",
         "Money is per month, in the gym's own currency, with no symbol."]
    if roster.empty:
        L.append("No scored members yet.")
        return "\n".join(L)

    n = len(roster)
    L.append(f"\nMEMBERS (recorded): {n} active members tracked, "
             f"total monthly fees {roster['monthly_fee'].sum():,.0f}.")
    counts = roster["risk_category"].value_counts()
    L.append("Risk levels (ESTIMATE from an experimental model): "
             + ", ".join(f"{k} {int(counts.get(k, 0))}" for k in ("High", "Medium", "Low")))
    L.append(f"Expected monthly revenue at risk (ESTIMATE): {roster['revenue_at_risk'].sum():,.0f}. "
             f"Fees held by high-risk members: "
             f"{roster.loc[roster['risk_category'] == 'High', 'monthly_fee'].sum():,.0f}.")

    declining = roster[roster["attendance_change"] <= -3]
    away = roster[roster["days_since_last_visit"] >= 14]
    lapsed = roster[roster["renewal_due_days"] < 0]
    L.append(f"Attendance (recorded): {len(declining)} members visiting at least 3 times less than the "
             f"previous 30 days; {len(away)} not seen for 14+ days; {len(lapsed)} memberships already lapsed.")

    watch = gc.renewal_watch(roster)
    if len(watch):
        L.append(f"\nRENEWAL WATCH (renewing within 30 days and attending less or at risk): "
                 f"{len(watch)} members, fees {watch['monthly_fee'].sum():,.0f}/month")
        for _, r in watch.head(10).iterrows():
            L.append(f"- {r['full_name']}: renews in {int(r['renewal_due_days'])} days, "
                     f"{r['membership_type']} plan, fee {r['monthly_fee']:,.0f}, "
                     f"visits {int(r['visits_previous_30_days'])} -> {int(r['visits_last_30_days'])}, "
                     f"{r['risk_category']} risk")

    need = members_to_contact(roster, actions)
    if len(need):
        ranked = need.assign(_v=need["cancellation_probability"] * need["monthly_fee"]) \
                     .sort_values("_v", ascending=False)
        L.append(f"\nPRIORITY QUEUE ({len(need)} medium/high-risk members with no open play):")
        for _, r in ranked.head(12).iterrows():
            story = gc.risk_story(r)
            nxt = re.sub("<[^>]+>", "", story["next"])
            L.append(f"- {r['full_name']}: {r['risk_category']} risk ({r['cancellation_probability']:.0%} estimate), "
                     f"fee {r['monthly_fee']:,.0f}, goal {_text(r.get('fitness_goal'), 'not set')}. "
                     f"Why: {story['why']}. When: {story['when']}. Suggested next: {nxt}.")

    res = gc.outcomes(roster, actions)
    L.append(f"\nFOLLOW-UPS (recorded): {res['todo']} to do, {res['doing']} in progress, "
             f"{res['overdue']} overdue, {res['due_today']} due today, "
             f"{res.get('followup_due', 0)} contacted members waiting for their follow-up.")
    if not actions.empty:
        live = actions[actions["status"] != "Done"]
        if "archived_at" in live.columns:
            live = live[live["archived_at"].isna()]
        names_ = roster.set_index("id")["full_name"].to_dict()
        for r in live.head(15).to_dict("records"):
            info = PLAY_INFO.get(r.get("action_type"), {})
            line = _contact_line(r)
            L.append(f"- {names_.get(r['member_id'], 'a member')}: {r.get('action_type')} "
                     f"({action_stage(r)}; goal: {info.get('objective', 'n/a')})"
                     + (f"; {line}" if line else ""))
    if not actions.empty and res["overdue"]:
        names = roster.set_index("id")["full_name"].to_dict()
        open_a = actions[actions["status"] != "Done"].copy()
        open_a["_due"] = pd.to_datetime(open_a["due_date"], errors="coerce").dt.date
        for _, a in open_a[open_a["_due"] < date.today()].head(8).iterrows():
            L.append(f"- Overdue: {a['action_type']} for {names.get(a['member_id'], 'a member')}, "
                     f"due {a['_due']}, status {a['status']}")

    L.append(f"\nOUTCOMES, LAST 30 DAYS (RECORDED, verified): {res['retained_n']} members retained after a play "
             f"(monthly fees {res['retained_rev']:,.0f}); {res['cancelled_n']} cancelled; "
             f"{res['resolved_n']} plays closed; {res['reengaged_n']} members checked in again after a play. "
             f"Save rate: {'not enough data' if res['save_rate'] is None else format(res['save_rate'], '.0%')}.")
    try:
        import gympulse_revenue as gr
        if supabase is not None and gym_id:
            rev = gr.revenue_summary(supabase, gym_id, roster)
            if rev["source"] == "payments":
                L.append(f"PAYMENTS, LAST 30 DAYS (RECORDED): collected {rev['collected']:,.0f} from "
                         f"{rev['renewals_n']} renewal payments; {rev['credited_n']} renewals credited to a "
                         f"retention play worth {rev['retained_by_plays']:,.0f}; recovered from lapsed members "
                         f"{rev['recovered']:,.0f} ({rev['recovered_n']}). Credit means the play was involved, "
                         "not proof the member would have left without it.")
            if rev["renewal_rate"] is not None:
                L.append(f"Renewal rate, last 30 days (RECORDED): {rev['renewal_rate']:.0%} "
                         f"({rev['renewed']} renewed, {rev['lapsed']} lapsed).")
    except Exception:
        pass
    perf = gc.play_performance(actions)
    if perf:
        L.append("Play results, all time (kept / decided, 'No response' excluded): "
                 + "; ".join(f"{p['play']} {p['kept']}/{p['decided']}" for p in perf[:8]))

    if supabase is not None and gym_id:
        try:
            trainers = load_trainers(supabase, gym_id)
            if trainers:
                L.append("\nTrainers: " + ", ".join(
                    f"{_text(t.get('name'))} ({_text(t.get('specialty'), 'general')})" for t in trainers[:8]))
        except Exception:
            pass
        try:
            cls = load_classes(supabase, gym_id)
            if cls is not None and len(cls):
                rows = cls.to_dict("records") if hasattr(cls, "to_dict") else list(cls)
                L.append("Upcoming classes: " + "; ".join(
                    f"{_text(c.get('name'))} {str(c.get('starts_at', ''))[:16].replace('T', ' ')}"
                    for c in rows[:6]))
        except Exception:
            pass
    try:
        import gympulse_automation as ga
        staff = ga.staff_list()
        if staff and not actions.empty:
            L.append("Team workload (RECORDED, open plays): " + "; ".join(
                f"{w['who']} {w['open']} open, {w['overdue']} overdue" for w in ga.workload(actions, staff)))
        cfg = ga.automation_settings()
        on = [ga.TRIGGERS[r["trigger"]]["label"] + " -> "
              + ("suggested play" if r["play"] == ga.SUGGESTED else r["play"])
              for r in cfg["rules"] if r.get("enabled") and r["trigger"] in ga.TRIGGERS]
        L.append("Automation: " + (("on. Rules: " + "; ".join(on)) if cfg["enabled"] and on else "off")
                 + ". Automation only creates plays; it never sends messages.")
    except Exception:
        pass
    L.append("Retention plays the gym uses: " + ", ".join(ACTION_TYPES))
    return "\n".join(L)


ARCHIE_SYSTEM = (
    "You are Archie, the retention analyst inside GymPulse AI. You help a gym owner keep members "
    "and protect membership revenue. Be warm, direct and practical.\n"
    "Rules:\n"
    "1. Use only the GYM DATA below. If the answer is not in it, say what is missing and how to get it "
    "(for example: record outcomes in the Action Centre, check members in at the front desk).\n"
    "2. Always give the figures behind an answer and the data period they cover.\n"
    "3. Keep RECORDED facts (check-ins, renewals, outcomes) separate from ESTIMATES (risk scores, "
    "revenue at risk). Call estimates estimates. Never present an estimate as a result.\n"
    "4. Never invent members, numbers, results, discounts, prices or deadlines. Only mention an offer "
    "if the owner gives you its terms.\n"
    "5. When recommending, name who, why, and the next step (which play, which channel, when), "
    "ordered by urgency and monthly fee.\n"
    "6. A message sent is not a member saved. Only count members as retained when the data records it.\n"
    "7. When asked for a WhatsApp or email message, write it ready to send: short, friendly, personal "
    "(use their goal or habits), with no invented offer, signed with the owner's name.\n"
    "Format: short paragraphs or bullets, member names in bold, no tables unless asked. "
    "End data answers with one short line in italics starting 'Based on'."
)


def archie_reply(messages, context):
    """Ask Claude for Archie's answer. Returns (text, used_live_ai). Counts towards the gym's monthly Archie
    questions (plan limit, gympulse_billing.archie_allowed)."""
    gid, sb = st.session_state.get("gym_id"), st.session_state.get("supabase_client")
    if gid and sb:
        import gympulse_billing as gbill
        ok, _used, _lim, why = gbill.archie_allowed(sb, gid)
        if not ok:
            return why, False
    text, live = _archie_reply(messages, context)
    if live and gid and sb:
        gbill.archie_count(sb, gid)
    return text, live


def _archie_reply(messages, context):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        try:
            key = st.secrets["ANTHROPIC_API_KEY"]
        except Exception:
            key = None
    if not key:
        return ("Archie can't find ANTHROPIC_API_KEY. Add it under "
                "Environment on Render, then redeploy."), False

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        history = [{"role": m["role"], "content": m["content"]}
                   for m in messages[-12:]]
        response = client.messages.create(
            model=ARCHIE_MODEL,
            max_tokens=900,
            system=ARCHIE_SYSTEM + "\n\nGYM DATA:\n" + context,
            messages=history,
        )
        text = "".join(
            block.text for block in response.content
            if getattr(block, "type", "") == "text"
        ).strip()
        if not text:
            return "Archie had no answer this time. Please try again.", False
        return text, True
    except Exception as error:
        return f"Archie could not answer right now.\n\nTechnical detail: {error}", False


def _member_photos(supabase, gym_id, ids):
    try:
        rows = (supabase.table("members").select("id, photo")
                .eq("gym_id", gym_id).in_("id", list(ids)).execute().data or [])
    except Exception:
        return {}
    return {r["id"]: r.get("photo") for r in rows}


def _mention_buttons(text, roster, tag, supabase=None, gym_id=None):
    """A pill button, with the member's photo or initials, for each name in Archie's reply."""
    if roster is None or roster.empty or "full_name" not in roster.columns:
        return
    lowered = str(text).lower()
    found, seen = [], set()
    people = sorted(roster[["id", "full_name"]].dropna().itertuples(index=False),
                    key=lambda p: len(str(p.full_name)), reverse=True)
    for p in people:
        name = str(p.full_name).strip()
        if len(name) >= 3 and name.lower() in lowered and p.id not in seen:
            seen.add(p.id)
            found.append((p.id, name))
    if not found:
        return
    found = found[:6]

    photos = {}
    if "photo" in roster.columns:
        photos = dict(zip(roster["id"], roster["photo"]))
    elif supabase is not None and gym_id:
        photos = _member_photos(supabase, gym_id, [i for i, _ in found])

    rules = []
    for member_id, name in found:
        pic = photos.get(member_id)
        src = pic if has_photo(pic) else _user_avatar(name)
        rules.append(
            f'[class*="st-key-mention_{tag}_{member_id}"] button::before {{'
            f'content:"";display:inline-block;width:26px;height:26px;'
            f'border-radius:50%;flex-shrink:0;margin-right:10px;'
            f'background:url("{src}") center/cover no-repeat;'
            f'border:2px solid rgba(183,243,74,0.6);box-sizing:border-box;}}'
        )
    st.markdown("<style>" + "".join(rules) + "</style>", unsafe_allow_html=True)

    st.caption("Tap a name to open their profile")
    for member_id, name in found:
        st.button(name, key=f"mention_{tag}_{member_id}",
                  on_click=open_profile, args=(member_id, "Archie"))


def render_archie(supabase, gym_id, assess_fn, business_name, owner_name="the gym owner"):
    st.session_state["_chat_owner"] = owner_name
    st.session_state["_chat_biz"] = business_name
    hero = st.empty()
    _md(_archie_hero(False), hero)
    try:
        roster, _ = load_roster(supabase, gym_id, assess_fn, with_photos=False)
        actions = load_actions(supabase, gym_id, include_archived=True)
    except Exception:
        roster, actions = pd.DataFrame(), pd.DataFrame()
    if len(roster):
        context = archie_context(roster, actions, business_name, supabase, gym_id)
    else:
        context = f"Gym: {business_name}. No scored members yet."
    context += f"\nThe owner's name is {owner_name}. Sign messages with this name."
    _p = st.session_state.get("user_profile") or {}
    _lang = (_p.get("settings") or {}).get("language") or _p.get("language") or "English"
    context += f"\nReply in {_lang}."

    if "archie_msgs" not in st.session_state:
        st.session_state.archie_msgs = []

    if len(roster) and not st.session_state.archie_msgs:
        import gympulse_command as gc  # local import: gympulse_command imports this module
        try:
            res = gc.outcomes(roster, actions)
            need = members_to_contact(roster, actions)
            bullets = "".join(f"<li>{b}</li>" for b in gc.daily_brief(
                roster, actions, res, gc.renewal_watch(roster), need))
            _md(f"""<div class="cc-brief" style="margin-top:8px"><div class="cc-brief-head">
                <div class="cc-brief-orb"></div><div><div class="cc-brief-title">Today's brief</div>
                <div class="cc-brief-sub">Ready before you ask · from your records, check-ins and outcomes</div>
                </div></div><ul>{bullets}</ul></div>""")
        except Exception:
            pass

    st.markdown('<div class="section-label">TRY ASKING</div>', unsafe_allow_html=True)
    picked = None
    per_row = 2 if _mobile() else 3
    for i in range(0, len(ARCHIE_PROMPTS), per_row):
        cols = st.columns(per_row)
        for col, p in zip(cols, ARCHIE_PROMPTS[i:i + per_row]):
            if col.button(p, key=f"ap_{p}", use_container_width=True):
                picked = p
    if not st.session_state.archie_msgs:
        hour = datetime.now(APP_TZ).hour
        hello = ("Good morning" if hour < 12
                 else "Good afternoon" if hour < 17 else "Good evening")
        with _chat_message("assistant"):
            st.markdown(
                f"{hello}, {owner_name}! Welcome to **{business_name}**. "
                "I'm Archie. Ask me who needs a call today, or tap a question above.")
    for i, m in enumerate(st.session_state.archie_msgs):
        with _chat_message(m["role"]):
            st.markdown(m["content"])
            if m["role"] == "assistant":
                _mention_buttons(m["content"], roster, f"h{i}", supabase, gym_id)
    try:
        import gympulse_billing as gbill
        _ok, _used, _lim, _why = gbill.archie_allowed(supabase, gym_id)
        if _lim:
            st.caption(f"{_used:,} of {_lim:,} Archie questions used this month.")
        if not _ok:
            st.info(_why)
    except Exception:
        pass
    typed = st.chat_input("Ask Archie...")
    question = typed or picked or st.session_state.pop("archie_pending", None)
    if question:
        st.session_state.archie_msgs.append({"role": "user", "content": question})
        with _chat_message("user"):
            st.markdown(question)
        _md(_archie_hero(True), hero)
        with _chat_message("assistant"):
            slot = st.empty()
            _md('<div class="think"><span class="think-label">Archie is thinking</span>'
                '<div class="skel"><i></i><i></i><i></i></div></div>', slot)
            reply, live = archie_reply(st.session_state.archie_msgs, context)
            _stream(slot, reply)
            _mention_buttons(reply, roster, f"n{len(st.session_state.archie_msgs)}",
                             supabase, gym_id)
        _md(_archie_hero(False), hero)
        st.session_state.archie_msgs.append({"role": "assistant", "content": reply})
    if st.session_state.archie_msgs and st.button("Clear chat", type="tertiary"):
        st.session_state.archie_msgs = []
        st.rerun()
    st.caption("Archie can be wrong. Check details before contacting members. "
               "To answer, member names, attendance, renewal and follow-up details from "
               "your workspace are shared with the AI service. Phone numbers and emails are not.")

# ------------------------------------------------------ front desk check-in
def _page_checkins(supabase, gym_id, since, cols):
    rows, start = [], 0
    while True:
        page = (supabase.table("checkins").select(cols)
                .eq("gym_id", gym_id).gte("checked_in_at", since)
                .order("checked_in_at", desc=True)
                .range(start, start + 999).execute().data or [])
        rows += page
        if len(page) < 1000 or len(rows) >= 20000:
            break
        start += 1000
    return rows


def _fetch_checkins(supabase, gym_id, days=90):
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = None
    for cols in ("id, member_id, checked_in_at, class_id, source",
                 "id, member_id, checked_in_at, class_id", "id, member_id, checked_in_at"):
        try:
            rows = _page_checkins(supabase, gym_id, since, cols)
            break
        except Exception:
            rows = None
    if rows is None:
        return None
    if not rows:
        return pd.DataFrame(columns=["id", "member_id", "at", "day", "class_id", "source"])
    df = pd.DataFrame(rows)
    at = (pd.to_datetime(df["checked_in_at"], errors="coerce", utc=True, format="ISO8601")
          .dt.tz_convert(APP_TZ).dt.tz_localize(None))
    out = pd.DataFrame({"id": df["id"], "member_id": df["member_id"], "at": at,
                        "class_id": df["class_id"] if "class_id" in df.columns else None,
                        "source": (df["source"].fillna("unknown") if "source" in df.columns
                                   else "unknown")})
    out = out.dropna(subset=["at"])
    out["day"] = out["at"].dt.normalize()
    return out


def load_checkins(supabase, gym_id):
    return _cached(("checkins", gym_id), lambda: _fetch_checkins(supabase, gym_id), ttl=30)


def _fetch_classes(supabase, gym_id):
    try:
        rows = (supabase.table("classes").select("*").eq("gym_id", gym_id)
                .order("starts_at").execute().data or [])
    except Exception:
        return []
    out = []
    for r in rows:
        t = pd.to_datetime(r.get("starts_at"), errors="coerce", utc=True)
        if pd.isna(t):
            continue
        r["_start"] = t.tz_convert(APP_TZ).tz_localize(None).to_pydatetime()
        out.append(r)
    return out


def load_classes(supabase, gym_id):
    return _cached(("classes", gym_id), lambda: _fetch_classes(supabase, gym_id))


def checkin_stats(ck):
    """Per member, from real check-ins: days since last visit, recent pace (last 14 days,
    scaled to 30), their own earlier baseline pace, and their usual gap between visits."""
    if ck is None or ck.empty:
        return pd.DataFrame()
    today = pd.Timestamp(today_local())
    d = ck.drop_duplicates(["member_id", "day"]).copy()
    d["age"] = (today - d["day"]).dt.days.clip(lower=0)
    rows = []
    for mid, g in d.groupby("member_id"):
        ages = g["age"]
        base_n = int(((ages >= 14) & (ages < 60)).sum())
        gaps = g["day"].sort_values().diff().dropna().dt.days
        rows.append({
            "member_id": mid,
            "ck_days": int(ages.min()),
            "ck_recent": min(20, round(int((ages < 14).sum()) * 30 / 14)),
            "ck_base": min(20, round(base_n * 30 / 46)) if base_n >= 3 else None,
            "usual_gap_days": float(gaps.median()) if len(g) >= 4 and len(gaps) else None,
        })
    return pd.DataFrame(rows)


def checkin_signature(supabase, gym_id):
    """Cheap marker of the newest check-in, used to refresh scores when someone checks in."""
    try:
        r = (supabase.table("checkins").select("id").eq("gym_id", gym_id)
             .order("checked_in_at", desc=True).limit(1).execute().data or [])
        return str(r[0]["id"]) if r else "none"
    except Exception:
        return None


def bump_data_version():
    st.session_state["_dv"] = st.session_state.get("_dv", 0) + 1


def absence_alerts(ck):
    """Members whose visit rhythm has changed."""
    if ck is None or ck.empty:
        return []
    today = pd.Timestamp(today_local())
    d = ck.drop_duplicates(["member_id", "day"]).copy()
    d["age"] = (today - d["day"]).dt.days
    d = d[(d["age"] >= 0) & (d["age"] < 56)]
    out = []
    for mid, g in d.groupby("member_id"):
        if len(g) < 4:
            continue
        gaps = g["day"].sort_values().diff().dropna().dt.days
        typical = float(gaps.median())
        n = max(1, round(typical))
        last_age = int(g["age"].min())
        counts = g["day"].dt.weekday.value_counts()
        usual = set(counts[counts >= 3].index)
        if last_age > max(typical * 2, typical + 3) and last_age >= 3:
            out.append({"id": mid, "kind": "pattern", "last": last_age,
                        "reason": f"Usually visits every {n} day{'s' if n != 1 else ''}, "
                                  f"but hasn't been in for {last_age} days"})
        elif today.weekday() in usual and last_age > 0:
            out.append({"id": mid, "kind": "expected", "last": last_age,
                        "reason": f"Usually trains on {today:%A}s and isn't in yet today"})
    out.sort(key=lambda a: (a["kind"] != "pattern", -a["last"]))
    return out


def class_suggestion(mid, ck, classes):
    """Best upcoming class to invite an absent member to: one like those they attended."""
    now = datetime.now(APP_TZ).replace(tzinfo=None)
    upcoming = [c for c in classes if c["_start"] > now]
    if not upcoming:
        return None
    attended = set()
    if ck is not None and not ck.empty and "class_id" in ck.columns:
        names = {c["id"]: c["name"] for c in classes}
        mine = ck[(ck["member_id"] == mid) & ck["class_id"].notna()]
        attended = {names.get(i) for i in mine["class_id"] if names.get(i)}
    for c in upcoming:
        if c["name"] in attended:
            return c, True
    return upcoming[0], False


# ------------------------------------------------ attendance events
# Every way a member can check in (front desk, QR/card scan, kiosk, a device
# calling the API, a history import) produces the same record in `checkins`:
#   gym_id, member_id, checked_in_at, source, event_id (+ class_id, location_id)
# event_id is unique per gym, so the same visit can never be counted twice.
CHECKIN_SOURCES = {
    "front_desk": "Front desk", "scan": "QR or card scan", "kiosk": "Kiosk",
    "device": "Check-in device", "import": "Imported", "unknown": "Earlier check-in",
}
DUPLICATE_WINDOW_MINUTES = 10


def checkin_event_id(gym_id, member_id, at_iso=None):
    """A stable id: the same member at the same minute always gives the same id."""
    import uuid
    if at_iso is None:
        return str(uuid.uuid4())
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"gympulse:{gym_id}:{member_id}:{str(at_iso)[:16]}"))


def _is_duplicate_error(error):
    text = str(error).lower()
    return "23505" in text or "duplicate key" in text or "unique" in text


def record_checkin(supabase, gym_id, member_id, source="front_desk", at=None,
                   class_id=None, event_id=None):
    """Save one attendance event. Returns "saved", "duplicate" or "legacy"
    (saved without the Phase 1 columns because the SQL has not been run yet)."""
    row = {"gym_id": gym_id, "member_id": member_id}
    if at is not None:
        row["checked_in_at"] = at
    extra = {"source": source, "event_id": event_id or checkin_event_id(gym_id, member_id, at)}
    attempts = []
    if class_id:
        attempts.append({**row, **extra, "class_id": class_id})
    attempts.append({**row, **extra})
    if class_id:
        attempts.append({**row, "class_id": class_id})
    attempts.append(row)
    last = None
    for i, payload in enumerate(attempts):
        try:
            supabase.table("checkins").insert(payload).execute()
            return "saved" if "event_id" in payload else "legacy"
        except Exception as error:
            if _is_duplicate_error(error):
                return "duplicate"
            last = error
    raise last


def _recently_checked_in(supabase, gym_id, member_id, minutes=DUPLICATE_WINDOW_MINUTES):
    since = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    try:
        rows = (supabase.table("checkins").select("id").eq("gym_id", gym_id)
                .eq("member_id", member_id).gte("checked_in_at", since).limit(1)
                .execute().data or [])
        return bool(rows)
    except Exception:
        return False


def _do_checkin(supabase, gym_id, member_id, name, use_class=False, source="front_desk"):
    cid = st.session_state.get("ck_class_sel") if use_class else None
    first = (name or "").split(" ")[0] or "there"
    if _recently_checked_in(supabase, gym_id, member_id):
        st.session_state["ck_flash"] = f"{first} is already checked in."
    else:
        try:
            result = record_checkin(supabase, gym_id, member_id, source, class_id=cid)
            st.session_state["ck_flash"] = (f"{first} is already checked in." if result == "duplicate"
                                            else f"Welcome, {first}! You're checked in.")
        except Exception as error:
            st.session_state["ck_flash"] = f"Could not check in: {error}"
    bump_data_version()
    st.session_state["ck_n"] = st.session_state.get("ck_n", 0) + 1


CHECKIN_IMPORT_HELP = (
    "One row per visit. Columns: **member** (name, email, phone or member code) and "
    "**date** (for example 2026-10-14). Optional: **time** (18:30). Visits already in "
    "GymPulse are skipped, so you can import the same file twice safely."
)


def parse_checkin_csv(csv_df, members):
    """Match each row to a member and a visit time. Returns (rows, issues)."""
    cols = {c.strip().lower(): c for c in csv_df.columns}
    member_col = next((cols[c] for c in ("member", "name", "full_name", "member_name",
                                         "email", "phone", "member_code", "code") if c in cols), None)
    date_col = next((cols[c] for c in ("date", "visit_date", "checked_in_at", "check_in",
                                       "datetime", "timestamp") if c in cols), None)
    time_col = next((cols[c] for c in ("time", "visit_time") if c in cols), None)
    if member_col is None or date_col is None:
        return [], [{"Row": "-", "Member": "-", "Problem": "Need a 'member' column and a 'date' column",
                     "Result": "Nothing imported"}]
    lookup = {}
    for _, m in members.iterrows():
        mid = m["id"]
        for key in (_text(m.get("full_name")).lower(), _text(m.get("email")).lower(),
                    member_code(mid).lower(), str(mid).lower()):
            if key:
                lookup.setdefault(key, mid)
        ph = re.sub(r"\D", "", _text(m.get("phone")))
        if len(ph) >= 7:
            lookup.setdefault(ph[-10:], mid)
    rows, issues = [], []
    now = datetime.now(APP_TZ)
    for i, rec in csv_df.iterrows():
        raw = _text(rec.get(member_col)).strip()
        key = raw.lower()
        mid = lookup.get(key)
        if mid is None:
            digits = re.sub(r"\D", "", raw)
            mid = lookup.get(digits[-10:]) if len(digits) >= 7 else None
        if mid is None:
            issues.append({"Row": i + 2, "Member": raw or "(blank)", "Problem": "No matching member",
                           "Result": "Skipped"})
            continue
        when_text = _text(rec.get(date_col)).strip()
        if time_col is not None and _text(rec.get(time_col)).strip():
            when_text += " " + _text(rec.get(time_col)).strip()
        when = pd.to_datetime(when_text, errors="coerce", dayfirst=False)
        if pd.isna(when):
            issues.append({"Row": i + 2, "Member": raw, "Problem": f"Can't read date '{when_text}'",
                           "Result": "Skipped"})
            continue
        if when.tzinfo is None:
            if when.hour == 0 and when.minute == 0 and time_col is None and len(when_text) <= 10:
                when = when + pd.Timedelta(hours=12)   # date only: count it at midday
            when = when.tz_localize(APP_TZ)
        if when > pd.Timestamp(now) + pd.Timedelta(minutes=5):
            issues.append({"Row": i + 2, "Member": raw, "Problem": "Date is in the future",
                           "Result": "Skipped"})
            continue
        rows.append({"member_id": mid, "at": when.tz_convert("UTC").isoformat()})
    return rows, issues


def import_checkins(supabase, gym_id, rows, existing):
    """Insert parsed visits, skipping any already recorded. Returns counts."""
    seen = set()
    if existing is not None and not existing.empty:
        at = pd.to_datetime(existing["at"]).dt.tz_localize(APP_TZ).dt.tz_convert("UTC")
        seen = set(zip(existing["member_id"], at.dt.strftime("%Y-%m-%dT%H:%M")))
    saved = skipped = 0
    for r in rows:
        key = (r["member_id"], r["at"][:16])
        if key in seen:
            skipped += 1
            continue
        seen.add(key)
        if record_checkin(supabase, gym_id, r["member_id"], "import", at=r["at"]) == "duplicate":
            skipped += 1
        else:
            saved += 1
    bump_data_version()
    return saved, skipped


def render_checkin_import(supabase, gym_id, members, ck):
    st.markdown(CHECKIN_IMPORT_HELP)
    up = st.file_uploader("Visit history (CSV)", type=["csv"], key="ck_import_file")
    import gympulse_reports as rp  # local import: gympulse_reports imports this module
    rp.download_link("Download a template", "member,date,time\nAda Obi,2026-10-01,07:30\n",
                     "gympulse_checkins_template.csv", "text/csv", "ck_import_tpl")
    if up is None:
        return
    try:
        df = pd.read_csv(up, dtype=str).fillna("")
    except Exception as error:
        st.error(f"Could not read that file: {error}")
        return
    rows, issues = parse_checkin_csv(df, members)
    st.write(f"**{len(rows)}** visit(s) ready to import"
             + (f", **{len(issues)}** row(s) need attention." if issues else "."))
    if issues:
        table(pd.DataFrame(issues)[ISSUE_COLS])
    if rows and st.button(f"Import {len(rows)} visit(s)", type="primary", key="ck_import_go"):
        with st.spinner("Importing visits…"):
            saved, skipped = import_checkins(supabase, gym_id, rows, ck)
        st.session_state["ck_flash"] = (f"Imported {saved} visit(s)."
                                        + (f" {skipped} were already recorded." if skipped else "")
                                        + " The Risk Radar now uses this history.")
        st.session_state.pop("ck_import_file", None)
        st.rerun()


def _undo_checkin(supabase, gym_id, checkin_id):
    try:
        (supabase.table("checkins").delete()
         .eq("id", checkin_id).eq("gym_id", gym_id).execute())
        st.session_state["ck_flash"] = "Check-in removed."
    except Exception as error:
        st.session_state["ck_flash"] = f"Could not remove: {error}"


def _alert_action(supabase, gym_id, member_id, name):
    try:
        if _has_open_action(supabase, member_id):
            st.session_state["ck_flash"] = f"{name} already has an open action."
        else:
            _create_action(supabase, gym_id, member_id, "WhatsApp check-in", 1)
            st.session_state["ck_flash"] = (f"Follow-up added for {name}. "
                                            "Find it in the Action Centre.")
    except Exception as error:
        st.session_state["ck_flash"] = f"Could not add: {error}"


def _invite_to_class(supabase, gym_id, member_id, name, cls):
    try:
        if _has_open_action(supabase, member_id):
            st.session_state["ck_flash"] = f"{name} already has an open action."
        else:
            _create_action(supabase, gym_id, member_id, "Class invite", 1,
                           details={"title": cls["name"], "when": class_when_long(cls["_start"])})
            st.session_state["ck_flash"] = (f"Class invite for {name} added. Open it in the "
                                            "Action Centre to send the message.")
    except Exception as error:
        st.session_state["ck_flash"] = f"Could not add: {error}"


def _delete_class(supabase, gym_id, class_id):
    try:
        supabase.table("classes").delete().eq("id", class_id).eq("gym_id", gym_id).execute()
        st.session_state["ck_flash"] = "Class removed."
    except Exception as error:
        st.session_state["ck_flash"] = f"Could not remove: {error}"


def render_checkin(supabase, gym_id):
    page_header("Front Desk Check-in",
                "Members check in at the gym. Attendance, drop-off alerts and the "
                "Risk Radar update by themselves.",
                "At the gym")
    flash = st.session_state.pop("ck_flash", None)
    if flash:
        st.success(flash)

    ck = load_checkins(supabase, gym_id)
    if ck is None:
        st.warning("Check-ins need a one-time database update. Run the checkins "
                   "SQL in Supabase, then refresh this page.")
        return
    try:
        members, _ = fetch_members(supabase, gym_id, archived=False)
    except Exception as error:
        st.error("Could not load members.")
        with st.expander("Technical details"):
            st.code(str(error))
        return
    members = members[~members["suspended"]]
    if members.empty:
        st.info("Register members in Member Management first.")
        return

    classes = load_classes(supabase, gym_id)
    names = dict(zip(members["id"], members["full_name"]))
    photos = dict(zip(members["id"], members["photo"]))
    today = pd.Timestamp(today_local())
    now = datetime.now(APP_TZ).replace(tzinfo=None)
    has_rows = not ck.empty
    today_rows = ck[ck["day"] == today] if has_rows else ck
    today_ids = set(today_rows["member_id"]) if has_rows else set()
    week_ids = set(ck.loc[(today - ck["day"]).dt.days < 7, "member_id"]) if has_rows else set()
    if has_rows:
        recent = ck[(today - ck["day"]).dt.days < 30]
        month_visits = len(recent.drop_duplicates(["member_id", "day"]))
    else:
        month_visits = 0
    kpi_row([
        ("In today", len(today_ids), "lime", f"{today:%A}"),
        ("Active this week", len(week_ids), "cyan", "Members who visited"),
        ("Visits, 30 days", month_visits, "white", "One per member per day"),
    ])

    tab_in, tab_alert, tab_log, tab_cls, tab_imp = st.tabs(
        ["Check in", "Drop-off alerts", "Today's log", "Classes", "Import history"])
    with tab_imp:
        render_checkin_import(supabase, gym_id, members, ck)

    with tab_in:
        today_classes = [c for c in classes if c["_start"].date() == now.date()]
        cls_ids = [None] + [c["id"] for c in today_classes]
        if st.session_state.get("ck_class_sel") not in cls_ids:
            best, gap = None, None
            for c in today_classes:
                mins = (c["_start"] - now).total_seconds() / 60
                if -90 <= mins <= 30 and (gap is None or abs(mins) < gap):
                    best, gap = c["id"], abs(mins)
            st.session_state["ck_class_sel"] = best
        if today_classes:
            by_id = {c["id"]: c for c in today_classes}
            st.selectbox("Checking in for", cls_ids, key="ck_class_sel",
                         format_func=lambda i: "Open gym" if i is None
                         else f'{by_id[i]["name"]} · {by_id[i]["_start"]:%I:%M %p}')

        n = st.session_state.get("ck_n", 0)
        q = st.text_input("Find a member, or scan a code", key=f"ck_search_{n}",
                          placeholder="Type a name or phone, or scan a QR, barcode or fob")
        needle = q.strip().lower()
        digits = re.sub(r"\D", "", needle)

        if len(needle) == 8 and re.fullmatch(r"[0-9a-f]{8}", needle):
            hit = None
            for _, r in members.iterrows():
                if member_code(r["id"]).lower() == needle:
                    hit = r
                    break
            if hit is not None:
                if hit["id"] in today_ids:
                    st.session_state["ck_flash"] = f"{_text(hit['full_name'])} is already checked in today."
                    st.session_state["ck_n"] = n + 1
                else:
                    _do_checkin(supabase, gym_id, hit["id"], _text(hit["full_name"]), True,
                                source="scan")
                st.rerun()

        if not needle:
            st.caption("Members can type their name or phone number. Scanners, RFID "
                       "readers and card readers that type a code check in automatically.")
        else:
            hits = []
            for _, r in members.iterrows():
                name_ok = needle in _text(r["full_name"]).lower()
                phone_ok = (len(digits) >= 3
                            and digits in re.sub(r"\D", "", _text(r["phone"])))
                if name_ok or phone_ok:
                    hits.append(r)
            if not hits:
                st.info("No member found. Check the spelling, or ask the front desk.")
            for r in hits[:6]:
                mid, name = r["id"], _text(r["full_name"])
                with st.container(border=True, key=f"card_ci_{mid}"):
                    _md(f'<div style="display:flex;align-items:center;gap:14px;">'
                        f'{avatar_html(name, r["photo"], 56)}'
                        f'<div style="font-size:18px;font-weight:800;color:#F4F7FB;">'
                        f'{_esc(name)}</div></div>')
                    if mid in today_ids:
                        st.button("Checked in today ✓", key=f"ci_{mid}",
                                  disabled=True, use_container_width=True)
                    else:
                        st.button("Check in", key=f"ci_{mid}", type="primary",
                                  on_click=_do_checkin,
                                  args=(supabase, gym_id, mid, name, True),
                                  use_container_width=True)
        st.caption("Tip: leave this page open on a tablet at the front desk. "
                   "The search box clears after each check-in.")

    with tab_alert:
        alerts = [a for a in absence_alerts(ck) if a["id"] in names]
        if not alerts:
            st.success("Nobody has dropped out of their pattern. "
                       "Alerts appear once members have a few weeks of check-ins.")
        else:
            st.caption(f"{len(alerts)} member(s) have changed their usual pattern.")
            if st.button("Add follow-up actions for everyone listed",
                         key="ck_all", use_container_width=True):
                for a in alerts[:20]:
                    _alert_action(supabase, gym_id, a["id"], names[a["id"]])
                st.rerun()
            for a in alerts[:20]:
                mid, name = a["id"], names[a["id"]]
                tone = "red" if a["kind"] == "pattern" else "amber"
                label = "Pattern change" if a["kind"] == "pattern" else "Expected today"
                sug = class_suggestion(mid, ck, classes)
                with st.container(border=True, key=f"card_al_{mid}"):
                    _md(f'<div style="display:flex;align-items:center;gap:12px;">'
                        f'{avatar_html(name, photos.get(mid), 46)}<div>'
                        f'<div style="font-weight:800;color:#F4F7FB;">{_esc(name)}</div>'
                        f'<div class="chip-row">{chip(label, tone, dot=True)}</div></div></div>')
                    st.caption(a["reason"])
                    if sug:
                        cls, similar = sug
                        st.caption(f"{'A class like ones they attended' if similar else 'Next class'}: "
                                   f"{cls['name']} · {class_when(cls['_start'])}")
                    bc = st.columns(3 if sug else 2)
                    bc[0].button("Add follow-up", key=f"alx_{mid}", on_click=_alert_action,
                                 args=(supabase, gym_id, mid, name), use_container_width=True)
                    bc[1].button("Message", key=f"alm_{mid}", on_click=open_followup,
                                 args=(mid, "Check-in"), use_container_width=True)
                    if sug:
                        bc[2].button("Invite to class", key=f"alc_{mid}", on_click=_invite_to_class,
                                     args=(supabase, gym_id, mid, name, sug[0]),
                                     use_container_width=True)

    with tab_log:
        if today_rows.empty:
            st.caption("No check-ins yet today.")
        else:
            cname = {c["id"]: c["name"] for c in classes}
            for _, r in today_rows.sort_values("at", ascending=False).iterrows():
                nm = names.get(r["member_id"], "Member")
                c1, c2, c3 = st.columns([3, 1.6, 1.2], vertical_alignment="center")
                cls_chip = chip(cname[r["class_id"]], "cyan") if r.get("class_id") in cname else ""
                _md(f'<div style="display:flex;align-items:center;gap:10px;">'
                    f'{avatar_html(nm, photos.get(r["member_id"]), 36)}'
                    f'<b style="color:#F4F7FB;">{_esc(nm)}</b>{cls_chip}</div>', c1)
                src = CHECKIN_SOURCES.get(str(r.get("source") or "unknown"), "Check-in")
                _md(f'<div class="money">{r["at"]:%H:%M}</div>'
                    f'<div class="why" style="padding:0">{_esc(src)}</div>', c2)
                c3.button("Undo", key=f"cu_{r['id']}", on_click=_undo_checkin,
                          args=(supabase, gym_id, r["id"]), use_container_width=True)

    with tab_cls:
        st.caption("Add your classes here. When a member checks in during a class, "
                   "it is counted as attendance, and absent members are invited to "
                   "similar classes.")
        with st.form("add_class", clear_on_submit=True):
            cn = st.text_input("Class name", placeholder="e.g. Saturday Morning Yoga")
            c1, c2 = st.columns(2)
            cd = c1.date_input("Date", value=date.today())
            ct = c2.time_input("Start time", value=datetime.strptime("09:00", "%H:%M").time())
            ok = st.form_submit_button("Add class", type="primary", use_container_width=True)
        if ok:
            if not cn.strip():
                st.error("Please enter the class name.")
            else:
                try:
                    supabase.table("classes").insert({
                        "gym_id": gym_id, "name": cn.strip(),
                        "starts_at": datetime.combine(cd, ct).replace(tzinfo=APP_TZ).isoformat(),
                    }).execute()
                    st.session_state["ck_flash"] = "Class added."
                    st.rerun()
                except Exception as error:
                    st.error(f"Could not add the class. Have you run the classes SQL? {error}")
        counts = {}
        if has_rows and "class_id" in ck.columns:
            att = ck[ck["class_id"].notna()]
            counts = att.groupby("class_id")["member_id"].nunique().to_dict()
        booked = {}
        try:                                   # places booked from the member app (phase 18)
            for b in (supabase.table("class_bookings").select("class_id, member_id").eq("gym_id", gym_id)
                      .execute().data or []):
                booked.setdefault(str(b["class_id"]), []).append(b["member_id"])
        except Exception:
            pass
        for c in sorted(classes, key=lambda x: x["_start"], reverse=True)[:12]:
            future = c["_start"] > now
            with st.container(border=True, key=f"card_cls_{c['id']}"):
                _md(f'<div class="chip-row"><b style="color:#F4F7FB;">{_esc(c["name"])}</b>'
                    f'{chip(class_when(c["_start"]), "cyan")}'
                    f'{chip("Upcoming", "lime") if future else chip(str(counts.get(c["id"], 0)) + " attended", "grey")}'
                    f'</div>')
                if future and booked.get(str(c["id"])):
                    who = booked[str(c["id"])]
                    st.caption(f"{len(who)} booked: " + ", ".join(names.get(i, "Member") for i in who[:15]))
                if not future and counts.get(c["id"]):
                    who = ck[ck["class_id"] == c["id"]]["member_id"].unique()
                    st.caption("Attended: " + ", ".join(names.get(i, "Member") for i in who[:15]))
                st.button("Remove class", type="tertiary", key=f"cls_rm_{c['id']}", on_click=_delete_class,
                          args=(supabase, gym_id, c["id"]))

# ------------------------------------------------------------ settings
LANGUAGES = ["English", "French", "Spanish", "Portuguese", "Arabic",
             "Yoruba", "Igbo", "Hausa", "Nigerian Pidgin"]


def render_settings(supabase, owner_id, gym_id, log_out):
    page_header("Settings", "Your profile, gym details and preferences.", "Account")
    flash = st.session_state.pop("settings_flash", None)
    if flash:
        st.success(flash)

    profile = st.session_state.get("user_profile")
    if not isinstance(profile, dict):
        profile = {}
        st.session_state["user_profile"] = profile
    email = (st.session_state.get("auth_user") or {}).get("email", "")
    full = _text(profile.get("full_name"))
    first, _, last = full.partition(" ")
    gym_name = _text(profile.get("business_name"), "My Gym")
    avatar = profile.get("avatar")

    _md(f"""
    <div class="profile-hero">
      {avatar_html(full or "User", avatar, 96, "avatar-ring")}
      <div>
        <div class="profile-name">{_esc(full or "Your name")}</div>
        <div class="chip-row">{chip(gym_name, "cyan")}{chip(email, "grey") if email else ""}</div>
      </div>
    </div>
    """)

    def save(fields, message):
        try:
            supabase.table("profiles").update(fields).eq("id", owner_id).execute()
            saved = fields
        except Exception:
            saved = {k: v for k, v in fields.items()
                     if k in ("full_name", "business_name")}
            try:
                if saved:
                    supabase.table("profiles").update(saved).eq("id", owner_id).execute()
            except Exception as error:
                st.error(f"Could not save: {error}")
                return
            if len(saved) < len(fields):
                st.warning("Some settings need the one-time database update "
                           "(the SQL in the setup notes). Name and gym name were saved.")
        profile.update(saved)
        if "business_name" in saved and gym_id:
            try:
                (supabase.table("gyms").update({"business_name": saved["business_name"]})
                 .eq("id", gym_id).execute())
            except Exception:
                pass
        st.session_state["settings_flash"] = message
        st.rerun()

    SECTIONS = ["Personal info", "Photo", "Gym", "Email & branding", "Trainers", "Team & automation",
                "Check-in devices", "Preferences", "Account"]
    st.session_state.setdefault("settings_section", "Personal info")
    section = st.segmented_control("Settings section", SECTIONS, key="settings_section",
                                   label_visibility="collapsed") or "Personal info"

    if section == "Personal info":
        with st.form("settings_profile"):
            c1, c2 = st.columns(2)
            f_first = c1.text_input("First name", value=first)
            f_last = c2.text_input("Last name", value=last)
            f_user = st.text_input("Username", value=_text(profile.get("username")))
            st.text_input("Email address", value=email, disabled=True)
            ok = st.form_submit_button("Save personal info", type="primary", use_container_width=True)
        if ok:
            name = f"{f_first.strip()} {f_last.strip()}".strip()
            if not name:
                st.error("Please enter your name.")
            else:
                save({"full_name": name, "username": f_user.strip() or None},
                     "Personal info saved.")

    if section == "Photo":
        c1, c2 = st.columns([1, 2])
        with c1:
            _md(avatar_html(full or "User", avatar, 130, "avatar-ring"))
        with c2:
            up = st.file_uploader("Upload a profile photo",
                                  type=PHOTO_TYPES, key="settings_photo")
            if up is not None:
                try:
                    new_photo = process_photo(up.getvalue())
                except Exception:
                    new_photo = None
                    st.error("That image could not be read.")
                if new_photo:
                    _md(avatar_html(full or "User", new_photo, 90))
                    if st.button("Save photo", key="settings_photo_save", type="primary"):
                        save({"avatar": new_photo}, "Profile photo saved.")
            if has_photo(avatar) and st.button("Remove photo", type="tertiary", key="settings_photo_rm"):
                save({"avatar": None}, "Profile photo removed.")

    if section == "Gym":
        with st.form("settings_gym"):
            g_name = st.text_input("Gym or company name", value=gym_name)
            ok = st.form_submit_button("Save gym name", type="primary", use_container_width=True)
        if ok:
            if not g_name.strip():
                st.error("Please enter a gym name.")
            else:
                save({"business_name": g_name.strip()}, "Gym name saved.")

    if section == "Trainers":
        render_trainers_editor(supabase, gym_id)

    if section == "Email & branding":
        import gympulse_campaigns as gcamp  # local import: gympulse_campaigns imports this module
        gcamp.render_brand_settings(supabase, gym_id, save)

    if section == "Team & automation":
        import gympulse_automation as ga  # local import: gympulse_automation imports this module
        ga.render_automation_settings(save, profile)

    if section == "Preferences":
        s = dict(profile.get("settings") or {})
        current = s.get("language") or _text(profile.get("language"), "English")
        options = LANGUAGES if current in LANGUAGES else [current] + LANGUAGES
        lang = st.selectbox("Language", options, index=options.index(current))
        tones = ["Warm and friendly", "Professional", "Short and casual"]
        tone = st.selectbox("Message tone", tones,
                            index=tones.index(s["tone"]) if s.get("tone") in tones else 0)
        biz_phone = st.text_input("Business phone or WhatsApp number",
                                  value=s.get("biz_phone", ""))
        signoff = st.text_input("Sign-off on messages", value=s.get("signoff", ""),
                                placeholder=f"The {gym_name} team")
        auto = st.toggle("Automatic renewal reminders", value=s.get("auto_reminders", True))
        days = st.slider("Start reminding this many days before renewal", 3, 14,
                         int(s.get("remind_days", 7)))
        notify = st.toggle("Notify me of new member replies", value=s.get("notify", True))
        if st.button("Save preferences", key="settings_prefs", type="primary"):
            save({"language": lang,
                  "settings": {**s, "language": lang, "tone": tone,
                               "biz_phone": biz_phone.strip(), "signoff": signoff.strip(),
                               "auto_reminders": auto, "remind_days": days,
                               "notify": notify}},
                 "Preferences saved.")

    if section == "Check-in devices":
        st.markdown("**How members can check in**")
        st.write(
            "- **QR code:** every member has one on their profile, Check-in tab. "
            "Print it on a card or show it on their phone.\n"
            "- **Barcode scanners, RFID or NFC readers, card readers and key fobs:** "
            "these usually type the member code and press Enter, so they work on the "
            "Front Desk Check-in page with no setup. Put the member code on the card or fob.\n"
            "- **Self-service kiosk:** open the Check-in page on a touchscreen tablet.\n"
            "- **Biometric and other systems with an HTTP or webhook option:** use the "
            "device key below.")
        key = ""
        try:
            row = (supabase.table("gyms").select("device_key").eq("id", gym_id)
                   .limit(1).execute().data or [])
            key = (row[0].get("device_key") if row else "") or ""
        except Exception:
            key = ""
        if key:
            url = ""
            try:
                url = st.secrets["SUPABASE_URL"]
            except Exception:
                url = "YOUR_SUPABASE_URL"
            st.caption("Your device key. Keep it private, it lets a device check members in:")
            st.code(key)
            st.caption("A device can send a check-in with this request:")
            st.code(f'POST {url}/rest/v1/rpc/device_checkin\n'
                    f'apikey: YOUR_SUPABASE_ANON_KEY\n'
                    f'Content-Type: application/json\n\n'
                    f'{{"p_device_key": "{key}", "p_member_code": "A1B2C3D4"}}', language="text")
        else:
            st.info("Run the check-in devices SQL to create your device key.")

    if section == "Account":
        st.caption("Signing out ends your session on this device.")
        st.button("Log Out", key="settings_logout", on_click=log_out)

# ------------------------------------------------------------------ FAQs
FAQS = [
    ("Getting started", [
        ("How do I add members?",
         "Open Member Management, fill in the member's details and tap Register Member. "
         "Only the full name is required, but a phone number and email let you message them."),
        ("What should I do right after registering members?",
         "Give each member their activity once: plan, monthly fee and visits. Open the Risk Radar, "
         "then Data tools, and use Update activity or Import CSV. After that, check-ins keep "
         "attendance up to date by themselves."),
        ("Does it work on a phone or tablet?",
         "Yes. GymPulse AI works in any modern browser on a laptop, tablet or phone. "
         "A tablet at the front desk works well for check-in."),
        ("Is my gym's data separate from other gyms?",
         "Yes. Every account has its own workspace, and you only ever see your own members."),
    ]),
    ("Front desk check-in", [
        ("How does check-in work?",
         "Open Check-in from the menu. A member types their name or phone number, or scans their "
         "code, and taps Check in. Their attendance and risk update straight away."),
        ("Which check-in methods are supported?",
         "Typing a name or phone, QR codes, and any barcode, RFID, NFC, card or key-fob reader that "
         "types a code and presses Enter. A tablet works as a self-service kiosk. Systems that can "
         "send a web request, such as some biometric or access-control systems, can use the device "
         "key under Settings → Check-in devices. Phone wallet passes and built-in face or "
         "fingerprint recognition are not included."),
        ("Where do I find a member's QR code?",
         "Open the member's profile and go to the Check-in tab. It shows their QR code and member "
         "code, which you can print on a card or fob."),
        ("What are drop-off alerts?",
         "When a member who usually visits regularly stops coming, they appear under Drop-off alerts. "
         "Alerts start once a member has about four visits across the last eight weeks."),
        ("I checked someone in by mistake. Can I undo it?",
         "Yes. Open Today's log on the Check-in page and tap Undo next to their name."),
        ("How are classes tracked?",
         "Add your classes under Check-in → Classes. Members who check in during a class are counted "
         "as attending. Absent members can then be invited to a similar upcoming class."),
    ]),
    ("Risk Radar and scores", [
        ("What does the cancellation probability mean?",
         "It is the model's estimate of how likely a member is to cancel. Use it to decide who to "
         "contact first, not as a guarantee."),
        ("What do High, Medium and Low mean?",
         "High is 50% or more, Medium is 30% to just under 50%, and Low is below 30%."),
        ("How accurate is it?",
         "The model was trained on simulated data, so its accuracy on real members has not been "
         "proven. Combine it with what you know about your members."),
        ("Why does days since last visit go up every day?",
         "The count moves forward with the calendar from the last time activity was saved or the "
         "member last checked in. A member last seen 200 days ago shows 201 tomorrow."),
        ("Why is a member missing from the Risk Radar?",
         "A member appears once they have activity data. Suspended and archived members are left out."),
    ]),
    ("Action Centre and retention plays", [
        ("What are the retention pillars?",
         "Four groups of plays: Customer experience, Trainer relationship, Community and Culture. "
         "Each play is a specific action, such as a trainer intro, a class invite or a welcome-back note."),
        ("How do I run a play?",
         "Tap a play, choose the member, fill in the details it asks for and tap Add to the board. "
         "Open its card, tap Do this play, send the message, then tap I've sent it."),
        ("Does GymPulse send messages by itself?",
         "No. It prepares the message and opens WhatsApp or your email app with the text ready, "
         "and you tap send. Fully automatic WhatsApp needs a paid business service."),
        ("How do I introduce a trainer to a member?",
         "Add trainers under Settings → Trainers. Then start a Trainer intro, Free PT session or "
         "Goal review play. The message includes a private link to the trainer's profile."),
        ("Who can open a trainer's private link?",
         "Anyone you send it to. It shows only that one trainer's photo, specialty, phone and bio, "
         "and does not give access to anything else."),
        ("What does Remove from board do?",
         "Open plays are deleted. Finished plays are hidden from the board, but their results stay "
         "in Business Insights."),
        ("How is What Works calculated?",
         "Save rate = Retained ÷ (Retained + Cancelled). No-response results are listed but not "
         "counted either way, because the real outcome is unknown."),
    ]),
    ("Payments and renewals", [
        ("How do renewal reminders work?",
         "Starting seven days before a membership ends (you can change this in Settings → "
         "Preferences), unpaid members appear under Renewal reminders with a gentle message from "
         "your business. After you send it, tap Mark as sent. The reminder returns weekly until "
         "they renew, and stops 60 days after the plan lapses."),
        ("How do I record a renewal or payment?",
         "Open the member's profile, go to Membership, and use Record a renewal. Once recorded, the "
         "member drops out of the reminders."),
    ]),
    ("Archie", [
        ("What can Archie do?",
         "Archie answers questions about your members and revenue, suggests who to contact first "
         "and writes messages for you. Member names in his answers are buttons that open the profile."),
        ("What does Archie see?",
         "A summary of your numbers and your top at-risk members' names and scores."),
    ]),
    ("Account and settings", [
        ("How do I switch between dark and light mode?",
         "Tap your profile picture at the top right and use the appearance button."),
        ("How do I change my name, photo, gym name or language?",
         "Tap your profile picture, then Profile & settings. Language changes Archie's replies. "
         "Screen labels stay in English."),
        ("I didn't get my confirmation or reset email.",
         "Check your spam folder first. On the sign-in page you can tap the resend button, and "
         "waiting a few minutes between attempts avoids hitting the email limit."),
        ("How do I log out?",
         "Tap your profile picture and choose Log Out."),
    ]),
    ("Troubleshooting", [
        ("The first page load is slow.",
         "On the free hosting plan, the app can take up to a minute to wake up after a quiet period. "
         "After that it is fast."),
        ("A photo won't upload.",
         "JPG, PNG, WebP and iPhone HEIC photos are supported. Try a smaller photo if it still fails."),
        ("A button doesn't respond.",
         "Refresh the page once. If it keeps happening, tell us which page and button it was."),
    ]),
]


def render_faqs():
    page_header("Frequently Asked Questions",
                "Quick answers about members, check-in, plays and settings.", "Help")
    q = st.text_input("Search the help", placeholder="Search, for example: QR code, reminders",
                      key="faq_search", label_visibility="collapsed").strip().lower()
    shown = 0
    for title, items in FAQS:
        rows = [(a, b) for a, b in items if not q or q in a.lower() or q in b.lower()]
        if not rows:
            continue
        st.markdown(f'<div class="section-label">{_esc(title.upper())}</div>',
                    unsafe_allow_html=True)
        for question, answer in rows:
            with st.expander(question, expanded=bool(q)):
                st.write(answer)
            shown += 1
    if not shown:
        st.info("Nothing matches that search. Try a shorter word.")


# --------------------------------------------------------- dashboard
def render_dashboard(supabase, gym_id, assess_fn, greeting, user_name, business_name):
    page_header(f"{greeting}, {user_name}",
                f"Welcome to {business_name}. Let's build a stronger, smarter fitness business.",
                "Your fitness workspace")
    try:
        roster, _ = load_roster(supabase, gym_id, assess_fn)
        actions = load_actions(supabase, gym_id)
    except Exception:
        roster, actions = pd.DataFrame(), pd.DataFrame()

    if roster.empty:
        st.markdown('<div class="section-label">GET STARTED IN THREE STEPS</div>',
                    unsafe_allow_html=True)
        _md("""
        <div class="lp-steps">
          <div class="lp-stepcard"><div class="lp-num">01</div>
            <h4>Register your members</h4>
            <p>Add each member with a photo, contact details and goal in Member Management.</p></div>
          <div class="lp-stepcard"><div class="lp-num">02</div>
            <h4>Add their activity</h4>
            <p>Enter visits and renewal timing, or import a CSV from the Risk Radar.</p></div>
          <div class="lp-stepcard"><div class="lp-num">03</div>
            <h4>Reach out early</h4>
            <p>See who is drifting away and follow up from the Action Centre.</p></div>
        </div>
        """)
        st.button("Register your first member", key="qa_register", on_click=_go,
                  args=("Member Management",), use_container_width=True)
    else:
        k = kpis(roster, actions)
        kpi_row([
            ("Members scored", k["members_scored"], "cyan", "On your radar"),
            ("High risk", k["high"], "red", "Need you first"),
            ("Expected monthly loss", _money(k["expected_loss"]), "amber", "Estimate, not a forecast"),
            ("Open actions", k["open_actions"], "lime", "Follow-ups to finish"),
        ])
        due_n = renewal_due_count(supabase, gym_id, roster)
        if due_n:
            st.info(f"{due_n} renewal reminder{'s' if due_n != 1 else ''} due. "
                    "Unpaid members get a gentle weekly nudge until they renew.")
            st.button("Open renewal reminders", key="dash_rem", on_click=_go,
                      args=("Payments & Renewals",))
        st.markdown('<div class="section-label">WHO NEEDS YOU TODAY</div>',
                    unsafe_allow_html=True)
        need = members_to_contact(roster, actions)
        if need.empty:
            st.success("Nobody needs a follow-up right now. Nice work.")
        else:
            if _mobile():
                for _, r in need.head(3).iterrows():
                    mobile_member_card(
                        r, "dash", why=r["drivers"],
                        chips=risk_chip(r["risk_category"], r["cancellation_probability"])
                              + chip(r["suggested_action"], "cyan"),
                        actions=[("Open profile", "mopen_dash", open_profile,
                                  (r["id"], "Dashboard"))])
            else:
                with st.container(border=True, key="card_dash_today"):
                    for _, r in need.head(3).iterrows():
                        c = st.columns([0.6, 3.4, 2.2], vertical_alignment="center")
                        _md(avatar_html(r["full_name"], r.get("photo"), 44, "row-tight"), c[0])
                        c[1].button(str(r["full_name"]), key=f"mrow_dash_{r['id']}",
                                    on_click=open_profile, args=(r["id"], "Dashboard"),
                                    use_container_width=True)
                        _md(f'<div class="why">{_esc(r["drivers"])}</div>', c[1])
                        _md(risk_chip(r["risk_category"], r["cancellation_probability"])
                            + chip(r["suggested_action"], "cyan"), c[2])
            st.button("See everyone on the Risk Radar", key="qa_radar_more", type="tertiary", on_click=_go,
                      args=("Risk Radar",))

    st.markdown('<div class="section-label">QUICK ACTIONS</div>', unsafe_allow_html=True)
    tiles = [
        ("Member Management", "Member Management", ":material/group:"),
        ("Action Centre", "Action Centre", ":material/task_alt:"),
        ("Front Desk Check-in", "Check-in", ":material/how_to_reg:"),
        ("Ask Archie", "Archie", ":material/smart_toy:"),
        ("Payments & Renewals", "Payments & Renewals", ":material/payments:"),
    ]

    for i in range(0, len(tiles), 4):
        cols = st.columns(4)
        for col, (label, page, icon) in zip(cols, tiles[i:i+4]):
            _ibtn(col, label, icon, key=f"qa_{page}", on_click=_go, args=(page,),
                  use_container_width=True)

    st.markdown('<div class="section-label">HOW IT WORKS</div>', unsafe_allow_html=True)
    _md("""
    <div class="lp-steps">
      <div class="lp-stepcard"><div class="lp-num">01</div><h4>Input</h4>
        <p>Provide membership, attendance, renewal and personal-training information.</p></div>
      <div class="lp-stepcard"><div class="lp-num">02</div><h4>Analyse</h4>
        <p>The model processes five features to estimate cancellation probability.</p></div>
      <div class="lp-stepcard"><div class="lp-num">03</div><h4>Explore</h4>
        <p>Review the experimental estimate and investigate attendance patterns.</p></div>
    </div>
    """)
