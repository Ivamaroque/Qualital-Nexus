import type { Tool } from "@/types/tool";

export const tools: Tool[] = [
  {
    slug: "extracao-pdf",
    nome: "Extração de documentos",
    descricao: "Envie documentos técnicos em PDF ou Word e receba um CSV estruturado.",
    rota: "/ferramentas/extracao-pdf",
    icone: "file-search",
    acessoMinimo: "usuario"
  }
];
