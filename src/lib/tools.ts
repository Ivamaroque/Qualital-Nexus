import type { Tool } from "@/types/tool";

export const tools: Tool[] = [
  {
    slug: "extracao-pdf",
    nome: "Extração PDF",
    descricao: "Envie PDFs técnicos em ordem e receba um CSV estruturado.",
    rota: "/ferramentas/extracao-pdf",
    icone: "file-search",
    acessoMinimo: "usuario"
  }
];