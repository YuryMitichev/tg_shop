"use client";

import { createContext, useContext, ReactNode } from "react";

interface SubscriptionState {
  subscriptionActive: boolean;
}

const SubscriptionContext = createContext<SubscriptionState>({
  subscriptionActive: true,
});

export function SubscriptionProvider({
  children,
  subscriptionActive,
}: {
  children: ReactNode;
  subscriptionActive: boolean;
}) {
  return (
    <SubscriptionContext.Provider value={{ subscriptionActive }}>
      {children}
    </SubscriptionContext.Provider>
  );
}

export function useSubscription(): SubscriptionState {
  return useContext(SubscriptionContext);
}

const BLOCKED_ROUTES = [
  "/products",
  "/categories",
  "/broadcasts",
  "/analytics",
  "/promos",
  "/reviews",
  "/admins",
  "/settings",
];

export function isRouteBlocked(pathname: string): boolean {
  return BLOCKED_ROUTES.some(
    (route) => pathname === route || pathname.startsWith(route + "/"),
  );
}
