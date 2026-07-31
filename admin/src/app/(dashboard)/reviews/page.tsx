"use client";

import useSWR from "swr";
import { fetcher } from "@/lib/swr";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Star, Trash2 } from "lucide-react";
import { formatDate } from "@/lib/format";
import type { Review } from "@/lib/types";

function StarRating({ rating }: { rating: number }) {
  return (
    <div className="flex">
      {[1, 2, 3, 4, 5].map((i) => (
        <Star
          key={i}
          className={`h-4 w-4 ${
            i <= rating
              ? "fill-amber-400 text-amber-400"
              : "fill-muted text-muted-foreground"
          }`}
        />
      ))}
    </div>
  );
}

export default function ReviewsPage() {
  const { data: reviews, isLoading, mutate } = useSWR<Review[]>("/reviews", fetcher);

  async function remove(id: number) {
    try {
      await api.delete(`/reviews/${id}`);
      mutate();
      toast.success("Отзыв удалён");
    } catch {
      toast.error("Ошибка");
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold">Отзывы</h1>
        <div className="space-y-3">
          {[...Array(4)].map((_, i) => (
            <Skeleton key={i} className="h-28 w-full rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Отзывы</h1>

      {reviews?.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12 text-muted-foreground">
            <Star className="mb-2 h-8 w-8 opacity-50" />
            <p>Нет отзывов</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {reviews?.map((review) => (
            <Card key={review.id}>
              <CardContent className="space-y-2 py-4">
                <div className="flex items-start justify-between">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <StarRating rating={review.rating} />
                      {review.product_name && (
                        <Badge variant="outline">{review.product_name}</Badge>
                      )}
                    </div>
                    {review.text && (
                      <p className="text-sm">{review.text}</p>
                    )}
                    <div className="flex items-center gap-3 text-xs text-muted-foreground">
                      <span>ID: {review.telegram_user_id}</span>
                      <span>{formatDate(review.created_at)}</span>
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => remove(review.id)}
                  >
                    <Trash2 className="h-3 w-3 text-red-500" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
