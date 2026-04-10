"use client";

import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";

type MenuItem = {
  id: number;
  name: string;
  price: number;
  is_available: boolean;
  category: string;
};

export default function MenuPage() {
  const [items, setItems] = useState<MenuItem[]>([]);
  const [grouped, setGrouped] = useState<Record<string, MenuItem[]>>({});

  useEffect(() => {
    fetchMenu();
  }, []);

  useEffect(() => {
    const g: Record<string, MenuItem[]> = {};
    items.forEach((it) => {
      (g[it.category] ||= []).push(it);
    });
    setGrouped(g);
  }, [items]);

  async function fetchMenu() {
    const { data } = await supabase
      .from("menu_items")
      .select("*")
      .order("category")
      .order("name");
    setItems((data as MenuItem[]) || []);
  }

  async function toggleAvailability(item: MenuItem) {
    const next = !item.is_available;
    await supabase
      .from("menu_items")
      .update({ is_available: next })
      .eq("id", item.id);
    setItems((prev) =>
      prev.map((i) => (i.id === item.id ? { ...i, is_available: next } : i))
    );
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">إدارة المنيو</h1>

      {Object.entries(grouped).map(([cat, catItems]) => (
        <div key={cat} className="mb-8">
          <h2 className="text-sm font-semibold text-amber-400 mb-3 uppercase tracking-wider">
            {cat}
          </h2>
          <div className="grid gap-2">
            {catItems.map((item) => (
              <div
                key={item.id}
                className={`flex items-center justify-between bg-zinc-900 border rounded-lg px-4 py-3 transition ${
                  item.is_available
                    ? "border-zinc-800"
                    : "border-red-500/30 opacity-60"
                }`}
              >
                <div className="flex items-center gap-3">
                  <span className="text-sm">{item.name}</span>
                  <span className="text-xs text-zinc-500">
                    {item.price.toFixed(2)} د.أ
                  </span>
                </div>

                <button
                  onClick={() => toggleAvailability(item)}
                  className={`relative w-11 h-6 rounded-full transition-colors ${
                    item.is_available ? "bg-emerald-500" : "bg-zinc-700"
                  }`}
                >
                  <span
                    className={`absolute top-0.5 w-5 h-5 bg-white rounded-full transition-transform ${
                      item.is_available ? "right-0.5" : "right-[22px]"
                    }`}
                  />
                </button>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
