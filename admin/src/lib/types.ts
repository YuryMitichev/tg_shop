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
