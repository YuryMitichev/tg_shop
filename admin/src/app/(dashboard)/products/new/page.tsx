"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { fetcher } from "@/lib/swr";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Plus, Trash2, Loader2, ArrowLeft } from "lucide-react";
import Link from "next/link";
import type { Category, ProductAttrsSettings, ProductAttrDef } from "@/lib/types";

interface VariantRow {
  volume: string;
  price: string;
  stock: string;
  attributes: Record<string, string>;
}

function emptyVariant(): VariantRow {
  return { volume: "", price: "", stock: "", attributes: {} };
}

export default function NewProductPage() {
  const router = useRouter();
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

  const [categoryId, setCategoryId] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [variants, setVariants] = useState<VariantRow[]>([emptyVariant()]);
  const [loading, setLoading] = useState(false);

  function addVariant() {
    setVariants([...variants, emptyVariant()]);
  }

  function removeVariant(index: number) {
    setVariants(variants.filter((_, i) => i !== index));
  }

  function updateVariant(index: number, field: keyof VariantRow, value: string) {
    setVariants(
      variants.map((v, i) => (i === index ? { ...v, [field]: value } : v)),
    );
  }

  function updateAttr(index: number, key: string, value: string) {
    setVariants(
      variants.map((v, i) =>
        i === index ? { ...v, attributes: { ...v.attributes, [key]: value } } : v,
      ),
    );
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    if (!categoryId) {
      toast.error("Выберите категорию");
      return;
    }

    if (!name.trim() || !description.trim()) {
      toast.error("Заполните название и описание");
      return;
    }

    const validVariants = variants.filter((v) => v.price);

    if (validVariants.length === 0) {
      toast.error("Добавьте хотя бы один вариант с ценой");
      return;
    }

    setLoading(true);

    try {
      const res = await api.post<{ id: number }>("/products", {
        category_id: Number(categoryId),
        name,
        description,
        variants: validVariants.map((v) => {
          const attributes: Record<string, string> = {};
          for (const [k, val] of Object.entries(v.attributes)) {
            if (val.trim()) attributes[k] = val.trim();
          }
          return {
            volume: v.volume || "—",
            price: Number(v.price),
            stock: v.stock ? Number(v.stock) : 0,
            attributes,
          };
        }),
      });

      toast.success("Товар создан");
      router.push(`/products/${res.id}`);
    } catch {
      toast.error("Ошибка создания");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" render={<Link href="/products" />}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <h1 className="text-2xl font-bold">Новый товар</h1>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Основное</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label>Категория</Label>
              <Select value={categoryId} onValueChange={(v) => setCategoryId(v || "")} items={categoryItems}>
                <SelectTrigger>
                  <SelectValue placeholder="Выберите категорию" />
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
                placeholder="Свеча «Лаванда»"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="description">Описание</Label>
              <Textarea
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={4}
                placeholder="Натуральная соевая свеча с ароматом лаванды..."
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Варианты</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {variants.map((variant, i) => (
              <div key={i} className="rounded-lg border p-3 space-y-2">
                <div className="flex items-end gap-2 flex-wrap">
                  <div className="flex-1 min-w-[100px] space-y-1">
                    <Label className="text-xs">Объём</Label>
                    <Input
                      placeholder="200 мл"
                      value={variant.volume}
                      onChange={(e) => updateVariant(i, "volume", e.target.value)}
                    />
                  </div>
                  {attrDefs.map((attr) => (
                    <div key={attr.id} className="flex-1 min-w-[100px] space-y-1">
                      <Label className="text-xs">{attr.label}</Label>
                      <Input
                        placeholder={attr.label}
                        value={variant.attributes[attr.key] ?? ""}
                        onChange={(e) => updateAttr(i, attr.key, e.target.value)}
                      />
                    </div>
                  ))}
                  <div className="w-28 space-y-1">
                    <Label className="text-xs">Цена (₽)</Label>
                    <Input
                      type="number"
                      placeholder="1500"
                      value={variant.price}
                      onChange={(e) => updateVariant(i, "price", e.target.value)}
                    />
                  </div>
                  <div className="w-24 space-y-1">
                    <Label className="text-xs">Остаток</Label>
                    <Input
                      type="number"
                      placeholder="0"
                      value={variant.stock}
                      onChange={(e) => updateVariant(i, "stock", e.target.value)}
                    />
                  </div>
                  {variants.length > 1 && (
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      onClick={() => removeVariant(i)}
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

        <div className="flex justify-end gap-3">
          <Button variant="outline" render={<Link href="/products" />}>Отмена</Button>
          <Button type="submit" disabled={loading}>
            {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Создать товар
          </Button>
        </div>
      </form>
    </div>
  );
}
