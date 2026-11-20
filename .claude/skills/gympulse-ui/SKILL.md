---
name: gympulse-ui
description: Rules and procedure for any UI, styling or UX change in the GymPulse AI app (signed-in workspaces), including how to preview and screenshot changes. Use together with frontend-design and docs/DESIGN.md.
---

# Changing the GymPulse AI interface

## First principles
- Read `docs/DESIGN.md` and follow it. It is the source of truth for colour, type, spacing, phones and dashboards.
- **Keep the workspaces as they are** unless the founder asks for a redesign: same layout, pages, page names,
  buttons and their positions. Improve the look through CSS, not by restructuring.
- **Show before building** anything that changes layout or navigation: make a mockup (HTML rendered to PNG),
  send it, and wait for approval.
- The public website (landing page, `lx-*` styles, SEO pages) is off-limits unless asked.

## Where styles go
| Layer | Applies to | Use for |
|---|---|---|
| `CSS` in `gympulse_design.py` (`apply()`) | Everywhere, including the website | Base tokens; avoid editing |
| `POLISH_CSS` (in `apply()`) | Everywhere | Accessibility rules: 44px tap targets, 16px inputs on phones |
| `APP_CSS` (`apply_app()`, called after sign-in) | Signed-in app only | App-only tweaks |
| `REGISTER_CSS` (last in `apply()` and `apply_app()`) | Everywhere | The Register look: colours, fonts, ruled lines. New look-and-feel changes go here |

Use high-specificity selectors (`html body .stApp.stApp ...`) so the layer wins over older rules.
Never override `[data-testid="stIconMaterial"]` fonts.

## What to avoid (reads as AI-generated)
- ALL-CAPS, letter-spaced labels; write sentence case in the source text.
- Gradients on buttons, bars, avatars or text; glows; colour blobs.
- Several bright accents at once. Lime = action or presence, red/orange = risk, amber = waiting.
- Identical rounded cards with soft shadows everywhere; hover lifts on cards.
- "A · B · C" label strings, "→" on buttons, numbered 01/02/03 markers on things that aren't steps.

## Preview procedure
1. Write a small Streamlit page in the scratchpad that imports the real modules and calls
   `gw.apply_ui_styles(); gd.apply(); gd.apply_app()`, then renders real components
   (`page_header`, `kpi_row`, `table`, cards, buttons, inputs, tabs) with demo-style data.
2. **Start Streamlit from the repository folder** so `.streamlit/config.toml` (dark theme) is used:
   `cd /workspace/<repo> && streamlit run <scratch>/demo.py --server.port 8601 --server.headless true`.
   Running it from another folder shows a light theme that isn't real.
3. Fonts from Google can't load in the sandbox: for previews, serve the local `.ttf` files from
   `.claude/skills/canvas-design/canvas-fonts` via `--server.enableStaticServing true`.
4. Screenshot with Playwright at 1366×1500 and 390×2600 after `text=` of real content appears; measure
   computed sizes for tap targets and input font sizes when relevant.
5. Compare before and after, fix, then ship with `gympulse-shipping`. Send the founder the before/after images.
