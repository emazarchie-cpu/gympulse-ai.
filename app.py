import gympulse_workspaces as gw
import gympulse_followups as fu
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
        background: transparent;
        color: var(--white);
        border: 1px solid rgba(255,255,255,0.18);
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
        background: rgba(255,255,255,0.07);
        border-color: rgba(255,255,255,0.3);
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

    /* Lime buttons: the label must always be dark and easy to read */
    .stButton > button p,
    .stFormSubmitButton > button p,
    .stButton > button:hover p,
    .stFormSubmitButton > button:hover p {
        color: #10182A !important;
        font-weight: 800 !important;
    }

    .stDownloadButton > button p {
        color: #0B1020 !important;
        font-weight: 800 !important;
    }

    .stDownloadButton > button {
        background: var(--cyan);
        color: #0B1020;
        border: none;
        border-radius: 10px;
        font-weight: 800;
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


@st.dialog("Terms of Service")
def show_terms():
    st.markdown(
        """
**Last updated: October 2026**

By creating an account or using GymPulse AI, you agree to these terms.

**1. What GymPulse AI is.** A tool that gives gym owners experimental
estimates of member cancellation risk, plus a register for managing members.

**2. Estimates are not guarantees.** The model is currently trained on
synthetic data. Results are a guide only and should not be the sole basis
for any decision about a member.

**3. Your account.** Keep your login details private. You are responsible
for activity under your account.

**4. Your data and your members.** You confirm you have the right to enter
and process the member information you add, and that members have agreed
to this where the law requires it.

**5. Acceptable use.** Do not misuse the service, attempt to access other
accounts, or upload unlawful content.

**6. Availability and liability.** The service is provided as is, without
warranties. To the extent the law allows, GymPulse AI is not liable for
losses arising from its use.

**7. Changes.** We may update these terms. Continued use means you accept
the updated terms.

**8. Governing law.** These terms are governed by the laws of Nigeria.

**Contact:** YOUR-COMPANY-EMAIL
        """
    )


@st.dialog("Privacy Policy")
def show_privacy():
    st.markdown(
        """
**Last updated: October 2026**

**What we collect.** Your name, business name and email address when you
sign up, and the member records you choose to add (name, contact details,
age, weight, height and fitness goal).

**CSV uploads.** Files uploaded for batch assessment are processed during
your session and are not saved by GymPulse AI.

**How we use it.** To run your account, show your members, and generate
assessments. We do not sell your data or your members' data.

**Where it is stored.** In our database provider (Supabase). Each gym can
only access its own records. Passwords are handled by the authentication
service and are not stored in plain text.

**Emails.** We send account emails such as confirmations and password
reset codes.

**Your responsibilities.** You are responsible for having permission from
your members to store their information.

**Your rights.** You can ask us to access, correct or delete your data
under applicable law, including the Nigeria Data Protection Act.

**Contact:** gympulseai22@gmail.com
        """
    )


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

    # Brand lockup: identical to the top bar (logo, wordmark, tagline),
    # placed in the same left-hand column so it lines up exactly
    login_brand_col, _, _ = st.columns(
        [3.0, 6.4, 1.1],
        vertical_alignment="center"
    )

    with login_brand_col:
        html(f"""
        <div class="login-brand">
          {logo_img_tag('nav-brand-logo')}
          <div class="login-brand-word">GYM<span>PULSE</span> AI</div>
          <div class="nav-tagline">Smarter insights. Stronger member retention.</div>
        </div>
        """)

    # Hero
    html(f"""
    <div class="lp-hero">
      <div>
        <div class="lp-pill"><span class="lp-dot"></span>
          Member retention intelligence for gyms</div>
        <div class="lp-title">Know who is leaving<br>
          <span class="lp-grad">before they do.</span></div>
        <div class="lp-sub">GymPulse AI reads attendance and renewal
          patterns and flags the members who are drifting away, so you can
          reach out while it still matters. Add members by hand or drop in
          a spreadsheet.</div>
        <div class="lp-chips">
          <div class="lp-chip">{icon('check', 14)} Free to start</div>
          <div class="lp-chip">{icon('check', 14)} Runs in your browser</div>
          <div class="lp-chip">{icon('check', 14)} Works with a simple CSV</div>
          <div class="lp-chip">{icon('check', 14)} Archie AI assistant</div>
        </div>
      </div>
      <div class="lp-radar">
        <div class="lp-radar-head">
          <div class="lp-radar-title">Risk Radar</div>
          <div class="lp-live"><span class="lp-dot"></span>LIVE PREVIEW</div>
        </div>
        <svg class="lp-pulse-line" viewBox="0 0 400 54" preserveAspectRatio="none">
          <path d="M0 30 H110 L130 30 L145 6 L165 50 L182 18 L195 30 H400"
                fill="none" stroke="#B7F34A" stroke-width="2.5"
                stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        <div class="lp-row">
          <div class="lp-avatar" style="background:#FF8A5B;">AO</div>
          <div class="lp-row-main">
            <div class="lp-row-name">Member A</div>
            <div class="lp-row-sub">18 days away · renews in 6 days</div>
          </div>
          <div class="lp-risk lp-high">HIGH · 72%</div>
        </div>
        <div class="lp-row">
          <div class="lp-avatar" style="background:#FFC44D;">KB</div>
          <div class="lp-row-main">
            <div class="lp-row-name">Member B</div>
            <div class="lp-row-sub">Visits down 4 this month</div>
          </div>
          <div class="lp-risk lp-med">MEDIUM · 41%</div>
        </div>
        <div class="lp-row">
          <div class="lp-avatar" style="background:#B7F34A;">CE</div>
          <div class="lp-row-main">
            <div class="lp-row-name">Member C</div>
            <div class="lp-row-sub">Steady visits · 6 PT sessions</div>
          </div>
          <div class="lp-risk lp-low">LOW · 14%</div>
        </div>
        <div class="lp-tiny">ILLUSTRATIVE EXAMPLE · NOT REAL MEMBER DATA</div>
      </div>
    </div>
    <div class="lp-stats">
      <div class="lp-stat"><b>5</b><span>signals analysed</span></div>
      <div class="lp-stat"><b>3</b><span>clear risk levels</span></div>
      <div class="lp-stat"><b>CSV</b><span>or manual entry</span></div>
      <div class="lp-stat"><b>Seconds</b><span>to a full assessment</span></div>
    </div>
    <div class="section-label" style="text-align:center;margin-top:34px;">
      SIGN IN TO YOUR WORKSPACE</div>
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
    _, auth_col, _ = st.columns([1, 1.4, 1])

    with auth_col:
        with st.container(border=True, key="auth_card"):
# ---------------- LOGIN PAGE ----------------
            if st.session_state.auth_mode == "login":

                st.markdown(
                    '<div class="auth-title">Welcome back, sign in</div>',
                    unsafe_allow_html=True
                )

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
                        "I agree to the Terms of Service and Privacy Policy"
                    )

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
                    elif not agree:
                        st.warning(
                            "Please accept the Terms of Service and Privacy Policy."
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
                                            "account_type": "gym_owner"
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

            legal_a, legal_b = st.columns(2)

            with legal_a:
                if st.button("Terms of Service", key="open_terms"):
                    show_terms()

            with legal_b:
                if st.button("Privacy Policy", key="open_privacy"):
                    show_privacy()

    # LANDING PAGE SECTIONS

    # The quiet exit
    html(f"""
    <div class="lp-kicker">The problem</div>
    <div class="lp-h2">Members rarely say goodbye.<br>They just fade.</div>
    <div class="lp-lead">By the time a cancellation lands, the warning signs
      have been there for weeks.</div>
    <div class="lp-split">
      <div>
        <div class="lp-ic">{icon('down')}</div>
        <h3>Attendance slips first. Cancellation follows.</h3>
        <p>A drop from regular visits to almost none is easy to miss in a
          busy gym. GymPulse AI watches that pattern together with renewal
          timing and personal-training activity, then tells you where to
          look first.</p>
      </div>
      <div>
        <div class="lp-bars">
          <div class="lp-bar-col"><div class="lp-bar-fill" style="height:92%"></div><div class="lp-bar-lbl">W1</div></div>
          <div class="lp-bar-col"><div class="lp-bar-fill" style="height:84%"></div><div class="lp-bar-lbl">W2</div></div>
          <div class="lp-bar-col"><div class="lp-bar-fill" style="height:70%"></div><div class="lp-bar-lbl">W3</div></div>
          <div class="lp-bar-col"><div class="lp-bar-fill warn" style="height:46%"></div><div class="lp-bar-lbl">W4</div></div>
          <div class="lp-bar-col"><div class="lp-bar-fill warn" style="height:28%"></div><div class="lp-bar-lbl">W5</div></div>
          <div class="lp-bar-col"><div class="lp-bar-fill warn" style="height:14%"></div><div class="lp-bar-lbl">W6</div></div>
        </div>
        <div class="lp-bar-cap">Illustrative weekly visits for one member</div>
      </div>
    </div>
    """)

    # How it works
    html(f"""
    <div class="lp-kicker">How it works</div>
    <div class="lp-h2">From spreadsheet to action<br>in three moves</div>
    <div class="lp-lead">Bring the information you already have. No hardware,
      no installs.</div>
    <div class="lp-steps">
      <div class="lp-stepcard"><div class="lp-num">01</div>
        <div class="lp-ic">{icon('upload')}</div>
        <h4>Bring your data</h4>
        <p>Register members one at a time or upload a CSV with membership
          type, visits, renewal timing and PT sessions.</p></div>
      <div class="lp-stepcard"><div class="lp-num">02</div>
        <div class="lp-ic">{icon('gauge')}</div>
        <h4>Get risk estimates</h4>
        <p>Each member gets a cancellation probability and a High, Medium
          or Low level you can read at a glance.</p></div>
      <div class="lp-stepcard"><div class="lp-num">03</div>
        <div class="lp-ic">{icon('chat')}</div>
        <h4>Reach out early</h4>
        <p>Start with the members who need you most, check in personally and
          download the results for your team.</p></div>
    </div>
    """)

    # Meet Archie
    html(f"""
    <div class="lp-kicker">Meet Archie</div>
    <div class="lp-h2">Your AI retention assistant</div>
    <div class="lp-lead">Archie reads your live member data, tells you who needs
      you first, and writes excited, ready-to-send messages for WhatsApp and email.</div>
    <div class="lp-archie">
      <div class="lp-archie-bot">{gw.ARCHIE_BOT_SVG}</div>
      <div class="lp-chat">
        <div class="lp-msg me">Who should I call first today?</div>
        <div class="lp-msg ai">Great news, I found three members who would love to hear
          from you. Ada has not visited in 18 days and renews this week, so she is first.</div>
        <div class="lp-msg ai">Here is a message ready to send: "Hi Ada! We have missed you
          at the gym and we are so excited to help you reach your goal. Can we chat this week?"</div>
        <div class="lp-send">WHATSAPP · EMAIL · SEND IN ONE CLICK</div>
      </div>
    </div>
    """)

    # Bento features
    html(f"""
    <div class="lp-kicker">Features</div>
    <div class="lp-h2">Built for one job:<br>keeping your members</div>
    <div class="lp-lead">Focused tools, no clutter.</div>
    <div class="lp-bento-grid">
      <div class="lp-bento b-4">
        <div class="lp-ic">{icon('upload')}</div>
        <h4>Batch CSV assessment</h4>
        <p>Upload your whole membership list, preview the records, and
          download an estimate for every member in a single file.</p>
        <div class="lp-mini">
          <span class="lp-risk lp-high">HIGH</span>
          <span class="lp-risk lp-med">MEDIUM</span>
          <span class="lp-risk lp-low">LOW</span>
        </div>
      </div>
      <div class="lp-bento b-2">
        <div class="lp-ic">{icon('user')}</div>
        <h4>Individual assessment</h4>
        <p>One member, instant estimate, plus suggested next steps.</p>
      </div>
      <div class="lp-bento b-2">
        <div class="lp-ic">{icon('users')}</div>
        <h4>Member management</h4>
        <p>A private register with goals, contact details and body metrics.</p>
      </div>
      <div class="lp-bento b-2">
        <div class="lp-ic">{icon('sliders')}</div>
        <h4>What-if explorer</h4>
        <p>See how the estimate shifts as time since the last visit grows.</p>
      </div>
      <div class="lp-bento b-2">
        <div class="lp-ic">{icon('target')}</div>
        <h4>Priority follow-up</h4>
        <p>Plain-language guidance on who to contact first.</p>
      </div>
    </div>
    """)

    # Transparency
    html(f"""
    <div class="lp-kicker">Transparency</div>
    <div class="lp-note">
      <div class="lp-ic">{icon('shield')}</div>
      <div>
        <h4>Experimental estimates, clearly labelled</h4>
        <p>GymPulse AI is an early-stage project and its model is trained on
          synthetic data. Treat results as a guide for deciding who to check
          in with, not a guarantee. Your own knowledge of your members always
          comes first.</p>
      </div>
    </div>
    """)

    # Closing call to action
    html(f"""
    <div class="lp-cta">
      <div class="lp-cta-title">Keep more members.<br>
        <span class="lp-grad">Start with GymPulse AI.</span></div>
      <p>Create your free account at the top of this page
        <span class="lp-arrow">{icon('arrow', 16)}</span></p>
    </div>
    <div class="footer">© GymPulse AI · Smarter insights. Stronger member retention.</div>
    """)
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

    # Create a workspace if this owner does not have one
    if gym_rows:
        gym = gym_rows[0]

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

except Exception as error:
    st.session_state.gym_id = None

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
    """Train a demonstration model using synthetic fitness data."""

    rng = np.random.default_rng(42)

    sample_size = 1000

    membership_type = rng.choice(
        ["Monthly", "Quarterly", "Annual"],
        size=sample_size,
        p=[0.55, 0.25, 0.20]
    )

    days_since_last_visit = rng.integers(
        0, 31, size=sample_size
    )

    visits_previous_30_days = rng.integers(
        0, 21, size=sample_size
    )

    visits_last_30_days = rng.integers(
        0, 21, size=sample_size
    )

    renewal_due_days = rng.integers(
        0, 91, size=sample_size
    )

    pt_sessions_attended = rng.integers(
        0, 13, size=sample_size
    )

    attendance_change = (
        visits_last_30_days
        - visits_previous_30_days
    )

    training_data = pd.DataFrame({
        "membership_type": membership_type,
        "days_since_last_visit": days_since_last_visit,
        "attendance_change": attendance_change,
        "renewal_due_days": renewal_due_days,
        "pt_sessions_attended": pt_sessions_attended
    })

    # Demonstration labels generated from assumed risk patterns.
    # These are synthetic labels, not real member outcomes.
    risk_score = (
        0.09 * days_since_last_visit
        - 0.12 * attendance_change
        - 0.18 * pt_sessions_attended
        - 0.025 * renewal_due_days
        + np.where(membership_type == "Monthly", 0.8, 0)
        + np.where(membership_type == "Annual", -0.5, 0)
        + rng.normal(0, 1.5, sample_size)
    )

    cancellation_label = (
        risk_score > np.median(risk_score)
    ).astype(int)

    categorical_features = ["membership_type"]

    numeric_features = [
        "days_since_last_visit",
        "attendance_change",
        "renewal_due_days",
        "pt_sessions_attended"
    ]

    preprocessing = ColumnTransformer(
        transformers=[
            (
                "membership",
                OneHotEncoder(handle_unknown="ignore"),
                categorical_features
            ),
            (
                "numeric",
                StandardScaler(),
                numeric_features
            )
        ]
    )

    pipeline = Pipeline([
        ("preprocessing", preprocessing),
        ("classifier", LogisticRegression(max_iter=1000))
    ])

    pipeline.fit(training_data, cancellation_label)

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

    features = prepare_member_data(data)

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
    "Archie",
    "Member Management",
]

MORE_PAGES = [
    "Follow-ups",
    "Check-in",
    "Model Insights",
    "About the Model",
    "FAQs",
]

if "current_page" not in st.session_state:
    _saved = st.query_params.get("p", "")
    st.session_state["current_page"] = (
        _saved if _saved in MAIN_PAGES + MORE_PAGES else "Dashboard"
    )

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
    return name


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


_av = profile.get("avatar")
_av_src = _av if gw.has_photo(_av) else gw._user_avatar(user_name)

st.markdown(f"""
<style>
.st-key-top_profile button::before {{
    content: ""; display: block; width: 34px; height: 34px; border-radius: 50%;
    background: url('{_av_src}') center/cover no-repeat;
    border: 2px solid #B7F34A; box-sizing: border-box;
}}
.st-key-top_msg, .st-key-top_profile {{ display: flex; justify-content: flex-end; }}
.st-key-top_msg button, .st-key-top_profile button {{
    background: rgba(255,255,255,0.06) !important;
    border: 1px solid var(--border) !important;
    border-radius: 10px !important; min-height: 38px !important;
    padding: 0 10px !important; box-shadow: none !important;
}}
.st-key-top_profile button {{
    border-radius: 50% !important; width: 42px !important;
    min-height: 42px !important; padding: 0 !important;
    justify-content: center !important;
}}
.st-key-top_profile button p,
.st-key-top_profile [data-testid="stIconMaterial"] {{ display: none !important; }}
.st-key-top_msg [data-testid="stIconMaterial"] {{ font-size: 22px !important; color: var(--white) !important; }}
.st-key-top_msg button p {{ color: var(--white) !important; font-weight: 800 !important; margin: 0 !important; }}
.st-key-top_msg button:hover, .st-key-top_profile button:hover {{ border-color: var(--lime) !important; }}

@media (min-width: 769px) {{
    .st-key-top_nav [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(3),
    .st-key-top_nav [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(4),
    .st-key-top_nav [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(5) {{
        flex: 0 0 52px !important; width: 52px !important; min-width: 52px !important;
    }}
}}
@media (max-width: 768px) {{
    .st-key-top_nav [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(3),
    .st-key-top_nav [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(4),
    .st-key-top_nav [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(5) {{
        display: flex !important; flex: 0 0 auto !important;
        width: auto !important; min-width: 0 !important;
    }}
}}
</style>
""", unsafe_allow_html=True)
st.markdown("""
<style>
@media (min-width: 769px) and (max-width: 1100px) {
    .st-key-top_nav [data-testid="stHorizontalBlock"] {
        flex-wrap: nowrap !important; gap: 8px !important; align-items: center !important;
    }
    .st-key-top_nav [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(2) {
        display: none !important;
    }
    .st-key-top_nav [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(1) {
        flex: 1 1 auto !important; width: auto !important; min-width: 0 !important;
    }
    .st-key-top_nav [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(n+3) {
        display: flex !important; flex: 0 0 52px !important;
        width: 52px !important; min-width: 52px !important;
    }
    .st-key-pop_main { display: block !important; }
}
/* Lighter pages on iPad and phones */
@media (max-width: 1100px), (hover: none) {
    .archie-bot, .lp-radar,
    [data-testid="stChatMessageAvatarAssistant"] { animation: none !important; filter: none !important; }
    .stButton > button { box-shadow: none !important; transition: none !important; transform: none !important; }
    [class*="st-key-card_"] { transition: none !important; }
    * { backdrop-filter: none !important; }
}
</style>
""", unsafe_allow_html=True)

with st.container(key="top_nav"):
    brand_col, nav_col, msg_col, profile_col, menu_col = st.columns(
        [2.0, 8.0, 0.55, 0.55, 0.55],
        vertical_alignment="center"
    )

    # BRAND / LOGO
    with brand_col:
        st.markdown(logo_img_tag("nav-brand-logo"), unsafe_allow_html=True)
        st.button("PULSE", on_click=go_home, key="brand_home", use_container_width=True)
        st.markdown(
            '<div class="nav-tagline">Smarter insights. Stronger member retention.</div>',
            unsafe_allow_html=True
        )

    # MAIN NAVIGATION (laptop only)
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

    # MESSAGES ICON -> Follow-ups
    with msg_col:
        with st.container(key="top_msg"):
            st.button(
                f":material/forum: {unread_replies}" if unread_replies else ":material/forum:",
                key="top_msg_btn",
                on_click=show_page,
                args=("Follow-ups",),
                help="Follow-ups"
            )
# Define safe display names
# Define safe display names
safe_user_name = str(st.session_state.get("user_name") or "User")
safe_business_name = str(
    st.session_state.get("business_name") or "Your Business"
)

# PROFILE ICON -> dropdown
with profile_col:
    with st.container(key="top_profile"):
        with st.popover("Profile"):
            st.markdown(f"**{safe_user_name}**")
            st.caption(safe_business_name)
            st.caption("APPEARANCE")

            _dark = st.session_state.get("theme", "dark") == "dark"
            st.button(
                    "Switch to light mode" if _dark else "Switch to dark mode",
                    icon=":material/light_mode:" if _dark else ":material/dark_mode:",
                    key="theme_toggle",
                    on_click=toggle_theme,
                    use_container_width=True
                )
            st.divider()
            st.button(
                "Profile & settings",
                key="open_settings",
                on_click=show_page,
                args=("Settings",),
                use_container_width=True
            )
            st.button(
                    "Log Out",
                    key="logout_button_main",
                    on_click=log_out,
                    use_container_width=True
                )

    # HAMBURGER MENU (top right)
    with menu_col:
        with st.container(key="top_menu"):
            with st.popover("☰", use_container_width=False):

                # Main pages: shown on phones only
                with st.container(key="pop_main"):
                    for name in MAIN_PAGES:
                        st.button(
                            name,
                            key=f"mob_main_{name}",
                            on_click=show_page,
                            args=(name,),
                            use_container_width=True
                        )
                    st.divider()

                # Extra pages (Follow-ups now lives in the message icon)
                for name in MORE_PAGES:
                    if name == "Follow-ups":
                        continue
                    st.button(
                        name,
                        key=f"mob_more_{name}",
                        on_click=show_page,
                        args=(name,),
                        use_container_width=True
                    )
    page = st.session_state["current_page"]
    if page not in ("Dashboard", "Member Profile") and st.session_state.get("nav_hist"):
        st.button("← Back", key="global_back", on_click=go_back)
    if page in MAIN_PAGES + MORE_PAGES and st.query_params.get("p") != page:
        st.query_params["p"] = page

    _fragment = getattr(st, "fragment", None)
    if _fragment is not None:
        try:
            @_fragment(run_every=None if page == "Archie" else 30)
            def _watch_inbox():
                count = _unread_now()
                if count and count > st.session_state.get("last_unread", 0):
                    st.session_state["last_unread"] = count
                    _notify_replies(count)
                    if st.session_state.get("current_page") == "Follow-ups":
                        st.rerun()
            _watch_inbox()
        except TypeError:
            pass
    
    
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
if page == "Dashboard":
    gw.render_dashboard(
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
elif page == "Business Insights":
    gw.render_business_insights(supabase, st.session_state.gym_id, assess_members)
elif page == "Payments & Renewals":
    gw.render_payments(supabase, st.session_state.gym_id, assess_members)
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
elif page == "Check-in":
    gw.render_checkin(supabase, st.session_state.gym_id)
elif page == "Settings":
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
        st.markdown("### Register a New Member")

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

            submitted = st.form_submit_button(
                "Register Member",
                use_container_width=True
            )

        if submitted:

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
                    (
                        supabase.table("members")
                        .insert(member_data)
                        .execute()
                    )

                    st.success("Member registered successfully!")
                    st.rerun()

                except Exception as error:
                    st.error(f"Could not register member: {error}")

        st.markdown("---")
        st.markdown("### Registered Members")

        gw.render_member_directory(supabase, gym_id)


# =========================================================
# 10. INDIVIDUAL MEMBER ASSESSMENT
# =========================================================

elif page == "Member Profile":

    gw.render_member_profile(
        supabase,
        st.session_state.get("gym_id"),
        st.session_state.get("profile_member_id"),
        assess_members
    )

elif page == "Member Assessment":

    gw.page_header(
        "Member Assessment",
        "Enter a hypothetical member's details to explore "
        "the output of the trained model.",
        "Try it out"
    )

    with st.form("member_assessment_form"):

        membership_type = st.selectbox(
            "Membership type",
            ["Monthly", "Quarterly", "Annual"]
        )

        col1, col2 = st.columns(2)

        with col1:

            days_since_last_visit = st.number_input(
                "Days since last visit",
                min_value=0,
                max_value=365,
                value=7
            )

            visits_previous_30_days = st.number_input(
                "Visits in the previous 30 days",
                min_value=0,
                max_value=100,
                value=10
            )

            renewal_due_days = st.number_input(
                "Days until renewal",
                min_value=0,
                max_value=365,
                value=14
            )

        with col2:

            visits_last_30_days = st.number_input(
                "Visits in the most recent 30 days",
                min_value=0,
                max_value=100,
                value=5
            )

            pt_sessions_attended = st.number_input(
                "Personal-training sessions attended",
                min_value=0,
                max_value=100,
                value=2
            )

        submitted = st.form_submit_button(
            "Generate Assessment",
            use_container_width=True
        )

    if submitted:

        member = pd.DataFrame([{
            "membership_type": membership_type,
            "days_since_last_visit": days_since_last_visit,
            "visits_previous_30_days": visits_previous_30_days,
            "visits_last_30_days": visits_last_30_days,
            "renewal_due_days": renewal_due_days,
            "pt_sessions_attended": pt_sessions_attended
        }])

        try:

            result = assess_members(member).iloc[0]

            probability = float(
                result["cancellation_probability"]
            )

            risk = result["risk_category"]

            st.markdown("---")
            st.markdown("### Assessment Results")

            col1, col2 = st.columns(2)

            col1.metric(
                "Estimated Cancellation Probability",
                f"{probability:.1%}"
            )

            col2.metric(
                "Provisional Risk Category",
                risk
            )

            st.progress(
                max(0.0, min(1.0, probability))
            )

            attendance_change = (
                visits_last_30_days
                - visits_previous_30_days
            )

            st.markdown(
                '<div class="section-label">ATTENDANCE ANALYSIS</div>',
                unsafe_allow_html=True
            )

            a, b, c = st.columns(3)

            a.metric(
                "Previous 30 Days",
                int(visits_previous_30_days)
            )

            b.metric(
                "Recent 30 Days",
                int(visits_last_30_days)
            )

            c.metric(
                "Attendance Change",
                f"{attendance_change:+}"
            )

            if attendance_change < 0:

                st.warning(
                    "WARNING: MEMBER CHECK-IN RECOMMENDED\n\n"
                    "Attendance has dropped compared with the previous "
                    "30 days. Consider contacting the member to understand "
                    "the change and offer support."
                )

            elif attendance_change > 0:

                st.success(
                    "POSITIVE ENGAGEMENT\n\n"
                    "Attendance has improved compared with the previous "
                    "30 days. Encourage the member to maintain this progress."
                )

            else:

                st.info(
                    "ENGAGEMENT STABLE\n\n"
                    "Attendance is unchanged compared with the previous "
                    "30 days. Continue monitoring activity and encourage "
                    "consistent attendance."
                )

            if risk == "High":

                st.error(
                    "PRIORITY FOLLOW-UP\n\n"
                    "This member requires a priority review. Check their "
                    "recent attendance and renewal date, then contact "
                    "them to understand any difficulties they may be "
                    "experiencing. Record the outcome and schedule a "
                    "follow-up if needed."
                )

            elif risk == "Medium":

                st.warning(
                    "WARNING: MEMBER ENGAGEMENT NEEDS ATTENTION\n\n"
                    "Review this member's recent attendance and upcoming "
                    "renewal date. Consider a personal check-in and agree "
                    "on a practical next step to encourage regular visits."
                )

            else:

                st.success(
                    "MAINTAIN MEMBER ENGAGEMENT\n\n"
                    "Continue monitoring attendance and supporting the "
                    "member's fitness goals. Encourage consistent visits "
                    "and review their progress at the next check-in."
                )

        except Exception as error:

            st.error(f"Assessment failed: {error}")
# =========================================================
# 11. BATCH CSV ASSESSMENT
# =========================================================

elif page == "Batch Assessment":

    # -----------------------------------------------------
    # PAGE HEADER
    # -----------------------------------------------------

    st.markdown(
        """
        <div class="hero">
            <div class="hero-eyebrow">
                GYMPULSE AI · BATCH INTELLIGENCE
            </div>
            <div class="hero-title">
                Batch Assessment
            </div>
            <div class="hero-description">
                Analyse multiple membership records in one workflow.
                Explore experimental cancellation-risk estimates
                and identify patterns that may deserve further review.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # -----------------------------------------------------
    # REQUIRED DATA FIELDS
    # -----------------------------------------------------

    st.markdown(
        '<div class="section-label">REQUIRED DATA</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        """
        <p style="color: #9CA3AF; margin-bottom: 20px;">
            Your CSV file must contain all six fields below.
            Use the exact column names shown.
        </p>
        """,
        unsafe_allow_html=True
    )

    required_fields = [
        (
            "01",
            "Membership Type",
            "membership_type",
            "The member's membership category."
        ),
        (
            "02",
            "Days Since Last Visit",
            "days_since_last_visit",
            "How many days have passed since the last visit."
        ),
        (
            "03",
            "Previous 30-Day Visits",
            "visits_previous_30_days",
            "Attendance during the preceding 30-day period."
        ),
        (
            "04",
            "Last 30-Day Visits",
            "visits_last_30_days",
            "Recent attendance activity."
        ),
        (
            "05",
            "Renewal Due Days",
            "renewal_due_days",
            "Days remaining until renewal is due."
        ),
        (
            "06",
            "PT Sessions Attended",
            "pt_sessions_attended",
            "Number of personal-training sessions attended."
        ),
    ]

    for row_start in range(0, len(required_fields), 3):
        columns = st.columns(3)

        for column, field in zip(
            columns,
            required_fields[row_start:row_start + 3]
        ):
            number, title, field_name, description = field

            with column:
                st.markdown(
                    f"""
<div style="
    background-color: #111827;
    border: 1px solid #273449;
    border-radius: 14px;
    padding: 18px;
">
    <div style="color: var(--lime); font-weight: 700;">
        FIELD {number}
    </div>
    <div style="color: #FFFFFF; font-size: 16px;">
        {title}
    </div>
    <div style="color: var(--lime); font-size: 12px;">
        {field_name}
    </div>
    <div style="color: #9CA3AF; font-size: 13px;">
        {description}
    </div>
</div>
""",
                    unsafe_allow_html=True
                )
# -----------------------------------------------------
# CSV UPLOAD
# -----------------------------------------------------

    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown(
        '<div class="section-label">UPLOAD MEMBERSHIP DATA</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        """
<div style="
    background-color: #111827;
    border: 1px solid #273449;
    border-left: 5px solid var(--lime);
    border-radius: 16px;
    padding: 24px;
    margin: 12px 0 18px 0;
">
    <div style="
        color: #FFFFFF;
        font-size: 20px;
        font-weight: 600;
        margin-bottom: 8px;
    ">
        Upload your membership records
    </div>
    <div style="
        color: #9CA3AF;
        font-size: 14px;
        line-height: 1.6;
    ">
        Select a CSV file containing your membership data.
        You can review the records before running the assessment.
    </div>
</div>
""",
        unsafe_allow_html=True
    )
    uploaded_file = st.file_uploader(
        "Choose a CSV file",
        type=["csv"],
        help="Upload a CSV containing all six required columns."
    )

    st.caption("Supported format: CSV · Maximum file size: 200 MB")

    if uploaded_file is not None:

        try:

            uploaded_data = pd.read_csv(uploaded_file)

            if uploaded_data.empty:
                st.error(
                    "The uploaded CSV contains no records."
                )
                st.stop()

            # ---------------------------------------------
            # VALIDATE REQUIRED COLUMNS
            # ---------------------------------------------

            required_columns = [
                "membership_type",
                "days_since_last_visit",
                "visits_previous_30_days",
                "visits_last_30_days",
                "renewal_due_days",
                "pt_sessions_attended",
            ]

            missing_columns = [
                column
                for column in required_columns
                if column not in uploaded_data.columns
            ]

            if missing_columns:

                st.error(
                    "Your CSV is missing the following required "
                    "columns: "
                    + ", ".join(missing_columns)
                )

                st.info(
                    "Check the column names in the Required Data "
                    "section above and upload the corrected file."
                )

                st.stop()

            # ---------------------------------------------
            # FILE SUMMARY
            # ---------------------------------------------

            st.markdown("<br>", unsafe_allow_html=True)

            st.markdown(
                '<div class="section-label">FILE OVERVIEW</div>',
                unsafe_allow_html=True
            )

            overview_col1, overview_col2, overview_col3 = (
                st.columns(3)
            )

            overview_col1.metric(
                "Total Records",
                f"{len(uploaded_data):,}"
            )

            overview_col2.metric(
                "Required Fields",
                len(required_columns)
            )

            overview_col3.metric(
                "File Status",
                "Ready"
            )

            # ---------------------------------------------
            # DATA PREVIEW
            # ---------------------------------------------

            with st.expander(
                "Preview uploaded membership data",
                expanded=True
            ):

                st.dataframe(
                    uploaded_data.head(10),
                    use_container_width=True,
                    hide_index=True
                )

                st.caption(
                    "Showing the first 10 records. "
                    "Your original uploaded data is not modified here."
                )

            # ---------------------------------------------
            # RUN ASSESSMENT
            # ---------------------------------------------

            st.markdown("<br>", unsafe_allow_html=True)

            st.markdown(
                '<div class="section-label">RUN ASSESSMENT</div>',
                unsafe_allow_html=True
            )

            st.markdown(
                """
                <p style="color: #9CA3AF;">
                    Run the existing model against the uploaded records
                    to explore its experimental risk estimates.
                </p>
                """,
                unsafe_allow_html=True
            )

            if st.button(
                "Assess All Members",
                use_container_width=True,
                type="primary"
            ):

                with st.spinner(
                    "Assessing membership records..."
                ):

                    results = assess_members(uploaded_data)

                total_members = len(results)

                high_risk = int(
                    (results["risk_category"] == "High").sum()
                )

                medium_risk = int(
                    (results["risk_category"] == "Medium").sum()
                )

                low_risk = int(
                    (results["risk_category"] == "Low").sum()
                )

                # -----------------------------------------
                # RESULTS SUMMARY
                # -----------------------------------------

                st.markdown("<br>", unsafe_allow_html=True)

                st.markdown(
                    '<div class="section-label">'
                    'ASSESSMENT SUMMARY</div>',
                    unsafe_allow_html=True
                )

                st.markdown(
                    """
                    <p style="color: #9CA3AF;">
                        Overview of the model outputs for this batch.
                    </p>
                    """,
                    unsafe_allow_html=True
                )

                col1, col2, col3, col4 = st.columns(4)

                col1.metric(
                    "Records Assessed",
                    f"{total_members:,}"
                )

                col2.metric(
                    "High Risk",
                    f"{high_risk:,}"
                )

                col3.metric(
                    "Medium Risk",
                    f"{medium_risk:,}"
                )

                col4.metric(
                    "Low Risk",
                    f"{low_risk:,}"
                )

                # -----------------------------------------
                # RESULTS TABLE
                # -----------------------------------------

                st.markdown("<br>", unsafe_allow_html=True)

                st.markdown(
                    '<div class="section-label">'
                    'MEMBER ASSESSMENT RESULTS</div>',
                    unsafe_allow_html=True
                )

                st.dataframe(
                    results,
                    use_container_width=True,
                    hide_index=True
                )

                # -----------------------------------------
                # DOWNLOAD RESULTS
                # -----------------------------------------

                csv_output = results.to_csv(
                    index=False
                ).encode("utf-8")

                st.download_button(
                    label="Download Assessment Results CSV",
                    data=csv_output,
                    file_name="gympulse_assessment_results.csv",
                    mime="text/csv",
                    use_container_width=True,
                    type="primary"
                )

                st.caption(
                    "Results are generated for this session and are "
                    "not saved to a permanent member database. "
                    "Risk estimates are experimental and should not "
                    "be treated as confirmed predictions of cancellation."
                )

        except Exception as error:

            st.error(
                "Could not process the uploaded file. "
                "Check the required columns, values, and file format."
            )

            with st.expander("Technical details"):

                st.code(str(error))

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

            st.dataframe(
                display_results,
                hide_index=True,
                use_container_width=True
            )

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

    gw.page_header(
        "Frequently Asked Questions",
        "Quick answers to help you get the most out of GymPulse AI.",
        "Help"
    )

    st.markdown(
        '<div class="section-label">GETTING STARTED</div>',
        unsafe_allow_html=True
    )

    with st.expander("How do I add members to my gym?"):
        st.write(
            "Open **Member Management**, fill in the member's details, "
            "and click **Register Member**. Only the full name is "
            "required. Registered members appear in the table below "
            "the form."
        )

    with st.expander("Can I suspend or remove a member?"):
        st.write(
            "Yes. In **Member Management**, scroll to **Registered "
            "Members**, pick a member and choose **Suspend**, "
            "**Archive** or **Delete permanently**. Suspended and "
            "archived members are left out of risk scoring and can be "
            "reactivated or restored at any time."
        )

    with st.expander("How do I see a member's full details?"):
        st.write(
            "Click a member's name in **Member Management**, the "
            "**Risk Radar** priority list, or the **Action Centre**. "
            "Their profile shows their photo, contact details, body "
            "stats and whether their membership is **Active** or "
            "**Inactive**. A membership is Active until its end date "
            "passes. Use **Record a renewal** on the Membership tab "
            "when they renew."
        )

    with st.expander("Is my gym's data separate from other gyms?"):
        st.write(
            "Yes. Each account has its own gym workspace, and the "
            "Member Management page only loads members registered "
            "under your gym."
        )

    with st.expander("How do I log out?"):
        st.write(
            "Click **Log Out** at the top right. This ends your "
            "session and returns you to the login page. Always log "
            "out on shared computers."
        )

    st.markdown(
        '<div class="section-label">RISK ASSESSMENTS</div>',
        unsafe_allow_html=True
    )

    with st.expander("What does the cancellation probability mean?"):
        st.write(
            "It is the model's estimate of how likely a member is to "
            "cancel, based on membership type, days since last visit, "
            "attendance change, days until renewal, and personal-"
            "training sessions. It is a guide for deciding who to "
            "check in with, not a guarantee."
        )

    with st.expander("What do High, Medium, and Low risk mean?"):
        st.write(
            "- **High**: estimated probability of 50% or more\n"
            "- **Medium**: 30% to just under 50%\n"
            "- **Low**: below 30%\n\n"
            "These categories are provisional and meant to help you "
            "prioritise follow-ups."
        )

    with st.expander("How accurate are the predictions?"):
        st.write(
            "The model was trained on **synthetic** (simulated) data, "
            "so its accuracy on real gym members has not been "
            "established. Treat results as experimental and combine "
            "them with your own knowledge of your members."
        )

    with st.expander("What should I do for a high-risk member?"):
        st.write(
            "Check their recent attendance and renewal date, then "
            "reach out personally. Ask how they are finding their "
            "training, offer support or a session with a trainer, and "
            "note the outcome so you can follow up."
        )

    st.markdown(
        '<div class="section-label">BATCH ASSESSMENT</div>',
        unsafe_allow_html=True
    )

    with st.expander("What columns does my CSV need?"):
        st.write(
            "Your file must include these exact column names:\n\n"
            "- `membership_type` (Monthly, Quarterly, or Annual)\n"
            "- `days_since_last_visit`\n"
            "- `visits_previous_30_days`\n"
            "- `visits_last_30_days`\n"
            "- `renewal_due_days`\n"
            "- `pt_sessions_attended`"
        )

    with st.expander("Why did my CSV upload fail?"):
        st.write(
            "The most common causes are a misspelled column name, "
            "an empty cell, a negative number, or a membership type "
            "other than Monthly, Quarterly, or Annual. Fix the file "
            "and upload it again."
        )

    with st.expander("Are my batch results saved?"):
        st.write(
            "No. Batch results exist only for your current session. "
            "Use **Download Assessment Results CSV** to keep a copy."
        )

    st.markdown(
        '<div class="section-label">PRIVACY</div>',
        unsafe_allow_html=True
    )

    with st.expander("How should I handle member data?"):
        st.write(
            "Only collect information members have agreed to share, "
            "keep your login private, and log out on shared devices. "
            "Follow the data-protection rules that apply where you "
            "operate."
        )
# =========================================================
# 14. FOOTER
# =========================================================
