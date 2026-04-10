import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "مطعم أبو خليل — لوحة التحكم",
  description: "AI Call Center Dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ar" dir="rtl">
      <body className="bg-zinc-950 text-zinc-100 min-h-screen font-sans">
        <nav className="border-b border-zinc-800 px-6 py-3 flex items-center gap-6">
          <span className="text-lg font-bold text-amber-400">🍽️ أبو خليل</span>
          <Link href="/" className="text-sm hover:text-amber-300 transition">الطلبات</Link>
          <Link href="/menu" className="text-sm hover:text-amber-300 transition">المنيو</Link>
        </nav>
        <main className="p-6 max-w-6xl mx-auto">{children}</main>
      </body>
    </html>
  );
}
