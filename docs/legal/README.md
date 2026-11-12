# Legal documents: brief for the lawyer

GymPulse AI (GYMPULSE AI LTD, RC 9996401, Calabar, Cross River State) is online software that helps Nigerian gyms keep their members. These documents are written against Nigerian law, in particular the Nigeria Data Protection Act 2023 (NDPA), the Federal Competition and Consumer Protection Act 2018 (FCCPA) and the Evidence Act 2011. Please review and adapt them before GymPulse AI takes paying customers at scale.

| File | Between | What it is | Where it is used |
|---|---|---|---|
| `TERMS_OF_SERVICE.md` | GymPulse AI and each gym | General terms for using GymPulse AI | Sign-up, sign-in page, acceptance banner |
| `PRIVACY_POLICY.md` | GymPulse AI and everyone | How GymPulse AI handles personal data | Same |
| `DATA_PROCESSING_AGREEMENT.md` | Gym (controller) and GymPulse AI (processor) | Member data processing under NDPA s.29 | Same |
| `SUBSCRIPTION_AGREEMENT.md` | GymPulse AI and each paying gym | Paid plans: month to month, right to cancel, fees, member limits, refunds, liability | Signed once at the gym's first payment |
| `MEMBER_AGREEMENT.md` | Each gym and each of its members | Membership Agreement and Waiver: membership terms, health declaration, assumption of risk, waiver, emergency care, house rules, data | Signed by every member when they join |

The app shows these files exactly as written. Changing a document and its version number asks people to accept or sign the new version.

## How each document is accepted or signed
- **Terms, Privacy Policy, Data Processing Agreement:** at sign-up the gym owner ticks (1) agreement to all three and (2) "I have my members' permission to store their details in GymPulse AI and to email or message them, and I'll tell my members that my gym uses GymPulse AI." The version, time and email are saved. Existing owners accept through a one-time banner.
- **Subscription Agreement:** signed once, at the gym's first payment after its 30-day free trial. GymPulse AI's side carries the Founder's signature (Emmanuel Archibong), applied electronically. The gym's authorised person draws their signature (finger or mouse; typing the name is the fallback), chooses their role and ticks agreement. Kept: signer, role, business, email, time, IP, browser, version, a SHA-256 fingerprint of the exact text, the drawing, plan and price. A signed PDF with both signatures is emailed to the gym and the Founder.
- **Member Agreement and Waiver:** a template filled in per member (gym, member, plan, fee, dates) plus the gym's own house rules. The member answers 7 health questions, gives an emergency contact, draws their signature and ticks agreement, at the front desk on the gym's device or through a private link sent on WhatsApp. Kept: the exact text signed, its SHA-256 fingerprint, the drawing, health answers, emergency contact, how, when and from where. The gym and member can download the signed PDF.

## Still to fill in
- Terms of Service §13: the dispute forum (the Subscription Agreement uses mediation at the Lagos Multi-Door Courthouse, then the Lagos State courts; the Terms should match).
- Privacy Policy: Data Protection Officer details, and hosting regions for Supabase, Render and Sentry (§5).

## Questions for the lawyer
1. Does GymPulse AI need to register with the NDPC as a data controller or processor of major importance, and when (number of data subjects)?
2. Is clickwrap acceptance enough for the Terms and DPA, or should gyms also sign them?
3. What is the right safeguard for transfers outside Nigeria (NDPA ss.41–43) to US/EU sub-processors: standard contractual clauses, consent, or an NDPC-approved instrument?
4. Are the breach timelines (processor tells the gym within 48h; the gym tells the NDPC within 72h) right?
5. Are the liability cap (12 months' fees) and the risk-estimate wording (NDPA s.37, automated decisions) adequate?
6. Is an annual NDPA compliance audit (CAR filing) required for GymPulse AI, and for gyms?
7. **Electronic signatures:** are a drawn signature (or typed name) plus a tick, with the record and SHA-256 fingerprint described above, valid and provable under section 93 of the Evidence Act 2011 (and any other law), for both the Subscription Agreement and the Member Agreement? Is anything else needed (for example a certificate under section 84 for computer-generated evidence)?
8. **Founder's signature:** is it acceptable for GymPulse AI's side of the Subscription Agreement to carry the Founder's signature applied electronically to every copy, or should it be signed by a director in another way (or under the company's seal)?
9. **Stamp duty:** do the Subscription Agreement or the Member Agreement need to be stamped (including electronic stamping under the Stamp Duties Act as amended), and who should pay?
10. **Subscription Agreement:** are the refund terms (duplicate payments, outages over 7 days, 14 days for a yearly prepayment), the month-to-month term with the right to cancel, the member-limit clause and the FCCPA wording right?
11. **Member waiver:** clause 5 releases the gym from the normal risks of exercise and the member's own actions, but deliberately does **not** exclude liability for death or injury caused by the gym's negligence, or gross negligence. Is this the strongest wording a Nigerian court is likely to enforce? Should it differ for minors (members under 18 signed for by a parent)?
12. **Health data:** the Member Agreement collects health answers (sensitive personal data under the NDPA). Is the consent and use wording in clause 9 enough, and should gyms keep these answers separately or for a limited time?
13. **Who is the contracting party** for the Member Agreement: the gym as a business (many gyms are sole proprietors or unregistered). Does the template need to adapt for that?
14. Should a ready "Privacy notice for your members" be added for gyms to print or send?
15. **Trademark:** other products abroad use "GymPulse" in their names (e.g. gympulse.cl, gympulse.fit). Should GYMPULSE AI LTD register "GymPulse AI" (name and logo) as a trademark in Nigeria (and which classes, e.g. 9 and 42), and is there any conflict risk to check first?
