# GymPulse AI design rules

Every screen follows these. They're enforced globally by `POLISH_CSS` in `gympulse_design.py`;
new screens should follow them too instead of adding their own styling.

## Colour
- **One accent for actions: lime (`--gp-lime`).** Primary buttons are solid lime with dark text.
  No gradients on buttons, avatars or controls, and no glows.
- **Colour means something.** Red = danger/high risk/money at risk, amber = medium risk or waiting,
  lime = do this / good / done, ink grey (`--gp-cyan`, now #C9C4B8) = neutral information. Never use them as decoration.
- **Never rely on colour alone.** Chips say "High", errors say what to fix, links are underlined.
- **Tint large areas, keep strong colour for small details.** No coloured page backgrounds or blobs.

## Dark mode (the app is dark only)
- The "Register" look (chosen 20 Nov 2026): near-black paper `#0E0F12` (`--gp-bg`), warm paper-white text `#F2EFE6`
  (`--gp-text`), ruled hairlines `#262A33` instead of boxes, 4px corners, no shadows or gradients. Text is `--gp-text`,
  secondary text is `--gp-muted`. Every text colour must reach 4.5:1 contrast on its surface.
- Surfaces rise by getting **lighter** (`--gp-s1` → `--gp-s2` → `--gp-s3`), not by drop shadows.

## Type
- Two typefaces, everywhere: **IBM Plex Sans** for words and headings (600 for headings), **IBM Plex Mono** for
  numbers, dates and money (KPI values, ₦ amounts, the page date). Set in `REGISTER_CSS` (gympulse_design.py),
  applied last on every page; guide pages use the same fonts in `gympulse_seo.CSS`.
  Use weight, not more fonts, for variety.
- Body text: 14–16px, line height 1.5–1.6, about 45–75 characters per line.
- Headings clearly bigger or bolder than body; tighten letter spacing on large headings.
- Sentence case everywhere: section headings, KPI labels, table headers and eyebrows. No tracked-out ALL CAPS.
- No "A · B · C" strings in labels; use a comma or a colon.
- Numbers use tabular figures and are right-aligned in tables.

## Layout and spacing
- Spacing comes from one scale: 4, 8, 16, 24, 32 px.
- More space between groups than inside them; keep labels close to their field.
- Cards have at least 16px padding. Inner corner radius = outer radius − padding.
- Left-align anything longer than two lines.

## Buttons and copy
- **One primary action per view.** Everything else is secondary or a text button.
- Buttons say what happens ("Start this play", "Record outcome"), never "OK" or "Yes".
- Use visible labels on form fields; placeholders are examples, not labels.

## Phones
- Tap targets are at least **44 × 44 px**.
- Inputs use **16px** text, so iPhone doesn't zoom in when a field is tapped.
- Nothing important is hidden behind hover; actions stay on screen.
- Put the main action where the thumb can reach it; prefer bottom sheets to centred dialogs.
- Open the right keyboard (phone numbers → number pad, emails → email keyboard).

## Dashboards
- Lead with the number that matters most; give each number a period and, where possible, a change.
- Bar charts start at zero. More than three parts of a whole → sorted bars, not a pie.
- Highlight one series and grey out the rest.
