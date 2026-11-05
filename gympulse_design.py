"""GymPulse AI design system v2.

One extra style layer that sits on top of the existing styles in app.py and
gympulse_workspaces.py, plus the public landing page. The palette stays the
same (deep navy, lime, cyan); surfaces, type and spacing are modernised.
"""
import streamlit as st

LIME, CYAN, NAVY = "#B7F34A", "#35D6ED", "#0B1020"

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600;700;800&display=swap');

:root {
    --gp-bg: #0A0F1E; --gp-s1: #10172A; --gp-s2: #141D33; --gp-s3: #1A2540;
    --gp-line: rgba(255,255,255,0.08); --gp-line-2: rgba(255,255,255,0.16);
    --gp-text: #F4F7FB; --gp-muted: #93A1B8; --gp-dim: #6B7A93;
    --gp-lime: #B7F34A; --gp-cyan: #35D6ED; --gp-red: #FF6B6B; --gp-amber: #FFC44D;
    --gp-grad: linear-gradient(100deg, #B7F34A 0%, #35D6ED 100%);
    --gp-display: 'Space Grotesk', 'Inter', sans-serif;
    --gp-r: 18px;
}

/* ---------- canvas ---------- */
html body .stApp {
    background:
      radial-gradient(1100px 520px at 12% -8%, rgba(183,243,74,0.07), transparent 60%),
      radial-gradient(900px 480px at 95% 0%, rgba(53,214,237,0.07), transparent 60%),
      var(--gp-bg) !important;
}
html body .block-container { max-width: 1280px; }

/* ---------- type ---------- */
html body .pg-title, html body .lx-h1, html body .lx-h2, html body .cc-hello,
html body .kpi-value, html body .cc-kpi-value, html body .archie-name {
    font-family: var(--gp-display) !important;
}
html body .pg-title { font-size: 30px; letter-spacing: -0.8px; }
html body .pg-eyebrow { color: var(--gp-lime); letter-spacing: 1.6px; font-weight: 700; }
html body .section-label {
    display: flex; align-items: center; gap: 10px;
    color: var(--gp-muted); font-weight: 700; letter-spacing: 1.4px;
}
html body .section-label::before {
    content: ""; width: 14px; height: 3px; border-radius: 3px; background: var(--gp-grad);
}

/* ---------- surfaces ---------- */
html body .kpi {
    background: linear-gradient(180deg, rgba(255,255,255,0.035), rgba(255,255,255,0.01)), var(--gp-s1);
    border: 1px solid var(--gp-line); border-radius: var(--gp-r);
    padding: 18px 18px 16px 18px; box-shadow: 0 1px 0 rgba(255,255,255,0.04) inset;
}
html body .kpi::before {
    width: auto; height: 2px; left: 18px; right: 18px; top: 0; bottom: auto;
    border-radius: 0 0 3px 3px; opacity: .9;
}
html body .kpi-label { color: var(--gp-muted); text-transform: uppercase; letter-spacing: 1px; }
html body .kpi-value { font-size: 28px; font-weight: 700; color: var(--gp-text); }

html body [data-testid="stVerticalBlock"]:is([class*="st-key-card_"], [class*="st-key-cc_"]) {
    background: linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.008)), var(--gp-s1) !important;
    border: 1px solid var(--gp-line) !important; border-radius: var(--gp-r) !important;
}
html body [data-testid="stExpander"] details {
    border-radius: 14px !important; border-color: var(--gp-line) !important;
    background: var(--gp-s1) !important;
}

/* ---------- buttons ---------- */
html body button[kind="primary"], html body button[kind="primaryFormSubmit"] {
    background: var(--gp-grad) !important; color: #0A0F1E !important; border: 0 !important;
    font-weight: 700 !important; border-radius: 12px !important;
    box-shadow: 0 6px 22px -12px rgba(183,243,74,0.8) !important;
}
html body button[kind="primary"] *, html body button[kind="primaryFormSubmit"] * {
    color: #0A0F1E !important; font-weight: 700 !important;
}
html body button[kind="primary"]:hover, html body button[kind="primaryFormSubmit"]:hover {
    filter: brightness(1.07); transform: translateY(-1px);
}
html body button[kind="secondary"] { border-radius: 12px !important; }

/* ---------- inputs ---------- */
html body [data-baseweb="input"], html body [data-baseweb="select"] > div,
html body [data-baseweb="textarea"], html body [data-testid="stTextInputRootElement"],
html body [data-testid="stTextAreaRootElement"], html body [data-testid="stNumberInputContainer"],
html body [data-testid="stDateInputField"] {
    border-radius: 12px !important; background: #0C1324 !important;
    border: 1px solid var(--gp-line-2) !important;
}
html body [data-baseweb="input"] input, html body [data-baseweb="textarea"] textarea {
    background: transparent !important; color: var(--gp-text) !important;
}
html body [data-baseweb="input"]:focus-within, html body [data-baseweb="textarea"]:focus-within,
html body [data-testid="stTextInputRootElement"]:focus-within, html body [data-testid="stTextAreaRootElement"]:focus-within,
html body [data-testid="stNumberInputContainer"]:focus-within {
    border-color: rgba(183,243,74,0.6) !important; box-shadow: 0 0 0 3px rgba(183,243,74,0.15) !important;
}
.lx-card p, .lx-card h4 { margin-bottom: 0 !important; }

/* ---------- top bar ---------- */
html body .st-key-top_nav { border-bottom: 1px solid var(--gp-line) !important; }
html body .st-key-top_nav [data-testid="stRadioOption"] > div > div:first-child:not([data-testid]) { display: none !important; }
html body .st-key-top_nav div[role="radiogroup"] { gap: 2px !important; flex-wrap: nowrap !important; }
html body .st-key-top_nav div[role="radiogroup"] label { padding: 7px 12px !important; border-radius: 10px !important; }
html body .st-key-top_nav [data-testid="stRadioOption"][data-selected="true"] {
    background: rgba(183,243,74,0.12) !important; box-shadow: inset 0 0 0 1px rgba(183,243,74,0.35);
}
html body .st-key-top_nav div[role="radiogroup"] label p { font-weight: 600 !important; font-size: 13.5px !important; white-space: nowrap; }
html body .nav-tagline { display: none !important; }

/* ---------- member rows: name reads like a link, left aligned ---------- */
html body [class*="st-key-mrow_"] button, html body [class*="st-key-cc_w_"] button {
    justify-content: flex-start !important; text-align: left !important; padding-left: 0 !important;
    background: transparent !important; border: 0 !important; box-shadow: none !important; min-height: 30px !important;
}
html body [class*="st-key-mrow_"] button p, html body [class*="st-key-cc_w_"] button p {
    font-weight: 700 !important; font-size: 15px !important; color: var(--gp-text) !important; text-align: left !important;
}
html body [class*="st-key-mrow_"] button:hover p, html body [class*="st-key-cc_w_"] button:hover p { color: var(--gp-lime) !important; }
html body [class*="st-key-mrow_"] button > div, html body [class*="st-key-mrow_"] button span,
html body [class*="st-key-cc_w_"] button > div { justify-content: flex-start !important; width: 100%; }
html body [class*="st-key-mrow_"] [data-testid="stMarkdownContainer"] { text-align: left !important; width: 100%; }
html body .why { text-align: left !important; }

/* ---------- chips ---------- */
html body .chip { border-radius: 999px; }
.gp-tag { display: inline-flex; align-items: center; gap: 5px; font-size: 10.5px; font-weight: 700;
    letter-spacing: .6px; text-transform: uppercase; padding: 3px 8px; border-radius: 999px;
    border: 1px solid var(--gp-line-2); color: var(--gp-muted); white-space: nowrap; }
.gp-tag.ok { color: var(--gp-lime); border-color: rgba(183,243,74,0.35); background: rgba(183,243,74,0.08); }
.gp-tag.est { color: var(--gp-amber); border-color: rgba(255,196,77,0.35); background: rgba(255,196,77,0.07); }
.gp-tag.live::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: var(--gp-lime);
    box-shadow: 0 0 0 3px rgba(183,243,74,0.2); }

/* =====================================================================
   Retention command centre (dashboard)
   ===================================================================== */
.cc-hero { position: relative; overflow: hidden; border-radius: 22px; padding: 26px 28px;
    border: 1px solid var(--gp-line);
    background: radial-gradient(600px 220px at 85% 0%, rgba(53,214,237,0.14), transparent 70%),
                radial-gradient(500px 240px at 0% 100%, rgba(183,243,74,0.12), transparent 70%), var(--gp-s1);
    margin-bottom: 18px; }
.cc-hero-top { display: flex; justify-content: space-between; gap: 16px; flex-wrap: wrap; align-items: flex-start; }
.cc-eyebrow { color: var(--gp-lime); font-size: 11px; font-weight: 700; letter-spacing: 1.6px; text-transform: uppercase; }
.cc-hello { font-size: 30px; font-weight: 700; letter-spacing: -0.8px; color: var(--gp-text); margin: 6px 0 4px; line-height: 1.15; }
.cc-sub { color: var(--gp-muted); font-size: 14.5px; line-height: 1.6; max-width: 640px; }
.cc-sub b { color: var(--gp-text); }
.cc-meta { display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
.cc-pulse { position: absolute; left: 0; right: 0; bottom: -2px; height: 46px; opacity: .35; pointer-events: none; }

.cc-kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin: 0 0 6px; }
.cc-kpi { position: relative; border-radius: var(--gp-r); padding: 16px 18px; border: 1px solid var(--gp-line);
    background: linear-gradient(180deg, rgba(255,255,255,0.035), rgba(255,255,255,0.01)), var(--gp-s1); min-width: 0; }
.cc-kpi::before { content: ""; position: absolute; left: 18px; right: 18px; top: 0; height: 2px;
    background: var(--tone); border-radius: 0 0 3px 3px; }
.cc-kpi-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.cc-kpi-label { font-size: 11px; font-weight: 700; letter-spacing: 1px; text-transform: uppercase; color: var(--gp-muted); }
.cc-kpi-value { font-size: 28px; font-weight: 700; letter-spacing: -0.8px; color: var(--gp-text); margin: 8px 0 2px; line-height: 1.1; }
.cc-kpi-value small { font-size: 14px; color: var(--gp-muted); font-weight: 600; margin-left: 4px; letter-spacing: 0; }
.cc-kpi-hint { font-size: 12.5px; color: var(--gp-muted); line-height: 1.45; }

.cc-loop { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0; border-radius: var(--gp-r);
    border: 1px solid var(--gp-line); background: var(--gp-s1); overflow: hidden; }
.cc-step { padding: 16px 18px; position: relative; min-width: 0; }
.cc-step + .cc-step { border-left: 1px solid var(--gp-line); }
.cc-step-n { font-size: 11px; font-weight: 700; letter-spacing: 1.2px; color: var(--gp-dim); text-transform: uppercase; }
.cc-step-v { font-family: var(--gp-display); font-size: 26px; font-weight: 700; color: var(--gp-text); margin: 6px 0 2px; }
.cc-step-l { font-size: 12.5px; color: var(--gp-muted); line-height: 1.4; }
.cc-step-bar { height: 4px; border-radius: 4px; background: rgba(255,255,255,0.06); margin-top: 10px; overflow: hidden; }
.cc-step-bar span { display: block; height: 100%; background: var(--gp-grad); border-radius: 4px; }

.cc-pri-name { font-weight: 700; color: var(--gp-text); font-size: 15px; }
.cc-story { display: grid; grid-template-columns: 64px minmax(0, 1fr); gap: 3px 10px; font-size: 13px; line-height: 1.5; margin-top: 6px; }
.cc-story dt { color: var(--gp-dim); font-weight: 700; font-size: 10.5px; letter-spacing: .8px; text-transform: uppercase; padding-top: 2px; }
.cc-story dd { margin: 0 !important; color: #C9D3E3; font-size: 13.5px !important; line-height: 1.5 !important; }
.cc-story dd b { color: var(--gp-lime); font-weight: 700; }
.cc-chips { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 2px; }

.cc-brief { border-radius: var(--gp-r); padding: 18px 18px 14px; border: 1px solid rgba(183,243,74,0.25);
    background: radial-gradient(380px 160px at 100% 0%, rgba(53,214,237,0.16), transparent 70%),
                linear-gradient(180deg, rgba(183,243,74,0.08), rgba(183,243,74,0.02)), var(--gp-s1); }
.cc-brief-head { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.cc-brief-orb { width: 34px; height: 34px; border-radius: 50%; flex-shrink: 0;
    background: radial-gradient(circle at 35% 30%, #F4FFD6, #B7F34A 40%, #1E9E55); box-shadow: 0 0 0 4px rgba(183,243,74,0.14); }
.cc-brief-title { font-weight: 700; color: var(--gp-text); font-size: 15px; }
.cc-brief-sub { font-size: 11.5px; color: var(--gp-muted); }
.cc-brief ul { margin: 0; padding-left: 18px; }
.cc-brief li { color: #D5DEEC; font-size: 13.5px; line-height: 1.55; margin-bottom: 6px; }
.cc-brief li b { color: var(--gp-text); }
.cc-brief-foot { font-size: 11px; color: var(--gp-dim); margin-top: 8px; }

.cc-play { display: grid; grid-template-columns: minmax(0, 1.3fr) minmax(0, 2fr) 64px; gap: 10px; align-items: center;
    padding: 9px 0; border-bottom: 1px dashed var(--gp-line); font-size: 13px; }
.cc-play:last-child { border-bottom: 0; }
.cc-play-name { color: var(--gp-text); font-weight: 600; }
.cc-play-bar { height: 8px; border-radius: 8px; background: rgba(255,255,255,0.06); overflow: hidden; }
.cc-play-bar span { display: block; height: 100%; background: var(--gp-grad); }
.cc-play-rate { text-align: right; color: var(--gp-muted); font-weight: 600; font-variant-numeric: tabular-nums; }
.cc-empty { color: var(--gp-muted); font-size: 13.5px; line-height: 1.6; padding: 6px 0; }

@media (max-width: 900px) {
    .cc-kpis, .cc-loop { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .cc-step:nth-child(3) { border-left: 0; }
    .cc-step:nth-child(n+3) { border-top: 1px solid var(--gp-line); }
    .cc-hello { font-size: 24px; }
    .cc-hero { padding: 20px; }
    .cc-meta { justify-content: flex-start; }
}

/* =====================================================================
   Landing page
   ===================================================================== */
.lx-nav { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 6px 0 8px; }
.lx-nav img { height: 44px; width: auto; display: block; }
.lx-nav-links { display: flex; gap: 22px; color: var(--gp-muted); font-size: 13.5px; font-weight: 600; }
.lx-hero { display: grid; grid-template-columns: minmax(0, 1.05fr) minmax(0, 0.95fr); gap: 40px; align-items: center;
    padding: 34px 0 26px; }
.lx-pill { display: inline-flex; align-items: center; gap: 8px; padding: 6px 12px 6px 8px; border-radius: 999px;
    border: 1px solid rgba(183,243,74,0.3); background: rgba(183,243,74,0.07); color: #D9F7A6; font-size: 12.5px; font-weight: 600; }
.lx-pill i { font-style: normal; background: var(--gp-lime); color: #0A0F1E; border-radius: 999px; padding: 2px 8px; font-size: 11px; font-weight: 800; }
.lx-h1 { font-size: 58px; line-height: 1.02; letter-spacing: -2.2px; font-weight: 700; color: var(--gp-text); margin: 18px 0 16px; }
.lx-grad { background: var(--gp-grad); -webkit-background-clip: text; background-clip: text; color: transparent; }
.lx-lead { color: var(--gp-muted); font-size: 17px; line-height: 1.65; max-width: 560px; }
.lx-lead b { color: var(--gp-text); font-weight: 600; }
.lx-trust { display: flex; gap: 18px; flex-wrap: wrap; margin-top: 22px; color: var(--gp-muted); font-size: 13px; }
.lx-trust span { display: inline-flex; align-items: center; gap: 6px; }
.lx-trust svg { color: var(--gp-lime); }

.lx-app { position: relative; border-radius: 22px; padding: 16px; border: 1px solid var(--gp-line-2);
    background: linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.01)), #0E1528;
    box-shadow: 0 40px 80px -30px rgba(0,0,0,0.7), 0 0 0 1px rgba(255,255,255,0.02) inset; }
.lx-app::before { content: ""; position: absolute; inset: -1px; border-radius: 22px; padding: 1px;
    background: linear-gradient(140deg, rgba(183,243,74,0.6), transparent 40%, transparent 60%, rgba(53,214,237,0.6));
    -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0); -webkit-mask-composite: xor; mask-composite: exclude; pointer-events: none; }
.lx-app-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.lx-dots { display: flex; gap: 6px; } .lx-dots i { width: 9px; height: 9px; border-radius: 50%; background: rgba(255,255,255,0.14); }
.lx-mini-kpis { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-bottom: 10px; }
.lx-mk { border-radius: 12px; padding: 10px 12px; background: rgba(255,255,255,0.03); border: 1px solid var(--gp-line); min-width: 0; }
.lx-mk span { display: block; font-size: 9.5px; font-weight: 700; letter-spacing: .9px; text-transform: uppercase; color: var(--gp-dim); }
.lx-mk b { font-family: var(--gp-display); font-size: 19px; color: var(--gp-text); }
.lx-mk em { font-style: normal; font-size: 11px; color: var(--gp-lime); margin-left: 4px; }
.lx-row { display: grid; grid-template-columns: 34px minmax(0, 1fr) auto; gap: 10px; align-items: center;
    padding: 10px; border-radius: 12px; background: rgba(255,255,255,0.025); margin-top: 6px; border: 1px solid transparent; }
.lx-row.hot { border-color: rgba(255,107,107,0.28); background: rgba(255,107,107,0.05); }
.lx-av { width: 34px; height: 34px; border-radius: 50%; display: grid; place-items: center; font-size: 12px; font-weight: 800; color: #0A0F1E; }
.lx-row-n { font-size: 13px; font-weight: 700; color: var(--gp-text); }
.lx-row-s { font-size: 11.5px; color: var(--gp-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.lx-play { font-size: 10.5px; font-weight: 700; padding: 5px 9px; border-radius: 8px; background: var(--gp-grad); color: #0A0F1E; white-space: nowrap; }
.lx-bubble { margin-top: 10px; display: flex; gap: 10px; align-items: flex-start; padding: 11px 12px; border-radius: 14px;
    background: rgba(183,243,74,0.07); border: 1px solid rgba(183,243,74,0.22); font-size: 12.5px; color: #D5DEEC; line-height: 1.5; }
.lx-bubble .cc-brief-orb { width: 24px; height: 24px; }
.lx-note { font-size: 10px; letter-spacing: 1px; color: var(--gp-dim); text-align: center; margin-top: 10px; text-transform: uppercase; }

.lx-strip { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); border: 1px solid var(--gp-line);
    border-radius: 18px; background: var(--gp-s1); margin: 8px 0 8px; overflow: hidden; }
.lx-strip div { padding: 18px 20px; min-width: 0; } .lx-strip div + div { border-left: 1px solid var(--gp-line); }
.lx-strip b { display: block; font-family: var(--gp-display); font-size: 22px; color: var(--gp-text); }
.lx-strip span { font-size: 12.5px; color: var(--gp-muted); }

.lx-demo { padding: 42px 0 30px; text-align: center; }
.lx-video { position: relative; max-width: 1040px; margin: 4px auto 0; border-radius: 22px; overflow: hidden;
    aspect-ratio: 16 / 9; background: #05070D; border: 1px solid var(--gp-line-2);
    box-shadow: 0 40px 90px -36px rgba(0,0,0,0.8), 0 0 80px -30px rgba(183,243,74,0.35); }
.lx-video video { width: 100%; height: 100%; display: block; object-fit: cover; }
.lx-demo-note { color: var(--gp-dim); font-size: 12.5px; margin-top: 10px; }
.lx-demo-cta { display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; margin-top: 18px; }
.lx-btn { display: inline-flex; align-items: center; justify-content: center; min-height: 46px; padding: 0 24px;
    border-radius: 12px; font-weight: 700; font-size: 15px; text-decoration: none !important;
    color: var(--gp-text) !important; border: 1px solid var(--gp-line-2); background: rgba(255,255,255,0.04); }
.lx-btn:hover { border-color: rgba(183,243,74,0.6); background: rgba(183,243,74,0.08); }
.lx-btn-primary { background: var(--gp-grad); color: #0A0F1E !important; border: 0;
    box-shadow: 0 8px 26px -12px rgba(183,243,74,0.8); }
.lx-btn-primary:hover { filter: brightness(1.06); background: var(--gp-grad); }
.lx-sec { padding: 64px 0 8px; }
.lx-kicker { color: var(--gp-lime); font-size: 12px; font-weight: 700; letter-spacing: 1.8px; text-transform: uppercase; text-align: center; }
.lx-h2 { font-size: 40px; line-height: 1.1; letter-spacing: -1.4px; font-weight: 700; color: var(--gp-text); text-align: center; margin: 10px auto 12px; max-width: 760px; }
.lx-sub { color: var(--gp-muted); font-size: 16px; line-height: 1.65; text-align: center; max-width: 640px; margin: 0 auto 30px; }

.lx-loop { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.lx-card { position: relative; border-radius: 18px; padding: 22px 20px; border: 1px solid var(--gp-line);
    background: linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01)), var(--gp-s1); min-width: 0; transition: transform .2s, border-color .2s; }
.lx-card:hover { transform: translateY(-3px); border-color: rgba(183,243,74,0.4); }
.lx-num { font-family: var(--gp-display); font-size: 12px; font-weight: 700; color: var(--gp-dim); letter-spacing: 1px; }
.lx-ic { width: 40px; height: 40px; border-radius: 12px; display: grid; place-items: center; margin: 12px 0 14px;
    background: rgba(183,243,74,0.1); color: var(--gp-lime); border: 1px solid rgba(183,243,74,0.25); }
.lx-card h4 { margin: 0 0 6px; font-size: 16.5px; color: var(--gp-text); font-weight: 700; }
.lx-card p { margin: 0; color: var(--gp-muted); font-size: 13.5px; line-height: 1.6; }
.lx-card .lx-out { margin-top: 14px; font-size: 11.5px; font-weight: 700; color: var(--gp-cyan); letter-spacing: .3px; }

.lx-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 12px; }
.lx-grid .lx-card.w3 { grid-column: span 3; } .lx-grid .lx-card.w2 { grid-column: span 2; }
.lx-story { margin-top: 14px; border-radius: 12px; padding: 12px 14px; background: rgba(255,255,255,0.03); border: 1px solid var(--gp-line);
    font-size: 12.5px; color: #C9D3E3; line-height: 1.6; }
.lx-story b { color: var(--gp-lime); }

.lx-archie { display: grid; grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr); gap: 28px; align-items: center;
    border-radius: 24px; padding: 30px; border: 1px solid var(--gp-line);
    background: radial-gradient(500px 260px at 0% 0%, rgba(183,243,74,0.12), transparent 70%), var(--gp-s1); }
.lx-archie .archie-bot { width: 100%; max-width: 230px; display: block; margin: 0 auto; }
.lx-q { display: flex; flex-wrap: wrap; gap: 8px; margin: 14px 0 0; }
.lx-q span { font-size: 12.5px; padding: 7px 12px; border-radius: 999px; border: 1px solid var(--gp-line-2); color: #D5DEEC; }
.lx-msg { border-radius: 16px; padding: 12px 14px; font-size: 13.5px; line-height: 1.6; margin-bottom: 10px; }
.lx-msg.me { background: rgba(183,243,74,0.1); border: 1px solid rgba(183,243,74,0.25); color: var(--gp-text); margin-left: 18%; }
.lx-msg.ai { background: rgba(255,255,255,0.04); border: 1px solid var(--gp-line); color: #D5DEEC; margin-right: 6%; }
.lx-msg.ai b { color: var(--gp-text); }
.lx-src { font-size: 11px; color: var(--gp-dim); margin-top: 6px; }

.lx-principles { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.lx-cta { margin: 64px 0 18px; text-align: center; border-radius: 26px; padding: 48px 24px; border: 1px solid rgba(183,243,74,0.25);
    background: radial-gradient(600px 240px at 50% 0%, rgba(183,243,74,0.16), transparent 70%), var(--gp-s1); }
.lx-cta h3 { font-family: var(--gp-display); font-size: 38px; letter-spacing: -1.2px; margin: 0 0 10px; color: var(--gp-text); line-height: 1.1; }
.lx-cta p { color: var(--gp-muted); margin: 0; font-size: 15px; }
.lx-foot { display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; color: var(--gp-dim); font-size: 12.5px;
    border-top: 1px solid var(--gp-line); padding: 18px 0 8px; margin-top: 18px; }

.lx-auth-head { text-align: center; margin: 46px 0 14px; }
html body .st-key-auth_card { border-radius: 22px !important; border: 1px solid var(--gp-line-2) !important;
    background: linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01)), var(--gp-s1) !important;
    box-shadow: 0 30px 60px -30px rgba(0,0,0,0.7); }

.lx-nav-links a { color: var(--gp-lime) !important; text-decoration: none !important; }
.lx-tiers { display: grid; grid-template-columns: repeat(var(--n, 3), minmax(0, 1fr)); gap: 12px; }
.lx-tier { position: relative; border-radius: 16px; padding: 20px; border: 1px solid var(--gp-line);
    background: var(--gp-s1); min-width: 0; border-top: 3px solid rgba(255,255,255,0.12); }
.lx-tier.rec { border-top-color: var(--gp-lime); background: radial-gradient(420px 160px at 50% 0%, rgba(183,243,74,0.10), transparent 70%), var(--gp-s1); }
.lx-tier-rec { position: absolute; top: 16px; right: 16px; font-size: 11px; font-weight: 700; color: var(--gp-lime);
    border: 1px solid rgba(183,243,74,0.4); border-radius: 6px; padding: 2px 8px; }
.lx-tier-name { font-size: 13px; font-weight: 800; letter-spacing: 1.6px; text-transform: uppercase; color: var(--gp-text); }
.lx-tier-who { color: var(--gp-cyan); font-size: 13px; font-weight: 600; margin-top: 4px; }
.lx-tier-line { color: var(--gp-muted); font-size: 13px; line-height: 1.5; margin-top: 10px; }
.lx-tier-prices { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 16px; }
.lx-tier-prices > div { border-radius: 10px; padding: 10px 12px; background: rgba(255,255,255,0.03); border: 1px solid var(--gp-line); }
.lx-tier-prices b { display: block; font-family: var(--gp-display); font-size: 21px; color: var(--gp-text); letter-spacing: -.5px; }
.lx-tier-prices span { display: block; font-size: 11.5px; color: var(--gp-dim); margin-top: 2px; }
.lx-compare { margin-top: 14px; border-radius: 16px; border: 1px solid var(--gp-line); background: var(--gp-s1); overflow-x: auto; }
.lx-compare table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
.lx-compare th { padding: 14px 12px; color: var(--gp-text); font-weight: 700; text-align: center; white-space: nowrap; }
.lx-compare th:first-child { text-align: left; color: var(--gp-muted); font-weight: 600; }
.lx-compare td { padding: 11px 12px; border-top: 1px solid var(--gp-line); color: #C9D3E3; text-align: center; }
.lx-compare td:first-child { text-align: left; }
.lx-compare td svg { color: var(--gp-lime); vertical-align: middle; }
.lx-compare td i { color: var(--gp-dim); font-style: normal; }
.lx-plan-foot { text-align: center; color: var(--gp-dim); font-size: 12.5px; margin-top: 16px; }
@media (max-width: 900px) { .lx-tiers { grid-template-columns: minmax(0, 1fr); }
    .lx-compare table { font-size: 12.5px; } .lx-compare th, .lx-compare td { padding: 9px 6px; } }
@media (max-width: 900px) {
    .lx-hero, .lx-archie { grid-template-columns: minmax(0, 1fr); gap: 26px; }
    .lx-h1 { font-size: 40px; letter-spacing: -1.4px; }
    .lx-h2 { font-size: 30px; }
    .lx-loop, .lx-strip, .lx-principles { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .lx-strip div:nth-child(3) { border-left: 0; }
    .lx-strip div:nth-child(n+3) { border-top: 1px solid var(--gp-line); }
    .lx-grid { grid-template-columns: minmax(0, 1fr); }
    .lx-grid .lx-card.w3, .lx-grid .lx-card.w2 { grid-column: auto; }
    .lx-nav-links { display: none; }
    .lx-sec { padding-top: 46px; }
    .lx-cta h3 { font-size: 28px; }
}
@media (max-width: 520px) {
    .lx-loop, .lx-principles { grid-template-columns: minmax(0, 1fr); }
    .lx-h1 { font-size: 34px; }
    .lx-mini-kpis { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px; }
    .lx-mk b { font-size: 15px; }
}

/* ---- tool header cards ---- */
html body [class*="st-key-intro_"] { border: 1px solid var(--gp-line); border-radius: 18px; padding: 16px 22px 14px;
    margin: 2px 0 10px; gap: 4px !important;
    background: radial-gradient(520px 150px at 0% 0%, rgba(183,243,74,0.10), transparent 70%), var(--gp-s1); }
html body [class*="st-key-intro_"] p strong { font-size: 18px; font-weight: 700; color: var(--gp-text); }
html body [class*="st-key-intro_"] [data-testid="stIconMaterial"] { color: var(--gp-lime); font-size: 22px !important; vertical-align: -4px; margin-right: 4px; }
html body [class*="st-key-intro_"] [data-testid="stMarkdownContainer"] p { margin-bottom: 0 !important; }
.gm-sum { border: 1px solid rgba(183,243,74,0.35); border-radius: 16px; padding: 14px 20px; margin: 6px 0 12px;
    background: linear-gradient(90deg, rgba(183,243,74,0.10), transparent 80%), var(--gp-s1); }
.gm-sum-k { color: var(--gp-muted); font-size: 12px; letter-spacing: .06em; text-transform: uppercase; margin-bottom: 4px; }
.gm-sum-v { color: var(--gp-text); font-size: 18px; line-height: 1.5; }
.gm-sum-v b { color: var(--gp-lime); font-weight: 700; }
.gp-intro-s { color: var(--gp-muted); font-size: 13.5px; line-height: 1.6; max-width: 900px; margin-top: 6px; }
.gp-intro-t { font-weight: 700; font-size: 18px; color: var(--gp-text); }
/* Grow: group switcher above the tool tabs */
html body .st-key-grow_groups [data-testid="stButtonGroup"] button { font-weight: 700; }
/* ---- tables: one clean style everywhere ---- */
.gp-tbl-wrap { border: 1px solid var(--gp-line); border-radius: 16px; overflow: auto; background: var(--gp-s1);
    margin: 4px 0 10px; -webkit-overflow-scrolling: touch; }
html body .gp-tbl { width: 100% !important; border-collapse: separate !important; border-spacing: 0 !important; font-size: 13.5px; display: table !important; }
.gp-tbl thead th { position: sticky; top: 0; z-index: 1; background: var(--gp-s2); color: var(--gp-muted);
    font-size: 11px; font-weight: 700; letter-spacing: .9px; text-transform: uppercase; text-align: left;
    padding: 12px 16px; white-space: nowrap; border-bottom: 1px solid var(--gp-line); }
.gp-tbl tbody td { padding: 12px 16px; border-bottom: 1px solid var(--gp-line); color: var(--gp-text);
    vertical-align: middle; white-space: nowrap; }
.gp-tbl tbody td.wide { white-space: normal; min-width: 220px; max-width: 420px; line-height: 1.5; }
.gp-tbl tbody tr:last-child td { border-bottom: 0; }
html body .gp-tbl th, html body .gp-tbl td { border-left: 0 !important; border-right: 0 !important; border-top: 0 !important; }
html body .gp-tbl { margin: 0 !important; border: 0 !important; }
.gp-tbl tbody tr:hover td { background: rgba(127,127,127,0.06); }
.gp-tbl td.first { font-weight: 600; }
.gp-tbl .num { text-align: right; font-variant-numeric: tabular-nums; }
.gp-pill { display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px 3px 8px; border-radius: 999px;
    font-size: 12px; font-weight: 600; line-height: 1.4; border: 1px solid transparent; }
.gp-pill::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.gp-pill-lime { color: #B7F34A; background: rgba(183,243,74,0.10); border-color: rgba(183,243,74,0.25); }
.gp-pill-cyan { color: #35D6ED; background: rgba(53,214,237,0.10); border-color: rgba(53,214,237,0.25); }
.gp-pill-amber { color: #FFC44D; background: rgba(255,196,77,0.10); border-color: rgba(255,196,77,0.25); }
.gp-pill-red { color: #FF6B6B; background: rgba(255,107,107,0.10); border-color: rgba(255,107,107,0.25); }
.gp-pill-grey { color: var(--gp-muted); background: rgba(127,127,127,0.10); border-color: rgba(127,127,127,0.22); }
.gp-tbl-empty { border: 1px dashed var(--gp-line-2); border-radius: 14px; padding: 18px; text-align: center;
    color: var(--gp-muted); font-size: 13.5px; }
/* Streamlit's own grids (data editors): match the tables */
html body [data-testid="stDataFrame"], html body [data-testid="stDataEditor"] { border-radius: 14px; overflow: hidden;
    border: 1px solid var(--gp-line); }
"""


def apply():
    from gympulse_reports import DOWNLOAD_CSS
    st.markdown("<style>" + CSS + DOWNLOAD_CSS + "</style>", unsafe_allow_html=True)


PULSE_SVG = ('<svg class="cc-pulse" viewBox="0 0 1200 46" preserveAspectRatio="none">'
             '<path d="M0 30 H470 L500 30 L520 6 L548 44 L572 14 L590 30 H1200" fill="none" '
             'stroke="url(#ccg)" stroke-width="2"/><defs><linearGradient id="ccg" x1="0" x2="1">'
             '<stop offset="0" stop-color="#B7F34A"/><stop offset="1" stop-color="#35D6ED"/>'
             '</linearGradient></defs></svg>')


def landing_top(lockup_uri, icon):
    """Navigation, hero and live product preview."""
    return f"""
    <div class="lx-nav">
      <img src="{lockup_uri}" alt="GymPulse AI">
      <div class="lx-nav-links"><span>How it works</span><span>Features</span><span>Archie AI</span><a href="#pricing">Pricing</a></div>
    </div>
    <div class="lx-hero">
      <div>
        <div class="lx-pill"><i>NEW</i> Intelligent member retention for gyms</div>
        <div class="lx-h1">Know who's drifting.<br>Know why.<br><span class="lx-grad">Keep the revenue.</span></div>
        <div class="lx-lead">GymPulse AI reads <b>check-ins, renewals and payments</b>,
          spots members who are fading before they cancel, tells you the right play to run,
          and shows you the revenue those actions actually kept.</div>
        <div class="lx-trust">
          <span>{icon('check', 15)} 30-day free trial</span>
          <span>{icon('check', 15)} No card needed</span>
          <span>{icon('check', 15)} Front-desk check-in or CSV</span>
          <span>{icon('check', 15)} You approve every message</span>
        </div>
      </div>
      <div class="lx-app">
        <div class="lx-app-bar"><div class="lx-dots"><i></i><i></i><i></i></div>
          <span class="gp-tag live">Today's priorities</span></div>
        <div class="lx-mini-kpis">
          <div class="lx-mk"><span>Revenue at risk</span><b>₦186k</b></div>
          <div class="lx-mk"><span>Retained · 30d</span><b>₦75k</b><em>verified</em></div>
          <div class="lx-mk"><span>Follow-ups due</span><b>4</b></div>
        </div>
        <div class="lx-row hot"><div class="lx-av" style="background:#FF8A5B">AO</div>
          <div><div class="lx-row-n">Member A · High risk</div>
          <div class="lx-row-s">12 → 3 visits a month · 14 days away · renews in 10 days</div></div>
          <div class="lx-play">Trainer check-in</div></div>
        <div class="lx-row"><div class="lx-av" style="background:#FFC44D">KB</div>
          <div><div class="lx-row-n">Member B · Medium risk</div>
          <div class="lx-row-s">Usually trains every 3 days, now 9 away</div></div>
          <div class="lx-play">Class invite</div></div>
        <div class="lx-row"><div class="lx-av" style="background:#B7F34A">CE</div>
          <div><div class="lx-row-n">Member C · Payment overdue</div>
          <div class="lx-row-s">Still visiting · renewal lapsed 3 days ago</div></div>
          <div class="lx-play">Renewal reminder</div></div>
        <div class="lx-bubble"><div class="cc-brief-orb"></div>
          <div><b>Archie:</b> 7 of your 18 fading members renew in the next 30 days.
          Start with them: that is ₦175k of monthly fees.</div></div>
        <div class="lx-note">Illustrative example · not real member data</div>
      </div>
    </div>
    <div class="lx-demo" id="demo">
      <div class="lx-kicker">See it in action</div>
      <div class="lx-h2">The whole retention loop, in under a minute.</div>
      <div class="lx-video">
        <video src="/app/static/gympulse-demo.mp4?v=2" poster="/app/static/gympulse-demo-poster.jpg?v=2"
               autoplay muted loop playsinline controls preload="metadata"
               aria-label="GymPulse AI product demo"></video>
      </div>
      <div class="lx-demo-note">Plays muted. Tap the video for sound.</div>
      <div class="lx-demo-cta">
        <a class="lx-btn lx-btn-primary" href="#get-started">Start your free trial</a>
        <a class="lx-btn" href="?demo=book" target="_self">Book a 15-minute demo</a>
      </div>
    </div>
    <div class="lx-strip">
      <div><b>Check-in → Radar</b><span>Attendance feeds risk automatically</span></div>
      <div><b>Who · Why · Next</b><span>Every flag explains itself</span></div>
      <div><b>One board</b><span>Plays, follow-ups and outcomes together</span></div>
      <div><b>Verified ₦</b><span>Only confirmed renewals count as saved</span></div>
    </div>
    """


def landing_sections(icon, bot_svg):
    """Everything below the sign-in card."""
    return f"""
    <div class="lx-sec">
      <div class="lx-kicker">The retention loop</div>
      <div class="lx-h2">One connected system, from first warning sign to money kept</div>
      <div class="lx-sub">Other systems record what members do. GymPulse AI explains what that
        behaviour means, recommends what to do next, and measures whether it worked.</div>
      <div class="lx-loop">
        <div class="lx-card"><div class="lx-num">01 · DATA</div><div class="lx-ic">{icon('users')}</div>
          <h4>One member record</h4><p>Profiles, plans, renewal dates, trainers and every check-in in one place.</p>
          <div class="lx-out">Member Management · Check-in</div></div>
        <div class="lx-card"><div class="lx-num">02 · DETECT</div><div class="lx-ic">{icon('pulse')}</div>
          <h4>Spot the drift early</h4><p>Each member is compared with their own habits, so a daily lifter who goes quiet is flagged fast.</p>
          <div class="lx-out">Risk Radar · Drop-off alerts</div></div>
        <div class="lx-card"><div class="lx-num">03 · ACT</div><div class="lx-ic">{icon('target')}</div>
          <h4>Run the right play</h4><p>Trainer check-ins, class invites, renewal offers. A ready message in your voice, sent when you approve it.</p>
          <div class="lx-out">Action Centre · Follow-ups</div></div>
        <div class="lx-card"><div class="lx-num">04 · MEASURE</div><div class="lx-ic">{icon('gauge')}</div>
          <h4>Prove the revenue</h4><p>Track renewals, recovered payments and which plays work, kept separate from estimates.</p>
          <div class="lx-out">Payments · Business Insights</div></div>
      </div>
    </div>

    <div class="lx-sec">
      <div class="lx-kicker">Built for owners</div>
      <div class="lx-h2">Answers, not another dashboard to babysit</div>
      <div class="lx-sub">Open GymPulse AI and you see who needs you today, why, and what to do about it.</div>
      <div class="lx-grid">
        <div class="lx-card w3"><div class="lx-ic">{icon('target')}</div>
          <h4>Risk that explains itself</h4><p>Every flag answers who, why, when it started and what to do next.</p>
          <div class="lx-story"><b>Why:</b> visits fell from 12 to 3 a month, no check-in for 14 days.<br>
            <b>When:</b> the slide started about 3 weeks ago.<br>
            <b>Next:</b> personal check-in from their trainer before the renewal in 10 days.</div></div>
        <div class="lx-card w3"><div class="lx-ic">{icon('calendar')}</div>
          <h4>Renewals with context</h4><p>A fading member with a renewal due gets a different play from a loyal member whose plan is ending.</p>
          <div class="lx-story"><b>Renewal watch:</b> 7 members renew in 30 days and are attending less.
            Together they pay ₦175k a month.</div></div>
        <div class="lx-card w2"><div class="lx-ic">{icon('check')}</div>
          <h4>Front-desk check-in</h4><p>Search, tap, done. Each visit updates the Risk Radar straight away.</p></div>
        <div class="lx-card w2"><div class="lx-ic">{icon('chat')}</div>
          <h4>Follow-ups that close</h4><p>Recommended, in progress, done, each with an outcome. One board, no lost tasks.</p></div>
        <div class="lx-card w2"><div class="lx-ic">{icon('shield')}</div>
          <h4>You stay in control</h4><p>No invented discounts, no automatic sends. Offers follow your own prices and terms.</p></div>
      </div>
    </div>

    <div class="lx-sec">
      <div class="lx-kicker">Meet Archie</div>
      <div class="lx-h2">An AI retention analyst that shows its working</div>
      <div class="lx-sub">Archie reads your live gym data, gives you the figures behind every answer,
        and keeps recorded results separate from estimates.</div>
      <div class="lx-archie">
        <div>{bot_svg}
          <div class="lx-q"><span>Who should I call first today?</span><span>Which plays are working?</span>
            <span>Which renewals are at risk?</span><span>What should my staff do today?</span></div></div>
        <div>
          <div class="lx-msg me">What should my staff prioritise today?</div>
          <div class="lx-msg ai">You have <b>18 members with falling attendance</b>. <b>7 of them renew
            within 30 days</b>, worth ₦175,000 a month. Start with those seven: a personal renewal call
            from their trainer. Two follow-ups are also overdue.
            <div class="lx-src">Based on check-ins from the last 60 days · revenue is an estimate</div></div>
        </div>
      </div>
    </div>

    <div class="lx-sec">
      <div class="lx-kicker">Our principles</div>
      <div class="lx-h2">Honest numbers. Human decisions.</div>
      <div class="lx-sub">GymPulse AI is in early access. Risk estimates come from an experimental model,
        and we say so wherever they appear.</div>
      <div class="lx-principles">
        <div class="lx-card"><div class="lx-ic">{icon('users')}</div><h4>Data before predictions</h4>
          <p>Real check-ins first. Typed-in numbers are only a fallback.</p></div>
        <div class="lx-card"><div class="lx-ic">{icon('arrow')}</div><h4>Action before alerts</h4>
          <p>Every risk flag comes with a practical next step for your team.</p></div>
        <div class="lx-card"><div class="lx-ic">{icon('gauge')}</div><h4>Revenue you can trust</h4>
          <p>A message sent is not a member saved. Only recorded outcomes count.</p></div>
      </div>
    </div>

    <div class="lx-cta">
      <h3>Keep more members.<br><span class="lx-grad">Keep more revenue.</span></h3>
      <p>Try every feature free for 30 days. Setting up takes about a minute.</p>
      <div class="lx-demo-cta">
        <a class="lx-btn lx-btn-primary" href="#get-started">Start your free trial</a>
        <a class="lx-btn" href="?demo=book" target="_self">Book a 15-minute demo</a>
      </div>
    </div>
    <div class="lx-foot"><span>© GymPulse AI</span><span>Smarter insights. Stronger member retention.</span></div>
    """


# =====================================================================
# Light mode: a real light palette (not an inverted dark theme).
# Applied after every other style layer when the owner picks light mode.
# =====================================================================
LIGHT_CSS = """
html body .stApp.stApp .gp-pill-lime { color: #3F6212; background: #EEF7DC; border-color: #D3E9A8; }
html body .stApp.stApp .gp-pill-cyan { color: #0E7490; background: #E3F6FA; border-color: #B8E6F0; }
html body .stApp.stApp .gp-pill-amber { color: #92400E; background: #FEF3D6; border-color: #F8DE9C; }
html body .stApp.stApp .gp-pill-red { color: #B42318; background: #FDE8E7; border-color: #F6C2BE; }
html body .stApp.stApp .gp-tbl tbody td { color: #0F172A; }
html body .stApp.stApp .gp-tbl thead th { background: #F6F8FB; color: #5B6678; }
html body .stApp.stApp .gp-tbl-wrap { background: #FFFFFF; }

:root, html body {
    --gp-bg: #F4F6FA; --gp-s1: #FFFFFF; --gp-s2: #F1F4F8; --gp-s3: #E9EEF5;
    --gp-line: rgba(15,23,42,0.09); --gp-line-2: rgba(15,23,42,0.16);
    --gp-text: #0F172A; --gp-muted: #5B6678; --gp-dim: #7A8699;
    --gp-lime: #4D7C0F; --gp-cyan: #0E7490;
    --background: #F4F6FA; --surface: #FFFFFF; --surface-light: #F1F4F8; --white: #0F172A;
    --muted: #5B6678; --border: rgba(15,23,42,0.09);
    --surface-1: #FFFFFF; --surface-2: #F1F4F8; --line: rgba(15,23,42,0.09);
    --line-strong: rgba(15,23,42,0.22); --text: #0F172A; --text-muted: #5B6678; --accent: #4D7C0F;
    color-scheme: light;
}
html body .stApp {
    background:
      radial-gradient(1000px 480px at 10% -10%, rgba(183,243,74,0.16), transparent 60%),
      radial-gradient(900px 460px at 95% 0%, rgba(53,214,237,0.12), transparent 60%),
      #F4F6FA !important;
    color: #0F172A !important;
}
/* every piece of text: dark ink first, then the exceptions below */
html body .stApp.stApp.stApp :is(p, span, label, li, h1, h2, h3, h4, h5, h6, b, strong, td, th, dd, dt,
    small, em, div, a:not(.gp-dl):not(.lx-btn)) { color: #0F172A; }
html body .stApp.stApp.stApp :is(input, textarea) {
    color: #0F172A !important; -webkit-text-fill-color: #0F172A !important; caret-color: #0F172A; }
html body .stApp.stApp.stApp :is(input, textarea)::placeholder { color: #94A0B2 !important;
    -webkit-text-fill-color: #94A0B2 !important; }

/* secondary text */
html body .stApp.stApp.stApp :is(.pg-sub, .pg-date, .kpi-hint, .kpi-label, .why, .why *, .cc-sub, .cc-kpi-hint,
    .cc-kpi-label, .cc-step-l, .cc-step-n, .cc-brief-sub, .cc-brief-foot, .cc-story dt, .cc-empty, .section-label,
    .bk-sub, .bk-small, .lx-sub, .lx-demo-note, .pm-gym, .pm-label, .chat-who, .archie-role, .sb-sub,
    .gp-table th, .gp-table .sub, .gp-table-foot, .kb-empty, .bp-sub, .pn, .pillar p, .money,
    [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] *,
    [data-testid="stWidgetLabel"] small, .cc-play-rate) { color: #5B6678 !important; }
html body .stApp.stApp.stApp :is(.cc-sub b, .cc-story dd, .cc-brief li, .cc-brief li *) { color: #1E293B !important; }
/* accent text, deeper so it reads on white */
html body .stApp.stApp.stApp :is(.pg-eyebrow, .cc-eyebrow, .lx-kicker, .cc-story dd b, .archie-status,
    .kicker) { color: #4D7C0F !important; }
html body .stApp.stApp.stApp a:not(.gp-dl):not(.lx-btn):not([data-testid^="stBaseLinkButton"]) { color: #0E7490; }

/* surfaces */
html body .stApp.stApp :is(.kpi, .cc-kpi, .cc-loop, .panel, .pillar, .board-progress, .kb-head, .gp-table-wrap,
    .status-big, .profile-hero, .lx-card, .lx-strip, .bk-done) {
    background: #FFFFFF !important; border: 1px solid rgba(15,23,42,0.08) !important;
    box-shadow: 0 1px 2px rgba(15,23,42,0.04), 0 8px 24px -16px rgba(15,23,42,0.18) !important; }
html body .stApp.stApp .kpi::after { display: none; }
html body .stApp.stApp :is(.cc-hero, .archie-hero) {
    background: radial-gradient(600px 220px at 85% 0%, rgba(53,214,237,0.18), transparent 70%),
                radial-gradient(500px 240px at 0% 100%, rgba(183,243,74,0.22), transparent 70%), #FFFFFF !important;
    border: 1px solid rgba(15,23,42,0.08) !important; box-shadow: 0 10px 30px -18px rgba(15,23,42,0.25) !important; }
html body .stApp.stApp .cc-brief {
    background: radial-gradient(380px 160px at 100% 0%, rgba(53,214,237,0.14), transparent 70%),
                linear-gradient(180deg, rgba(183,243,74,0.14), rgba(183,243,74,0.04)), #FFFFFF !important;
    border: 1px solid rgba(77,124,15,0.25) !important; }
html body .stApp.stApp .cc-step + .cc-step { border-left-color: rgba(15,23,42,0.08) !important; }
html body .stApp.stApp :is(.cc-step-bar, .cc-play-bar, .pbar) { background: #E9EEF5 !important; }
html body .stApp.stApp .gp-table th { background: #F6F8FB !important; }
html body .stApp.stApp .gp-table td { border-bottom-color: rgba(15,23,42,0.06) !important; }
html body .stApp.stApp [data-testid="stVerticalBlock"]:is([class*="st-key-card_"], [class*="st-key-cc_"], .st-key-auth_card) {
    background: #FFFFFF !important; border: 1px solid rgba(15,23,42,0.08) !important;
    box-shadow: 0 1px 2px rgba(15,23,42,0.04), 0 10px 28px -18px rgba(15,23,42,0.2) !important; }
html body .stApp.stApp [data-testid="stExpander"] details { background: #FFFFFF !important;
    border-color: rgba(15,23,42,0.1) !important; }
html body .stApp.stApp [data-testid="stExpander"] summary { background: #FFFFFF !important; color: #0F172A !important; }
html body .stApp.stApp [data-testid="stExpander"] summary:hover { background: #F6F8FB !important; }
html body .stApp.stApp [data-testid="stChatMessage"] { background: #FFFFFF !important;
    border: 1px solid rgba(15,23,42,0.08) !important; }
html body .stApp.stApp [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
    background: #F3F9E6 !important; border-color: rgba(77,124,15,0.25) !important; }
html body .stApp.stApp [data-testid="stChatInput"] { background: #FFFFFF !important; border-color: rgba(15,23,42,0.16) !important; }
html body .stApp.stApp [data-testid="stChatInput"] textarea { background: transparent !important; }
html body .stApp.stApp.stApp [data-testid="stChatInput"],
html body .stApp.stApp.stApp [data-testid="stChatInput"] > div,
html body .stApp.stApp.stApp [data-testid="stChatInput"] [data-baseweb] { background: #FFFFFF !important; }
html body .stApp.stApp.stApp [data-testid="stChatInput"] div:not(:has(button)) { background-color: transparent !important; }

/* inputs, selects, uploads */
html body .stApp.stApp :is([data-testid="stTextInputRootElement"], [data-testid="stTextAreaRootElement"],
    [data-testid="stNumberInputContainer"], [data-testid="stDateInputField"], [data-baseweb="select"] > div,
    [data-baseweb="input"], [data-baseweb="textarea"]) {
    background: #FFFFFF !important; border: 1px solid #D5DCE6 !important; }
html body .stApp.stApp [data-testid="stNumberInputContainer"] button { background: #F1F4F8 !important; }
html body .stApp.stApp :is([data-testid="stSelectbox"], [data-testid="stMultiSelect"], [data-testid="stDateInput"],
    [data-testid="stTimeInput"]) [role="group"] { background: #FFFFFF !important; border: 1px solid #D5DCE6 !important; }
html body .stApp.stApp [data-testid="stRadioOption"]:not([data-selected="true"]) > div > div:first-child:not([data-testid]) {
    background: #FFFFFF !important; border: 1px solid #B8C2D0 !important; }
html body .stApp.stApp [data-testid="stBottom"] > div { background: #F4F6FA !important; }
html, html body { background: #F4F6FA !important; }
html body .stApp.stApp [data-testid="stFileUploaderDropzone"] { background: #FFFFFF !important;
    border: 1px dashed #C7D0DC !important; }
html body [data-baseweb="popover"] :is(ul, [role="listbox"], [data-baseweb="menu"]) {
    background: #FFFFFF !important; border: 1px solid #E3E8EF !important; }
html body [data-baseweb="popover"] :is(li, [role="option"]) , html body [data-baseweb="popover"] :is(li, [role="option"]) * {
    color: #0F172A !important; }
html body [data-baseweb="popover"] [role="option"]:hover, html body [data-baseweb="popover"] [aria-selected="true"] {
    background: #F1F6E8 !important; }
html body [data-testid="stPopoverBody"] { background: #FFFFFF !important; border: 1px solid #E3E8EF !important;
    box-shadow: 0 20px 50px -20px rgba(15,23,42,0.35) !important; }
html body [data-testid="stPopoverBody"] * { color: #0F172A; }
html body [data-testid="stPopoverBody"][data-testid="stPopoverBody"][data-testid="stPopoverBody"] .stButton button,
html body [data-testid="stPopoverBody"][data-testid="stPopoverBody"][data-testid="stPopoverBody"] .stButton button :is(p, span, div) { color: #1F2937 !important; }
html body [data-testid="stPopoverBody"][data-testid="stPopoverBody"][data-testid="stPopoverBody"] .stButton button[data-testid^="stBaseButton-secondary"] {
    background-color: #F4F6FA !important; border: 1px solid #E3E8EF !important; }
html body [data-testid="stPopoverBody"][data-testid="stPopoverBody"][data-testid="stPopoverBody"] .stButton button:hover { background-color: #EEF4E2 !important; }
html body [data-testid="stPopoverBody"][data-testid="stPopoverBody"][data-testid="stPopoverBody"] .stButton button:hover :is(p, span, div) { color: #3F6212 !important; }
html body [data-testid="stPopoverBody"][data-testid="stPopoverBody"][data-testid="stPopoverBody"] .st-key-logout_button_main .stButton button :is(p, span, div) { color: #B42318 !important; }
html body [data-testid="stPopoverBody"][data-testid="stPopoverBody"][data-testid="stPopoverBody"] hr { border-color: #E3E8EF !important; }
html body .stApp.stApp [data-baseweb="tab-list"] { border-bottom-color: rgba(15,23,42,0.1) !important; }
html body .stApp.stApp [data-testid="stAlert"] > div { background: #FFFFFF !important;
    border: 1px solid rgba(15,23,42,0.1) !important; }
html body [data-testid="stToast"] { background: #FFFFFF !important; color: #0F172A !important; }

/* buttons */
html body .stApp.stApp :is(button[kind="secondary"], button[kind="secondaryFormSubmit"],
    [data-testid="stBaseLinkButton-secondary"], [data-testid="stPopover"] > div > button,
    button[data-variant="segmented_control"]) {
    background-color: #FFFFFF !important; border: 1px solid #D5DCE6 !important; color: #0F172A !important;
    box-shadow: 0 1px 2px rgba(15,23,42,0.05) !important; }
html body .stApp.stApp.stApp.stApp :is(button[kind="secondary"], button[kind="secondaryFormSubmit"],
    [data-testid="stBaseLinkButton-secondary"], button[data-variant="segmented_control"]) :is(p, span, div) {
    color: #0F172A !important; }
html body .stApp.stApp button[data-variant="segmented_control"][aria-checked="true"] {
    background-color: #EEF7DC !important; border-color: rgba(77,124,15,0.45) !important; }
html body .stApp.stApp.stApp.stApp button[data-variant="segmented_control"][aria-checked="true"] * { color: #3F6212 !important; }
html body .stApp.stApp.stApp .st-key-brand_home button { background-color: transparent !important;
    border: 0 !important; box-shadow: none !important; }
html body .stApp.stApp :is(button[kind="secondary"], [data-testid="stBaseLinkButton-secondary"]):hover {
    border-color: #8DB33A !important; background: #F7FBEF !important; }
html body .stApp.stApp :is(button[kind="primary"], button[kind="primaryFormSubmit"]) * { color: #0A0F1E !important; }
html body .stApp.stApp button[kind="tertiary"] * { color: #0E7490 !important; }
html body .stApp.stApp .gp-dl { background: #FFFFFF !important; border-color: #D5DCE6 !important; color: #0F172A !important; }
html body .stApp.stApp .gp-dl-primary { background: linear-gradient(100deg, #B7F34A, #35D6ED) !important; border: 0 !important; color: #0A0F1E !important; }

/* top bar */
html body .stApp.stApp .st-key-top_nav { background: rgba(255,255,255,0.75) !important;
    border-bottom: 1px solid rgba(15,23,42,0.08) !important; }
html body .stApp.stApp.stApp .st-key-top_nav div[role="radiogroup"] label p { color: #334155 !important; }
html body .stApp.stApp .st-key-top_nav [data-testid="stRadioOption"][data-selected="true"] {
    background: #EEF7DC !important; box-shadow: inset 0 0 0 1px rgba(77,124,15,0.35) !important; }
html body .stApp.stApp.stApp .st-key-top_nav [data-testid="stRadioOption"][data-selected="true"] p { color: #3F6212 !important; }
html body .stApp.stApp :is(.st-key-top_msg, .st-key-top_menu) button { background: #FFFFFF !important;
    border: 1px solid #D5DCE6 !important; }

/* chips: same tones, readable on white */
html body .stApp.stApp.stApp .chip { background: #F1F4F8 !important; color: #334155 !important; }
html body .stApp.stApp.stApp .chip-lime { background: #EEF7DC !important; color: #3F6212 !important; }
html body .stApp.stApp.stApp .chip-cyan { background: #E3F6FA !important; color: #0E7490 !important; }
html body .stApp.stApp.stApp .chip-amber { background: #FEF3DC !important; color: #B45309 !important; }
html body .stApp.stApp.stApp .chip-red { background: #FDE8E8 !important; color: #B91C1C !important; }
html body .stApp.stApp.stApp .gp-tag { border-color: rgba(15,23,42,0.16) !important; color: #475569 !important; }
html body .stApp.stApp.stApp .gp-tag.ok { color: #3F6212 !important; background: #EEF7DC !important; border-color: rgba(77,124,15,0.3) !important; }
html body .stApp.stApp.stApp .gp-tag.est { color: #B45309 !important; background: #FEF3DC !important; border-color: rgba(180,83,9,0.3) !important; }

/* misc */
html body .stApp.stApp hr, html body .stApp.stApp [data-testid="stDivider"] { border-color: rgba(15,23,42,0.1) !important; }
html body .stApp.stApp .cc-pulse { opacity: .55; }
html body ::selection { background: rgba(183,243,74,0.45); color: #0F172A; }
"""


def apply_light():
    st.markdown("<style>" + LIGHT_CSS + "</style>", unsafe_allow_html=True)
