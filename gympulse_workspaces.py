"""GymPulse AI: Risk Radar, Retention Action Centre, Business Insights, Archie.

Pure logic (build_roster, drivers, playbook, kpis, archie_context) is separate
from Streamlit rendering so it can be tested without a database.
"""
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import streamlit as st

ARCHIE_MODEL = "claude-sonnet-5-5"

ACTIVITY_COLS = [
    "membership_type", "days_since_last_visit", "visits_previous_30_days",
    "visits_last_30_days", "renewal_due_days", "pt_sessions_attended",
]
ACTION_TYPES = ["Personal call", "WhatsApp check-in", "Free PT session",
                "Renewal offer", "Class invite", "Goal review"]
STATUSES = ["To do", "In progress", "Done"]
OUTCOMES = ["Retained", "Cancelled", "No response"]


MOBILE_CSS = """
<style>
@media (hover: none) {
    /* touch screens keep :hover after a tap, which left tabs stuck lime */
    .st-key-top_nav div[role="radiogroup"] label:hover {
        background: transparent !important;
    }
    .st-key-top_nav div[role="radiogroup"] label:hover p {
        color: var(--muted) !important;
    }
    .st-key-top_nav div[role="radiogroup"] label:has(input:checked):hover p {
        color: var(--lime) !important;
    }
}

@media (max-width: 640px) {
    .block-container {
        padding-left: 0.9rem !important;
        padding-right: 0.9rem !important;
        padding-top: 0.6rem !important;
    }

    /* top bar: tagline hidden, tabs scroll sideways in one row */
    .nav-tagline { display: none !important; }
    .st-key-top_nav div[role="radiogroup"] {
        flex-wrap: nowrap !important;
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
        scrollbar-width: none;
    }
    .st-key-top_nav div[role="radiogroup"]::-webkit-scrollbar { display: none; }
    .st-key-top_nav div[role="radiogroup"] label {
        flex: 0 0 auto;
        white-space: nowrap;
        padding: 8px 10px !important;
    }

    /* keep the logo and the wordmark side by side */
    .st-key-top_nav [data-testid="stColumn"]:first-child [data-testid="stHorizontalBlock"] {
        flex-direction: row !important;
        flex-wrap: nowrap !important;
    }
    .st-key-top_nav [data-testid="stColumn"]:first-child [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
        min-width: 0 !important;
    }

    /* metric cards: two per row instead of one long stack */
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

    /* hero banner */
    .hero { padding: 18px !important; }
    .hero-title { font-size: 26px !important; }

    /* 16px inputs stop iPhones zooming in when a field is tapped */
    input, textarea, [data-baseweb="select"] input { font-size: 16px !important; }

    /* easier tap targets */
    .block-container .stButton > button { min-height: 44px; }
}
</style>
"""


LOCK_CSS = """
<style>
@media (max-width: 900px) {
    /* the page may only scroll up and down, never sideways */
    html, body, .stApp,
    [data-testid="stApp"],
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"],
    section.main, .main {
        overflow-x: hidden !important;
        overflow-x: clip !important;
        max-width: 100vw !important;
        overscroll-behavior-x: none;
    }
    html, body, .stApp,
    [data-testid="stApp"],
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"] {
        touch-action: pan-y pinch-zoom !important;
    }
    html, body { position: relative; width: 100%; }
    .block-container {
        max-width: 100% !important;
        overflow-x: hidden;
    }
    [data-testid="stMarkdownContainer"] { overflow-wrap: anywhere; }
    img, svg, video, canvas { max-width: 100%; }
    [data-testid="stRadio"] { max-width: 100%; min-width: 0; }

    /* quarantine the top bar: nothing inside it may widen the page */
    .st-key-top_nav {
        max-width: 100% !important;
        overflow-x: clip;
    }
    .st-key-top_nav [data-testid="stElementContainer"],
    .st-key-top_nav [data-testid="stColumn"] {
        max-width: 100% !important;
    }
    /* swiping past the end of the tab row must not drag the page */
    .st-key-top_nav div[role="radiogroup"],
    .vega-embed, [data-testid="stDataFrame"] {
        overscroll-behavior-x: contain;
    }

    .vega-embed, [data-testid="stVegaLiteChart"] {
        max-width: 100% !important;
        overflow-x: auto;
    }
}
</style>
"""


OVERFLOW_JS = r"""
<div id="out" style="font:12px monospace;color:#fff;background:#111;padding:8px;
 white-space:pre-wrap;word-break:break-all">scanning...</div>
<script>
function scan() {
  try {
    const d = window.parent.document, w = d.documentElement.clientWidth;
    const clipped = (el) => {
      for (let a = el.parentElement; a && a !== d.body; a = a.parentElement) {
        const o = window.parent.getComputedStyle(a).overflowX;
        if (['auto', 'scroll', 'hidden', 'clip'].includes(o)) {
          const r = a.getBoundingClientRect();
          if (r.right <= w + 1 && r.left >= -1) return true;
        }
      }
      return false;
    };
    const bad = [];
    d.querySelectorAll('body *').forEach(el => {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && (r.right > w + 1 || r.left < -1) && !clipped(el)) {
        const tid = el.getAttribute('data-testid');
        const cls = (typeof el.className === 'string' && el.className)
          ? '.' + el.className.split(' ').filter(Boolean).slice(0, 2).join('.') : '';
        bad.push(el.tagName.toLowerCase() + (tid ? '[' + tid + ']' : '') + cls
          + '  right=' + Math.round(r.right) + ' width=' + Math.round(r.width));
      }
    });
    const doc = d.documentElement;
    document.getElementById('out').textContent =
      'viewport=' + w + 'px  scrollWidth=' + doc.scrollWidth + 'px\n'
      + (bad.slice(0, 20).join('\n') || 'no overflowing elements found');
  } catch (e) {
    document.getElementById('out').textContent = 'scan failed: ' + e;
  }
}
scan();
setInterval(scan, 2000);
</script>
"""


LOCK_JS = r"""
<script>
function lockFn() {
  let sx = 0, sy = 0, dir = null;
  const SAFE = '[role="slider"],[data-baseweb="slider"],input,textarea,select,' +
    '[data-testid="stDataFrame"],.vega-embed,[role="radiogroup"],pre,code,canvas';
  function insideScroller(el) {
    for (let n = el; n && n !== document.body && n !== document.documentElement;
         n = n.parentElement) {
      if (n.matches && n.matches(SAFE)) return true;
      const cs = getComputedStyle(n);
      if ((cs.overflowX === 'auto' || cs.overflowX === 'scroll') &&
          n.scrollWidth > n.clientWidth + 1) return true;
    }
    return false;
  }
  document.addEventListener('touchstart', function (e) {
    dir = null;
    if (e.touches.length === 1) { sx = e.touches[0].clientX; sy = e.touches[0].clientY; }
  }, {passive: true});
  document.addEventListener('touchmove', function (e) {
    if (e.touches.length !== 1) return;
    const dx = e.touches[0].clientX - sx, dy = e.touches[0].clientY - sy;
    if (dir === null && (Math.abs(dx) > 6 || Math.abs(dy) > 6)) {
      dir = Math.abs(dx) > Math.abs(dy) ? 'h' : 'v';
    }
    if (dir === 'h' && e.cancelable && !insideScroller(e.target)) e.preventDefault();
  }, {passive: false});
}
(function () {
  try {
    var d = window.parent.document;
    if (d.getElementById('gp-hlock')) return;
    var s = d.createElement('script');
    s.id = 'gp-hlock';
    s.textContent = '(' + lockFn.toString() + ')();';
    d.head.appendChild(s);
  } catch (e) {}
})();
</script>
"""


HELPER_CSS = """
<style>
[data-testid="stElementContainer"]:has(iframe[height="0"]) {
    position: absolute !important;
    width: 0 !important; height: 0 !important;
    margin: 0 !important; padding: 0 !important;
    overflow: hidden !important;
}
</style>
"""


def apply_mobile_styles():
    """Call once, right after the main CSS block in app.py.

    The always-on styles are the phone layout fixes you tested. Anything
    experimental is opt-in through the address bar, so a problem can never
    stop the normal app from opening:
      ?lock=css          CSS-only attempt to stop sideways sliding
      ?lock=1            swipe-lock script only
      ?lock=all          both
      ?debug=overflow    lists elements wider than the screen
    """
    st.markdown(MOBILE_CSS, unsafe_allow_html=True)
    try:
        params = st.query_params
        mode = str(params.get("lock", ""))
        if mode in ("css", "all"):
            st.markdown(LOCK_CSS, unsafe_allow_html=True)
        if mode in ("1", "js", "all"):
            import streamlit.components.v1 as components
            st.markdown(HELPER_CSS, unsafe_allow_html=True)
            components.html(LOCK_JS, height=0)
        if params.get("debug") == "overflow":
            import streamlit.components.v1 as components
            components.html(OVERFLOW_JS, height=320, scrolling=True)
    except Exception:
        pass


# ---------------------------------------------------------------- data
def load_roster(supabase, gym_id, assess_fn):
    """Members + activity, scored by the model. Members without activity
    data are returned in `missing` so the UI can ask for it."""
    members = pd.DataFrame(
        supabase.table("members")
        .select("id, full_name, email, phone, fitness_goal")
        .eq("gym_id", gym_id).eq("archived", False).execute().data or []
    )
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


def load_actions(supabase, gym_id):
    rows = (supabase.table("retention_actions").select("*")
            .eq("gym_id", gym_id).order("created_at", desc=True).execute().data or [])
    return pd.DataFrame(rows)


# ------------------------------------------------------------- logic
def drivers(row):
    """Plain-language reasons a member is flagged (rule-based, transparent)."""
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


def archie_context(roster, actions, business_name):
    k = kpis(roster, actions)
    lines = [f"Gym: {business_name}. Members scored: {k['members_scored']}.",
             f"High risk: {k['high']}, Medium: {k['medium']}.",
             f"Monthly revenue: {k['monthly_revenue']:,.0f}; held by high-risk members: "
             f"{k['high_risk_revenue']:,.0f}; expected monthly loss: {k['expected_loss']:,.0f}.",
             f"Renewals in 30 days that are at risk: {k['renewals_30d_at_risk']}.",
             f"Open retention actions: {k['open_actions']}; members saved: {k['saves']}."]
    if len(roster):
        lines.append("Top 10 at-risk members (name | risk% | reasons | suggested action):")
        for _, r in roster.head(10).iterrows():
            lines.append(f"- {r['full_name']} | {r['cancellation_probability']:.0%} | "
                         f"{r['drivers']} | {r['suggested_action']}")
    return "\n".join(lines)


ARCHIE_SYSTEM = (
    "You are Archie, the retention assistant inside GymPulse AI. You help gym "
    "owners keep members. Use ONLY the data provided; if something is not in it, "
    "say so. The risk scores come from a model trained on synthetic data, so call "
    "them estimates, never facts. Be warm, concrete and brief. When asked for a "
    "message to a member, write it ready to send (WhatsApp length, friendly, no "
    "pressure, no mention of 'risk' or 'cancellation')."
)


def _clean_key(raw):
    """Remove spaces, newlines and stray quotes a paste can add."""
    return str(raw).strip().strip('"').strip("'").strip()


def key_check():
    """Safe description of the key Streamlit is passing in (never the key)."""
    try:
        raw = st.secrets.get("ANTHROPIC_API_KEY")
    except Exception:
        raw = None
    if not raw:
        return "No ANTHROPIC_API_KEY found in secrets."
    key = _clean_key(raw)
    return (f"Key found: {len(key)} characters, starts with "
            f"'{key[:7]}', ends with '...{key[-3:]}', "
            f"valid prefix: {key.startswith('sk-ant-')}.")


def archie_reply(history, context):
    """Claude if ANTHROPIC_API_KEY is set; otherwise a rules-based answer."""
    try:
        raw = st.secrets.get("ANTHROPIC_API_KEY")
    except Exception:
        raw = None
    if not raw:
        return _offline_reply(history[-1]["content"], context), False
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=_clean_key(raw))
        resp = client.messages.create(
            model=ARCHIE_MODEL, max_tokens=700,
            system=ARCHIE_SYSTEM + "\n\nGYM DATA:\n" + context,
            messages=history[-12:],
        )
        return resp.content[0].text, True
    except Exception as e:
        detail = str(e)[:300]
        return (f"Archie couldn't reach the AI service "
                f"({type(e).__name__}): {detail}\n\n"
                + _offline_reply(history[-1]["content"], context)), False


def _offline_reply(question, context):
    return ("Here is today's snapshot from your data:\n\n" + context
            + "\n\n(AI answers are off. " + key_check() + ")")


# ------------------------------------------------------- rendering
def _money(x):
    return f"{x:,.0f}"


def _activity_editor(supabase, gym_id, roster, missing):
    """Add or update visit/renewal data for any member."""
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

    with st.expander("Add or update member activity", expanded=roster.empty):
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
    """Check an uploaded CSV and match each row to a registered member.

    Returns (payload, issues, fatal):
      payload - list of dicts ready to upsert into member_activity
      issues  - DataFrame of rows that were skipped or need a note
      fatal   - list of problems that stop the whole import
    """
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
        line = int(i) + 2          # +2: header row, and spreadsheets start at 1
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


def render_csv_import(supabase, gym_id):
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
    with st.expander("Import activity from CSV"):
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


def _member_manager(supabase, gym_id, roster, missing):
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

    with st.expander(f"Archive, restore or delete members ({len(archived)} archived)"):
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


def _radar_chart(view):
    """Scatter of absence vs risk: fixed colours, 0-100% axis, member tooltips."""
    cols = ["full_name", "days_since_last_visit", "cancellation_probability",
            "risk_category", "monthly_fee"]
    data = view[cols].copy()
    data["cancellation_probability"] = data["cancellation_probability"].astype(float)
    try:
        import altair as alt
        x_max = max(14, float(data["days_since_last_visit"].max()) * 1.1)
        colours = alt.Scale(domain=["High", "Medium", "Low"],
                            range=["#FF6B6B", "#FFC44D", "#B7F34A"])
        chart = (
            alt.Chart(data).mark_circle(opacity=0.85)
            .encode(
                x=alt.X("days_since_last_visit:Q", title="Days since last visit",
                        scale=alt.Scale(domain=[0, x_max])),
                y=alt.Y("cancellation_probability:Q", title="Cancellation estimate",
                        scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format="%")),
                color=alt.Color("risk_category:N", title="Risk", scale=colours),
                size=alt.Size("monthly_fee:Q", legend=None,
                              scale=alt.Scale(range=[90, 420])),
                tooltip=[
                    alt.Tooltip("full_name:N", title="Member"),
                    alt.Tooltip("risk_category:N", title="Risk"),
                    alt.Tooltip("cancellation_probability:Q", title="Estimate", format=".0%"),
                    alt.Tooltip("days_since_last_visit:Q", title="Days away"),
                    alt.Tooltip("monthly_fee:Q", title="Monthly fee", format=",.0f"),
                ],
            )
            .properties(height=320)
        )
        st.altair_chart(chart, use_container_width=True)
    except Exception:
        st.scatter_chart(data, x="days_since_last_visit", y="cancellation_probability",
                         color="risk_category", size="monthly_fee", height=320)


def render_risk_radar(supabase, gym_id, assess_fn):
    st.markdown("## Member Risk Radar")
    flash = st.session_state.pop("flash", None)
    if flash:
        st.success(flash)
    st.write("Every member, scored and ranked, with the reasons behind the flag.")
    try:
        roster, missing = load_roster(supabase, gym_id, assess_fn)
    except Exception as e:
        st.error("Couldn't load the radar. Have you run schema.sql?")
        with st.expander("Technical details"):
            st.code(str(e))
        return
    if roster.empty:
        st.info("Add attendance data so the model can score your members.")
        _activity_editor(supabase, gym_id, roster, missing)
        render_csv_import(supabase, gym_id)
        _member_manager(supabase, gym_id, roster, missing)
        return

    k = kpis(roster, pd.DataFrame())
    c = st.columns(5)
    c[0].metric("Members scored", k["members_scored"])
    c[1].metric("High risk", k["high"])
    c[2].metric("Medium risk", k["medium"])
    c[3].metric("Low risk", k["members_scored"] - k["high"] - k["medium"])
    c[4].metric("Renewals ≤30d at risk", k["renewals_30d_at_risk"])

    _activity_editor(supabase, gym_id, roster, missing)
    render_csv_import(supabase, gym_id)
    _member_manager(supabase, gym_id, roster, missing)

    f1, f2, f3 = st.columns([2, 2, 3])
    levels = f1.multiselect("Risk level", ["High", "Medium", "Low"], ["High", "Medium", "Low"])
    plans = f2.multiselect("Membership", ["Monthly", "Quarterly", "Annual"],
                           ["Monthly", "Quarterly", "Annual"])
    search = f3.text_input("Search member")
    view = roster[roster["risk_category"].isin(levels) & roster["membership_type"].isin(plans)]
    if search:
        view = view[view["full_name"].str.contains(search, case=False, na=False)]
    if view.empty:
        st.info("No members match these filters.")
        return

    st.markdown('<div class="section-label">THE RADAR</div>', unsafe_allow_html=True)
    st.caption("Right = longer absent. Up = higher cancellation estimate.")
    _radar_chart(view)

    st.markdown('<div class="section-label">PRIORITY LIST</div>', unsafe_allow_html=True)
    show = view[["full_name", "risk_category", "cancellation_probability",
                 "suggested_action", "monthly_fee", "drivers"]].rename(columns={
        "full_name": "Member", "risk_category": "Risk",
        "cancellation_probability": "Probability", "drivers": "Why flagged",
        "suggested_action": "Suggested action", "monthly_fee": "Monthly fee"})
    st.dataframe(show, hide_index=True, use_container_width=True,
                 column_config={"Probability": st.column_config.ProgressColumn(
                     format="%.0f%%", min_value=0, max_value=1)})

    if view.empty:
        return
    st.markdown('<div class="section-label">MEMBER DETAIL</div>', unsafe_allow_html=True)
    pick = st.selectbox("Select a member", view["full_name"], key="radar_pick")
    m = view[view["full_name"] == pick].iloc[0]
    d1, d2, d3 = st.columns(3)
    d1.metric("Cancellation estimate", f"{m['cancellation_probability']:.0%}")
    d2.metric("Attendance change", f"{int(m['attendance_change']):+d}")
    d3.metric("Renews in", f"{int(m['renewal_due_days'])} days")
    st.write(f"**Why flagged:** {m['drivers']}")
    st.write(f"**Suggested:** {m['suggested_action']}")
    if st.button(f"Create action for {pick}", key="radar_create"):
        _create_action(supabase, gym_id, m["id"], m["suggested_action"],
                       m["renewal_due_days"])
        st.success("Added to the Retention Action Centre.")
    st.caption("Estimates come from a model trained on synthetic data. Use them "
               "to prioritise conversations, not to make decisions about members.")


def _create_action(supabase, gym_id, member_id, action_type, renewal_days, note=""):
    due = date.today() + timedelta(days=1 if renewal_days <= 14 else 3)
    supabase.table("retention_actions").insert({
        "gym_id": gym_id, "member_id": member_id, "action_type": action_type,
        "due_date": due.isoformat(), "note": note}).execute()


def render_action_centre(supabase, gym_id, assess_fn):
    st.markdown("## Retention Action Centre")
    st.write("Turn risk into follow-ups, track them, and learn what works.")
    try:
        roster, _ = load_roster(supabase, gym_id, assess_fn)
        actions = load_actions(supabase, gym_id)
    except Exception as e:
        st.error("Couldn't load actions. Have you run schema.sql?")
        with st.expander("Technical details"):
            st.code(str(e))
        return
    if roster.empty:
        st.info("Score your members in the Risk Radar first.")
        return
    names = roster.set_index("id")["full_name"].to_dict()
    k = kpis(roster, actions)
    c = st.columns(3)
    c[0].metric("Open actions", k["open_actions"])
    c[1].metric("Members saved", k["saves"])
    c[2].metric("Save rate", "n/a" if k["save_rate"] is None else f"{k['save_rate']:.0%}")

    open_ids = set(actions.loc[actions["status"] != "Done", "member_id"]) if not actions.empty else set()
    todo = roster[(roster["risk_category"] != "Low") & ~roster["id"].isin(open_ids)]
    st.markdown('<div class="section-label">SUGGESTED TODAY</div>', unsafe_allow_html=True)
    if todo.empty:
        st.success("Every at-risk member already has an open action.")
    else:
        top = todo.head(5)
        for _, r in top.iterrows():
            a, b = st.columns([5, 1])
            a.write(f"**{r['full_name']}** · {r['cancellation_probability']:.0%} · "
                    f"{r['suggested_action']}  \n<small>{r['drivers']}</small>",
                    unsafe_allow_html=True)
            if b.button("Add", key=f"add_{r['id']}"):
                _create_action(supabase, gym_id, r["id"], r["suggested_action"],
                               r["renewal_due_days"])
                st.rerun()
        if len(todo) > 1 and st.button("Add all top 5", use_container_width=True):
            for _, r in top.iterrows():
                _create_action(supabase, gym_id, r["id"], r["suggested_action"],
                               r["renewal_due_days"])
            st.rerun()

    st.markdown('<div class="section-label">YOUR BOARD</div>', unsafe_allow_html=True)
    if actions.empty:
        st.info("No actions yet. Add one from the suggestions above.")
        return
    tabs = st.tabs([f"{s} ({int((actions['status'] == s).sum())})" for s in STATUSES])
    for tab, status in zip(tabs, STATUSES):
        with tab:
            sub = actions[actions["status"] == status]
            if sub.empty:
                st.caption("Nothing here.")
            for _, a in sub.iterrows():
                with st.container(border=True):
                    who = names.get(a["member_id"], "Archived member")
                    st.write(f"**{who}** · {a['action_type']} · due {a.get('due_date') or '-'}")
                    if status == "Done":
                        st.caption(f"Outcome: {a.get('outcome') or 'not recorded'}")
                    else:
                        n = st.text_input("Note", a.get("note") or "", key=f"n_{a['id']}")
                        x, y = st.columns(2)
                        if status == "To do" and x.button("Start", key=f"s_{a['id']}"):
                            supabase.table("retention_actions").update(
                                {"status": "In progress", "note": n}).eq("id", a["id"]).execute()
                            st.rerun()
                        out = y.selectbox("Outcome", OUTCOMES, key=f"o_{a['id']}")
                        if y.button("Mark done", key=f"d_{a['id']}"):
                            supabase.table("retention_actions").update({
                                "status": "Done", "outcome": out, "note": n,
                                "completed_at": date.today().isoformat()}
                            ).eq("id", a["id"]).execute()
                            st.rerun()
                    _delete_action_control(supabase, a["id"])


def render_business_insights(supabase, gym_id, assess_fn):
    st.markdown("## Business Insights")
    st.write("What retention is worth, where it leaks, and what's working.")
    try:
        roster, _ = load_roster(supabase, gym_id, assess_fn)
        actions = load_actions(supabase, gym_id)
    except Exception as e:
        st.error("Couldn't load insights. Have you run schema.sql?")
        with st.expander("Technical details"):
            st.code(str(e))
        return
    if roster.empty:
        st.info("Score your members in the Risk Radar first.")
        return
    k = kpis(roster, actions)
    c = st.columns(4)
    c[0].metric("Monthly revenue", _money(k["monthly_revenue"]))
    c[1].metric("Expected monthly loss", _money(k["expected_loss"]))
    c[2].metric("Held by high-risk", _money(k["high_risk_revenue"]))
    c[3].metric("Revenue saved", _money(k["revenue_saved"]))
    st.caption("Expected loss = each member's estimate × their monthly fee. "
               "It is a planning figure from a synthetic-data model, not a forecast.")

    l, r = st.columns(2)
    with l:
        st.markdown('<div class="section-label">RISK MIX</div>', unsafe_allow_html=True)
        mix = roster["risk_category"].value_counts().reindex(["High", "Medium", "Low"]).fillna(0)
        st.bar_chart(mix)
    with r:
        st.markdown('<div class="section-label">REVENUE AT RISK BY PLAN</div>', unsafe_allow_html=True)
        st.bar_chart(roster.groupby("membership_type")["revenue_at_risk"].sum())

    st.markdown('<div class="section-label">RENEWAL PIPELINE</div>', unsafe_allow_html=True)
    bins = pd.cut(roster["renewal_due_days"], [-1, 7, 14, 30, 60, 10_000],
                  labels=["≤7d", "8-14d", "15-30d", "31-60d", "60d+"])
    pipe = roster.groupby(bins, observed=False).agg(
        members=("id", "count"), avg_risk=("cancellation_probability", "mean"),
        fees=("monthly_fee", "sum"))
    pipe["avg_risk"] = pipe["avg_risk"].fillna(0).map("{:.0%}".format)
    st.dataframe(pipe.rename(columns={"members": "Members", "avg_risk": "Avg risk",
                                      "fees": "Monthly fees"}),
                 use_container_width=True)

    st.markdown('<div class="section-label">WHAT WORKS</div>', unsafe_allow_html=True)
    done = actions[actions["status"] == "Done"] if not actions.empty else actions
    if done.empty:
        st.info("Complete some actions with outcomes and this will show which "
                "tactics keep members.")
    else:
        tbl = done.groupby("action_type")["outcome"].agg(
            Done="count", Retained=lambda s: int((s == "Retained").sum()))
        tbl["Save rate"] = (tbl["Retained"] / tbl["Done"]).map("{:.0%}".format)
        st.dataframe(tbl, use_container_width=True)
        if len(done) < 20:
            st.caption("Small sample, so treat these as early signals only.")

    st.markdown('<div class="section-label">TO DO THIS WEEK</div>', unsafe_allow_html=True)
    if k["high"]:
        st.write(f"- Contact the **{k['high']}** high-risk members, starting with "
                 f"the {k['renewals_30d_at_risk']} renewing within 30 days.")
    if k["open_actions"]:
        st.write(f"- Close out **{k['open_actions']}** open actions and record outcomes.")
    if not k["high"] and not k["open_actions"]:
        st.write("- Nothing urgent. Run a goal review with a few Low-risk members.")


ARCHIE_PROMPTS = [
    "Who should I call first today?",
    "Write a WhatsApp message for my most at-risk member",
    "Why is revenue at risk this month?",
    "Give me a 3-step plan for this week",
]


def render_archie(supabase, gym_id, assess_fn, business_name):
    st.markdown("## Archie · your retention assistant")
    st.write("Ask about your members, revenue and follow-ups. Archie reads your "
             "live GymPulse data.")
    try:
        roster, _ = load_roster(supabase, gym_id, assess_fn)
        actions = load_actions(supabase, gym_id)
    except Exception:
        roster, actions = pd.DataFrame(), pd.DataFrame()
    context = archie_context(roster, actions, business_name) if len(roster) \
        else f"Gym: {business_name}. No scored members yet."

    if "archie_msgs" not in st.session_state:
        st.session_state.archie_msgs = []
    cols = st.columns(len(ARCHIE_PROMPTS))
    picked = None
    for col, p in zip(cols, ARCHIE_PROMPTS):
        if col.button(p, key=f"ap_{p}", use_container_width=True):
            picked = p
    for m in st.session_state.archie_msgs:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
    typed = st.chat_input("Ask Archie...")
    question = typed or picked
    if question:
        st.session_state.archie_msgs.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            with st.spinner("Archie is thinking..."):
                reply, live = archie_reply(st.session_state.archie_msgs, context)
            st.markdown(reply)
        st.session_state.archie_msgs.append({"role": "assistant", "content": reply})
    if st.session_state.archie_msgs and st.button("Clear chat"):
        st.session_state.archie_msgs = []
        st.rerun()
    st.caption("Archie can be wrong. Check details before contacting members. "
               "Only your top at-risk members' names and scores are shared with "
               "the AI service.")
