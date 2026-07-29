"use client";

import Link from "next/link";
import { AuthGuard } from "@/components/AuthGuard";
import { AppHeader } from "@/components/AppHeader";
import { ToolCard } from "@/components/ToolCard";
import { useAuthenticatedProfile } from "@/hooks/useAuthenticatedProfile";
import { tools } from "@/lib/tools";

function DashboardContent() {
  const { displayName, notice, userEmail } = useAuthenticatedProfile();

  return (
    <main className="page-shell">
      <div className="container stack stack--xl">
        <AppHeader
          title="Dashboard"
          subtitle="Hub de ferramentas internas do Qualital Nexus"
          userEmail={userEmail}
          userName={displayName}
        />

        {notice ? (
          <div
            className="alert alert--warning"
            role="status"
          >
            {notice}
          </div>
        ) : null}

        <section className="surface card stack">
          <div className="toolbar">
            <div className="stack" style={{ gap: 8 }}>
              <p className="eyebrow">Bem-vindo</p>
              <h2 className="title title--lg">Olá, {displayName}.</h2>
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
