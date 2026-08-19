"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Package,
  FolderTree,
  ShoppingCart,
  Users,
  BarChart3,
  Ticket,
  Star,
  Settings,
  Shield,
  Megaphone,
  Store,
  FileText,
  Globe,
  CreditCard,
  Layers,
  Sparkles,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useSubscription, isRouteBlocked } from "@/lib/subscription-context";

const navItems = [
  { href: "/dashboard", label: "Дашборд", icon: LayoutDashboard },
  { href: "/products", label: "Товары", icon: Package },
  { href: "/channel-import", label: "AI-импорт", icon: Sparkles },
  { href: "/categories", label: "Категории", icon: FolderTree },
  { href: "/orders", label: "Заказы", icon: ShoppingCart },
  { href: "/users", label: "Пользователи", icon: Users },
  { href: "/broadcasts", label: "Рассылки", icon: Megaphone },
  { href: "/analytics", label: "Аналитика", icon: BarChart3 },
  { href: "/promos", label: "Промокоды", icon: Ticket },
  { href: "/reviews", label: "Отзывы", icon: Star },
  { href: "/admins", label: "Админы", icon: Shield },
  { href: "/settings", label: "Настройки", icon: Settings },
];

const superItems = [
  { href: "/shops", label: "Магазины", icon: Store },
  { href: "/platform", label: "Платформа", icon: Globe },
  { href: "/platform/subscriptions", label: "Подписки", icon: CreditCard },
  { href: "/platform/plans", label: "Тарифы", icon: Layers },
  { href: "/platform/payment-settings", label: "Оплата", icon: Settings },
  { href: "/offer", label: "Оферта", icon: FileText },
];

export function Sidebar({
  isSuper = false,
  shopName,
  onNavigate,
}: {
  isSuper?: boolean;
  shopName?: string;
  onNavigate?: () => void;
}) {
  const pathname = usePathname();
  const { subscriptionActive } = useSubscription();

  const items = isSuper
    ? [...navItems, ...superItems]
    : navItems;

  return (
    <aside className="flex h-full w-full flex-col border-r bg-card">
      <div className="flex h-14 shrink-0 items-center gap-2 border-b px-5">
        <span className="text-lg font-semibold">{shopName || "Магазин"}</span>
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto p-3">
        {items.map((item, idx) => {
          const active = pathname === item.href || pathname.startsWith(item.href + "/");
          const blocked = !subscriptionActive && isRouteBlocked(item.href);
          const isSectionStart = isSuper && idx === navItems.length;

          return (
            <div key={item.href}>
              {isSectionStart && (
                <div className="mb-1 mt-3 border-t px-3 pt-3">
                  <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Платформа
                  </span>
                </div>
              )}
              <Link
                href={item.href}
                onClick={onNavigate}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                  blocked && "pointer-events-none cursor-not-allowed opacity-40",
                  active && !blocked
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                )}
              >
                <item.icon className="h-4 w-4 shrink-0" />
                {item.label}
              </Link>
            </div>
          );
        })}
      </nav>
    </aside>
  );
}
