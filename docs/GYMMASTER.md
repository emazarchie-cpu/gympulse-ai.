# Import members from GymMaster

Members → **Import members from GymMaster (CSV)**.

## How to export from GymMaster
1. In GymMaster, open **Reports** and run a member report (a member list or memberships report).
2. Use **Add Column** to include the columns you have from this list:
   - First Name, Surname
   - Email, Mobile
   - Membership
   - Start Date, Expiry Date
   - Price
   - Last Visit (if available)
3. Choose **Export to CSV** and upload the file. Excel files work too.

GymMaster lets each gym choose its own columns, so headings differ. That's fine:
- GymPulse guesses each column from common names, and you can change any guess before importing.
- Each GymMaster membership name (e.g. "12 Month Membership", "Monthly Gold") is matched to a GymPulse plan, and you can change those too. The price is converted to a monthly fee.

## What happens on import
- **New members are created** with their name, email and phone. Their age is worked out from the date of birth, if the file has one.
- **Plan, monthly fee and end date are set**, so they appear on the Risk Radar straight away. A missing end date is worked out from the start date and plan.
- **Last visit is recorded as a check-in**, so the Risk Radar starts with real data.
- **Members already in GymPulse** are matched by email, then phone, then name, and updated rather than duplicated. You can untick updating.
- Duplicate rows in the file are imported once.
- If the database requires a field GymMaster doesn't export (age, weight or height), a neutral placeholder is used and you're told, so you can fix it on the member's profile.
- Up to 3,000 members per file. Import more in batches.

There is no automatic live connection to GymMaster yet. Each gym creates its own API key under GymMaster's Settings → Integrations. With a gym's key and GymMaster's API documentation, an automatic sync can be added later.
