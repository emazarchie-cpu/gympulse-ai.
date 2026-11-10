"""GymPulse AI · Stay signed in ("remember me"), the way most websites do it.

Phones close a website's live connection as soon as you switch apps, and the server forgets a
disconnected visit after a while. Without this, coming back to GymPulse meant signing in again.

* After sign-in, the login's refresh token is saved in a secure cookie for 30 days (Secure, SameSite=Lax,
  only sent to usegympulseai.com).
* When a new visit starts without a login, that cookie signs the person back in silently.
* Supabase rotates refresh tokens, so the cookie is updated whenever the token changes.
* Log out deletes the cookie, and a token that no longer works is deleted too.
"""
import json

import streamlit as st

COOKIE = "gp_rt"
DAYS = 30


def _js(script):
    """Run a tiny script on the page (an invisible frame on the same site)."""
    import streamlit.components.v1 as components
    with st.container(key="gp_rt_box"):
        st.markdown("<style>.st-key-gp_rt_box{display:none}</style>", unsafe_allow_html=True)
        components.html(f"<script>try{{{script}}}catch(e){{}}</script>", height=0)


def saved():
    try:
        return st.context.cookies.get(COOKIE) or None
    except Exception:
        return None


def write(refresh_token):
    """Save (or update) the cookie. Only writes when the token changed, so it costs nothing per tap."""
    if not refresh_token or st.session_state.get("_rt_saved") == refresh_token:
        return
    st.session_state["_rt_saved"] = refresh_token
    value = json.dumps(refresh_token)
    _js(f"parent.document.cookie = '{COOKIE}=' + encodeURIComponent({value}) + "
        f"'; Max-Age={DAYS * 86400}; Path=/; Secure; SameSite=Lax';")


def clear():
    st.session_state["_rt_saved"] = None
    _js(f"parent.document.cookie = '{COOKIE}=; Max-Age=0; Path=/; Secure; SameSite=Lax';")


def forget_on_next_run():
    """Called from Log out (a button callback can't draw anything): stop the silent sign-in and
    delete the cookie on the next run."""
    st.session_state["_rt_tried"] = True
    st.session_state["_rt_clear"] = True


def restore(supabase):
    """Sign back in from the cookie once per visit. Returns the Supabase user, or None."""
    if st.session_state.pop("_rt_clear", False):
        clear()
        return None
    if st.session_state.get("_rt_tried"):
        return None
    st.session_state["_rt_tried"] = True
    token = saved()
    if not token:
        return None
    try:
        res = supabase.auth.refresh_session(token)
        user = res.user or (res.session.user if res.session else None)
    except Exception:
        user, res = None, None
    if not user:
        clear()                                   # expired, revoked or used: don't try again
        return None
    if res.session and res.session.refresh_token:
        write(res.session.refresh_token)
    return user
