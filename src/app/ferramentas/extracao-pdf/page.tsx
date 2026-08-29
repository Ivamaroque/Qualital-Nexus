"use client";

import { useEffect, useState } from "react";
import { AuthGuard } from "@/components/AuthGuard";
import { AppHeader } from "@/components/AppHeader";
import { FileOrderList } from "@/components/FileOrderList";
import { FileUploadArea } from "@/components/FileUploadArea";
import { ProcessingSteps } from "@/components/ProcessingSteps";
import { isAllowedExtractionFile } from "@/lib/fileValidation";
import { getSupabaseBrowserClient } from "@/lib/supabaseClient";
import { processarExtracaoPdf } from "@/services/extracaoPdfService";
import type { ExtracaoPdfProgress } from "@/types/extracaoPdf";

type QueueFile = {
  id: string;
  file: File;
};

const processingSteps = [
  "Analisando documentos e calculando o total",
  "Extraindo texto dos documentos",
  "Aplicando regras e exemplos do parser",
  "Gerando linhas com IA",
  "Consolidando resultados",
  "Gerando XLSX"
];

const processingStepByStage: Record<string, number> = {
  envio: 0,
  preparacao: 0,
  regras: 2,
  ia: 3,
  normalizacao: 4,
  xlsx: 5,
  csv: 5,
  concluido: processingSteps.length
};

const iaStatusLabels: Record<string, string> = {
  enviando_lote: "enviando o lote",
  conectando: "conectando",
  aguardando_resposta: "aguardando o primeiro trecho",
  raciocinando: "processando o lote",
  gerando_resposta: "transmitindo a resposta",
  resposta_completa: "resposta completa",
  corrigindo_formato: "corrigindo o formato da resposta",
  corrigindo_cobertura: "recuperando blocos sem saída"
};

function createQueueFile(file: File): QueueFile {
  return {
    id: `${file.name}-${file.lastModified}-${Math.random().toString(36).slice(2, 8)}`,
    file
  };
}

function ExtracaoPdfContent() {
  const [files, setFiles] = useState<QueueFile[]>([]);
  const [selectedFileError, setSelectedFileError] = useState<string | null>(null);
  const [processingError, setProcessingError] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [processingProgress, setProcessingProgress] = useState<ExtracaoPdfProgress | null>(null);
  const [resultFilename, setResultFilename] = useState<string | null>(null);
  const [resultUrl, setResultUrl] = useState<string | null>(null);

  const canProcess = files.length > 0 && !isProcessing;

  useEffect(() => {
    if (!resultUrl) {
      return;
    }

    return () => {
      URL.revokeObjectURL(resultUrl);
    };
  }, [resultUrl]);


  function resetResultState() {
    setResultFilename(null);
    if (resultUrl) {
      URL.revokeObjectURL(resultUrl);
      setResultUrl(null);
    }
  }

  function addFiles(nextFiles: File[]) {
    if (nextFiles.length === 0) {
      setSelectedFileError("Selecione arquivos PDF, DOC ou DOCX válidos.");
      return;
    }

    const invalidFile = nextFiles.find((file) => !isAllowedExtractionFile(file));
    if (invalidFile) {
      setSelectedFileError(`O arquivo ${invalidFile.name} não possui uma extensão permitida.`);
      return;
    }

    setSelectedFileError(null);
    setProcessingError(null);
    resetResultState();
    setFiles((current) => [...current, ...nextFiles.map(createQueueFile)]);
  }

  function moveFile(index: number, direction: -1 | 1) {
    setFiles((current) => {
      const targetIndex = index + direction;

      if (targetIndex < 0 || targetIndex >= current.length) {
        return current;
      }

      const next = [...current];
      const [selected] = next.splice(index, 1);
      next.splice(targetIndex, 0, selected);
      return next;
    });

    resetResultState();
    setSelectedFileError(null);
  }

  function reorderFiles(sourceIndex: number, targetIndex: number) {
    setFiles((current) => {
      const next = [...current];
      const [selected] = next.splice(sourceIndex, 1);
      next.splice(targetIndex, 0, selected);
      return next;
    });

    resetResultState();
    setSelectedFileError(null);
  }
  function removeFile(index: number) {
    setFiles((current) => current.filter((_, currentIndex) => currentIndex !== index));
    resetResultState();
    setSelectedFileError(null);
  }

  async function handleProcessFiles() {
    if (files.length === 0) {
      setProcessingError("Adicione pelo menos um documento antes de processar.");
      return;
    }

    setProcessingError(null);
    setSelectedFileError(null);
    setIsProcessing(true);
    setProcessingProgress({
      status: "processando",
      etapa: "envio",
      mensagem: "Preparando o envio dos arquivos.",
      arquivo_atual: 0,
      total_arquivos: files.length,
      lote_atual: 0,
      total_lotes: 0,
      etapas_concluidas: 0,
      etapas_totais: 0,
      progresso_percentual: 0,
      ia_status: "",
      ia_trechos_recebidos: 0,
      ia_caracteres_recebidos: 0,
      atualizado_em: new Date().toISOString()
    });
    resetResultState();

    try {
      const supabase = getSupabaseBrowserClient();
      let accessToken: string | undefined;

      if (supabase) {
        const { data: sessionData } = await supabase.auth.getSession();
        accessToken = sessionData.session?.access_token;
      }

      const result = await processarExtracaoPdf(files.map((entry) => entry.file), {
        accessToken,
        onProgress: setProcessingProgress
      });
      const url = URL.createObjectURL(result.blob);
      setResultFilename(result.filename);
      setResultUrl(url);
      setProcessingProgress((current) => ({
        ...(current ?? {
          arquivo_atual: files.length,
          total_arquivos: files.length,
          lote_atual: 0,
          total_lotes: 0,
          etapas_concluidas: 0,
          etapas_totais: 0,
          progresso_percentual: 100,
          ia_status: "",
          ia_trechos_recebidos: 0,
          ia_caracteres_recebidos: 0,
          atualizado_em: new Date().toISOString()
        }),
        status: "concluido",
        etapa: "concluido",
        mensagem: "XLSX gerado e pronto para download."
      }));
    } catch (error) {
      const message = error instanceof Error ? error.message : "Não foi possível processar os arquivos agora.";
      setProcessingProgress((current) => ({
        ...(current ?? {
          arquivo_atual: 0,
          total_arquivos: files.length,
          lote_atual: 0,
          total_lotes: 0,
          etapas_concluidas: 0,
          etapas_totais: 0,
          progresso_percentual: 0,
          ia_status: "",
          ia_trechos_recebidos: 0,
          ia_caracteres_recebidos: 0,
          atualizado_em: new Date().toISOString()
        }),
        status: "erro",
        etapa: "erro",
        mensagem: message
      }));
      setProcessingError(error instanceof Error ? error.message : "Não foi possível processar os arquivos agora.");
    } finally {
      setIsProcessing(false);
    }
  }

  function downloadResult() {
    if (!resultUrl || !resultFilename) {
      return;
    }

    const anchor = document.createElement("a");
    anchor.href = resultUrl;
    anchor.download = resultFilename;
    anchor.click();
  }

  return (
    <main className="extraction-page">
      <AppHeader title="Extração de documentos" />

      <div className="extraction-content stack stack--xl">
        <section className="extraction-hero">
          <div className="stack" style={{ gap: 12 }}>
            <p className="eyebrow">Ferramenta operacional</p>
            <h2 className="title title--lg">Envie os documentos na ordem desejada e acompanhe o processamento em etapas.</h2>
            <p className="text text--sm">
              Organize os arquivos na fila conforme a sequência de leitura desejada. Ao final, a planilha estará disponível para download.
            </p>
          </div>
        </section>

        {selectedFileError ? (
          <div
            className="alert alert--error"
            role="alert"
          >
            {selectedFileError}
          </div>
        ) : null}
        {processingError ? (
          <div
            className="alert alert--error"
            role="alert"
          >
            {processingError}
          </div>
        ) : null}

        <div className="extraction-grid">
          <div className="extraction-actions">
            <FileUploadArea
              disabled={isProcessing}
              errorMessage={selectedFileError}
              fileCount={files.length}
              onFilesSelected={addFiles}
            />

            <FileOrderList
              disabled={isProcessing}
              files={files}
              canProcess={canProcess}
              onMoveDown={(index) => moveFile(index, 1)}
              onMoveUp={(index) => moveFile(index, -1)}
              onProcess={handleProcessFiles}
              onReorder={reorderFiles}
              onRemove={removeFile}
            />
          </div>

          <div className="extraction-monitoring">
            <ProcessingSteps
              activeIndex={processingStepByStage[processingProgress?.etapa ?? "envio"] ?? 0}
              isProcessing={isProcessing}
              steps={processingSteps}
            />

            <section className="extraction-terminal-card" aria-live="polite" aria-label="Acompanhamento ao vivo">
              <div className="row row--between">
                <div>
                  <p className="extraction-card-eyebrow">Acompanhamento ao vivo</p>
                  <h2>Atualizações do processamento</h2>
                </div>
                {isProcessing || processingProgress?.status === "erro" ? (
                  <span className="extraction-status-pill extraction-status-pill--processing">
                    {processingProgress?.status === "erro" ? "Atenção" : "Atualizando"}
                  </span>
                ) : null}
              </div>
              <div className={`debug-console ${processingProgress?.status === "erro" ? "debug-console--error" : ""}`}>
                <p>{processingProgress?.mensagem ?? "O status do processamento aparecerá aqui após o envio."}</p>
                {processingProgress?.ia_status ? (
                  <p>
                    IA: {iaStatusLabels[processingProgress.ia_status] ?? processingProgress.ia_status}
                    {processingProgress.ia_trechos_recebidos > 0
                      ? ` · ${processingProgress.ia_trechos_recebidos} trechos recebidos (${processingProgress.ia_caracteres_recebidos} caracteres)`
                      : ""}
                  </p>
                ) : null}
                {processingProgress?.etapas_totais ? (
                  <>
                    <p>
                      Progresso real: {processingProgress.etapas_concluidas} de {processingProgress.etapas_totais} etapas concluídas
                      ({processingProgress.progresso_percentual}%).
                    </p>
                    <progress
                      className="processing-progress"
                      max={processingProgress.etapas_totais}
                      value={processingProgress.etapas_concluidas}
                    >
                      {processingProgress.progresso_percentual}%
                    </progress>
                  </>
                ) : processingProgress ? (
                  <p>Calculando o total real das etapas antes de iniciar a IA.</p>
                ) : null}
                {processingProgress && processingProgress.total_arquivos > 0 ? (
                  <p>
                    Arquivo {processingProgress.arquivo_atual || 1} de {processingProgress.total_arquivos}
                    {processingProgress.total_lotes > 0
                      ? ` · lote ${processingProgress.lote_atual || 1} de ${processingProgress.total_lotes}`
                      : ""}
                  </p>
                ) : null}
              </div>
            </section>
            <section className="extraction-result-card">
              <div className="extraction-card-header">
                <div>
                  <p className="extraction-card-eyebrow">Resultado</p>
                  <h2>XLSX de saída</h2>
                </div>
                <span className={resultUrl && resultFilename ? "extraction-status-pill extraction-status-pill--ready" : "extraction-status-pill"}>
                  {resultUrl && resultFilename ? "Disponível" : "Aguardando"}
                </span>
              </div>

              <div className="extraction-card-footer extraction-card-footer--result">
                <p className="extraction-result-file">
                  {resultUrl && resultFilename
                    ? `Arquivo pronto: ${resultFilename}`
                    : "O arquivo será disponibilizado após o processamento."}
                </p>
                <button
                  className="extraction-download-button"
                  disabled={!resultUrl || !resultFilename}
                  onClick={downloadResult}
                  type="button"
                >
                  Baixar XLSX
                </button>
              </div>
            </section>
          </div>
        </div>
      </div>
    </main>
  );
}

export default function ExtracaoPdfPage() {
  return (
    <AuthGuard>
      <ExtracaoPdfContent />
    </AuthGuard>
  );
}