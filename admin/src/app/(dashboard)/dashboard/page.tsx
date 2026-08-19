"use client";

import useSWR from "swr";
import { fetcher } from "@/lib/swr";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatPrice } from "@/lib/format";
import type { Stats, RevenueChartItem } from "@/lib/types";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import { TrendingUp, ShoppingCart, CircleCheckBig, Wallet, XCircle, Percent } from "lucide-react";

export default function DashboardPage() {
  const { data: stats, isLoading } = useSWR<Stats>("/stats", fetcher);
  const { data: chart } = useSWR<RevenueChartItem[]>("/analytics/revenue?days=30", fetcher);

  const cards = [
    {
      title: "Выручка за всё время",
      value: stats ? formatPrice(stats.total_revenue) : "—",
      icon: Wallet,
      color: "text-green-600",
    },
    {
      title: "Выручка за месяц",
      value: stats ? formatPrice(stats.month_revenue) : "—",
      icon: TrendingUp,
      color: "text-blue-600",
    },
    {
      title: "Создано заказов",
      value: stats?.total_orders ?? "—",
      icon: ShoppingCart,
      color: "text-purple-600",
    },
    {
      title: "Оплачено заказов",
      value: stats?.paid_orders ?? "—",
      icon: CircleCheckBig,
      color: "text-amber-600",
    },
    {
      title: "Отменено заказов",
      value: stats?.cancelled_orders ?? "—",
      icon: XCircle,
      color: "text-red-600",
    },
    {
      title: "Конверсия заказ → оплата",
      value: stats ? `${stats.payment_conversion_rate}%` : "—",
      icon: Percent,
      color: "text-cyan-600",
    },
  ];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Дашборд</h1>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {cards.map((card) => (
          <Card key={card.title}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                {card.title}
              </CardTitle>
              <card.icon className={`h-4 w-4 ${card.color}`} />
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <Skeleton className="h-8 w-32" />
              ) : (
                <div className="text-2xl font-bold">{card.value}</div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Выручка за 30 дней</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <AreaChart data={chart || []}>
                <defs>
                  <linearGradient id="rev" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 12 }}
                  tickFormatter={(v) => v.slice(5)}
                />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip
                  formatter={(value) => [formatPrice(Number(value)), "Выручка"]}
                />
                <Area
                  type="monotone"
                  dataKey="revenue"
                  stroke="#3b82f6"
                  fill="url(#rev)"
                  strokeWidth={2}
                />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Топ товаров</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {isLoading ? (
              [...Array(5)].map((_, i) => <Skeleton key={i} className="h-12 w-full" />)
            ) : stats?.top_products?.length ? (
              stats.top_products.map((p, i) => (
                <div key={i} className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="flex h-6 w-6 items-center justify-center rounded-full bg-muted text-xs font-bold">
                      {i + 1}
                    </span>
                    <span className="text-sm">{p.name}</span>
                  </div>
                  <span className="text-sm font-semibold text-muted-foreground">
                    {formatPrice(p.revenue)}
                  </span>
                </div>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">Нет данных</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
