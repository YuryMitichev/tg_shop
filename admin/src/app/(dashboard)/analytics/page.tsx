"use client";

import useSWR from "swr";
import { useState } from "react";
import { fetcher } from "@/lib/swr";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  AreaChart,
  Area,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Star, TrendingUp, TrendingDown, Users, Ticket } from "lucide-react";
import { formatPrice } from "@/lib/format";
import type {
  Stats,
  RevenueChartItem,
  AnalyticsOverview,
  CategoryStat,
  ProductStat,
  CustomerStats,
  PromoStats,
  ReviewStats,
} from "@/lib/types";

const PIE_COLORS = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#6b7280"];
const STAR_COLORS = ["#ef4444", "#f97316", "#f59e0b", "#84cc16", "#10b981"];

function Growth({ value }: { value: number }) {
  if (value > 0) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-green-600">
        <TrendingUp className="h-3 w-3" />+{value}%
      </span>
    );
  }
  if (value < 0) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-red-600">
        <TrendingDown className="h-3 w-3" />{value}%
      </span>
    );
  }
  return <span className="text-xs text-muted-foreground">0%</span>;
}

function KpiCard({
  title,
  value,
  growth,
  isLoading,
}: {
  title: string;
  value: string;
  growth?: number;
  isLoading?: boolean;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-7 w-28" />
        ) : (
          <div className="flex items-center gap-2">
            <span className="text-2xl font-bold">{value}</span>
            {growth !== undefined && <Growth value={growth} />}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function AnalyticsPage() {
  const [days, setDays] = useState(30);

  const { data: stats } = useSWR<Stats>("/stats", fetcher);
  const { data: chart } = useSWR<RevenueChartItem[]>(`/analytics/revenue?days=${days}`, fetcher);
  const { data: overview, isLoading: ovLoading } = useSWR<AnalyticsOverview>(
    `/analytics/overview?days=${days}`,
    fetcher,
  );
  const { data: categories } = useSWR<CategoryStat[]>(`/analytics/categories?days=${days}`, fetcher);
  const { data: products } = useSWR<ProductStat[]>(`/analytics/products?days=${days}`, fetcher);
  const { data: customers, isLoading: custLoading } = useSWR<CustomerStats>(
    `/analytics/customers?days=${days}`,
    fetcher,
  );
  const { data: promos } = useSWR<PromoStats>(`/analytics/promos?days=${days}`, fetcher);
  const { data: reviews } = useSWR<ReviewStats>("/analytics/reviews", fetcher);

  const statusData = stats
    ? [
        { name: "Новые", value: stats.new_orders },
        { name: "Отменены", value: stats.cancelled_orders },
        {
          name: "Завершены",
          value: stats.total_orders - stats.new_orders - stats.cancelled_orders,
        },
      ]
    : [];

  const customerPieData = customers
    ? [
        { name: "Новые", value: customers.new_customers },
        { name: "Вернувшиеся", value: customers.returning_customers },
      ]
    : [];

  const promoPieData = promos
    ? [
        { name: "С промокодом", value: promos.orders_with_promo },
        { name: "Без промокода", value: promos.orders_without_promo },
      ]
    : [];

  const ratingData = reviews
    ? [5, 4, 3, 2, 1].map((star) => ({
        name: `${star}★`,
        value: reviews.distribution[String(star)] || 0,
      }))
    : [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Аналитика</h1>
        <div className="flex gap-2">
          {[7, 30, 90].map((d) => (
            <Button
              key={d}
              variant={days === d ? "default" : "outline"}
              size="sm"
              onClick={() => setDays(d)}
            >
              {d} дней
            </Button>
          ))}
        </div>
      </div>

      {/* KPI */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          title="Выручка"
          value={formatPrice(overview?.revenue || 0)}
          growth={overview?.revenue_growth}
          isLoading={ovLoading}
        />
        <KpiCard
          title="Средний чек"
          value={formatPrice(overview?.avg_order_value || 0)}
          growth={overview?.aov_growth}
          isLoading={ovLoading}
        />
        <KpiCard
          title="Создано заказов"
          value={String(overview?.created_orders || 0)}
          growth={overview?.orders_growth}
          isLoading={ovLoading}
        />
        <KpiCard
          title="Оплачено заказов"
          value={String(overview?.paid_orders || 0)}
          growth={overview?.paid_orders_growth}
          isLoading={ovLoading}
        />
      </div>

      {/* Дополнительные KPI */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Конверсия заказ → оплата
            </CardTitle>
          </CardHeader>
          <CardContent>
            {ovLoading ? (
              <Skeleton className="h-7 w-20" />
            ) : (
              <div className="text-2xl font-bold">{overview?.order_to_payment_rate || 0}%</div>
            )}
            <div className="mt-1 text-xs text-muted-foreground">
              {overview?.paid_orders || 0} из {overview?.created_orders || 0} заказов
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Повторные покупки
            </CardTitle>
          </CardHeader>
          <CardContent>
            {ovLoading ? (
              <Skeleton className="h-7 w-20" />
            ) : (
              <div className="text-2xl font-bold">{overview?.repeat_rate || 0}%</div>
            )}
            <div className="mt-1 text-xs text-muted-foreground">
              {overview?.repeat_customers || 0} клиентов вернулись
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Товаров в заказе
            </CardTitle>
          </CardHeader>
          <CardContent>
            {ovLoading ? (
              <Skeleton className="h-7 w-20" />
            ) : (
              <div className="text-2xl font-bold">{overview?.avg_items_per_order || 0}</div>
            )}
            <div className="mt-1 text-xs text-muted-foreground">в среднем</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">LTV</CardTitle>
          </CardHeader>
          <CardContent>
            {custLoading ? (
              <Skeleton className="h-7 w-28" />
            ) : (
              <div className="text-2xl font-bold">{formatPrice(customers?.ltv || 0)}</div>
            )}
            <div className="mt-1 text-xs text-muted-foreground">
              {customers?.total_customers || 0} клиентов всего
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Динамика выручки */}
      <Card>
        <CardHeader>
          <CardTitle>Динамика выручки ({days} дн.)</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={chart || []}>
              <defs>
                <linearGradient id="rev" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
              <XAxis dataKey="date" tick={{ fontSize: 12 }} tickFormatter={(v) => v.slice(5)} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip formatter={(value) => [formatPrice(Number(value)), "Выручка"]} />
              <Area type="monotone" dataKey="revenue" stroke="#10b981" fill="url(#rev)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* Заказы по дням + Статусы */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Заказы по дням</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={chart || []}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis dataKey="date" tick={{ fontSize: 12 }} tickFormatter={(v) => v.slice(5)} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip />
                <Bar dataKey="created_orders" name="Создано" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                <Bar dataKey="paid_orders" name="Оплачено" fill="#10b981" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Статусы заказов</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={250}>
              <PieChart>
                <Pie
                  data={statusData}
                  cx="50%"
                  cy="50%"
                  innerRadius={50}
                  outerRadius={80}
                  dataKey="value"
                  label={({ name, value }) => `${name}: ${value}`}
                >
                  {statusData.map((_, i) => (
                    <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                  ))}
                </Pie>
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* Категории + Топ товаров по количеству */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Выручка по категориям ({days} дн.)</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={categories || []}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis
                  dataKey="name"
                  tick={{ fontSize: 11 }}
                  tickFormatter={(v, i) => `${categories?.[i]?.emoji || ""} ${v}`}
                />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip formatter={(value) => [formatPrice(Number(value)), "Выручка"]} />
                <Bar dataKey="revenue" fill="#f59e0b" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Топ товаров по количеству ({days} дн.)</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={products || []} layout="vertical" margin={{ left: 100 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis type="number" tick={{ fontSize: 12 }} />
                <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={100} />
                <Tooltip />
                <Bar dataKey="quantity" fill="#8b5cf6" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* Клиенты + Промокоды */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Users className="h-4 w-4" /> Новые vs вернувшиеся
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie
                  data={customerPieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={45}
                  outerRadius={75}
                  dataKey="value"
                  label={({ name, value }) => `${name}: ${value}`}
                >
                  {customerPieData.map((_, i) => (
                    <Cell key={i} fill={i === 0 ? "#10b981" : "#3b82f6"} />
                  ))}
                </Pie>
                <Legend />
              </PieChart>
            </ResponsiveContainer>
            {customers?.top_customers && customers.top_customers.length > 0 && (
              <div className="mt-4 space-y-2">
                <div className="text-xs font-medium text-muted-foreground">Топ клиентов</div>
                {customers.top_customers.map((c, i) => (
                  <div key={i} className="flex items-center justify-between text-sm">
                    <span>{c.name}</span>
                    <span className="font-medium">
                      {c.orders} зак. · {formatPrice(c.spent)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Ticket className="h-4 w-4" /> Промокоды ({days} дн.)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie
                  data={promoPieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={45}
                  outerRadius={75}
                  dataKey="value"
                  label={({ name, value }) => `${name}: ${value}`}
                >
                  {promoPieData.map((_, i) => (
                    <Cell key={i} fill={i === 0 ? "#8b5cf6" : "#6b7280"} />
                  ))}
                </Pie>
                <Legend />
              </PieChart>
            </ResponsiveContainer>
            {promos && (
              <div className="mt-4 space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Сумма скидок</span>
                  <span className="font-medium text-red-600">{formatPrice(promos.total_discount)}</span>
                </div>
                {promos.top_promos.length > 0 && (
                  <>
                    <div className="text-xs font-medium text-muted-foreground pt-1">Топ промокодов</div>
                    {promos.top_promos.map((p, i) => (
                      <div key={i} className="flex items-center justify-between text-sm">
                        <span className="font-mono">{p.code}</span>
                        <span>
                          {p.uses} раз · −{formatPrice(p.discount)}
                        </span>
                      </div>
                    ))}
                  </>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Отзывы */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Star className="h-4 w-4" /> Рейтинги и отзывы
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-6 sm:grid-cols-3">
            <div className="space-y-2">
              <div className="text-4xl font-bold">{reviews?.avg_rating || 0}</div>
              <div className="flex">
                {[1, 2, 3, 4, 5].map((s) => (
                  <Star
                    key={s}
                    className={`h-4 w-4 ${
                      s <= Math.round(reviews?.avg_rating || 0)
                        ? "fill-amber-400 text-amber-400"
                        : "text-muted-foreground"
                    }`}
                  />
                ))}
              </div>
              <div className="text-xs text-muted-foreground">
                {reviews?.total_reviews || 0} отзывов
              </div>
            </div>
            <div className="sm:col-span-2">
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={ratingData}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                  <YAxis tick={{ fontSize: 12 }} allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                    {ratingData.map((_, i) => (
                      <Cell key={i} fill={STAR_COLORS[4 - i]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Топ товаров по выручке (всё время) */}
      <Card>
        <CardHeader>
          <CardTitle>Топ товаров по выручке (всё время)</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart
              data={stats?.top_products || []}
              layout="vertical"
              margin={{ left: 120 }}
            >
              <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
              <XAxis type="number" tick={{ fontSize: 12 }} />
              <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={120} />
              <Tooltip formatter={(value) => [formatPrice(Number(value)), "Выручка"]} />
              <Bar dataKey="revenue" fill="#8b5cf6" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </div>
  );
}
