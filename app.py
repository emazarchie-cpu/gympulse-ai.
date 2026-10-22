import os
import html
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import streamlit as st
from supabase import create_client
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


# =========================================================
# 1. PAGE CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="GYMPULSE Ai | Member Intelligence",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# =========================================================
# 2. GLOBAL STYLES
# =========================================================

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    :root {
        --bg: #0B1020;
        --surface: #121B2E;
        --surface-2: #1A2540;
        --card: rgba(17, 24, 39, 0.9);
        --lime: #B7F34A;
        --lime-dark: #9FD83E;
        --cyan: #35D6ED;
        --white: #F4F7FB;
        --muted: #9AA8BD;
        --border: rgba(255,255,255,0.09);
        --danger: #FF7A7A;
        --warning: #FFC44D;
        --success: #A7F3D0;
        --shadow: rgba(0,0,0,0.45);
    }

    html, body, [class*="st"] {
        font-family: "Inter", sans-serif;
    }

    .stApp {
        background: var(--bg);
        color: var(--white);
    }

    [data-testid="stHeader"] {
        background: rgba(11,16,32,0.96);
        border-bottom: 1px solid var(--border);
    }

    .block-container {
        padding-top: 1rem !important;
        padding-left: 1.5rem !important;
        padding-right: 1.5rem !important;
    }

    .brand-logo {
        font-size: 26px;
        font-weight: 900;
        letter-spacing: -0.08em;
        line-height: 1;
        margin: 0;
        display: flex;
        align-items: center;
        justify-content: flex-start;
        gap: 0;
    }

    .brand-logo .white {
        color: var(--white);
    }

    .brand-logo .lime {
        color: var(--lime);
    }

    .brand-logo .small-ai {
        color: var(--white);
        font-size: 0.72em;
        display: inline-block;
        transform: translateY(0.12em);
        margin-left: 0.03em;
    }

    .brand-tagline {
        color: var(--muted);
        font-size: 10px;
        margin-top: 2px;
        white-space: nowrap;
    }

    .hero {
        position: relative;
        overflow: hidden;
        background: linear-gradient(135deg, #1A2740 0%, #121B2E 55%, #1A2A34 100%);
        border: 1px solid var(--border);
        border-radius: 24px;
        padding: 32px 28px;
        margin-bottom: 22px;
    }

    .hero::before {
        content: "";
        position: absolute;
        inset: -20% auto auto -10%;
        width: 420px;
        height: 420px;
        background: radial-gradient(circle, rgba(183,243,74,0.15), transparent 60%);
        pointer-events: none;
    }

    .hero::after {
        content: "";
        position: absolute;
        inset: auto -12% -25% auto;
        width: 440px;
        height: 440px;
        background: radial-gradient(circle, rgba(53,214,237,0.12), transparent 60%);
        pointer-events: none;
    }

    .hero-inner {
        position: relative;
        z-index: 1;
    }

    .hero-pill {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        background: rgba(255,255,255,0.04);
        border: 1px solid var(--border);
        border-radius: 999px;
        padding: 7px 12px 7px 10px;
        color: var(--muted);
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        margin-bottom: 18px;
    }

    .hero-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: var(--lime);
        animation: pulse 1.8s infinite;
    }

    .hero-title {
        font-size: clamp(2.3rem, 5vw, 4rem);
        font-weight: 900;
        line-height: 1.05;
        letter-spacing: -0.06em;
        margin: 0;
        color: var(--white);
    }

    .hero-gradient {
        background: linear-gradient(90deg, var(--lime), var(--cyan));
        -webkit-background-clip: text;
        background-clip: text;
        color: transparent;
    }

    .hero-sub {
        color: #bcc8d8;
        font-size: 16px;
        line-height: 1.75;
        max-width: 680px;
        margin-top: 18px;
        margin-bottom: 20px;
    }

    .chips {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-top: 8px;
    }

    .chip {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: rgba(255,255,255,0.03);
        border: 1px solid var(--border);
        border-radius: 999px;
        padding: 7px 12px;
        font-size: 12px;
        color: var(--muted);
    }

    .chip svg {
        color: var(--lime);
    }

    .section-label {
        color: var(--lime);
        text-transform: uppercase;
        font-size: 11px;
        letter-spacing: 0.18em;
        font-weight: 800;
        margin-top: 30px;
        margin-bottom: 14px;
    }

    .feature-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 18px;
    }

    .feature-card {
        background: rgba(17,24,39,0.8);
        border: 1px solid var(--border);
        border-radius: 20px;
        padding: 22px 20px 18px;
        min-height: 170px;
    }

    .feature-no {
        position: absolute;
        top: 18px;
        right: 18px;
        font-size: 48px;
        font-weight: 800;
        color: rgba(255,255,255,0.06);
        letter-spacing: -0.08em;
    }

    .feature-card {
        position: relative;
    }

    .feature-card h4 {
        margin-top: 12px;
        margin-bottom: 8px;
        color: var(--white);
        font-size: 18px;
        font-weight: 800;
    }

    .feature-card p {
        color: var(--muted);
        line-height: 1.7;
        margin: 0;
        font-size: 13px;
    }

    .mini-icon {
        width: 44px;
        height: 44px;
        border-radius: 12px;
        display: grid;
        place-items: center;
        background: linear-gradient(135deg, rgba(183,243,74,0.18), rgba(53,214,237,0.08));
        border: 1px solid rgba(183,243,74,0.30);
        color: var(--lime);
    }

    .auth-container {
        background: rgba(17,24,39,0.9);
        border: 1px solid rgba(255,255,255,0.12);
        border-radius: 22px;
        padding: 18px 18px 14px;
        box-shadow: 0 26px 80px rgba(0,0,0,0.32);
    }

    .auth-title {
        font-size: 28px;
        font-weight: 800;
        letter-spacing: -0.04em;
        text-align: center;
        color: var(--white);
        margin: 8px 0 10px;
    }

    .auth-subtle {
        color: var(--muted);
        text-align: center;
        margin: 0 0 12px;
        font-size: 12px;
    }

    .nav-pill {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        padding: 0 !important;
        min-height: 0 !important;
        margin: 0 !important;
    }

    .nav-pill p {
        margin: 0 !important;
        font-size: 13px !important;
        font-weight: 700 !important;
        color: var(--muted) !important;
    }

    .nav-pill:hover p {
        color: var(--lime) !important;
    }

    .nav-pill-radio [data-baseweb="radio-group"] {
        display: flex;
        gap: 12px;
        flex-wrap: wrap;
    }

    .nav-pill-radio label {
        border-radius: 10px !important;
        background: transparent !important;
        border: 1px solid transparent !important;
        padding: 8px 12px !important;
    }

    .nav-pill-radio label p {
        color: var(--muted) !important;
        font-weight: 700 !important;
    }

    .nav-pill-radio label:has(input:checked) {
        background: rgba(183,243,74,0.08) !important;
        border-color: rgba(183,243,74,0.35) !important;
    }

    .nav-pill-radio label:has(input:checked) p {
        color: var(--lime) !important;
    }

    .stButton > button,
    .stFormSubmitButton > button {
        background: var(--lime);
        color: #10182A;
        border: none;
        border-radius: 10px;
        font-weight: 800;
        min-height: 42px;
        transition: 0.2s ease;
    }

    .stButton > button:hover,
    .stFormSubmitButton > button:hover {
        background: #D0FF7A;
        color: #10182A;
    }

    .st-bd {
        border-radius: 14px !important;
    }

    .stAlert {
        border-radius: 12px;
    }

    .stMetric {
        background: rgba(17,24,39,0.8);
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 18px 20px;
    }

    .stMetricLabel {
        color: var(--muted) !important;
        font-size: 12px !important;
    }

    .stMetricValue {
        color: var(--white) !important;
        font-weight: 800 !important;
        font-size: 2rem !important;
    }

    .big-cta {
        background: radial-gradient(circle at 20% 0%, rgba(183,243,74,0.16), transparent 38%),
                    radial-gradient(circle at 80% 100%, rgba(53,214,237,0.16), transparent 38%),
                    #121B2E;
        border: 1px solid rgba(183,243,74,0.25);
        border-radius: 28px;
        padding: 52px 30px;
        text-align: center;
        margin-top: 60px;
    }

    .big-cta h3 {
        font-size: clamp(2rem, 4vw, 3.5rem);
        line-height: 1.05;
        letter-spacing: -0.06em;
        margin: 0;
        color: var(--white);
    }

    .footer-text {
        text-align: center;
        color: var(--muted);
        font-size: 11px;
        margin-top: 22px;
    }

    @keyframes pulse {
        0% { box-shadow: 0 0 0 0 rgba(183,243,74,0.6); }
        100% { box-shadow: 0 0 0 10px rgba(183,243,74,0); }
    }

    @media (max-width: 900px) {
        .feature-grid {
            grid-template-columns: 1fr;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# 3. SUPABASE CLIENT
# =========================================================

if "supabase_client" not in st.session_state:
    st.session_state.supabase_client = create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_KEY"],
    )

supabase = st.session_state.supabase_client


# =========================================================
# 4. AUTH STATE
# =========================================================

if "auth_user" not in st.session_state:
    st.session_state.auth_user = None

if "user_profile" not in st.session_state:
    st.session_state.user_profile = None

if "auth_mode" not in st.session_state:
    st.session_state.auth_mode = "login"

if "reset_email_sent" not in st.session_state:
    st.session_state.reset_email_sent = False

if "reset_email" not in st.session_state:
    st.session_state.reset_email = ""

if "password_updated" not in st.session_state:
    st.session_state.password_updated = False


# =========================================================
# 5. AUTH HELPERS
# =========================================================

def set_auth_mode(mode: str):
    st.session_state.auth_mode = mode
    st.session_state.reset_email_sent = False


@st.dialog("Terms of Service")
def show_terms():
    st.markdown(
        """
**Last updated: October 2026**

By creating an account or using GymPulse AI, you agree to these terms.

**1. What GymPulse AI is.** A tool that gives gym owners experimental estimates of member cancellation risk, plus a register for managing members.

**2. Estimates are not guarantees.** The model is currently trained on synthetic data. Results are a guide only and should not be the sole basis for any decision about a member.

**3. Your account.** Keep your login details private. You are responsible for activity under your account.

**4. Your data and your members.** You confirm you have the right to enter and process the member information you add, and that members have agreed to this where required by law.

**5. Acceptable use.** Do not misuse the service, attempt to access other accounts, or upload unlawful content.

**6. Availability and liability.** The service is provided as is, without warranties. To the extent the law allows, GymPulse AI is not liable for losses arising from its use.

**7. Changes.** We may update these terms. Continued use means you accept the updated terms.

**8. Governing law.** These terms are governed by the laws of Nigeria.

**Contact:** gympulseai22@gmail.com
        """
    )


@st.dialog("Privacy Policy")
def show_privacy():
    st.markdown(
        """
**Last updated: October 2026**

**What we collect.** Your name, business name, and email address when you sign up, and the member records you choose to add.

**CSV uploads.** Files uploaded for batch assessment are processed during your session and are not saved by GymPulse AI.

**How we use it.** To run your account, show your members, and generate assessments.

**Where it is stored.** In the database provider (Supabase). Each gym can only access its own records. Passwords are handled by the authentication service and are not stored in plain text.

**Emails.** We send account emails such as confirmations and password reset codes.

**Your responsibilities.** You are responsible for having permission from your members to store their information.

**Your rights.** You can ask us to access, correct, or delete your data under applicable law.

**Contact:** gympulseai22@gmail.com
        """
    )


def brand_logo():
    st.markdown(
        """
        <div class="brand-logo">
            <span class="white">GYM</span><span class="lime">PULSE</span><span class="white small-ai">Ai</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================================================
# 6. ICONS + HTML HELPER
# =========================================================

ICON_PATHS = {
    "check": '<polyline points="20 6 9 17 4 12"/>',
    "down": '<polyline points="22 17 13.5 8.5 8.5 13.5 2 7"/><polyline points="16 17 22 17 22 11"/>',
    "upload": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" x2="12" y1="3" y2="15"/>',
    "gauge": '<path d="m12 14 4-4"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/>',
    "chat": '<path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/>',
    "shield": '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
    "arrow": '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
    "user": '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    "users": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
    "target": '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
    "sliders": '<line x1="21" x2="14" y1="4" y2="4"/><line x1="10" x2="3" y1="4" y2="4"/><line x1="21" x2="12" y1="12" y2="12"/><line x1="8" x2="3" y1="12" y2="12"/><line x1="21" x2="16" y1="20" y2="20"/><line x1="12" x2="3" y1="20" y2="20"/><line x1="14" x2="14" y1="2" y2="6"/><line x1="8" x2="8" y1="10" y2="14"/><line x1="16" x2="16" y1="18" y2="22"/>',
    "calendar": '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
}


def icon(name: str, size: int = 22) -> str:
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="1.75" '
        'stroke-linecap="round" stroke-linejoin="round">'
        f'{ICON_PATHS[name]}</svg>'
    )


def html_block(block: str):
    flat = " ".join(line.strip() for line in block.splitlines() if line.strip())
    st.markdown(flat, unsafe_allow_html=True)


# =========================================================
# 7. AUTH UI
# =========================================================

def render_auth_screen():
    st.markdown(
        """
        <div style="display:flex; justify-content:center; margin-bottom: 14px;">
            <div class="brand-logo">
                <span class="white">GYM</span><span class="lime">PULSE</span><span class="white small-ai">Ai</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Landing hero
    html_block(
        f"""
        <div class="hero">
            <div class="hero-inner">
                <div class="hero-pill"><span class="hero-dot"></span>Member retention intelligence for gyms</div>
                <div class="hero-title">Know who is leaving<br><span class="hero-gradient">before they do.</span></div>
                <div class="hero-sub">
                    GymPulse Ai reads attendance and renewal patterns and flags members who are drifting away, so you can reach out while it still matters.
                    Add members by hand or drop in a spreadsheet.
                </div>
                <div class="chips">
                    <div class="chip">{icon('check', 14)} Free to start</div>
                    <div class="chip">{icon('check', 14)} Runs in your browser</div>
                    <div class="chip">{icon('check', 14)} Works with a simple CSV</div>
                </div>
            </div>
        </div>
        """
    )

    _, auth_col, _ = st.columns([1, 1.4, 1])
    with auth_col:
        with st.container(border=True, key="auth_card"):
            if st.session_state.auth_mode == "login":
                st.markdown('<div class="auth-title">Welcome back, sign in</div>', unsafe_allow_html=True)

                if st.session_state.get("password_updated", False):
                    st.success("Password updated. Sign in with your new password.")

                st.button(
                    "Sign up",
                    on_click=set_auth_mode,
                    args=("signup",),
                    key="to_signup",
                )

                with st.form("login_form", border=False):
                    login_email = st.text_input("Email address")
                    login_password = st.text_input("Password", type="password")
                    login_submitted = st.form_submit_button("Sign in with email", use_container_width=True)

                st.button(
                    "Forgot password?",
                    on_click=set_auth_mode,
                    args=("forgot",),
                    key="to_forgot",
                )

                if login_submitted:
                    if not login_email or not login_password:
                        st.warning("Enter your email and password.")
                    else:
                        try:
                            result = supabase.auth.sign_in_with_password(
                                {"email": login_email.strip(), "password": login_password}
                            )

                            if result.user:
                                st.session_state.auth_user = {
                                    "id": str(result.user.id),
                                    "email": result.user.email,
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
                                        "full_name": "User",
                                        "business_name": "My Gym",
                                    }

                                st.rerun()

                        except Exception:
                            st.error("Login failed. Check your credentials and confirm your email address.")

            elif st.session_state.auth_mode == "signup":
                st.markdown('<div class="auth-title">Create your free account</div>', unsafe_allow_html=True)

                st.button(
                    "Back to sign in",
                    on_click=set_auth_mode,
                    args=("login",),
                    key="back_to_login_from_signup",
                )

                with st.form("signup_form", border=False):
                    full_name = st.text_input("Your full name")
                    business_name = st.text_input("Gym or company name", placeholder="e.g. Nuelarch Gym")
                    signup_email = st.text_input("Email address")
                    signup_password = st.text_input("Create password", type="password")
                    confirm_password = st.text_input("Confirm password", type="password")
                    agree = st.checkbox("I agree to the Terms of Service and Privacy Policy")

                    signup_submitted = st.form_submit_button("Create free account", use_container_width=True)

                if signup_submitted:
                    if not all([
                        full_name.strip(),
                        business_name.strip(),
                        signup_email.strip(),
                        signup_password,
                        confirm_password,
                    ]):
                        st.warning("Please complete every field.")
                    elif not agree:
                        st.warning("Please accept the Terms of Service and Privacy Policy.")
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
                                        "data": {
                                            "full_name": full_name.strip(),
                                            "business_name": business_name.strip(),
                                            "account_type": "gym_owner",
                                        }
                                    },
                                }
                            )

                            if result.session and result.user:
                                st.session_state.auth_user = {
                                    "id": str(result.user.id),
                                    "email": result.user.email,
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
                                        "business_name": business_name.strip(),
                                    }

                                st.rerun()
                            else:
                                st.success("Registration submitted! Check your email for a confirmation link, then return and sign in.")

                        except Exception:
                            st.error("Registration failed. Your email may already be registered, or the request may have failed. Please try again.")

            elif st.session_state.auth_mode == "forgot":
                st.button(
                    "Back to sign in",
                    on_click=set_auth_mode,
                    args=("login",),
                    key="back_to_login_from_forgot",
                )

                st.markdown('<div class="auth-title">Reset your password</div>', unsafe_allow_html=True)
                st.markdown(
                    """
                    <div class="auth-subtle">
                        To reset your password, enter your registered email address below.
                        We will send an OTP to this email for password reset.
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                if not st.session_state.get("reset_email_sent", False):
                    with st.form("reset_request_form", border=False):
                        reset_email = st.text_input("Email address")
                        send_code = st.form_submit_button("Send reset code", use_container_width=True)

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
                        f"If an account exists for {st.session_state.reset_email}, a 6-digit code is on its way. Check your spam folder too."
                    )

                    with st.form("reset_confirm_form", border=False):
                        reset_code = st.text_input("6-digit code")
                        new_password = st.text_input("New password", type="password")
                        confirm_new = st.text_input("Confirm new password", type="password")
                        reset_submitted = st.form_submit_button("Update password", use_container_width=True)

                    if reset_submitted:
                        if not reset_code.strip() or not new_password:
                            st.warning("Please complete every field.")
                        elif new_password != confirm_new:
                            st.error("Your passwords do not match.")
                        elif len(new_password) < 8:
                            st.warning("Your password must contain at least 8 characters.")
                        else:
                            try:
                                supabase.auth.verify_otp(
                                    {
                                        "email": st.session_state.reset_email,
                                        "token": reset_code.strip(),
                                        "type": "recovery",
                                    }
                                )
                                supabase.auth.update_user({"password": new_password})
                                supabase.auth.sign_out()

                                st.session_state.reset_email_sent = False
                                st.session_state.auth_mode = "login"
                                st.session_state.password_updated = True
                                st.rerun()

                            except Exception:
                                st.error("That code is invalid or has expired. Request a new one and try again.")

            st.markdown(
                '<div class="auth-subtle">Secure sign-in. Your password is never stored in plain text.</div>',
                unsafe_allow_html=True,
            )

            legal_a, legal_b = st.columns(2)
            with legal_a:
                if st.button("Terms of Service", key="open_terms"):
                    show_terms()
            with legal_b:
                if st.button("Privacy Policy", key="open_privacy"):
                    show_privacy()


# =========================================================
# 8. MODEL FUNCTIONS
# =========================================================

@st.cache_resource
def load_model():
    rng = np.random.default_rng(42)
    sample_size = 1000

    membership_type = rng.choice(
        ["Monthly", "Quarterly", "Annual"],
        size=sample_size,
        p=[0.55, 0.25, 0.20],
    )

    days_since_last_visit = rng.integers(0, 31, size=sample_size)
    visits_previous_30_days = rng.integers(0, 21, size=sample_size)
    visits_last_30_days = rng.integers(0, 21, size=sample_size)
    renewal_due_days = rng.integers(0, 91, size=sample_size)
    pt_sessions_attended = rng.integers(0, 13, size=sample_size)

    attendance_change = visits_last_30_days - visits_previous_30_days

    training_data = pd.DataFrame({
        "membership_type": membership_type,
        "days_since_last_visit": days_since_last_visit,
        "attendance_change": attendance_change,
        "renewal_due_days": renewal_due_days,
        "pt_sessions_attended": pt_sessions_attended,
    })

    risk_score = (
        0.09 * days_since_last_visit
        - 0.12 * attendance_change
        - 0.18 * pt_sessions_attended
        - 0.025 * renewal_due_days
        + np.where(membership_type == "Monthly", 0.8, 0)
        + np.where(membership_type == "Annual", -0.5, 0)
        + rng.normal(0, 1.5, sample_size)
    )

    cancellation_label = (risk_score > np.median(risk_score)).astype(int)

    categorical_features = ["membership_type"]
    numeric_features = [
        "days_since_last_visit",
        "attendance_change",
        "renewal_due_days",
        "pt_sessions_attended",
    ]

    preprocessing = ColumnTransformer(
        transformers=[
            ("membership", OneHotEncoder(handle_unknown="ignore"), categorical_features),
            ("numeric", StandardScaler(), numeric_features),
        ]
    )

    pipeline = Pipeline([
        ("preprocessing", preprocessing),
        ("classifier", LogisticRegression(max_iter=1000)),
    ])

    pipeline.fit(training_data, cancellation_label)
    return pipeline


model = load_model()


def prepare_member_data(data: pd.DataFrame) -> pd.DataFrame:
    data = data.copy()

    required_columns = [
        "membership_type",
        "days_since_last_visit",
        "visits_previous_30_days",
        "visits_last_30_days",
        "renewal_due_days",
        "pt_sessions_attended",
    ]

    missing = [col for col in required_columns if col not in data.columns]
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(missing))

    numeric_columns = [
        "days_since_last_visit",
        "visits_previous_30_days",
        "visits_last_30_days",
        "renewal_due_days",
        "pt_sessions_attended",
    ]

    for col in numeric_columns:
        data[col] = pd.to_numeric(data[col], errors="raise")
        if data[col].isna().any():
            raise ValueError(f"{col} contains missing values.")
        if (data[col] < 0).any():
            raise ValueError(f"{col} cannot contain negative values.")

    if not data["membership_type"].isin(["Monthly", "Quarterly", "Annual"]).all():
        raise ValueError("Membership type must be Monthly, Quarterly, or Annual.")

    data["attendance_change"] = data["visits_last_30_days"] - data["visits_previous_30_days"]

    return data[
        [
            "membership_type",
            "days_since_last_visit",
            "attendance_change",
            "renewal_due_days",
            "pt_sessions_attended",
        ]
    ]


def assess_members(data: pd.DataFrame) -> pd.DataFrame:
    if data.empty:
        raise ValueError("The uploaded dataset contains no members.")

    features = prepare_member_data(data)
    probs = model.predict_proba(features)[:, 1]

    results = data.copy()
    results["cancellation_probability"] = probs
    results["risk_category"] = [
        "High" if p >= 0.50 else "Medium" if p >= 0.30 else "Low"
        for p in probs
    ]
    return results


# =========================================================
# 9. APP ROUTING
# =========================================================

def go_home():
    st.session_state["selected_page"] = "Dashboard"


def log_out():
    try:
        supabase.auth.sign_out()
    except Exception:
        pass

    for key in list(st.session_state.keys()):
        del st.session_state[key]


NAV_PAGES = [
    "Dashboard",
    "Member Management",
    "Member Assessment",
    "Batch Assessment",
    "Model Insights",
    "About the Model",
    "FAQs",
]


# =========================================================
# 10. MAIN APP
# =========================================================

if st.session_state.auth_user is None:
    render_auth_screen()
    st.stop()


# Logged-in app
profile = st.session_state.user_profile or {}
user_name = profile.get("full_name", "User")
business_name = profile.get("business_name", "My Gym")

owner_id = st.session_state.auth_user["id"]

try:
    gym_result = (
        supabase.table("gyms")
        .select("*")
        .eq("owner_id", owner_id)
        .limit(1)
        .execute()
    )

    if gym_result.data:
        gym = gym_result.data[0]
    else:
        new_gym = (
            supabase.table("gyms")
            .insert({"owner_id": owner_id, "business_name": business_name.strip() or "My Gym"})
            .execute()
        )

        if not new_gym.data:
            raise RuntimeError("The gym workspace could not be created.")
        gym = new_gym.data[0]

    st.session_state.gym_id = gym["id"]
    business_name = gym["business_name"]

except Exception as error:
    st.session_state.gym_id = None
    st.error("We couldn't load your gym workspace. Please try refreshing the page.")
    with st.expander("Technical details"):
        st.code(str(error))
    st.stop()


with st.container(key="top_nav"):
    brand_col, nav_col, user_col = st.columns([2.2, 7, 1.1], vertical_alignment="center")

    with brand_col:
        brand_logo()
        st.markdown(
            '<div class="brand-tagline">Smarter insights. Stronger member retention.</div>',
            unsafe_allow_html=True,
        )

    with nav_col:
        page = st.radio(
            "WORKSPACE",
            NAV_PAGES,
            horizontal=True,
            key="selected_page",
            label_visibility="collapsed",
        )

    with user_col:
        st.button("Log Out", on_click=log_out, use_container_width=True, key="logout_button_main")


# personal greeting
current_hour = datetime.now(ZoneInfo("Africa/Lagos")).hour
if current_hour < 12:
    greeting = "Good morning"
elif current_hour < 17:
    greeting = "Good afternoon"
else:
    greeting = "Good evening"

safe_user_name = html.escape(str(user_name))
safe_business_name = html.escape(str(business_name))


# =========================================================
# 11. DASHBOARD
# =========================================================

if page == "Dashboard":
    st.markdown(
        """
        <div style="background-color: #111827; padding: 22px 24px; border-left: 5px solid #B7F34A; border-radius: 16px; margin-bottom: 18px;">
            <div style="color:#B7F34A; font-size:14px; font-weight:700; letter-spacing:0.18em; text-transform:uppercase;">Your Fitness Workspace</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.subheader(f"{greeting}, {safe_user_name}! 👋")
    st.markdown(f"Welcome to **{safe_business_name}**. Let's build a stronger, smarter fitness business.")

    st.markdown(
        """
        <div class="hero">
            <div class="hero-inner">
                <div class="hero-pill"><span class="hero-dot"></span>Fitness intelligence platform</div>
                <div class="hero-title">Smarter insights.<br><span class="hero-gradient">Stronger member retention.</span></div>
                <div class="hero-sub">
                    Explore experimental machine-learning estimates using gym membership and attendance information.
                    Turn member activity data into opportunities for further investigation.
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="section-label">How it works</div>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(
            """
            <div class="feature-card">
                <div class="feature-no">01</div>
                <div class="mini-icon">""" + icon("upload", 18) + """</div>
                <h4>Input</h4>
                <p>Provide membership, attendance, renewal, and personal-training information.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            """
            <div class="feature-card">
                <div class="feature-no">02</div>
                <div class="mini-icon">""" + icon("gauge", 18) + """</div>
                <h4>Analyse</h4>
                <p>The model processes five features to estimate cancellation probability.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            """
            <div class="feature-card">
                <div class="feature-no">03</div>
                <div class="mini-icon">""" + icon("chat", 18) + """</div>
                <h4>Explore</h4>
                <p>Review the experimental estimate and investigate attendance patterns.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown('<div class="section-label">Get started</div>', unsafe_allow_html=True)

    left, right = st.columns(2)
    with left:
        st.markdown("### Individual assessment")
        st.write("Explore an estimate for one hypothetical member.")
        if st.button("Open Member Assessment", use_container_width=True):
            st.session_state["selected_page"] = "Member Assessment"
            st.rerun()

    with right:
        st.markdown("### Batch assessment")
        st.write("Explore a CSV of membership records and download the resulting estimates.")
        if st.button("Open Batch Assessment", use_container_width=True):
            st.session_state["selected_page"] = "Batch Assessment"
            st.rerun()


# =========================================================
# 12. MEMBER MANAGEMENT
# =========================================================

elif page == "Member Management":
    st.markdown("## Member Management")
    st.write("Register and manage members at your gym.")

    gym_id = st.session_state.get("gym_id")
    if not gym_id:
        st.warning("No gym workspace found for your account.")
    else:
        st.markdown("### Register a New Member")

        with st.form("register_member_form", clear_on_submit=True):
            full_name = st.text_input("Full name")
            email = st.text_input("Email address")
            phone = st.text_input("Phone number")

            col1, col2 = st.columns(2)
            with col1:
                age = st.number_input("Age", min_value=16, max_value=120, value=25)
                weight_kg = st.number_input("Weight (kg)", min_value=1.0, max_value=500.0, value=70.0, step=0.5)
            with col2:
                height_cm = st.number_input("Height (cm)", min_value=50.0, max_value=260.0, value=170.0, step=0.5)
                fitness_goal = st.selectbox(
                    "Fitness goal",
                    ["Weight loss", "Muscle gain", "General fitness", "Strength", "Endurance", "Sports performance"],
                )

            submitted = st.form_submit_button("Register Member", use_container_width=True)

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
                    "fitness_goal": fitness_goal,
                }

                if email.strip():
                    member_data["email"] = email.strip()
                if phone.strip():
                    member_data["phone"] = phone.strip()

                try:
                    supabase.table("members").insert(member_data).execute()
                    st.success("Member registered successfully!")
                    st.rerun()
                except Exception as error:
                    st.error(f"Could not register member: {error}")

        st.markdown("---")
        st.markdown("### Registered Members")
        try:
            result = (
                supabase.table("members")
                .select("full_name, email, phone, age, weight_kg, height_cm, fitness_goal, created_at")
                .eq("gym_id", gym_id)
                .order("created_at", desc=True)
                .execute()
            )

            if result.data:
                members_df = pd.DataFrame(result.data)
                st.metric("Total Members", len(members_df))
                st.dataframe(members_df, use_container_width=True, hide_index=True)
            else:
                st.info("No members registered yet. Register your first member above.")
        except Exception as error:
            st.error(f"Could not load members: {error}")


# =========================================================
# 13. MEMBER ASSESSMENT
# =========================================================

elif page == "Member Assessment":
    st.markdown("## Member Assessment")
    st.write("Enter a hypothetical member's details to explore the output of the trained model.")

    with st.form("member_assessment_form"):
        membership_type = st.selectbox("Membership type", ["Monthly", "Quarterly", "Annual"])

        col1, col2 = st.columns(2)
        with col1:
            days_since_last_visit = st.number_input("Days since last visit", min_value=0, max_value=365, value=7)
            visits_previous_30_days = st.number_input("Visits in previous 30 days", min_value=0, max_value=100, value=10)
            renewal_due_days = st.number_input("Days until renewal", min_value=0, max_value=365, value=14)
        with col2:
            visits_last_30_days = st.number_input("Visits in most recent 30 days", min_value=0, max_value=100, value=5)
            pt_sessions_attended = st.number_input("PT sessions attended", min_value=0, max_value=100, value=2)

        submitted = st.form_submit_button("Generate Assessment", use_container_width=True)

    if submitted:
        member = pd.DataFrame([{
            "membership_type": membership_type,
            "days_since_last_visit": days_since_last_visit,
            "visits_previous_30_days": visits_previous_30_days,
            "visits_last_30_days": visits_last_30_days,
            "renewal_due_days": renewal_due_days,
            "pt_sessions_attended": pt_sessions_attended,
        }])

        try:
            result = assess_members(member).iloc[0]
            probability = float(result["cancellation_probability"])
            risk = result["risk_category"]

            st.markdown("---")
            st.markdown("### Assessment Results")

            col_a, col_b = st.columns(2)
            col_a.metric("Estimated Cancellation Probability", f"{probability:.1%}")
            col_b.metric("Provisional Risk Category", risk)

            st.progress(max(0.0, min(1.0, probability)))

            attendance_change = visits_last_30_days - visits_previous_30_days
            a, b, c = st.columns(3)
            a.metric("Previous 30 Days", int(visits_previous_30_days))
            b.metric("Recent 30 Days", int(visits_last_30_days))
            c.metric("Attendance Change", f"{attendance_change:+}")

            if attendance_change < 0:
                st.warning("WARNING: MEMBER CHECK-IN RECOMMENDED\n\nAttendance has dropped compared with the previous 30 days.")
            elif attendance_change > 0:
                st.success("POSITIVE ENGAGEMENT\n\nAttendance has improved compared with the previous 30 days.")
            else:
                st.info("ENGAGEMENT STABLE\n\nAttendance is unchanged compared with the previous 30 days.")

            if risk == "High":
                st.error("PRIORITY FOLLOW-UP\n\nThis member requires a priority review and a personal check-in.")
            elif risk == "Medium":
                st.warning("WARNING: MEMBER ENGAGEMENT NEEDS ATTENTION\n\nReview this member's recent attendance and upcoming renewal date.")
            else:
                st.success("MAINTAIN MEMBER ENGAGEMENT\n\nContinue monitoring attendance and supporting the member's goals.")

        except Exception as error:
            st.error(f"Assessment failed: {error}")


# =========================================================
# 14. BATCH ASSESSMENT
# =========================================================

elif page == "Batch Assessment":
    st.markdown(
        """
        <div class="hero">
            <div class="hero-inner">
                <div class="hero-pill"><span class="hero-dot"></span>GYMPULSE Ai · batch intelligence</div>
                <div class="hero-title">Batch Assessment</div>
                <div class="hero-sub">
                    Analyse multiple membership records in one workflow.
                    Explore experimental cancellation-risk estimates and identify patterns that may deserve further review.
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="section-label">Required data</div>', unsafe_allow_html=True)
    st.markdown(
        "<p style='color: #9CA3AF;'>Your CSV file must contain all six fields below. Use the exact column names shown.</p>",
        unsafe_allow_html=True,
    )

    required_fields = [
        ("01", "Membership Type", "membership_type", "The member's membership category."),
        ("02", "Days Since Last Visit", "days_since_last_visit", "How many days have passed since the last visit."),
        ("03", "Previous 30-Day Visits", "visits_previous_30_days", "Attendance during the preceding 30-day period."),
        ("04", "Last 30-Day Visits", "visits_last_30_days", "Recent attendance activity."),
        ("05", "Renewal Due Days", "renewal_due_days", "Days remaining until renewal is due."),
        ("06", "PT Sessions Attended", "pt_sessions_attended", "Number of personal-training sessions attended."),
    ]

    for i in range(0, len(required_fields), 3):
        fields = required_fields[i : i + 3]
        cols = st.columns(3)
        for col, item in zip(cols, fields):
            number, title, field_name, description = item
            with col:
                st.markdown(
                    f"""
                    <div style="background-color:#111827; border:1px solid #273449; border-radius:14px; padding:18px; min-height: 150px;">
                        <div style="color:#B7F34A; font-weight:700;">FIELD {number}</div>
                        <div style="color:#FFFFFF; font-size:16px; margin-top:6px;">{title}</div>
                        <div style="color:#B7F34A; font-size:12px; margin-top:6px;">{field_name}</div>
                        <div style="color:#9CA3AF; font-size:13px; line-height:1.6; margin-top:8px;">{description}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    st.markdown("<br>", unsafe_allow_html=True)
    uploaded_file = st.file_uploader("Choose a CSV file", type=["csv"], help="Upload a CSV containing all six required columns.")

    if uploaded_file is not None:
        try:
            uploaded_data = pd.read_csv(uploaded_file)

            if uploaded_data.empty:
                st.error("The uploaded CSV contains no records.")
                st.stop()

            required_columns = [
                "membership_type",
                "days_since_last_visit",
                "visits_previous_30_days",
                "visits_last_30_days",
                "renewal_due_days",
                "pt_sessions_attended",
            ]

            missing_columns = [col for col in required_columns if col not in uploaded_data.columns]
            if missing_columns:
                st.error("Your CSV is missing the following required columns: " + ", ".join(missing_columns))
                st.info("Check the column names in the Required Data section above and upload the corrected file.")
                st.stop()

            with st.expander("Preview uploaded data", expanded=True):
                st.dataframe(uploaded_data.head(10), use_container_width=True, hide_index=True)

            if st.button("Assess All Members", use_container_width=True, type="primary"):
                with st.spinner("Assessing membership records..."):
                    results = assess_members(uploaded_data)

                total_members = len(results)
                high_risk = int((results["risk_category"] == "High").sum())
                medium_risk = int((results["risk_category"] == "Medium").sum())
                low_risk = int((results["risk_category"] == "Low").sum())

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Records Assessed", f"{total_members:,}")
                c2.metric("High Risk", f"{high_risk:,}")
                c3.metric("Medium Risk", f"{medium_risk:,}")
                c4.metric("Low Risk", f"{low_risk:,}")

                st.markdown('<div class="section-label">Member assessment results</div>', unsafe_allow_html=True)
                st.dataframe(results, use_container_width=True, hide_index=True)

                csv_output = results.to_csv(index=False).encode("utf-8")
                st.download_button(
                    label="Download Assessment Results CSV",
                    data=csv_output,
                    file_name="gympulse_assessment_results.csv",
                    mime="text/csv",
                    use_container_width=True,
                    type="primary",
                )

        except Exception as error:
            st.error("Could not process the uploaded file. Check the required columns, values, and format.")
            with st.expander("Technical details"):
                st.code(str(error))


# =========================================================
# 15. MODEL INSIGHTS
# =========================================================

elif page == "Model Insights":
    st.markdown("## Model Insights")
    st.write("Explore how the model's estimates change when one input varies while the other inputs remain constant.")

    st.info("This experiment shows how the model responds to different inputs. It does not establish causation or real-world accuracy.")

    col1, col2 = st.columns(2)
    with col1:
        insight_membership = st.selectbox("Membership type", ["Monthly", "Quarterly", "Annual"])
        insight_previous = st.number_input("Previous 30-day visits", min_value=0, max_value=100, value=10)
        insight_recent = st.number_input("Recent 30-day visits", min_value=0, max_value=100, value=5)
    with col2:
        insight_renewal = st.number_input("Days until renewal", min_value=0, max_value=365, value=14)
        insight_pt = st.number_input("PT sessions attended", min_value=0, max_value=100, value=2)
        max_days = st.slider("Maximum days since last visit to explore", min_value=7, max_value=90, value=30)

    if st.button("Run Sensitivity Experiment", use_container_width=True):
        scenario_days = list(range(0, max_days + 1, max(1, max_days // 10)))
        if max_days not in scenario_days:
            scenario_days.append(max_days)

        scenarios = pd.DataFrame({
            "membership_type": [insight_membership] * len(scenario_days),
            "days_since_last_visit": scenario_days,
            "visits_previous_30_days": [insight_previous] * len(scenario_days),
            "visits_last_30_days": [insight_recent] * len(scenario_days),
            "renewal_due_days": [insight_renewal] * len(scenario_days),
            "pt_sessions_attended": [insight_pt] * len(scenario_days),
        })

        try:
            sensitivity_results = assess_members(scenarios).sort_values("days_since_last_visit")

            chart_data = sensitivity_results.set_index("days_since_last_visit")[["cancellation_probability"]].rename(columns={"cancellation_probability": "Estimated cancellation probability"})
            st.line_chart(chart_data, use_container_width=True)

            display_results = sensitivity_results[["days_since_last_visit", "cancellation_probability", "risk_category"]].rename(columns={
                "days_since_last_visit": "Days since last visit",
                "cancellation_probability": "Estimated probability",
                "risk_category": "Provisional risk category",
            })
            st.dataframe(display_results, hide_index=True, use_container_width=True)

            first_probability = float(sensitivity_results.iloc[0]["cancellation_probability"])
            last_probability = float(sensitivity_results.iloc[-1]["cancellation_probability"])
            st.metric("Change across tested scenarios", f"{(last_probability - first_probability) * 100:+.1f} percentage points")

        except Exception as error:
            st.error("The sensitivity experiment could not be completed.")
            with st.expander("Technical details"):
                st.code(str(error))


# =========================================================
# 16. ABOUT THE MODEL
# =========================================================

elif page == "About the Model":
    st.markdown("## About GymPulse Ai")

    st.write("GymPulse Ai is a machine-learning portfolio project exploring gym membership cancellation-risk assessment.")

    c1, c2, c3 = st.columns(3)
    c1.metric("Algorithm", "Logistic Regression")
    c2.metric("Input Features", "5")
    c3.metric("Training Dataset", "Synthetic")

    st.metric("Medium-Risk Threshold", "30%")

    st.markdown("### Features used by the model")
    st.dataframe(
        pd.DataFrame({
            "Feature": ["Membership type", "Days since last visit", "Attendance change", "Days until renewal", "PT sessions attended"],
            "Description": [
                "Member's membership category",
                "Time since the most recent visit",
                "Recent visits minus previous-period visits",
                "Days remaining before renewal",
                "Recorded personal-training attendance",
            ],
        }),
        hide_index=True,
        use_container_width=True,
    )

    st.markdown("### Recorded development test results")
    st.dataframe(
        pd.DataFrame({
            "Metric": ["Accuracy", "Precision", "Recall", "F1-score", "ROC-AUC"],
            "Recorded result": ["59.0%", "44.9%", "75.7%", "56.4%", "65.1%"],
        }),
        hide_index=True,
        use_container_width=True,
    )

    st.warning("These metrics describe earlier evaluation on synthetic data. They do not establish performance on real gym members.")

    st.markdown("### Responsible development")
    st.write("Before operational use, the model would require real-world evaluation, data-quality checks, probability calibration, and privacy safeguards.")

    st.markdown("### Project scope")
    st.write("This app demonstrates model integration, input validation, interactive predictions, CSV processing, and sensitivity analysis. It is an educational prototype rather than a validated commercial prediction system.")


# =========================================================
# 17. FAQS
# =========================================================

elif page == "FAQs":
    st.markdown("## Frequently Asked Questions")

    with st.expander("How do I add members to my gym?"):
        st.write("Open Member Management, fill in the member details, and click Register Member.")

    with st.expander("Is my gym's data separate from other gyms?"):
        st.write("Yes. Each account has its own gym workspace, and the member list is scoped to your gym.")

    with st.expander("How do I log out?"):
        st.write("Click Log Out in the top-right corner to end your session.")

    with st.expander("What does the cancellation probability mean?"):
        st.write("It is the model's estimate of how likely a member is to cancel, based on membership type, attendance, renewal timing, and PT activity. It is a guide, not a guarantee.")

    with st.expander("What do High, Medium, and Low risk mean?"):
        st.write("- High: 50% or more\n- Medium: 30% to just under 50%\n- Low: below 30%")

    with st.expander("How accurate are the predictions?"):
        st.write("The model was trained on synthetic data, so its accuracy on real gym members has not been established.")

    with st.expander("What should I do for a high-risk member?"):
        st.write("Check their recent attendance and renewal date, then reach out personally and offer support.")

    with st.expander("What columns does my CSV need?"):
        st.write("Your file must include these exact column names:\n- membership_type\n- days_since_last_visit\n- visits_previous_30_days\n- visits_last_30_days\n- renewal_due_days\n- pt_sessions_attended")

    with st.expander("Why did my CSV upload fail?"):
        st.write("The common causes are misspelled column names, empty cells, negative values, or invalid membership types.")

    with st.expander("How should I handle member data?"):
        st.write("Only collect information members have agreed to share, keep your login private, and log out on shared devices.")


# =========================================================
# 18. FOOTER
# =========================================================

st.markdown('<div class="footer-text">© GYMPULSE Ai · Smarter insights. Stronger member retention.</div>', unsafe_allow_html=True)
