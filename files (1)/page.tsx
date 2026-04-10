"use client";

import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { Clock, CheckCircle, Truck, XCircle, ChefHat } from "lucide-react";

type Order = {
  id: number;
  customer_phone: string;
  items: { name: string; qty: number; unit_price: number }[];
  total_price: number;
  status: string;
  delivery_address: string | null;
  notes: string | null;
  created_at: string;
};

const STATUS_FLOW = ["new", "preparing", "ready", "delivered"];

const STATUS_META: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  new:       { label: "جديد",    color: "bg-amber-500/20 text-amber-400 border-amber-500/30", icon: <Clock size={14} /> },
  preparing: { label: "تحضير",   color: "bg-blue-500/20 text-blue-400 border-blue-500/30",    icon: <ChefHat size={14} /> },
  ready:     { label: "جاهز",    color: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30", icon: <CheckCircle size={14} /> },
  delivered: { label: "تم التوصيل", color: "bg-zinc-700/40 text-zinc-400 border-zinc-600/30", icon: <Truck size={14} /> },
  cancelled: { label: "ملغي",    color: "bg-red-500/20 text-red-400 border-red-500/30",       icon: <XCircle size={14} /> },
};

export default function OrdersPage() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [filter, setFilter] = useState<string>("active");

  // Fetch orders
  useEffect(() => {
    fetchOrders();

    // Subscribe to realtime changes
    const channel = supabase
      .channel("orders-realtime")
      .on("postgres_changes", { event: "*", schema: "public", table: "orders" }, () => {
        fetchOrders();
      })
      .subscribe();

    return () => { supabase.removeChannel(channel); };
  }, [filter]);

  async function fetchOrders() {
    let q = supabase
      .from("orders")
      .select("*")
      .order("created_at", { ascending: false })
      .limit(100);

    if (filter === "active") {
      q = q.in("status", ["new", "preparing", "ready"]);
    }

    const { data } = await q;
    setOrders((data as Order[]) || []);
  }

  async function advanceStatus(order: Order) {
    const idx = STATUS_FLOW.indexOf(order.status);
    if (idx < 0 || idx >= STATUS_FLOW.length - 1) return;
    const next = STATUS_FLOW[idx + 1];
    await supabase.from("orders").update({ status: next }).eq("id", order.id);
  }

  async function cancelOrder(id: number) {
    await supabase.from("orders").update({ status: "cancelled" }).eq("id", id);
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">الطلبات</h1>
        <div className="flex gap-2">
          {["active", "all"].map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1.5 text-xs rounded-full border transition ${
                filter === f
                  ? "bg-amber-500/20 text-amber-300 border-amber-500/40"
                  : "border-zinc-700 text-zinc-400 hover:border-zinc-500"
              }`}
            >
              {f === "active" ? "النشطة" : "الكل"}
            </button>
          ))}
        </div>
      </div>

      {orders.length === 0 ? (
        <p className="text-zinc-500 text-center py-20">لا يوجد طلبات</p>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {orders.map((o) => {
            const meta = STATUS_META[o.status] || STATUS_META.new;
            return (
              <div
                key={o.id}
                className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 flex flex-col gap-3"
              >
                {/* Header */}
                <div className="flex items-center justify-between">
                  <span className="font-mono text-sm text-zinc-400">#{o.id}</span>
                  <span className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border ${meta.color}`}>
                    {meta.icon} {meta.label}
                  </span>
                </div>

                {/* Items */}
                <div className="space-y-1 text-sm">
                  {(o.items || []).map((it, i) => (
                    <div key={i} className="flex justify-between">
                      <span>{it.qty}× {it.name}</span>
                      <span className="text-zinc-400">{(it.qty * it.unit_price).toFixed(2)}</span>
                    </div>
                  ))}
                </div>

                <div className="border-t border-zinc-800 pt-2 flex justify-between text-sm font-semibold">
                  <span>المجموع</span>
                  <span className="text-amber-400">{o.total_price?.toFixed(2)} د.أ</span>
                </div>

                {/* Meta */}
                <div className="text-xs text-zinc-500 space-y-0.5">
                  <div>📞 {o.customer_phone}</div>
                  {o.delivery_address && <div>📍 {o.delivery_address}</div>}
                  {o.notes && <div>📝 {o.notes}</div>}
                  <div>{new Date(o.created_at).toLocaleTimeString("ar-JO")}</div>
                </div>

                {/* Actions */}
                {!["delivered", "cancelled"].includes(o.status) && (
                  <div className="flex gap-2 mt-auto">
                    <button
                      onClick={() => advanceStatus(o)}
                      className="flex-1 bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 text-xs py-2 rounded-lg transition"
                    >
                      {o.status === "new" ? "ابدأ التحضير" : o.status === "preparing" ? "جاهز" : "تم التوصيل"}
                    </button>
                    <button
                      onClick={() => cancelOrder(o.id)}
                      className="bg-red-500/10 hover:bg-red-500/20 text-red-400 text-xs px-3 py-2 rounded-lg transition"
                    >
                      إلغاء
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
