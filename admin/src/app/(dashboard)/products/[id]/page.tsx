"use client";

import { useState, useMemo } from "react";
import { useParams } from "next/navigation";
import Image from "next/image";
import useSWR from "swr";
import { fetcher } from "@/lib/swr";
import { api, photoUrl } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ArrowLeft, Loader2, Trash2, Upload, Plus } from "lucide-react";
import Link from "next/link";
import type { Product, Category, ProductAttrsSettings, ProductAttrDef } from "@/lib/types";

interface EditableVariant {
  id?: number;
  volume: string;
  price: string;
  stock: string;
  attributes: Record<string, string>;
}

export default function EditProductPage() {
  const params = useParams();
  const id = params.id as string;

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [variants, setVariants] = useState<EditableVariant[]>([]);
  const [savingVariant, setSavingVariant] = useState<number | null>(null);

  const { data: product, mutate } = useSWR<Product>(`/products/${id}`, fetcher, {
    onSuccess: (nextProduct) => {
      setName(nextProduct.name);
      setDescription(nextProduct.description);
      setCategoryId(String(nextProduct.category_id));
      setVariants(
        nextProduct.variants.map((variant) => ({
          id: variant.id,
          volume: variant.volume,
          price: String(variant.price),
          stock: String(variant.stock ?? 0),
          attributes: { ...(variant.attributes ?? {}) },
        })),
      );
    },
  });
  const { data: categories } = useSWR<Category[]>("/categories", fetcher);
  const { data: attrsData } = useSWR<ProductAttrsSettings>("/settings/product-attrs", fetcher);

  const attrDefs: ProductAttrDef[] = attrsData?.attrs ?? [];

  const categoryItems = useMemo(() => {
    const map: Record<string, string> = {};
    for (const c of categories ?? []) {
      map[String(c.id)] = `${c.emoji} ${c.name}`;
    }
    return map;
  }, [categories]);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);

    try {
      await api.put(`/products/${id}`, {
        name,
        description,
        category_id: Number(categoryId),
      });
      mutate();
      toast.success("Сохранено");
    } catch {
      toast.error("Ошибка");
    } finally {
      setLoading(false);
    }
  }

  function updateVariantField(index: number, field: keyof EditableVariant, value: string) {
    setVariants((prev) =>
      prev.map((v, i) => (i === index ? { ...v, [field]: value } : v)),
    );
  }

  function updateVariantAttr(index: number, key: string, value: string) {
    setVariants((prev) =>
      prev.map((v, i) =>
        i === index ? { ...v, attributes: { ...v.attributes, [key]: value } } : v,
      ),
    );
  }

  async function saveVariant(index: number) {
    const v = variants[index];
    if (!v.id) return;

    setSavingVariant(index);
    try {
      await api.put(`/variants/${v.id}`, {
        volume: v.volume || "—",
        price: Number(v.price) || 0,
        stock: Number(v.stock) || 0,
        attributes: v.attributes,
      });
      toast.success("Вариант сохранён");
    } catch {
      toast.error("Ошибка");
    } finally {
      setSavingVariant(null);
    }
  }

  async function addVariant() {
    try {
      const res = await api.post<{ id: number }>(`/products/${id}/variants`, {
        volume: "Новый вариант",
        price: 0,
        stock: 0,
        attributes: {},
      });
      setVariants([...variants, { id: res.id, volume: "Новый вариант", price: "0", stock: "0", attributes: {} }]);
      toast.success("Вариант добавлен");
    } catch {
      toast.error("Ошибка");
    }
  }

  async function deleteVariant(index: number) {
    const v = variants[index];
    if (!v.id) return;

    if (variants.length <= 1) {
      toast.error("Должен остаться хотя бы один вариант");
      return;
    }

    try {
      await api.delete(`/variants/${v.id}`);
      setVariants(variants.filter((_, i) => i !== index));
      toast.success("Вариант удалён");
    } catch {
      toast.error("Ошибка");
    }
  }

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    try {
      await api.upload(`/products/${id}/photos`, file);
      mutate();
      toast.success("Фото добавлено");
    } catch {
      toast.error("Ошибка загрузки");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  }

  async function deletePhoto(photoId: number) {
    try {
      await api.delete(`/products/${id}/photos/${photoId}`);
      mutate();
      toast.success("Фото удалено");
    } catch {
      toast.error("Ошибка");
    }
  }

  if (!product) {
    return <Skeleton className="h-96 w-full" />;
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" render={<Link href="/products" />}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <h1 className="text-2xl font-bold">Редактирование товара</h1>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Фото</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              {product.photos.map((photo) => (
                <div key={photo.id} className="group relative aspect-square overflow-hidden rounded-lg bg-muted">
                  <Image
                    src={photoUrl(photo.id)}
                    alt=""
                    fill
                    unoptimized
                    sizes="(max-width: 768px) 50vw, 25vw"
                    className="object-cover"
                  />
                  <button
                    onClick={() => deletePhoto(photo.id)}
                    className="absolute right-1 top-1 rounded-full bg-red-500 p-1.5 text-white shadow-md"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              ))}

              <label className="flex aspect-square cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed bg-muted/50 transition-colors hover:bg-muted">
                {uploading ? (
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                ) : (
                  <>
                    <Upload className="h-6 w-6 text-muted-foreground" />
                    <span className="mt-1 text-xs text-muted-foreground">Загрузить</span>
                  </>
                )}
                <input
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={handleUpload}
                  disabled={uploading}
                />
              </label>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Варианты</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {variants.map((v, i) => (
              <div key={v.id ?? i} className="rounded-lg border p-3 space-y-2">
                <div className="flex items-end gap-2 flex-wrap">
                  <div className="flex-1 min-w-[100px] space-y-1">
                    <Label className="text-xs">Объём</Label>
                    <Input
                      value={v.volume}
                      onChange={(e) => updateVariantField(i, "volume", e.target.value)}
                    />
                  </div>
                  {attrDefs.map((attr) => (
                    <div key={attr.id} className="flex-1 min-w-[100px] space-y-1">
                      <Label className="text-xs">{attr.label}</Label>
                      <Input
                        value={v.attributes[attr.key] ?? ""}
                        onChange={(e) => updateVariantAttr(i, attr.key, e.target.value)}
                      />
                    </div>
                  ))}
                  <div className="w-24 space-y-1">
                    <Label className="text-xs">Цена (₽)</Label>
                    <Input
                      type="number"
                      value={v.price}
                      onChange={(e) => updateVariantField(i, "price", e.target.value)}
                    />
                  </div>
                  <div className="w-20 space-y-1">
                    <Label className="text-xs">Остаток</Label>
                    <Input
                      type="number"
                      value={v.stock}
                      onChange={(e) => updateVariantField(i, "stock", e.target.value)}
                    />
                  </div>
                </div>
                <div className="flex justify-end gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => saveVariant(i)}
                    disabled={savingVariant === i}
                  >
                    {savingVariant === i && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
                    Сохранить
                  </Button>
                  {variants.length > 1 && (
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      onClick={() => deleteVariant(i)}
                    >
                      <Trash2 className="h-4 w-4 text-red-500" />
                    </Button>
                  )}
                </div>
              </div>
            ))}

            <Button type="button" variant="outline" size="sm" onClick={addVariant}>
              <Plus className="mr-2 h-4 w-4" />
              Добавить вариант
            </Button>
          </CardContent>
        </Card>
      </div>

      <form onSubmit={handleSave}>
        <Card>
          <CardHeader>
            <CardTitle>Основное</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label>Категория</Label>
              <Select value={categoryId} onValueChange={(v) => setCategoryId(v || "")} items={categoryItems}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {categories?.map((c) => (
                    <SelectItem key={c.id} value={String(c.id)}>
                      {c.emoji} {c.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="name">Название</Label>
              <Input
                id="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="description">Описание</Label>
              <Textarea
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={5}
              />
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <Button type="submit" disabled={loading}>
                {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Сохранить
              </Button>
            </div>
          </CardContent>
        </Card>
      </form>
    </div>
  );
}
