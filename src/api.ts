export type Role = "admin" | "donor" | "recipient" | "volunteer";
export type User = { id: number; name: string; email: string; role: Role; organization_id?: number };
export type Listing = {
  id: number;
  title: string;
  category: string;
  portions: number;
  status: string;
  pickup_deadline: string;
  donor_name?: string;
  latitude?: number | null;
  longitude?: number | null;
};
export type Match = {
  match_id: number;
  listing_id: number;
  request_id: number;
  listing_title: string;
  recipient_name: string;
  score: number;
  explanation: string;
  portions: number;
};
export type NetworkSnapshot = {
  locations: { id: string; name: string; kind: "donor" | "recipient" | "volunteer"; latitude: number; longitude: number }[];
  routes: { id: number; points: [number, number][] }[];
};
export type Delivery = {
  id: number;
  status: string;
  volunteer_user_id: number | null;
  listing_id: number;
  request_id: number;
  listing_title: string;
  recipient_name: string;
  donor_latitude: number | null;
  donor_longitude: number | null;
  recipient_latitude: number | null;
  recipient_longitude: number | null;
  proof_uploaded: boolean;
};
export type PendingOrganization = { id: number; name: string; kind: string; verification_status: string; created_at: string };
export type AdminMetrics = {
  meals_saved: number;
  recipient_organizations_supported: number;
  completed_deliveries: number;
  rescinded_deliveries: number;
  safety_rejections: number;
  pending_verifications: number;
};

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem("foodbridge-token");
  const response = await fetch(`${API_BASE}/api${path}`, {
    ...init,
    headers: {
      ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(data.detail ?? `Request failed (${response.status})`);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

export function socketUrl(): string {
  const base = API_BASE || window.location.origin;
  const url = new URL("/ws/updates", base);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  const token = localStorage.getItem("foodbridge-token");
  if (token) url.searchParams.set("token", token);
  return url.toString();
}
