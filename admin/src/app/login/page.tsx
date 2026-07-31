"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { api, setToken } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Loader2, Lock } from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const [step, setStep] = useState<"id" | "code">("id");
  const [telegramId, setTelegramId] = useState("");
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);

  async function sendCode(e: React.FormEvent) {
    e.preventDefault();

    if (!telegramId.trim()) {
      toast.error("Введите ваш Telegram ID");
      return;
    }

    setLoading(true);

    try {
      const res = await api.post<{ ok: boolean; error?: string }>("/auth/request-code", {
        telegram_user_id: Number(telegramId),
      });

      if (!res.ok) {
        toast.error(res.error || "Пользователь не является администратором");
        return;
      }

      setStep("code");
      toast.success("Код отправлен в Telegram");
    } catch {
      toast.error("Ошибка запроса");
    } finally {
      setLoading(false);
    }
  }

  async function verifyCode(e: React.FormEvent) {
    e.preventDefault();

    if (!code.trim()) {
      toast.error("Введите код");
      return;
    }

    setLoading(true);

    try {
      const res = await api.post<{ ok: boolean; token?: string; error?: string }>("/auth/verify", {
        telegram_user_id: Number(telegramId),
        code,
      });

      if (!res.ok || !res.token) {
        toast.error(res.error || "Неверный код");
        return;
      }

      setToken(res.token);
      toast.success("Вход выполнен");
      router.push("/dashboard");
    } catch {
      toast.error("Ошибка запроса");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <div className="mx-auto mb-2 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
            <Lock className="h-6 w-6 text-primary" />
          </div>
          <CardTitle className="text-2xl">Админ-панель</CardTitle>
          <CardDescription>
            {step === "id"
              ? "Введите ваш Telegram ID для получения кода"
              : "Введите код из Telegram"}
          </CardDescription>
        </CardHeader>

        <CardContent>
          {step === "id" ? (
            <form onSubmit={sendCode} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="tg-id">Telegram ID</Label>
                <Input
                  id="tg-id"
                  type="number"
                  placeholder="Например: 123456789"
                  value={telegramId}
                  onChange={(e) => setTelegramId(e.target.value)}
                  disabled={loading}
                />
                <p className="text-xs text-muted-foreground">
                  Узнать свой ID: @userinfobot в Telegram
                </p>
              </div>

              <Button type="submit" className="w-full" disabled={loading}>
                {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Получить код
              </Button>
            </form>
          ) : (
            <form onSubmit={verifyCode} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="code">Код подтверждения</Label>
                <Input
                  id="code"
                  type="text"
                  placeholder="000000"
                  maxLength={6}
                  className="text-center text-2xl tracking-widest"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  disabled={loading}
                />
              </div>

              <Button type="submit" className="w-full" disabled={loading}>
                {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Войти
              </Button>

              <Button
                type="button"
                variant="ghost"
                className="w-full"
                onClick={() => {
                  setStep("id");
                  setCode("");
                }}
                disabled={loading}
              >
                Назад
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
