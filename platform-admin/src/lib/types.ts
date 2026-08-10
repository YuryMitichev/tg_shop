export interface PlatformStats {
  total_shops: number;
  active_shops: number;
  trial_shops: number;
  expired_shops: number;
  new_shops_30d: number;
  total_revenue: number;
}

export interface ShopManagement {
  id: number;
  name: string;
  bot_token_masked: string;
  owner_telegram_id: number;
  is_active: boolean;
  delivery_enabled: boolean;
  courier_services: string[];
  company_name: string | null;
  company_inn: string | null;
  company_address: string | null;
  payment_card_number: string | null;
  payment_recipient_name: string | null;
  yookassa_shop_id: string | null;
  yookassa_secret_key_masked: string | null;
  yookassa_enabled: boolean;
  manual_payment_enabled: boolean;
  created_at: string | null;
}

export interface PlatformSubscription {
  id: number;
  shop_id: number;
  shop_name: string;
  plan_name: string;
  plan_price: number;
  is_trial: boolean;
  status: string;
  started_at: string | null;
  expires_at: string;
  external_payment_id: string | null;
}

export interface SubscriptionPlanAdmin {
  id: number;
  name: string;
  description: string | null;
  price: number;
  duration_days: number;
  is_trial: boolean;
  is_active: boolean;
  features: string[];
}

export interface PlatformPaymentSettings {
  yookassa_shop_id: string | null;
  yookassa_secret_key_masked: string | null;
  yookassa_enabled: boolean;
}
