"""
Phase 5: Kitchen Printer
========================
Listens to Supabase Realtime INSERT events on `orders` table
and prints a formatted receipt on a thermal printer via python-escpos.

Usage:
    pip install supabase realtime-py python-escpos python-dotenv
    python printer.py

For USB printer:  escpos.printer.Usb(0x04b8, 0x0202)
For Network:      escpos.printer.Network("192.168.1.100")
"""

import asyncio
import json
import os
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

# ── Printer Setup ──
# Uncomment ONE of these depending on your printer connection:

# USB Printer (find vendor/product IDs with `lsusb`):
# from escpos.printer import Usb
# printer = Usb(0x04b8, 0x0202, profile="TM-T88V")

# Network Printer:
# from escpos.printer import Network
# printer = Network("192.168.1.100")

# For development/testing — print to console:
class ConsolePrinter:
    """Mock printer that outputs to terminal."""
    def set(self, *a, **kw): pass
    def text(self, t): print(t, end="")
    def cut(self): print("\n" + "=" * 40 + " [CUT] " + "=" * 40 + "\n")
    def ln(self, n=1): print("\n" * n, end="")

printer = ConsolePrinter()


def format_order(order: dict) -> str:
    """Format an order for thermal printing (58mm or 80mm)."""
    W = 32  # chars per line on 58mm paper

    lines = []
    lines.append("=" * W)
    lines.append("مطعم أبو خليل".center(W))
    lines.append("=" * W)
    lines.append(f"طلب رقم: #{order.get('id', '?')}")

    ts = order.get("created_at", "")
    if ts:
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            lines.append(f"التاريخ: {dt.strftime('%Y-%m-%d %H:%M')}")
        except Exception:
            lines.append(f"التاريخ: {ts[:16]}")

    lines.append(f"هاتف: {order.get('customer_phone', '-')}")
    lines.append(f"عنوان: {order.get('delivery_address', '-')}")
    lines.append("-" * W)

    items = order.get("items", [])
    if isinstance(items, str):
        items = json.loads(items)

    for it in items:
        name = it.get("name", "?")
        qty = it.get("qty", 1)
        price = it.get("unit_price", 0)
        subtotal = qty * price
        line = f"{qty}x {name}"
        price_str = f"{subtotal:.2f}"
        padding = W - len(line) - len(price_str)
        if padding < 1:
            padding = 1
        lines.append(f"{line}{' ' * padding}{price_str}")

    lines.append("-" * W)
    total_str = f"{order.get('total_price', 0):.2f} JOD"
    lines.append(f"{'المجموع:':<{W - len(total_str)}}{total_str}")
    lines.append("=" * W)

    notes = order.get("notes", "")
    if notes:
        lines.append(f"ملاحظات: {notes}")
        lines.append("=" * W)

    lines.append("")
    return "\n".join(lines)


def print_order(order: dict):
    """Send formatted order to printer."""
    text = format_order(order)
    printer.text(text)
    printer.cut()
    print(f"[PRINTER] Order #{order.get('id')} printed.")


async def listen():
    """Subscribe to Supabase Realtime INSERT on orders table."""
    from supabase import create_client

    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    channel = sb.channel("kitchen-printer")

    def on_insert(payload):
        record = payload.get("new") or payload.get("record", {})
        print(f"[REALTIME] New order received: #{record.get('id')}")
        print_order(record)

    channel.on_postgres_changes(
        event="INSERT",
        schema="public",
        table="orders",
        callback=on_insert,
    ).subscribe()

    print("[PRINTER] Listening for new orders... (Ctrl+C to quit)")

    # Keep alive
    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(listen())
