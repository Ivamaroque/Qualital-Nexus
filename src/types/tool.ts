export type ToolAccessLevel = "usuario" | "admin";

export type Tool = {
  slug: string;
  nome: string;
  descricao: string;
  rota: string;
  icone: string;
  acessoMinimo: ToolAccessLevel;
};