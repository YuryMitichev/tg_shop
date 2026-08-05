"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Sidebar } from "@/components/layout/sidebar";
import { SubscriptionBanner } from "@/components/layout/subscription-banner";
import { SubscriptionProvider, isRouteBlocked } from "@/lib/subscription-context";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { LogOut } from "lucide-react";
import { usePathname } from "next/navigation";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [ready, setReady] = useState(false);
  const [subscriptionActive, setSubscriptionActive] = useState(true);
  const [isSuper, setIsSuper] = useState(false);
  const [shopName, setShopName] = useState("");

  useEffect(() => {
    api
      .get<{ telegram_user_id: number; subscription_active: boolean; is_super_admin: boolean; shop_name: string }>("/auth/me")
      .then((res) => {
        setSubscriptionActive(res.subscription_active ?? true);
        setIsSuper(res.is_super_admin ?? false);
        setShopName(res.shop_name ?? "");
        setReady(true);
      })
      .catch(() => router.push("/login"));
  }, [router]);

  async function handleLogout() {
    try {
      await api.post("/auth/logout");
    } catch {
      // игнорируем — всё равно редиректим
    }
    router.push("/login");
  }

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-muted-foreground">Загрузка...</p>
      </div>
    );
  }

  const showBanner = !subscriptionActive && isRouteBlocked(pathname);

  return (
    <SubscriptionProvider subscriptionActive={subscriptionActive}>
      <div className="flex min-h-screen">
        <div className="hidden md:block">
          <Sidebar isSuper={isSuper} shopName={shopName} />
        </div>

        <div className="flex flex-1 flex-col">
          <header className="flex h-14 items-center justify-between border-b bg-card px-6">
            <div className="flex-1" />
            <Button variant="ghost" size="sm" onClick={handleLogout}>
              <LogOut className="mr-2 h-4 w-4" />
              Выйти
            </Button>
          </header>

          <main className="flex-1 overflow-y-auto p-6">
            {showBanner && <SubscriptionBanner />}
            {children}
          </main>
        </div>
      </div>
    </SubscriptionProvider>
  );
}
