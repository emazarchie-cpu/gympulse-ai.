"""GymPulse AI · Pay the gym by QR code: shop items, day passes, membership renewals and balances owed.

One QR code at the counter covers every payment. The customer chooses what they're paying for:
  Buy something       the shop (below)
  Renew my membership they type their phone number; the renewal is paid and recorded by gympulse_memberpay
  Pay what I owe      the same, towards their balance owed (gympulse_memberpay._apply_balance)
Staff only check the "Paid online today" list in Check-in → Shop.

Shop orders:

A QR code on the counter or fridge opens usegympulseai.com/?shop=<join code>. The customer taps what they want and
pays through Paystack (bank transfer, card or USSD) to the gym's own bank account, using the gym's subaccount from
online renewals (gympulse_memberpay). When Paystack confirms, the server records the sale by itself
(shop_record_online, sql/phase55_shop_online.sql): stock goes down, it shows in Today's sales, and the customer gets
an order number. The front desk sees it in Online orders (Check-in → Shop) and taps Handed over.

Each payment is recorded once (shop_sales.pay_ref). Payments where the customer closed the page are picked up by the
Paystack sync job (gympulse_billing.reconcile_paystack, source "gympulse_shop").
The gym switches it on in Check-in → Shop → Products → Order by QR code (profiles.settings["shop_online"]).
"""
import json
import uuid
from datetime import date
from urllib.parse import quote as url_quote

import streamlit as st

import gympulse_workspaces as gw

SHOP_PARAM, DONE_PARAM = "shop", "shop_done"


# One QR code per kind of payment, plus the all-in-one code (no "for")
KINDS = {"shop": ("Shop", "For the fridge or counter: drinks, supplements and merch"),
         "walkin": ("Walk-in day pass", "For the door: visitors pay for a day pass"),
         "renew": ("Renew membership", "For the front desk: members renew their plan"),
         "balance": ("Pay balance", "For the front desk: members pay what they owe")}


def print_card(url, label, gym):
    """A printable card (PNG, 1200 x 1650): gym name, what it's for, the QR code, and how to pay."""
    import io
    import os
    import qrcode
    from PIL import Image, ImageDraw, ImageFont
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts")

    def font(bold, size):
        try:
            return ImageFont.truetype(os.path.join(here, f"InstrumentSans-{'Bold' if bold else 'Regular'}.ttf"), size)
        except OSError:
            return ImageFont.load_default(size)
    navy, lime, grey = (11, 18, 32), (190, 242, 100), (90, 98, 112)
    W, H = 1200, 1650
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    d.text((100, 110), gw._text(gym, "")[:40], font=font(False, 44), fill=grey)
    big = font(True, 96)
    words, lines, cur = label.split(), [], ""
    for w in words:                                   # wrap the label to the card width
        t = (cur + " " + w).strip()
        if d.textlength(t, font=big) > W - 200 and cur:
            lines.append(cur)
            cur = w
        else:
            cur = t
    lines.append(cur)
    y = 180
    for ln in lines[:2]:
        d.text((100, y), ln, font=big, fill=navy)
        y += 110
    qr = qrcode.make(url, box_size=20, border=1).convert("RGB")
    side = 820
    qr = qr.resize((side, side), Image.NEAREST)
    img.paste(qr, ((W - side) // 2, y + 50))
    y += 50 + side + 50
    d.text((100, y), "Open your phone camera and point it here.", font=font(False, 44), fill=navy)
    d.text((100, y + 64), "Transfer, card or USSD, secured by Paystack.", font=font(False, 36), fill=grey)
    d.rectangle((0, H - 120, W, H), fill=navy)
    d.text((100, H - 88), "Scan to pay", font=font(True, 48), fill=lime)
    d.text((W - 100, H - 80), "GymPulse AI", font=font(False, 34), fill=(200, 205, 215), anchor="ra")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def shop_link(code, kind=None):
    return f"{gw.APP_URL}/?{SHOP_PARAM}={code}" + (f"&for={kind}" if kind in KINDS else "")


def _naira(x):
    return f"₦{float(x or 0):,.0f}"


def _gym(sc, code):
    """(gym row, owner settings) for a shop code, or (None, {})."""
    try:
        g = (sc.table("gyms").select("id, business_name, owner_id, join_code").eq("join_code", str(code))
             .limit(1).execute().data or [None])[0]
    except Exception:
        g = None
    if not g:
        return None, {}
    try:
        prof = (sc.table("profiles").select("settings").eq("id", g["owner_id"]).limit(1).execute().data or [{}])[0]
    except Exception:
        prof = {}
    return g, dict(prof.get("settings") or {})


def is_on(settings):
    return bool(dict(settings.get("shop_online") or {}).get("on"))


def _products(sc, gym_id):
    try:
        return (sc.table("shop_products").select("id, name, price, stock, category").eq("gym_id", gym_id)
                .eq("active", True).order("name").execute().data or [])
    except Exception:
        return []


# ================================================================== the customer's page (?shop=<code>)
CHOICES = ["Shop", "Renew", "Pay balance"]


def find_member(sc, gym_id, phone):
    """The current member with this phone number (last 10 digits match), or None."""
    want = gw.whatsapp_digits(phone)[-10:]
    if len(want) < 10:
        return None
    try:
        rows = gw.fetch_all(sc.table("members").select("id, full_name, phone, archived").eq("gym_id", gym_id)
                            .order("id"))
    except Exception:
        return None
    hits = [r for r in rows if not r.get("archived") and gw.whatsapp_digits(r.get("phone"))[-10:] == want]
    return hits[0] if len(hits) == 1 else None


def _go(url):
    st.link_button("Continue to secure payment", url, type="primary", use_container_width=True)
    st.markdown(f'<meta http-equiv="refresh" content="0; url={url}">', unsafe_allow_html=True)


def render_public(code):
    import gympulse_booking as gb
    import gympulse_memberpay as gmp
    gb._header()
    col = gw.center("shopqr", 560)
    with col:
        sc = gmp._service()
        g, settings = _gym(sc, code) if sc else (None, {})
        if not g or not is_on(settings) or not gmp.gym_account(sc, g["id"]):
            gw._md('<div class="bk-title">Paying by QR isn\'t open</div>'
                   '<div class="bk-sub">Please pay at the front desk.</div>')
            return
        gym = g.get("business_name") or "the gym"
        kind = st.query_params.get("for")
        kind = kind if kind in KINDS else None
        title = {None: f"Pay {gym}", "shop": f"Shop at {gym}", "walkin": f"Day pass at {gym}",
                 "renew": f"Renew at {gym}", "balance": f"Pay your balance at {gym}"}[kind]
        gw._md(f'<div class="bk-title">{gw._esc(title)}</div>'
               '<div class="bk-sub">Pay on your phone. The front desk sees it straight away.</div>')
        if kind is None:
            what = st.segmented_control("What are you paying for?", CHOICES, default=CHOICES[0], key="sq_what") \
                or CHOICES[0]
            kind = {CHOICES[0]: "all", CHOICES[1]: "renew", CHOICES[2]: "balance"}[what]
        if kind in ("all", "shop", "walkin"):
            _render_buy(sc, g, gmp, kind)
        else:
            _render_member_pay(sc, g, gmp, renew=kind == "renew")
        st.caption("Pay by bank transfer, card or USSD, secured by Paystack. The money goes straight to the gym.")


def _render_member_pay(sc, g, gmp, renew):
    phone = st.text_input("Your phone number (the one the gym has)", key="sq_mphone", placeholder="e.g. 0803 000 0000")
    if not phone.strip():
        return
    found = find_member(sc, g["id"], phone)
    if not found:
        st.info("We couldn't find a member with that number. Please pay at the front desk.")
        return
    m, (plan, amount) = gmp._member(sc, found["id"])
    first = (gw._text(m.get("full_name")).split() or ["there"])[0]
    if renew:
        if amount <= 0:
            st.info(f"Hi {first}. Your plan price isn't set yet. Please renew at the front desk.")
            return
        ends = (f", ending {date.fromisoformat(str(m['membership_end'])[:10]):%-d %B}"
                if m.get("membership_end") else "")
        gw._md(f'<div class="bk-sub">Hi {gw._esc(first)}. Your {gw._esc(gw.plan_phrase(plan))} plan{ends}.</div>'
               f'<div style="font-size:30px;font-weight:700;margin:6px 0 4px">₦{amount:,.0f}</div>')
        if m.get("_offer"):
            st.caption(f"Includes your {int(m['_offer']['percent'])}% discount for staying.")
        if st.button(f"Renew for ₦{amount:,.0f}", type="primary", use_container_width=True, key="sq_renew"):
            url, msg = gmp.start(sc, m, plan, amount, gmp._email_for(m), False)
            _go(url) if url else st.error(msg)
        return
    rows = sc.table("members").select("balance_owed").eq("id", m["id"]).limit(1).execute().data or [{}]
    owed = float(rows[0].get("balance_owed") or 0)
    if owed <= 0:
        st.success(f"Hi {first}. You don't owe anything. Thank you!")
        return
    gw._md(f'<div class="bk-sub">Hi {gw._esc(first)}. You owe</div>'
           f'<div style="font-size:30px;font-weight:700;margin:6px 0 4px">₦{owed:,.0f}</div>')
    amount = st.number_input("Amount to pay now (₦)", min_value=min(100.0, owed), max_value=owed, value=owed,
                             step=500.0, format="%.0f", key="sq_bal_amt")
    if st.button(f"Pay ₦{amount:,.0f}", type="primary", use_container_width=True, key="sq_bal_pay"):
        url, msg = gmp.start_balance(sc, m, amount)
        _go(url) if url else st.error(msg)


def _render_buy(sc, g, gmp, kind="all"):
    products = [p for p in _products(sc, g["id"]) if p.get("stock") is None or int(p["stock"]) > 0]
    if kind == "walkin":
        products = [p for p in products if p.get("category") == "day_pass"]
    elif kind == "shop":
        products = [p for p in products if p.get("category") != "day_pass"]
    if not products:
        st.caption("Day passes aren't set up yet. Please pay at the front desk." if kind == "walkin"
                   else "Nothing is available to buy right now.")
        return
    cart = st.session_state.setdefault("sq_cart", {})
    for p in products:
        c1, c2 = st.columns([3, 1.3], vertical_alignment="center")
        c1.markdown(f"**{p['name']}**  \n{_naira(p['price'])}")
        top = 20 if p.get("stock") is None else min(20, int(p["stock"]))
        cart[p["id"]] = c2.number_input(p["name"], 0, top, int(cart.get(p["id"], 0)), 1,
                                        key=f"sq_{p['id']}", label_visibility="collapsed")
    chosen = {pid: q for pid, q in cart.items() if q}
    by_id = {p["id"]: p for p in products}
    total = sum(float(by_id[pid]["price"]) * q for pid, q in chosen.items() if pid in by_id)
    name = st.text_input("Your name (so the front desk knows it's you)", key="sq_name")
    phone = st.text_input("Phone" + ("" if kind == "walkin" else " (optional)"), key="sq_phone",
                          help="So the gym can welcome you back." if kind == "walkin" else None)
    if st.button(f"Pay {_naira(total)}" if chosen else "Choose something first", type="primary",
                 use_container_width=True, disabled=not chosen, key="sq_pay"):
        acc = gmp.gym_account(sc, g["id"])
        ref = f"gs-{str(g['id'])[:8]}-{uuid.uuid4().hex[:12]}"
        items = [{"product_id": pid, "qty": int(q)} for pid, q in chosen.items() if pid in by_id]
        r = gmp._paystack("POST", "/transaction/initialize", json={
            "email": f"shop{uuid.uuid4().hex[:10]}@members.usegympulseai.com",
            "amount": int(round(total * 100)), "currency": "NGN", "reference": ref,
            "subaccount": acc["subaccount"], "bearer": "subaccount",
            "callback_url": f"{gw.APP_URL}/?{DONE_PARAM}=1",
            "metadata": {"source": "gympulse_shop", "gym_id": g["id"], "items": items,
                         "buyer": name.strip()[:80], "phone": phone.strip()[:30]}})
        url = (r.get("data") or {}).get("authorization_url") if r.get("status") else None
        if not url:
            st.error("We couldn't open the payment page. Please try again, or pay at the front desk.")
            return
        _go(url)


def apply(reference, sc=None):
    """Check a shop payment with Paystack and record the order (once). Returns (ok, message, details)."""
    import gympulse_memberpay as gmp
    sc = sc or gmp._service()
    r = gmp._paystack("GET", f"/transaction/verify/{url_quote(str(reference), safe='')}")
    d = r.get("data") or {}
    if not r.get("status") or d.get("status") != "success":
        return False, "Your payment hasn't gone through yet. If money left your account, it will show shortly.", {}
    md = d.get("metadata") or {}
    if isinstance(md, str):
        try:
            md = json.loads(md)
        except ValueError:
            md = {}
    if md.get("source") != "gympulse_shop" or not md.get("gym_id"):
        return False, "That payment isn't a shop order.", {}
    res = sc.rpc("shop_record_online", {"p_gym_id": md["gym_id"], "p_items": md.get("items") or [],
                                        "p_buyer_name": md.get("buyer") or None,
                                        "p_buyer_phone": md.get("phone") or None, "p_ref": str(reference),
                                        "p_paid": (d.get("amount") or 0) / 100}).execute().data
    res = res[0] if isinstance(res, list) and res else res
    if not (isinstance(res, dict) and res.get("ok")):
        import gympulse_billing as gbill
        gbill._email_founder(f"Shop payment to check: {reference}",
                             f"A shop payment ({reference}, gym {md.get('gym_id')}) wasn't recorded: {res}.")
        return False, "We've received your payment. Please show this screen at the front desk.", {}
    return True, "Paid", res


def render_done(params):
    import gympulse_booking as gb
    gb._header()
    col = gw.center("shopqr_done", 560)
    with col:
        ref = params.get("reference") or params.get("trxref")
        if not ref:
            st.error("We couldn't find your payment. If money left your account, show your bank alert at the desk.")
            return
        ok, msg, res = apply(ref)
        if not ok:
            st.warning(msg)
            if st.button("Check again", type="primary"):
                st.rerun()
            return
        items = ", ".join(f"{i.get('qty')} × {i.get('name')}" for i in (res.get("items") or []))
        gw._md(f'<div class="bk-sub">Paid {_naira(res.get("total"))}</div>'
               f'<div style="font-size:64px;font-weight:700;line-height:1;margin:8px 0 6px">Order {res.get("order_no")}</div>'
               f'<div class="bk-sub">{gw._esc(items)}</div>')
        st.success("Show this screen at the front desk to collect your order.")
        st.session_state.pop("sq_cart", None)


# ================================================================== the front desk (Check-in → Shop)
def pending_orders(supabase, gym_id):
    """Today's paid online orders not handed over yet, read fresh (customers add them from their phones)."""
    import gympulse_shop as gs
    try:
        return (supabase.table("shop_sales").select("id, order_no, buyer_name, items, total")
                .eq("gym_id", gym_id).eq("method", "online").eq("voided", False).is_("handed_over_at", "null")
                .gte("created_at", gs._day_start_utc()).order("order_no").limit(50).execute().data or [])
    except Exception:
        return []


def paid_online_today(supabase, gym_id):
    """Today's renewals and balance payments made online, newest first: [{name, what, amount}]."""
    try:
        pays = (supabase.table("payments").select("member_id, amount, plan, note, kind")
                .eq("gym_id", gym_id).eq("method", "Paystack (online)").eq("paid_on", gw.today_local().isoformat())
                .order("created_at", desc=True).limit(50).execute().data or [])
    except Exception:
        return []
    if not pays:
        return []
    ids = list({p["member_id"] for p in pays if p.get("member_id")})
    try:
        names = {r["id"]: r["full_name"] for r in supabase.table("members").select("id, full_name")
                 .in_("id", ids).execute().data or []}
    except Exception:
        names = {}
    out = []
    for p in pays:
        bal = gw._text(p.get("note"), "") == "Balance payment"
        out.append({"name": names.get(p.get("member_id"), "A member"),
                    "what": "paid towards their balance" if bal
                    else f"renewed ({gw._text(p.get('plan'), 'membership')})",
                    "amount": p.get("amount")})
    return out


def render_orders(supabase, gym_id):
    """Everything paid by QR today. Shop orders wait for Handed over. Refreshes by itself every 10 seconds."""
    @st.fragment(run_every=10)
    def _orders():
        rows = pending_orders(supabase, gym_id)
        paid = paid_online_today(supabase, gym_id)
        if not rows and not paid:
            return
        with st.container(border=True, key="sq_feed"):
            if rows:
                st.markdown(f"**Paid online, to hand over ({len(rows)})**")
            for r in sorted(rows, key=lambda x: x.get("order_no") or 0):
                items = ", ".join(f"{i.get('qty')} × {i.get('name')}" for i in (r.get("items") or []))
                c1, c2 = st.columns([4, 1.3], vertical_alignment="center")
                c1.markdown(f"**Order {r.get('order_no')}**, {gw._esc(r.get('buyer_name') or 'customer')}: "
                            f"{gw._esc(items)}, {_naira(r.get('total'))} paid", unsafe_allow_html=True)
                if c2.button("Handed over", key=f"sq_done_{r['id']}", type="primary", use_container_width=True):
                    from datetime import datetime, timezone
                    supabase.table("shop_sales").update({"handed_over_at": datetime.now(timezone.utc).isoformat()}) \
                        .eq("id", r["id"]).eq("gym_id", gym_id).execute()
                    gw.bump_data_version(gym_id)
                    st.rerun()
            if paid:
                st.markdown(f"**Paid online today ({len(paid)})**")
                st.caption("Already recorded. Nothing to do.")
                for p in paid:
                    st.markdown(f"{gw._esc(p['name'])} {gw._esc(p['what'])}, {_naira(p['amount'])}",
                                unsafe_allow_html=True)
    _orders()


def render_setup(supabase, gym_id, code):
    """Products view: switch QR ordering on and get the QR code to print."""
    import gympulse_grow as gg
    import gympulse_memberpay as gmp
    import gympulse_signup as gsign
    import gympulse_team as gteam
    prof = st.session_state.get("user_profile") or {}
    settings = dict(prof.get("settings") or {})
    with st.expander("Pay by QR code (shop, renewals and balances)"):
        st.caption("Print one QR code for the counter. Customers scan it and pay for shop items, day passes, their "
                   "membership renewal or what they owe, by transfer, card or USSD through Paystack. Every payment "
                   "records itself and shows at the top of this tab. Paystack's fee is taken from each payment, as "
                   "with online renewals.")
        try:
            sc = gmp._service()
            has_acc = bool(sc and gmp.gym_account(sc, gym_id))
        except Exception:
            has_acc = False
        if not has_acc:
            st.info("First switch on online payments in Grow → Renewals & messages → Collect renewals. The money "
                    "then goes straight to your bank account.")
            return
        if not code:
            st.info("Turn on your member sign-up link first (Grow); the QR code uses the same gym code.")
            return
        on = is_on(settings)
        if not gteam.is_staff():
            if st.toggle("Take payments by QR code", value=on, key="sq_on") != on:
                gg._save_settings(supabase, prof.get("id"), {"shop_online": {"on": not on}},
                                  "Paying by QR " + ("switched off." if on else "switched on."))
                st.rerun()
        if on:
            gym_name = gw._text(prof.get("business_name"), "")
            st.markdown("**A QR code for each kind of payment.** Print each one and put it where people pay "
                        "for that thing.")
            cols = st.columns(2)
            for i, (k, (label, where)) in enumerate(KINDS.items()):
                with cols[i % 2].container(border=True):
                    url = shop_link(code, k)
                    st.markdown(f"**{label}**")
                    st.caption(where)
                    st.image(gsign._qr_png(url), width=160)
                    st.download_button("Download to print", print_card(url, label, gym_name), f"QR {label}.png",
                                       "image/png",
                                       key=f"sq_dl_{k}", use_container_width=True)
            with st.container(border=True):
                url = shop_link(code)
                st.markdown("**All in one**")
                st.caption("One code for everything: the customer chooses Shop, Renew or Pay balance.")
                st.image(gsign._qr_png(url), width=160)
                st.download_button("Download to print", print_card(url, "Pay the gym", gym_name),
                                   "QR All payments.png", "image/png",
                                   key="sq_dl_all")
                st.code(url, language=None)
