export function formatPrice(amount: number): string {
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 0,
  }).format(amount);
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export const STATUS_COLORS: Record<string, string> = {
  new: "bg-blue-100 text-blue-800",
  confirmed: "bg-amber-100 text-amber-800",
  paid: "bg-green-100 text-green-800",
  shipped: "bg-purple-100 text-purple-800",
  done: "bg-gray-100 text-gray-800",
  cancelled: "bg-red-100 text-red-800",
};

export const STATUS_LABELS: Record<string, string> = {
  new: "🆕 Новый",
  confirmed: "✅ Подтверждён",
  paid: "💰 Оплачен",
  shipped: "🚚 Отправлен",
  done: "🏁 Выполнен",
  cancelled: "❌ Отменён",
};
