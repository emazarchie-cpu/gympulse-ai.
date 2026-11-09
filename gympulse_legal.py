"""GymPulse AI · Terms, Privacy Policy and Data Processing Agreement.

The documents live in docs/legal/*.md, so the app always shows the same text
the lawyer reviewed. Each gym owner accepts them once per version. New owners
accept at sign-up; existing owners see a short banner until they accept. The
acceptance (version, time, email) is saved in their profile settings.
"""
import os
from datetime import datetime, timezone

import streamlit as st

LEGAL_VERSION = "1.0"
HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = {"terms": "TERMS_OF_SERVICE.md", "privacy": "PRIVACY_POLICY.md", "dpa": "DATA_PROCESSING_AGREEMENT.md"}
TITLES = {"terms": "Terms of Service", "privacy": "Privacy Policy", "dpa": "Data Processing Agreement"}

CONSENT_TEXT = ("I have my members' permission to store their details in GymPulse AI and to email or message them, "
                "and I'll tell my members that my gym uses GymPulse AI.")


COMPANY = "GYMPULSE AI LTD · RC 9996401 · 37, TTC Road, Ikot Ansa, Calabar, Cross River State, Nigeria"


def read(kind):
    try:
        with open(os.path.join(HERE, "docs", "legal", DOCS[kind]), encoding="utf-8") as f:
            text = f.read()
        lines = text.split("\n")
        body = "\n".join(l for l in lines if not l.startswith("# "))     # the dialog has its own title
        return body + f"\n\n---\n*{COMPANY}*"
    except Exception:
        return f"The {TITLES[kind]} is being updated. Email hello@usegympulseai.com for a copy."


@st.dialog("Terms of Service", width="large")
def show_terms():
    st.markdown(read("terms"))


@st.dialog("Privacy Policy", width="large")
def show_privacy():
    st.markdown(read("privacy"))


@st.dialog("Data Processing Agreement", width="large")
def show_dpa():
    st.markdown(read("dpa"))


def acceptance(email):
    return {"version": LEGAL_VERSION, "accepted_at": datetime.now(timezone.utc).isoformat(), "email": email,
            "members_consent": True}


def accepted(profile):
    s = dict((profile or {}).get("settings") or {})
    return (s.get("legal") or {}).get("version") == LEGAL_VERSION


def render_acceptance_banner(supabase, owner_id):
    """For owners who signed up before this version: accept once, then it disappears."""
    profile = st.session_state.get("user_profile") or {}
    if accepted(profile):
        return
    with st.container(border=True):
        st.markdown("**Please review our updated terms.** To keep using GymPulse AI under the Nigeria Data "
                    "Protection Act, we need you to accept these once.")
        c1, c2, c3 = st.columns(3)
        if c1.button("Terms of Service", key="legal_b_terms", use_container_width=True):
            show_terms()
        if c2.button("Privacy Policy", key="legal_b_privacy", use_container_width=True):
            show_privacy()
        if c3.button("Data Processing Agreement", key="legal_b_dpa", use_container_width=True):
            show_dpa()
        a = st.checkbox("I agree to the Terms of Service, Privacy Policy and Data Processing Agreement",
                        key="legal_b_agree")
        b = st.checkbox(CONSENT_TEXT, key="legal_b_consent")
        if st.button("Accept", type="primary", key="legal_b_accept", disabled=not (a and b)):
            email = (st.session_state.get("auth_user") or {}).get("email", "")
            s = {**dict(profile.get("settings") or {}), "legal": acceptance(email)}
            try:
                supabase.table("profiles").update({"settings": s}).eq("id", owner_id).execute()
                profile["settings"] = s
                st.session_state["user_profile"] = profile
                st.rerun()
            except Exception as error:
                st.error(f"Could not save: {error}")
