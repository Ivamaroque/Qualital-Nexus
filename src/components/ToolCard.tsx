import Link from "next/link";
import type { Tool } from "@/types/tool";

type ToolCardProps = {
  tool: Tool;
};

export function ToolCard({ tool }: ToolCardProps) {
  return (
    <article className="surface card tool-card">
      <div className="row" style={{ alignItems: "flex-start" }}>
        <div className="tool-card__icon" aria-hidden="true">
          {tool.icone === "file-search" ? "⌕" : "•"}
        </div>
        <div className="stack" style={{ gap: 8 }}>
          <div className="row" style={{ gap: 8 }}>
            <h2 className="title" style={{ fontSize: "1.25rem" }}>
              {tool.nome}
            </h2>
            <span className="badge">Acesso mínimo: {tool.acessoMinimo}</span>
          </div>
          <p className="text">{tool.descricao}</p>
        </div>
      </div>

      <div className="tool-card__footer">
        <span className="text text--xs">Rota: {tool.rota}</span>
        <Link className="button button--primary" href={tool.rota}>
          Acessar ferramenta
        </Link>
      </div>
    </article>
  );
}