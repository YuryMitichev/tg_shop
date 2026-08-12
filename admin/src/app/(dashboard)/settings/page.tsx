"use client";

import useSWR from "swr";
import { useState, useEffect } from "react";
import { fetcher } from "@/lib/swr";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button, buttonVariants } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { RotateCcw, Save, Download, Lock, ExternalLink, Info } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { SystemMessage, DeliverySettings, ProductAttrsSettings, ProductAttrDef, CompanyInfo, LegalDocument, RoskomnadzorInfo, ShopInfo, ThemeSettings } from "@/lib/types";

const LEGAL_TYPE_LABELS: Record<string, string> = {
  individual: "Физическое лицо",
  ip: "Индивидуальный предприниматель",
  ooo: "Общество с ограниченной ответственностью",
};

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

      <Tabs defaultValue="shop">
        <TabsList>
          <TabsTrigger value="shop">Магазин</TabsTrigger>
          <TabsTrigger value="messages">Сообщения</TabsTrigger>
          <TabsTrigger value="delivery">Доставка</TabsTrigger>
          <TabsTrigger value="attrs">Характеристики</TabsTrigger>
          <TabsTrigger value="company">Реквизиты</TabsTrigger>
          <TabsTrigger value="payment">Оплата</TabsTrigger>
          <TabsTrigger value="theme">Дизайн</TabsTrigger>
          <TabsTrigger value="legal">Документы</TabsTrigger>
        </TabsList>

        <TabsContent value="shop">
          <ShopNameSettings />
        </TabsContent>

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

        <TabsContent value="attrs">
          <ProductAttrsSettingsTab />
        </TabsContent>

        <TabsContent value="company">
          <CompanyInfoSettings />
        </TabsContent>

        <TabsContent value="payment">
          <PaymentSettings />
        </TabsContent>

        <TabsContent value="theme">
          <ThemeSettingsTab />
        </TabsContent>

        <TabsContent value="legal">
          <LegalDocsSettings />
        </TabsContent>
      </Tabs>
    </div>
  );
}

interface PaymentSettingsData {
  payment_card_number: string | null;
  payment_recipient_name: string | null;
  yookassa_shop_id: string | null;
  yookassa_secret_key_masked: string | null;
  yookassa_enabled: boolean;
  manual_payment_enabled: boolean;
}

function PaymentSettings() {
  const { data, isLoading, mutate } = useSWR<PaymentSettingsData>("/settings/payments", fetcher);

  const [manualEnabled, setManualEnabled] = useState(true);
  const [cardNumber, setCardNumber] = useState("");
  const [recipientName, setRecipientName] = useState("");

  const [yookassaEnabled, setYookassaEnabled] = useState(false);
  const [yookassaShopId, setYookassaShopId] = useState("");
  const [yookassaSecretKey, setYookassaSecretKey] = useState("");
  const [yookassaSecretTouched, setYookassaSecretTouched] = useState(false);

  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (data) {
      setManualEnabled(data.manual_payment_enabled);
      setCardNumber(data.payment_card_number || "");
      setRecipientName(data.payment_recipient_name || "");
      setYookassaEnabled(data.yookassa_enabled);
      setYookassaShopId(data.yookassa_shop_id || "");
      setYookassaSecretKey("");
      setYookassaSecretTouched(false);
    }
  }, [data]);

  async function handleSave() {
    setSaving(true);
    try {
      await api.put("/settings/payments", {
        payment_card_number: cardNumber,
        payment_recipient_name: recipientName,
        yookassa_shop_id: yookassaShopId,
        yookassa_secret_key: yookassaSecretTouched ? yookassaSecretKey : null,
        yookassa_enabled: yookassaEnabled,
        manual_payment_enabled: manualEnabled,
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
    <div className="space-y-4">
      {/* Ручной перевод */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base">💰 Перевод на карту</CardTitle>
              <CardDescription className="mt-1">
                Покупатель переводит деньги на вашу карту вручную
              </CardDescription>
            </div>
            <Switch checked={manualEnabled} onCheckedChange={setManualEnabled} />
          </div>
        </CardHeader>
        {manualEnabled && (
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label>Номер карты</Label>
              <Input
                value={cardNumber}
                onChange={(e) => setCardNumber(e.target.value)}
                placeholder="2200 1234 5678 9010"
                className="font-mono"
              />
              <p className="text-xs text-muted-foreground">
                Поддерживаются буквы и пробелы — покупатель увидит как есть
              </p>
            </div>
            <div className="space-y-2">
              <Label>Получатель</Label>
              <Input
                value={recipientName}
                onChange={(e) => setRecipientName(e.target.value)}
                placeholder="Иван И."
              />
            </div>
            <details className="text-sm">
              <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                Как это работает для покупателя
              </summary>
              <div className="mt-2 space-y-1 rounded-md bg-muted p-3 text-xs leading-relaxed">
                <p>1. Покупатель выбирает «Перевод на карту» при оформлении заказа.</p>
                <p>2. Бот показывает номер карты, получателя и сумму.</p>
                <p>3. Покупатель делает перевод и нажимает «Я оплатил».</p>
                <p>4. Вы проверяете поступление и подтверждаете заказ в админке.</p>
              </div>
            </details>
          </CardContent>
        )}
      </Card>

      {/* ЮKassa */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base">🏦 ЮKassa</CardTitle>
              <CardDescription className="mt-1">
                Онлайн-оплата картой через ЮKassa (эквайринг)
              </CardDescription>
            </div>
            <Switch checked={yookassaEnabled} onCheckedChange={setYookassaEnabled} />
          </div>
        </CardHeader>
        {yookassaEnabled && (
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
                <p><b>Шаг 1.</b> Зарегистрируйтесь на{" "}
                  <a href="https://yookassa.ru" target="_blank" rel="noopener noreferrer"
                     className="text-blue-500 underline">
                    yookassa.ru
                  </a>{" "}и пройдите проверку (ИНН, реквизиты).</p>
                <p><b>Шаг 2.</b> В личном кабинете ЮKassa откройте раздел
                  «Интеграция» → «Настройки API».</p>
                <p><b>Шаг 3.</b> Скопируйте значения:</p>
                <ul className="ml-4 list-disc space-y-0.5">
                  <li><b>shopId</b> — номер магазина (вверху страницы)</li>
                  <li><b>Секретный ключ</b> — нажмите «Выпустить ключ»,
                    скопируйте значение целиком</li>
                </ul>
                <p><b>Шаг 4.</b> Вставьте оба значения в поля выше и нажмите «Сохранить».</p>
                <p className="text-muted-foreground">
                  После подключения покупатель сможет оплатить картой прямо в боте.
                  Деньги поступают на ваш счёт ЮKassa за вычетом комиссии (обычно 2.8%).
                </p>
              </div>
            </details>
          </CardContent>
        )}
      </Card>

      <div className="flex justify-end">
        <Button onClick={handleSave} disabled={saving}>
          <Save className="mr-2 h-4 w-4" />
          Сохранить
        </Button>
      </div>
    </div>
  );
}

function ThemeSettingsTab() {
  const { data, isLoading, mutate } = useSWR<ThemeSettings>("/settings/theme", fetcher);

  const [primaryColor, setPrimaryColor] = useState("");
  const [bgColor, setBgColor] = useState("");
  const [textColor, setTextColor] = useState("");
  const [buttonTextColor, setButtonTextColor] = useState("");
  const [secondaryBgColor, setSecondaryBgColor] = useState("");
  const [radius, setRadius] = useState("");
  const [fontFamily, setFontFamily] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (data) {
      setPrimaryColor(data.primary_color || "");
      setBgColor(data.bg_color || "");
      setTextColor(data.text_color || "");
      setButtonTextColor(data.button_text_color || "");
      setSecondaryBgColor(data.secondary_bg_color || "");
      setRadius(data.radius || "");
      setFontFamily(data.font_family || "");
    }
  }, [data]);

  async function handleSave() {
    setSaving(true);
    try {
      await api.put("/settings/theme", {
        primary_color: primaryColor,
        bg_color: bgColor,
        text_color: textColor,
        button_text_color: buttonTextColor,
        secondary_bg_color: secondaryBgColor,
        radius,
        font_family: fontFamily,
      });
      mutate();
      toast.success("Сохранено");
    } catch {
      toast.error("Ошибка");
    } finally {
      setSaving(false);
    }
  }

  function ColorField({
    label,
    value,
    onChange,
    placeholder,
  }: {
    label: string;
    value: string;
    onChange: (v: string) => void;
    placeholder: string;
  }) {
    return (
      <div className="space-y-1.5">
        <Label>{label}</Label>
        <div className="flex items-center gap-2">
          <input
            type="color"
            value={value || "#000000"}
            onChange={(e) => onChange(e.target.value)}
            className="h-9 w-9 shrink-0 cursor-pointer rounded-md border border-input bg-background p-0.5"
          />
          <Input
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={placeholder}
            className="flex-1 font-mono text-sm"
          />
          {value && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onChange("")}
              className="shrink-0 text-muted-foreground"
            >
              Сбросить
            </Button>
          )}
        </div>
      </div>
    );
  }

  if (isLoading) return <Skeleton className="h-48 w-full" />;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Цвета</CardTitle>
          <CardDescription>
            Оставьте поле пустым, чтобы использовать тему Telegram по умолчанию
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <ColorField
            label="Основной цвет (кнопки, акценты)"
            value={primaryColor}
            onChange={setPrimaryColor}
            placeholder="#3390ec"
          />
          <ColorField
            label="Фон"
            value={bgColor}
            onChange={setBgColor}
            placeholder="#ffffff"
          />
          <ColorField
            label="Текст"
            value={textColor}
            onChange={setTextColor}
            placeholder="#1a1a1a"
          />
          <ColorField
            label="Текст на кнопках"
            value={buttonTextColor}
            onChange={setButtonTextColor}
            placeholder="#ffffff"
          />
          <ColorField
            label="Фон карточек / секций"
            value={secondaryBgColor}
            onChange={setSecondaryBgColor}
            placeholder="#f5f5f5"
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Форма и шрифт</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>Скругление углов</Label>
            <Select value={radius} onValueChange={(v) => setRadius((v ?? "") === "__default__" ? "" : (v ?? ""))} items={{ "__default__": "По умолчанию", "0px": "Острые", "8px": "Маленькое", "14px": "Среднее", "20px": "Большое", "9999px": "Круглое" }}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder="По умолчанию" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__default__">По умолчанию</SelectItem>
                <SelectItem value="0px">Острые</SelectItem>
                <SelectItem value="8px">Маленькое</SelectItem>
                <SelectItem value="14px">Среднее</SelectItem>
                <SelectItem value="20px">Большое</SelectItem>
                <SelectItem value="9999px">Круглое</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Шрифт</Label>
            <Select value={fontFamily} onValueChange={(v) => setFontFamily((v ?? "") === "__default__" ? "" : (v ?? ""))} items={{ "__default__": "Системный (по умолчанию)", "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif": "Sans-serif", "Georgia, 'Times New Roman', serif": "Serif (Georgia)", "'Courier New', Courier, monospace": "Monospace", "'Comic Sans MS', 'Marker Felt', cursive": "Cursive" }}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Системный (по умолчанию)" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__default__">Системный (по умолчанию)</SelectItem>
                <SelectItem value="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif">Sans-serif</SelectItem>
                <SelectItem value="Georgia, 'Times New Roman', serif">Serif (Georgia)</SelectItem>
                <SelectItem value="'Courier New', Courier, monospace">Monospace</SelectItem>
                <SelectItem value="'Comic Sans MS', 'Marker Felt', cursive">Cursive</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button onClick={handleSave} disabled={saving}>
          <Save className="mr-2 h-4 w-4" />
          Сохранить
        </Button>
      </div>
    </div>
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

function ProductAttrsSettingsTab() {
  const { data, isLoading, mutate } = useSWR<ProductAttrsSettings>("/settings/product-attrs", fetcher);

  const [newLabel, setNewLabel] = useState("");
  const [adding, setAdding] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  async function handleAdd() {
    const label = newLabel.trim();
    if (!label) return;
    setAdding(true);
    try {
      await api.post("/settings/product-attrs", { label });
      setNewLabel("");
      mutate();
      toast.success("Характеристика добавлена");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Ошибка");
    } finally {
      setAdding(false);
    }
  }

  async function handleDelete(id: number) {
    setDeletingId(id);
    try {
      await api.delete(`/settings/product-attrs/${id}`);
      mutate();
      toast.success("Удалено");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Ошибка");
    } finally {
      setDeletingId(null);
    }
  }

  if (isLoading) return <Skeleton className="h-48 w-full" />;

  const attrs = data?.attrs ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Характеристики товаров</CardTitle>
        <CardDescription>
          Управляйте характеристиками, которые можно указать для вариантов товара.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <div className="flex flex-wrap gap-2">
            {attrs.map((attr: ProductAttrDef) => (
              <Badge key={attr.id} variant="default" className="gap-1 text-sm">
                {attr.label}
                <button
                  onClick={() => handleDelete(attr.id)}
                  disabled={deletingId === attr.id}
                  className="ml-1 hover:text-red-400 disabled:opacity-50"
                >
                  ×
                </button>
              </Badge>
            ))}
          </div>
        </div>

        <div className="flex gap-2">
          <Input
            value={newLabel}
            onChange={(e) => setNewLabel(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAdd()}
            placeholder="Название характеристики (например: Цвет, Вес, Материал)"
            disabled={adding}
          />
          <Button onClick={handleAdd} disabled={adding || !newLabel.trim()}>
            Добавить
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function ShopNameSettings() {
  const { data, isLoading, mutate } = useSWR<ShopInfo>("/settings/shop", fetcher);

  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (data) {
      setName(data.name || "");
    }
  }, [data]);

  async function handleSave() {
    setSaving(true);
    try {
      await api.put("/settings/shop", { name });
      mutate();
      toast.success("Название магазина обновлено");
      setTimeout(() => window.location.reload(), 800);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Ошибка");
    } finally {
      setSaving(false);
    }
  }

  if (isLoading) return <Skeleton className="h-48 w-full" />;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Название магазина</CardTitle>
        <CardDescription>
          Отображается в боковом меню админ-панели. Новые магазили задают название при онбординге.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label>Название</Label>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Например: Свечи Варвара"
            maxLength={100}
          />
        </div>

        <div className="flex justify-end">
          <Button onClick={handleSave} disabled={saving || !name.trim()}>
            <Save className="mr-2 h-4 w-4" />
            Сохранить
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function CompanyInfoSettings() {
  const { data, isLoading, mutate } = useSWR<CompanyInfo>("/settings/company", fetcher);

  const [name, setName] = useState("");
  const [inn, setInn] = useState("");
  const [address, setAddress] = useState("");
  const [legalType, setLegalType] = useState("individual");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (data) {
      setName(data.company_name || "");
      setInn(data.company_inn || "");
      setAddress(data.company_address || "");
      setLegalType(data.legal_type || "individual");
    }
  }, [data]);

  async function handleSave() {
    setSaving(true);
    try {
      await api.put("/settings/company", {
        company_name: name || null,
        company_inn: inn || null,
        company_address: address || null,
        legal_type: legalType,
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
        <CardTitle className="text-base">Реквизиты</CardTitle>
        <CardDescription>
          Подставляются в документы: политику конфиденциальности, согласие,
          условия заказа, поручение на обработку ПДн и уведомление Роскомнадзора
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label>Правовая форма</Label>
          <Select value={legalType} onValueChange={(v) => setLegalType(v || "individual")} items={{ individual: "Физическое лицо", ip: "Индивидуальный предприниматель", ooo: "Общество с ограниченной ответственностью" }}>
            <SelectTrigger className="w-full">
              <SelectValue placeholder="Выберите правовую форму" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="individual">Физическое лицо</SelectItem>
              <SelectItem value="ip">Индивидуальный предприниматель</SelectItem>
              <SelectItem value="ooo">Общество с ограниченной ответственностью</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label>Наименование (ИП / ООО / ФИО)</Label>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="ИП Иванов Иван Иванович"
          />
        </div>
        <div className="space-y-2">
          <Label>ИНН</Label>
          <Input
            value={inn}
            onChange={(e) => setInn(e.target.value)}
            placeholder="324301224122"
          />
        </div>
        <div className="space-y-2">
          <Label>Юридический адрес</Label>
          <Textarea
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            rows={3}
            placeholder="Московская область, Ленинский район, ..."
          />
        </div>

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

function LegalDocsSettings() {
  const { data: docs, isLoading, mutate } = useSWR<LegalDocument[]>("/settings/legal-documents", fetcher);
  const { data: rknInfo } = useSWR<RoskomnadzorInfo>("/settings/roskomnadzor", fetcher);

  const [addendums, setAddendums] = useState<Record<string, string>>({});
  const [savingType, setSavingType] = useState<string | null>(null);
  const [downloadingRkn, setDownloadingRkn] = useState(false);

  useEffect(() => {
    if (docs) {
      const map: Record<string, string> = {};
      for (const doc of docs) {
        map[doc.document_type] = doc.seller_addendum || "";
      }
      setAddendums(map);
    }
  }, [docs]);

  async function handleSaveAddendum(docType: string) {
    setSavingType(docType);
    try {
      await api.put(`/settings/legal-documents/${docType}`, {
        seller_addendum: addendums[docType] || null,
      });
      mutate();
      toast.success("Сохранено");
    } catch {
      toast.error("Ошибка");
    } finally {
      setSavingType(null);
    }
  }

  async function handleDownloadRkn() {
    setDownloadingRkn(true);
    try {
      const { blob, filename } = await api.download("/settings/roskomnadzor/draft");
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast.success("Черновик скачан");
    } catch {
      toast.error("Ошибка загрузки");
    } finally {
      setDownloadingRkn(false);
    }
  }

  if (isLoading) return <Skeleton className="h-48 w-full" />;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Правовые документы</CardTitle>
          <CardDescription>
            Системный шаблон формируется из реквизитов автоматически (вкладка «Реквизиты»).
            Ниже каждого шаблона можно добавить дополнительные условия продавца.
          </CardDescription>
        </CardHeader>
      </Card>

      {docs?.map((doc) => (
        <Card key={doc.document_type}>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">{doc.title}</CardTitle>
              {doc.is_read_only ? (
                <Badge variant="secondary" className="gap-1">
                  <Lock className="h-3 w-3" />
                  формируется автоматически
                </Badge>
              ) : (
                <Badge variant="outline">редактируемое дополнение</Badge>
              )}
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <Label className="text-xs text-muted-foreground">Системный шаблон</Label>
              <Textarea
                value={doc.system_template}
                readOnly
                rows={8}
                className="mt-1 bg-muted font-mono text-xs"
              />
            </div>

            {!doc.is_read_only && (
              <div>
                <Label className="text-xs text-muted-foreground">
                  Дополнительные условия продавца
                </Label>
                <Textarea
                  value={addendums[doc.document_type] ?? ""}
                  onChange={(e) =>
                    setAddendums((prev) => ({
                      ...prev,
                      [doc.document_type]: e.target.value,
                    }))
                  }
                  rows={4}
                  className="mt-1 font-mono text-sm"
                  placeholder="Необязательно. Текст будет добавлен после системного шаблона."
                />
                <div className="mt-2 flex justify-end">
                  <Button
                    size="sm"
                    onClick={() => handleSaveAddendum(doc.document_type)}
                    disabled={savingType === doc.document_type}
                  >
                    <Save className="mr-2 h-3 w-3" />
                    {savingType === doc.document_type ? "Сохранение..." : "Сохранить"}
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      ))}

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Info className="h-4 w-4 text-muted-foreground" />
            <CardTitle className="text-base">
              Обработка персональных данных — уведомление в Роскомнадзор
            </CardTitle>
          </div>
          <CardDescription className="whitespace-pre-line">
            {rknInfo?.info}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {rknInfo && (
            <div className="rounded-md bg-muted p-3 text-xs leading-relaxed">
              <p>
                <span className="text-muted-foreground">Оператор:</span>{" "}
                {LEGAL_TYPE_LABELS[rknInfo.legal_type] || rknInfo.legal_type}
                {rknInfo.company_name ? ` ${rknInfo.company_name}` : ""}
              </p>
              {rknInfo.company_inn && (
                <p>
                  <span className="text-muted-foreground">ИНН:</span>{" "}
                  {rknInfo.company_inn}
                </p>
              )}
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleDownloadRkn}
              disabled={downloadingRkn}
            >
              <Download className="mr-2 h-3 w-3" />
              {downloadingRkn ? "Загрузка..." : "Скачать черновик уведомления"}
            </Button>
            {rknInfo && (
              <a
                href={rknInfo.official_url}
                target="_blank"
                rel="noopener noreferrer"
                className={buttonVariants({ variant: "ghost", size: "sm" })}
              >
                <ExternalLink className="mr-2 h-3 w-3" />
                Подать в Роскомнадзор
              </a>
            )}
          </div>
          <p className="text-xs text-muted-foreground">
            Черновик формируется из реквизитов. Заполните реквизиты и скачайте
            готовый текст для подачи через портал Роскомнадзора.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
