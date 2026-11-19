---
name: gympulse-setup-help
description: How to guide the GymPulse AI founder through outside services - Meta/WhatsApp Business, Render, GitHub secrets, Supabase, Paystack, CAC/NDPC paperwork, domains - usually from phone screenshots. Use whenever the founder is clicking through a third-party dashboard.
---

# Guiding the founder through setup

## How to guide
- **One step at a time.** Say what the screen they sent means, then the next 1–3 actions, then what to send back.
- Name buttons exactly as they appear, including in other languages (translate German screens).
- Read screenshots carefully; if digits are blurry, tell them to copy the value with the copy icon instead of typing yours.
- Say what is safe to ignore on the screen, and what must **not** be tapped (e.g. "Can't try another device?").
- When something fails, find the real cause (logs, exact error) before suggesting a retry; don't retry blindly.

## Secrets
- Never ask for a key, token, password, PIN or card number in chat. Tell them where to paste it:

| Value | Render | GitHub secret | Supabase function |
|---|---|---|---|
| `WHATSAPP_TOKEN` | ✓ | ✓ | ✓ |
| `WHATSAPP_PHONE_ID` | ✓ | ✓ | |
| `WHATSAPP_WABA_ID` | ✓ | | |
| `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_PIN` | | ✓ | (set by workflow) |
| `SUPABASE_ACCESS_TOKEN` (starts `sbp_`) | | ✓ | |
| `PAYSTACK_SECRET_KEY`, `RESEND_API_KEY`, `SUPABASE_*` | ✓ | ✓ | |

- If a screenshot shows a secret or full card number, point it out and say how to protect it.

## Meta (Facebook / WhatsApp)
- Use **one trusted device** (the founder's phone apps or one normal browser). No incognito, no office laptop,
  no opening Meta links from email: these trigger account locks.
- Two-factor authentication is on; logins may need approval in the Facebook app.
- Business verification needs documents showing the exact legal name **and** the address typed into the form
  (bank statement works; the CAC certificate shows no address).
- WhatsApp billing is in USD; Nigerian naira cards often fail, a virtual USD card works.
- The ad-account payment screen (with "ad credit") is not WhatsApp billing.
- After adding a number, run **Actions → Deploy WhatsApp webhook** with the App ID, WABA ID and phone_id to
  connect the webhook and register the number; then submit templates again from Admin → WhatsApp.

## Other services
- **Render:** environment variables are edited in place (duplicates error); saving redeploys.
- **GitHub Actions:** I can trigger workflows and read logs; the founder adds secrets.
- **Supabase SQL:** the founder runs `sql/*.sql` files in the SQL editor; tell them the exact file.
- **Domains:** `usegympulseai.com` works; check `www` and mobile-network DNS separately before blaming the site.
- **Costs:** say clearly when a step costs money and roughly how much, before they pay.
