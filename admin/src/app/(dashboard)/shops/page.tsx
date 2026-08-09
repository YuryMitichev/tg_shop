"use client";

import useSWR from "swr";
import { superAdminFetcher } from "@/lib/swr";
import { superAdminApi, api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
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
import { Store, Trash2 } from "lucide-react";
import { formatDate } from "@/lib/format";
import type { ShopManagement } from "@/lib/types";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

export default function ShopsPage() {
  const router = useRouter();
  const [allowed, setAllowed] = useState(false);

  useEffect(() => {
    api
      .get<{ is_super_admin: boolean }>("/auth/me")
      .then((res) => {
        if (!res.is_super_admin) {
          router.replace("/dashboard");
        } else {
          setAllowed(true);
        }
      })
      .catch(() => router.replace("/login"));
  }, [router]);

  const { data, isLoading, mutate } = useSWR<{ shops: ShopManagement[] }>(
    allowed ? "/shops" : null,
    superAdminFetcher,
  );

  const shops = data?.shops ?? [];

  if (!allowed) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <p className="text-muted-foreground">Загрузка...</p>
      </div>
    );
  }

  async function remove(shop: ShopManagement) {
    try {
      await superAdminApi.delete(`/shops/${shop.id}`);
      mutate();
      toast.success(`Магазин «${shop.name}» удалён`);
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Ошибка при удалении магазина",
      );
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Магазины</h1>
        <p className="text-sm text-muted-foreground">
          Управление всеми магазинами платформы
        </p>
      </div>

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="space-y-2 p-4">
              {[...Array(3)].map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : shops.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
              <Store className="mb-2 h-8 w-8 opacity-50" />
              <p>Нет магазинов</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead>
                  <TableHead>Название</TableHead>
                  <TableHead>Bot Token</TableHead>
                  <TableHead>Владелец</TableHead>
                  <TableHead>Статус</TableHead>
                  <TableHead>Создан</TableHead>
                  <TableHead className="text-right">Действия</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {shops.map((shop) => (
                  <TableRow key={shop.id}>
                    <TableCell className="font-mono text-muted-foreground">
                      {shop.id}
                    </TableCell>
                    <TableCell className="font-medium">{shop.name}</TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {shop.bot_token_masked}
                    </TableCell>
                    <TableCell className="font-mono text-muted-foreground">
                      {shop.owner_telegram_id}
                    </TableCell>
                    <TableCell>
                      {shop.is_active ? (
                        <Badge variant="default">Активен</Badge>
                      ) : (
                        <Badge variant="secondary">Отключён</Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {formatDate(shop.created_at)}
                    </TableCell>
                    <TableCell className="text-right">
                      {shop.id === 1 ? (
                        <span className="text-xs text-muted-foreground">
                          По умолчанию
                        </span>
                      ) : (
                        <AlertDialog>
                          <AlertDialogTrigger
                            render={
                              <Button size="sm" variant="outline" />
                            }
                          >
                            <Trash2 className="h-3 w-3 text-red-500" />
                          </AlertDialogTrigger>
                          <AlertDialogContent>
                            <AlertDialogHeader>
                              <AlertDialogTitle>
                                Удалить магазин «{shop.name}»?
                              </AlertDialogTitle>
                              <AlertDialogDescription>
                                Будут безвозвратно удалены все товары, заказы,
                                пользователи, отзывы, рассылки, промокоды и
                                другие данные этого магазина. Бот будет
                                остановлен. Это действие нельзя отменить.
                              </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                              <AlertDialogCancel>Отмена</AlertDialogCancel>
                              <AlertDialogAction
                                onClick={() => remove(shop)}
                              >
                                Удалить безвозвратно
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
