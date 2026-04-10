"""Supabase DB helpers — menu, customers, orders."""

from supabase import create_client, Client
from config import get_settings

_client: Client | None = None


def get_db() -> Client:
    global _client
    if _client is None:
        s = get_settings()
        _client = create_client(s.supabase_url, s.supabase_service_key)
    return _client


# ── Menu ─────────────────────────────────────────────
def get_available_menu() -> list[dict]:
    """Return all available menu items grouped by category."""
    res = get_db().table("menu_items") \
        .select("id, name, price, category") \
        .eq("is_available", True) \
        .order("category") \
        .execute()
    return res.data


def build_menu_text() -> str:
    """Build a plain-text menu string for the AI system prompt."""
    items = get_available_menu()
    if not items:
        return "القائمة فاضية حالياً."
    lines: list[str] = []
    current_cat = ""
    for it in items:
        if it["category"] != current_cat:
            current_cat = it["category"]
            lines.append(f"\n【{current_cat}】")
        lines.append(f"  • {it['name']} — {it['price']:.2f} دينار")
    return "\n".join(lines)


# ── Customers ────────────────────────────────────────
def lookup_customer(phone: str) -> dict | None:
    res = get_db().table("customers") \
        .select("*") \
        .eq("phone_number", phone) \
        .maybe_single() \
        .execute()
    return res.data


def upsert_customer(phone: str, name: str | None = None, address: str | None = None):
    payload: dict = {"phone_number": phone}
    if name:
        payload["name"] = name
    if address:
        payload["last_address"] = address
    get_db().table("customers").upsert(payload, on_conflict="phone_number").execute()


# ── Orders ───────────────────────────────────────────
def create_order(customer_phone: str, items: list[dict], total: float,
                 address: str | None = None, notes: str | None = None) -> dict:
    """Insert a new order and return the created row."""
    row = {
        "customer_phone": customer_phone,
        "items": items,
        "total_price": total,
        "delivery_address": address,
        "notes": notes,
        "status": "new",
    }
    res = get_db().table("orders").insert(row).execute()
    return res.data[0] if res.data else {}


def update_order_status(order_id: int, status: str):
    get_db().table("orders") \
        .update({"status": status}) \
        .eq("id", order_id) \
        .execute()
