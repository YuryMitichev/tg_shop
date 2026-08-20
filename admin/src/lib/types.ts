export interface Category {
  id: number;
  name: string;
  emoji: string | null;
}

export interface Variant {
  id?: number;
  volume: string;
  price: number;
  stock?: number;
  attributes?: Record<string, string>;
}

export interface Photo {
  id: number;
  file_id: string;
  position: number;
}

export interface Product {
  id: number;
  category_id: number;
  category_name?: string;
  name: string;
  description: string;
  is_active: boolean;
  total_stock: number;
  lifecycle_status:
    | "in_stock"
    | "out_of_stock_visible"
    | "out_of_stock_hidden"
    | "out_of_stock_manual_hidden";
  out_of_stock_since?: string | null;
  auto_hidden_at?: string | null;
  auto_hide_at?: string | null;
  auto_delete_at?: string | null;
  variants: Variant[];
  photos: Photo[];
}

export interface ProductsResponse {
  products: Product[];
  total: number;
  page: number;
  per_page: number;
}

export interface Order {
  id: number;
  status: string;
  full_name: string;
  phone: string;
  total_amount: number;
  promo_code?: string | null;
  discount_amount?: number;
  created_at?: string;
  telegram_user_id?: number;
}

export interface OrderDetail extends Order {
  address?: string;
  comment?: string | null;
  items?: OrderItem[];
}

export interface OrderItem {
  product_name: string;
  variant_volume: string;
  price: number;
  quantity: number;
}

export interface User {
  telegram_user_id: number;
  full_name: string;
  phone: string;
  orders_count: number;
  total_spent: number;
  last_order: string | null;
}

export interface CrmUser {
  telegram_user_id: number;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  full_name: string;
  phone: string | null;
  notes: string | null;
  tags: string[];
  created_at: string | null;
  last_seen: string | null;
  orders_count: number;
  total_spent: number;
  last_order: string | null;
}

export interface CrmUserDetail extends CrmUser {
  avg_order_value: number;
  orders: CrmOrder[];
  favorite_products: { name: string; quantity: number }[];
}

export interface CrmOrder {
  id: number;
  status: string;
  total_amount: number;
  promo_code: string | null;
  discount_amount: number;
  created_at: string | null;
  items_count: number;
}

export interface CrmMessage {
  id: number;
  direction: string;
  message_type: string;
  text: string | null;
  admin_id: number | null;
  created_at: string;
}

export interface CrmMessagesResponse {
  messages: CrmMessage[];
  total: number;
  page: number;
  per_page: number;
}

export interface CrmUsersResponse {
  users: CrmUser[];
  total: number;
  page: number;
  per_page: number;
}

export interface Promo {
  id: number;
  code: string;
  discount_type: string;
  discount_value: number;
  max_uses: number | null;
  used_count: number;
  is_active: boolean;
  valid_until?: string | null;
}

export interface Review {
  id: number;
  product_id: number;
  product_name: string | null;
  telegram_user_id: number;
  rating: number;
  text: string | null;
  created_at: string;
}

export interface SystemMessage {
  key: string;
  label: string;
  content: string;
  is_default: boolean;
}

export interface DeliverySettings {
  delivery_enabled: boolean;
  courier_services: string[];
  available_couriers: string[];
}

export interface ProductAttrDef {
  id: number;
  key: string;
  label: string;
  position: number;
  is_required: boolean;
}

export interface ProductAttrsSettings {
  attrs: ProductAttrDef[];
}

export interface CompanyInfo {
  company_name: string | null;
  company_inn: string | null;
  company_address: string | null;
  legal_type: string;
}

export interface LegalDocument {
  document_type: string;
  title: string;
  system_template: string;
  seller_addendum: string | null;
  text: string;
  is_read_only: boolean;
}

export interface RoskomnadzorInfo {
  legal_type: string;
  company_name: string | null;
  company_inn: string | null;
  info: string;
  official_url: string;
}

export interface ShopInfo {
  name: string | null;
}

export interface ThemeSettings {
  primary_color: string | null;
  bg_color: string | null;
  text_color: string | null;
  button_text_color: string | null;
  secondary_bg_color: string | null;
  radius: string | null;
  font_family: string | null;
  price_color: string | null;
  price_size: string | null;
  price_weight: string | null;
}

export interface Stats {
  total_orders: number;
  new_orders: number;
  paid_orders: number;
  cancelled_orders: number;
  payment_conversion_rate: number;
  total_revenue: number;
  month_revenue: number;
  top_products: { name: string; quantity: number; revenue: number }[];
}

export interface RevenueChartItem {
  date: string;
  revenue: number;
  orders: number;
  created_orders: number;
  paid_orders: number;
  cancelled_orders: number;
}

export interface StatusOption {
  value: string;
  label: string;
}

export interface AnalyticsOverview {
  revenue: number;
  revenue_growth: number;
  orders: number;
  orders_growth: number;
  created_orders: number;
  paid_orders: number;
  paid_orders_growth: number;
  cancelled_orders: number;
  order_to_payment_rate: number;
  avg_order_value: number;
  aov_growth: number;
  unique_customers: number;
  customers_growth: number;
  completed_orders: number;
  completion_rate: number;
  repeat_customers: number;
  repeat_rate: number;
  avg_items_per_order: number;
}

export interface PublicationAnalyticsPost {
  post_id: number;
  telegram_message_id: number;
  published_at: string | null;
  text: string;
  channel_title: string;
  post_url: string | null;
  media_id: number | null;
  products: string[];
  views: number;
  forwards: number;
  views_updated_at: string | null;
  opens: number;
  total_opens: number;
  cart_adds: number;
  total_cart_adds: number;
  paid_orders: number;
  units_sold: number;
  revenue: number;
  ctr: number;
  purchase_conversion: number;
}

export interface PublicationAnalyticsReport {
  summary: {
    views: number;
    opens: number;
    cart_adds: number;
    paid_orders: number;
    revenue: number;
    ctr: number;
    purchase_conversion: number;
  };
  posts: PublicationAnalyticsPost[];
}

export interface CategoryStat {
  id: number;
  name: string;
  emoji: string | null;
  revenue: number;
  quantity: number;
}

export interface ProductStat {
  name: string;
  quantity: number;
  revenue: number;
}

export interface CustomerStats {
  new_customers: number;
  returning_customers: number;
  total_customers: number;
  ltv: number;
  top_customers: { name: string; orders: number; spent: number }[];
}

export interface PromoStats {
  total_discount: number;
  orders_with_promo: number;
  orders_without_promo: number;
  top_promos: { code: string; uses: number; discount: number }[];
}

export interface ReviewStats {
  avg_rating: number;
  total_reviews: number;
  distribution: Record<string, number>;
}

export interface Admin {
  id: number;
  telegram_user_id: number;
  display_name: string | null;
  role: "owner" | "manager" | "content" | "support";
  created_at: string | null;
  is_super: boolean;
}

export interface Broadcast {
  id: number;
  product_id: number;
  product_name: string;
  variant_id: number | null;
  variant_volume: string | null;
  original_price: number;
  discount_percent: number;
  discounted_price: number;
  message_text: string | null;
  filter_tags: string[];
  status: string;
  recipients_count: number;
  sent_count: number;
  failed_count: number;
  created_by: number | null;
  created_at: string | null;
  completed_at: string | null;
  expires_at: string | null;
}

export interface BroadcastsResponse {
  broadcasts: Broadcast[];
  total: number;
  page: number;
  per_page: number;
}

export interface PreviewRecipientsResponse {
  recipients_count: number;
}

export interface BroadcastProduct {
  id: number;
  name: string;
  variants: Variant[];
}

export interface BroadcastTagsResponse {
  tags: string[];
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

export interface PlatformStats {
  total_shops: number;
  active_shops: number;
  trial_shops: number;
  expired_shops: number;
  new_shops_30d: number;
  total_revenue: number;
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
