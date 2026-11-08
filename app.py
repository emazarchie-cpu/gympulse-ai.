import gympulse_monitoring as gmon
gmon.init("app")
import gympulse_workspaces as gw
import gympulse_followups as fu
import gympulse_legal as gl
import gympulse_billing as gbill
import gympulse_design as gd
import gympulse_command as gc
import gympulse_grow as gg
import gympulse_team as gteam
import os
import textwrap

import joblib
import pandas as pd
import streamlit as st
from supabase import create_client


# =========================================================
# 1. PAGE CONFIGURATION
# =========================================================

from PIL import Image

_FAVICON_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "GymPulse_AI_favicon.png"
)

try:
    _page_icon = Image.open(_FAVICON_PATH)
except Exception:
    _page_icon = "💪"   # fallback if the file is missing

st.set_page_config(
    page_title="GymPulse AI | Member Intelligence",
    page_icon=_page_icon,
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Switching workspace: hide the previous page's leftovers straight away, so the new page never shows
# old content while it loads. Always the same element here, so ordinary taps don't hide anything.
_rp = st.session_state.get("_rendered_page")
_nav_new = bool(st.session_state.get("navigate_to")) or (
    _rp is not None and st.session_state.get("current_page") != _rp
    and (_rp != "__landing__" or bool(st.session_state.get("auth_user"))))   # landing -> app after sign-in
st.markdown('<style>[data-testid="stElementContainer"][data-stale="true"]{display:none !important}</style>'
            if _nav_new else '<style></style>', unsafe_allow_html=True)



# =========================================================
# 2. PREMIUM FITNESS-TECH DESIGN
# =========================================================

st.markdown(
    """
    <style>
    @import url(
        'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap'
    );

    :root {
        --background: #0B1020;
        --surface: #151D30;
        --surface-light: #1B263B;
        --lime: #B7F34A;
        --cyan: #35D6ED;
        --white: #F4F7FB;
        --muted: #9AA8BD;
        --border: rgba(255,255,255,0.09);
    }

    .stApp {
        background: var(--background);
        color: var(--white);
        font-family: 'Inter', sans-serif;
    }

    [data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stMainMenu"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"] {
    display: none !important;
}

    [data-testid="stSidebar"] {
        background: #10182A;
        border-right: 1px solid var(--border);
    }

    [data-testid="stSidebar"] *:not([data-testid="stIconMaterial"]) {
        font-family: 'Inter', sans-serif;
    }

    h1, h2, h3 {
        color: var(--white) !important;
        font-weight: 800 !important;
        letter-spacing: -0.5px;
    }

    p, label, .stMarkdown {
        color: var(--white);
    }

    .brand-logo {
        font-size: 27px;
        font-weight: 800;
        letter-spacing: -1px;
        color: var(--white);
        margin-bottom: 2px;
    }

    .brand-accent {
        color: var(--lime);
    }

    .brand-tagline {
        color: var(--muted);
        font-size: 12px;
        margin-bottom: 28px;
    }

    .hero {
        padding: 28px 30px;
        background: linear-gradient(
            115deg,
            #17243A 0%,
            #142033 55%,
            #202D37 100%
        );
        border: 1px solid var(--border);
        border-radius: 20px;
        margin-bottom: 25px;
    }

    .hero-eyebrow {
        color: var(--lime);
        text-transform: uppercase;
        font-size: 11px;
        font-weight: 800;
        letter-spacing: 2px;
        margin-bottom: 10px;
    }

    .hero-title {
        font-size: 34px;
        font-weight: 800;
        line-height: 1.2;
        color: var(--white);
        margin-bottom: 10px;
    }

    .hero-description {
        color: #BCC8D8;
        font-size: 14px;
        line-height: 1.7;
        max-width: 720px;
    }

    .section-label {
        color: var(--lime);
        text-transform: uppercase;
        font-size: 11px;
        font-weight: 800;
        letter-spacing: 1.5px;
        margin-top: 22px;
        margin-bottom: 12px;
    }

    [data-testid="stMetric"] {
        background: var(--surface);
        border: 1px solid var(--border);
        padding: 20px 22px;
        border-radius: 16px;
    }

    [data-testid="stMetricLabel"] {
        color: var(--muted) !important;
        font-size: 12px !important;
    }

    [data-testid="stMetricValue"] {
        color: var(--lime) !important;
        font-weight: 800 !important;
    }

    div[data-testid="stForm"],
    div[data-testid="stFileUploader"] {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 20px;
    }

        /* ===== Buttons: secondary by default; only primary is filled ===== */
        .stButton > button,
    .stFormSubmitButton > button,
    .stDownloadButton > button,
    .stLinkButton > a {
        background: rgba(255,255,255,0.06);
        color: var(--white);
        border: 1px solid rgba(255,255,255,0.28);
        border-radius: 10px;
        font-weight: 600;
        min-height: 40px;
        box-shadow: none;
        transition: background .15s ease, border-color .15s ease;
    }
    .stButton > button:hover,
    .stFormSubmitButton > button:hover,
    .stDownloadButton > button:hover,
    .stLinkButton > a:hover {
        background: rgba(255,255,255,0.10);
        border-color: rgba(255,255,255,0.40);
        color: var(--white);
    }
    .stButton > button p,
    .stFormSubmitButton > button p,
    .stDownloadButton > button p,
    .stLinkButton > a p {
        color: inherit !important;
        font-weight: 600 !important;
        margin: 0 !important;
    }

    /* Primary */
    .stButton > button[data-testid^="stBaseButton-primary"],
    .stFormSubmitButton > button[data-testid^="stBaseButton-primary"],
    .stDownloadButton > button[data-testid^="stBaseButton-primary"],
    .stLinkButton > a[data-testid^="stBaseLinkButton-primary"] {
        background: var(--lime);
        border-color: var(--lime);
        color: #10182A;
    }
    .stButton > button[data-testid^="stBaseButton-primary"]:hover,
    .stFormSubmitButton > button[data-testid^="stBaseButton-primary"]:hover,
    .stDownloadButton > button[data-testid^="stBaseButton-primary"]:hover,
    .stLinkButton > a[data-testid^="stBaseLinkButton-primary"]:hover {
        background: #C6F76B;
        border-color: #C6F76B;
        color: #10182A;
    }
    .stButton > button[data-testid^="stBaseButton-primary"] p,
    .stFormSubmitButton > button[data-testid^="stBaseButton-primary"] p,
    .stDownloadButton > button[data-testid^="stBaseButton-primary"] p {
        color: #10182A !important;
    }

    /* Tertiary: text only */
    .stButton > button[data-testid^="stBaseButton-tertiary"],
    .stFormSubmitButton > button[data-testid^="stBaseButton-tertiary"] {
        background: transparent;
        border-color: transparent;
        color: var(--muted);
    }
    .stButton > button[data-testid^="stBaseButton-tertiary"]:hover,
    .stFormSubmitButton > button[data-testid^="stBaseButton-tertiary"]:hover {
        background: rgba(255,255,255,0.05);
        border-color: transparent;
        color: var(--white);
    }


    .stButton > button:hover,
    .stFormSubmitButton > button:hover {
        background: var(--lime);
        color: #10182A;
        border: none;
    }


    .stProgress > div > div > div > div {
        background: var(--lime);
    }

    [data-testid="stDataFrame"] {
        border: 1px solid var(--border);
        border-radius: 12px;
        overflow: hidden;
    }

    div[data-baseweb="select"] > div,
    div[data-baseweb="input"] > div {
        background: #111B2D;
        border-color: var(--border);
    }

    [data-testid="stAlert"] {
        border-radius: 12px;
    }

    hr {
        border-color: var(--border);
    }

    .risk-card {
        background: var(--surface);
        padding: 22px;
        border: 1px solid var(--border);
        border-radius: 16px;
        min-height: 130px;
    }

    .risk-label {
        font-size: 12px;
        color: var(--muted);
        margin-bottom: 10px;
    }

    .risk-number {
        font-size: 29px;
        font-weight: 800;
        color: var(--lime);
    }

    .risk-note {
        color: var(--muted);
        font-size: 12px;
        margin-top: 6px;
    }
.st-key-brand_home button {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        padding: 0 !important;
        min-height: 0 !important;
        justify-content: flex-start !important;
    }

    .st-key-brand_home button p {
        font-size: 27px !important;
        font-weight: 800 !important;
        letter-spacing: -1px !important;
        color: var(--lime) !important;
        white-space: pre !important;
        margin: 0 !important;
    }

    .st-key-brand_home button p::before {
        content: "GYM";
        color: #F4F7FB;
    }

    .st-key-brand_home button p::after {
        content: " AI";
        color: #F4F7FB;
    }

    .st-key-brand_home button:hover p {
        opacity: 0.85;
    }[data-testid="stSidebar"],
    [data-testid="stSidebarCollapsedControl"],
    [data-testid="collapsedControl"] {
        display: none !important;
    }

    /* ---------- Compact page spacing ---------- */
    .block-container {
        padding-top: 1rem !important;
    }

    /* Style-only markdown blocks still take a 16px flex gap each, which
       stacks into a big empty band at the top. Take them out of the flow. */
    [data-testid="stElementContainer"]:has([data-testid="stMarkdownContainer"] > style:only-child) {
        display: none !important;
    }

    /* ---------- Top bar container ---------- */
    .st-key-top_nav {
        border-bottom: 1px solid var(--border);
        padding-bottom: 10px;
        margin-bottom: 18px;
    }

    /* ---------- Brand lockup: logo, wordmark and tagline ---------- */
    .st-key-top_nav [data-testid="stColumn"]:first-child [data-testid="stVerticalBlock"],
    .st-key-top_nav [data-testid="column"]:first-child [data-testid="stVerticalBlock"] {
        gap: 0 !important;
    }

    .nav-tagline {
        color: var(--muted) !important;
        font-size: 10px !important;
        line-height: 1.25 !important;
        margin: 2px 0 0 0 !important;
        padding: 0 !important;
        white-space: nowrap;
        letter-spacing: 0 !important;
    }

    .st-key-brand_home button:hover p {
        opacity: 1 !important;
    }

    /* ---------- Logo button: GYM (white) PULSE (lime) AI (white) ---------- */
    .st-key-brand_home button {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        padding: 0 !important;
        min-height: 0 !important;
        justify-content: flex-start !important;
    }

    .st-key-brand_home button p {
        font-size: 24px !important;
        font-weight: 800 !important;
        letter-spacing: -1px !important;
        line-height: 1.1 !important;
        color: var(--lime) !important;
        white-space: pre !important;
        margin: 0 !important;
    }

    .st-key-brand_home button p::before {
        content: "GYM";
        color: #F4F7FB;
    }

    .st-key-brand_home button p::after {
        content: " AI";
        color: #F4F7FB;
    }

    /* ---------- Navigation: blends with the background ---------- */
    .st-key-top_nav div[role="radiogroup"] {
        gap: 2px;
        flex-wrap: wrap;
    }

    .st-key-top_nav div[role="radiogroup"] label {
        background: transparent;
        border: none;
        border-bottom: 2px solid transparent;
        border-radius: 10px;
        padding: 8px 14px;
        cursor: pointer;
        transition: background 0.15s ease;
    }

    /* Hide the radio circle */
    .st-key-top_nav div[role="radiogroup"] label > div:first-child {
        display: none;
    }

    .st-key-top_nav div[role="radiogroup"] label p {
        font-size: 13px;
        font-weight: 700;
        color: var(--muted);
        margin: 0;
    }

    /* Current page: lime text with an underline */
    .st-key-top_nav div[role="radiogroup"] label:has(input:checked) {
        border-bottom: 2px solid var(--lime);
        border-radius: 10px 10px 0 0;
    }

    .st-key-top_nav div[role="radiogroup"] label:has(input:checked) p {
        color: var(--lime);
    }

    /* Hover: subtle neutral tint so the lime accent stays for the current page */
    .st-key-top_nav div[role="radiogroup"] label:hover {
        background: rgba(255,255,255,0.06) !important;
        border-radius: 10px;
    }

    .st-key-top_nav div[role="radiogroup"] label:hover p {
        color: var(--white) !important;
    }
    /* ---------- Landing page 2026 ---------- */
    .lp-hero {
        position: relative;
        display: grid;
        grid-template-columns: 1.1fr 0.9fr;
        gap: 36px;
        align-items: center;
        padding: 30px 6px 20px;
        overflow: hidden;
    }
    .lp-hero::before {
        content: "";
        position: absolute;
        width: 520px; height: 520px;
        top: -200px; left: -120px;
        background: radial-gradient(circle, rgba(183,243,74,0.22), transparent 65%);
        filter: blur(30px);
        pointer-events: none;
    }
    .lp-hero::after {
        content: "";
        position: absolute;
        width: 480px; height: 480px;
        bottom: -220px; right: -100px;
        background: radial-gradient(circle, rgba(53,214,237,0.20), transparent 65%);
        filter: blur(30px);
        pointer-events: none;
    }
    .lp-hero > * { position: relative; z-index: 1; }

    .lp-pill {
        display: inline-flex; align-items: center; gap: 8px;
        padding: 6px 14px 6px 10px;
        border-radius: 999px;
        border: 1px solid var(--border);
        background: rgba(255,255,255,0.04);
        backdrop-filter: blur(10px);
        color: var(--muted);
        font-size: 12px; font-weight: 600;
        margin-bottom: 20px;
    }
    .lp-dot {
        width: 8px; height: 8px; border-radius: 50%;
        background: var(--lime);
        animation: lp-pulse 1.8s infinite;
    }
    .lp-title {
        font-size: 58px; font-weight: 800;
        line-height: 1.04; letter-spacing: -2.5px;
        color: var(--white);
    }
    .lp-grad {
        background: linear-gradient(90deg, var(--lime), #35D6ED);
        -webkit-background-clip: text;
        background-clip: text;
        color: transparent;
    }
    .lp-sub {
        color: #BCC8D8; font-size: 16px; line-height: 1.7;
        max-width: 540px; margin: 20px 0 22px;
    }
    .lp-chips { display: flex; gap: 8px; flex-wrap: wrap; }
    .lp-chip {
        display: inline-flex; align-items: center; gap: 6px;
        font-size: 12px; color: var(--muted);
        padding: 6px 12px; border-radius: 999px;
        border: 1px solid var(--border);
        background: rgba(255,255,255,0.03);
    }
    .lp-chip svg { color: var(--lime); }

    /* Risk Radar preview */
    .lp-radar {
        background: rgba(21,29,48,0.75);
        backdrop-filter: blur(16px);
        border: 1px solid rgba(255,255,255,0.12);
        border-radius: 22px;
        padding: 20px;
        box-shadow: 0 30px 80px rgba(0,0,0,0.45), 0 0 0 1px rgba(183,243,74,0.05);
        animation: lp-float 6s ease-in-out infinite;
    }
    .lp-radar-head {
        display: flex; justify-content: space-between; align-items: center;
        margin-bottom: 6px;
    }
    .lp-radar-title { font-weight: 800; font-size: 15px; color: var(--white); }
    .lp-live {
        display: inline-flex; align-items: center; gap: 6px;
        font-size: 11px; font-weight: 700; color: var(--lime);
    }
    .lp-pulse-line { width: 100%; height: 54px; margin: 4px 0 8px; }
    .lp-pulse-line path {
        stroke-dasharray: 700; stroke-dashoffset: 700;
        animation: lp-dash 3.5s ease-out infinite;
    }
    .lp-row {
        display: flex; align-items: center; gap: 12px;
        padding: 11px 12px; margin-top: 8px;
        background: rgba(255,255,255,0.035);
        border: 1px solid var(--border);
        border-radius: 14px;
    }
    .lp-avatar {
        width: 34px; height: 34px; border-radius: 50%;
        display: grid; place-items: center;
        font-size: 12px; font-weight: 800; color: #10182A;
    }
    .lp-row-main { flex: 1; }
    .lp-row-name { font-size: 13px; font-weight: 700; color: var(--white); }
    .lp-row-sub { font-size: 11px; color: var(--muted); }
    .lp-risk {
        font-size: 11px; font-weight: 800;
        padding: 4px 10px; border-radius: 999px;
    }
    .lp-high { background: rgba(255,107,107,0.16); color: #FF7A7A; }
    .lp-med  { background: rgba(255,196,77,0.16);  color: #FFC44D; }
    .lp-low  { background: rgba(183,243,74,0.16);  color: var(--lime); }
    .lp-tiny {
        text-align: center; font-size: 10px; color: var(--muted);
        margin-top: 12px; letter-spacing: 1px;
    }

    /* Stat strip */
    .lp-stats {
        display: grid; grid-template-columns: repeat(4, 1fr);
        gap: 1px; background: var(--border);
        border: 1px solid var(--border);
        border-radius: 18px; overflow: hidden; margin: 18px 0 6px;
    }
    .lp-stat { background: var(--surface); padding: 18px; text-align: center; }
    .lp-stat b { display: block; font-size: 26px; color: var(--white); letter-spacing: -1px; }
    .lp-stat span { font-size: 12px; color: var(--muted); }

    /* Section headings */
    .lp-kicker {
        text-align: center; color: var(--lime);
        font-size: 11px; font-weight: 800; letter-spacing: 2.5px;
        text-transform: uppercase; margin: 76px 0 10px;
    }
    .lp-h2 {
        text-align: center; font-size: 38px; font-weight: 800;
        letter-spacing: -1.5px; line-height: 1.1; color: var(--white);
    }
    .lp-lead {
        text-align: center; color: var(--muted);
        font-size: 15px; line-height: 1.7;
        max-width: 600px; margin: 12px auto 34px;
    }

    /* Icon tile */
    .lp-ic {
        width: 44px; height: 44px; border-radius: 13px;
        display: grid; place-items: center; margin-bottom: 14px;
        color: var(--lime);
        background: linear-gradient(145deg, rgba(183,243,74,0.16), rgba(53,214,237,0.08));
        border: 1px solid rgba(183,243,74,0.25);
    }

    /* Fade-out visual */
    .lp-split {
        display: grid; grid-template-columns: 1fr 1fr; gap: 28px;
        align-items: center;
        background: var(--surface); border: 1px solid var(--border);
        border-radius: 24px; padding: 30px;
    }
    .lp-split h3 { font-size: 24px; letter-spacing: -0.5px; margin: 0 0 10px; }
    .lp-split p { color: var(--muted); font-size: 14px; line-height: 1.7; }
    .lp-bars {
        display: flex; align-items: flex-end; gap: 12px; height: 190px;
        padding: 0 6px; border-bottom: 1px solid var(--border);
    }
    .lp-bar-col { flex: 1; text-align: center; }
    .lp-bar-fill {
        border-radius: 8px 8px 0 0;
        background: linear-gradient(180deg, var(--lime), rgba(183,243,74,0.25));
        transform-origin: bottom;
        animation: lp-grow 1.2s ease-out both;
    }
    .lp-bar-fill.warn { background: linear-gradient(180deg, #FF8A5B, rgba(255,138,91,0.2)); }
    .lp-bar-lbl { font-size: 10px; color: var(--muted); margin-top: 6px; }
    .lp-bar-cap {
        font-size: 11px; color: var(--muted); text-align: center; margin-top: 10px;
    }

    /* Steps */
    .lp-steps {
        display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px;
        position: relative;
    }
    .lp-stepcard {
        background: var(--surface); border: 1px solid var(--border);
        border-radius: 20px; padding: 24px; position: relative;
    }
    .lp-num {
        position: absolute; top: 18px; right: 20px;
        font-size: 46px; font-weight: 800; letter-spacing: -2px;
        color: rgba(255,255,255,0.05);
    }
    .lp-stepcard h4, .lp-bento h4 {
        color: var(--white); font-size: 17px; font-weight: 800; margin: 0 0 6px;
    }
    .lp-stepcard p, .lp-bento p {
        color: var(--muted); font-size: 13px; line-height: 1.65; margin: 0;
    }

    /* Bento grid */
    .lp-bento-grid {
        display: grid; grid-template-columns: repeat(6, 1fr);
        gap: 16px;
    }
    .lp-bento {
        position: relative; overflow: hidden;
        background: var(--surface); border: 1px solid var(--border);
        border-radius: 22px; padding: 24px;
        transition: transform .25s ease, border-color .25s ease;
    }
    .lp-bento::after {
        content: ""; position: absolute; inset: 0;
        background: radial-gradient(circle at 100% 0%, rgba(183,243,74,0.10), transparent 55%);
        opacity: 0; transition: opacity .3s ease; pointer-events: none;
    }
    .lp-bento:hover { transform: translateY(-4px); border-color: rgba(183,243,74,0.5); }
    .lp-bento:hover::after { opacity: 1; }
    .b-4 { grid-column: span 4; }
    .b-3 { grid-column: span 3; }
    .b-2 { grid-column: span 2; }
    .lp-mini {
        display: flex; gap: 8px; margin-top: 16px; flex-wrap: wrap;
    }

    /* Transparency + CTA */
    .lp-note {
        max-width: 860px; margin: 0 auto;
        display: flex; gap: 18px; align-items: flex-start;
        background: var(--surface); border: 1px solid var(--border);
        border-radius: 22px; padding: 26px;
    }
    .lp-note h4 { color: var(--white); margin: 0 0 6px; font-size: 17px; }
    .lp-note p { color: #BCC8D8; margin: 0; font-size: 14px; line-height: 1.7; }
    .lp-note .lp-ic { margin: 0; flex-shrink: 0; color: var(--cyan);
        border-color: rgba(53,214,237,0.3);
        background: rgba(53,214,237,0.1); }

    .lp-cta {
        position: relative; overflow: hidden; text-align: center;
        margin: 70px 0 10px; padding: 64px 24px;
        border-radius: 28px; border: 1px solid rgba(183,243,74,0.25);
        background:
            radial-gradient(circle at 20% 0%, rgba(183,243,74,0.22), transparent 50%),
            radial-gradient(circle at 80% 100%, rgba(53,214,237,0.20), transparent 50%),
            #121B2E;
    }
    .lp-cta-title {
        font-size: 44px; font-weight: 800;
        letter-spacing: -2px; line-height: 1.08; color: var(--white);
    }
    .lp-cta p { color: var(--muted); margin: 14px 0 0; font-size: 15px; }
    .lp-arrow { display: inline-flex; vertical-align: middle; margin-left: 4px; }

    @keyframes lp-pulse {
        0% { box-shadow: 0 0 0 0 rgba(183,243,74,0.6); }
        100% { box-shadow: 0 0 0 10px rgba(183,243,74,0); }
    }
    @keyframes lp-float { 50% { transform: translateY(-8px); } }
    @keyframes lp-dash { to { stroke-dashoffset: 0; } }
    @keyframes lp-grow { from { transform: scaleY(0); } to { transform: scaleY(1); } }

    @media (max-width: 900px) {
        .lp-hero, .lp-split, .lp-steps { grid-template-columns: 1fr; }
        .lp-stats { grid-template-columns: repeat(2, 1fr); }
        .b-4, .b-3, .b-2 { grid-column: span 6; }
        .lp-title { font-size: 40px; }
        .lp-h2 { font-size: 28px; }
        .lp-cta-title { font-size: 30px; }
    }
    /* ---------- Auth card ---------- */
    .st-key-auth_card {
        background: rgba(21,29,48,0.85);
        backdrop-filter: blur(14px);
        border: 1px solid rgba(255,255,255,0.12) !important;
        border-radius: 22px !important;
        padding: 14px 10px !important;
        box-shadow: 0 30px 80px rgba(0,0,0,0.4);
    }

    .auth-title {
        font-size: 28px;
        font-weight: 800;
        letter-spacing: -1px;
        color: var(--white);
        text-align: center;
        margin: 4px 0 2px;
    }

    .auth-secure {
        text-align: center;
        color: var(--muted);
        font-size: 11px;
        margin-top: 14px;
    }

    /* "Don't have an account? Sign up" as one clickable button */
    .st-key-to_signup button,
    .st-key-to_login button {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        min-height: 0 !important;
        padding: 2px 0 !important;
        width: 100%;
        justify-content: center !important;
    }

    .st-key-to_signup button p,
    .st-key-to_login button p {
        color: var(--lime) !important;
        font-size: 14px !important;
        font-weight: 800 !important;
        margin: 0 !important;
        white-space: pre !important;
    }

    .st-key-to_signup button p::before {
        content: "Don't have an account?  ";
        color: var(--muted);
        font-weight: 500;
    }

    .st-key-to_login button p::before {
        content: "Already have an account?  ";
        color: var(--muted);
        font-weight: 500;
    }

    .st-key-to_signup button:hover p,
    .st-key-to_login button:hover p {
        text-decoration: underline;
    }
    .st-key-to_forgot button,
    .st-key-back_to_login button,
    .st-key-reset_other button,
    .st-key-open_terms button,
    .st-key-open_privacy button {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        min-height: 0 !important;
        padding: 2px 0 !important;
        width: 100%;
        justify-content: center !important;
    }

    .st-key-to_forgot button p,
    .st-key-back_to_login button p,
    .st-key-reset_other button p,
    .st-key-open_terms button p,
    .st-key-open_privacy button p {
        color: var(--muted) !important;
        font-size: 12px !important;
        font-weight: 600 !important;
        margin: 0 !important;
    }

    .st-key-to_forgot button:hover p,
    .st-key-back_to_login button:hover p,
    .st-key-reset_other button:hover p,
    .st-key-open_terms button:hover p,
    .st-key-open_privacy button:hover p {
        color: var(--lime) !important;
        text-decoration: underline;
    }
    .footer {
        text-align: center;
        color: var(--muted);
        font-size: 11px;
        padding: 20px 0;
    }

    /* ---------- Brand lockup: logo on top, then wordmark, then tagline ---------- */
    .brand-lockup {
        text-align: center;
        margin: 0 auto;
    }
    .brand-lockup-logo {
        display: block;
        width: 112px;
        height: auto;
        margin: 0 auto 14px auto;
    }
    .brand-lockup-word {
        font-size: 34px;
        line-height: 38px;
        font-weight: 800;
        letter-spacing: -1px;
        color: #F4F7FB;
    }
    .brand-lockup-word span {
        color: var(--lime);
    }
    .brand-lockup-tag {
        font-size: 13px;
        line-height: 20px;
        color: #BCC8D8;
        margin-top: 8px;
    }

    /* Same lockup, scaled down for the top bar */
    .nav-brand-logo {
        display: block;
        width: 52px;
        height: auto;
        margin: 0 auto 2px auto;
    }
    .st-key-top_nav .nav-brand-logo {
        margin-bottom: 6px;
    }
    .st-key-top_nav [data-testid="stColumn"]:first-child [data-testid="stMarkdownContainer"] {
        width: 100%;
        text-align: center;
    }
    .st-key-brand_home {
        width: 100%;
        padding-top: 10px;
    }
    .st-key-brand_home button {
        width: 100% !important;
        justify-content: center !important;
    }
    .st-key-brand_home button p {
        font-size: 24px !important;
        text-align: center;
    }
    .nav-tagline {
        color: #BCC8D8 !important;
        text-align: center;
        width: 100%;
    }
    .login-brand {
        text-align: center;
        width: 100%;
    }
    .login-brand-word {
        font-size: 24px;
        font-weight: 800;
        letter-spacing: -1px;
        line-height: 1.1;
        color: #F4F7FB;
        white-space: pre;
    }
    .login-brand-word span {
        color: var(--lime);
    }

    </style>
    """,
    unsafe_allow_html=True
)
gw.apply_mobile_styles()
gw.apply_ui_styles()
st.markdown("""
<style>
button, [role="radio"], label, a { touch-action: manipulation; -webkit-tap-highlight-color: transparent; }
@media (hover: none) {
    .stButton > button:hover, [class*="st-key-"] button:hover {
        transform: none !important; box-shadow: none !important;
    }
}
</style>
""", unsafe_allow_html=True)
st.markdown("""
<style>
html, body, .stApp,
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
.block-container {
    max-width: 100vw !important;
    overflow-x: hidden !important;
    overflow-x: clip !important;
    overscroll-behavior-x: none !important;
    touch-action: pan-y !important;
}

/* Let grid columns shrink instead of stretching the page */
.lp-hero { grid-template-columns: minmax(0, 1.1fr) minmax(0, 0.9fr); }
.lp-split { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.lp-steps { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.lp-stats { grid-template-columns: repeat(4, minmax(0, 1fr)); }
.lp-bento-grid { grid-template-columns: repeat(6, minmax(0, 1fr)); }
.lp-hero > *, .lp-split > *, .lp-steps > *, .lp-bento { min-width: 0; }

@media (max-width: 900px) {
    .lp-hero, .lp-split, .lp-steps { grid-template-columns: minmax(0, 1fr); }
    .lp-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 768px) {
    .block-container { padding-left: 1rem !important; padding-right: 1rem !important; }
    .lp-title { font-size: 36px; letter-spacing: -1.5px; word-break: break-word; }
    .lp-radar, .lp-note, .lp-cta { max-width: 100%; box-sizing: border-box; }
}
</style>
""", unsafe_allow_html=True)

# =========================================================
# BRAND LOGO HELPER (shared by the login page and the top bar)
# =========================================================
import base64
import io


@st.cache_resource
def logo_data_uri(width=256):
    """Return the logo mark as an inline image so it can sit inside HTML."""
    path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "GymPulse_AI_logo_mark.png"
    )
    try:
        img = Image.open(path).convert("RGBA")
        width = min(width, img.width)
        height = round(img.height * width / img.width)
        img = img.resize((width, height), Image.LANCZOS)
        buffer = io.BytesIO()
        img.save(buffer, format="PNG", optimize=True)
        return "data:image/png;base64," + base64.b64encode(
            buffer.getvalue()
        ).decode()
    except Exception:
        return ""


def logo_img_tag(css_class):
    uri = logo_data_uri()
    if not uri:
        return ""
    return f'<img class="{css_class}" src="{uri}" alt="GymPulse AI logo">'
@st.cache_resource
def lockup_data_uri(width=720, dark_text=False):
    """The full GymPulse AI logo (shapes + lettering) as an inline image.
    dark_text=True gives the light-mode version with navy lettering."""
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, "gympulse-logo-dark.png" if dark_text else "GymPulse_AI_logo_full.png")
    if not os.path.exists(path):
        # Fall back to the full lockup that ships with the repo
        path = os.path.join(base, "gympulse-email-logo.png")
    try:
        img = Image.open(path).convert("RGBA")
        width = min(width, img.width)
        height = round(img.height * width / img.width)
        img = img.convert("RGBa").resize((width, height), Image.LANCZOS).convert("RGBA")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG", optimize=True)
        return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
    except Exception:
        return ""


# =========================================================
# 3. USER AUTHENTICATION
# =========================================================

from datetime import datetime
from zoneinfo import ZoneInfo


# Connect to Supabase once per user session
if "supabase_client" not in st.session_state:
    st.session_state.supabase_client = gw.TrackedClient(
        create_client(
            st.secrets["SUPABASE_URL"],
            st.secrets["SUPABASE_KEY"]
        )
    )

supabase = st.session_state.supabase_client
_trainer_token = st.query_params.get("trainer")
if _trainer_token:
    gw.render_public_trainer(supabase, _trainer_token)
    st.stop()

# Public unsubscribe page for gyms' member emails (no sign-in needed)
if st.query_params.get("unsub"):
    import gympulse_campaigns as gcamp
    gd.apply()
    gcamp.render_unsubscribe(supabase, st.query_params.get("unsub"))
    st.stop()

# Member portal: each member's own page (private link), and the page to ask for a link
if st.query_params.get("me") or st.query_params.get("member"):
    import gympulse_portal as gportal
    gd.apply()
    if st.query_params.get("me"):
        gportal.render_portal(supabase, st.query_params.get("me"))
    else:
        gportal.render_login(supabase)
    st.stop()

# Public member sign-up page (the gym's link or QR code, no sign-in)
if st.query_params.get("join"):
    import gympulse_signup as gsign
    gd.apply()
    gsign.render_public(supabase, st.query_params.get("join"))
    st.stop()

# Public machine guide page (QR code on a machine, no sign-in)
if st.query_params.get("guide"):
    import gympulse_train as gtr
    gd.apply()
    gtr.render_guide(supabase, st.query_params.get("guide"))
    st.stop()

# Public HMO check-in page (the gym's HMO QR code, or a member's one-tap link, no sign-in)
if st.query_params.get("hmo"):
    import gympulse_hmo as ghmo
    gd.apply()
    ghmo.render_public(supabase, st.query_params.get("hmo"), st.query_params.get("t"))
    st.stop()

# Public happiness check answer page (one tap from the member's email, no sign-in)
if st.query_params.get("fb"):
    import gympulse_happy as ghappy
    gd.apply()
    ghappy.render_public(supabase, dict(st.query_params))
    st.stop()

# Public "Book a demo" page and its cancel link (no sign-in needed)
if st.query_params.get("demo") or st.query_params.get("demo_cancel"):
    import gympulse_booking as gb
    gd.apply()
    gb.render_router(supabase)
    st.stop()

# Paystack sends payers back here (?paystack=1&reference=...): check and apply the payment
if st.query_params.get("paystack") and (st.query_params.get("reference") or st.query_params.get("trxref")):
    gd.apply()
    gbill.render_return_page(dict(st.query_params))
    st.stop()

# Initialise login state
if "auth_user" not in st.session_state:
    st.session_state.auth_user = None

if "user_profile" not in st.session_state:
    st.session_state.user_profile = None

# ---------- Landing page helpers ----------

ICON_PATHS = {
    "pulse": '<path d="M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2"/>',
    "down": '<polyline points="22 17 13.5 8.5 8.5 13.5 2 7"/><polyline points="16 17 22 17 22 11"/>',
    "calendar": '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    "target": '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
    "user": '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    "users": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
    "upload": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" x2="12" y1="3" y2="15"/>',
    "gauge": '<path d="m12 14 4-4"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/>',
    "sliders": '<line x1="21" x2="14" y1="4" y2="4"/><line x1="10" x2="3" y1="4" y2="4"/><line x1="21" x2="12" y1="12" y2="12"/><line x1="8" x2="3" y1="12" y2="12"/><line x1="21" x2="16" y1="20" y2="20"/><line x1="12" x2="3" y1="20" y2="20"/><line x1="14" x2="14" y1="2" y2="6"/><line x1="8" x2="8" y1="10" y2="14"/><line x1="16" x2="16" y1="18" y2="22"/>',
    "chat": '<path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/>',
    "shield": '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
    "check": '<polyline points="20 6 9 17 4 12"/>',
    "arrow": '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/>',
}


def icon(name, size=22):
    """Return a thin-stroke SVG icon that inherits the current text color."""
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="1.75" '
        'stroke-linecap="round" stroke-linejoin="round">'
        f'{ICON_PATHS[name]}</svg>'
    )


def html(block):
    """Render an HTML block. Flattens it so Streamlit's Markdown never
    mistakes indented lines for a code block."""
    flat = " ".join(
        line.strip() for line in block.splitlines() if line.strip()
    )
    st.markdown(flat, unsafe_allow_html=True)


# Terms, Privacy Policy and Data Processing Agreement come from docs/legal/
show_terms, show_privacy, show_dpa = gl.show_terms, gl.show_privacy, gl.show_dpa


# Design system v2 sits on top of every earlier style layer
gd.apply()

# Show login and registration until authenticated
if st.session_state.auth_user is None:
    # -------------------------
    # GYMPULSE AI LOGIN BRANDING
    # -------------------------

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    LOGO_PATH = os.path.join(
        BASE_DIR,
        "GymPulse_AI_logo_mark.png"
    )

    # Landing: navigation, hero and live product preview
    html(gd.landing_top(lockup_data_uri(900), icon))
    if st.session_state.get("bill_flash"):
        (st.success if st.session_state.get("bill_flash_ok") else st.info)(
            st.session_state["bill_flash"] + " Sign in below to continue.")
    html("""
    <div class="lx-auth-head" id="get-started">
      <div class="lx-kicker">Your workspace</div>
      <div class="lx-h2" style="font-size:30px;margin-bottom:4px;">Sign in or start your 30-day free trial</div>
    </div>
    """)

    # -------------------------
    # AUTH FLOW
    # -------------------------

    if "auth_mode" not in st.session_state:
        st.session_state.auth_mode = "login"

    if "reset_email_sent" not in st.session_state:
        st.session_state.reset_email_sent = False

    if "reset_email" not in st.session_state:
        st.session_state.reset_email = ""

    if "password_updated" not in st.session_state:
        st.session_state.password_updated = False


    def set_auth_mode(mode):
        st.session_state.auth_mode = mode
        st.session_state.reset_email_sent = False

    def resend_block():
        pending = st.session_state.get("pending_confirm_email")
        if not pending:
            return
        if st.button(f"Resend confirmation email to {pending}",
                     key="resend_confirm", use_container_width=True):
            try:
                supabase.auth.resend({"type": "signup", "email": pending})
                st.success("Sent. Check your inbox and spam folder.")
            except Exception as error:
                if "rate" in str(error).lower():
                    st.error("Too many emails were sent to this address. Wait a few minutes and try again.")
                else:
                    st.error("Could not resend right now. Please try again shortly.")
    auth_col = gw.center("auth", 520)

    with auth_col:
        _who = st.segmented_control("Who is signing in?", ["Gym owner", "Member"], default="Gym owner",
                                    key="who_login", label_visibility="collapsed") or "Gym owner"
    if _who == "Member":
        with auth_col:
            import gympulse_portal as gportal
            gportal.render_code_login(supabase, embedded=True)
    else:
      with auth_col:
            with st.container(border=True, key="auth_card"):
    # ---------------- LOGIN PAGE ----------------
                if st.session_state.auth_mode == "login":

                    st.markdown(
                        '<div class="auth-title">Welcome back, sign in</div>',
                        unsafe_allow_html=True
                    )
                    _login_flash = st.session_state.pop("login_flash", None)
                    if _login_flash:
                        st.info(_login_flash)

                    if st.session_state.get("password_updated", False):
                        st.success("Password updated. Sign in with your new password.")
                    st.button(
                        "Sign up",
                        on_click=set_auth_mode,
                        args=("signup",),
                        key="to_signup"
                    )

                    with st.form("login_form", border=False):
                        login_email = st.text_input("Email address")
                        login_password = st.text_input("Password", type="password")

                        login_submitted = st.form_submit_button(
                            "Sign in with email",
                            type="primary",
                            use_container_width=True
                        )

                    st.button(
                        "Forgot password?",
                        on_click=set_auth_mode,
                        args=("forgot",),
                        key="to_forgot"
                    )

                    if login_submitted:
                        if not login_email or not login_password:
                            st.warning("Enter your email and password.")
                        else:
                            try:
                                result = supabase.auth.sign_in_with_password(
                                    {
                                        "email": login_email.strip(),
                                        "password": login_password
                                    }
                                )

                                if result.user:
                                    st.session_state.auth_user = {
                                        "id": str(result.user.id),
                                        "email": result.user.email
                                    }

                                    profile_result = (
                                        supabase.table("profiles")
                                        .select("*")
                                        .eq("id", str(result.user.id))
                                        .execute()
                                    )

                                    if profile_result.data:
                                        st.session_state.user_profile = profile_result.data[0]
                                        # Save the terms they accepted at sign-up (kept with their login)
                                        _legal = (result.user.user_metadata or {}).get("legal") or {}
                                        _prof = st.session_state.user_profile
                                        if _legal.get("version") == gl.LEGAL_VERSION and not gl.accepted(_prof):
                                            try:
                                                _s = {**dict(_prof.get("settings") or {}), "legal": _legal}
                                                supabase.table("profiles").update({"settings": _s}) \
                                                    .eq("id", str(result.user.id)).execute()
                                                _prof["settings"] = _s
                                            except Exception:
                                                pass
                                    else:
                                        meta = result.user.user_metadata or {}
                                        fallback = {
                                            "id": str(result.user.id),
                                            "full_name": meta.get("full_name") or "User",
                                            "business_name": meta.get("business_name") or "My Gym",
                                        }
                                        try:
                                            supabase.table("profiles").insert(fallback).execute()
                                        except Exception:
                                            pass
                                        st.session_state.user_profile = fallback

                                    gw.show_boot_overlay()
                                    st.rerun()

                            except Exception as error:
                                reason = str(error).lower()
                                if "not confirmed" in reason:
                                    st.session_state["pending_confirm_email"] = login_email.strip()
                                    st.warning("Your email isn't confirmed yet. Open the confirmation "
                                               "email (check spam), or resend it below.")
                                elif "rate" in reason:
                                    st.error("Too many attempts. Please wait a few minutes and try again.")
                                else:
                                    st.error("Wrong email or password. If you haven't registered yet, tap Sign up.")

                    resend_block()

                # ---------------- SIGNUP PAGE ----------------

                elif st.session_state.auth_mode == "signup":

                    st.markdown(
                        '<div class="auth-title">Create your free account</div>',
                        unsafe_allow_html=True
                    )

                    st.button(
                        "Back to sign in",
                        on_click=set_auth_mode,
                        args=("login",),
                        key="back_to_login_from_signup"
                    )

                    with st.form("signup_form", border=False):
                        full_name = st.text_input("Your full name")
                        business_name = st.text_input(
                            "Gym or company name",
                            placeholder="e.g. Nuelarch Gym"
                        )
                        signup_email = st.text_input("Email address", key="signup_email")
                        signup_password = st.text_input(
                            "Create password",
                            type="password",
                            key="signup_password"
                        )
                        confirm_password = st.text_input(
                            "Confirm password",
                            type="password"
                        )
                        agree = st.checkbox(
                            "I agree to the Terms of Service, Privacy Policy and Data Processing Agreement"
                        )
                        members_ok = st.checkbox(gl.CONSENT_TEXT)

                        signup_submitted = st.form_submit_button(
                            "Create free account",
                            type="primary",
                            use_container_width=True
                        )

                    if signup_submitted:
                        if not all([
                            full_name.strip(),
                            business_name.strip(),
                            signup_email.strip(),
                            signup_password,
                            confirm_password
                        ]):
                            st.warning("Please complete every field.")
                        elif not agree or not members_ok:
                            st.warning(
                                "Please tick both boxes: the terms, and that you have your members' permission."
                            )
                        elif signup_password != confirm_password:
                            st.error("Your passwords do not match.")
                        elif len(signup_password) < 8:
                            st.warning("Your password must contain at least 8 characters.")
                        else:
                            try:
                                result = supabase.auth.sign_up(
                                    {
                                        "email": signup_email.strip(),
                                        "password": signup_password,
                                        "options": {
                                            "email_redirect_to": "https://usegympulseai.com",
                                            "data": {
                                                "full_name": full_name.strip(),
                                                "business_name": business_name.strip(),
                                                "account_type": "gym_owner",
                                                "legal": gl.acceptance(signup_email.strip())
                                            }
                                        }
                                    }
                                )

                                if result.session and result.user:
                                    st.session_state.auth_user = {
                                        "id": str(result.user.id),
                                        "email": result.user.email
                                    }

                                    profile_result = (
                                        supabase.table("profiles")
                                        .select("*")
                                        .eq("id", str(result.user.id))
                                        .execute()
                                    )

                                    if profile_result.data:
                                        st.session_state.user_profile = profile_result.data[0]
                                    else:
                                        st.session_state.user_profile = {
                                            "full_name": full_name.strip(),
                                            "business_name": business_name.strip()
                                        }

                                    gw.show_boot_overlay()
                                    st.rerun()

                                else:
                                    if result.user and not (result.user.identities or []):
                                        st.error("This email is already registered. Sign in instead, "
                                                 "or tap Forgot password.")
                                    else:
                                        st.session_state["pending_confirm_email"] = signup_email.strip()
                                        st.success("Registration submitted! Check your email (and spam) "
                                                   "for the confirmation link, then come back and sign in.")

                            except Exception as error:
                                reason = str(error).lower()
                                if "rate" in reason:
                                    st.session_state["pending_confirm_email"] = signup_email.strip()
                                    st.error("Several emails were sent to this address recently. "
                                             "Wait a few minutes, then tap Resend below.")
                                elif "already" in reason:
                                    st.error("This email is already registered. Sign in instead.")
                                st.error("Registration failed. Please check your details and try again.")

                    resend_block()

                # ---------------- FORGOT PASSWORD PAGE ----------------

                elif st.session_state.auth_mode == "forgot":

                    st.button(
                        "Back to sign in",
                        on_click=set_auth_mode,
                        args=("login",),
                        key="back_to_login_from_forgot"
                    )

                    st.markdown(
                        '<div class="auth-title">Reset your password</div>',
                        unsafe_allow_html=True
                    )

                    st.markdown(
                        """
                        <div style="margin-bottom: 12px;">
                            To reset your password, enter your registered email address below.
                            We will send an OTP to this email for password reset.
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

                    if not st.session_state.get("reset_email_sent", False):
                        with st.form("reset_request_form", border=False):
                            reset_email = st.text_input("Email address")
                            send_code = st.form_submit_button(
                                "Send reset code",
                                type="primary",
                                use_container_width=True
                            )

                        if send_code:
                            if not reset_email.strip():
                                st.warning("Enter your email address.")
                            else:
                                try:
                                    supabase.auth.reset_password_for_email(reset_email.strip())
                                except Exception:
                                    pass

                                st.session_state.reset_email = reset_email.strip()
                                st.session_state.reset_email_sent = True
                                st.rerun()

                    else:
                        st.info(
                            f"If an account exists for {st.session_state.reset_email}, "
                            "a 6-digit code is on its way. Check your spam folder too."
                        )

                        with st.form("reset_confirm_form", border=False):
                            reset_code = st.text_input("6-digit code")
                            new_password = st.text_input(
                                "New password",
                                type="password"
                            )
                            confirm_new = st.text_input(
                                "Confirm new password",
                                type="password"
                            )

                            reset_submitted = st.form_submit_button(
                                "Update password",
                                type="primary",
                                use_container_width=True
                            )

                        if reset_submitted:
                            if not reset_code.strip() or not new_password:
                                st.warning("Please complete every field.")
                            elif new_password != confirm_new:
                                st.error("Your passwords do not match.")
                            elif len(new_password) < 8:
                                st.warning(
                                    "Your password must contain at least 8 characters."
                                )
                            else:
                                try:
                                    supabase.auth.verify_otp(
                                        {
                                            "email": st.session_state.reset_email,
                                            "token": reset_code.strip(),
                                            "type": "recovery"
                                        }
                                    )
                                except Exception:
                                    st.error("That code is invalid or has expired. Request a new one and try again.")
                                else:
                                    try:
                                        supabase.auth.update_user({"password": new_password})
                                        supabase.auth.sign_out()
                                    except Exception as e:
                                        reason = str(e).lower()
                                        if "different from the old" in reason:
                                            st.error("Your new password must be different from your current one.")
                                        elif "password" in reason:
                                            st.error("That password was not accepted. Try a longer one with letters and numbers.")
                                        else:
                                            st.error("Your code worked, but the new password could not be saved. Please try again.")
                                    else:
                                        st.session_state.reset_email_sent = False
                                        st.session_state.auth_mode = "login"
                                        st.session_state.password_updated = True
                                        st.rerun()
                # ---------------- LEGAL LINKS ----------------
                st.markdown(
                    '<div class="auth-secure">'
                    "Secure sign-in. Your password is never stored in plain text."
                    "</div>",
                    unsafe_allow_html=True
                )

                legal_a, legal_b, legal_c = st.columns(3)

                with legal_a:
                    if st.button("Terms of Service", key="open_terms"):
                        show_terms()

                with legal_b:
                    if st.button("Privacy Policy", key="open_privacy"):
                        show_privacy()

                with legal_c:
                    if st.button("Data Processing Agreement", key="open_dpa"):
                        show_dpa()

    # LANDING PAGE SECTIONS (pricing goes just before the closing call to action)
    _sections = gd.landing_sections(icon, gw.ARCHIE_BOT_SVG)
    _cut = _sections.index('<div class="lx-cta">')
    html(_sections[:_cut])
    try:
        gbill.render_landing_pricing(icon)
    except Exception as _price_error:
        gmon.capture(_price_error, "landing pricing")
    html(_sections[_cut:])
    st.session_state["_rendered_page"] = "__landing__"
    st.stop()

# =========================================================
# 4. PERSONALIZED WORKSPACE HEADER
# =========================================================
if st.session_state.auth_user is None:
    st.stop()
profile = st.session_state.user_profile or {}
if "theme" not in st.session_state:
    st.session_state["theme"] = profile.get("theme") or "dark"
gw.apply_theme(st.session_state["theme"])
user_name = profile.get("full_name", "User")
business_name = profile.get("business_name", "My Gym")

owner_id = st.session_state.auth_user["id"]

# Keep the Supabase login alive: get_session() renews an expired access token
# (they last about an hour), so queries keep running as this owner.
_session = None
try:
    _session = supabase.auth.get_session()
except Exception:
    _session = None
_session_lost = False


def _auth_error(error):
    text = str(error).lower()
    return any(k in text for k in ("42501", "row-level security", "jwt", "pgrst301", "pgrst303", "invalid token"))


try:
    # Retrieve the gym belonging to the authenticated owner
    gym_rows = gw.cached(
        ("gym", owner_id),
        lambda: (
            supabase.table("gyms")
            .select("*")
            .eq("owner_id", owner_id)
            .limit(1)
            .execute()
            .data or []
        ),
        ttl=600,
        skip_empty=True
    )

    # An empty answer can mean the login has lapsed, not that there's no gym:
    # renew the session and ask again before creating anything.
    if not gym_rows:
        try:
            supabase.auth.refresh_session()
        except Exception:
            pass
        try:
            gym_rows = (supabase.table("gyms").select("*").eq("owner_id", owner_id)
                        .limit(1).execute().data or [])
        except Exception as error:
            if _auth_error(error):
                _session_lost = True
            gym_rows = []
    if not gym_rows and _session is None and not _session_lost:
        try:
            _session_lost = supabase.auth.get_session() is None and bool(
                st.session_state.get("_had_gym"))
        except Exception:
            pass
    if _session_lost:
        raise PermissionError("session expired")

    # A staff login works in their owner's gym (sql/phase13_staff.sql)
    _staff_ctx = None
    if not gym_rows:
        _staff_ctx = gteam.staff_context(supabase)

    # Create a workspace if this owner does not have one
    if gym_rows:
        gym = gym_rows[0]
        st.session_state["_had_gym"] = True
        st.session_state["role"] = "owner"

    elif _staff_ctx:
        if (_staff_ctx.get("staff") or {}).get("status") != "active":
            gd.apply()
            st.warning("Your access to this gym on GymPulse AI is switched off. Please speak to the gym owner.")
            if st.button("Sign out"):
                for _k in list(st.session_state.keys()):
                    del st.session_state[_k]
                st.rerun()
            st.stop()
        gym = _staff_ctx["gym"]
        st.session_state["_had_gym"] = True
        if st.session_state.get("role") != "staff":
            gteam.enter_staff_mode(_staff_ctx, st.session_state.get("user_profile"))
        gteam.touch_last_seen()

    else:
        new_gym = (
            supabase.table("gyms")
            .insert({
                "owner_id": owner_id,
                "business_name": business_name.strip() or "My Gym"
            })
            .execute()
        )

        if not new_gym.data:
            raise RuntimeError(
                "The gym workspace could not be created."
            )

        gym = new_gym.data[0]

    # Save the workspace information for the current session
    st.session_state.gym_id = gym["id"]
    business_name = gym["business_name"]
    if gteam.is_staff():
        user_name = gteam.staff_name()
        profile = st.session_state.user_profile or {}

except Exception as error:
    st.session_state.gym_id = None
    if not (isinstance(error, PermissionError) or _auth_error(error)):
        gmon.capture(error, "load gym workspace")

    if isinstance(error, PermissionError) or _auth_error(error):
        # The login lapsed: sign in again instead of showing a database error.
        for _k in list(st.session_state.keys()):
            del st.session_state[_k]
        st.session_state["login_flash"] = "Your session expired. Please sign in again."
        st.rerun()

    st.error(
        "We couldn't load your gym workspace. "
        "Please try refreshing the page."
    )

    with st.expander("Technical details"):
        st.code(str(error))

    st.stop()
# =========================================================
# 5. MODEL PREDICTION FUNCTIONS
# =========================================================
# =========================================================
# MODEL INITIALIZATION
# =========================================================

import numpy as np

from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression

@st.cache_resource
def load_model():
    """Demonstration model trained on simulated members."""
    rng = np.random.default_rng(42)
    n = 4000
    plan = rng.choice(["Monthly", "Quarterly", "Annual"], size=n, p=[0.55, 0.25, 0.20])
    base = rng.integers(0, 21, n)
    gap = 30 / np.maximum(base, 1)
    lapsing = rng.random(n) < 0.22
    days = np.where(lapsing, rng.integers(7, 60, n),
                    np.minimum(rng.exponential(gap), 45)).astype(int)
    recent = np.where(lapsing, np.maximum(0, base - rng.integers(3, 15, n)),
                      np.clip(base + rng.integers(-3, 4, n), 0, 20))
    change = recent - base
    renew = rng.integers(0, 91, n)
    pt = rng.integers(0, 13, n)

    z = (-2.5 + 0.10 * days - 0.11 * change - 0.12 * pt - 0.04 * renew
         + np.where(plan == "Monthly", 0.5, 0)
         + np.where(plan == "Annual", -0.4, 0)
         + rng.normal(0, 0.6, n))
    label = (rng.random(n) < 1 / (1 + np.exp(-z))).astype(int)

    training_data = pd.DataFrame({
        "membership_type": plan,
        "days_since_last_visit": days,
        "attendance_change": change,
        "renewal_due_days": renew,
        "pt_sessions_attended": pt,
    })
    preprocessing = ColumnTransformer([
        ("membership", OneHotEncoder(handle_unknown="ignore"), ["membership_type"]),
        ("numeric", StandardScaler(), ["days_since_last_visit", "attendance_change",
                                       "renewal_due_days", "pt_sessions_attended"]),
    ])
    pipeline = Pipeline([
        ("preprocessing", preprocessing),
        ("classifier", LogisticRegression(max_iter=1000)),
    ])
    pipeline.fit(training_data, label)
    return pipeline



model = load_model()
def prepare_member_data(data):
    """Validate member records and prepare model features."""

    data = data.copy()

    required_columns = [
        "membership_type",
        "days_since_last_visit",
        "visits_previous_30_days",
        "visits_last_30_days",
        "renewal_due_days",
        "pt_sessions_attended"
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in data.columns
    ]

    if missing_columns:
        raise ValueError(
            "Missing required columns: "
            + ", ".join(missing_columns)
        )

    numeric_columns = [
        "days_since_last_visit",
        "visits_previous_30_days",
        "visits_last_30_days",
        "renewal_due_days",
        "pt_sessions_attended"
    ]

    for column in numeric_columns:
        data[column] = pd.to_numeric(
            data[column],
            errors="raise"
        )

        if data[column].isna().any():
            raise ValueError(
                f"{column} contains missing values."
            )

        if (data[column] < 0).any():
            raise ValueError(
                f"{column} cannot contain negative values."
            )

    if not data["membership_type"].isin(
        ["Monthly", "Quarterly", "Annual"]
    ).all():
        raise ValueError(
            "Membership type must be Monthly, Quarterly, or Annual."
        )

    data["attendance_change"] = (
        data["visits_last_30_days"]
        - data["visits_previous_30_days"]
    )

    model_features = [
        "membership_type",
        "days_since_last_visit",
        "attendance_change",
        "renewal_due_days",
        "pt_sessions_attended"
    ]

    return data[model_features]

def assess_members(data):
    """Generate cancellation probabilities and provisional risk labels."""

    if data.empty:
        raise ValueError("The uploaded dataset contains no members.")

    # Score every plan on the three plan types the model was trained on
    features = prepare_member_data(
        data.assign(membership_type=data["membership_type"].map(gw.model_plan)))

    probabilities = model.predict_proba(features)[:, 1]

    results = data.copy()

    results["cancellation_probability"] = probabilities

    results["risk_category"] = [
        "High" if probability >= 0.50
        else "Medium" if probability >= 0.30
        else "Low"
        for probability in probabilities
    ]

    return results


# =========================================================
# 6. BRANDING AND SIDEBAR
# =========================================================

# Handle dashboard navigation before creating the sidebar widget
MAIN_PAGES = [
    "Dashboard",
    "Risk Radar",
    "Action Centre",
    "Payments & Renewals",
    "Business Insights",
    "Grow",
    "Archie",
    "Member Management",
    "Community",
    "Check-in",
]

MORE_PAGES = [
    "Follow-ups",
    "Subscription",
    "FAQs",
]
if gteam.is_staff():
    MAIN_PAGES = [p for p in MAIN_PAGES if p not in gteam.OWNER_ONLY]
    MORE_PAGES = [p for p in MORE_PAGES if p not in gteam.OWNER_ONLY]
else:
    MAIN_PAGES = ["Owner" if p == "Business Insights" else p for p in MAIN_PAGES]
import gympulse_admin as gadm
if gadm.is_admin():
    MORE_PAGES.append("Admin")

NAV_SHORT = {
    "Payments & Renewals": "Renewals",
    "Business Insights": "Insights",
    "Member Management": "Members",
    "Owner": "Owner",
}

if "current_page" not in st.session_state:
    # Every sign-in starts on the Dashboard, not on the page saved in the
    # address bar from the last visit.
    st.session_state["current_page"] = "Dashboard"
    if st.query_params.get("p") == "Subscription":        # "Renew now" links in emails
        st.session_state["current_page"] = "Subscription"
    try:
        if st.query_params.get("p"):
            del st.query_params["p"]
    except Exception:
        pass

def _is_mobile():
    try:
        ua = st.context.headers.get("User-Agent", "").lower()
    except Exception:
        return False
    return any(w in ua for w in ("iphone", "android", "ipad", "mobile"))
def show_page(name):
    """Open a page and keep the top-bar radio in sync."""
    _cur = st.session_state.get("current_page")
    if _cur and _cur != name:
        _h = st.session_state.setdefault("nav_hist", [])
        _h.append(_cur)
        del _h[:-15]
    st.session_state["current_page"] = name
    

def on_main_nav():
    cur = st.session_state.get("current_page")
    choice = st.session_state.get(f"main_nav_{cur}")
    if choice and choice != cur:
        _h = st.session_state.setdefault("nav_hist", [])
        _h.append(cur)
        del _h[:-15]
        st.session_state["current_page"] = choice


def go_back():
    _h = st.session_state.get("nav_hist", [])
    if _h:
        st.session_state["current_page"] = _h.pop()

def go_home():
    show_page("Dashboard")
def log_out():
    """End the Supabase session and return to the login page."""
    try:
        supabase.auth.sign_out()
    except Exception:
        pass

    for key in list(st.session_state.keys()):
        del st.session_state[key]

    try:
        st.query_params.clear()
    except Exception:
        pass

# Dashboard buttons still set "navigate_to"
if "navigate_to" in st.session_state:
    show_page(st.session_state.pop("navigate_to"))


def _unread_now():
    gid = st.session_state.get("gym_id")
    if not gid:
        return None
    return gw.cached(("unread", gid),
                     lambda: fu.unread_count(supabase, gid), ttl=20)



def _notify_replies(count):
    try:
        st.toast(f"{count} new repl{'y' if count == 1 else 'ies'} from your members")
    except Exception:
        pass


unread_replies = _unread_now() or 0
if unread_replies > st.session_state.get("last_unread", 0):
    _notify_replies(unread_replies)
st.session_state["last_unread"] = unread_replies


def nav_label(name):
    if name == "Follow-ups" and unread_replies:
        return f"{name} ({unread_replies})"
    return NAV_SHORT.get(name, name)


st.markdown("""
<style>
    /* ---------- TYMS STYLE NAV ---------- */
    /* 1. Hide the default radio circle */
    .st-key-top_nav div[role="radiogroup"] label > div:first-child {
        display: none !important;
    }
    
    /* 2. Style the nav links as pills */
    .st-key-top_nav div[role="radiogroup"] label {
        padding: 8px 12px !important;
        margin: 0 2px !important;
        background: transparent !important;
        border-radius: 20px !important; 
        border: none !important;
        transition: all 0.2s ease !important;
    }

    /* 3. The text styling */
    .st-key-top_nav div[role="radiogroup"] label p {
        color: var(--muted) !important;
        font-size: 14px !important;
        font-weight: 600 !important;
    }

    /* 4. Hover effect */
    .st-key-top_nav div[role="radiogroup"] label:hover {
        background: rgba(255,255,255,0.08) !important;
    }
    .st-key-top_nav div[role="radiogroup"] label:hover p {
        color: var(--white) !important;
    }

    /* 5. Active state */
    .st-key-top_nav div[role="radiogroup"] label:has(input:checked) {
        background: rgba(183,243,74,0.15) !important; 
    }
    .st-key-top_nav div[role="radiogroup"] label:has(input:checked) p {
        color: var(--lime) !important; 
    }
    
    /* 6. Clean mobile hamburger button */
    .mobile-menu-btn button {
        background: transparent !important;
        border: none !important;
        color: var(--white) !important;
        font-size: 24px !important;
        padding: 0 !important;
        box-shadow: none !important;
    }
    .mobile-menu-btn button:hover {
        color: var(--lime) !important;
        background: transparent !important;
    }
</style>
""", unsafe_allow_html=True)
# --- NAVIGATION CSS ---
st.markdown("""
<style>
/* --- LAPTOP VIEW --- */
@media (min-width: 769px) {
    /* Hide mobile hamburger and desktop More menu */
    .mobile-menu-btn,
    .st-key-mobile_menu_btn,
    .st-key-desktop-more {
        display: none !important;
    }
}
    
    /* Force everything onto one line */
    .st-key-top_nav div[role="radiogroup"] {
        flex-wrap: nowrap !important;
        white-space: nowrap !important;
        gap: 4px !important; /* Tight spacing */
    }
    
    /* Hide the circles */
    .st-key-top_nav div[role="radiogroup"] label > div:first-child {
        display: none !important;
    }
    
    /* Style the text as pills */
    .st-key-top_nav div[role="radiogroup"] label {
        padding: 6px 10px !important;
        margin: 0 !important;
        border-radius: 20px !important;
        background: transparent !important;
        border: none !important;
    }
    
    .st-key-top_nav div[role="radiogroup"] label p {
        color: var(--muted) !important;
        font-size: 13px !important; /* Slightly smaller to fit 8 items */
        font-weight: 600 !important;
    }
    
    .st-key-top_nav div[role="radiogroup"] label:hover {
        background: rgba(255,255,255,0.08) !important;
    }
    .st-key-top_nav div[role="radiogroup"] label:hover p {
        color: var(--white) !important;
    }
    
    /* Active pill */
    .st-key-top_nav div[role="radiogroup"] label:has(input:checked) {
        background: rgba(183,243,74,0.15) !important;
    }
    .st-key-top_nav div[role="radiogroup"] label:has(input:checked) p {
        color: var(--lime) !important;
    }
}

/* --- MOBILE VIEW --- */
@media (max-width: 768px) {

    /* Hide desktop navigation and More menu */
    .st-key-top_nav div[role="radiogroup"] {
        display: none !important;
    }

    .st-key-top_nav .st-key-desktop-more {
        display: none !important;
    }

    /* Hide desktop Log Out outside the hamburger */
    .st-key-logout_button_main {
        display: none !important;
    }

    /* Show the hamburger menu */
    .st-key-mobile_menu_btn,
    .mobile-menu-btn {
        display: block !important;
        text-align: right;
    }

    .st-key-mobile_menu_btn button,
    .mobile-menu-btn button {
        background: transparent !important;
        border: none !important;
        color: var(--white) !important;
        font-size: 24px !important;
        padding: 0 !important;
        box-shadow: none !important;
    }

    .st-key-mobile_menu_btn button:hover,
    .mobile-menu-btn button:hover {
        color: var(--lime) !important;
    }

    /* Prevent horizontal scrolling on mobile */
    html,
    body,
    .stApp,
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"],
    section.main {
        max-width: 100% !important;
        overflow-x: hidden !important;
    }

    /* Keep columns and media within the screen */
    [data-testid="stHorizontalBlock"] {
        max-width: 100% !important;
    }

    img,
    video,
    iframe {
        max-width: 100% !important;
    }
}
</style>
""", unsafe_allow_html=True)

# --- TOP NAV CONTAINER ---
# --- NAVIGATION CSS & LOGIC ---
st.markdown("""
<style>

/* =====================================
   DESKTOP / LAPTOP
   ===================================== */

@media (min-width: 769px) {

    .custom-nav {
        display: flex !important;
        flex-wrap: nowrap !important;
        align-items: center !important;
        justify-content: flex-start !important;
        gap: 2px !important;
        width: 100% !important;
        white-space: nowrap !important;
    }

    .custom-nav a {
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        color: var(--muted) !important;
        text-decoration: none !important;
        font-size: 12px !important;
        font-weight: 600 !important;
        padding: 6px 5px !important;
        border-radius: 20px;
        white-space: nowrap !important;
        flex-shrink: 0 !important;
        transition: all 0.2s ease;
    }

    .custom-nav a:hover {
        background: rgba(255,255,255,0.08);
        color: var(--white) !important;
    }

    .custom-nav a.active {
        background: rgba(183,243,74,0.15);
        color: var(--lime) !important;
    }

    .mobile-menu-btn {
        display: none !important;
    }

    .st-key-logout_button_main button {
        min-width: 85px !important;
        white-space: nowrap !important;
    }

}

/* =====================================
   MOBILE
   ===================================== */

@media (max-width: 768px) {

    /* Hide desktop navigation */
    .custom-nav {
        display: none !important;
    }

    /* Hide desktop More popover */
    .st-key-desktop-more {
        display: none !important;
    }

    /* Hide the desktop navigation column */
    .st-key-top_nav [data-testid="stHorizontalBlock"]
    > [data-testid="stColumn"]:nth-child(2) {
        display: none !important;
    }

    /* Keep logo and action controls visible */
    .st-key-top_nav [data-testid="stHorizontalBlock"] {
        align-items: center !important;
        gap: 8px !important;
    }

    .st-key-top_nav [data-testid="stHorizontalBlock"]
    > [data-testid="stColumn"]:first-child {
        flex: 1 1 auto !important;
        min-width: 0 !important;
    }

    .st-key-top_nav [data-testid="stHorizontalBlock"]
    > [data-testid="stColumn"]:last-child {
        flex: 0 0 auto !important;
        min-width: 0 !important;
    }

    /* Hamburger */
    .mobile-menu-btn {
        display: block !important;
    }

    .mobile-menu-btn button {
        background: transparent !important;
        border: none !important;
        color: var(--white) !important;
        font-size: 25px !important;
        padding: 4px 8px !important;
        min-height: 36px !important;
        box-shadow: none !important;
    }

    .mobile-menu-btn button:hover {
        color: var(--lime) !important;
    }

    /* Compact logout */
    .st-key-logout_button_main button {
        min-width: 0 !important;
        width: auto !important;
        min-height: 36px !important;
        padding: 0 10px !important;
        font-size: 12px !important;
        white-space: nowrap !important;
    }

}

</style>
""", unsafe_allow_html=True)
st.markdown("""
<style>
/* ================= TOP BAR ================= */

/* ---------- Laptop: logo | 7 pages | Log Out | hamburger ---------- */
@media (min-width: 769px) {
    .st-key-top_nav [data-testid="stHorizontalBlock"] {
        flex-wrap: nowrap !important;
        align-items: center !important;
        gap: 10px !important;
    }
    .st-key-top_nav [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(1) {
        flex: 0 0 190px !important; width: 190px !important; min-width: 190px !important;
    }
    .st-key-top_nav [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(2) {
        flex: 1 1 0 !important; width: auto !important; min-width: 0 !important;
    }
    .st-key-top_nav [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(3) {
        flex: 0 0 90px !important; width: 90px !important; min-width: 90px !important;
    }
    .st-key-top_nav [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(4) {
        flex: 0 0 52px !important; width: 52px !important; min-width: 52px !important;
    }

    /* Page links shrink a little on smaller laptops so all 7 always fit */
    .st-key-top_nav [data-testid="stRadio"] { width: 100% !important; }
    .st-key-top_nav div[role="radiogroup"] {
        flex-wrap: nowrap !important;
        gap: 2px !important;
        justify-content: flex-start !important;
    }
    .st-key-top_nav div[role="radiogroup"] label {
        margin: 0 !important;
        padding: 6px clamp(4px, 0.5vw, 10px) !important;
        white-space: nowrap !important;
    }
    .st-key-top_nav div[role="radiogroup"] label p {
        font-size: clamp(10px, 0.85vw, 13px) !important;
        white-space: nowrap !important;
    }

    /* Page list inside the hamburger is mobile only */
    .st-key-pop_main, .st-key-pop_logout { display: none !important; }
}

/* ---------- Phone: logo + tagline on the left, hamburger on the right ---------- */
@media (max-width: 768px) {
    .st-key-top_nav [data-testid="stHorizontalBlock"] {
        flex-wrap: nowrap !important;
        align-items: center !important;
        gap: 8px !important;
    }
    .st-key-top_nav [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(2),
    .st-key-top_nav [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(3) {
        display: none !important;
    }
    .st-key-top_nav [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(1) {
        flex: 1 1 auto !important; width: auto !important; min-width: 0 !important;
    }
    .st-key-top_nav [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(4) {
        flex: 0 0 auto !important; width: auto !important; min-width: 0 !important;
    }
    .st-key-top_nav .nav-tagline { font-size: 9px !important; }
}

/* ---------- Logo and tagline (both screens) ---------- */
.st-key-top_nav .nav-brand-logo { display: block !important; width: 40px !important; }
.st-key-top_nav .nav-tagline {
    display: block !important;
    white-space: normal !important;
    font-size: 10px;
    line-height: 1.25 !important;
    text-align: center;
    margin: 2px auto 0 auto !important;
}
.pop-logo { display: none !important; }

/* ---------- Hamburger button, top right ---------- */
.st-key-top_menu { display: flex; justify-content: flex-end; }
.st-key-top_menu button {
    background: rgba(255,255,255,0.06) !important;
    border: 1px solid var(--border) !important;
    border-radius: 10px !important;
    min-height: 38px !important;
    padding: 0 12px !important;
    box-shadow: none !important;
}
.st-key-top_menu button p {
    color: var(--white) !important;
    font-size: 20px !important;
    font-weight: 700 !important;
    margin: 0 !important;
}
.st-key-top_menu button:hover { border-color: var(--lime) !important; }
.st-key-top_menu button:hover p { color: var(--lime) !important; }
.st-key-top_menu [data-testid="stIconMaterial"] { display: none !important; }

/* ---------- Remove the red focus ring after a tap ---------- */
.stButton > button:focus,
.stButton > button:focus-visible,
.stButton > button:active,
[data-testid="stPopover"] button:focus,
[data-testid="stPopover"] button:focus-visible,
[data-testid="stPopover"] button:active {
    outline: none !important;
    box-shadow: none !important;
    border-color: transparent !important;
}
</style>
""", unsafe_allow_html=True) 
def toggle_theme():
    new = "light" if st.session_state.get("theme", "dark") == "dark" else "dark"
    st.session_state["theme"] = new
    try:
        (supabase.table("profiles").update({"theme": new})
         .eq("id", st.session_state.auth_user["id"]).execute())
    except Exception:
        pass


def open_settings(section):
    st.session_state["settings_section"] = section
    show_page("Settings")


_av = profile.get("avatar")
_av_src = _av if gw.has_photo(_av) else gw._user_avatar(user_name)

st.markdown(f"""
<style>
.st-key-top_profile button::before {{
    content: ""; display: block;
    background: #10182A url('{_av_src}') center/contain no-repeat;
}}
</style>
""", unsafe_allow_html=True)
st.markdown(
    f"<style>html body .st-key-brand_home button "
    f"{{ background-image: url('{lockup_data_uri(520, st.session_state.get('theme') == 'light')}') !important; }}</style>",
    unsafe_allow_html=True
)
with st.container(key="top_nav"):
    brand_col, nav_col, actions_col = st.columns(
        [1.5, 8.6, 1.6], vertical_alignment="center"
    )

    with brand_col:
        st.button("GymPulse AI", on_click=go_home, key="brand_home",
                  help="Go to Dashboard")
        st.markdown(
            '<div class="nav-tagline">Smarter insights. Stronger member retention.</div>',
            unsafe_allow_html=True
        )

    with nav_col:
        if not _is_mobile():
            _current = st.session_state.get("current_page")
            st.radio(
                "Navigation",
                MAIN_PAGES,
                index=MAIN_PAGES.index(_current) if _current in MAIN_PAGES else None,
                format_func=nav_label,
                horizontal=True,
                label_visibility="collapsed",
                key=f"main_nav_{_current}",
                on_change=on_main_nav
            )

    with actions_col:
        with st.container(key="top_actions", horizontal=True,
                          horizontal_alignment="right",
                          vertical_alignment="center", gap="small"):

            with st.container(key="top_msg"):
                st.button(
                    f":material/forum: {unread_replies}" if unread_replies else ":material/forum:",
                    key="top_msg_btn", on_click=show_page, args=("Follow-ups",),
                    help="Follow-ups"
                )

            with st.container(key="top_profile"):
                with st.popover("Profile"):
                    _who = user_name if gteam.is_staff() else (profile.get("full_name") or user_name)
                    _gym = profile.get("business_name") or business_name
                    gw._md(
                        f'<div class="pm-id">{gw.avatar_html(_who, _av, 44)}'
                        f'<div><div class="pm-name">{gw._esc(_who)}</div>'
                        f'<div class="pm-gym">{gw._esc(_gym)}</div></div></div>'
                    )
                    st.markdown('<div class="pm-label">Appearance</div>', unsafe_allow_html=True)
                    _dark = st.session_state.get("theme", "dark") == "dark"
                    st.button(
                        "Switch to light mode" if _dark else "Switch to dark mode",
                        icon=":material/light_mode:" if _dark else ":material/dark_mode:",
                        key="theme_toggle", on_click=toggle_theme,
                        use_container_width=True
                    )
                    st.markdown('<div class="pm-label">Account</div>', unsafe_allow_html=True)
                    st.button("Profile & settings", icon=":material/person:",
                              key="pm_item_profile", type="tertiary",
                              on_click=open_settings, args=("Personal info",),
                              use_container_width=True)
                    st.button("Trainers", icon=":material/groups:",
                              key="pm_item_trainers", type="tertiary",
                              on_click=open_settings, args=("Trainers",),
                              use_container_width=True)
                    st.button("Check-in devices", icon=":material/qr_code_scanner:",
                              key="pm_item_devices", type="tertiary",
                              on_click=open_settings, args=("Check-in devices",),
                              use_container_width=True)
                    st.button("Preferences", icon=":material/tune:",
                              key="pm_item_prefs", type="tertiary",
                              on_click=open_settings, args=("Preferences",),
                              use_container_width=True)
                    st.divider()
                    st.button("Log Out", icon=":material/logout:",
                              key="logout_button_main", on_click=log_out,
                              use_container_width=True)

            with st.container(key="top_menu"):
                with st.popover("☰"):
                    with st.container(key="pop_main"):
                        for name in MAIN_PAGES:
                            st.button(name, key=f"mob_main_{name}", on_click=show_page,
                                      args=(name,), use_container_width=True)
                        st.divider()
                    for name in MORE_PAGES:
                        if name == "Follow-ups":
                            continue
                        st.button(name, key=f"mob_more_{name}", on_click=show_page,
                                  args=(name,), use_container_width=True)

    page = st.session_state["current_page"]
    if gteam.is_staff() and page in gteam.OWNER_ONLY:
        page = st.session_state["current_page"] = "Dashboard"
    st.session_state["_rendered_page"] = page

    if page in MAIN_PAGES + MORE_PAGES and st.query_params.get("p") != page:
        st.query_params["p"] = page

    _fragment = getattr(st, "fragment", None)
    if _fragment is not None:
        try:
            @_fragment(run_every=None if page == "Archie" else 20)
            def _watch_inbox():
                import time as _t
                if _t.time() - st.session_state.get("_watch_at", 0) < 15:
                    return                       # checked moments ago: don't slow down this tap
                st.session_state["_watch_at"] = _t.time()
                count = _unread_now()
                if count and count > st.session_state.get("last_unread", 0):
                    st.session_state["last_unread"] = count
                    _notify_replies(count)
                    if st.session_state.get("current_page") == "Follow-ups":
                        st.rerun()
                gid = st.session_state.get("gym_id")
                if gid:
                    sig = gw.checkin_signature(supabase, gid)
                    prev = st.session_state.get("ck_sig")
                    st.session_state["ck_sig"] = sig
                    if prev is not None and sig is not None and sig != prev:
                        gw.bump_data_version()
                        if st.session_state.get("current_page") not in ("Check-in", "Archie", "Settings"):
                            st.rerun()
            _watch_inbox()
        except TypeError:
            pass
    
if page not in ("Dashboard", "Member Profile") and st.session_state.get("nav_hist"):
    st.button("Back", icon=":material/arrow_back:", key="global_back", on_click=go_back)
# =========================================================
# PERSONALIZED GREETING VARIABLES
# =========================================================

from datetime import datetime
from zoneinfo import ZoneInfo
from html import escape as html_escape

current_hour = datetime.now(ZoneInfo("Africa/Lagos")).hour

if current_hour < 12:
    greeting = "Good morning"
elif current_hour < 17:
    greeting = "Good afternoon"
else:
    greeting = "Good evening"

safe_user_name = html_escape(str(user_name))
safe_business_name = html_escape(str(business_name))
   
# =========================================================
# 7. DASHBOARD
# =========================================================
if st.session_state.get("gym_id") and st.session_state.get("_freeze_day") != str(gw.today_local()):
    st.session_state["_freeze_day"] = str(gw.today_local())
    try:
        gg.process_freezes(supabase, st.session_state["gym_id"])
    except Exception:
        pass

if not gteam.is_staff():
    gl.render_acceptance_banner(supabase, owner_id)

# Free trial and subscription: the Upgrade pop-up and the Subscription page
# instead of the app once a trial or plan has ended; pages above the gym's plan
# show an upgrade card.
_bill_upsell = False
try:
    if gteam.is_staff():
        if gbill.must_lock(supabase, st.session_state.get("gym_id")) and page not in ("Settings", "FAQs"):
            gw.page_header("Plan ended", "", "GymPulse AI")
            st.warning("Your gym's GymPulse AI plan has ended. Please ask the gym owner to renew it. "
                       "Everything you've added is safe.")
            gw.apply_theme(st.session_state.get("theme", "dark"))
            st.stop()
    else:
        gbill.render_banner(supabase, st.session_state.get("gym_id"))
        if st.session_state.get("gym_id") and st.session_state.get("current_page") in ("Dashboard", "Member Management"):
            gbill.render_limit_banner(supabase, st.session_state.get("gym_id"))
    if page not in gbill.ALWAYS_OPEN and gbill.must_lock(supabase, st.session_state.get("gym_id")):
        page = "Subscription"
    elif not gbill.page_allowed(supabase, st.session_state.get("gym_id"), page):
        _bill_upsell = True
except Exception as _bill_error:
    gmon.capture(_bill_error, "billing")

if _bill_upsell:
    gbill.render_upsell(supabase, st.session_state.get("gym_id"), page)
    gw.apply_theme(st.session_state.get("theme", "dark"))
    st.stop()

if page == "Dashboard":
    try:
        gg.render_month_banner(supabase, st.session_state.get("gym_id"), assess_members, owner_id)
    except Exception:
        pass
    st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)
    gc.render_command_centre(
        supabase,
        st.session_state.get("gym_id"),
        assess_members,
        greeting,
        user_name,
        business_name
    )

# =========================================================
# 8. WORKSPACE PAGES
# =========================================================
elif page == "Risk Radar":
    gw.render_risk_radar(supabase, st.session_state.gym_id, assess_members)
elif page == "Action Centre":
    gw.render_action_centre(supabase, st.session_state.gym_id, assess_members)
elif page == "Owner":
    gteam.render_owner_hub(supabase, st.session_state.gym_id, assess_members, owner_id)
elif page == "Business Insights":
    gw.render_business_insights(supabase, st.session_state.gym_id, assess_members)
elif page == "Payments & Renewals":
    gw.render_payments(supabase, st.session_state.gym_id, assess_members)
elif page == "Grow":
    gg.render_grow(supabase, st.session_state.gym_id, assess_members, owner_id)
elif page == "Admin":
    gadm.render_admin()
elif page == "Subscription":
    gbill.render_subscription_page(supabase, st.session_state.get("gym_id"))
elif page == "Follow-ups":
    fu.render_followups(
        supabase,
        st.session_state.gym_id,
        assess_members,
        user_name,
        business_name
    )
elif page == "Archie":
    gw.render_archie(
        supabase,
        st.session_state.gym_id,
        assess_members,
        business_name,
        user_name
    )
elif page == "Community":
    import gympulse_community as gcom
    gcom.render_owner(supabase, st.session_state.gym_id)
elif page == "Check-in":
    gw.render_checkin(supabase, st.session_state.gym_id)
elif page == "Settings":
    if gteam.is_staff():
        gteam.render_staff_settings(supabase, owner_id, log_out)
    else:
        gw.render_settings(
            supabase,
            owner_id,
            st.session_state.gym_id,
            log_out
        )

elif page == "Member Management":
    gw.page_header(
        "Member Management",
        "Register members, add their photo, and open any member's full profile.",
        "Your members"
    )
    gym_id = st.session_state.get("gym_id")

    if not gym_id:
        st.warning("No gym workspace found for your account.")
    else:
        _mm_flash = st.session_state.pop("mm_flash", None)
        if _mm_flash:
            st.success(_mm_flash)
        with st.expander("Bring your members in: import from GymMaster, Excel or any software",
                         icon=":material/upload_file:",
                         expanded=bool(st.session_state.get("gm_flash") or st.session_state.get("gm_errors"))):
            import gympulse_gymmaster as ggm
            ggm.render_gymmaster_import(supabase, gym_id)
            st.divider()
            ggm.render_photo_bulk(supabase, gym_id)
        with st.expander("Member sign-up link and QR code: members add their own details",
                         icon=":material/qr_code_2:"):
            import gympulse_signup as gsign
            gsign.render_owner(supabase, gym_id)
        with st.expander("Member app: each member's own page to renew, check in, book classes and message you",
                         icon=":material/smartphone:"):
            import gympulse_portal as gportal
            gportal.render_owner(supabase, gym_id)
        st.button("Member community: open your Community page", icon=":material/forum:", key="mm_to_comm",
                  on_click=show_page, args=("Community",), type="tertiary")
        st.markdown("### Register a New Member")
        import gympulse_billing as _gb_lim
        _can_add, _why_full = _gb_lim.can_add_members(supabase, gym_id)
        if not _can_add:
            st.info(_why_full)

        with st.form("register_member_form"):

            full_name = st.text_input("Full name")
            email = st.text_input("Email address")
            phone = st.text_input("Phone number")
            photo_file = st.file_uploader(
                "Photo (optional)",
                type=["jpg", "jpeg", "png", "heic", "heif", "webp"],
                key="register_photo"
            )

            col1, col2 = st.columns(2)

            with col1:
                age = st.number_input(
                    "Age", min_value=16, max_value=120, value=25
                )

                weight_kg = st.number_input(
                    "Weight (kg)",
                    min_value=1.0,
                    max_value=500.0,
                    value=70.0,
                    step=0.5
                )

            with col2:
                height_cm = st.number_input(
                    "Height (cm)",
                    min_value=50.0,
                    max_value=260.0,
                    value=170.0,
                    step=0.5
                )

                fitness_goal = st.selectbox(
                    "Fitness goal",
                    [
                        "Weight loss",
                        "Muscle gain",
                        "General fitness",
                        "Strength",
                        "Endurance",
                        "Sports performance"
                    ]
                )

            st.markdown('<div class="section-label">MEMBERSHIP</div>', unsafe_allow_html=True)
            st.caption("Plan, price and end date put the member on the Risk Radar straight away. "
                       "Their check-ins then update it automatically.")
            mcol1, mcol2, mcol3 = st.columns(3)
            plan = mcol1.selectbox("Plan", gw.PLANS, index=gw.PLANS.index("Monthly"))
            plan_price = mcol2.number_input("Price of this plan", min_value=0.0, step=500.0, value=0.0,
                                            help="What the member pays for the plan, e.g. 5,000 for a week.")
            membership_end = mcol3.date_input(
                "Membership ends",
                value=None,
                min_value=gw.today_local() - gw.timedelta(days=365),
                help="Leave empty to count the plan from today.",
            )
            pcol1, pcol2 = st.columns(2)
            paid_today = pcol1.number_input(
                "Amount paid today (optional)", min_value=0.0, step=500.0, value=0.0,
                help="Records their joining payment. Leave at 0 if they haven't paid yet."
            )
            paid_method = pcol2.selectbox("Paid by", ["Cash", "Bank transfer", "Card", "POS",
                                                      "Mobile money", "Other"])

            submitted = st.form_submit_button(
                "Register Member",
                type="primary",
                use_container_width=True,
                disabled=not _can_add
            )

        if submitted:
            if membership_end is None:
                membership_end = gw.today_local() + gw.timedelta(days=gw.PLAN_DAYS[plan])
            monthly_fee = round(float(plan_price) / gw.PLAN_MONTHS[plan], 2)

            if not full_name.strip():
                st.error("Please enter the member's full name.")

            else:
                member_data = {
                    "gym_id": gym_id,
                    "full_name": full_name.strip(),
                    "age": int(age),
                    "weight_kg": float(weight_kg),
                    "height_cm": float(height_cm),
                    "fitness_goal": fitness_goal
                }

                if email.strip():
                    member_data["email"] = email.strip()

                if phone.strip():
                    member_data["phone"] = phone.strip()

                if photo_file is not None:
                    try:
                        member_data["photo"] = gw.process_photo(
                            photo_file.getvalue()
                        )
                    except Exception:
                        st.warning(
                            "The photo could not be read, so the member "
                            "was registered without one."
                        )

                try:
                    created = (
                        supabase.table("members")
                        .insert(member_data)
                        .execute()
                    ).data or []
                except Exception as error:
                    st.error(f"Could not register member: {error}")
                else:
                    new_id = created[0]["id"] if created else None
                    note = gw.save_membership(
                        supabase, gym_id, new_id, plan, monthly_fee, membership_end
                    )
                    if new_id and paid_today > 0:
                        import gympulse_revenue as gr
                        try:
                            gr.record_payment(
                                supabase, gym_id, new_id, full_name.strip(), paid_today, plan,
                                gw.today_local(), paid_method, act=True, first=True,
                                end=membership_end,
                            )
                            note = (note + " " if note else "") + \
                                f"Joining payment of {paid_today:,.0f} recorded."
                        except Exception:
                            note = (note + " " if note else "") + \
                                "The joining payment could not be saved; record it on Renewals."
                    st.session_state["mm_flash"] = (
                        f"{full_name.strip()} is registered." + (f" {note}" if note else
                        " They're on the Risk Radar now; check-ins will keep them up to date.")
                    )
                    st.rerun()

        st.markdown("---")
        st.markdown("### Registered Members")

        gw.render_member_directory(supabase, gym_id)


# =========================================================
# 10. MEMBER PROFILE
# =========================================================

elif page == "Member Profile":

    gw.render_member_profile(
        supabase,
        st.session_state.get("gym_id"),
        st.session_state.get("profile_member_id"),
        assess_members
    )

# Member Assessment and Batch Assessment were retired in Phase 1: members are
# scored from their record and check-ins on the Risk Radar instead. The scoring
# logic they used (prepare_member_data, assess_members) is kept above.

# =========================================================
# 12. MODEL INSIGHTS
# =========================================================

elif page == "Model Insights":

    gw.page_header(
        "Model Insights",
        "Explore how the model's estimates change when one input "
        "varies while the other inputs remain constant.",
        "Under the hood"
    )

    st.write(
        "**What this page is for:** it is a *teaching tool*. Every input is "
        "held constant except one — days since last visit — and you see how "
        "the model's estimate moves as that single number grows. Use it to "
        "judge whether the model's logic makes sense, not to forecast real "
        "members."
    )
    st.info(
        "This experiment shows how the model responds to different "
        "inputs. It does not establish causation or real world accuracy."
    )

    st.markdown("### Set the baseline member")

    col1, col2 = st.columns(2)

    with col1:
        insight_membership = st.selectbox(
            "Membership type",
            ["Monthly", "Quarterly", "Annual"],
            key="insight_membership"
        )

        insight_previous = st.number_input(
            "Previous 30 day visits",
            min_value=0,
            max_value=100,
            value=10,
            key="insight_previous"
        )

        insight_recent = st.number_input(
            "Recent 30 day visits",
            min_value=0,
            max_value=100,
            value=5,
            key="insight_recent"
        )

    with col2:
        insight_renewal = st.number_input(
            "Days until renewal",
            min_value=0,
            max_value=365,
            value=14,
            key="insight_renewal"
        )

        insight_pt = st.number_input(
            "PT sessions attended",
            min_value=0,
            max_value=100,
            value=2,
            key="insight_pt"
        )

        max_days = st.slider(
            "Maximum days since last visit to explore",
            min_value=7,
            max_value=90,
            value=30
        )

    if st.button("Run Sensitivity Experiment", use_container_width=True):

        scenario_days = list(
            range(0, max_days + 1, max(1, max_days // 10))
        )

        if max_days not in scenario_days:
            scenario_days.append(max_days)

        scenarios = pd.DataFrame({
            "membership_type": [insight_membership] * len(scenario_days),
            "days_since_last_visit": scenario_days,
            "visits_previous_30_days": [insight_previous] * len(scenario_days),
            "visits_last_30_days": [insight_recent] * len(scenario_days),
            "renewal_due_days": [insight_renewal] * len(scenario_days),
            "pt_sessions_attended": [insight_pt] * len(scenario_days)
        })

        try:
            sensitivity_results = assess_members(scenarios)

            sensitivity_results = sensitivity_results.sort_values(
                "days_since_last_visit"
            )

            st.markdown("---")
            st.markdown("### Experimental response")

            chart_data = sensitivity_results.set_index(
                "days_since_last_visit"
            )[["cancellation_probability"]].rename(
                columns={
                    "cancellation_probability":
                    "Estimated cancellation probability"
                }
            )

            gw.modern_line_chart(sensitivity_results)

            display_results = sensitivity_results[
                [
                    "days_since_last_visit",
                    "cancellation_probability",
                    "risk_category"
                ]
            ].rename(
                columns={
                    "days_since_last_visit": "Days since last visit",
                    "cancellation_probability": "Estimated probability",
                    "risk_category": "Provisional risk category"
                }
            )

            _dr = display_results.copy()
            _dr["Estimated probability"] = _dr["Estimated probability"].map(lambda v: f"{float(v):.0%}")
            gw.table(_dr, pills={"Provisional risk category": {"High": "red", "Medium": "amber", "Low": "lime"}})

            first_probability = float(
                sensitivity_results.iloc[0]["cancellation_probability"]
            )

            last_probability = float(
                sensitivity_results.iloc[-1]["cancellation_probability"]
            )

            st.metric(
                "Change across tested scenarios",
                f"{(last_probability - first_probability) * 100:+.1f} percentage points"
            )

            st.caption(
                "Only days since last visit changes across scenarios. "
                "All other inputs are held constant. Results describe "
                "the model's response, not a causal effect."
            )

        except Exception as error:
            st.error("The sensitivity experiment could not be completed.")

            with st.expander("Technical details"):
                st.code(str(error))
                
# =========================================================
# 13. ABOUT THE MODEL
# =========================================================

elif page == "About the Model":

    gw.page_header(
        "About GymPulse AI",
        "A machine-learning portfolio project exploring gym membership "
        "cancellation-risk assessment.",
        "The project"
    )

    st.markdown("### Model architecture")

    col1, col2, col3 = st.columns(3)
    col1.metric("Algorithm", "Logistic Regression")
    col2.metric("Input Features", "5")
    col3.metric("Training Dataset", "Synthetic")

    st.markdown("### Features used by the model")

    rows = [
        {"feature": "Membership type", "use": "Member's membership category"},
        {"feature": "Days since last visit", "use": "Time since the most recent visit"},
        {"feature": "Attendance change", "use": "Recent visits minus previous-period visits"},
        {"feature": "Days until renewal", "use": "Days remaining before renewal"},
        {"feature": "PT sessions attended", "use": "Recorded personal-training attendance"},
    ]
    gw.data_card(rows, [("feature", "Feature"), ("use", "Description")],
                 key_prefix="model_features", tone="lime")

    st.warning(
        "The model is trained on synthetic (simulated) data. Its accuracy on "
        "real gym members has not been established, and recorded test results "
        "from earlier development should not be treated as a real-world "
        "performance guarantee."
    )

    st.write(
        "Before operational use, the model would need real-world evaluation, "
        "calibration and a bias assessment. Member data must be handled with "
        "permission and privacy safeguards. This is an educational prototype, "
        "not a validated commercial prediction system."
    )
# =========================================================
# 13B. FAQs
# =========================================================

elif page == "FAQs":
    gw.render_faqs()

# =========================================================
# 14. FOOTER
# =========================================================

# Light mode goes last so it sits on top of every page's own styles
gw.apply_theme(st.session_state.get("theme", "dark"))
