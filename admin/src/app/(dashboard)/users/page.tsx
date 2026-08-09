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
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Search, Eye } from "lucide-react";
import { formatPrice, formatDate } from "@/lib/format";
import type { CrmUsersResponse } from "@/lib/types";

export default function UsersPage() {
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");

  const { data, isLoading } = useSWR<CrmUsersResponse>(
    `/crm/users?search=${encodeURIComponent(debouncedSearch)}&per_page=50`,
    fetcher,
  );

  const users = data?.users || [];

  function onSearch(e: React.ChangeEvent<HTMLInputElement>) {
    setSearch(e.target.value);
    const v = e.target.value;
    setTimeout(() => setDebouncedSearch(v), 400);
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-bold">Клиенты</h1>
        <div className="text-sm text-muted-foreground">
          Всего: {data?.total || 0}
        </div>
      </div>

      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Поиск по имени, телефону, @username..."
          value={search}
          onChange={onSearch}
          className="pl-9"
        />
      </div>

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="space-y-2 p-4">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : users.length === 0 ? (
            <p className="p-8 text-center text-muted-foreground">Нет клиентов</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Клиент</TableHead>
                  <TableHead>Телефон</TableHead>
                  <TableHead className="text-center">Заказов</TableHead>
                  <TableHead className="text-right">Потрачено</TableHead>
                  <TableHead>Теги</TableHead>
                  <TableHead>Последний визит</TableHead>
                  <TableHead className="text-right">Действия</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map((user) => (
                  <TableRow key={user.telegram_user_id}>
                    <TableCell>
                      <div className="font-medium">{user.full_name || "Без имени"}</div>
                      {user.username && (
                        <div className="text-xs text-muted-foreground">@{user.username}</div>
                      )}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {user.phone || "—"}
                    </TableCell>
                    <TableCell className="text-center">{user.orders_count}</TableCell>
                    <TableCell className="text-right font-semibold">
                      {formatPrice(user.total_spent)}
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {user.tags?.map((tag) => (
                          <Badge key={tag} variant="secondary" className="text-xs">
                            {tag}
                          </Badge>
                        ))}
                      </div>
                    </TableCell>
                    <TableCell className="text-muted-foreground text-sm">
                      {formatDate(user.last_seen)}
                    </TableCell>
                    <TableCell className="text-right">
                      <Link href={`/users/${user.telegram_user_id}`}>
                        <Button size="sm" variant="ghost">
                          <Eye className="h-4 w-4" />
                        </Button>
                      </Link>
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
