-- Remove o fluxo RAG legado. O pipeline ativo usa exclusivamente parser_rules.
-- Não usa CASCADE: dependências externas inesperadas devem impedir a exclusão.

BEGIN;

DROP FUNCTION IF EXISTS public.buscar_exemplos_rag(text, text, text[], integer);
DROP TABLE IF EXISTS public.rag_examples;

COMMIT;
