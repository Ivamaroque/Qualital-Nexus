export type ExtracaoPdfResult = {
  filename: string;
  blob: Blob;
};

export type ExtracaoPdfProgress = {
  status: "processando" | "concluido" | "erro";
  etapa: string;
  mensagem: string;
  arquivo_atual: number;
  total_arquivos: number;
  lote_atual: number;
  total_lotes: number;
  etapas_concluidas: number;
  etapas_totais: number;
  progresso_percentual: number;
  ia_status: string;
  ia_trechos_recebidos: number;
  ia_caracteres_recebidos: number;
  atualizado_em: string;
};

export type ExtracaoPdfRequestOptions = {
  accessToken?: string;
  onProgress?: (progress: ExtracaoPdfProgress) => void;
};
