# Legal documents

GymPulse AI (GYMPULSE AI LTD, RC 9996401, Calabar, Cross River State) is a member retention platform for Nigerian gyms. These documents are written against Nigerian law: the Companies and Allied Matters Act 2020 (CAMA), the Nigeria Data Protection Act 2023 (NDPA) and the NDPC's directives, the Federal Competition and Consumer Protection Act 2018 (FCCPA) and the Evidence Act 2011.

**Status (version 1.1, 12 November 2026):** in use. They were checked clause by clause against those laws and the gaps below were closed, but they have **not yet been reviewed by a Nigerian lawyer**. The open questions at the end are the points the law doesn't clearly settle; a short fixed-fee review of those points is recommended before GymPulse AI has many paying gyms.

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

## What changed in version 1.1
- **All documents:** company identified as required by CAMA (name, "private company limited by shares", RC number, registered office in Calabar); GymPulse AI described as a member retention platform that runs alongside other gym software; "draft" labels removed.
- **Terms of Service:** dispute clause now matches the Subscription Agreement (30 days' negotiation, mediation at the Lagos Multi-Door Courthouse, then the Lagos State courts); one free trial per owner and branch rules; electronic acceptance (Evidence Act); FCCPA rights preserved; security testing without permission prohibited.
- **Privacy Policy:** Data Protection Officer (Emmanuel Archibong, emmanuel@usegympulseai.com); hosting stated (Supabase in Frankfurt, Germany; Render in Ohio, USA; others in the USA; Paystack in Nigeria); transfer safeguards (NDPA ss.41–43); health answers as sensitive data (s.30); retention of signed agreements and invoices for 6 years; cookies; children (s.31).
- **Data Processing Agreement:** sub-processor table with locations; sensitive data; NDPC registration is each controller's own responsibility; section 84 Evidence Act certificates; right to leave with a refund if a new sub-processor is unacceptable.
- **Subscription Agreement:** registered office wording; branch discount (10/15/20%); one trial per owner; signing procedure identifies the signatory (Evidence Act s.93), records kept 6 years, s.84 certificate on request; stamp duty paid by whoever the law requires; signed by Emmanuel Archibong as Founder and Director.
- **Membership Agreement and Waiver:** explicit consent for health answers (NDPA s.30) and how to withdraw it; where data is stored; members under 18 signed for by a parent or guardian (s.31); STOP and unsubscribe; complaint to the NDPC; FCCPA rights preserved.

Version numbers were raised, so gym owners accept the new Terms, Privacy Policy and DPA once (banner) and the next Subscription Agreement signature is version 1.1. Members who already signed version 1.0 of the Membership Agreement stay signed: each record keeps the exact text that member signed. New members sign version 1.1.

## Things the founder must do (no lawyer needed)
1. **NDPC registration.** Under NDPA s.44, data controllers and processors "of major importance" must register with the NDPC. The NDPC's guidance sets levels by the number of people whose data is processed in six months, with a yearly fee for each level. Check the current levels and fees on ndpc.gov.ng and register GymPulse AI at the right level; gyms with many members may need to register themselves too.
2. **Provider agreements.** Accept (or download and keep) the data processing terms of Supabase, Render, Resend, Anthropic, GitHub and Sentry, so the transfer safeguards in the Privacy Policy and DPA are on file.
3. **Annual NDPA compliance audit.** Check on ndpc.gov.ng whether GymPulse AI must file an annual compliance audit return, and when.
4. **Registered office.** The documents refer to the registered office "at the address recorded with the Corporate Affairs Commission", so the street address is never published. If CAC records change, nothing in the documents needs editing.

## Questions for the lawyer
1. Confirm the NDPC registration level for GymPulse AI as a processor for many gyms, and whether gyms must register separately.
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
