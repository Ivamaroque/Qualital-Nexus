export const ALLOWED_EXTRACTION_FILE_EXTENSIONS = ["pdf", "doc", "docx"] as const;

function getFileExtension(fileName: string) {
  return fileName.split(".").pop()?.toLowerCase() ?? "";
}

export function isAllowedExtractionFile(file: File) {
  return ALLOWED_EXTRACTION_FILE_EXTENSIONS.includes(
    getFileExtension(file.name) as (typeof ALLOWED_EXTRACTION_FILE_EXTENSIONS)[number]
  );
}

export function getAllowedExtractionFileLabel() {
  return ALLOWED_EXTRACTION_FILE_EXTENSIONS.map((extension) => `.${extension.toUpperCase()}`).join(", ");
}
