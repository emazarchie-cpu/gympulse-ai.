# WhatsApp channel

GymPulse AI's automatic messages (renewal reminders, we missed you, new-member check-ins, celebrations,
happiness check) can go out on WhatsApp as well as email. Each gym chooses in **Grow → Automatic messages →
How messages go out**: *Email only*, *WhatsApp first* (email if the member isn't on WhatsApp, or WhatsApp fails),
or *WhatsApp and email*. Until the settings below are added, everything keeps going by email.

Members tap reply buttons on the message:

| Message | Buttons | What happens |
|---|---|---|
| Renewal reminder | Renew now · Talk to us | Renew now sends the gym's payment options (Paystack link, bank details); both land in Follow-ups |
| We missed you | Yes, I'll come in · Pause my membership | Friendly reply; both land in Follow-ups |
| New member check-in | Going great · I'd like some help | "Help" lands in Follow-ups |
| Celebration | Thank you! | — |
| Happiness check | Love it · Happy · It's okay · Not happy | Saved as their answer (Grow → Happiness); unhappy answers land in Follow-ups |

Replying **STOP** switches WhatsApp off for that member (START switches it back on). Every other reply lands in
the Follow-ups inbox. Delivered and read ticks are tracked.

## Setup

1. **Meta Business portfolio** and **business verification** (business.facebook.com → Business settings →
   Security centre). Use the CAC certificate, address and usegympulseai.com.
2. **Meta app** at developers.facebook.com → Create app → Business → add **WhatsApp**. The test number works
   straight away for up to 5 recipient numbers.
3. **Phone number**: add GymPulse AI's number in WhatsApp Manager (a WhatsApp Business App number can be
   connected and kept), set the display name, add a payment method.
4. **Permanent token**: Business settings → System users → add an admin system user → assign the app and the
   WhatsApp account → Generate token with `whatsapp_business_messaging` and `whatsapp_business_management`.
5. **Secrets** (never in chat or code):

   | Name | Where it comes from | Render | GitHub | Supabase function |
   |---|---|---|---|---|
   | `WHATSAPP_TOKEN` | step 4 | ✓ | ✓ | ✓ |
   | `WHATSAPP_PHONE_ID` | WhatsApp → API setup → Phone number ID | ✓ | ✓ | |
   | `WHATSAPP_WABA_ID` | WhatsApp Business Account ID | ✓ | | |
   | `WHATSAPP_APP_SECRET` | App settings → Basic → App secret | | | ✓ |
   | `WHATSAPP_VERIFY_TOKEN` | any passphrase you make up | | | ✓ |

6. **Database**: run `sql/phase17_whatsapp.sql` in the Supabase SQL Editor.
7. **Webhook**: Supabase → Edge Functions → Deploy a new function named `whatsapp-webhook`, paste
   `supabase/functions/whatsapp-webhook/index.ts`, and turn **Enforce JWT verification off** (Meta can't send a
   Supabase login; the function checks Meta's signature instead). Add the three function secrets above.
   Then in the Meta app: WhatsApp → Configuration → Webhook: callback URL
   `https://<project>.supabase.co/functions/v1/whatsapp-webhook`, verify token = `WHATSAPP_VERIFY_TOKEN`,
   and subscribe to **messages**.
8. **Templates**: in GymPulse **Admin → WhatsApp**, press *Submit templates to Meta*. Approval usually takes
   minutes to a day; the table shows each status. Send yourself a test from the same page.
9. Each gym picks its channel in Grow → Automatic messages.

## Costs and rules

Meta charges per template message (utility for renewal reminders, marketing for the rest; prices depend on the
member's country). Replies within 24 hours of a member's message are free-form and not charged as templates.
Only message members who gave their number to the gym; STOP is always honoured.

All gyms currently send from GymPulse AI's number with the gym's name in the message. Connecting each gym's own
number (Meta Embedded Signup, Tech Provider) is a later step.

The older `Webhook receiver · PY` draft is replaced by the Supabase function.
