"use client";

import useSWR from "swr";
import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { fetcher } from "@/lib/swr";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
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
import { formatPrice, formatDate, STATUS_LABELS } from "@/lib/format";
import type { CrmUserDetail, CrmMessagesResponse } from "@/lib/types";
import {
  ArrowLeft,
  Send,
  Tag as TagIcon,
  X,
  MessageSquare,
  Package,
  Star,
} from "lucide-react";

export default function UserDetailPage() {
  const params = useParams();
  const router = useRouter();
  const telegramUserId = Number(params.id);

  const { data: user, isLoading, mutate } = useSWR<CrmUserDetail>(
    `/crm/users/${telegramUserId}`,
    fetcher,
  );
  const { data: msgData, mutate: mutateMsgs } = useSWR<CrmMessagesResponse>(
    `/crm/users/${telegramUserId}/messages?per_page=100`,
    fetcher,
  );

  const [notes, setNotes] = useState("");
  const [notesDirty, setNotesDirty] = useState(false);
  const [newTag, setNewTag] = useState("");
  const [phone, setPhone] = useState("");
  const [phoneDirty, setPhoneDirty] = useState(false);
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <div className="grid gap-6 lg:grid-cols-3">
          <Skeleton className="h-96" />
          <Skeleton className="h-96 lg:col-span-2" />
        </div>
      </div>
    );
  }

  if (!user) {
    return <div className="py-12 text-center text-muted-foreground">Пользователь не найден</div>;
  }

  async function saveNotes() {
    try {
      await api.put(`/crm/users/${telegramUserId}/notes`, { notes });
      mutate();
      setNotesDirty(false);
      toast.success("Заметки сохранены");
    } catch {
      toast.error("Ошибка");
    }
  }

  async function savePhone() {
    try {
      await api.put(`/crm/users/${telegramUserId}/phone`, { phone: phone || null });
      mutate();
      setPhoneDirty(false);
      toast.success("Телефон сохранён");
    } catch {
      toast.error("Ошибка");
    }
  }

  async function addTag() {
    const tag = newTag.trim();
    if (!tag) return;
    try {
      await api.post(`/crm/users/${telegramUserId}/tags`, { tag });
      mutate();
      setNewTag("");
      toast.success("Тег добавлен");
    } catch {
      toast.error("Ошибка");
    }
  }

  async function removeTag(tag: string) {
    try {
      await api.delete(`/crm/users/${telegramUserId}/tags/${encodeURIComponent(tag)}`);
      mutate();
      toast.success("Тег удалён");
    } catch {
      toast.error("Ошибка");
    }
  }

  async function sendMessage() {
    const text = message.trim();
    if (!text) return;
    setSending(true);
    try {
      const res = await api.post<{ ok: boolean; error?: string }>(
        `/crm/users/${telegramUserId}/send`,
        { text },
      );
      if (!res.ok) {
        toast.error(res.error || "Ошибка отправки");
        return;
      }
      setMessage("");
      mutateMsgs();
      toast.success("Сообщение отправлено");
    } catch {
      toast.error("Ошибка");
    } finally {
      setSending(false);
    }
  }

  const messages = msgData?.messages || [];

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="sm" onClick={() => router.push("/users")}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Назад
        </Button>
        <h1 className="text-2xl font-bold">
          {user.full_name || "Без имени"}
        </h1>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Левая колонка — профиль */}
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Профиль</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div>
                <span className="text-muted-foreground">Telegram ID:</span>
                <span className="ml-2 font-mono">{user.telegram_user_id}</span>
              </div>
              {user.username && (
                <div>
                  <span className="text-muted-foreground">Username:</span>
                  <span className="ml-2">@{user.username}</span>
                </div>
              )}
              <div>
                <span className="text-muted-foreground">Телефон:</span>
              </div>
              <div className="flex gap-2">
                <Input
                  value={phoneDirty ? phone : (user.phone || "")}
                  onChange={(e) => {
                    setPhone(e.target.value);
                    setPhoneDirty(true);
                  }}
                  placeholder="Не указан"
                  className="h-8 text-sm"
                />
                {phoneDirty && (
                  <Button size="sm" onClick={savePhone}>
                    OK
                  </Button>
                )}
              </div>
              <div>
                <span className="text-muted-foreground">Регистрация:</span>
                <span className="ml-2">{formatDate(user.created_at)}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Последний визит:</span>
                <span className="ml-2">{formatDate(user.last_seen)}</span>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Package className="h-4 w-4" /> Статистика
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Заказов</span>
                <span className="font-medium">{user.orders_count}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Потрачено всего</span>
                <span className="font-medium">{formatPrice(user.total_spent)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Средний чек</span>
                <span className="font-medium">{formatPrice(user.avg_order_value)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Последний заказ</span>
                <span className="font-medium">{formatDate(user.last_order)}</span>
              </div>
            </CardContent>
          </Card>

          {user.favorite_products.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Star className="h-4 w-4" /> Любимые товары
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                {user.favorite_products.map((p, i) => (
                  <div key={i} className="flex justify-between">
                    <span>{p.name}</span>
                    <span className="text-muted-foreground">{p.quantity} шт.</span>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <TagIcon className="h-4 w-4" /> Теги
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex flex-wrap gap-2">
                {user.tags.length === 0 && (
                  <span className="text-sm text-muted-foreground">Нет тегов</span>
                )}
                {user.tags.map((tag) => (
                  <Badge key={tag} variant="secondary" className="gap-1">
                    {tag}
                    <button onClick={() => removeTag(tag)}>
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                ))}
              </div>
              <div className="flex gap-2">
                <Input
                  value={newTag}
                  onChange={(e) => setNewTag(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && addTag()}
                  placeholder="VIP, опт, проблема..."
                  className="h-8 text-sm"
                />
                <Button size="sm" onClick={addTag}>
                  <TagIcon className="h-3 w-3" />
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Заметки</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <Textarea
                value={notesDirty ? notes : (user.notes || "")}
                onChange={(e) => {
                  setNotes(e.target.value);
                  setNotesDirty(true);
                }}
                placeholder="Внутренние заметки о клиенте..."
                rows={4}
              />
              {notesDirty && (
                <Button size="sm" onClick={saveNotes}>
                  Сохранить
                </Button>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Правая колонка — заказы и коммуникация */}
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <MessageSquare className="h-4 w-4" /> Общение
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex gap-2">
                <Input
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && sendMessage()}
                  placeholder="Написать клиенту..."
                />
                <Button onClick={sendMessage} disabled={sending || !message.trim()}>
                  <Send className="h-4 w-4" />
                </Button>
              </div>

              <div className="max-h-[400px] space-y-2 overflow-y-auto rounded-lg border p-3">
                {messages.length === 0 ? (
                  <p className="py-8 text-center text-sm text-muted-foreground">
                    История пуста
                  </p>
                ) : (
                  messages.slice().reverse().map((msg) => (
                    <div
                      key={msg.id}
                      className={`flex ${msg.direction === "out" ? "justify-end" : "justify-start"}`}
                    >
                      <div
                        className={`max-w-[75%] rounded-lg px-3 py-2 text-sm ${
                          msg.direction === "out"
                            ? "bg-primary text-primary-foreground"
                            : "bg-muted"
                        }`}
                      >
                        <div>{msg.text || `[${msg.message_type}]`}</div>
                        <div
                          className={`mt-1 text-xs ${
                            msg.direction === "out" ? "text-primary-foreground/70" : "text-muted-foreground"
                          }`}
                        >
                          {formatDate(msg.created_at)}
                          {msg.admin_id && msg.direction === "out" && ` · admin #${msg.admin_id}`}
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Заказы клиента</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {user.orders.length === 0 ? (
                <p className="p-8 text-center text-sm text-muted-foreground">Нет заказов</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>№</TableHead>
                      <TableHead>Статус</TableHead>
                      <TableHead className="text-right">Сумма</TableHead>
                      <TableHead>Дата</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {user.orders.map((order) => (
                      <TableRow key={order.id}>
                        <TableCell className="font-mono">#{order.id}</TableCell>
                        <TableCell>
                          <Badge variant="outline">
                            {STATUS_LABELS[order.status] || order.status}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right font-medium">
                          {formatPrice(order.total_amount)}
                        </TableCell>
                        <TableCell className="text-muted-foreground text-sm">
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
      </div>
    </div>
  );
}
