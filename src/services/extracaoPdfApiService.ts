import type { ExtracaoPdfProgress, ExtracaoPdfRequestOptions, ExtracaoPdfResult } from "@/types/extracaoPdf";

const STATUS_POLL_INTERVAL_MS = 1_250;

function getFilename(contentDisposition: string | null) {
  const match = contentDisposition?.match(/filename\*?=(?:UTF-8''|\")?([^;\"]+)/i);
  const encodedFilename = match?.[1]?.trim();

  if (!encodedFilename) {
    return "qualital-nexus-extracao-pdf.csv";
  }

  try {
    return decodeURIComponent(encodedFilename);
  } catch {
    return "qualital-nexus-extracao-pdf.csv";
  }
}

async function getErrorMessage(response: Response) {
  try {
    const payload: unknown = await response.json();
    if (
      typeof payload === "object" &&
      payload !== null &&
      "detail" in payload &&
      typeof payload.detail === "string"
    ) {
      return payload.detail;
    }
  } catch {
    // A resposta de erro pode não conter JSON.
  }

  return "Não foi possível processar os arquivos. Tente novamente em instantes.";
}

function createProcessingId() {
  return crypto.randomUUID();
}

function getStatusEndpoint(endpoint: string, processingId: string) {
  return `${endpoint.replace(/\/$/, "")}/${processingId}/status`;
}

function startProgressPolling(endpoint: string, processingId: string, options: ExtracaoPdfRequestOptions) {
  let active = true;
  let timer: ReturnType<typeof setTimeout> | undefined;

  const poll = async () => {
    try {
      const response = await fetch(getStatusEndpoint(endpoint, processingId), {
        headers: options.accessToken ? { Authorization: `Bearer ${options.accessToken}` } : undefined
      });
      if (response.ok) {
        const progress = (await response.json()) as ExtracaoPdfProgress;
        if (active) {
          options.onProgress?.(progress);
        }
      }
    } catch {
      // A requisição principal exibirá erros de rede ou processamento ao usuário.
    } finally {
      if (active) {
        timer = setTimeout(() => void poll(), STATUS_POLL_INTERVAL_MS);
      }
    }
  };

  void poll();
  return () => {
    active = false;
    if (timer) {
      clearTimeout(timer);
    }
  };
}

export async function processarExtracaoPdfApi(
  files: File[],
  endpoint: string,
  options: ExtracaoPdfRequestOptions = {}
): Promise<ExtracaoPdfResult> {
  const formData = new FormData();
  const processingId = options.onProgress ? createProcessingId() : undefined;

  // A ordem dos append é a mesma da fila exibida e deve ser preservada pelo FastAPI.
  files.forEach((file) => formData.append("files[]", file, file.name));

  const headers = new Headers();
  if (options.accessToken) {
    headers.set("Authorization", `Bearer ${options.accessToken}`);
  }
  if (processingId) {
    headers.set("X-Processing-Id", processingId);
  }
  const stopPolling = processingId ? startProgressPolling(endpoint, processingId, options) : undefined;

  let response: Response;
  try {
    response = await fetch(endpoint, {
      method: "POST",
      body: formData,
      headers
    });
  } finally {
    stopPolling?.();
  }

  if (!response.ok) {
    throw new Error(await getErrorMessage(response));
  }

  return {
    filename: getFilename(response.headers.get("content-disposition")),
    blob: await response.blob()
  };
}
