"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Bot, Check, Copy, RefreshCw, Save, Sparkles, X } from "lucide-react";

import { api, channelImportMediaUrl } from "@/lib/api";
import { fetcher } from "@/lib/swr";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

type Variant = {
  title?: string;
  volume?: string;
  price: number | null;
  stock: number | null;
  currency?: string;
  attributes?: Record<string, string>;
};

type Candidate = {
  id: number;
  status: string;
  name: string | null;
  description: string | null;
  category_name: string | null;
  proposed_category: boolean;
  sku: string | null;
  currency: string | null;
  variants: Variant[];
  attributes: Record<string, string>;
  duplicate_product_id: number | null;
  duplicate_score: number | null;
  product_id: number | null;
  owner_note: string | null;
  job_id: number;
  post: { text: string | null; telegram_message_id: number; version: number };
  photos?: { id: number; position: number }[];
};

type ImportSettings = {
  connected: boolean;
  feature_enabled: boolean;
  channel_title: string | null;
  channel_username: string | null;
  is_paused: boolean;
  notifications_enabled: boolean;
  backfill_status: string | null;
  backfill_error: string | null;
};

type ImportStats = {
  candidates: Record<string, number>;
  prefilter: Record<string, number>;
  jobs: Record<string, number>;
  ai: { cost_usd: number; budget_usd: number; budget_percent: number };
};

const statusLabel: Record<string, string> = {
  pending: "Готов к проверке",
  needs_manual: "Нужно заполнить",
  possible_duplicate: "Возможный дубликат",
  duplicate_skipped: "Дубликат",
  approved: "Опубликован",
  rejected: "Отклонён",
  superseded: "Устарел",
};

export default function ChannelImportPage() {
  const [filter, setFilter] = useState("open");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const { data: settings, mutate: mutateSettings } = useSWR<ImportSettings>(
    "/channel-import/settings",
    fetcher,
  );
  const { data: stats, mutate: mutateStats } = useSWR<ImportStats>(
    "/channel-import/stats",
    fetcher,
  );
  const { data: allCandidates, mutate: mutateCandidates } = useSWR<Candidate[]>(
    "/channel-import/candidates",
    fetcher,
    { refreshInterval: 5000 },
  );
  const candidates = (allCandidates ?? []).filter((candidate) =>
    filter === "all"
      ? true
      : filter === "open"
        ? ["pending", "needs_manual", "possible_duplicate"].includes(candidate.status)
        : candidate.status === filter,
  );
  const detailKey = selectedId ? `/channel-import/candidates/${selectedId}` : null;
  const { data: detail, mutate: mutateDetail } = useSWR<Candidate>(detailKey, fetcher);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const id = Number(new URLSearchParams(window.location.search).get("candidate"));
      if (id) setSelectedId(id);
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  async function updateSettings(values: Partial<ImportSettings>) {
    try {
      await api.put("/channel-import/settings", values);
      await mutateSettings();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось изменить настройки");
    }
  }

  async function backfill() {
    try {
      await api.post("/channel-import/backfill");
      toast.success("Импорт последних 50 постов запущен");
      await mutateSettings();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось запустить импорт");
    }
  }

  async function refreshAll() {
    await Promise.all([mutateCandidates(), mutateDetail(), mutateStats(), mutateSettings()]);
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold">
            <Sparkles className="h-6 w-6" /> AI-импорт
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Посты проходят бесплатный локальный фильтр, AI создаёт только черновики.
          </p>
        </div>
        <Button variant="outline" onClick={refreshAll}>
          <RefreshCw className="mr-2 h-4 w-4" /> Обновить
        </Button>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader><CardTitle>Канал</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            {settings?.connected ? (
              <>
                <div>
                  <div className="font-medium">{settings.channel_title}</div>
                  <div className="text-xs text-muted-foreground">
                    {settings.channel_username ? `@${settings.channel_username}` : "Приватный канал"}
                  </div>
                </div>
                <div className="flex items-center justify-between">
                  <Label>Импорт приостановлен</Label>
                  <Switch
                    checked={settings.is_paused}
                    onCheckedChange={(checked) => updateSettings({ is_paused: checked })}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <Label>Telegram-уведомления</Label>
                  <Switch
                    checked={settings.notifications_enabled}
                    onCheckedChange={(checked) => updateSettings({ notifications_enabled: checked })}
                  />
                </div>
                <Button
                  variant="outline"
                  className="w-full"
                  onClick={backfill}
                  disabled={settings.backfill_status === "not_configured"}
                >
                  Повторить импорт 50 постов
                </Button>
                <div className="text-xs text-muted-foreground">
                  Backfill: {settings.backfill_status === "not_configured"
                    ? "не настроен — realtime работает"
                    : settings.backfill_status || "не запускался"}
                  {settings.backfill_error && <div className="mt-1 text-destructive">{settings.backfill_error}</div>}
                </div>
              </>
            ) : (
              <div className="space-y-3 text-sm">
                <Bot className="h-8 w-8 text-muted-foreground" />
                <p>Откройте бота магазина и отправьте команду <code>/connect_channel</code>.</p>
                <p className="text-muted-foreground">Бот должен быть администратором выбранного канала.</p>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>AI-бюджет месяца</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <div className="text-2xl font-bold">
              ${stats?.ai.cost_usd.toFixed(4) ?? "0.0000"} / ${stats?.ai.budget_usd.toFixed(2) ?? "2.00"}
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-muted">
              <div
                className={`h-full ${Number(stats?.ai.budget_percent) >= 80 ? "bg-amber-500" : "bg-primary"}`}
                style={{ width: `${Math.min(100, stats?.ai.budget_percent ?? 0)}%` }}
              />
            </div>
            <p className="text-xs text-muted-foreground">
              При 100% новые задания сохраняются со статусом budget_blocked.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Поток</CardTitle></CardHeader>
          <CardContent className="grid grid-cols-2 gap-3 text-sm">
            <Metric label="Отсечено локально" value={stats?.prefilter.non_product ?? 0} />
            <Metric label="Черновиков" value={stats?.candidates.pending ?? 0} />
            <Metric label="Ручная проверка" value={stats?.candidates.needs_manual ?? 0} />
            <Metric label="Ошибок" value={stats?.jobs.failed ?? 0} />
          </CardContent>
        </Card>
      </div>

      <div className="grid min-h-[640px] gap-4 lg:grid-cols-[340px_1fr]">
        <Card>
          <CardHeader className="border-b">
            <CardTitle>Черновики</CardTitle>
            <select
              className="mt-2 h-9 rounded-md border bg-background px-2 text-sm"
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
            >
              <option value="open">Требуют решения</option>
              <option value="all">Все</option>
              <option value="approved">Опубликованные</option>
              <option value="rejected">Отклонённые</option>
              <option value="duplicate_skipped">Дубликаты</option>
            </select>
          </CardHeader>
          <CardContent className="max-h-[720px] space-y-2 overflow-y-auto py-3">
            {candidates.length ? candidates.map((candidate) => (
              <button
                key={candidate.id}
                onClick={() => setSelectedId(candidate.id)}
                className={`w-full rounded-lg border p-3 text-left transition-colors hover:bg-muted ${selectedId === candidate.id ? "border-primary bg-muted" : ""}`}
              >
                <div className="line-clamp-2 font-medium">{candidate.name || "Без названия"}</div>
                <div className="mt-2 flex items-center justify-between gap-2">
                  <Badge variant={candidate.status === "approved" ? "default" : "outline"}>
                    {statusLabel[candidate.status] || candidate.status}
                  </Badge>
                  <span className="text-xs text-muted-foreground">#{candidate.id}</span>
                </div>
              </button>
            )) : <p className="py-8 text-center text-sm text-muted-foreground">Черновиков нет</p>}
          </CardContent>
        </Card>

        {detail ? (
          <CandidateEditor
            key={detail.id}
            candidate={detail}
            onChanged={refreshAll}
          />
        ) : (
          <Card><CardContent className="flex h-full items-center justify-center text-muted-foreground">Выберите черновик</CardContent></Card>
        )}
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return <div className="rounded-lg bg-muted p-3"><div className="text-xl font-semibold">{value}</div><div className="text-xs text-muted-foreground">{label}</div></div>;
}

function CandidateEditor({ candidate, onChanged }: { candidate: Candidate; onChanged: () => Promise<void> }) {
  const editable = ["pending", "needs_manual", "possible_duplicate"].includes(candidate.status);
  const [name, setName] = useState(candidate.name ?? "");
  const [description, setDescription] = useState(candidate.description ?? "");
  const [category, setCategory] = useState(candidate.category_name ?? "");
  const [sku, setSku] = useState(candidate.sku ?? "");
  const [currency, setCurrency] = useState(candidate.currency ?? "RUB");
  const [variants, setVariants] = useState<Variant[]>(candidate.variants ?? []);
  const [attributesJson, setAttributesJson] = useState(JSON.stringify(candidate.attributes ?? {}, null, 2));
  const [saving, setSaving] = useState(false);

  async function save() {
    let attributes: Record<string, string>;
    try {
      attributes = JSON.parse(attributesJson);
    } catch {
      toast.error("Характеристики должны быть валидным JSON-объектом");
      return;
    }
    setSaving(true);
    try {
      await api.patch(`/channel-import/candidates/${candidate.id}`, {
        name, description, category_name: category, sku, currency, variants, attributes,
      });
      toast.success("Черновик сохранён");
      await onChanged();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось сохранить");
    } finally {
      setSaving(false);
    }
  }

  async function action(actionName: "approve" | "reject" | "mark-duplicate" | "reanalyze") {
    try {
      await api.post(`/channel-import/candidates/${candidate.id}/${actionName}`);
      toast.success(actionName === "approve" ? "Товар опубликован" : "Решение сохранено");
      await onChanged();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Операция не выполнена");
    }
  }

  function updateVariant(index: number, patch: Partial<Variant>) {
    setVariants((items) => items.map((item, current) => current === index ? { ...item, ...patch } : item));
  }

  return (
    <Card>
      <CardHeader className="border-b">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <CardTitle>{candidate.name || "Новый черновик"}</CardTitle>
            <Badge className="mt-2" variant="outline">{statusLabel[candidate.status] || candidate.status}</Badge>
          </div>
          <div className="flex flex-wrap gap-2">
            {editable && <Button variant="outline" onClick={save} disabled={saving}><Save className="mr-2 h-4 w-4" />Сохранить</Button>}
            {editable && <Button onClick={() => action("approve")}><Check className="mr-2 h-4 w-4" />Подтвердить</Button>}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-6 py-5">
        {(candidate.photos?.length ?? 0) > 0 && (
          <div className="flex gap-3 overflow-x-auto">
            {candidate.photos?.map((photo) => (
              <img key={photo.id} src={channelImportMediaUrl(photo.id)} alt="Фото из поста" className="h-40 w-40 shrink-0 rounded-lg object-cover" />
            ))}
          </div>
        )}

        <div className="rounded-lg bg-muted p-4">
          <div className="mb-2 text-xs font-semibold uppercase text-muted-foreground">Исходный пост · версия {candidate.post.version}</div>
          <p className="whitespace-pre-wrap text-sm">{candidate.post.text || "Пост без текста"}</p>
        </div>

        {candidate.duplicate_product_id && (
          <div className="rounded-lg border border-amber-400/50 bg-amber-50 p-3 text-sm dark:bg-amber-950/20">
            Возможный дубликат товара #{candidate.duplicate_product_id}, сходство {Math.round((candidate.duplicate_score ?? 0) * 100)}%
          </div>
        )}

        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Название"><Input value={name} disabled={!editable} onChange={(e) => setName(e.target.value)} /></Field>
          <Field label="Категория"><Input value={category} disabled={!editable} onChange={(e) => setCategory(e.target.value)} /></Field>
          <Field label="Артикул"><Input value={sku} disabled={!editable} onChange={(e) => setSku(e.target.value)} /></Field>
          <Field label="Валюта"><Input value={currency} disabled={!editable} onChange={(e) => setCurrency(e.target.value)} /></Field>
        </div>
        <Field label="Описание"><Textarea rows={5} value={description} disabled={!editable} onChange={(e) => setDescription(e.target.value)} /></Field>

        <div className="space-y-3">
          <div className="flex items-center justify-between"><Label>Варианты, цены и остатки</Label>{editable && <Button size="sm" variant="outline" onClick={() => setVariants([...variants, { title: "—", price: null, stock: null, currency: "RUB", attributes: {} }])}>Добавить вариант</Button>}</div>
          {variants.map((variant, index) => (
            <div key={index} className="grid gap-2 rounded-lg border p-3 md:grid-cols-[1fr_140px_120px_auto]">
              <Input placeholder="Вариант / объём" disabled={!editable} value={variant.title ?? variant.volume ?? ""} onChange={(e) => updateVariant(index, { title: e.target.value })} />
              <Input type="number" placeholder="Цена" disabled={!editable} value={variant.price ?? ""} onChange={(e) => updateVariant(index, { price: e.target.value === "" ? null : Number(e.target.value) })} />
              <Input type="number" placeholder="Остаток" disabled={!editable} value={variant.stock ?? ""} onChange={(e) => updateVariant(index, { stock: e.target.value === "" ? null : Number(e.target.value) })} />
              {editable && <Button size="sm" variant="ghost" onClick={() => setVariants(variants.filter((_, current) => current !== index))}><X className="h-4 w-4" /></Button>}
            </div>
          ))}
        </div>

        <Field label="Общие характеристики (JSON)"><Textarea className="font-mono text-xs" rows={6} value={attributesJson} disabled={!editable} onChange={(e) => setAttributesJson(e.target.value)} /></Field>

        {editable && (
          <div className="flex flex-wrap gap-2 border-t pt-4">
            <Button variant="outline" onClick={() => action("reanalyze")}><RefreshCw className="mr-2 h-4 w-4" />Переанализировать</Button>
            <Button variant="outline" onClick={() => action("mark-duplicate")}><Copy className="mr-2 h-4 w-4" />Это дубликат</Button>
            <Button variant="destructive" onClick={() => action("reject")}><X className="mr-2 h-4 w-4" />Не товар</Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="space-y-2"><Label>{label}</Label>{children}</div>;
}
