# Branded retention emails

Gyms send designed emails to their members, with their own logo, photo, colours and name.

## For gym owners

1. **Settings → Email & branding**
   - Sender name (for example "Emmanuel from GymPulse AI"), company email (replies go here), brand colour, banner background, WhatsApp number, website and footer address.
   - **Email background:** White or Black. This is the default for every email, and you can change it for any single email or campaign before sending.
   - Upload your **logo** and a **gym photo**. The photo goes on the left of every banner.
2. **Send to one member:** Follow-ups → Compose → choose the member → Send via **Email** → leave **Designed email** on.
   - The design follows the play you pick. Every part is editable: headline, tagline, offer, message, button and link.
   - You see a live preview before you send.
3. **Send to a group:** Follow-ups → **Email campaigns**.
   - Pick a group: lapsed in the last 60 days, not seen for 14+ days, high risk, renewing in 14 days, or all active members.
   - Then pick a design, edit it, preview it, tick the confirmation box and send.
   - Each email is personalised with the member's first name. Members who unsubscribed or have no email are skipped.

**Designs included:** Win-back ("Come back"), We miss you, Let's talk, Keep going (renewal), See you in class, Better together (bring a friend), Meet your coach, Your session (PT), Your next win (goal review), Your voice (feedback), Take on the challenge, Well done (milestone), Welcome back.

**Trainer emails:** Meet your coach, Your session and Your next win include a profile card for the trainer you pick: photo, name, specialty, bio, WhatsApp and call buttons, and a link to their full profile. Details come from Settings → Trainers. Untick **Show their profile** to leave the card out.

**Offers:** an offer only appears if the gym types one in. GymPulse never invents discounts or deadlines.

**Unsubscribe:** every email has an unsubscribe link and a one-tap unsubscribe header. GymPulse never emails a member who unsubscribed.

## Who the email comes from

| Setup | From | Replies go to |
|---|---|---|
| Default, works straight away | `Your Gym <your-gym@usegympulseai.com>` | the gym's company email |
| Gym connects its own domain | `Emmanuel from GymPulse AI <hello@company.com>` | the gym's company email |

To connect a domain, the gym goes to Settings → Email & branding → **Send from your own email address**, enters its domain and sender address, taps **Connect domain**, adds the DNS records shown, then taps **Check verification**.

## For the GymPulse AI owner

1. **Supabase:** run `sql/gym_email.sql`. It switches on unsubscribe links and image hosting for logos, photos and banners. Without it, emails still send, but with a text banner and no images.
2. **Render (already set):** `RESEND_API_KEY` sends every email.
3. **To let gyms connect their own domains:** add `RESEND_ADMIN_KEY`, a Resend API key with **Full access**. Resend's free plan allows one domain (usegympulseai.com), so gym domains need the Pro plan.
4. **Limits:** Resend's free plan sends 100 emails a day and 3,000 a month. Upgrade before gyms run large campaigns.
