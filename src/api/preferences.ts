import { supabase } from "../lib/supabaseClient";

export type AppUser = {
  user_id: string;
  first_name: string;
  email: string;
  created_at: string;
};

export type Preference = {
  preference_id: number;
  user_id: string;
  created_at: string;
  dietary_restrictions: string | null;
  dining_preference: string | null;
};

export async function createUser(input: {
  firstName: string;
  email: string;
}): Promise<AppUser> {
  const { data, error } = await supabase
    .from("app_user")
    .insert({
      first_name: input.firstName,
      email: input.email,
    })
    .select("*")
    .single();

  if (error) throw error;
  return data as AppUser;
}

export async function createPreference(input: {
  userId: string;
  dietaryRestrictions?: string;
  diningPreference?: string;
}): Promise<Preference> {
  const { data, error } = await supabase
    .from("preference")
    .insert({
      user_id: input.userId,
      dietary_restrictions: input.dietaryRestrictions ?? null,
      dining_preference: input.diningPreference ?? null,
    })
    .select("*")
    .single();

  if (error) throw error;
  return data as Preference;
}

export async function fetchPreferencesByUserId(userId: string): Promise<Preference[]> {
  const { data, error } = await supabase
    .from("preference")
    .select("*")
    .eq("user_id", userId)
    .order("created_at", { ascending: false });

  if (error) throw error;
  return (data ?? []) as Preference[];
}

