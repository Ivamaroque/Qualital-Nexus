"use client";

type QueueFile = {
  id: string;
  file: File;
};

type FileOrderListProps = {
  files: QueueFile[];
  onMoveUp: (index: number) => void;
  onMoveDown: (index: number) => void;
  onRemove: (index: number) => void;
  disabled?: boolean;
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

export function FileOrderList({ files, onMoveUp, onMoveDown, onRemove, disabled }: FileOrderListProps) {
  return (
    <section className="surface card card--compact stack" aria-label="Lista de arquivos enviados">
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
            <div className="file-item" key={entry.id}>
              <div className="file-item__index">{index + 1}</div>
              <div className="file-item__meta">
                <p className="file-item__name">{entry.file.name}</p>
                <p className="file-item__sub">{formatSize(entry.file.size)} · {entry.file.type || "application/pdf"}</p>
              </div>
              <div className="file-item__controls">
                <button className="button button--ghost" type="button" onClick={() => onMoveUp(index)} disabled={disabled || index === 0}>
                  Subir
                </button>
                <button
                  className="button button--ghost"
                  type="button"
                  onClick={() => onMoveDown(index)}
                  disabled={disabled || index === files.length - 1}
                >
                  Descer
                </button>
                <button className="button button--danger" type="button" onClick={() => onRemove(index)} disabled={disabled}>
                  Remover
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}