"use client";

import { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { api, setToken } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Loader2, Lock, CheckCircle2 } from "lucide-react";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const tokenFromUrl = searchParams.get("token");

  const [step, setStep] = useState<"id" | "waiting" | "verifying">("id");
  const [telegramId, setTelegramId] = useState("");
  const [loading, setLoading] = useState(false);
  const [verifyError, setVerifyError] = useState<string | null>(null);

  useEffect(() => {
    if (tokenFromUrl) {
      setStep("verifying");
      verifyToken(tokenFromUrl);
    } else {
      api
        .get("/auth/me")
        .then(() => router.replace("/dashboard"))
        .catch(() => {});
    }
  }, [tokenFromUrl, router]);

  async function verifyToken(t: string) {
    try {
      const res = await api.post<{ ok: boolean; token?: string; error?: string }>(
        "/auth/verify-token",
        { token: t },
      );

      if (!res.ok) {
        setVerifyError(res.error || "Ссылка недействительна или истекла");
        setStep("id");
        return;
      }

      if (res.token) {
        setToken(res.token);
      }

      router.push("/dashboard");
    } catch {
      setVerifyError("Ошибка запроса");
      setStep("id");
    }
  }

  async function sendLink(e: React.FormEvent) {
    e.preventDefault();

    if (!telegramId.trim()) {
      toast.error("Введите ваш Telegram ID");
      return;
    }

    setLoading(true);

    try {
      const res = await api.post<{ ok: boolean; error?: string }>(
        "/auth/request-login",
        { telegram_user_id: Number(telegramId), panel_url: window.location.origin },
      );

      if (!res.ok) {
        toast.error(res.error || "Пользователь не является администратором");
        return;
      }

      setStep("waiting");
    } catch {
      toast.error("Слишком много попыток. Попробуйте позже.");
    } finally {
      setLoading(false);
    }
  }

  if (step === "verifying") {
    return (
      <div className="flex min-h-screen items-center justify-center p-4">
        <Card className="w-full max-w-md">
          <CardContent className="flex flex-col items-center gap-4 py-12">
            <Loader2 className="h-10 w-10 animate-spin text-primary" />
            <p className="text-muted-foreground">Проверка ссылки...</p>
          </CardContent>
        </Card>
      </div>
    );
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
              ? "Введите ваш Telegram ID для получения ссылки"
              : "Ссылка отправлена в Telegram"}
          </CardDescription>
        </CardHeader>

        <CardContent>
          {verifyError && (
            <div className="mb-4 rounded-md bg-destructive/10 p-3 text-center text-sm text-destructive">
              {verifyError}
            </div>
          )}

          {step === "id" ? (
            <form onSubmit={sendLink} className="space-y-4">
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
                Отправить ссылку для входа
              </Button>
            </form>
          ) : (
            <div className="space-y-4">
              <div className="flex flex-col items-center gap-3 py-6 text-center">
                <CheckCircle2 className="h-12 w-12 text-green-500" />
                <p className="text-sm text-muted-foreground">
                  Мы отправили ссылку для входа в Telegram.
                  <br />
                  Нажмите на неё, чтобы войти.
                </p>
                <p className="text-xs text-muted-foreground">
                  Ссылка действует 5 минут.
                </p>
              </div>

              <Button
                type="button"
                variant="ghost"
                className="w-full"
                onClick={() => {
                  setStep("id");
                  setVerifyError(null);
                }}
              >
                Назад
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}
