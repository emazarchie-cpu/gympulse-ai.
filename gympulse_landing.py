"""GymPulse AI · website extras: the "what you're losing" calculator.

The owner types their members, average monthly fee and how many leave a month. We show the fees walking out
and what saving some of those members keeps, next to the price of the plan that fits their gym. The kept figure
is deliberately conservative: one more month of fees per member saved, nothing more.
"""
import streamlit as st

import gympulse_workspaces as gw

CALC_CSS = """
html body .st-key-lx_calc { border: 1px solid var(--gp-line); border-radius: 20px; padding: 22px 22px 18px;
    background: radial-gradient(620px 220px at 100% 0%, rgba(53,214,237,0.10), transparent 70%),
                radial-gradient(520px 200px at 0% 100%, rgba(183,243,74,0.08), transparent 70%), var(--gp-s1);
    max-width: 980px; margin: 0 auto; }
.lx-calc-out { display: grid; gap: 10px; }
.lx-calc-big { border-radius: 16px; padding: 16px 18px; border: 1px solid var(--gp-line); background: var(--gp-s2); }
.lx-calc-big span { display: block; color: var(--gp-muted); font-size: 13px; }
.lx-calc-big b { display: block; font-family: var(--gp-display); font-size: 30px; letter-spacing: -0.8px;
    color: var(--gp-text); line-height: 1.15; margin-top: 2px; }
.lx-calc-big em { font-style: normal; color: var(--gp-dim); font-size: 12.5px; }
.lx-calc-big.lose b { color: #FF8A7A; }
.lx-calc-big.keep { border-color: rgba(183,243,74,0.45); }
.lx-calc-big.keep b { background: var(--gp-grad); -webkit-background-clip: text; background-clip: text;
    color: transparent; }
.lx-calc-roi { color: var(--gp-muted); font-size: 13.5px; line-height: 1.6; }
.lx-calc-roi b { color: var(--gp-text); }
.lx-calc-note { color: var(--gp-dim); font-size: 12px; margin-top: 6px; }
@media (max-width: 520px) { .lx-calc-big b { font-size: 25px; } }
"""

SAVE_OPTIONS = {"1 in 10": 0.10, "1 in 5": 0.20, "1 in 4": 0.25, "1 in 3": 0.33}


def _n(x):
    return f"₦{x:,.0f}"


def numbers(members, fee, leave_pct, save):
    """The calculator's figures. Pure, so it can be tested."""
    leaving = members * leave_pct / 100
    lost_month = leaving * fee
    saved = leaving * save
    kept_month = saved * fee
    return {"leaving": leaving, "lost_month": lost_month, "lost_year": lost_month * 12,
            "saved": saved, "kept_month": kept_month, "kept_year": kept_month * 12}


def render_calculator():
    import gympulse_billing as gbill
    gw._md(f"<style>{CALC_CSS}</style>")
    gw._md('''<div class="lx-sec" id="calculator" style="padding-bottom:18px">
      <div class="lx-kicker">What you're losing</div>
      <div class="lx-h2">How much do members who leave cost your gym?</div>
      <div class="lx-sub" style="margin-bottom:8px">Put in your own numbers. Most members who cancel stop coming
        weeks before they say anything, and that's when GymPulse AI flags them.</div></div>''')
    with st.container(key="lx_calc"):
        left, right = st.columns([1, 1.15], gap="large")
        with left:
            members = st.number_input("Active members", min_value=10, max_value=20000, value=300, step=10,
                                      key="calc_members")
            fee = st.number_input("Average monthly fee (₦)", min_value=1000, max_value=1000000, value=15000,
                                  step=1000, key="calc_fee")
            leave = st.slider("Members who leave each month (%)", 1, 25, 6, key="calc_leave",
                              help="Most gyms lose between 3% and 8% of their members every month.")
            save_label = st.segmented_control("If GymPulse AI helps you keep", list(SAVE_OPTIONS),
                                              default="1 in 5", key="calc_save") or "1 in 5"
        f = numbers(members, fee, leave, SAVE_OPTIONS[save_label])
        try:
            ps = gbill.plans(gbill.public_pricing())
            plan = gbill.fits(ps, members)
        except Exception:
            plan = None
        price = float(plan.get("monthly") or 0) if plan else 0
        roi = (f'<div class="lx-calc-roi">The <b>{gw._esc(plan["name"])}</b> plan for a gym your size is '
               f'<b>{_n(price)} a month</b>'
               + (f', so it would pay for itself about <b>{f["kept_month"] / price:,.0f} times over</b>.'
                  if price and f["kept_month"] >= price * 1.5 else '.')
               + '</div>') if plan and price else ""
        with right:
            gw._md(f'''<div class="lx-calc-out">
              <div class="lx-calc-big lose"><span>Fees walking out every month</span><b>{_n(f["lost_month"])}</b>
                <em>about {f["leaving"]:,.0f} members a month · {_n(f["lost_year"])} a year</em></div>
              <div class="lx-calc-big keep"><span>Keep {save_label} of them and you keep</span>
                <b>{_n(f["kept_month"])} a month</b><em>{_n(f["kept_year"])} over a year</em></div>
              {roi}
              <div class="lx-calc-note">A rough guide, not a promise: it counts just one more month of fees for each
                member kept. Inside GymPulse AI, only renewals you actually record count as money kept.</div>
            </div>''')
