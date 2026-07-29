"use client";

import { useEffect, useState } from "react";
import { getSupabaseBrowserClient } from "@/lib/supabaseClient";
import type { Profile } from "@/types/profile";

type AuthenticatedProfileState = {
  displayName: string;
  userEmail: string | null;
  notice: string | null;
};

const initialState: AuthenticatedProfileState = {
  displayName: "Usuário",
  userEmail: null,
  notice: null
};

export function useAuthenticatedProfile() {
  const [state, setState] = useState<AuthenticatedProfileState>(initialState);

  useEffect(() => {
    let isMounted = true;

    async function loadProfile() {
      try {
        const supabase = getSupabaseBrowserClient();

        if (!supabase) {
          if (isMounted) {
            setState({
              displayName: "Usuário",
              userEmail: null,
              notice: "Não foi possível carregar o perfil porque a configuração do Supabase está ausente."
            });
          }
          return;
        }

        const { data: userData, error: userError } = await supabase.auth.getUser();
        const user = userData.user;

        if (!user || userError) {
          if (isMounted) {
            setState({
              displayName: "Usuário",
              userEmail: null,
              notice: "Não foi possível identificar o usuário autenticado para carregar o perfil."
            });
          }
          return;
        }

        const userEmail = user.email ?? null;
        const { data: profile, error: profileError } = await supabase
          .from("profiles")
          .select("id, nome, email, role")
          .eq("id", user.id)
          .maybeSingle<Profile>();

        if (!isMounted) {
          return;
        }

        if (profileError) {
          setState({
            displayName: userEmail ?? "Usuário",
            userEmail,
            notice: "Não foi possível carregar seu perfil agora. Você pode continuar usando as ferramentas com sua conta autenticada."
          });
          return;
        }

        setState({
          displayName: profile?.nome?.trim() || userEmail || "Usuário",
          userEmail,
          notice: profile
            ? null
            : "Seu perfil ainda não foi cadastrado. Exibimos seu e-mail enquanto o cadastro não é concluído."
        });
      } catch {
        if (isMounted) {
          setState({
            displayName: "Usuário",
            userEmail: null,
            notice: "Não foi possível carregar seu perfil agora. Você pode continuar usando as ferramentas com sua conta autenticada."
          });
        }
      }
    }

    loadProfile();

    return () => {
      isMounted = false;
    };
  }, []);

  return state;
}
