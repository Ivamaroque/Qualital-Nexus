import { processarExtracaoPdfApi } from "@/services/extracaoPdfApiService";
import type { ExtracaoPdfRequestOptions, ExtracaoPdfResult } from "@/types/extracaoPdf";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");
const extractionApiUrl = process.env.NEXT_PUBLIC_EXTRACAO_PDF_API_URL ?? (apiBaseUrl ? `${apiBaseUrl}/api/extracao-pdf/process` : undefined);
const extractionApiConfigurationError =
  "A extração real não está configurada. Defina NEXT_PUBLIC_API_URL ou NEXT_PUBLIC_EXTRACAO_PDF_API_URL e reinicie o frontend.";

export async function processarExtracaoPdf(
  files: File[],
  options: ExtracaoPdfRequestOptions = {}
): Promise<ExtracaoPdfResult> {
  if (!extractionApiUrl) {
    throw new Error(extractionApiConfigurationError);
  }

  return processarExtracaoPdfApi(files, extractionApiUrl, options);
}
