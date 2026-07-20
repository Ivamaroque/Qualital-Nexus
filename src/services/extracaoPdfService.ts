const FAKE_PROCESSING_DELAY_MS = 4200;

function escapeCsvValue(value: string) {
  return `"${value.replaceAll('"', '""')}"`;
}

function buildFakeCsv(files: File[]) {
  const header = ["ordem", "arquivo", "tipo", "status"];
  const rows = files.map((file, index) => [
    String(index + 1),
    file.name,
    file.type || "application/pdf",
    "processado"
  ]);

  return [header, ...rows]
    .map((row) => row.map((value) => escapeCsvValue(value)).join(","))
    .join("\n");
}

export async function processarExtracaoPdf(files: File[]): Promise<{
  filename: string;
  blob: Blob;
}> {
  const invalidFile = files.find((file) => file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf"));

  if (invalidFile) {
    throw new Error(`O arquivo ${invalidFile.name} não é um PDF.`);
  }

  await new Promise((resolve) => {
    setTimeout(resolve, FAKE_PROCESSING_DELAY_MS);
  });

  const csv = buildFakeCsv(files);
  const blob = new Blob(["\ufeff", csv], { type: "text/csv;charset=utf-8" });

  return {
    filename: "qualital-nexus-extracao-pdf.csv",
    blob
  };
}