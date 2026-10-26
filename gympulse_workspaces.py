"""GymPulse AI: Risk Radar, Retention Action Centre, Payments & Renewals,
Business Insights, Archie.
"""
import base64
import io
import os
import re
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from html import escape as _html_escape

import pandas as pd
import streamlit as st

ARCHIE_MODEL = "claude-sonnet-5-5"

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
    .nav-tagline { display: none !important; }
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
PLAN_DAYS = {"Monthly": 30, "Quarterly": 90, "Annual": 365}
PLAN_MONTHS = {"Monthly": 1, "Quarterly": 3, "Annual": 12}
PHOTO_SIZE = 192
GOALS = ["Weight loss", "Muscle gain", "General fitness", "Strength",
         "Endurance", "Sports performance"]
CHART_MUTED = "#9AA8BD"

def _esc(value):
    return _html_escape("" if value is None else str(value), quote=True)

def _md(markup, target=None):
    flat = " ".join(line.strip() for line in str(markup).splitlines() if line.strip())
    (target if target is not None else st).markdown(flat, unsafe_allow_html=True)

def _text(value, default=""):
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    return str(value)

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
    style = f"width:{size}px;height:{size}px;font-size:{max(11, int(size * 0.38))}px;"
    if has_photo(photo):
        return f'<img class="{cls}" style="{style}" src="{photo}" alt="{_esc(name)}">'
    return f'<div class="{cls}" style="{style}">{_esc(initials(name))}</div>'

def whatsapp_digits(phone):
    digits = re.sub(r"\D", "", str(phone or ""))
    if digits.startswith("00"):
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = "234" + digits[1:]
    return digits

# ----------------------------------------------------------- components
def page_header(title, subtitle="", eyebrow=""):
    parts = []
    if eyebrow:
        parts.append(f'<div class="pg-eyebrow">{_esc(eyebrow)}</div>')
    parts.append(f'<div class="pg-title">{_esc(title)}</div>')
    if subtitle:
        parts.append(f'<div class="pg-sub">{_esc(subtitle)}</div>')
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

[data-testid="stChatMessageAvatarUser"] { background: #35D6ED !important; }
[data-testid="stChatMessageAvatarUser"] * { color: #0B1020 !important; }
[data-testid="stChatMessageAvatarAssistant"] { background: transparent !important; }
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
.stButton > button { box-shadow: 0 6px 18px rgba(183,243,74,.16);
    transition: transform .15s ease, box-shadow .15s ease; }
.stButton > button:hover { transform: translateY(-1px); box-shadow: 0 10px 24px rgba(183,243,74,.24); }
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
[data-testid="stChatMessage"] { background: rgba(21,29,48,0.7);
    border: 1px solid rgba(255,255,255,0.08); border-radius: 16px; }

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

def apply_ui_styles():
    st.markdown("<style>" + UI_CSS + "</style>", unsafe_allow_html=True)

# ------------------------------------------------------------ speed & caching
class _TrackedTable:
    def __init__(self, table):
        self._t = table
    def __getattr__(self, name):
        attr = getattr(self._t, name)
        if name in ("insert", "update", "upsert", "delete"):
            def wrapper(*args, **kwargs):
                st.session_state["_dv"] = st.session_state.get("_dv", 0) + 1
                return attr(*args, **kwargs)
            return wrapper
        return attr

class TrackedClient:
    def __init__(self, client):
        self._client = client
    def __getattr__(self, name):
        return getattr(self._client, name)
    def table(self, name):
        return _TrackedTable(self._client.table(name))

def _clone(value):
    if isinstance(value, pd.DataFrame):
        return value.copy()
    if isinstance(value, tuple):
        return tuple(_clone(v) for v in value)
    return value

def _cached(key, fn, ttl=60, skip_empty=False):
    # Increased TTL to 60s to avoid re-fetching on every page switch
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
            rows = query.order("created_at", desc=True).execute().data or []
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
    
    # Carry through payment / renewal columns so Payments page works
    keep = ["id", "full_name", "email", "phone", "fitness_goal",
            "membership_end", "last_payment", "last_renewed_on"]
    if with_photos:
        keep.append("photo")
    members = members[[c for c in keep if c in members.columns]].reset_index(drop=True)

    activity = pd.DataFrame(
        supabase.table("member_activity").select("*")
        .eq("gym_id", gym_id).execute().data or []
    )
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
    scored = assess_fn(scored.reset_index(drop=True))
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
    rows = query.order("created_at", desc=True).execute().data or []
    return pd.DataFrame(rows)

def fetch_members(supabase, gym_id, archived=None, include_photo=True):
    return _cached(("members", gym_id, archived, include_photo),
                   lambda: _fetch_members_uncached(supabase, gym_id, archived, include_photo))

def load_roster(supabase, gym_id, assess_fn, with_photos=True):
    return _cached(("roster", gym_id, with_photos),
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
        out.append(f"renews in {int(row['renewal_due_days'])} days")
    if row["pt_sessions_attended"] == 0:
        out.append("no PT sessions")
    if row["membership_type"] == "Monthly":
        out.append("monthly plan (easy to leave)")
    return ", ".join(out) or "no major warning signs"

def suggest_action(row):
    if row["renewal_due_days"] <= 14 and row["risk_category"] != "Low":
        return "Renewal offer"
    if row["days_since_last_visit"] >= 14:
        return "Personal call"
    if row["pt_sessions_attended"] == 0:
        return "Free PT session"
    if row["risk_category"] == "Low":
        return "Goal review"
    return "WhatsApp check-in"

def members_to_contact(roster, actions, cooldown_days=SUGGEST_COOLDOWN_DAYS, today=None):
    if roster.empty:
        return roster
    blocked = set()
    if not actions.empty:
        now = pd.Timestamp(today or date.today())
        open_mask = actions["status"] != "Done"
        blocked |= set(actions.loc[open_mask, "member_id"])
        done = actions[~open_mask].copy()
        when = pd.to_datetime(done["completed_at"], errors="coerce", utc=True)
        when = when.dt.tz_localize(None)
        recent = when.isna() | (when >= now - pd.Timedelta(days=cooldown_days))
        blocked |= set(done.loc[recent, "member_id"])
        blocked |= set(done.loc[done["outcome"] == "Cancelled", "member_id"])
    return roster[(roster["risk_category"] != "Low") & ~roster["id"].isin(blocked)]

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

    plans = ["Monthly", "Quarterly", "Annual"]

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
                index=plans.index(val("membership_type", "Monthly"))
            )
            fee = c2.number_input(
                "Monthly fee", min_value=0.0, step=500.0,
                value=float(val("monthly_fee", 0.0))
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
            if st.form_submit_button("Save activity", use_container_width=True):
                supabase.table("member_activity").upsert({
                    "member_id": member_id, "gym_id": gym_id,
                    "membership_type": mtype, "monthly_fee": float(fee),
                    "days_since_last_visit": int(d),
                    "visits_previous_30_days": int(prev),
                    "visits_last_30_days": int(last),
                    "renewal_due_days": int(ren),
                    "pt_sessions_attended": int(pt),
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
IMPORT_PLANS = {"monthly": "Monthly", "quarterly": "Quarterly", "annual": "Annual"}
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
            skip("membership_type must be Monthly, Quarterly or Annual")
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
        st.download_button(
            "Download a template with my members",
            template.to_csv(index=False).encode("utf-8"),
            "gympulse_activity_template.csv", "text/csv",
        )
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
            st.dataframe(issues, hide_index=True, use_container_width=True)
        if not payload:
            return

        names = members.set_index("id")["full_name"]
        preview = pd.DataFrame(payload)
        preview.insert(0, "member", preview["member_id"].map(names))
        st.caption("Preview of the first 20 rows:")
        st.dataframe(preview.drop(columns="member_id").head(20),
                     hide_index=True, use_container_width=True)

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
                if b.button("Restore", key=f"rs_{r['id']}"):
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

def _create_action(supabase, gym_id, member_id, action_type, renewal_days, note=""):
    due = date.today() + timedelta(days=1 if renewal_days <= 14 else 3)
    supabase.table("retention_actions").insert({
        "gym_id": gym_id, "member_id": member_id, "action_type": action_type,
        "due_date": due.isoformat(), "note": note}).execute()

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
    with st.container(border=True, key="card_dir"):
        for _, r in shown.head(limit).iterrows():
            a, b = st.columns([0.7, 6], vertical_alignment="center")
            _md(avatar_html(r["full_name"], r["photo"], 48, "row-tight"), a)
            b.button(str(r["full_name"]), key=f"mrow_dir_{r['id']}",
                     on_click=open_profile, args=(r["id"], "Member Management"),
                     use_container_width=True)
    if len(shown) > limit:
        st.button(f"Show {min(12, len(shown) - limit)} more "
                  f"({len(shown) - limit} left)", key="mm_more",
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
    st.button("← Back", key="profile_back_btn", on_click=_go, args=(back,))

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
    if act:
        try:
            one = pd.DataFrame([{c: act.get(c) for c in ACTIVITY_COLS}])
            scored = assess_fn(one).iloc[0]
            drivers_text = drivers(scored)
            action_text = suggest_action(scored)
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

    tab_overview, tab_plan, tab_photo, tab_edit = st.tabs(
        ["Overview", "Membership", "Photo", "Edit details"])

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
              <div class="why" style="padding:8px 0 0;">Why: {_esc(drivers_text)}</div>
            </div>
            """)
            if st.button("Create a follow-up action", key="prof_create"):
                if _has_open_action(supabase, member_id):
                    st.info(f"{name} already has an open action in the Action Centre.")
                else:
                    _create_action(supabase, gym_id, member_id, action_text,
                                   int(scored["renewal_due_days"]))
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
        renewed = _text(m["last_renewed_on"])[:10]
        paid = _num(m["last_payment"], None)
        _md(f"""
        <div class="panel">
          <div class="kv"><span>Plan</span><b>{_esc(_text(act.get("membership_type")) if act else "—")}</b></div>
          <div class="kv"><span>Monthly fee</span><b>{"—" if fee is None else f"{fee:,.0f}"}</b></div>
          <div class="kv"><span>Plan runs until</span><b>{state["end"].strftime("%d %b %Y") if state["end"] else "—"}</b></div>
          <div class="kv"><span>Last renewed</span><b>{_esc(renewed) if renewed else "—"}</b></div>
          <div class="kv"><span>Last payment</span><b>{"—" if paid is None else f"{paid:,.0f}"}</b></div>
        </div>
        """)

        st.markdown("#### Record a renewal")
        plans = list(PLAN_DAYS)
        current_plan = _text(act.get("membership_type")) if act else "Monthly"
        if current_plan not in plans:
            current_plan = "Monthly"
        r1, r2, r3 = st.columns(3)
        plan = r1.selectbox("Plan", plans, index=plans.index(current_plan),
                            key=f"renew_plan_{member_id}")
        current_end = state["end"]
        start_default = (current_end if current_end and current_end >= date.today()
                         else date.today())
        start = r2.date_input("Starts on", value=start_default,
                              key=f"renew_start_{member_id}_{plan}")
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
        if st.button("Save renewal", key="renew_save",
                     disabled=not feat["profile_ready"]):
            try:
                (supabase.table("members").update({
                    "membership_end": new_end.isoformat(),
                    "last_renewed_on": date.today().isoformat(),
                    "last_payment": float(amount),
                }).eq("id", member_id).eq("gym_id", gym_id).execute())
                if act:
                    changes = {
                        "membership_type": plan,
                        "renewal_due_days": int(min(max((new_end - date.today()).days, 0), 730)),
                    }
                    if update_fee and amount > 0:
                        changes["monthly_fee"] = round(float(amount) / PLAN_MONTHS[plan], 2)
                    (supabase.table("member_activity").update(changes)
                     .eq("member_id", member_id).execute())
            except Exception as error:
                st.error(f"Could not save the renewal: {error}")
            else:
                st.session_state["profile_flash"] = (
                    f"Renewal saved. {name} is Active until {new_end:%d %b %Y}.")
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
            up = st.file_uploader("Upload a photo (JPG or PNG)",
                                  type=["jpg", "jpeg", "png"],
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
                    if st.button("Save photo", key="photo_save",
                                 disabled=not feat["profile_ready"]):
                        try:
                            (supabase.table("members").update({"photo": new_photo})
                             .eq("id", member_id).eq("gym_id", gym_id).execute())
                        except Exception as error:
                            st.error(f"Could not save the photo: {error}")
                        else:
                            st.session_state["profile_flash"] = "Photo saved."
                            st.rerun()
            if has_photo(m["photo"]) and st.button("Remove photo", key="photo_remove"):
                try:
                    (supabase.table("members").update({"photo": None})
                     .eq("id", member_id).eq("gym_id", gym_id).execute())
                except Exception as error:
                    st.error(f"Could not remove the photo: {error}")
                else:
                    st.session_state["profile_flash"] = "Photo removed."
                    st.rerun()

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
            saved = st.form_submit_button("Save changes", use_container_width=True)
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
        fallback["risk"] = pd.Categorical(fallback["risk_category"],
                                          categories=["High", "Medium", "Low"],
                                          ordered=True)
        fallback = fallback.dropna(subset=["days_since_last_visit",
                                           "cancellation_probability"])
        st.scatter_chart(
            fallback,
            x="days_since_last_visit",
            y="cancellation_probability",
            color="risk_category",
            height=340,
        )
    except Exception as e:
        st.warning("Couldn't draw the radar chart. Falling back to a table.")
        st.dataframe(
            data[["full_name", "risk_category",
                  "days_since_last_visit", "cancellation_probability"]],
            hide_index=True, use_container_width=True,
        )

PRIORITY_WIDTHS = [0.6, 2.4, 1.0, 1.5, 1.6, 0.9, 1.2]

def _priority_rows(view):
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
            _md(f'<div class="why">{_esc(r["drivers"])}</div>', c[1])
            _md(risk_chip(r["risk_category"]), c[2])
            _md(prob_bar(r["cancellation_probability"], r["risk_category"]), c[3])
            _md(chip(r["suggested_action"], "cyan"), c[4])
            _md(f'<div class="money">{r["monthly_fee"]:,.0f}</div>', c[5])
            c[6].button("Follow up", key=f"follow_prio_{r['id']}", on_click=open_followup,
                        args=(r["id"], "Risk Radar"), use_container_width=True)
    if len(view) > limit:
        st.button(f"Show more ({len(view) - limit} left)", key="prio_more",
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
    plans = f2.multiselect("Membership", ["Monthly", "Quarterly", "Annual"],
                           ["Monthly", "Quarterly", "Annual"])
    search = f3.text_input("Search member", placeholder="Type a name")
    view = roster[roster["risk_category"].isin(levels) & roster["membership_type"].isin(plans)]
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
                 "cyan", "visits vs the previous 30 days"), d2)
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

# ------------------------------------------------------- action centre
def _action_card(supabase, a, names, photos, status, prefix):
    member_id = a["member_id"]
    who = names.get(member_id, "Archived member")
    note = a.get("note")
    note = note if isinstance(note, str) else ""
    with st.container(border=True, key=f"card_{prefix}_{a['id']}"):
        ca, cb = st.columns([0.34, 1], vertical_alignment="center")
        _md(avatar_html(who, photos.get(member_id), 38, "row-tight"), ca)
        cb.button(str(who), key=f"mrow_{prefix}_{a['id']}", on_click=open_profile,
                  args=(member_id, "Action Centre"), use_container_width=True)
        chips = chip(a["action_type"], "cyan") + due_chip(a.get("due_date"), status)
        if status == "Done":
            chips += outcome_chip(a.get("outcome"))
        _md(f'<div class="chip-row">{chips}</div>')
        if status != "Done":
            st.button("Message", key=f"follow_{prefix}_{a['id']}", on_click=open_followup,
                      args=(member_id, "Action Centre"), use_container_width=True)
        if status == "Done":
            if note:
                st.caption(note)
            return
        new_note = st.text_input("Note", value=note, key=f"{prefix}_n_{a['id']}",
                                 placeholder="Add a note…", label_visibility="collapsed")
        if status == "To do":
            if st.button("Start", key=f"{prefix}_s_{a['id']}", use_container_width=True):
                (supabase.table("retention_actions")
                 .update({"status": "In progress", "note": new_note})
                 .eq("id", a["id"]).execute())
                st.rerun()
        else:
            outcome = st.selectbox("Outcome", OUTCOMES, key=f"{prefix}_o_{a['id']}",
                                   label_visibility="collapsed")
            if st.button("Mark done", key=f"{prefix}_d_{a['id']}", use_container_width=True):
                (supabase.table("retention_actions").update({
                    "status": "Done", "outcome": outcome, "note": new_note,
                    "completed_at": datetime.now(timezone.utc).isoformat()})
                 .eq("id", a["id"]).execute())
                st.rerun()

BOARD_TONES = {"To do": "cyan", "In progress": "amber", "Done": "lime"}

def _visible_actions(actions):
    if actions.empty:
        return actions
    if "archived_at" in actions.columns:
        return actions[actions["archived_at"].isna()]
    return actions

def _kanban(supabase, actions, names, photos):
    cols = st.columns(3)
    for col, status in zip(cols, STATUSES):
        sub = actions[actions["status"] == status]
        if status == "Done" and "completed_at" in sub.columns:
            sub = sub.sort_values("completed_at", ascending=False, na_position="last")
        with col:
            _md(f'<div class="kb-head" style="--tone:{TONES[BOARD_TONES[status]]}">'
                f'<span>{status}</span><b>{len(sub)}</b></div>')
            if sub.empty:
                _md('<div class="kb-empty">Nothing here yet</div>')
            shown = sub.head(10) if status == "Done" else sub
            for _, a in shown.iterrows():
                _action_card(supabase, a, names, photos, status, "kb")
            if status == "Done" and len(sub) > 10:
                st.caption(f"+{len(sub) - 10} older ones in the List view.")

def _list_board(supabase, actions, names, photos):
    tabs = st.tabs([f"{s} ({int((actions['status'] == s).sum())})" for s in STATUSES])
    for tab, status in zip(tabs, STATUSES):
        with tab:
            sub = actions[actions["status"] == status]
            if sub.empty:
                st.caption("Nothing here.")
            for _, a in sub.iterrows():
                with st.container(border=True, key=f"card_ls_{a['id']}"):
                    member_id = a["member_id"]
                    who = names.get(member_id, "Archived member")
                    _md(f'<div class="chip-row">{avatar_html(who, photos.get(member_id), 30)}'
                        f'<b style="color:#F4F7FB;align-self:center">{_esc(who)}</b>'
                        f'{chip(a["action_type"], "cyan")}{due_chip(a.get("due_date"), status)}</div>')
                    if status == "Done":
                        _md(f'<div class="chip-row">{outcome_chip(a.get("outcome"))}</div>')
                    else:
                        note = a.get("note")
                        n = st.text_input("Note", note if isinstance(note, str) else "",
                                          key=f"n_{a['id']}")
                        x, y = st.columns(2)
                        if status == "To do" and x.button("Start", key=f"s_{a['id']}"):
                            (supabase.table("retention_actions")
                             .update({"status": "In progress", "note": n})
                             .eq("id", a["id"]).execute())
                            st.rerun()
                        out = y.selectbox("Outcome", OUTCOMES, key=f"o_{a['id']}")
                        if y.button("Mark done", key=f"d_{a['id']}"):
                            (supabase.table("retention_actions").update({
                                "status": "Done", "outcome": out, "note": n,
                                "completed_at": datetime.now(timezone.utc).isoformat()})
                             .eq("id", a["id"]).execute())
                            st.rerun()
                    _delete_action_control(supabase, a["id"])

def _pillars_panel(supabase, gym_id, roster, actions):
    st.markdown('<div class="section-label">RETENTION PILLARS</div>', unsafe_allow_html=True)
    st.caption("Members stay when they feel part of something, know their trainer "
               "and feel looked after. Start a play for any pillar.")
    cols = st.columns(len(PILLARS))
    for col, (name, info) in zip(cols, PILLARS.items()):
        own = actions[actions["action_type"].isin(info["plays"])] if not actions.empty else actions
        done_n = int((own["status"] == "Done").sum()) if len(own) else 0
        open_n = len(own) - done_n
        chips = "".join(chip(p, info["tone"]) for p in info["plays"])
        _md(f'<div class="pillar" style="--tone:{TONES[info["tone"]]}">'
            f'<div class="pillar-ic">{ic(info["icon"], 24)}</div><h4>{_esc(name)}</h4>'
            f'<p>{_esc(info["blurb"])}</p><div class="chip-row">{chips}</div>'
            f'<div class="pn">{done_n} done · {open_n} open</div></div>', col)
    with st.expander("Start a play for a member"):
        names = roster.set_index("id")["full_name"].to_dict()
        ids = list(names)
        c1, c2 = st.columns(2)
        who = c1.selectbox("Member", ids, format_func=lambda i: names[i], key="play_member")
        plays = [(pn, p) for pn, info in PILLARS.items() for p in info["plays"]]
        play = c2.selectbox("Play", plays, format_func=lambda t: f"{t[0]} · {t[1]}", key="play_type")
        if st.button("Add to the board", key="play_add"):
            row = roster[roster["id"] == who].iloc[0]
            _create_action(supabase, gym_id, who, play[1], int(row["renewal_due_days"]))
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
        with st.container(border=True, key="card_suggested"):
            for _, r in top.iterrows():
                c = st.columns([0.6, 3.2, 1.6, 1.2], vertical_alignment="center")
                _md(avatar_html(r["full_name"], r.get("photo"), 42, "row-tight"), c[0])
                c[1].button(str(r["full_name"]), key=f"mrow_sug_{r['id']}",
                            on_click=open_profile, args=(r["id"], "Action Centre"),
                            use_container_width=True)
                _md(f'<div class="why">{_esc(r["drivers"])}</div>', c[1])
                _md(risk_chip(r["risk_category"], r["cancellation_probability"])
                    + chip(r["suggested_action"], "cyan"), c[2])
                if c[3].button("Add", key=f"add_{r['id']}", use_container_width=True):
                    _create_action(supabase, gym_id, r["id"], r["suggested_action"],
                                   r["renewal_due_days"])
                    st.rerun()
        if len(todo) > 1 and st.button("Add all top 5", use_container_width=True):
            for _, r in top.iterrows():
                _create_action(supabase, gym_id, r["id"], r["suggested_action"],
                               r["renewal_due_days"])
            st.rerun()

    _pillars_panel(supabase, gym_id, roster, actions_all)

    st.markdown('<div class="section-label">YOUR BOARD</div>', unsafe_allow_html=True)
    if visible_actions.empty:
        st.info("No actions yet. Add one from the suggestions above.")
        return
    mode = st.radio("Board view", ["Board", "List"], horizontal=True,
                    key="ac_view", label_visibility="collapsed")
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
            
            # FIX NaT Type error
            if isinstance(r["_end"], date):
                end_txt = r["_end"].strftime("%d %b %Y")
            else:
                end_txt = "—"
                
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

    st.caption("Renewals are recorded from each member's profile → Membership "
               "tab → Record a renewal. Update the amount there to keep this "
               "page accurate.")

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


def render_business_insights(supabase, gym_id, assess_fn):
    page_header("Business Insights",
                "What retention is worth, where it leaks, and what's working.",
                "Numbers that matter")
    try:
        roster, _ = load_roster(supabase, gym_id, assess_fn)
        # include archived for accurate What Works history
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
        # Count ALL Done actions (including archived) for accuracy
        tbl = done.groupby("action_type")["outcome"].agg(
            Done="count", Retained=lambda s: int((s == "Retained").sum()))
        tbl["Save rate"] = (tbl["Retained"] / tbl["Done"]).map("{:.0%}".format)
        rows = [
            {"action": at, "done": int(r["Done"]),
             "retained": int(r["Retained"]), "rate": r["Save rate"]}
            for at, r in tbl.iterrows()
        ]
        data_card(rows, [
            ("action", "Action"),
            ("done", "Completed"),
            ("retained", "Retained"),
            ("rate", "Save rate"),
        ], key_prefix="what_works", tone="lime")
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

# ------------------------------------------------------------ Archie
ARCHIE_PROMPTS = [
    "Who should I call first today?",
    "Write a WhatsApp message for my most at-risk member",
    "Why is revenue at risk this month?",
    "Give me a 3-step plan for this week",
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
        <div class="archie-role">Your retention assistant. Ask about members, revenue and follow-ups.</div>
        <div class="archie-status"><span class="dot"></span>{status}
          <span class="archie-wave"><i></i><i></i><i></i><i></i><i></i></span></div>
      </div>
    </div>
    """

def _chat_message(role):
    if role == "assistant":
        return st.chat_message("assistant", avatar=":material/smart_toy:")
    else:
        return st.chat_message("user", avatar=":material/person:")

def _stream(slot, text):
    words = text.split(" ")
    step = max(1, len(words) // 40)
    for i in range(step, len(words), step):
        slot.markdown(" ".join(words[:i]) + " ▍")
        time.sleep(0.03)
    slot.markdown(text)
def archie_context(roster, actions, business_name):
    """Build a concise business context for Archie's member-retention assistant."""

    lines = [
        f"Gym business: {business_name}",
        f"Total scored members: {len(roster)}",
    ]

    # Summarize member risk where the expected columns are available.
    if "risk_category" in roster.columns:
        risk_counts = roster["risk_category"].fillna("Unknown").value_counts()

        lines.append("Member risk summary:")
        for category, count in risk_counts.items():
            lines.append(f"- {category} risk: {count} members")

    # Include recent actions when useful columns are available.
    if not actions.empty:
        lines.append(f"Recorded retention actions: {len(actions)}")

        for column in ("status", "action_type"):
            if column in actions.columns:
                counts = actions[column].fillna("Unknown").value_counts()
                lines.append(f"Actions by {column}:")
                for label, count in counts.items():
                    lines.append(f"- {label}: {count}")
                break

    return "\n".join(lines)
def render_archie(supabase, gym_id, assess_fn, business_name, owner_name="the gym owner"):
    hero = st.empty()
    _md(_archie_hero(False), hero)
    try:
        roster, _ = load_roster(supabase, gym_id, assess_fn, with_photos=False)
        actions = load_actions(supabase, gym_id)
    except Exception:
        roster, actions = pd.DataFrame(), pd.DataFrame()
    if len(roster):
        context = archie_context(roster, actions, business_name)
    else:
        context = f"Gym: {business_name}. No scored members yet."
    context += f"\nThe owner's name is {owner_name}. Sign messages with this name."

    if "archie_msgs" not in st.session_state:
        st.session_state.archie_msgs = []

    st.markdown('<div class="section-label">TRY ASKING</div>', unsafe_allow_html=True)
    cols = st.columns(len(ARCHIE_PROMPTS))
    picked = None
    for col, p in zip(cols, ARCHIE_PROMPTS):
        if col.button(p, key=f"ap_{p}", use_container_width=True):
            picked = p
    for m in st.session_state.archie_msgs:
        with _chat_message(m["role"]):
            st.markdown(m["content"])
    typed = st.chat_input("Ask Archie...")
    question = typed or picked
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
        _md(_archie_hero(False), hero)
        st.session_state.archie_msgs.append({"role": "assistant", "content": reply})
    if st.session_state.archie_msgs and st.button("Clear chat"):
        st.session_state.archie_msgs = []
        st.rerun()
    st.caption("Archie can be wrong. Check details before contacting members. "
               "Only your top at-risk members' names and scores are shared with "
               "the AI service.")

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
        st.markdown('<div class="section-label">WHO NEEDS YOU TODAY</div>',
                    unsafe_allow_html=True)
        need = members_to_contact(roster, actions)
        if need.empty:
            st.success("Nobody needs a follow-up right now. Nice work.")
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
            st.button("See everyone on the Risk Radar", key="qa_radar_more", on_click=_go,
                      args=("Risk Radar",))

    st.markdown('<div class="section-label">QUICK ACTIONS</div>', unsafe_allow_html=True)
    # Only 4 columns per row to make it fit standard desktop widths
    tiles = [
        ("Risk Radar", "Risk Radar", ":material/radar:"),
        ("Member Management", "Member Management", ":material/group:"),
        ("Action Centre", "Action Centre", ":material/task_alt:"),
        ("Follow-ups", "Follow-ups", ":material/forum:"),
        ("Ask Archie", "Archie", ":material/smart_toy:"),
        ("Payments & Renewals", "Payments & Renewals", ":material/payments:"),
        ("Member Assessment", "Member Assessment", ":material/science:"),
        ("Model Insights", "Model Insights", ":material/insights:"),
    ]
    
    # Split into 2 rows of 4
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
