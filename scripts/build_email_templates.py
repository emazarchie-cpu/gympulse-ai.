"""Build branded Supabase email templates from one place.

Edit the wording in TEMPLATES below, then run:
    python scripts/build_email_templates.py
It writes one HTML file per email into docs/email-templates/. Paste each file
into Supabase → Authentication → Emails → <template> → Message body (Source),
and set the subject shown in docs/email-templates/README.md.

Words in {{ double braces }} are filled in by Supabase. Keep them as they are:
  {{ .ConfirmationURL }}  the link the person clicks
  {{ .Token }}            the 6-digit code
  {{ .Email }}            their email address
  {{ .NewEmail }}         their new address (change email)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gympulse_email as ge  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "email-templates")

TEMPLATES = {
    # Authentication
    "confirm-signup": {
        "subject": "Confirm your GymPulse AI account",
        "title": "Welcome to GymPulse AI",
        "body": ("<p>Thanks for signing up. Confirm your email address to open your workspace and start "
                 "seeing who's drifting, why, and how to keep them.</p>"
                 + ge.button("Confirm my email", "{{ .ConfirmationURL }}")
                 + "<p style=\"margin:18px 0 0;font-size:13px;color:#5B6678\">Button not working? Copy this link "
                   "into your browser:<br><a href=\"{{ .ConfirmationURL }}\" style=\"color:#0B8F5A;word-break:break-all\">"
                   "{{ .ConfirmationURL }}</a></p>"),
        "footer": "You received this because someone signed up for GymPulse AI with {{ .Email }}. "
                  "If that wasn't you, you can ignore this email.",
    },
    "invite-user": {
        "subject": "You've been invited to GymPulse AI",
        "title": "You're invited to GymPulse AI",
        "body": ("<p>You've been invited to join a GymPulse AI workspace. Accept the invite to set your password "
                 "and get started.</p>" + ge.button("Accept invite", "{{ .ConfirmationURL }}")),
        "footer": "If you weren't expecting this invite, you can ignore this email.",
    },
    "magic-link": {
        "subject": "Your GymPulse AI sign-in link",
        "title": "Sign in to GymPulse AI",
        "body": ("<p>Tap the button to sign in. The link works once and expires soon.</p>"
                 + ge.button("Sign in", "{{ .ConfirmationURL }}")
                 + "<p style=\"margin:18px 0 6px\">Or enter this code:</p>" + ge.code_box("{{ .Token }}")),
        "footer": "If you didn't ask to sign in, you can ignore this email. Your account is safe.",
    },
    "change-email": {
        "subject": "Confirm your new GymPulse AI email",
        "title": "Confirm your new email address",
        "body": ("<p>You asked to change your GymPulse AI email from <b>{{ .Email }}</b> to "
                 "<b>{{ .NewEmail }}</b>. Confirm to finish.</p>" + ge.button("Confirm new email", "{{ .ConfirmationURL }}")),
        "footer": "If you didn't ask for this, reply to this email straight away.",
    },
    "reset-password": {
        "subject": "Your GymPulse AI password reset code",
        "title": "Reset your password",
        "body": ("<p>Enter this code in GymPulse AI to choose a new password:</p>" + ge.code_box("{{ .Token }}")
                 + "<p style=\"margin:0\">The code expires in one hour and works once.</p>"),
        "footer": "If you didn't ask to reset your password, you can ignore this email. Your password won't change.",
    },
    "reauthentication": {
        "subject": "Your GymPulse AI verification code",
        "title": "Confirm it's you",
        "body": "<p>Enter this code to continue:</p>" + ge.code_box("{{ .Token }}"),
        "footer": "If you didn't ask for this code, someone may know your password. Change it in Settings.",
    },
    # Security notifications
    "password-changed": {
        "subject": "Your GymPulse AI password was changed",
        "title": "Your password was changed",
        "body": "<p>The password for <b>{{ .Email }}</b> was just changed.</p>",
        "footer": "If this wasn't you, reset your password straight away and reply to this email.",
    },
    "email-changed": {
        "subject": "Your GymPulse AI email was changed",
        "title": "Your email address was changed",
        "body": "<p>Your GymPulse AI account email was changed to <b>{{ .Email }}</b>.</p>",
        "footer": "If this wasn't you, reply to this email straight away.",
    },
    "phone-changed": {
        "subject": "Your GymPulse AI phone number was changed",
        "title": "Your phone number was changed",
        "body": "<p>The phone number on your GymPulse AI account ({{ .Email }}) was changed.</p>",
        "footer": "If this wasn't you, reply to this email straight away.",
    },
    "sign-in-method-linked": {
        "subject": "A new sign-in method was added to GymPulse AI",
        "title": "New sign-in method added",
        "body": "<p>A new way to sign in was linked to your GymPulse AI account ({{ .Email }}).</p>",
        "footer": "If this wasn't you, change your password and reply to this email.",
    },
    "sign-in-method-removed": {
        "subject": "A sign-in method was removed from GymPulse AI",
        "title": "Sign-in method removed",
        "body": "<p>A sign-in method was removed from your GymPulse AI account ({{ .Email }}).</p>",
        "footer": "If this wasn't you, reply to this email straight away.",
    },
}

SUPABASE_NAMES = {
    "confirm-signup": "Authentication → Confirm sign up",
    "invite-user": "Authentication → Invite user",
    "magic-link": "Authentication → Magic link or OTP",
    "change-email": "Authentication → Change email address",
    "reset-password": "Authentication → Reset password",
    "reauthentication": "Authentication → Reauthentication",
    "password-changed": "Security → Password changed",
    "email-changed": "Security → Email address changed",
    "phone-changed": "Security → Phone number changed",
    "sign-in-method-linked": "Security → Sign-in method linked",
    "sign-in-method-removed": "Security → Sign-in method removed",
}


def main():
    os.makedirs(OUT, exist_ok=True)
    rows = []
    for key, t in TEMPLATES.items():
        html = ge.layout(t["title"], t["body"], preheader=t["title"], footer_html=t.get("footer", ""))
        with open(os.path.join(OUT, f"{key}.html"), "w", encoding="utf-8") as f:
            f.write(html)
        rows.append(f"| {SUPABASE_NAMES[key]} | `{t['subject']}` | `docs/email-templates/{key}.html` |")
    readme = (
        "# GymPulse AI email templates for Supabase\n\n"
        "Generated by `scripts/build_email_templates.py`. To change wording, edit that file and run it again.\n\n"
        "**How to install:** Supabase → Authentication → Emails → open a template → set **Subject** → "
        "switch the message body to **Source** → replace everything with the file's contents → **Save**.\n\n"
        "| Supabase template | Subject | File |\n|---|---|---|\n" + "\n".join(rows) + "\n\n"
        "## Send them from your own address (recommended)\n\n"
        "Supabase's built-in sender is limited to a few emails an hour and comes from a Supabase address. "
        "Send through your Resend account instead:\n\n"
        "1. Supabase → Authentication → Emails → **SMTP Settings** → turn on **Enable custom SMTP**.\n"
        "2. Fill in the fields below, then **Save**.\n\n"
        "| Field | Value |\n|---|---|\n"
        "| Sender email | `notifications@usegympulseai.com` |\n"
        "| Sender name | `GymPulse AI` |\n"
        "| Host | `smtp.resend.com` |\n"
        "| Port | `465` |\n"
        "| Username | `resend` |\n"
        "| Password | your Resend API key (`re_...`) |\n\n"
        "3. Under **Rate limits**, raise the email limit, for example to 60 an hour.\n")
    with open(os.path.join(OUT, "README.md"), "w", encoding="utf-8") as f:
        f.write(readme)
    print(f"Wrote {len(TEMPLATES)} templates to {OUT}")


if __name__ == "__main__":
    main()
