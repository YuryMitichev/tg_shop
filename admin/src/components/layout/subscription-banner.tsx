"use client";

import Link from "next/link";
import { AlertTriangle } from "lucide-react";

export function SubscriptionBanner() {
  return (
    <div className="mb-6 flex items-center gap-3 rounded-lg border border-orange-300 bg-orange-50 px-4 py-3 text-orange-900 dark:border-orange-900 dark:bg-orange-950 dark:text-orange-200">
      <AlertTriangle className="h-5 w-5 shrink-0" />
      <div className="flex-1">
        <p className="text-sm font-medium">
          Подписка истекла — доступны только заказы и клиенты
        </p>
      </div>
      <Link
        href="/settings"
        className="shrink-0 rounded-md bg-orange-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-orange-700"
      >
        Продлить
      </Link>
    </div>
  );
}
