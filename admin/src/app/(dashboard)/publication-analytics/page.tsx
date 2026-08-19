"use client";

import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { ExternalLink, RefreshCw } from "lucide-react";

import { api } from "@/lib/api";
import { fetcher } from "@/lib/swr";
import { formatDate, formatPrice } from "@/lib/format";
import type { PublicationAnalyticsReport } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export default function PublicationAnalyticsPage() {
  const { data, isLoading, mutate } = useSWR<PublicationAnalyticsReport>(
    "/channel-import/publication-analytics",
    fetcher,
  );
  const [refreshing, setRefreshing] = useState(false);

  async function refreshViews() {
    setRefreshing(true);
    try {
      const result = await api.post<{ updated: number }>(
        "/channel-import/publication-analytics/views/refresh",
        undefined,
        60000,
      );
      await mutate();
      toast.success(`Обновлено публикаций: ${result.updated}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось обновить просмотры");
    } finally {
      setRefreshing(false);
    }
  }

  const summary = data?.summary;
  const cards = [
    ["Просмотры", summary?.views ?? 0],
    ["Открыли товар", summary?.opens ?? 0],
    ["Добавили в корзину", summary?.cart_adds ?? 0],
    ["Оплачено заказов", summary?.paid_orders ?? 0],
    ["CTR", `${summary?.ctr ?? 0}%`],
    ["Конверсия в покупку", `${summary?.purchase_conversion ?? 0}%`],
    ["Фактическая выручка", formatPrice(summary?.revenue ?? 0)],
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Эффективность публикаций</h1>
          <p className="text-sm text-muted-foreground">
            Путь от просмотра поста до подтверждённой оплаты.
          </p>
        </div>
        <Button variant="outline" onClick={refreshViews} disabled={refreshing}>
          <RefreshCw className={`mr-2 h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
          Обновить просмотры
        </Button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map(([title, value]) => (
          <Card key={String(title)}>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-muted-foreground">{title}</CardTitle>
            </CardHeader>
            <CardContent>
              {isLoading ? <Skeleton className="h-8 w-28" /> : <div className="text-2xl font-bold">{value}</div>}
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Публикации</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Публикация</TableHead>
                <TableHead>Товары</TableHead>
                <TableHead className="text-right">Просмотры</TableHead>
                <TableHead className="text-right">Открытия</TableHead>
                <TableHead className="text-right">Корзина</TableHead>
                <TableHead className="text-right">Оплачено</TableHead>
                <TableHead className="text-right">CTR</TableHead>
                <TableHead className="text-right">Конверсия</TableHead>
                <TableHead className="text-right">Выручка</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(data?.posts || []).map((post) => (
                <TableRow key={post.post_id}>
                  <TableCell className="max-w-72 whitespace-normal">
                    <div className="font-medium">{post.channel_title} · #{post.telegram_message_id}</div>
                    <div className="line-clamp-2 text-xs text-muted-foreground">{post.text || "Без текста"}</div>
                    <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                      {formatDate(post.published_at)}
                      {post.post_url && (
                        <a href={post.post_url} target="_blank" rel="noreferrer" className="text-primary">
                          <ExternalLink className="h-3 w-3" />
                        </a>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="max-w-56 whitespace-normal">{post.products.join(", ")}</TableCell>
                  <TableCell className="text-right">{post.views}</TableCell>
                  <TableCell className="text-right">{post.opens}</TableCell>
                  <TableCell className="text-right">{post.cart_adds}</TableCell>
                  <TableCell className="text-right">{post.paid_orders}</TableCell>
                  <TableCell className="text-right">{post.ctr}%</TableCell>
                  <TableCell className="text-right">{post.purchase_conversion}%</TableCell>
                  <TableCell className="text-right font-medium">{formatPrice(post.revenue)}</TableCell>
                </TableRow>
              ))}
              {!isLoading && !data?.posts.length && (
                <TableRow>
                  <TableCell colSpan={9} className="py-10 text-center text-muted-foreground">
                    Пока нет публикаций с товарными кнопками.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
