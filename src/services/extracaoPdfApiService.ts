import type { ExtracaoPdfRequestOptions, ExtracaoPdfResult } from "@/types/extracaoPdf";

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

export async function processarExtracaoPdfApi(
  files: File[],
  endpoint: string,
  options: ExtracaoPdfRequestOptions = {}
): Promise<ExtracaoPdfResult> {
  const formData = new FormData();

  // A ordem dos append é a mesma da fila exibida e deve ser preservada pelo FastAPI.
  files.forEach((file) => formData.append("files[]", file, file.name));

  const response = await fetch(endpoint, {
    method: "POST",
    body: formData,
    headers: options.accessToken ? { Authorization: `Bearer ${options.accessToken}` } : undefined
  });

  if (!response.ok) {
    throw new Error(await getErrorMessage(response));
  }

  return {
    filename: getFilename(response.headers.get("content-disposition")),
    blob: await response.blob()
  };
}
