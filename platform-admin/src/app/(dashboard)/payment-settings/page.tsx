"use client";

import useSWR from "swr";
import { useState } from "react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Save } from "lucide-react";
import { superAdminApi, superAdminFetcher } from "@/lib/swr";
import type { PlatformPaymentSettings } from "@/lib/types";

export default function PlatformPaymentSettingsPage() {
  const { data, isLoading, mutate } = useSWR<PlatformPaymentSettings>("/payment-settings", superAdminFetcher);

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Платёжные настройки</h1>
        <p className="text-sm text-muted-foreground">Ключи ЮKassa для приёма оплаты подписок от магазинов</p>
      </div>
      {isLoading || !data ? (
        <Skeleton className="h-96 w-full" />
      ) : (
        <PaymentSettingsForm
          key={`${data.yookassa_enabled}:${data.yookassa_shop_id}:${data.yookassa_secret_key_masked}`}
          data={data}
          onSaved={() => void mutate()}
        />
      )}
    </div>
  );
}

function PaymentSettingsForm({
  data,
  onSaved,
}: {
  data: PlatformPaymentSettings;
  onSaved: () => void;
}) {
  const [yookassaEnabled, setYookassaEnabled] = useState(data.yookassa_enabled);
  const [yookassaShopId, setYookassaShopId] = useState(data.yookassa_shop_id || "");

  const [yookassaSecretKey, setYookassaSecretKey] = useState("");
  const [yookassaSecretTouched, setYookassaSecretTouched] = useState(false);
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    setSaving(true);
    try {
      await superAdminApi.put("/payment-settings", {
        yookassa_shop_id: yookassaShopId,
        yookassa_secret_key: yookassaSecretTouched ? yookassaSecretKey : null,
        yookassa_enabled: yookassaEnabled,
      });
      onSaved();
      toast.success("Сохранено");
    } catch { toast.error("Ошибка"); }
    finally { setSaving(false); }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-base">ЮKassa</CardTitle>
            <CardDescription className="mt-1">Онлайн-оплата подписок через ЮKassa</CardDescription>
          </div>
          <Switch checked={yookassaEnabled} onCheckedChange={setYookassaEnabled} />
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label>shopId</Label>
          <Input value={yookassaShopId} onChange={(e) => setYookassaShopId(e.target.value)} placeholder="123456" />
        </div>
        <div className="space-y-2">
          <Label>Секретный ключ</Label>
          <Input
            value={yookassaSecretTouched ? yookassaSecretKey : ""}
            onChange={(e) => { setYookassaSecretKey(e.target.value); setYookassaSecretTouched(true); }}
            placeholder={data.yookassa_secret_key_masked ? `Текущий: ${data.yookassa_secret_key_masked} — введите новый для замены` : "live_XXXXXXXXXXXXX или test_XXXXXXXXXXXXX"}
            className="font-mono"
          />
        </div>
        <details className="text-sm">
          <summary className="cursor-pointer text-muted-foreground hover:text-foreground">Как подключить ЮKassa — инструкция</summary>
          <div className="mt-2 space-y-2 rounded-md bg-muted p-3 text-xs leading-relaxed">
            <p><b>Шаг 1.</b> Зарегистрируйтесь на <a href="https://yookassa.ru" target="_blank" rel="noopener noreferrer" className="text-blue-500 underline">yookassa.ru</a> и пройдите проверку.</p>
            <p><b>Шаг 2.</b> В личном кабинете ЮKassa откройте «Интеграция» → «Настройки API».</p>
            <p><b>Шаг 3.</b> Скопируйте <b>shopId</b> и <b>секретный ключ</b>.</p>
            <p><b>Шаг 4.</b> Вставьте значения в поля выше и нажмите «Сохранить».</p>
          </div>
        </details>
        <div className="flex justify-end pt-2">
          <Button onClick={handleSave} disabled={saving}><Save className="mr-2 h-4 w-4" />{saving ? "Сохранение..." : "Сохранить"}</Button>
        </div>
      </CardContent>
    </Card>
  );
}
