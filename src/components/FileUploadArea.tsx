"use client";

import { useMemo, useRef, useState } from "react";
import { getAllowedExtractionFileLabel } from "@/lib/fileValidation";

type FileUploadAreaProps = {
  onFilesSelected: (files: File[]) => void;
  fileCount: number;
  errorMessage?: string | null;
  disabled?: boolean;
};

export function FileUploadArea({ onFilesSelected, fileCount, errorMessage, disabled }: FileUploadAreaProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const helperLabel = useMemo(() => {
    if (fileCount === 0) {
      return "Nenhum arquivo selecionado ainda.";
    }

    return `${fileCount} arquivo${fileCount === 1 ? "" : "s"} na fila.`;
  }, [fileCount]);

  function handleFiles(files: FileList | null) {
    if (!files || disabled) {
      return;
    }

    onFilesSelected(Array.from(files));
  }

  return (
    <section
      className={`upload-zone ${isDragging ? "upload-zone--active" : ""}`}
      onDragOver={(event) => {
        event.preventDefault();
        if (!disabled) {
          setIsDragging(true);
        }
      }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={(event) => {
        event.preventDefault();
        setIsDragging(false);
        handleFiles(event.dataTransfer.files);
      }}
    >
      <div className="stack stack--lg">
        <div className="row row--between">
          <div className="stack" style={{ gap: 6 }}>
            <p className="eyebrow">Envio de arquivos</p>
            <h2 className="title" style={{ fontSize: "1.3rem" }}>
              Arraste e solte os PDFs aqui
            </h2>
            <p className="text text--sm">Extensões permitidas neste MVP: {getAllowedExtractionFileLabel()}.</p>
          </div>
          <button
            className="button button--secondary"
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={disabled}
          >
            Selecionar arquivos
          </button>
        </div>

        <div className="panel stack" style={{ background: "rgba(255,255,255,0.7)" }}>
          <p className="text text--strong">{helperLabel}</p>
          <p className="text text--xs">{errorMessage ? errorMessage : "O sistema preserva a ordem visual da fila na hora do processamento."}</p>
        </div>
      </div>

      <input
        ref={inputRef}
        hidden
        multiple
        accept=".pdf,application/pdf"
        type="file"
        onChange={(event) => {
          handleFiles(event.target.files);
          event.currentTarget.value = "";
        }}
      />
    </section>
  );
}
