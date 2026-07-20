"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AuthGuard } from "@/components/AuthGuard";
import { AppHeader } from "@/components/AppHeader";
import { FileOrderList } from "@/components/FileOrderList";
import { FileUploadArea } from "@/components/FileUploadArea";
import { ProcessingSteps } from "@/components/ProcessingSteps";
import { getSupabaseBrowserClient } from "@/lib/supabaseClient";
import { processarExtracaoPdf } from "@/services/extracaoPdfService";
import type { Profile } from "@/types/profile";

type QueueFile = {
  id: string;
  file: File;
};

const processingSteps = [
  "Enviando arquivos",
  "Extraindo texto dos PDFs",
  "Separando conteúdo em blocos",
  "Consultando exemplos RAG",
  "Gerando CSV"
];

function createQueueFile(file: File): QueueFile {
  return {
    id: `${file.name}-${file.lastModified}-${Math.random().toString(36).slice(2, 8)}`,
    file
  };
}

function ExtracaoPdfContent() {
  const [userName, setUserName] = useState("Carregando...");
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const [files, setFiles] = useState<QueueFile[]>([]);
  const [selectedFileError, setSelectedFileError] = useState<string | null>(null);
  const [processingError, setProcessingError] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [activeStepIndex, setActiveStepIndex] = useState(0);
  const [resultFilename, setResultFilename] = useState<string | null>(null);
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const timeoutsRef = useRef<number[]>([]);

  const canProcess = files.length > 0 && !isProcessing;

  useEffect(() => {
    async function loadProfile() {
      try {
        const supabase = getSupabaseBrowserClient();

        if (!supabase) {
          setUserName("Usuário Qualital");
          return;
        }

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
        setUserName((current) => current || "Usuário Qualital");
      }
    }

    loadProfile();

    return () => {
      timeoutsRef.current.forEach((timeoutId) => window.clearTimeout(timeoutId));
    };
  }, []);

  useEffect(() => {
    if (!resultUrl) {
      return;
    }

    return () => {
      URL.revokeObjectURL(resultUrl);
    };
  }, [resultUrl]);

  const selectedCountLabel = useMemo(
    () => `${files.length} arquivo${files.length === 1 ? "" : "s"} selecionado${files.length === 1 ? "" : "s"}`,
    [files.length]
  );

  function resetResultState() {
    setResultFilename(null);
    if (resultUrl) {
      URL.revokeObjectURL(resultUrl);
      setResultUrl(null);
    }
  }

  function addFiles(nextFiles: File[]) {
    if (nextFiles.length === 0) {
      setSelectedFileError("Selecione apenas arquivos PDF válidos.");
      return;
    }

    const invalidFile = nextFiles.find((file) => file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf"));
    if (invalidFile) {
      setSelectedFileError(`O arquivo ${invalidFile.name} não é um PDF.`);
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

  function removeFile(index: number) {
    setFiles((current) => current.filter((_, currentIndex) => currentIndex !== index));
    resetResultState();
    setSelectedFileError(null);
  }

  async function handleProcessFiles() {
    if (files.length === 0) {
      setProcessingError("Adicione pelo menos um PDF antes de processar.");
      return;
    }

    setProcessingError(null);
    setSelectedFileError(null);
    setIsProcessing(true);
    setActiveStepIndex(0);
    resetResultState();

    const stepDurations = [0, 850, 1650, 2550, 3450];
    timeoutsRef.current.forEach((timeoutId) => window.clearTimeout(timeoutId));
    timeoutsRef.current = stepDurations.map((delay, index) =>
      window.setTimeout(() => {
        setActiveStepIndex(index);
      }, delay)
    );

    try {
      const result = await processarExtracaoPdf(files.map((entry) => entry.file));
      const url = URL.createObjectURL(result.blob);
      setResultFilename(result.filename);
      setResultUrl(url);
      setActiveStepIndex(processingSteps.length);
    } catch (error) {
      setProcessingError(error instanceof Error ? error.message : "Não foi possível processar os arquivos agora.");
    } finally {
      setIsProcessing(false);
      timeoutsRef.current.forEach((timeoutId) => window.clearTimeout(timeoutId));
      timeoutsRef.current = [];
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
    <main className="page-shell">
      <div className="container stack stack--xl">
        <AppHeader
          title="Extração PDF"
          subtitle="Envie PDFs técnicos em ordem e receba um CSV estruturado."
          userEmail={userEmail}
          userName={userName}
        />

        <section className="surface card stack hero">
          <div className="stack" style={{ gap: 12 }}>
            <p className="eyebrow">Ferramenta operacional</p>
            <h2 className="title title--lg">Envie os PDFs na ordem desejada e acompanhe o processamento em etapas.</h2>
            <p className="text text--sm">
              Este fluxo já preserva a ordenação visual dos arquivos para a futura chamada real ao backend FastAPI em multipart/form-data.
            </p>
          </div>

          <div className="row">
            <span className="badge">{selectedCountLabel}</span>
            <span className="badge">Backend futuro: POST /api/extracao-pdf/process</span>
          </div>
        </section>

        {selectedFileError ? <div className="alert alert--error">{selectedFileError}</div> : null}
        {processingError ? <div className="alert alert--error">{processingError}</div> : null}

        <div className="grid grid--two" style={{ alignItems: "start" }}>
          <div className="stack stack--lg">
            <FileUploadArea
              disabled={isProcessing}
              errorMessage={selectedFileError}
              fileCount={files.length}
              onFilesSelected={addFiles}
            />

            <FileOrderList
              disabled={isProcessing}
              files={files}
              onMoveDown={(index) => moveFile(index, 1)}
              onMoveUp={(index) => moveFile(index, -1)}
              onRemove={removeFile}
            />

            <section className="surface card card--compact stack">
              <div className="row row--between">
                <div>
                  <p className="eyebrow">Ação principal</p>
                  <h3 className="title" style={{ fontSize: "1.1rem", marginTop: 6 }}>
                    Processar arquivos e gerar o CSV
                  </h3>
                </div>
                <span className="badge">{canProcess ? "Pronto" : isProcessing ? "Em processamento" : "Sem arquivos"}</span>
              </div>

              <div className="row">
                <button className="button button--primary" type="button" onClick={handleProcessFiles} disabled={!canProcess}>
                  {isProcessing ? (
                    <>
                      <span className="spinner" aria-hidden="true" />
                      Processando
                    </>
                  ) : (
                    "Processar arquivos"
                  )}
                </button>

                <span className="text text--xs">A ordem de envio é a mesma exibida na fila acima.</span>
              </div>
            </section>
          </div>

          <div className="stack stack--lg">
            <ProcessingSteps activeIndex={activeStepIndex} isProcessing={isProcessing} steps={processingSteps} />

            <section className="surface card card--compact stack">
              <p className="eyebrow">Resultado</p>
              <h3 className="title" style={{ fontSize: "1.1rem" }}>
                CSV de saída
              </h3>

              {resultUrl && resultFilename ? (
                <>
                  <div className="alert alert--success">
                    Processamento concluído. O arquivo {resultFilename} está pronto para download.
                  </div>
                  <button className="button button--primary" type="button" onClick={downloadResult}>
                    Baixar CSV
                  </button>
                </>
              ) : (
                <div className="panel">
                  <p className="text">O resultado final será exibido aqui após o processamento dos arquivos.</p>
                </div>
              )}
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