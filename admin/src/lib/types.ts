export interface Category {
  id: number;
  name: string;
  emoji: string | null;
}

export interface Variant {
  id?: number;
  volume: string;
  price: number;
  burn?: string | null;
  stock?: number;
  size?: string | null;
  color?: string | null;
  scent?: string | null;
  dimensions?: string | null;
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
  variants: Variant[];
  photos: Photo[];
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

export interface ProductAttrOption {
  key: string;
  label: string;
}

export interface ProductAttrsSettings {
  product_attrs: string[];
  available: ProductAttrOption[];
}

export interface CompanyInfo {
  company_name: string | null;
  company_inn: string | null;
  company_address: string | null;
}

export interface ShopInfo {
  name: string | null;
}

export interface Stats {
  total_orders: number;
  new_orders: number;
  cancelled_orders: number;
  total_revenue: number;
  month_revenue: number;
  top_products: { name: string; quantity: number; revenue: number }[];
}

export interface RevenueChartItem {
  date: string;
  revenue: number;
  orders: number;
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
  product_attrs: string[];
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
