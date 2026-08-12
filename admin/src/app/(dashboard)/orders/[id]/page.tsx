"use client";

import useSWR from "swr";
import { useParams } from "next/navigation";
import Link from "next/link";
import { fetcher } from "@/lib/swr";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ArrowLeft } from "lucide-react";
import { formatPrice, formatDate, STATUS_LABELS } from "@/lib/format";
import type { OrderDetail } from "@/lib/types";
import { useState } from "react";

export default function OrderDetailPage() {
  const params = useParams();
  const id = params.id as string;

  const { data: order, mutate } = useSWR<OrderDetail>(`/orders/${id}`, fetcher);
  const [newStatus, setNewStatus] = useState("");

  async function changeStatus() {
    if (!newStatus) return;

    try {
      await api.patch(`/orders/${id}/status`, { status: newStatus });
      mutate();
      toast.success("Статус обновлён");
      setNewStatus("");
    } catch {
      toast.error("Ошибка");
    }
  }

  if (!order) {
    return <Skeleton className="h-96 w-full" />;
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" render={<Link href="/orders" />}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <h1 className="text-2xl font-bold">Заказ #{order.id}</h1>
        <Badge variant="outline">
          {STATUS_LABELS[order.status] || order.status}
        </Badge>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Клиент</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            <div>
              <span className="text-muted-foreground">Имя: </span>
              <span className="font-medium">{order.full_name}</span>
            </div>
            <div>
              <span className="text-muted-foreground">Телефон: </span>
              <span className="font-medium">{order.phone}</span>
            </div>
            {order.address && (
              <div>
                <span className="text-muted-foreground">Адрес: </span>
                <span className="font-medium">{order.address}</span>
              </div>
            )}
            {order.telegram_user_id && (
              <div>
                <span className="text-muted-foreground">Telegram ID: </span>
                <span className="font-medium">{order.telegram_user_id}</span>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Информация</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            <div>
              <span className="text-muted-foreground">Дата: </span>
              <span className="font-medium">{formatDate(order.created_at)}</span>
            </div>
            {order.promo_code && (
              <div>
                <span className="text-muted-foreground">Промокод: </span>
                <Badge variant="secondary">{order.promo_code}</Badge>
              </div>
            )}
            {order.discount_amount ? (
              <div>
                <span className="text-muted-foreground">Скидка: </span>
                <span className="font-medium text-red-600">
                  −{formatPrice(order.discount_amount)}
                </span>
              </div>
            ) : null}
            {order.comment && (
              <div className="pt-2">
                <span className="text-muted-foreground">Комментарий: </span>
                <p className="mt-1 rounded-lg bg-muted p-2 text-sm">{order.comment}</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Состав заказа</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {order.items?.map((item, i) => (
            <div key={i} className="flex items-center justify-between border-b pb-2 last:border-0">
              <div>
                <p className="font-medium">{item.product_name}</p>
                <p className="text-sm text-muted-foreground">
                  {item.variant_volume} × {item.quantity} шт.
                </p>
              </div>
              <span className="font-semibold">{formatPrice(item.price * item.quantity)}</span>
            </div>
          ))}

          <div className="flex items-center justify-between pt-3">
            <span className="font-bold">Итого:</span>
            <span className="text-xl font-bold">{formatPrice(order.total_amount)}</span>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Смена статуса</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-3">
            <Select value={newStatus} onValueChange={(v) => setNewStatus(v || "")} items={STATUS_LABELS}>
              <SelectTrigger className="w-48">
                <SelectValue placeholder="Выберите статус" />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(STATUS_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button onClick={changeStatus} disabled={!newStatus}>
              Применить
            </Button>
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            Клиент получит уведомление в Telegram
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
