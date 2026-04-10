"""Build the Gemini system instruction dynamically per call."""

from db import build_menu_text, lookup_customer
from config import get_settings


def build_system_prompt(caller_phone: str | None = None) -> str:
    s = get_settings()
    menu = build_menu_text()

    # Personalisation block
    greeting_hint = ""
    if caller_phone:
        cust = lookup_customer(caller_phone)
        if cust and cust.get("name"):
            greeting_hint = (
                f"\nالزبون اللي عم بيتصل اسمه «{cust['name']}» وآخر عنوان توصيل كان: {cust.get('last_address', 'مش معروف')}.\n"
                f"عدد طلباته السابقة: {cust.get('order_count', 0)}.\n"
                "ابدأ بتحييه باسمه وقوله 'أهلاً وسهلاً [اسم]، كيفك؟ نورتنا مرة ثانية!'\n"
                "واسأله إذا بده نفس العنوان أو عنوان جديد.\n"
            )

    return f"""أنت «أحمد»، موظف استقبال طلبات في {s.restaurant_name} في عمّان.

## القواعد الأساسية
- احكي باللهجة الأردنية العامية فقط. ممنوع الفصحى نهائياً.
- كون ودود، خفيف دم، ومختصر. لا تطوّل بالكلام.
- إذا الزبون سأل عن شي مش موجود بالمنيو، قوله "للأسف مش متوفر عنا هاد" واقترح بديل.
- لا تخترع أصناف. التزم بالمنيو الموجودة تحت.
- بعد ما الزبون يأكد الطلب، لخّصه وأكد المبلغ الإجمالي بالدينار، واسأله عن العنوان وأي ملاحظات.
- بعد التأكيد النهائي، استدعي الأداة record_order.
- إذا الزبون بده يلغي أو يعدّل قبل التأكيد، عدّل بدون مشاكل.

## المنيو الحالية
{menu}

## معلومات الزبون
{greeting_hint if greeting_hint else "زبون جديد — اسأله عن اسمه وعنوان التوصيل."}

## الأداة المتاحة
عندك أداة واحدة: record_order — استدعيها بس يأكد الزبون طلبه نهائياً.
"""


# The Gemini function declaration for record_order
RECORD_ORDER_TOOL = {
    "function_declarations": [
        {
            "name": "record_order",
            "description": "Record a finalized food order after the customer confirms.",
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "description": "List of ordered items",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "Item name in Arabic"},
                                "qty":  {"type": "integer", "description": "Quantity"},
                                "unit_price": {"type": "number", "description": "Price per unit in JOD"}
                            },
                            "required": ["name", "qty", "unit_price"]
                        }
                    },
                    "total": {
                        "type": "number",
                        "description": "Total order price in JOD"
                    },
                    "address": {
                        "type": "string",
                        "description": "Delivery address"
                    },
                    "notes": {
                        "type": "string",
                        "description": "Special instructions or notes"
                    }
                },
                "required": ["items", "total", "address"]
            }
        }
    ]
}
