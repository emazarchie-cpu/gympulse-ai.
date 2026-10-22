import os
import textwrap

import joblib
import pandas as pd
import streamlit as st
from supabase import create_client


# =========================================================
# 1. PAGE CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="GymPulse AI | Member Intelligence",
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

    [data-testid="stHeader"] {
        background: rgba(11,16,32,0.95);
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

    .stButton > button,
    .stFormSubmitButton > button {
        background: var(--lime);
        color: #10182A;
        border: none;
        border-radius: 10px;
        font-weight: 800;
        min-height: 43px;
        transition: 0.2s ease;
    }

    .stButton > button:hover,
    .stFormSubmitButton > button:hover {
        background: #D0FF7A;
        color: #10182A;
        border: none;
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
        color: #B7F34A !important;
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

    .st-key-top_nav div[role="radiogroup"] {
        gap: 6px;
        flex-wrap: wrap;
    }

    .st-key-top_nav div[role="radiogroup"] label {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 10px;
        padding: 8px 14px;
        cursor: pointer;
    }

    .st-key-top_nav div[role="radiogroup"] label > div:first-child {
        display: none;
    }

    .st-key-top_nav div[role="radiogroup"] label p {
        font-size: 13px;
        font-weight: 700;
        color: var(--white);
        margin: 0;
    }

    .st-key-top_nav div[role="radiogroup"] label:has(input:checked) {
        background: var(--lime);
        border-color: var(--lime);
    }

    .st-key-top_nav div[role="radiogroup"] label:has(input:checked) p {
        color: #10182A;
    }
    .footer {
        text-align: center;
        color: var(--muted);
        font-size: 11px;
        padding: 20px 0;
    }

    </style>
    """,
    unsafe_allow_html=True
)

# =========================================================
# 3. USER AUTHENTICATION
# =========================================================

from datetime import datetime
from zoneinfo import ZoneInfo


# Connect to Supabase once per user session
if "supabase_client" not in st.session_state:
    st.session_state.supabase_client = create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_KEY"]
    )

supabase = st.session_state.supabase_client


# Initialise login state
if "auth_user" not in st.session_state:
    st.session_state.auth_user = None

if "user_profile" not in st.session_state:
    st.session_state.user_profile = None


# Show login and registration until authenticated
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

    # Center the logo
    logo_col1, logo_col2, logo_col3 = st.columns([1, 1, 1])

    with logo_col2:
        st.image(LOGO_PATH, width=115)

    # Heading and tagline
    st.markdown(
        """
        <div style="text-align: center; padding: 0 0 20px;">
            <div style="font-size: 42px; font-weight: 800; line-height: 1.1;">
                GYM<span style="color:#B7F34A;">PULSE</span> AI
            </div>
            <p style="color:#9AA8BD; font-size:12px; margin-top:5px; margin-bottom:0;">
                Smarter insights. Stronger member retention.
            </p>
        </div>
        """,
        unsafe_allow_html=True
    )

    login_tab, signup_tab = st.tabs(
        ["Log In", "Create Account"]
    )

    # -------------------------
    # LOGIN
    # -------------------------
    with login_tab:

        st.subheader("Welcome back")

        with st.form("login_form"):

            login_email = st.text_input("Email address")
            login_password = st.text_input(
                "Password",
                type="password"
            )

            login_submitted = st.form_submit_button(
                "Log In",
                use_container_width=True
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
                            st.session_state.user_profile = (
                                profile_result.data[0]
                            )
                        else:
                            st.session_state.user_profile = {
                                "full_name": "User",
                                "business_name": "My Gym"
                            }

                        st.rerun()

                except Exception:
                    st.error(
                        "Login failed. Check your credentials "
                        "and confirm your email address."
                    )

    # -------------------------
    # SIGNUP
    # -------------------------
    with signup_tab:

        st.subheader("Create your workspace")

        with st.form("signup_form"):

            full_name = st.text_input("Your full name")

            business_name = st.text_input(
                "Gym or company name",
                placeholder="e.g. Nuelarch Gym"
            )

            signup_email = st.text_input(
                "Email address",
                key="signup_email"
            )

            signup_password = st.text_input(
                "Create password",
                type="password",
                key="signup_password"
            )

            confirm_password = st.text_input(
                "Confirm password",
                type="password"
            )

            signup_submitted = st.form_submit_button(
                "Create Free Account",
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

            elif signup_password != confirm_password:
                st.error("Your passwords do not match.")

            elif len(signup_password) < 8:
                st.warning(
                    "Your password must contain at least 8 characters."
                )

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
                            st.session_state.user_profile = (
                                profile_result.data[0]
                            )
                        else:
                            st.session_state.user_profile = {
                                "full_name": full_name.strip(),
                                "business_name": business_name.strip()
                            }

                        st.success("Account created successfully!")
                        st.rerun()

                    else:
                        st.success(
                            "Registration submitted! Check your email "
                            "for a confirmation link, then return here "
                            "to log in."
                        )

                except Exception:
                    st.error(
                        "Registration failed. Your email may already "
                        "be registered, or the request may have failed. "
                        "Please check your details and try again."
                    )

    st.stop()


# =========================================================
# 4. PERSONALIZED WORKSPACE HEADER
# =========================================================

profile = st.session_state.user_profile or {}

user_name = profile.get("full_name", "User")
business_name = profile.get("business_name", "My Gym")

owner_id = st.session_state.auth_user["id"]

try:
    # Retrieve the gym belonging to the authenticated owner
    gym_result = (
        supabase.table("gyms")
        .select("*")
        .eq("owner_id", owner_id)
        .limit(1)
        .execute()
    )

    # Create a workspace if this owner does not have one
    if gym_result.data:
        gym = gym_result.data[0]

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
if "navigate_to" in st.session_state:
    st.session_state["selected_page"] = st.session_state.pop(
        "navigate_to"
    )

    

def go_home():
    st.session_state["selected_page"] = "Dashboard"


def log_out():
    """End the Supabase session and return to the login page."""
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
    "FAQs"
]

with st.container(key="top_nav"):

    brand_col, nav_col, user_col = st.columns(
        [1.5, 7, 1.2],
        vertical_alignment="center"
    )

    with brand_col:
        st.button(
            "PULSE",
            on_click=go_home,
            key="brand_home"
        )

    with nav_col:
        page = st.radio(
            "WORKSPACE",
            NAV_PAGES,
            key="selected_page",
            horizontal=True,
            label_visibility="collapsed"
        )

    with user_col:
        st.button(
            "Log Out",
            on_click=log_out,
            use_container_width=True,
            key="logout_button_main"
        )

st.markdown("---")
    
# =========================================================
# PERSONALIZED GREETING VARIABLES
# =========================================================

from datetime import datetime
from zoneinfo import ZoneInfo
import html

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
# 7. SHARED HEADER — DASHBOARD ONLY
# =========================================================

if page == "Dashboard":

    # YOUR FITNESS WORKSPACE
    st.markdown(
        """
        <div style="
            background-color: #111827;
            padding: 24px;
            border-radius: 16px;
            border-left: 5px solid #B7F34A;
            margin-bottom: 24px;
        ">
            <p style="
                color: #B7F34A;
                font-size: 14px;
                margin-bottom: 8px;
                font-weight: 600;
            ">
                YOUR FITNESS WORKSPACE
            </p>
        </div>
        """,
        unsafe_allow_html=True
    )

    # PERSONALIZED GREETING
    st.subheader(f"{greeting}, {safe_user_name}! 👋")

    st.markdown(
        f"Welcome to **{safe_business_name}**. "
        "Let's build a stronger, smarter fitness business."
    )

    # FITNESS INTELLIGENCE PLATFORM
    st.markdown(
        """
        <div class="hero">
            <div class="hero-eyebrow">
                FITNESS INTELLIGENCE PLATFORM
            </div>
            <div class="hero-title">
                Smarter insights.<br>Stronger member retention.
            </div>
            <div class="hero-description">
                Explore experimental machine-learning estimates
                using gym membership and attendance information.
                Turn member activity data into opportunities for
                further investigation.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )
# =========================================================
# 8. DASHBOARD
# =========================================================
if page == "Dashboard":


# Personalized greeting — Dashboard only

# =====================================================
# PERSONALIZED GREETING VARIABLES
# =====================================================

# =====================================================
# EXISTING DASHBOARD CONTENT
# =====================================================
    st.markdown("## Dashboard")

    st.write(
        "Your starting point for exploring membership "
        "cancellation-risk estimates."
    )

    st.markdown(
        '<div class="section-label">HOW IT WORKS</div>',
        unsafe_allow_html=True
    )

    step1, step2, step3 = st.columns(3)

    with step1:
        st.markdown("### 01 | Input")

        st.write(
            "Provide membership, attendance, renewal, "
            "and personal-training information."
        )

    with step2:
        st.markdown("### 02 | Analyse")

        st.write(
            "The existing model processes five features "
            "to estimate cancellation probability."
        )

    with step3:
        st.markdown("### 03 | Explore")

        st.write(
            "Review the experimental estimate and investigate "
            "attendance patterns."
        )

    st.markdown(
        '<div class="section-label">GET STARTED</div>',
        unsafe_allow_html=True
    )

    left, right = st.columns(2)

    with left:
        st.markdown("### Individual assessment")

        st.write(
            "Explore an estimate for one hypothetical member."
        )

        if st.button(
            "Open Member Assessment",
            use_container_width=True
        ):
            st.session_state["navigate_to"] = "Member Assessment"
            st.rerun()

    with right:
        st.markdown("### Batch assessment")

        st.write(
            "Explore a CSV of membership records and "
            "download the resulting estimates."
        )

        if st.button(
            "Open Batch Assessment",
            use_container_width=True
        ):
            st.session_state["navigate_to"] = "Batch Assessment"
            st.rerun()


    
# =========================================================
# 9. MEMBER MANAGEMENT
# =========================================================

elif page == "Member Management":

    st.markdown("## Member Management")
    st.write("Register and manage members at your gym.")

    gym_id = st.session_state.get("gym_id")

    if not gym_id:
        st.warning("No gym workspace found for your account.")
    else:
        st.markdown("### Register a New Member")

        with st.form("register_member_form"):

            full_name = st.text_input("Full name")
            email = st.text_input("Email address")
            phone = st.text_input("Phone number")

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

        try:
            result = (
                supabase.table("members")
                .select(
                    "full_name, email, phone, age, "
                    "weight_kg, height_cm, fitness_goal, created_at"
                )
                .eq("gym_id", gym_id)
                .order("created_at", desc=True)
                .execute()
            )

            if result.data:
                members_df = pd.DataFrame(result.data)

                st.metric("Total Members", len(members_df))

                st.dataframe(
                    members_df,
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info(
                    "No members registered yet. "
                    "Register your first member above."
                )

        except Exception as error:
            st.error(f"Could not load members: {error}")


# =========================================================
# 10. INDIVIDUAL MEMBER ASSESSMENT
# =========================================================

elif page == "Member Assessment":

    st.markdown("## Member Assessment")

    st.write(
        "Enter a hypothetical member's details to explore "
        "the output of the trained model."
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
    <div style="color: #B7F34A; font-weight: 700;">
        FIELD {number}
    </div>
    <div style="color: #FFFFFF; font-size: 16px;">
        {title}
    </div>
    <div style="color: #B7F34A; font-size: 12px;">
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
    border-left: 5px solid #B7F34A;
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

    st.markdown("## Model Insights")

    st.write(
        "Explore how the model's estimates change when one input "
        "varies while the other inputs remain constant."
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

            st.line_chart(
                chart_data,
                y="Estimated cancellation probability",
                x_label="Days since last visit",
                y_label="Estimated probability",
                use_container_width=True
            )

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

    st.markdown("## About GymPulse AI")

    st.write(
        "GymPulse AI is a machine-learning portfolio project "
        "exploring gym membership cancellation-risk assessment."
    )

    st.markdown("### Model architecture")

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Algorithm",
        "Logistic Regression"
    )

    col2.metric(
        "Input Features",
        "5"
    )

    col3.metric(
        "Training Dataset",
        "Synthetic"
    )

    st.metric(
        "Medium-Risk Threshold",
        "30%"
    )

    st.markdown("### Features used by the model")

    st.dataframe(
        pd.DataFrame({
            "Feature": [
                "Membership type",
                "Days since last visit",
                "Attendance change",
                "Days until renewal",
                "PT sessions attended"
            ],
            "Description": [
                "Member's membership category",
                "Time since the most recent visit",
                "Recent visits minus previous-period visits",
                "Days remaining before renewal",
                "Recorded personal-training attendance"
            ]
        }),
        hide_index=True,
        use_container_width=True
    )

    st.markdown("### Recorded development test results")

    metrics = pd.DataFrame({
        "Metric": [
            "Accuracy",
            "Precision",
            "Recall",
            "F1-score",
            "ROC-AUC"
        ],
        "Recorded result": [
            "59.0%",
            "44.9%",
            "75.7%",
            "56.4%",
            "65.1%"
        ]
    })

    st.dataframe(
        metrics,
        hide_index=True,
        use_container_width=True
    )

    st.warning(
        "These metrics describe earlier evaluation on synthetic data. "
        "They do not establish performance on real gym members. "
        "Prior exploration of the test set also means the recorded "
        "test results should be interpreted cautiously."
    )

    st.markdown("### Responsible development")

    st.write(
        "Before operational use, the model would require suitable "
        "real-world evaluation, data-quality checks, probability "
        "calibration, and assessment of errors and potential bias. "
        "Member data should be handled with appropriate permission "
        "and privacy safeguards."
    )

    st.markdown("### Project scope")

    st.write(
        "This application demonstrates model integration, "
        "input validation, interactive predictions, CSV processing, "
        "and controlled sensitivity analysis. It is an educational "
        "prototype rather than a validated commercial prediction system."
    )
# =========================================================
# 13B. FAQs
# =========================================================

elif page == "FAQs":

    st.markdown("## Frequently Asked Questions")

    st.write(
        "Quick answers to help you get the most out of GymPulse AI."
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

