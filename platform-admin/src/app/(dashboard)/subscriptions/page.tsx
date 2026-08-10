"use client";

import useSWR from "swr";
import { superAdminFetcher, superAdminApi } from "@/lib/swr";
import { useState } from "react";
import { toast } from "sonner";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogClose } from "@/components/ui/dialog";
import { formatDate, formatPrice } from "@/lib/format";
import type { PlatformSubscription } from "@/lib/types";

const STATUS_LABELS: Record<string, string> = {
  trial: "Триал",
  active: "Активна",
  expired: "Истекла",
  cancelled: "Отменена",
};

export default function SubscriptionsPage() {
  const [filter, setFilter] = useState<string>("all");
  const [extendShop, setExtendShop] = useState<PlatformSubscription | null>(null);
  const [addDays, setAddDays] = useState("30");
  const [extending, setExtending] = useState(false);

  const queryParams = filter !== "all" ? `?status=${filter}` : "";
  const { data, isLoading, mutate } = useSWR<{ subscriptions: PlatformSubscription[] }>(
    `/subscriptions${queryParams}`,
    superAdminFetcher,
  );

  const subscriptions = data?.subscriptions ?? [];

  function openExtend(sub: PlatformSubscription) { setExtendShop(sub); setAddDays("30"); }

  async function handleExtend() {
    if (!extendShop) return;
    const days = parseInt(addDays, 10);
    if (!days || days <= 0) { toast.error("Введите количество дней"); return; }
    setExtending(true);
    try {
      await superAdminApi.patch(`/subscriptions/${extendShop.shop_id}`, { add_days: days });
      mutate();
      toast.success(`Подписка продлена на ${days} дн.`);
      setExtendShop(null);
    } catch { toast.error("Ошибка"); }
    finally { setExtending(false); }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Подписки</h1>
        <p className="text-sm text-muted-foreground">Управление подписками всех магазинов</p>
      </div>
      <div className="flex flex-wrap gap-2">
        {[{ key: "all", label: "Все" }, { key: "active", label: "Активные" }, { key: "trial", label: "Триал" }, { key: "expired", label: "Истёкшие" }].map((tab) => (
          <Button key={tab.key} variant={filter === tab.key ? "default" : "outline"} size="sm" onClick={() => setFilter(tab.key)}>{tab.label}</Button>
        ))}
      </div>
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="space-y-2 p-4">{[...Array(4)].map((_, i) => (<Skeleton key={i} className="h-12 w-full" />))}</div>
          ) : subscriptions.length === 0 ? (
            <div className="py-12 text-center text-sm text-muted-foreground">Нет подписок</div>
          ) : (
            <Table>
              <TableHeader><TableRow>
                <TableHead>Магазин</TableHead><TableHead>Тариф</TableHead><TableHead>Статус</TableHead>
                <TableHead>До</TableHead><TableHead>Сумма</TableHead><TableHead className="text-right">Действия</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {subscriptions.map((sub) => (
                  <TableRow key={sub.id}>
                    <TableCell className="font-medium">{sub.shop_name}</TableCell>
                    <TableCell>{sub.is_trial ? (<span className="text-muted-foreground">Триал</span>) : sub.plan_name}</TableCell>
                    <TableCell><Badge variant={sub.status === "active" ? "default" : sub.status === "trial" ? "secondary" : "outline"}>{STATUS_LABELS[sub.status] || sub.status}</Badge></TableCell>
                    <TableCell className="text-muted-foreground">{formatDate(sub.expires_at)}</TableCell>
                    <TableCell>{sub.is_trial ? "—" : formatPrice(sub.plan_price)}</TableCell>
                    <TableCell className="text-right"><Button size="sm" variant="outline" onClick={() => openExtend(sub)}>Продлить</Button></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
      <Dialog open={extendShop !== null} onOpenChange={(open) => { if (!open) setExtendShop(null); }}>
        <DialogContent>
          <DialogHeader><DialogTitle>Продлить подписку — {extendShop?.shop_name}</DialogTitle></DialogHeader>
          <div className="space-y-3 py-2">
            <p className="text-sm text-muted-foreground">Текущая дата окончания: {formatDate(extendShop?.expires_at ?? null)}</p>
            <div className="space-y-2">
              <Label>Добавить дней</Label>
              <Input type="number" value={addDays} onChange={(e) => setAddDays(e.target.value)} placeholder="30" min={1} />
            </div>
            <div className="flex flex-wrap gap-2">
              {[7, 30, 90, 180, 365].map((d) => (<Button key={d} size="sm" variant="outline" onClick={() => setAddDays(String(d))}>+{d}</Button>))}
            </div>
          </div>
          <DialogFooter>
            <DialogClose render={<Button variant="outline" />}>Отмена</DialogClose>
            <Button onClick={handleExtend} disabled={extending}>{extending ? "Продление..." : "Продлить"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
