"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getSupabaseBrowserClient } from "@/lib/supabaseClient";

type AuthGuardProps = {
  children: React.ReactNode;
};

export function AuthGuard({ children }: AuthGuardProps) {
  const router = useRouter();
  const [isChecking, setIsChecking] = useState(true);

  useEffect(() => {
    let isMounted = true;
    const supabase = getSupabaseBrowserClient();

    if (!supabase) {
      setIsChecking(false);
      return;
    }

    const supabaseClient = supabase;

    async function ensureSession() {
      const { data } = await supabaseClient.auth.getSession();

      if (!isMounted) {
        return;
      }

      if (!data.session) {
        router.replace("/login");
        return;
      }

      setIsChecking(false);
    }

    ensureSession();

    const { data: subscription } = supabaseClient.auth.onAuthStateChange((_event, session) => {
      if (!isMounted) {
        return;
      }

      if (!session) {
        router.replace("/login");
      }
    });

    return () => {
      isMounted = false;
      subscription.subscription.unsubscribe();
    };
  }, [router]);

  if (isChecking) {
    return (
      <main className="page-shell page-shell--centered">
        <div className="surface card stack" style={{ width: "min(440px, 100%)" }}>
          <p className="eyebrow">Qualital Nexus</p>
          <h1 className="title title--lg">Carregando sua sessão</h1>
          <p className="text">Verificando seu acesso antes de abrir a área interna.</p>
        </div>
      </main>
    );
  }

  if (!getSupabaseBrowserClient()) {
    return (
      <main className="page-shell page-shell--centered">
        <div className="surface card stack" style={{ width: "min(520px, 100%)" }}>
          <p className="eyebrow">Configuração necessária</p>
          <h1 className="title title--lg">Supabase não configurado</h1>
          <p className="text">
            Defina NEXT_PUBLIC_SUPABASE_URL e NEXT_PUBLIC_SUPABASE_ANON_KEY no arquivo de ambiente e reinicie o servidor de desenvolvimento.
          </p>
        </div>
      </main>
    );
  }

  return children;
}