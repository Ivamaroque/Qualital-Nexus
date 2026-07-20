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

    async function ensureSession() {
      const { data } = await supabase.auth.getSession();

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

    const { data: subscription } = supabase.auth.onAuthStateChange((_event, session) => {
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

  return children;
}