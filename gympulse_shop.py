"""GymPulse AI · Shop and day passes at the front desk.

So a gym doesn't need another till: staff sell water, drinks, supplements, merchandise and day passes, paid by
cash, bank transfer or POS card, or added to a member's balance (it then shows in Balances owed).
A walk-in who buys a day pass and leaves a phone number becomes a prospect, so someone follows up.

Database: sql/phase50_shop.sql (shop_products, shop_sales, shop_sell()).
"""
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import pandas as pd
import streamlit as st

import gympulse_workspaces as gw

SQL_HINT = "The shop needs a one-time setup: run sql/phase50_shop.sql in Supabase."
CATEGORIES = {"drink": "Drink", "supplement": "Supplement", "food": "Snack", "merch": "Merchandise",
              "day_pass": "Day pass", "other": "Other"}
METHODS = {"cash": "Cash", "transfer": "Transfer", "pos": "POS card", "account": "Add to their balance"}


def _naira(x):
    return f"₦{float(x or 0):,.0f}"


def _who():
    try:
        import gympulse_door as gdoor
        return gdoor._who()
    except Exception:
        return "Front desk"


def _day_start_utc(day=None):
    day = day or gw.today_local()
    return pd.Timestamp(day).tz_localize(gw.APP_TZ).tz_convert("UTC").isoformat()


def load_products(supabase, gym_id):
    """Every product (active first), or None when phase 50 hasn't been run."""
    def load():
        try:
            return (supabase.table("shop_products").select("*").eq("gym_id", gym_id)
                    .order("active", desc=True).order("name").execute().data or [])
        except Exception:
            return None
    return gw._cached(("shop_products", gym_id), load, ttl=60)


def load_sales(supabase, gym_id, day=None):
    """Sales on one day (Lagos time), newest first."""
    day = day or gw.today_local()
    start, end = _day_start_utc(day), _day_start_utc(day + timedelta(days=1))

    def load():
        try:
            return (supabase.table("shop_sales").select("*").eq("gym_id", gym_id).gte("created_at", start)
                    .lt("created_at", end).order("created_at", desc=True).limit(500).execute().data or [])
        except Exception:
            return None
    return gw._cached(("shop_sales", gym_id, str(day)), load, ttl=30)


def today_summary(supabase, gym_id):
    """(total sales today, day passes today), or None when the shop isn't set up."""
    rows = load_sales(supabase, gym_id)
    if rows is None:
        return None
    live = [r for r in rows if not r.get("voided")]
    return sum(float(r["total"]) for r in live), sum(int(r.get("day_passes") or 0) for r in live)


def _flash(msg, kind="success"):
    st.session_state["shop_flash"] = (kind, msg)


# ================================================================== the tab
def render_shop(supabase, gym_id, members):
    flash = st.session_state.pop("shop_flash", None)
    if flash:
        (st.success if flash[0] == "success" else st.error)(flash[1])
    products = load_products(supabase, gym_id)
    if products is None:
        st.info(SQL_HINT)
        return
    sales = load_sales(supabase, gym_id) or []
    live = [s for s in sales if not s.get("voided")]
    low = [p for p in products if p.get("active") and p.get("stock") is not None
           and int(p["stock"]) <= int(p.get("low_stock_at") or 0)]
    gw.kpi_row([
        ("Sales today", _naira(sum(float(s["total"]) for s in live)), "lime", f"{len(live)} sale(s)"),
        ("Day passes today", sum(int(s.get("day_passes") or 0) for s in live), "white", "Walk-ins who paid"),
        ("Running low", len(low), "amber" if low else "white", ", ".join(p["name"] for p in low[:3]) or "Stock is fine"),
    ])
    view = st.segmented_control("Shop view", ["Sell", "Today's sales", "Products"], default="Sell",
                                key="shop_view", label_visibility="collapsed") or "Sell"
    if view == "Sell":
        _render_sell(supabase, gym_id, members, [p for p in products if p.get("active")])
    elif view == "Today's sales":
        _render_today(sales)
    else:
        _render_products(supabase, gym_id, products)


TILE_CSS = """<style>
.st-key-shop_tiles button { min-height: 64px !important; justify-content: flex-start !important; text-align: left !important; }
.st-key-shop_tiles button p { font-size: 16px !important; line-height: 1.25 !important; }
.st-key-shop_pay button { min-height: 56px !important; }
.st-key-shop_pay button p { font-size: 17px !important; font-weight: 600 !important; }
@media (max-width: 640px) {   /* phones: two products per row, in order */
  .st-key-shop_tiles [data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; gap: 8px !important; }
  .st-key-shop_tiles [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
      flex: 1 1 calc(50% - 8px) !important; min-width: calc(50% - 8px) !important; width: calc(50% - 8px) !important; }
}
</style>"""


def _add(pid, n=1):
    cart = st.session_state.setdefault("shop_cart", {})
    cart[pid] = max(0, cart.get(pid, 0) + n)
    if not cart[pid]:
        cart.pop(pid)


def _match(products, text):
    """A scanned barcode (exact) or a typed name (best match)."""
    t = (text or "").strip().lower()
    if not t:
        return None
    for p in products:
        if str(p.get("barcode") or "").strip().lower() == t:
            return p
    starts = [p for p in products if p["name"].lower().startswith(t)]
    has = [p for p in products if t in p["name"].lower()]
    pick = starts or has
    return pick[0] if len(pick) >= 1 else None


def _record(supabase, gym_id, cart, by_id, method, member_id=None, buyer="", phone=""):
    items = [{"product_id": pid, "qty": q} for pid, q in cart.items() if q > 0]
    try:
        res = supabase.rpc("shop_sell", {"p_gym_id": gym_id, "p_member_id": member_id,
                                         "p_buyer_name": buyer or None, "p_buyer_phone": phone or None,
                                         "p_items": items, "p_method": method, "p_staff": _who()}).execute().data
    except Exception as error:
        _flash(f"Could not record the sale: {getattr(error, 'message', None) or error}", "error")
        return
    res = res[0] if isinstance(res, list) and res else res
    if not (isinstance(res, dict) and res.get("ok")):
        _flash((res or {}).get("error") or "Could not record the sale.", "error")
        return
    lines = [f"{q} × {by_id[pid]['name']}" for pid, q in cart.items() if pid in by_id]
    summary = f"Sold {', '.join(lines)}: {_naira(res.get('total'))}, {METHODS[method].lower()}."
    if method == "account":
        summary += " Added to their balance."
    if res.get("day_passes") and not member_id and phone:
        summary += " They're in Prospects for a follow-up."
    st.session_state["shop_last"] = (res.get("sale_id"), summary, time.time())
    st.session_state["shop_receipt"] = (phone, buyer, lines, float(res.get("total") or 0), method)
    st.session_state["shop_cart"] = {}
    st.session_state["shop_gen"] = st.session_state.get("shop_gen", 0) + 1
    gw.bump_data_version(gym_id)


def _render_sell(supabase, gym_id, members, products):
    if not products:
        st.info("Add what you sell first, such as water, energy drinks and a day pass, under Products.")
        return
    gw._md(TILE_CSS)
    by_id = {p["id"]: p for p in products}
    cart = {pid: q for pid, q in st.session_state.setdefault("shop_cart", {}).items() if pid in by_id}
    st.session_state["shop_cart"] = cart

    last = st.session_state.get("shop_last")              # the sale just recorded, with Undo for 5 minutes
    if last and time.time() - last[2] < 300:
        c1, c2 = st.columns([4, 1], vertical_alignment="center")
        c1.success(last[1])
        if c2.button("Undo", key="shop_undo", use_container_width=True):
            try:
                r = supabase.rpc("shop_void", {"p_sale_id": last[0]}).execute().data
                r = r[0] if isinstance(r, list) and r else r
                ok = isinstance(r, dict) and r.get("ok")
            except Exception:
                ok = False
            st.session_state.pop("shop_last", None)
            st.session_state.pop("shop_receipt", None)
            gw.bump_data_version(gym_id)
            _flash("Sale undone. The stock is back." if ok else "Could not undo that sale.",
                   "success" if ok else "error")
            st.rerun()
        rec = st.session_state.get("shop_receipt")
        if rec and rec[0]:
            phone_r, buyer_r, lines, amount, method = rec
            d = gw.whatsapp_digits(phone_r)
            gym = gw._text((st.session_state.get("user_profile") or {}).get("business_name"), "the gym")
            text = (f"Hi {str(buyer_r or '').split(' ')[0] or 'there'}, thank you for your purchase at {gym}: "
                    f"{', '.join(lines)}. Total {_naira(amount)} ({METHODS[method].lower()}).")
            if d and len(d) >= 10:
                st.link_button("Send the receipt on WhatsApp", f"https://wa.me/{d}?text={quote(text)}")

    with st.form("shop_scan", clear_on_submit=True, border=False):
        c1, c2 = st.columns([5, 1], vertical_alignment="bottom")
        code = c1.text_input("Scan or type", placeholder="Scan, or type a product",
                             label_visibility="collapsed", key="shop_scan_box")
        go = c2.form_submit_button("Add", use_container_width=True)
    if go and code:
        p = _match(products, code)
        if p:
            _add(p["id"])
            st.rerun()
        st.warning(f"Nothing matches \"{code}\". Add its barcode to the product under Products.")

    with st.container(key="shop_tiles"):
        for i, p in enumerate(products):
            if i % 4 == 0:
                cols = st.columns(4)                      # rows of 4 on a computer, 2 on a phone
            q = cart.get(p["id"], 0)
            stock = p.get("stock")
            out = stock is not None and int(stock) - q <= 0
            label = f"{p['name']}  \n{_naira(p['price'])}" + (f"  ×{q}" if q else "")
            cols[i % 4].button(label, key=f"tile_{p['id']}", on_click=_add, args=(p["id"],),
                               use_container_width=True, type="primary" if q else "secondary", disabled=out,
                               help=("Out of stock" if out else None))

    total = sum(float(by_id[pid]["price"]) * q for pid, q in cart.items())
    if not cart:
        st.caption("Tap a product (or scan it) to start a sale.")
        return
    c1, c2 = st.columns([4, 1], vertical_alignment="center")
    c1.markdown("**" + ", ".join(f"{q} × {by_id[pid]['name']}" for pid, q in cart.items()) + f"**  \n{_naira(total)}")
    if c2.button("Clear", key="shop_clear", use_container_width=True):
        st.session_state["shop_cart"] = {}
        st.rerun()

    gen = st.session_state.get("shop_gen", 0)
    member_id, buyer, phone = None, "", ""
    with st.expander("More options: a member, or a walk-in's name and phone"):
        opts = {r["id"]: f'{r["full_name"]} ({gw.member_code(r["id"])})' for _, r in members.iterrows()}
        member_id = st.selectbox("Member (to add it to their balance or send a receipt)", list(opts),
                                 format_func=lambda i: opts[i], index=None, placeholder="Type a name or member code",
                                 key=f"shop_member_{gen}")
        if member_id:
            row = members[members["id"] == member_id].iloc[0]
            buyer, phone = row["full_name"], row.get("phone") or ""
        else:
            c1, c2 = st.columns(2)
            buyer = c1.text_input("Walk-in name", key=f"shop_buyer_{gen}")
            phone = c2.text_input("Walk-in phone", key=f"shop_phone_{gen}",
                                  help="With a day pass, we add them to Prospects so someone follows up.")

    with st.container(key="shop_pay"):
        methods = ["cash", "transfer", "pos"] + (["account"] if member_id else [])
        cols = st.columns(len(methods))
        for col, m in zip(cols, methods):
            label = f"Cash {_naira(total)}" if m == "cash" else METHODS[m]
            if col.button(label, key=f"pay_{m}", type="primary" if m == "cash" else "secondary",
                          use_container_width=True):
                _record(supabase, gym_id, cart, by_id, m, member_id, buyer, phone)
                st.rerun()


def _render_today(sales):
    if not sales:
        st.caption("No sales yet today.")
        return
    live = [s for s in sales if not s.get("voided")]
    by = {m: sum(float(s["total"]) for s in live if s["method"] == m) for m in METHODS}
    st.markdown("**Close the day**")
    c = st.columns(4)
    for col, m in zip(c, METHODS):
        col.metric(METHODS[m] if m != "account" else "On balances", _naira(by[m]))
    counted = st.number_input("Cash counted in the drawer (₦)", min_value=0, step=500, value=None,
                              placeholder="Count the cash, then type it here", key="shop_counted")
    if counted is not None:
        diff = float(counted) - by["cash"]
        if abs(diff) < 1:
            st.success("The cash matches today's cash sales.")
        else:
            st.warning(f"The drawer is {_naira(abs(diff))} {'over' if diff > 0 else 'short'} against today's "
                       f"cash sales of {_naira(by['cash'])}.")
    rows = []
    for s in sales:
        t = pd.Timestamp(s["created_at"]).tz_convert(gw.APP_TZ)
        items = ", ".join(f"{i.get('qty')} × {i.get('name')}" for i in (s.get("items") or []))
        rows.append({"Time": f"{t:%H:%M}", "Buyer": s.get("buyer_name") or "Walk-in", "Items": items,
                     "Paid by": METHODS.get(s["method"], s["method"]), "Total": _naira(s["total"]),
                     "Sold by": s.get("staff") or ""})
    gw.table(rows, wide=("Items",))


def _render_products(supabase, gym_id, products):
    with st.expander("Add a product", expanded=not products):
        with st.form("shop_add", clear_on_submit=True):
            c1, c2 = st.columns([2, 1])
            name = c1.text_input("Name", placeholder="e.g. Water 75cl")
            cat = c2.selectbox("Type", list(CATEGORIES), format_func=CATEGORIES.get)
            c3, c4, c5 = st.columns(3)
            price = c3.number_input("Price (₦)", min_value=0, step=100, value=None, placeholder="e.g. 300")
            stock = c4.number_input("How many in stock", min_value=0, step=1, value=None,
                                    placeholder="Leave empty if you don't count it",
                                    help="Leave empty for things you don't count, such as a day pass.")
            low = c5.number_input("Warn me at", min_value=0, step=1, value=5)
            code = st.text_input("Barcode (optional)", placeholder="Click here, then scan the product with your scanner",
                                 help="With a USB barcode scanner, scanning the product at Sell adds it to the sale.")
            if st.form_submit_button("Add product", type="primary"):
                if not name.strip() or price is None:
                    st.error("Add a name and a price.")
                else:
                    try:
                        supabase.table("shop_products").insert({
                            "gym_id": gym_id, "name": name.strip()[:60], "category": cat, "price": float(price),
                            "stock": None if (stock is None or cat == "day_pass") else int(stock),
                            "low_stock_at": int(low), "barcode": code.strip() or None}).execute()
                        gw.bump_data_version(gym_id)
                        _flash(f"{name.strip()} added.")
                        st.rerun()
                    except Exception as error:
                        st.error(f"Could not add it: {error}")
    if not products:
        return
    st.caption("Change a price or the stock count, or untick Selling to hide a product. Then press Save changes.")
    df = pd.DataFrame([{"id": p["id"], "Product": p["name"], "Type": CATEGORIES.get(p["category"], "Other"),
                        "Price (₦)": float(p["price"]), "In stock": p.get("stock"),
                        "Warn at": int(p.get("low_stock_at") or 0), "Barcode": p.get("barcode") or "",
                        "Selling": bool(p.get("active"))}
                       for p in products])
    edited = st.data_editor(
        df, hide_index=True, use_container_width=True, key="shop_editor",
        column_config={"id": None,
                       "Product": st.column_config.TextColumn(disabled=True),
                       "Type": st.column_config.TextColumn(disabled=True),
                       "Price (₦)": st.column_config.NumberColumn(min_value=0, step=50, format="%d"),
                       "In stock": st.column_config.NumberColumn(min_value=0, step=1, format="%d",
                                                                 help="Empty means not counted."),
                       "Warn at": st.column_config.NumberColumn(min_value=0, step=1, format="%d"),
                       "Barcode": st.column_config.TextColumn(help="Click the cell and scan the product.")})
    if st.button("Save changes", key="shop_save"):
        changed = 0
        for (_, a), (_, b) in zip(df.iterrows(), edited.iterrows()):
            patch = {}
            if float(b["Price (₦)"] or 0) != float(a["Price (₦)"]):
                patch["price"] = float(b["Price (₦)"] or 0)
            sa, sb = a["In stock"], b["In stock"]
            if (pd.isna(sa) != pd.isna(sb)) or (not pd.isna(sb) and int(sb) != int(sa)):
                patch["stock"] = None if pd.isna(sb) else int(sb)
            if int(b["Warn at"] or 0) != int(a["Warn at"]):
                patch["low_stock_at"] = int(b["Warn at"] or 0)
            if str(b["Barcode"] or "").strip() != str(a["Barcode"] or "").strip():
                patch["barcode"] = str(b["Barcode"] or "").strip() or None
            if bool(b["Selling"]) != bool(a["Selling"]):
                patch["active"] = bool(b["Selling"])
            if patch:
                try:
                    supabase.table("shop_products").update(patch).eq("id", a["id"]).eq("gym_id", gym_id).execute()
                    changed += 1
                except Exception as error:
                    st.error(f"Could not save {a['Product']}: {error}")
                    return
        gw.bump_data_version(gym_id)
        _flash(f"Saved {changed} product(s)." if changed else "Nothing changed.")
        st.rerun()
