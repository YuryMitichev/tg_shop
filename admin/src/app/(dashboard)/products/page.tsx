"use client";

import useSWR from "swr";
import { useState } from "react";
import Link from "next/link";
import { fetcher } from "@/lib/swr";
import { api, photoUrl } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Plus, Pencil, Trash2, Eye, EyeOff, Upload } from "lucide-react";
import { ImportDialog } from "@/components/import-dialog";
import type { Product, Category } from "@/lib/types";
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

export default function ProductsPage() {
  const [filter, setFilter] = useState<string>("all");
  const [importOpen, setImportOpen] = useState(false);

  const { data: products, isLoading, mutate } = useSWR<Product[]>(
    filter === "all" ? "/products" : `/products?category_id=${filter}`,
    fetcher,
  );

  const { data: categories } = useSWR<Category[]>("/categories", fetcher);

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
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Товары</h1>
        <Button render={<Link href="/products/new" />}>
          <Plus className="mr-2 h-4 w-4" />
          Добавить
        </Button>
        <Button variant="outline" onClick={() => setImportOpen(true)}>
          <Upload className="mr-2 h-4 w-4" />
          Импорт
        </Button>
      </div>

      <div className="flex items-center gap-2">
        <Select value={filter} onValueChange={(v) => setFilter(v || "all")}>
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
      </div>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[...Array(6)].map((_, i) => (
            <Skeleton key={i} className="h-64 w-full rounded-lg" />
          ))}
        </div>
      ) : products?.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12 text-muted-foreground">
            <p>Нет товаров</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {products?.map((product) => (
            <Card key={product.id} className="overflow-hidden">
              <div className="aspect-square bg-muted">
                {product.photos[0] ? (
                  <img
                    src={photoUrl(product.photos[0].id)}
                    alt={product.name}
                    className="h-full w-full object-cover"
                  />
                ) : (
                  <div className="flex h-full items-center justify-center text-muted-foreground">
                    Нет фото
                  </div>
                )}
              </div>

              <CardContent className="space-y-3 p-4">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="font-semibold">{product.name}</h3>
                    <p className="text-xs text-muted-foreground">
                      {product.category_name}
                    </p>
                  </div>
                  <Badge variant={product.is_active ? "default" : "secondary"}>
                    {product.is_active ? (
                      <Eye className="mr-1 h-3 w-3" />
                    ) : (
                      <EyeOff className="mr-1 h-3 w-3" />
                    )}
                    {product.is_active ? "Видим" : "Скрыт"}
                  </Badge>
                </div>

                <div className="flex flex-wrap gap-1">
                  {product.variants.map((v) => (
                    <Badge key={v.id} variant="outline" className="text-xs">
                      {v.volume} — {v.price}₽
                    </Badge>
                  ))}
                </div>

                <div className="flex gap-2 pt-1">
                  <Button size="sm" variant="outline" render={<Link href={`/products/${product.id}`} className="flex-1" />}>
                    <Pencil className="mr-1 h-3 w-3" />
                    Изменить
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => toggleActive(product.id)}
                  >
                    {product.is_active ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
                  </Button>
                  <AlertDialog>
                    <AlertDialogTrigger render={<Button size="sm" variant="outline" />}>
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
    </div>
  );
}
