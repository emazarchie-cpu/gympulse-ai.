# Bringing members into GymPulse AI

Members page, two ways:

1. **Bring your members in: import from GymMaster, Excel or any software.** This takes a CSV or Excel export from:
   - GymMaster, Mindbody, Glofox or Spark;
   - Excel or Google Sheets, or any other list.

   Pick where your members are now to see how to export. It handles up to **20,000 members per file**, saved in batches of 500, so 5,000 members take seconds.
2. **Member sign-up link and QR code.** Share one link (WhatsApp) or print the QR code (front desk), and members fill in their own name, phone, email, goal and age, with consent. New sign-ups appear in the member list, marked "joined via link". Add their plan on the Risk Radar. The owner can switch the link off or make a new one. Needs `sql/phase14_member_signup.sql`.

Large gyms: member lists, activity, plays and payments now load page by page, so gyms with more than 1,000 members see everyone (Supabase returns 1,000 rows per request).

## Import details

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

## Photos

A CSV or Excel export can't hold the photos themselves, so GymPulse AI brings them in three ways:

1. **Photo link column**: if the export has a column with photo web links (http/https), each photo is downloaded and saved with the member during the import.
2. **ZIP or images**: at step "4. Photos (optional)", upload a ZIP or several images named after the member: member number (e.g. `1001.jpg`), email, phone or full name. They are matched automatically. For members you already have, use "Add photos for members you already have" under the import.
3. **Selfie on the sign-up link**: members can add their own photo when they join through the link. This needs `sql/phase15_signup_photo.sql` to be run once in the Supabase SQL Editor.

Photos are resized to a small JPEG (192px) before saving. The import also brings in member number, weight and height when the file has them.
