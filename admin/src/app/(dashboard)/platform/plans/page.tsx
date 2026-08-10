"use client";

import useSWR from "swr";
import { superAdminFetcher } from "@/lib/swr";
import { superAdminApi, api } from "@/lib/api";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog";
import { Plus, Pencil, Check } from "lucide-react";
import { formatPrice } from "@/lib/format";
import type { SubscriptionPlanAdmin } from "@/lib/types";

export default function PlansPage() {
  const router = useRouter();
  const [allowed, setAllowed] = useState(false);
  const [editing, setEditing] = useState<SubscriptionPlanAdmin | null>(null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    api
      .get<{ is_super_admin: boolean }>("/auth/me")
      .then((res) => {
        if (!res.is_super_admin) {
          router.replace("/dashboard");
        } else {
          setAllowed(true);
        }
      })
      .catch(() => router.replace("/login"));
  }, [router]);

  const { data, isLoading, mutate } = useSWR<{ plans: SubscriptionPlanAdmin[] }>(
    allowed ? "/plans" : null,
    superAdminFetcher,
  );

  const plans = data?.plans ?? [];

  if (!allowed) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <p className="text-muted-foreground">Загрузка...</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Тарифы</h1>
          <p className="text-sm text-muted-foreground">
            Управление тарифными планами подписки
          </p>
        </div>
        <Button size="sm" onClick={() => setCreating(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Новый тариф
        </Button>
      </div>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2">
          {[...Array(4)].map((_, i) => (
            <Skeleton key={i} className="h-48" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {plans.map((plan) => (
            <PlanCard key={plan.id} plan={plan} onEdit={() => setEditing(plan)} />
          ))}
        </div>
      )}

      {editing && (
        <PlanEditDialog
          plan={editing}
          open={!!editing}
          onOpenChange={(open) => { if (!open) setEditing(null); }}
          onSave={async (data) => {
            try {
              await superAdminApi.patch(`/plans/${editing.id}`, data);
              mutate();
              toast.success("Тариф обновлён");
              setEditing(null);
            } catch {
              toast.error("Ошибка");
            }
          }}
        />
      )}

      {creating && (
        <PlanEditDialog
          open={creating}
          onOpenChange={setCreating}
          onSave={async (data) => {
            try {
              await superAdminApi.post("/plans", data);
              mutate();
              toast.success("Тариф создан");
              setCreating(false);
            } catch {
              toast.error("Ошибка");
            }
          }}
        />
      )}
    </div>
  );
}

function PlanCard({ plan, onEdit }: { plan: SubscriptionPlanAdmin; onEdit: () => void }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">{plan.name}</CardTitle>
          <div className="flex gap-2">
            {plan.is_trial && <Badge variant="secondary">Триал</Badge>}
            {!plan.is_active && <Badge variant="outline">Отключён</Badge>}
          </div>
        </div>
        <CardDescription>{plan.description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-baseline gap-2">
          <span className="text-2xl font-bold">{formatPrice(plan.price)}</span>
          <span className="text-sm text-muted-foreground">
            / {plan.duration_days} дн.
          </span>
        </div>
        {plan.features.length > 0 && (
          <ul className="space-y-1">
            {plan.features.slice(0, 5).map((f, i) => (
              <li key={i} className="flex items-start gap-2 text-xs text-muted-foreground">
                <Check className="mt-0.5 h-3 w-3 shrink-0 text-green-500" />
                {f}
              </li>
            ))}
            {plan.features.length > 5 && (
              <li className="text-xs text-muted-foreground">
                +{plan.features.length - 5} ещё
              </li>
            )}
          </ul>
        )}
        <Button size="sm" variant="outline" onClick={onEdit}>
          <Pencil className="mr-2 h-3 w-3" />
          Редактировать
        </Button>
      </CardContent>
    </Card>
  );
}

interface PlanFormData {
  name: string;
  description: string | null;
  price: number;
  duration_days: number;
  features: string[];
  is_active?: boolean;
}

function PlanEditDialog({
  plan,
  open,
  onOpenChange,
  onSave,
}: {
  plan?: SubscriptionPlanAdmin;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (data: PlanFormData) => Promise<void>;
}) {
  const [name, setName] = useState(plan?.name ?? "");
  const [description, setDescription] = useState(plan?.description ?? "");
  const [price, setPrice] = useState(String(plan?.price ?? ""));
  const [durationDays, setDurationDays] = useState(String(plan?.duration_days ?? "30"));
  const [featuresText, setFeaturesText] = useState(
    plan?.features?.join("\n") ?? ""
  );
  const [isActive, setIsActive] = useState(plan?.is_active ?? true);
  const [saving, setSaving] = useState(false);

  async function handleSubmit() {
    if (!name.trim() || !price || !durationDays) {
      toast.error("Заполните обязательные поля");
      return;
    }
    setSaving(true);
    const data: PlanFormData = {
      name: name.trim(),
      description: description.trim() || null,
      price: parseFloat(price),
      duration_days: parseInt(durationDays, 10),
      features: featuresText.split("\n").map((s) => s.trim()).filter(Boolean),
      is_active: isActive,
    };
    await onSave(data);
    setSaving(false);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{plan ? "Редактировать тариф" : "Новый тариф"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label>Название</Label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Подписка — 1 месяц"
            />
          </div>
          <div className="space-y-2">
            <Label>Описание</Label>
            <Input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Полный функционал магазина"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label>Цена (₽)</Label>
              <Input
                type="number"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                placeholder="5000"
              />
            </div>
            <div className="space-y-2">
              <Label>Длительность (дн.)</Label>
              <Input
                type="number"
                value={durationDays}
                onChange={(e) => setDurationDays(e.target.value)}
                placeholder="30"
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label>Возможности (по одной на строку)</Label>
            <Textarea
              value={featuresText}
              onChange={(e) => setFeaturesText(e.target.value)}
              rows={5}
              className="text-sm"
              placeholder={"Каталог товаров\nЗаказы и корзина\nАдмин-панель"}
            />
          </div>
          {plan && !plan.is_trial && (
            <div className="flex items-center justify-between">
              <Label>Активен</Label>
              <Switch checked={isActive} onCheckedChange={setIsActive} />
            </div>
          )}
        </div>
        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>
            Отмена
          </DialogClose>
          <Button onClick={handleSubmit} disabled={saving}>
            {saving ? "Сохранение..." : "Сохранить"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
