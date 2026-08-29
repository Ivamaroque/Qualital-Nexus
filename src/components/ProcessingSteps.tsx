type ProcessingStepsProps = {
  steps: string[];
  activeIndex: number;
  isProcessing: boolean;
};

export function ProcessingSteps({ steps, activeIndex, isProcessing }: ProcessingStepsProps) {
  const visibleStepIndex = isProcessing ? activeIndex : 0;
  const completedPercentage = Math.min(Math.round((visibleStepIndex / steps.length) * 100), 100);
  const currentStep = isProcessing ? steps[Math.min(activeIndex, steps.length - 1)] : "Pronto para iniciar";
  const description = isProcessing
    ? "O processamento está em andamento. Você pode acompanhar as atualizações abaixo."
    : "Adicione arquivos à fila e inicie o processamento.";

  return (
    <section aria-label="Status do processamento" aria-live="polite" className="extraction-status-card">
      <div className="extraction-card-header">
        <div>
          <p className="extraction-card-eyebrow">Processamento</p>
          <h2>Status da Extração</h2>
        </div>
        <span className={isProcessing ? "extraction-status-pill extraction-status-pill--processing" : "extraction-status-pill"}>
          {isProcessing ? "Em andamento" : "Aguardando"}
        </span>
      </div>

      <div className="extraction-progress-panel">
        <div className="extraction-progress-summary">
          <strong>{currentStep}</strong>
          <span>{completedPercentage}%</span>
        </div>
        <div
          aria-label={`${completedPercentage}% concluído`}
          aria-valuemax={100}
          aria-valuemin={0}
          aria-valuenow={completedPercentage}
          className="extraction-progress-track"
          role="progressbar"
        >
          <span style={{ width: `${completedPercentage}%` }} />
        </div>
        <p>{description}</p>
      </div>
    </section>
  );
}