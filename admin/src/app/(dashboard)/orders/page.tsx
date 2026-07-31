"use client";

import useSWR from "swr";
import { useState } from "react";
import Link from "next/link";
import { fetcher } from "@/lib/swr";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { formatPrice, formatDate, STATUS_LABELS } from "@/lib/format";
import type { Order } from "@/lib/types";

export default function OrdersPage() {
  const [status, setStatus] = useState<string>("all");

  const { data, isLoading } = useSWR(
    `/orders?${status !== "all" ? `status=${status}&` : ""}page=1&per_page=50`,
    fetcher,
  );

  const orders = data?.orders || [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Заказы</h1>
        <Select value={status} onValueChange={(v) => setStatus(v || "all")}>
          <SelectTrigger className="w-48">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Все статусы</SelectItem>
            {Object.entries(STATUS_LABELS).map(([value, label]) => (
              <SelectItem key={value} value={value}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="space-y-2 p-4">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : orders.length === 0 ? (
            <p className="p-8 text-center text-muted-foreground">Нет заказов</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-16">№</TableHead>
                  <TableHead>Клиент</TableHead>
                  <TableHead>Телефон</TableHead>
                  <TableHead className="text-right">Сумма</TableHead>
                  <TableHead>Статус</TableHead>
                  <TableHead>Дата</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {orders.map((order: Order) => (
                  <TableRow
                    key={order.id}
                    className="cursor-pointer"
                  >
                    <TableCell className="font-medium">
                      <Link href={`/orders/${order.id}`} className="block">
                        #{order.id}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <Link href={`/orders/${order.id}`} className="block">
                        {order.full_name}
                      </Link>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {order.phone}
                    </TableCell>
                    <TableCell className="text-right font-semibold">
                      {formatPrice(order.total_amount)}
                    </TableCell>
                    <TableCell>
                      <Link href={`/orders/${order.id}`}>
                        <Badge variant="outline">
                          {STATUS_LABELS[order.status] || order.status}
                        </Badge>
                      </Link>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {formatDate(order.created_at)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
