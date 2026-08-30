"use client";

import useSWR from "swr";
import { superAdminFetcher } from "@/lib/swr";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Check } from "lucide-react";
import { formatPrice } from "@/lib/format";
import type { SubscriptionPlanAdmin } from "@/lib/types";

export default function PlansPage() {
  const { data, isLoading } = useSWR<{ plans: SubscriptionPlanAdmin[] }>(
    "/plans",
    superAdminFetcher,
  );
  const plans = data?.plans ?? [];

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Тарифы</h1>
        <p className="text-sm text-muted-foreground">
          Тарифы зафиксированы: 14 дней бесплатно, затем 1 299 ₽ в месяц
          или 3 507,30 ₽ за 3 месяца со скидкой 10%.
        </p>
      </div>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2">
          {[...Array(3)].map((_, index) => (
            <Skeleton key={index} className="h-48" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {plans.map((plan) => (
            <PlanCard key={plan.id} plan={plan} />
          ))}
        </div>
      )}
    </div>
  );
}

function PlanCard({ plan }: { plan: SubscriptionPlanAdmin }) {
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
            {plan.features.slice(0, 5).map((feature, index) => (
              <li
                key={index}
                className="flex items-start gap-2 text-xs text-muted-foreground"
              >
                <Check className="mt-0.5 h-3 w-3 shrink-0 text-green-500" />
                {feature}
              </li>
            ))}
            {plan.features.length > 5 && (
              <li className="text-xs text-muted-foreground">
                +{plan.features.length - 5} ещё
              </li>
            )}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
