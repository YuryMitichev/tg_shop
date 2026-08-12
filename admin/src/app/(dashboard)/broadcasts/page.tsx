"use client";

import useSWR from "swr";
import { useState, useMemo } from "react";
import { fetcher } from "@/lib/swr";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
import { Megaphone, Send, Users, Clock } from "lucide-react";
import { formatPrice, formatDate } from "@/lib/format";
import type {
  Product,
  BroadcastsResponse,
  PreviewRecipientsResponse,
} from "@/lib/types";

const BROADCAST_STATUS: Record<string, { label: string; color: string }> = {
  draft: { label: "Черновик", color: "bg-gray-100 text-gray-800" },
  sending: { label: "Отправка...", color: "bg-blue-100 text-blue-800" },
  sent: { label: "Отправлено", color: "bg-green-100 text-green-800" },
};

export default function BroadcastsPage() {
  const [productId, setProductId] = useState<string>("");
  const [variantId, setVariantId] = useState<string>("");
  const [discount, setDiscount] = useState<string>("10");
  const [messageText, setMessageText] = useState<string>("");
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [expiresAt, setExpiresAt] = useState<string>("");
  const [previewCount, setPreviewCount] = useState<number | null>(null);
  const [sending, setSending] = useState(false);

  const { data: productsData } = useSWR<{ products: Product[] }>(
    "/products?per_page=100",
    fetcher,
  );
  const products = productsData?.products;
  const { data: tags } = useSWR<string[]>("/crm/tags", fetcher);
  const { data: broadcastsData, isLoading, mutate } =
    useSWR<BroadcastsResponse>("/broadcasts", fetcher);

  const selectedProduct = useMemo(
    () => products?.find((p) => String(p.id) === productId),
    [products, productId],
  );

  const selectedVariant = useMemo(() => {
    if (!selectedProduct) return null;
    if (!variantId) return selectedProduct.variants[0] || null;
    return (
      selectedProduct.variants.find((v) => String(v.id) === variantId) || null
    );
  }, [selectedProduct, variantId]);

  const originalPrice = selectedVariant?.price || 0;
  const discountNum = Math.min(90, Math.max(0, parseInt(discount) || 0));
  const discountedPrice = Math.round(
    (originalPrice * (100 - discountNum)) / 100,
  );

  async function handlePreview() {
    try {
      const res = await api.post<PreviewRecipientsResponse>(
        "/broadcasts/preview",
        { tags: selectedTags.length ? selectedTags : null },
      );
      setPreviewCount(res.recipients_count);
    } catch {
      toast.error("Ошибка при подсчёте получателей");
    }
  }

  function toggleTag(tag: string) {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag],
    );
    setPreviewCount(null);
  }

  async function handleCreateAndSend() {
    if (!productId) {
      toast.error("Выберите товар");
      return;
    }
    setSending(true);
    try {
      const res = await api.post<{ ok: boolean; broadcast_id?: number; error?: string }>(
        "/broadcasts",
        {
          product_id: parseInt(productId),
          discount_percent: discountNum,
          variant_id: variantId ? parseInt(variantId) : null,
          filter_tags: selectedTags.length ? selectedTags : null,
          message_text: messageText.trim() || null,
          expires_at: expiresAt
            ? new Date(expiresAt).toISOString()
            : null,
        },
      );

      if (!res.ok || !res.broadcast_id) {
        toast.error(res.error || "Ошибка создания рассылки");
        return;
      }

      toast.info("Рассылка отправляется...");

      const sendRes = await api.post<{
        ok: boolean;
        sent?: number;
        failed?: number;
        error?: string;
      }>(`/broadcasts/${res.broadcast_id}/send`);

      if (sendRes.ok) {
        toast.success(
          `Отправлено: ${sendRes.sent}, ошибок: ${sendRes.failed}`,
        );
      } else {
        toast.error(sendRes.error || "Ошибка отправки");
      }

      setProductId("");
      setVariantId("");
      setDiscount("10");
      setMessageText("");
      setSelectedTags([]);
      setExpiresAt("");
      setPreviewCount(null);
      mutate();
    } catch (e) {
      toast.error("Ошибка при отправке");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Megaphone className="h-6 w-6" />
        <h1 className="text-2xl font-bold">Рассылки</h1>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>Новая рассылка</CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="space-y-2">
                <Label>Товар</Label>
                <Select
                  value={productId}
                  onValueChange={(v) => {
                    setProductId(v || "");
                    setVariantId("");
                    setPreviewCount(null);
                  }}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Выберите товар..." />
                  </SelectTrigger>
                  <SelectContent>
                    {products?.map((p) => (
                      <SelectItem key={p.id} value={String(p.id)}>
                        {p.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {selectedProduct && selectedProduct.variants.length > 1 && (
                <div className="space-y-2">
                  <Label>Объём</Label>
                  <Select
                    value={variantId}
                    onValueChange={(v) => {
                      setVariantId(v || "");
                      setPreviewCount(null);
                    }}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Выберите объём..." />
                    </SelectTrigger>
                    <SelectContent>
                      {selectedProduct.variants.map((v) => (
                        <SelectItem key={v.id} value={String(v.id)}>
                          {v.volume} — {v.price}₽
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}

              <div className="space-y-2">
                <Label>Скидка: {discountNum}%</Label>
                <Input
                  type="range"
                  min={0}
                  max={90}
                  step={5}
                  value={discountNum}
                  onChange={(e) => setDiscount(e.target.value)}
                />
                {originalPrice > 0 && discountNum > 0 && (
                  <div className="flex items-center gap-3 text-sm">
                    <span className="text-muted-foreground line-through">
                      {formatPrice(originalPrice)}
                    </span>
                    <span className="text-lg font-bold text-green-600">
                      {formatPrice(discountedPrice)}
                    </span>
                    <Badge variant="secondary">-{discountNum}%</Badge>
                  </div>
                )}
              </div>

              <div className="space-y-2">
                <Label>Дополнительное сообщение (необязательно)</Label>
                <Textarea
                  placeholder="Например: Только сегодня! Успейте заказать..."
                  value={messageText}
                  onChange={(e) => setMessageText(e.target.value)}
                  rows={2}
                />
              </div>

              <div className="space-y-2">
                <Label>Срок действия предложения</Label>
                <div className="flex items-center gap-2">
                  <Input
                    type="datetime-local"
                    value={expiresAt}
                    onChange={(e) => setExpiresAt(e.target.value)}
                    className="max-w-xs"
                  />
                  {expiresAt && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setExpiresAt("")}
                    >
                      Сбросить
                    </Button>
                  )}
                </div>
                <p className="text-xs text-muted-foreground">
                  Скидка автоматически деактивируется после этой даты. Необязательно.
                </p>
              </div>

              <div className="space-y-2">
                <Label>Кому отправить (по тегам)</Label>
                <p className="text-xs text-muted-foreground">
                  Выберите теги получателей. Пусто = всем пользователям.
                </p>
                <div className="flex flex-wrap gap-2">
                  {tags?.map((tag) => {
                    const active = selectedTags.includes(tag);
                    return (
                      <button
                        key={tag}
                        type="button"
                        onClick={() => toggleTag(tag)}
                        className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                          active
                            ? "border-primary bg-primary text-primary-foreground"
                            : "border-border bg-background hover:bg-accent"
                        }`}
                      >
                        {tag}
                      </button>
                    );
                  })}
                  {(!tags || tags.length === 0) && (
                    <p className="text-xs text-muted-foreground">
                      Тегов пока нет. Запустите бота для автотегирования.
                    </p>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-3 border-t pt-4">
                <Button variant="outline" size="sm" onClick={handlePreview}>
                  <Users className="mr-2 h-4 w-4" />
                  Подсчитать получателей
                </Button>
                {previewCount !== null && (
                  <span className="text-sm font-medium">
                    Получателей: <b>{previewCount}</b>
                  </span>
                )}
              </div>

              <AlertDialog>
                <AlertDialogTrigger
                  render={
                    <Button
                      className="w-full"
                      size="lg"
                      disabled={!productId || sending}
                    />
                  }
                >
                  <Send className="mr-2 h-4 w-4" />
                  {sending ? "Отправка..." : "Отправить рассылку"}
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Отправить рассылку?</AlertDialogTitle>
                    <AlertDialogDescription>
                      Сообщение получат{" "}
                      {previewCount !== null
                        ? previewCount
                        : "все подходящие"}{" "}
                      пользователей. Это действие нельзя отменить.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Отмена</AlertDialogCancel>
                    <AlertDialogAction onClick={handleCreateAndSend}>
                      Отправить
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </CardContent>
          </Card>
        </div>

        <div>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Предпросмотр сообщения</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="rounded-lg bg-muted p-4 text-sm">
                <p className="font-bold">🔥 Специальное предложение!</p>
                <div className="mt-3">
                  <p className="font-semibold">
                    📦 {selectedProduct?.name || "Выберите товар"}
                    {selectedVariant && ` (${selectedVariant.volume})`}
                  </p>
                </div>
                {originalPrice > 0 && discountNum > 0 && (
                  <div className="mt-2">
                    <p className="text-xs">🎁 Скидка {discountNum}%!</p>
                    <p>
                      <span className="text-muted-foreground line-through">
                        {formatPrice(originalPrice)}
                      </span>{" "}
                      → <b>{formatPrice(discountedPrice)}</b>
                    </p>
                  </div>
                )}
                {messageText.trim() && (
                  <p className="mt-2 text-muted-foreground">
                    💬 {messageText.trim()}
                  </p>
                )}
                {expiresAt && (
                  <p className="mt-2 font-medium text-orange-600">
                    ⏰ До {new Date(expiresAt).toLocaleString("ru-RU")}
                  </p>
                )}
                <p className="mt-3 text-xs text-muted-foreground">
                  🛒 Откройте каталог, чтобы заказать!
                </p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      <div>
        <h2 className="mb-3 text-lg font-semibold">История рассылок</h2>
        <Card>
          <CardContent className="p-0">
            {isLoading ? (
              <div className="space-y-2 p-4">
                {[...Array(3)].map((_, i) => (
                  <Skeleton key={i} className="h-12 w-full" />
                ))}
              </div>
            ) : !broadcastsData?.broadcasts?.length ? (
              <p className="p-8 text-center text-muted-foreground">
                Рассылок пока нет
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Дата</TableHead>
                    <TableHead>Товар</TableHead>
                    <TableHead className="text-center">Скидка</TableHead>
                    <TableHead>Срок</TableHead>
                    <TableHead>Теги</TableHead>
                    <TableHead className="text-center">Статус</TableHead>
                    <TableHead className="text-center">Отправлено</TableHead>
                    <TableHead className="text-center">Ошибок</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {broadcastsData.broadcasts.map((b) => (
                    <TableRow key={b.id}>
                      <TableCell className="text-sm text-muted-foreground">
                        {formatDate(b.created_at)}
                      </TableCell>
                      <TableCell className="font-medium">
                        {b.product_name}
                        {b.variant_volume && ` (${b.variant_volume})`}
                      </TableCell>
                      <TableCell className="text-center">
                        {b.discount_percent > 0 ? (
                          <Badge variant="secondary">-{b.discount_percent}%</Badge>
                        ) : (
                          "—"
                        )}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {b.expires_at ? formatDate(b.expires_at) : "∞"}
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-1">
                          {b.filter_tags?.map((tag) => (
                            <Badge
                              key={tag}
                              variant="outline"
                              className="text-xs"
                            >
                              {tag}
                            </Badge>
                          )) || "Все"}
                        </div>
                      </TableCell>
                      <TableCell className="text-center">
                        <span
                          className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                            BROADCAST_STATUS[b.status]?.color ||
                            "bg-gray-100 text-gray-800"
                          }`}
                        >
                          {BROADCAST_STATUS[b.status]?.label || b.status}
                        </span>
                      </TableCell>
                      <TableCell className="text-center font-medium">
                        {b.sent_count}
                      </TableCell>
                      <TableCell className="text-center text-red-500">
                        {b.failed_count || "—"}
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
  );
}
