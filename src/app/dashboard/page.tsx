"use client";

import Link from "next/link";
import { AuthGuard } from "@/components/AuthGuard";
import { AppHeader } from "@/components/AppHeader";
import { ToolCard } from "@/components/ToolCard";
import { useAuthenticatedProfile } from "@/hooks/useAuthenticatedProfile";
import { tools } from "@/lib/tools";

function DashboardContent() {
  const { displayName } = useAuthenticatedProfile();

  return (
    <main className="dashboard-page">
      <AppHeader title="Hub de ferramentas" />

      <div className="dashboard-content">
        <section className="dashboard-welcome">
          <div>
            <p className="dashboard-eyebrow">Bem-vindo</p>
            <h1>Olá, {displayName}.</h1>
            <p>Escolha uma ferramenta abaixo para continuar o fluxo interno.</p>
          </div>
          <span className="dashboard-availability">{tools.length} ferramenta disponível</span>
        </section>

        <section className="dashboard-tools" aria-label="Ferramentas disponíveis">
          {tools.map((tool) => (
            <ToolCard key={tool.slug} tool={tool} />
          ))}
        </section>

        <section className="dashboard-next">
          <p className="dashboard-eyebrow">Próximos módulos</p>
          <p>
            A arquitetura já está pronta para receber backend FastAPI, histórico de extrações, RAG operacional e mais
            ferramentas no frontend sem depender de banco para a lista inicial.
          </p>
          <div>
            <button className="dashboard-next__button" disabled type="button">
              Módulos em desenvolvimento…
            </button>
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
