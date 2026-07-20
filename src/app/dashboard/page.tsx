"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AuthGuard } from "@/components/AuthGuard";
import { AppHeader } from "@/components/AppHeader";
import { ToolCard } from "@/components/ToolCard";
import { getSupabaseBrowserClient } from "@/lib/supabaseClient";
import { tools } from "@/lib/tools";
import type { Profile } from "@/types/profile";

function DashboardContent() {
  const [userName, setUserName] = useState("Carregando...");
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadProfile() {
      try {
        const supabase = getSupabaseBrowserClient();
        const { data: sessionData } = await supabase.auth.getUser();

        if (!sessionData.user) {
          return;
        }

        setUserEmail(sessionData.user.email ?? null);

        const { data: profileData, error: profileError } = await supabase
          .from("profiles")
          .select("id, full_name, email, role")
          .eq("id", sessionData.user.id)
          .maybeSingle<Profile>();

        if (profileError) {
          throw profileError;
        }

        setUserName(profileData?.full_name?.trim() || sessionData.user.email || "Usuário Qualital");
      } catch {
        setError("Não foi possível carregar o perfil agora. O dashboard seguirá com o e-mail do usuário autenticado.");
      }
    }

    loadProfile();
  }, []);

  return (
    <main className="page-shell">
      <div className="container stack stack--xl">
        <AppHeader
          title="Dashboard"
          subtitle="Hub de ferramentas internas do Qualital Nexus"
          userEmail={userEmail}
          userName={userName}
        />

        {error ? <div className="alert alert--error">{error}</div> : null}

        <section className="surface card stack">
          <div className="toolbar">
            <div className="stack" style={{ gap: 8 }}>
              <p className="eyebrow">Bem-vindo</p>
              <h2 className="title title--lg">Olá, {userName}.</h2>
              <p className="text">Escolha uma ferramenta abaixo para continuar o fluxo interno.</p>
            </div>
            <div className="badge">{tools.length} ferramenta disponível</div>
          </div>
        </section>

        <section className="grid grid--tools">
          {tools.map((tool) => (
            <ToolCard key={tool.slug} tool={tool} />
          ))}
        </section>

        <section className="surface card stack">
          <p className="eyebrow">Próximos módulos</p>
          <p className="text text--sm">
            A arquitetura já está pronta para receber backend FastAPI, histórico de extrações, RAG operacional e mais ferramentas no frontend sem depender de banco para a lista inicial.
          </p>
          <div className="row">
            <Link className="button button--primary" href="/ferramentas/extracao-pdf">
              Ir para Extração PDF
            </Link>
            <span className="text text--xs">Acesso mínimo da ferramenta: usuario</span>
          </div>
        </section>
      </div>
    </main>
  );
}

export default function DashboardPage() {
  return (
    <AuthGuard>
      <DashboardContent />
    </AuthGuard>
  );
}