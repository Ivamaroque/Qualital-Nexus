"use client";

import { useState } from "react";

type QueueFile = {
  id: string;
  file: File;
};

type FileOrderListProps = {
  files: QueueFile[];
  onMoveUp: (index: number) => void;
  onMoveDown: (index: number) => void;
  onRemove: (index: number) => void;
  onReorder: (sourceIndex: number, targetIndex: number) => void;
  disabled?: boolean;
  canProcess: boolean;
  onProcess: () => void;
};

function formatSize(bytes: number) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }

  const kilobytes = bytes / 1024;
  if (kilobytes < 1024) {
    return `${kilobytes.toFixed(1)} KB`;
  }

  return `${(kilobytes / 1024).toFixed(1)} MB`;
}

export function FileOrderList({
  files,
  onMoveUp,
  onMoveDown,
  onRemove,
  onReorder,
  disabled,
  canProcess,
  onProcess
}: FileOrderListProps) {
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);
  const [dropIndex, setDropIndex] = useState<number | null>(null);

  function resetDragState() {
    setDraggedIndex(null);
    setDropIndex(null);
  }

  return (
    <section aria-label="Lista de arquivos enviados" className="surface card card--compact stack">
      <div className="row row--between">
        <div>
          <p className="eyebrow">Fila de envio</p>
          <h3 className="title" style={{ fontSize: "1.1rem", marginTop: 6 }}>
            Arquivos na ordem de processamento
          </h3>
        </div>
        <span className="badge">{files.length} selecionado{files.length === 1 ? "" : "s"}</span>
      </div>

      {files.length === 0 ? (
        <div className="panel">
          <p className="text">Nenhum arquivo foi adicionado ainda. Use a área de upload para começar.</p>
        </div>
      ) : (
        <div className="file-list">
          {files.map((entry, index) => (
            <div
              aria-grabbed={draggedIndex === index}
              className={`file-item ${draggedIndex === index ? "file-item--dragging" : ""} ${dropIndex === index && draggedIndex !== index ? "file-item--drop-target" : ""}`}
              draggable={!disabled}
              key={entry.id}
              onDragEnd={resetDragState}
              onDragOver={(event) => {
                if (disabled || draggedIndex === null) {
                  return;
                }

                event.preventDefault();
                event.dataTransfer.dropEffect = "move";
                setDropIndex(index);
              }}
              onDragStart={(event) => {
                if (disabled) {
                  return;
                }

                event.dataTransfer.effectAllowed = "move";
                event.dataTransfer.setData("text/plain", entry.id);
                setDraggedIndex(index);
              }}
              onDrop={(event) => {
                event.preventDefault();

                if (!disabled && draggedIndex !== null && draggedIndex !== index) {
                  onReorder(draggedIndex, index);
                }

                resetDragState();
              }}
            >
              <span aria-hidden="true" className="file-item__drag-handle" title="Arraste para reordenar">
                <svg fill="none" viewBox="0 0 24 24">
                  <path d="M9 5h.01M15 5h.01M9 12h.01M15 12h.01M9 19h.01M15 19h.01" stroke="currentColor" strokeLinecap="round" strokeWidth="3" />
                </svg>
              </span>
              <div className="file-item__index">{index + 1}</div>
              <div className="file-item__meta">
                <p className="file-item__name">{entry.file.name}</p>
                <p className="file-item__sub">{formatSize(entry.file.size)} · {entry.file.type || "tipo não informado"}</p>
              </div>
              <div className="file-item__controls">
                <button
                  aria-label={`Mover ${entry.file.name} para cima`}
                  className="button button--ghost"
                  disabled={disabled || index === 0}
                  onClick={() => onMoveUp(index)}
                  title="Mover para cima"
                  type="button"
                >
                  <svg aria-hidden="true" fill="none" viewBox="0 0 24 24">
                    <path d="m6 15 6-6 6 6" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
                  </svg>
                </button>
                <button
                  aria-label={`Mover ${entry.file.name} para baixo`}
                  className="button button--ghost"
                  disabled={disabled || index === files.length - 1}
                  onClick={() => onMoveDown(index)}
                  title="Mover para baixo"
                  type="button"
                >
                  <svg aria-hidden="true" fill="none" viewBox="0 0 24 24">
                    <path d="m6 9 6 6 6-6" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
                  </svg>
                </button>
                <button
                  aria-label={`Remover ${entry.file.name}`}
                  className="button button--danger"
                  disabled={disabled}
                  onClick={() => onRemove(index)}
                  title="Remover arquivo"
                  type="button"
                >
                  <svg aria-hidden="true" fill="none" viewBox="0 0 24 24">
                    <path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
                  </svg>
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="file-list__footer">
        <button
          className="extraction-process-button"
          disabled={!canProcess}
          onClick={onProcess}
          type="button"
        >
          {disabled ? (
            <>
              <span aria-hidden="true" className="spinner" />
              Processando
            </>
          ) : (
            "Processar arquivos"
          )}
        </button>
      </div>
    </section>
  );
}