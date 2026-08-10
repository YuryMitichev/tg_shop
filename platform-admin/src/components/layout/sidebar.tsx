"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Globe, Store, CreditCard, Layers, Settings } from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/dashboard", label: "Обзор", icon: Globe },
  { href: "/shops", label: "Магазины", icon: Store },
  { href: "/subscriptions", label: "Подписки", icon: CreditCard },
  { href: "/plans", label: "Тарифы", icon: Layers },
  { href: "/payment-settings", label: "Оплата", icon: Settings },
];

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();

  return (
    <aside className="flex h-full w-full flex-col border-r bg-card">
      <div className="flex h-14 shrink-0 items-center gap-2 border-b px-5">
        <Globe className="h-5 w-5 text-primary" />
        <span className="text-lg font-semibold">Платформа</span>
      </div>
      <nav className="flex-1 space-y-1 overflow-y-auto p-3">
        {navItems.map((item) => {
          const active = pathname === item.href || pathname.startsWith(item.href + "/");
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                active
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
              )}
            >
              <item.icon className="h-4 w-4 shrink-0" />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
