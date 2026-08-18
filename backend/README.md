# Backend local — Qualital Nexus

API FastAPI da ferramenta **Extração de documentos**. Recebe arquivos PDF, DOC e DOCX em `multipart/form-data`, preserva a ordem das partes, consulta regras e exemplos no Supabase, transforma cada bloco e devolve `matriz_priorizacao.xlsx` como saída principal e permite CSV compatível com `?format=csv`.

## Configuração

Crie `backend/.env` a partir de `.env.example` (ou use o `.env` da raiz):

```env
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
FRONTEND_ORIGIN=http://localhost:3000
```

`SUPABASE_SERVICE_ROLE_KEY` é exclusiva do backend e nunca deve ser colocada em variáveis `NEXT_PUBLIC_*` nem versionada. Sem Supabase, a API funciona sem regras e exemplos remotos; sem `OPENAI_API_KEY`, a conversão retorna erro claro pois a geração da matriz depende da OpenAI.

## Executar localmente

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Teste a saúde do serviço em `GET http://localhost:8000/health`.

Para o frontend, defina `NEXT_PUBLIC_API_URL=http://localhost:8000`. O cliente envia cada documento como `files[]`, na mesma ordem exibida na tela. A API também aceita o campo legado `files`.

## Endpoints

- `POST /api/extracao-pdf/process`: devolve `matriz_priorizacao.xlsx` como download por padrão; use `?format=csv` para CSV.
- `POST /api/extracao-pdf/debug`: devolve blocos, categorias, contagem de exemplos RAG, regras selecionadas e prévia das linhas.

Ambos aceitam um ou mais arquivos PDF, DOC ou DOCX, até 20 arquivos de 25 MB por padrão. PDFs sem camada de texto ainda não têm OCR.
