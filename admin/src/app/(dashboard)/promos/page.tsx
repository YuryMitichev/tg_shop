"use client";

import useSWR from "swr";
import { useState } from "react";
import { fetcher } from "@/lib/swr";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Plus, Ticket, Trash2 } from "lucide-react";
import type { Promo } from "@/lib/types";

export default function PromosPage() {
  const { data: promos, isLoading, mutate } = useSWR<Promo[]>("/promos", fetcher);

  const [open, setOpen] = useState(false);
  const [code, setCode] = useState("");
  const [type, setType] = useState("percent");
  const [value, setValue] = useState("");
  const [maxUses, setMaxUses] = useState("");
  const [loading, setLoading] = useState(false);

  async function createPromo() {
    if (!code.trim() || !value) {
      toast.error("Заполните все поля");
      return;
    }

    setLoading(true);
    try {
      await api.post("/promos", {
        code: code.toUpperCase(),
        discount_type: type,
        discount_value: Number(value),
        max_uses: maxUses ? Number(maxUses) : null,
      });
      mutate();
      toast.success("Промокод создан");
      setOpen(false);
      setCode("");
      setValue("");
      setMaxUses("");
    } catch {
      toast.error("Ошибка");
    } finally {
      setLoading(false);
    }
  }

  async function toggle(id: number) {
    try {
      await api.patch(`/promos/${id}/toggle`);
      mutate();
      toast.success("Статус изменён");
    } catch {
      toast.error("Ошибка");
    }
  }

  async function remove(id: number) {
    try {
      await api.delete(`/promos/${id}`);
      mutate();
      toast.success("Промокод удалён");
    } catch {
      toast.error("Ошибка");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Промокоды</h1>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger render={<Button />}>
            <Plus className="mr-2 h-4 w-4" />
            Создать
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Новый промокод</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 py-2">
              <div className="space-y-2">
                <Label>Код</Label>
                <Input
                  value={code}
                  onChange={(e) => setCode(e.target.value.toUpperCase())}
                  placeholder="NEW10"
                />
              </div>
              <div className="space-y-2">
                <Label>Тип скидки</Label>
                <Select value={type} onValueChange={(v) => setType(v || "percent")}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="percent">Процент (%)</SelectItem>
                    <SelectItem value="fixed">Фиксированная сумма (₽)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Размер скидки ({type === "percent" ? "%" : "₽"})</Label>
                <Input
                  type="number"
                  value={value}
                  onChange={(e) => setValue(e.target.value)}
                  placeholder={type === "percent" ? "10" : "500"}
                />
              </div>
              <div className="space-y-2">
                <Label>Макс. использований (пусто = ∞)</Label>
                <Input
                  type="number"
                  value={maxUses}
                  onChange={(e) => setMaxUses(e.target.value)}
                  placeholder="100"
                />
              </div>
            </div>
            <DialogFooter>
              <DialogClose render={<Button variant="outline" />}>Отмена</DialogClose>
              <Button onClick={createPromo} disabled={loading}>
                Создать
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="space-y-2 p-4">
              {[...Array(4)].map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : promos?.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
              <Ticket className="mb-2 h-8 w-8 opacity-50" />
              <p>Нет промокодов</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Код</TableHead>
                  <TableHead>Скидка</TableHead>
                  <TableHead className="text-center">Использовано</TableHead>
                  <TableHead>Статус</TableHead>
                  <TableHead className="text-right">Действия</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {promos?.map((promo) => (
                  <TableRow key={promo.id}>
                    <TableCell>
                      <span className="font-mono font-bold">{promo.code}</span>
                    </TableCell>
                    <TableCell>
                      {promo.discount_type === "percent"
                        ? `−${promo.discount_value}%`
                        : `−${promo.discount_value}₽`}
                    </TableCell>
                    <TableCell className="text-center">
                      {promo.used_count}
                      {promo.max_uses ? `/${promo.max_uses}` : "/∞"}
                    </TableCell>
                    <TableCell>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => toggle(promo.id)}
                      >
                        <Badge variant={promo.is_active ? "default" : "secondary"}>
                          {promo.is_active ? "✅ Активен" : "🚫 Выключен"}
                        </Badge>
                      </Button>
                    </TableCell>
                    <TableCell className="text-right">
                      <AlertDialog>
                        <AlertDialogTrigger render={<Button size="sm" variant="outline" />}>
                          <Trash2 className="h-3 w-3 text-red-500" />
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader>
                            <AlertDialogTitle>Удалить промокод?</AlertDialogTitle>
                            <AlertDialogDescription>
                              Промокод «{promo.code}» будет удалён безвозвратно.
                            </AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>Отмена</AlertDialogCancel>
                            <AlertDialogAction onClick={() => remove(promo.id)}>
                              Удалить
                            </AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
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
