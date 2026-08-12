"use client";

import useSWR from "swr";
import { superAdminFetcher } from "@/lib/swr";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Store, TrendingUp, Clock, AlertCircle, PlusCircle, Wallet } from "lucide-react";
import { formatPrice } from "@/lib/format";
import type { PlatformStats } from "@/lib/types";

export default function PlatformDashboardPage() {
  const { data, isLoading } = useSWR<PlatformStats>(
    "/dashboard",
    superAdminFetcher,
  );

  if (isLoading || !data) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[...Array(6)].map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      </div>
    );
  }

  const cards = [
    {
      label: "Всего магазинов",
      value: data.total_shops.toString(),
      sub: `+${data.new_shops_30d} за 30 дней`,
      icon: Store,
      color: "text-blue-500",
    },
    {
      label: "Активные",
      value: data.active_shops.toString(),
      sub: "с действующей подпиской",
      icon: TrendingUp,
      color: "text-green-500",
    },
    {
      label: "Триал",
      value: data.trial_shops.toString(),
      sub: "пробный период",
      icon: Clock,
      color: "text-amber-500",
    },
    {
      label: "Просрочены",
      value: data.expired_shops.toString(),
      sub: "подписка истекла",
      icon: AlertCircle,
      color: "text-red-500",
    },
    {
      label: "Новые (30 дней)",
      value: data.new_shops_30d.toString(),
      sub: "зарегистрированы",
      icon: PlusCircle,
      color: "text-purple-500",
    },
    {
      label: "Выручка платформы",
      value: formatPrice(data.total_revenue),
      sub: "оплаченные подписки",
      icon: Wallet,
      color: "text-emerald-500",
    },
  ];

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Платформа</h1>
        <p className="text-sm text-muted-foreground">
          Обзор всех магазинов и подписок
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {cards.map((card) => (
          <Card key={card.label}>
            <CardContent className="flex items-center gap-4 p-5">
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-muted">
                <card.icon className={`h-6 w-6 ${card.color}`} />
              </div>
              <div className="min-w-0">
                <p className="text-2xl font-bold">{card.value}</p>
                <p className="truncate text-sm font-medium text-muted-foreground">
                  {card.label}
                </p>
                <p className="truncate text-xs text-muted-foreground">{card.sub}</p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
