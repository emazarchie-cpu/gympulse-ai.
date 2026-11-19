# GymPulse AI: rules for Claude

GymPulse AI (GYMPULSE AI LTD, Calabar) is a **member retention platform for Nigerian gyms**. It is not gym
management software: it works alongside GymMaster, Excel or whatever a gym already uses. Built with
Streamlit, Supabase (Frankfurt) and Render, with Paystack billing and the WhatsApp Cloud API.

These rules always apply. The skills in `.claude/skills/` hold the detail for each kind of task.

## Always
- **Ask before changing the public website** (landing page, `gympulse_design.py` `lx-*`, `gympulse_seo.py`).
  Change only what was asked. Never swap media, copy or layout on the site unprompted.
- **Keep workspaces as they are** unless asked: same layout, pages, page names and button positions.
  Style changes go in a CSS layer, not in restructuring.
- **Never ask for secrets in chat.** API keys, tokens, passwords, PINs and card numbers go only into
  Render, GitHub secrets or Supabase. If one appears in a screenshot, say so and tell the founder how to protect it.
- **Privacy:** the registered office street address is private. Public pages say "Calabar, Cross River State";
  legal documents say "the address recorded with the CAC". Government and payment forms (NDPC, Paystack, Meta) may use it.
  The demo gym's password is emailed to the founder only, never printed.
- **Honesty:** no claims that aren't true today. No HMO partnerships. Say WhatsApp works only when templates
  are approved. The risk model is trained on synthetic data: say so when asked. No invented stats, logos,
  testimonials or customer counts. Label demo figures as demo figures.
- **Copyright:** never copy another company's design, wording, logo or brand name. Use generic placeholders
  ("e.g. Lekki branch"), not real gym names.
- **The app is dark only. Every plan includes every feature.**
- **Plain English, short sentences.** The founder often types quickly by voice: work out the intent, and if a
  request is genuinely ambiguous, ask one short question.
- **They/them** for anyone whose pronouns aren't stated.

## Everything visual must look modern and human-designed, never "AI slop"
This applies to all work: app screens, flyers, posters, videos, decks, social posts, documents and emails.
- Load `frontend-design` (or `canvas-design` for print and art) before designing anything, and make a short plan:
  palette, type, layout, and the one memorable element. Then check the plan against the list below.
- **Avoid:** gradients on buttons, text or bars; glows and colour blobs; ALL-CAPS letter-spaced labels;
  identical rounded cards with soft shadows; rainbow accents; "A · B · C" strings; "→" on buttons;
  01/02/03 markers on things that aren't steps; one highlighted word in a headline; emojis as decoration;
  hover lifts and fade-in on every element; stock phrases ("Unlock", "Elevate", "Seamless", "Revolutionise").
- **Do:** one accent colour with meaning, sentence case, two typefaces with character (Bricolage Grotesque +
  Instrument Sans), real content and real numbers, generous spacing, readable on a phone, one bold idea per piece.
- **Self-critique before sending:** render it, look at the screenshot, remove one thing, fix what reads as
  generic, and only then send it.

## Skills to use
| Task | Skill |
|---|---|
| Shipping any code change (branch, test, PR, merge, deploy check) | `gympulse-shipping` |
| Any UI or styling change in the app | `gympulse-ui` (with `frontend-design`) |
| Posts, flyers, videos, pitches, case studies, emails, WhatsApp messages | `gympulse-content` |
| Walking the founder through Meta, Render, GitHub, Supabase, Paystack, CAC or NDPC | `gympulse-setup-help` |
| Testing the app in a browser | `webapp-testing` |
| Posters and print pieces | `canvas-design` |
| Themes for decks and documents | `theme-factory` |
