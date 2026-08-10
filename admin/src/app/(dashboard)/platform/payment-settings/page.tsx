"use client";

import useSWR from "swr";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Save } from "lucide-react";
import { superAdminApi, api } from "@/lib/api";
import { superAdminFetcher } from "@/lib/swr";
import type { PlatformPaymentSettings } from "@/lib/types";

export default function PlatformPaymentSettingsPage() {
  const router = useRouter();
  const [allowed, setAllowed] = useState(false);

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

  const { data, isLoading, mutate } = useSWR<PlatformPaymentSettings>(
    allowed ? "/payment-settings" : null,
    superAdminFetcher,
  );

  const [yookassaEnabled, setYookassaEnabled] = useState(false);
  const [yookassaShopId, setYookassaShopId] = useState("");
  const [yookassaSecretKey, setYookassaSecretKey] = useState("");
  const [yookassaSecretTouched, setYookassaSecretTouched] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (data) {
      setYookassaEnabled(data.yookassa_enabled);
      setYookassaShopId(data.yookassa_shop_id || "");
      setYookassaSecretKey("");
      setYookassaSecretTouched(false);
    }
  }, [data]);

  async function handleSave() {
    setSaving(true);
    try {
      await superAdminApi.put("/payment-settings", {
        yookassa_shop_id: yookassaShopId,
        yookassa_secret_key: yookassaSecretTouched ? yookassaSecretKey : null,
        yookassa_enabled: yookassaEnabled,
      });
      mutate();
      toast.success("Сохранено");
    } catch {
      toast.error("Ошибка");
    } finally {
      setSaving(false);
    }
  }

  if (!allowed) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <p className="text-muted-foreground">Загрузка...</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Платёжные настройки платформы</h1>
        <p className="text-sm text-muted-foreground">
          Ключи ЮKassa для приёма оплаты подписок от магазинов
        </p>
      </div>

      {isLoading ? (
        <Skeleton className="h-96 w-full" />
      ) : (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-base">ЮKassa</CardTitle>
                <CardDescription className="mt-1">
                  Онлайн-оплата подписок через ЮKassa
                </CardDescription>
              </div>
              <Switch
                checked={yookassaEnabled}
                onCheckedChange={setYookassaEnabled}
              />
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label>shopId</Label>
              <Input
                value={yookassaShopId}
                onChange={(e) => setYookassaShopId(e.target.value)}
                placeholder="123456"
              />
            </div>
            <div className="space-y-2">
              <Label>Секретный ключ</Label>
              <Input
                value={yookassaSecretTouched ? yookassaSecretKey : ""}
                onChange={(e) => {
                  setYookassaSecretKey(e.target.value);
                  setYookassaSecretTouched(true);
                }}
                placeholder={
                  data?.yookassa_secret_key_masked
                    ? `Текущий: ${data.yookassa_secret_key_masked} — введите новый для замены`
                    : "live_XXXXXXXXXXXXX или test_XXXXXXXXXXXXX"
                }
                className="font-mono"
              />
            </div>
            <details className="text-sm">
              <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                Как подключить ЮKassa — инструкция
              </summary>
              <div className="mt-2 space-y-2 rounded-md bg-muted p-3 text-xs leading-relaxed">
                <p>
                  <b>Шаг 1.</b> Зарегистрируйтесь на{" "}
                  <a
                    href="https://yookassa.ru"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-500 underline"
                  >
                    yookassa.ru
                  </a>{" "}
                  и пройдите проверку (ИНН, реквизиты).
                </p>
                <p>
                  <b>Шаг 2.</b> В личном кабинете ЮKassa откройте раздел
                  «Интеграция» → «Настройки API».
                </p>
                <p>
                  <b>Шаг 3.</b> Скопируйте значения:
                </p>
                <ul className="ml-4 list-disc space-y-0.5">
                  <li>
                    <b>shopId</b> — номер магазина (вверху страницы)
                  </li>
                  <li>
                    <b>Секретный ключ</b> — нажмите «Выпустить ключ», скопируйте
                    значение целиком
                  </li>
                </ul>
                <p>
                  <b>Шаг 4.</b> Вставьте оба значения в поля выше и нажмите
                  «Сохранить».
                </p>
                <p className="text-muted-foreground">
                  После подключения магазины смогут оплачивать подписки картой.
                </p>
              </div>
            </details>

            <div className="flex justify-end pt-2">
              <Button onClick={handleSave} disabled={saving}>
                <Save className="mr-2 h-4 w-4" />
                {saving ? "Сохранение..." : "Сохранить"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
