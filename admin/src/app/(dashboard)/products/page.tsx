"use client";

import useSWR from "swr";
import { useMemo, useState } from "react";
import Link from "next/link";
import { fetcher } from "@/lib/swr";
import { api, photoUrl } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Plus, Pencil, Trash2, Eye, EyeOff, Upload, PackageCheck, ChevronLeft, ChevronRight } from "lucide-react";
import { ImportDialog } from "@/components/import-dialog";
import { StockUpdateDialog } from "@/components/stock-update-dialog";
import type { Category, ProductsResponse } from "@/lib/types";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const PER_PAGE = 18;

export default function ProductsPage() {
  const [filter, setFilter] = useState<string>("all");
  const [page, setPage] = useState(1);
  const [importOpen, setImportOpen] = useState(false);
  const [stockOpen, setStockOpen] = useState(false);

  const productsKey = filter === "all"
    ? `/products?page=${page}&per_page=${PER_PAGE}`
    : `/products?category_id=${filter}&page=${page}&per_page=${PER_PAGE}`;

  const { data, isLoading, mutate } = useSWR<ProductsResponse>(productsKey, fetcher);
  const products = data?.products;

  const { data: categories } = useSWR<Category[]>("/categories", fetcher);

  const categoryFilterItems = useMemo(() => {
    const map: Record<string, string> = { all: "Все категории" };
    for (const c of categories ?? []) {
      map[String(c.id)] = `${c.emoji} ${c.name}`;
    }
    return map;
  }, [categories]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.per_page)) : 1;

  async function toggleActive(id: number) {
    try {
      await api.patch(`/products/${id}/toggle`);
      mutate();
      toast.success("Статус изменён");
    } catch {
      toast.error("Ошибка");
    }
  }

  async function deleteProduct(id: number) {
    try {
      await api.delete(`/products/${id}`);
      mutate();
      toast.success("Товар удалён");
    } catch {
      toast.error("Ошибка");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-bold">Товары</h1>
        <div className="flex flex-wrap items-center gap-2">
          <Button render={<Link href="/products/new" />}>
            <Plus className="mr-2 h-4 w-4" />
            Добавить
          </Button>
          <Button variant="outline" onClick={() => setImportOpen(true)}>
            <Upload className="mr-2 h-4 w-4" />
            Импорт
          </Button>
          <Button variant="outline" onClick={() => setStockOpen(true)}>
            <PackageCheck className="mr-2 h-4 w-4" />
            Остатки
          </Button>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <Select value={filter} onValueChange={(v) => { setFilter(v || "all"); setPage(1); }} items={categoryFilterItems}>
          <SelectTrigger className="w-60">
            <SelectValue placeholder="Все категории" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Все категории</SelectItem>
            {categories?.map((c) => (
              <SelectItem key={c.id} value={String(c.id)}>
                {c.emoji} {c.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="text-sm text-muted-foreground">
          Всего: {data?.total ?? 0}
        </span>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
          {[...Array(18)].map((_, i) => (
            <Skeleton key={i} className="h-56 w-full rounded-lg" />
          ))}
        </div>
      ) : products?.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12 text-muted-foreground">
            <p>Нет товаров</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
          {products?.map((product) => (
            <Card key={product.id} size="sm" className="overflow-hidden">
              <div className="aspect-square bg-muted">
                {product.photos[0] ? (
                  <img
                    src={photoUrl(product.photos[0].id)}
                    alt={product.name}
                    className="h-full w-full object-cover"
                  />
                ) : (
                  <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
                    Нет фото
                  </div>
                )}
              </div>

              <CardContent className="space-y-2 p-3">
                <div className="flex items-start justify-between gap-1">
                  <h3 className="line-clamp-2 text-xs font-semibold leading-tight">{product.name}</h3>
                  <Badge variant={product.is_active ? "default" : "secondary"} className="shrink-0 text-[10px]">
                    {product.is_active ? "✓" : "✕"}
                  </Badge>
                </div>

                <p className="truncate text-[10px] text-muted-foreground">
                  {product.category_name}
                </p>

                <div className="flex flex-wrap gap-1">
                  {product.variants.slice(0, 3).map((v) => (
                    <Badge key={v.id} variant="outline" className="text-[10px]">
                      {v.volume} — {v.price}₽
                    </Badge>
                  ))}
                </div>

                <div className="flex gap-1 pt-1">
                  <Button size="sm" variant="outline" className="h-7 flex-1 px-2 text-xs" render={<Link href={`/products/${product.id}`} />}>
                    <Pencil className="h-3 w-3" />
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 w-7 p-0"
                    onClick={() => toggleActive(product.id)}
                  >
                    {product.is_active ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
                  </Button>
                  <AlertDialog>
                    <AlertDialogTrigger render={<Button size="sm" variant="outline" className="h-7 w-7 p-0" />}>
                      <Trash2 className="h-3 w-3 text-red-500" />
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Удалить товар?</AlertDialogTitle>
                        <AlertDialogDescription>
                          «{product.name}» будет удалён безвозвратно.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Отмена</AlertDialogCancel>
                        <AlertDialogAction onClick={() => deleteProduct(product.id)}>
                          Удалить
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <ImportDialog open={importOpen} onOpenChange={setImportOpen} onImported={() => mutate()} />
      <StockUpdateDialog open={stockOpen} onOpenChange={setStockOpen} onUpdated={() => mutate()} />

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-4">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            <ChevronLeft className="h-4 w-4" />
            Назад
          </Button>
          <span className="text-sm text-muted-foreground">
            Страница {page} из {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
            Вперёд
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
  );
}
