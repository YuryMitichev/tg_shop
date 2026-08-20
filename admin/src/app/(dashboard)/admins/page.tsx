"use client";

import useSWR from "swr";
import { useState } from "react";
import { fetcher } from "@/lib/swr";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
import { Plus, Shield, Trash2 } from "lucide-react";
import { formatDate } from "@/lib/format";
import type { Admin } from "@/lib/types";

export default function AdminsPage() {
  const { data: admins, isLoading, mutate } = useSWR<Admin[]>("/admins", fetcher);

  const [open, setOpen] = useState(false);
  const [telegramId, setTelegramId] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [role, setRole] = useState<"manager" | "content" | "support">("manager");
  const [loading, setLoading] = useState(false);

  async function addAdmin() {
    if (!telegramId.trim()) {
      toast.error("Введите Telegram ID");
      return;
    }

    setLoading(true);
    try {
      await api.post("/admins", {
        telegram_user_id: Number(telegramId),
        display_name: displayName.trim() || null,
        role,
      });
      mutate();
      toast.success("Администратор добавлен");
      setOpen(false);
      setTelegramId("");
      setDisplayName("");
      setRole("manager");
    } catch {
      toast.error("Ошибка");
    } finally {
      setLoading(false);
    }
  }

  async function remove(id: number) {
    try {
      const res = await api.delete<{ ok: boolean; error?: string }>(`/admins/${id}`);
      if (!res.ok) {
        toast.error(res.error || "Ошибка");
        return;
      }
      mutate();
      toast.success("Администратор удалён");
    } catch {
      toast.error("Ошибка");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Администраторы</h1>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger render={<Button />}>
            <Plus className="mr-2 h-4 w-4" />
            Добавить
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Новый администратор</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 py-2">
              <div className="space-y-2">
                <Label>Telegram ID</Label>
                <Input
                  type="number"
                  value={telegramId}
                  onChange={(e) => setTelegramId(e.target.value)}
                  placeholder="123456789"
                />
                <p className="text-xs text-muted-foreground">
                  Узнать ID: @userinfobot в Telegram
                </p>
              </div>
              <div className="space-y-2">
                <Label>Имя (необязательно)</Label>
                <Input
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="Иван"
                />
              </div>
              <div className="space-y-2">
                <Label>Роль</Label>
                <Select value={role} onValueChange={(value) => setRole(value as typeof role)}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="manager">Менеджер</SelectItem>
                    <SelectItem value="content">Контент</SelectItem>
                    <SelectItem value="support">Поддержка</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <DialogFooter>
              <DialogClose render={<Button variant="outline" />}>Отмена</DialogClose>
              <Button onClick={addAdmin} disabled={loading}>
                Добавить
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="space-y-2 p-4">
              {[...Array(3)].map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : admins?.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
              <Shield className="mb-2 h-8 w-8 opacity-50" />
              <p>Нет администраторов</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Telegram ID</TableHead>
                  <TableHead>Имя</TableHead>
                  <TableHead>Добавлен</TableHead>
                  <TableHead>Тип</TableHead>
                  <TableHead className="text-right">Действия</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {admins?.map((admin) => (
                  <TableRow key={admin.id}>
                    <TableCell className="font-mono">{admin.telegram_user_id}</TableCell>
                    <TableCell>{admin.display_name || "—"}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {formatDate(admin.created_at)}
                    </TableCell>
                    <TableCell>
                      {admin.is_super ? (
                        <Badge variant="default">Супер (env)</Badge>
                      ) : (
                        <Badge variant="secondary">
                          {{ manager: "Менеджер", content: "Контент", support: "Поддержка", owner: "Владелец" }[admin.role] || admin.role}
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      {!admin.is_super && (
                        <AlertDialog>
                          <AlertDialogTrigger render={<Button size="sm" variant="outline" />}>
                            <Trash2 className="h-3 w-3 text-red-500" />
                          </AlertDialogTrigger>
                          <AlertDialogContent>
                            <AlertDialogHeader>
                              <AlertDialogTitle>Удалить администратора?</AlertDialogTitle>
                              <AlertDialogDescription>
                                {admin.display_name || "Администратор"} ({admin.telegram_user_id}) потеряет доступ к панели.
                              </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                              <AlertDialogCancel>Отмена</AlertDialogCancel>
                              <AlertDialogAction onClick={() => remove(admin.id)}>
                                Удалить
                              </AlertDialogAction>
                            </AlertDialogFooter>
                          </AlertDialogContent>
                        </AlertDialog>
                      )}
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
