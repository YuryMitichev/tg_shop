"use client";

import useSWR from "swr";
import { superAdminFetcher } from "@/lib/swr";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { FileText } from "lucide-react";
import { formatDate } from "@/lib/format";

interface Acceptance {
  id: number;
  telegram_user_id: number;
  full_name: string | null;
  username: string | null;
  offer_version: string;
  accepted_at: string | null;
}

export default function OfferPage() {
  const { data, isLoading } = useSWR<{ acceptances: Acceptance[] }>(
    "/offer/acceptances",
    superAdminFetcher,
  );

  const acceptances = data?.acceptances ?? [];

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex items-center gap-3">
        <FileText className="h-6 w-6 text-muted-foreground" />
        <h1 className="text-2xl font-bold">Публичная оферта</h1>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Принявшие оферту</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Skeleton className="h-48 w-full" />
          ) : acceptances.length === 0 ? (
            <p className="text-sm text-muted-foreground">Пока никто не принял оферту.</p>
          ) : (
            <>
              <p className="mb-4 text-sm text-muted-foreground">
                Всего подписей: <span className="font-semibold">{acceptances.length}</span>
              </p>
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Имя</TableHead>
                      <TableHead>Telegram ID</TableHead>
                      <TableHead>Username</TableHead>
                      <TableHead>Версия</TableHead>
                      <TableHead>Дата</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {acceptances.map((a) => (
                      <TableRow key={a.id}>
                        <TableCell className="font-medium">{a.full_name || "—"}</TableCell>
                        <TableCell className="text-muted-foreground">{a.telegram_user_id}</TableCell>
                        <TableCell className="text-muted-foreground">
                          {a.username ? `@${a.username}` : "—"}
                        </TableCell>
                        <TableCell>
                          <Badge variant="secondary">{a.offer_version}</Badge>
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {a.accepted_at ? formatDate(a.accepted_at) : "—"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
