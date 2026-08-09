"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Sidebar } from "@/components/layout/sidebar";
import { SubscriptionBanner } from "@/components/layout/subscription-banner";
import { SubscriptionProvider, isRouteBlocked } from "@/lib/subscription-context";
import { api, clearToken } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { LogOut, Menu } from "lucide-react";
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
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

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
    clearToken();
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
        <div className="hidden w-64 shrink-0 md:block">
          <Sidebar isSuper={isSuper} shopName={shopName} />
        </div>

        <Sheet open={mobileNavOpen} onOpenChange={setMobileNavOpen}>
          <SheetContent side="left" className="p-0" showCloseButton>
            <Sidebar
              isSuper={isSuper}
              shopName={shopName}
              onNavigate={() => setMobileNavOpen(false)}
            />
          </SheetContent>
        </Sheet>

        <div className="flex flex-1 flex-col">
          <header className="flex h-14 items-center justify-between border-b bg-card px-4 md:px-6">
            <Button
              variant="ghost"
              size="icon"
              className="md:hidden"
              onClick={() => setMobileNavOpen(true)}
            >
              <Menu className="h-5 w-5" />
            </Button>
            <span className="truncate pl-2 text-sm font-medium text-muted-foreground md:hidden">
              {shopName || "Магазин"}
            </span>
            <div className="hidden flex-1 md:block" />
            <Button variant="ghost" size="sm" onClick={handleLogout}>
              <LogOut className="h-4 w-4 sm:mr-2" />
              <span className="hidden sm:inline">Выйти</span>
            </Button>
          </header>

          <main className="flex-1 overflow-y-auto p-4 md:p-6">
            {showBanner && <SubscriptionBanner />}
            {children}
          </main>
        </div>
      </div>
    </SubscriptionProvider>
  );
}
