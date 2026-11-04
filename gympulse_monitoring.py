"""GymPulse AI · error alerts with Sentry.

Set SENTRY_DSN on Render (and as a GitHub secret for the scheduled jobs) to get
an email whenever something breaks. Without it, nothing happens. Personal data
is never sent: no names, emails, phone numbers or request bodies, and any email
address or phone number in an error message is masked before it leaves.
"""
import os
import re

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"\+?\d[\d\s-]{8,}\d")
_started = False


def _scrub(text):
    if not isinstance(text, str):
        return text
    return _PHONE.sub("[phone]", _EMAIL.sub("[email]", text))


def _before_send(event, hint):
    event.pop("user", None)
    event.pop("request", None)
    for exc in (event.get("exception") or {}).get("values") or []:
        exc["value"] = _scrub(exc.get("value"))
        for frame in (exc.get("stacktrace") or {}).get("frames") or []:
            frame.pop("vars", None)             # local variables can hold member data
    if event.get("logentry"):
        event["logentry"]["message"] = _scrub(event["logentry"].get("message"))
        event["logentry"].pop("params", None)
    if event.get("message"):
        event["message"] = _scrub(event["message"])
    for crumb in (event.get("breadcrumbs") or {}).get("values") or []:
        crumb["message"] = _scrub(crumb.get("message"))
        crumb.pop("data", None)
    return event


def init(component="app"):
    """Start error reporting once per process (safe to call on every rerun)."""
    global _started
    if _started:
        return
    _started = True
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return
    try:
        import logging
        import sentry_sdk
        from sentry_sdk.integrations.logging import LoggingIntegration
        sentry_sdk.init(
            dsn=dsn,
            environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
            release=os.environ.get("RENDER_GIT_COMMIT", "")[:12] or None,
            send_default_pii=False,
            include_local_variables=False,
            traces_sample_rate=0,
            before_send=_before_send,
            # Streamlit logs every uncaught page error at ERROR level ("Uncaught app execution").
            integrations=[LoggingIntegration(level=logging.WARNING, event_level=logging.ERROR)],
        )
        sentry_sdk.set_tag("component", component)
    except Exception:
        pass


def capture(error, where=""):
    """Report an error we caught and handled (e.g. a failed email), without stopping the app."""
    try:
        import sentry_sdk
        with sentry_sdk.new_scope() as scope:
            if where:
                scope.set_tag("where", where)
            sentry_sdk.capture_exception(error)
    except Exception:
        pass
