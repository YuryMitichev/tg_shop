"use client";

import useSWR from "swr";
import { useState } from "react";
import { fetcher } from "@/lib/swr";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog";
import { Plus, Pencil, Trash2, FolderTree } from "lucide-react";
import type { Category } from "@/lib/types";

export default function CategoriesPage() {
  const { data: categories, isLoading, mutate } = useSWR<Category[]>("/categories", fetcher);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [emoji, setEmoji] = useState("");

  function openCreate() {
    setEditId(null);
    setName("");
    setEmoji("");
    setDialogOpen(true);
  }

  function openEdit(cat: Category) {
    setEditId(cat.id);
    setName(cat.name);
    setEmoji(cat.emoji || "");
    setDialogOpen(true);
  }

  async function handleSave() {
    if (!name.trim()) {
      toast.error("Введите название");
      return;
    }

    try {
      if (editId) {
        await api.put(`/categories/${editId}`, {
          name,
          emoji: emoji || null,
        });
        toast.success("Категория обновлена");
      } else {
        await api.post("/categories", {
          name,
          emoji: emoji || null,
        });
        toast.success("Категория создана");
      }
      mutate();
      setDialogOpen(false);
    } catch {
      toast.error("Ошибка");
    }
  }

  async function handleDelete(id: number) {
    try {
      const res = await api.delete<{ ok: boolean; error?: string }>(`/categories/${id}`);
      if (!res.ok) {
        toast.error(res.error || "В категории есть товары");
        return;
      }
      mutate();
      toast.success("Категория удалена");
    } catch {
      toast.error("Ошибка");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Категории</h1>
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger render={<Button onClick={openCreate} />}>
            <Plus className="mr-2 h-4 w-4" />
            Добавить
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{editId ? "Редактировать" : "Новая категория"}</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 py-2">
              <div className="space-y-2">
                <Label>Название</Label>
                <Input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Свечи"
                />
              </div>
              <div className="space-y-2">
                <Label>Эмодзи (необязательно)</Label>
                <Input
                  value={emoji}
                  onChange={(e) => setEmoji(e.target.value)}
                  placeholder="🕯"
                  maxLength={2}
                />
              </div>
            </div>
            <DialogFooter>
              <DialogClose render={<Button variant="outline" />}>Отмена</DialogClose>
              <Button onClick={handleSave}>Сохранить</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {[...Array(4)].map((_, i) => (
            <Skeleton key={i} className="h-16 w-full rounded-lg" />
          ))}
        </div>
      ) : categories?.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12 text-muted-foreground">
            <FolderTree className="mb-2 h-8 w-8 opacity-50" />
            <p>Нет категорий</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {categories?.map((cat) => (
            <Card key={cat.id}>
              <CardContent className="flex items-center justify-between py-4">
                <div className="flex items-center gap-3">
                  {cat.emoji && <span className="text-2xl">{cat.emoji}</span>}
                  <span className="font-medium">{cat.name}</span>
                </div>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => openEdit(cat)}
                  >
                    <Pencil className="h-3 w-3" />
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleDelete(cat.id)}
                  >
                    <Trash2 className="h-3 w-3 text-red-500" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
