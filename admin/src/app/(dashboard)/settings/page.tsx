"use client";

import useSWR from "swr";
import { useState, useEffect } from "react";
import { fetcher } from "@/lib/swr";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { RotateCcw, Save } from "lucide-react";
import type { SystemMessage, DeliverySettings } from "@/lib/types";

export default function SettingsPage() {
  const { data: messages, isLoading, mutate } = useSWR<SystemMessage[]>("/settings/messages", fetcher);

  const [selectedKey, setSelectedKey] = useState<string>("");
  const [content, setContent] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (messages && messages.length > 0 && !selectedKey) {
      setSelectedKey(messages[0].key);
      setContent(messages[0].content);
    }
  }, [messages, selectedKey]);

  useEffect(() => {
    if (messages && selectedKey) {
      const msg = messages.find((m) => m.key === selectedKey);
      if (msg) setContent(msg.content);
    }
  }, [selectedKey, messages]);

  async function handleSave() {
    setSaving(true);
    try {
      await api.put(`/settings/messages/${selectedKey}`, { content });
      mutate();
      toast.success("Сохранено");
    } catch {
      toast.error("Ошибка");
    } finally {
      setSaving(false);
    }
  }

  async function handleReset() {
    try {
      await api.post(`/settings/messages/${selectedKey}/reset`);
      await mutate();
      const updated = await api.get<SystemMessage>(`/settings/messages/${selectedKey}`);
      setContent(updated.content);
      toast.success("Сброшено к стандарту");
    } catch {
      toast.error("Ошибка");
    }
  }

  const selectedMsg = messages?.find((m) => m.key === selectedKey);

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <h1 className="text-2xl font-bold">Настройки</h1>

      <Tabs defaultValue="messages">
        <TabsList>
          <TabsTrigger value="messages">Сообщения</TabsTrigger>
          <TabsTrigger value="delivery">Доставка</TabsTrigger>
          <TabsTrigger value="payment">Оплата</TabsTrigger>
        </TabsList>

        <TabsContent value="messages" className="space-y-4">
          {isLoading ? (
            <Skeleton className="h-64 w-full" />
          ) : (
            <>
              <div className="flex flex-wrap gap-2">
                {messages?.map((msg) => (
                  <Button
                    key={msg.key}
                    variant={selectedKey === msg.key ? "default" : "outline"}
                    size="sm"
                    onClick={() => setSelectedKey(msg.key)}
                  >
                    {msg.label}
                    {!msg.is_default && (
                      <Badge variant="secondary" className="ml-2 text-xs">
                        изменён
                      </Badge>
                    )}
                  </Button>
                ))}
              </div>

              {selectedMsg && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">{selectedMsg.label}</CardTitle>
                    <CardDescription>
                      Текст с поддержкой HTML-тегов (&lt;b&gt;, &lt;i&gt;, &lt;code&gt;)
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <Textarea
                      value={content}
                      onChange={(e) => setContent(e.target.value)}
                      rows={8}
                      className="font-mono text-sm"
                    />

                    <div className="flex justify-between">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handleReset}
                        disabled={selectedMsg.is_default}
                      >
                        <RotateCcw className="mr-2 h-3 w-3" />
                        Сбросить к стандарту
                      </Button>
                      <Button onClick={handleSave} disabled={saving}>
                        <Save className="mr-2 h-4 w-4" />
                        Сохранить
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              )}
            </>
          )}
        </TabsContent>

        <TabsContent value="delivery">
          <DeliverySettings />
        </TabsContent>

        <TabsContent value="payment">
          <PaymentSettings />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function PaymentSettings() {
  const { data, isLoading } = useSWR<{ payment_card_number: string | null; payment_recipient_name: string | null; tinkoff_enabled: boolean }>("/settings/payment", fetcher);

  if (isLoading) return <Skeleton className="h-48 w-full" />;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Реквизиты для оплаты</CardTitle>
        <CardDescription>
          Настраиваются в файле .env на сервере
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div>
          <span className="text-muted-foreground">Номер карты: </span>
          <span className="font-mono font-medium">
            {data?.payment_card_number || "—"}
          </span>
        </div>
        <div>
          <span className="text-muted-foreground">Получатель: </span>
          <span className="font-medium">
            {data?.payment_recipient_name || "—"}
          </span>
        </div>
        <div>
          <span className="text-muted-foreground">Tinkoff эквайринг: </span>
          <Badge variant={data?.tinkoff_enabled ? "default" : "secondary"}>
            {data?.tinkoff_enabled ? "Подключён" : "Не подключён"}
          </Badge>
        </div>
      </CardContent>
    </Card>
  );
}

function DeliverySettings() {
  const { data, isLoading, mutate } = useSWR<DeliverySettings>("/settings/delivery", fetcher);

  const [enabled, setEnabled] = useState(true);
  const [couriers, setCouriers] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (data) {
      setEnabled(data.delivery_enabled);
      setCouriers(data.courier_services);
    }
  }, [data]);

  function toggleCourier(name: string) {
    setCouriers((prev) =>
      prev.includes(name) ? prev.filter((c) => c !== name) : [...prev, name]
    );
  }

  async function handleSave() {
    setSaving(true);
    try {
      await api.put("/settings/delivery", {
        delivery_enabled: enabled,
        courier_services: couriers,
      });
      mutate();
      toast.success("Сохранено");
    } catch {
      toast.error("Ошибка");
    } finally {
      setSaving(false);
    }
  }

  if (isLoading) return <Skeleton className="h-48 w-full" />;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Доставка</CardTitle>
        <CardDescription>
          Настройте отображение кнопки «Доставка» и выберите курьерские службы
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium">Кнопка «Доставка» в боте</p>
            <p className="text-xs text-muted-foreground">
              Показывать кнопку доставки в меню бота
            </p>
          </div>
          <Switch
            checked={enabled}
            onCheckedChange={setEnabled}
          />
        </div>

        {enabled && (
          <div className="space-y-3">
            <p className="text-sm font-medium">Курьерские службы</p>
            <p className="text-xs text-muted-foreground">
              Отметьте службы, с которыми вы работаете
            </p>
            <div className="flex flex-wrap gap-2">
              {data?.available_couriers?.map((courier) => {
                const selected = couriers.includes(courier);
                return (
                  <Button
                    key={courier}
                    variant={selected ? "default" : "outline"}
                    size="sm"
                    onClick={() => toggleCourier(courier)}
                  >
                    {courier}
                  </Button>
                );
              })}
            </div>
          </div>
        )}

        <div className="flex justify-end">
          <Button onClick={handleSave} disabled={saving}>
            <Save className="mr-2 h-4 w-4" />
            Сохранить
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
