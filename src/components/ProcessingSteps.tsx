type ProcessingStepsProps = {
  steps: string[];
  activeIndex: number;
  isProcessing: boolean;
};

export function ProcessingSteps({ steps, activeIndex, isProcessing }: ProcessingStepsProps) {
  return (
    <section className="surface card card--compact stack" aria-label="Status de processamento">
      <div className="row row--between">
        <div>
          <p className="eyebrow">Processamento</p>
          <h3 className="title" style={{ fontSize: "1.1rem", marginTop: 6 }}>
            Etapas em andamento
          </h3>
        </div>
        <span className="badge">{isProcessing ? "Executando" : "Aguardando"}</span>
      </div>

      <div className="step-list">
        {steps.map((step, index) => {
          const isDone = activeIndex > index;
          const isActive = activeIndex === index && isProcessing;

          return (
            <div
              className={`step-item ${isDone ? "step-item--done" : ""} ${isActive ? "step-item--active" : ""}`}
              key={step}
            >
              <span className="step-item__dot" aria-hidden="true" />
              <div>
                <p className="text text--strong" style={{ marginBottom: 2 }}>
                  {index + 1}. {step}
                </p>
                <p className="text text--xs">
                  {isDone ? "Concluído" : isActive ? "Em execução agora" : "Aguardando início"}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}