# Legal documents: brief for the lawyer

These are **drafts** written against the Nigeria Data Protection Act 2023 (NDPA). Please review and adapt them before GymPulse AI takes paying customers.

| File | What it is | Shown in the app |
|---|---|---|
| `TERMS_OF_SERVICE.md` | Agreement between GymPulse AI and each gym | Sign-in page, sign-up, acceptance banner |
| `PRIVACY_POLICY.md` | How GymPulse AI handles personal data | Same |
| `DATA_PROCESSING_AGREEMENT.md` | Controller (gym) to processor (GymPulse AI) agreement for member data, under NDPA s.29 | Same |

The app shows these files exactly as written. Edit the file, change `LEGAL_VERSION` in `gympulse_legal.py`, and every gym owner is asked to accept the new version once.

**How acceptance is recorded:** at sign-up, the owner must tick (1) agreement to all three documents and (2) "I have my members' permission to store their details in GymPulse AI and to email or message them, and I'll tell my members that my gym uses GymPulse AI." The version, time and email are saved with their login and profile. Existing owners accept through a one-time banner.

## To fill in
- Registered company name, RC number, registered address, and the governing dispute forum (Terms §13).
- Data Protection Officer name and email (Privacy intro).
- Hosting regions for Supabase, Render and Sentry (Privacy §5).

## Questions for the lawyer
1. Does GymPulse AI need to register with the NDPC as a data controller or processor of major importance, and when (number of data subjects)?
2. Is clickwrap acceptance enough for the DPA, or should pilot gyms also sign a copy (a signature block is included)?
3. What is the right safeguard for transfers outside Nigeria (NDPA ss.41–43) to US/EU sub-processors: standard contractual clauses, consent, or an NDPC-approved instrument?
4. Should a gym's member-facing notice be templated? We can add a ready "Privacy notice for your members" the gym can print or send.
5. Are the breach timelines (processor tells the gym within 48h; the gym tells the NDPC within 72h) right?
6. Are the liability cap (12 months' fees) and the risk-estimate wording (NDPA s.37, automated decisions) adequate?
7. Is an annual NDPA compliance audit (CAR filing) required for GymPulse AI, and for gyms?
