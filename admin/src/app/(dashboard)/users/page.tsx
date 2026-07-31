"use client";

import useSWR from "swr";
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
import { Skeleton } from "@/components/ui/skeleton";
import { formatPrice, formatDate } from "@/lib/format";
import type { User } from "@/lib/types";

export default function UsersPage() {
  const { data: users, isLoading } = useSWR<User[]>("/users", fetcher);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Пользователи</h1>

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="space-y-2 p-4">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : users?.length === 0 ? (
            <p className="p-8 text-center text-muted-foreground">Нет пользователей</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Имя</TableHead>
                  <TableHead>Телефон</TableHead>
                  <TableHead className="text-center">Заказов</TableHead>
                  <TableHead className="text-right">Потрачено</TableHead>
                  <TableHead>Последний заказ</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users?.map((user) => (
                  <TableRow key={user.telegram_user_id}>
                    <TableCell className="font-medium">{user.full_name}</TableCell>
                    <TableCell className="text-muted-foreground">{user.phone}</TableCell>
                    <TableCell className="text-center">{user.orders_count}</TableCell>
                    <TableCell className="text-right font-semibold">
                      {formatPrice(user.total_spent)}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {formatDate(user.last_order)}
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
