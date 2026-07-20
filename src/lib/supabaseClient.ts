import { createClient, type SupabaseClient } from "@supabase/supabase-js";

let supabaseBrowserClient: SupabaseClient | null = null;

function normalizeSupabaseUrl(url: string) {
  return url.replace(/\/rest\/v1\/?$/, "").replace(/\/$/, "");
}

export function getSupabaseBrowserClient() {
  if (supabaseBrowserClient) {
    return supabaseBrowserClient;
  }

  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!supabaseUrl || !supabaseAnonKey) {
    return null;
  }

  supabaseBrowserClient = createClient(normalizeSupabaseUrl(supabaseUrl), supabaseAnonKey);
  return supabaseBrowserClient;
}