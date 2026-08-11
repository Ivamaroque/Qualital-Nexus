import json
import logging
import re
import time
import unicodedata
from collections.abc import Callable
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.openai_client import get_openai_client
from app.schemas.matriz import MatrizLinha, MatrizOutput

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Você é um conversor técnico do Qualital Nexus. Sua função é converter blocos de PDFs "
    "técnicos em linhas para a Matriz de Priorização. Siga as regras do parser, os exemplos "
    "do parser e preserve a granularidade do documento. Não invente conteúdo. Não resuma "
    "excessivamente. Não crie linhas para cabeçalho, rodapé, página, INTERNA ou aprovação. "
    "Retorne somente um objeto JSON compatível com o schema solicitado."
)

JSON_OUTPUT_INSTRUCTION = (
    'Responda somente com um objeto JSON, sem markdown ou texto adicional, no formato '
    '{"linhas":[{"ordemBloco":1,"itemPadrao":"","descricao":"","tipoTarefa":"Execução",'
    '"subtarefaHTA":"","descricaoTarefa":""}]}. A chave raiz obrigatória é "linhas". '
    'Cada item de "linhas" deve conter "ordemBloco", "descricao" e "tipoTarefa". Para cada bloco recebido, '
    'retorne ao menos uma linha com a mesma ordemBloco; use tipoTarefa "Ignorar" somente para ruído. '
    'Os únicos valores de saída para tipoTarefa são "Padrão/Anexo", "Título/Subtítulo", "Informação" e "Execução".'
)

JSON_RETRY_INSTRUCTION = (
    'A resposta anterior é inválida. Gere novamente somente o JSON no formato solicitado. A chave raiz é "linhas" e '
    'cada objeto dentro de linhas deve usar "ordemBloco"; nunca use a chave legada "ordem".'
)

COVERAGE_RETRY_INSTRUCTION = (
    "A resposta anterior omitiu blocos. Converta somente os blocos recebidos agora e retorne ao menos uma linha para "
    "cada ordemBloco. Use exatamente o valor global do campo ordem de cada bloco, mesmo quando ele não começar em 1. "
    "Não use a posição local do lote e não crie ordens que não estejam na entrada."
)

_TIPOS_TAREFA_POR_CATEGORIA = {
    "padrao_documento": "Padrão/Anexo",
    "secao_principal": "Título/Subtítulo",
    "titulo_tabela": "Título/Subtítulo",
    "objetivo": "Informação",
    "atividade_tabela_2": "Título/Subtítulo",
    "atividade_anomalia": "Título/Subtítulo",
    "como_fazer": "Execução",
    "porque_fazer": "Informação",
}
_PALAVRAS_GENERICAS = {
    "atividade", "bloco", "contrato", "csv", "documento", "matriz", "numerada",
    "parser", "principal", "priorizacao", "regra", "secao", "subsecao",
}

OllamaProgressCallback = Callable[[str, int, int], None]


class LLMConversionError(RuntimeError):
    """Erro previsível ao transformar blocos com um provedor de IA."""


def _criar_prompt(
    blocos: list[dict[str, Any]],
    regras_parser: list[dict[str, Any]],
    exemplos_parser: list[dict[str, Any]],
    contexto: dict[str, Any],
) -> dict[str, Any]:
    orientacoes_parser = [
        {
            "categoria": regra.get("categoria"),
            "escopo": regra.get("escopo"),
            "tipoTarefa": regra.get("tipo_tarefa"),
        }
        for regra in regras_parser
    ]
    exemplos_compactos = [
        {
            "entrada": exemplo.get("exemplo_entrada"),
            "saida": exemplo.get("exemplo_saida_json"),
        }
        for exemplo in exemplos_parser
    ]
    blocos_para_prompt = [
        {
            "ordem": bloco["ordem"],
            "texto": bloco.get("texto", ""),
            "itemPadraoDetectado": bloco.get("itemPadraoDetectado", ""),
            "categoria": bloco.get("categoria", "geral"),
            "escopo": bloco.get("escopo", "documento_principal"),
            "contextoTarefa": bloco.get("contextoTarefa", {}),
            "tipoTarefaSugerido": (bloco.get("orientacao_parser") or {}).get("tipoTarefa"),
        }
        for bloco in blocos
    ]
    return {
        "contexto_arquivo": contexto.get("filename", ""),
        "file_order": contexto.get("file_order"),
        "instrucao": (
            "Converta todos os blocos na ordem recebida. Cada linha deve informar ordemBloco igual ao campo ordem "
            "do bloco de origem. Um bloco pode gerar várias linhas, mas nenhum bloco pode ficar sem linha. "
            "A orientacao_parser indica a regra que correspondeu ao trecho; siga-a quando existir. Use itemPadraoDetectado "
            "somente na linha de título da seção, removendo a numeração do início da descricao; para linhas de conteúdo "
            "da mesma seção deixe itemPadrao vazio. Para tarefas de execução, preencha subtarefaHTA com a ação curta e "
            "descricaoTarefa com o detalhamento explícito no PDF; nos demais tipos, deixe esses dois campos vazios."
        ),
        "orientacoes_parser": orientacoes_parser,
        "exemplos_parser": exemplos_compactos,
        "requisitos_conteudo": (
            "Cada texto de saída precisa ser comprovável pelo bloco de origem. Nunca gere nomes de regras, "
            "categorias, contratos, metadados ou exemplos do parser. Não repita frases. Em tabela operacional, "
            "a atividade é Título/Subtítulo, COMO FAZER é Execução e PORQUE FAZER é Informação."
        ),
        "ordensBlocoPermitidas": [bloco["ordem"] for bloco in blocos],
        "blocos": blocos_para_prompt,
    }


def _matriz_de_conteudo_json(conteudo: str) -> MatrizOutput:
    texto = conteudo.strip()
    if texto.startswith("```"):
        texto = texto.split("\n", maxsplit=1)[1].rsplit("```", maxsplit=1)[0].strip()
    try:
        conteudo_json = json.loads(texto)
        linhas = conteudo_json.get("linhas") if isinstance(conteudo_json, dict) else None
        if isinstance(linhas, list):
            for linha in linhas:
                if isinstance(linha, dict) and "ordemBloco" not in linha and "ordem" in linha:
                    linha["ordemBloco"] = linha.pop("ordem")
        return MatrizOutput.model_validate(conteudo_json)
    except ValueError as exc:
        raise LLMConversionError(
            'O provedor de IA retornou um JSON fora do formato esperado. A resposta deve conter a chave "linhas".'
        ) from exc


def _validar_cobertura_dos_blocos(blocos: list[dict[str, Any]], matriz: MatrizOutput) -> None:
    ordens_esperadas = {bloco["ordem"] for bloco in blocos}
    ordens_recebidas = {linha.ordemBloco for linha in matriz.linhas}
    ordens_desconhecidas = ordens_recebidas - ordens_esperadas
    ordens_ausentes = ordens_esperadas - ordens_recebidas
    if ordens_desconhecidas or ordens_ausentes:
        detalhes: list[str] = []
        if ordens_ausentes:
            detalhes.append(f"blocos sem saída: {sorted(ordens_ausentes)}")
        if ordens_desconhecidas:
            detalhes.append(f"ordens inexistentes: {sorted(ordens_desconhecidas)}")
        raise LLMConversionError("A IA não cobriu todos os blocos do parser (" + "; ".join(detalhes) + ").")


def _obter_blocos_sem_saida(blocos: list[dict[str, Any]], matriz: MatrizOutput) -> list[dict[str, Any]]:
    ordens_recebidas = {linha.ordemBloco for linha in matriz.linhas}
    return [bloco for bloco in blocos if bloco["ordem"] not in ordens_recebidas]


def _normalizar_ordens_da_resposta(blocos: list[dict[str, Any]], matriz: MatrizOutput) -> MatrizOutput:
    """Converte índices locais que alguns modelos retornam para a ordem global do PDF."""
    ordens_esperadas = [bloco["ordem"] for bloco in blocos]
    conjunto_ordens_esperadas = set(ordens_esperadas)
    resposta_usa_indices_locais = (
        ordens_esperadas != list(range(1, len(blocos) + 1))
        and any(
            linha.ordemBloco not in conjunto_ordens_esperadas and 1 <= linha.ordemBloco <= len(blocos)
            for linha in matriz.linhas
        )
    )
    linhas_normalizadas: list[MatrizLinha] = []

    for linha in matriz.linhas:
        ordem_recebida = linha.ordemBloco
        if resposta_usa_indices_locais and 1 <= ordem_recebida <= len(blocos):
            linhas_normalizadas.append(linha.model_copy(update={"ordemBloco": ordens_esperadas[ordem_recebida - 1]}))
        elif ordem_recebida in conjunto_ordens_esperadas:
            linhas_normalizadas.append(linha)
        else:
            logger.info(
                "Descartando linha da IA com ordemBloco inexistente ordem=%s esperadas=%s",
                ordem_recebida,
                ordens_esperadas,
            )

    return MatrizOutput(linhas=linhas_normalizadas)


def _criar_linha_de_fallback(bloco: dict[str, Any]) -> MatrizLinha:
    tipo_sugerido = (bloco.get("orientacao_parser") or {}).get("tipoTarefa")
    tipo_tarefa = (
        tipo_sugerido
        if tipo_sugerido in {"Padrão/Anexo", "Título/Subtítulo", "Informação", "Execução", "Ignorar"}
        else _TIPOS_TAREFA_POR_CATEGORIA.get(bloco.get("categoria"), "Informação")
    )
    if bloco.get("listaAgrupada"):
        descricao = "\n".join(
            " ".join(linha.split())
            for linha in str(bloco.get("texto") or "").splitlines()
            if linha.strip()
        )
    else:
        descricao = " ".join(str(bloco.get("texto") or "").split())
    if not descricao:
        descricao = "Bloco sem texto extraível no PDF."
    if bloco.get("categoria") == "padrao_documento":
        correspondencia = re.match(
            r"^((?:PE|PG|PR|PP)-[A-Z0-9]+-\d{5})\s*[-–—]\s*Versão\s*([0-9.]+)\s*[-–—]\s*(?:Padrão\s+Ativo\s*)?(.*)$",
            descricao,
            re.IGNORECASE,
        )
        item_padrao = (
            f"{correspondencia.group(1)}-{correspondencia.group(2)} - {correspondencia.group(3).strip()}"
            if correspondencia
            else descricao
        )
        return MatrizLinha(
            ordemBloco=bloco["ordem"],
            itemPadrao=item_padrao,
            descricao="",
            tipoTarefa="Padrão/Anexo",
        )
    if bloco.get("categoria") == "cabecalho_tabela":
        return MatrizLinha(ordemBloco=bloco["ordem"], descricao=descricao, tipoTarefa="Ignorar")
    contexto_tarefa = bloco.get("contextoTarefa") or {}
    if bloco.get("categoria") == "atividade_tabela_2":
        descricao = re.sub(r"^\s*\d+\s*[-–—.]\s*", "", descricao)
        descricao = re.split(
            r"\s+(?=(?:Técnico|Operador(?:a)?|P\.P\.N\.T|Boletim|Conforme)\b)",
            descricao,
            maxsplit=1,
        )[0].strip()
        item_padrao = str(contexto_tarefa.get("itemPadrao") or "")
        return MatrizLinha(
            ordemBloco=bloco["ordem"],
            itemPadrao=item_padrao,
            descricao=descricao,
            tipoTarefa="Título/Subtítulo",
            subtarefaHTA=str(contexto_tarefa.get("subtarefaHTA") or ""),
            descricaoTarefa=f"{descricao} ({item_padrao})" if item_padrao else descricao,
        )
    if bloco.get("categoria") == "como_fazer" and contexto_tarefa:
        descricao_tarefa = re.sub(r"^\s*COMO FAZER\s*:\s*", "", descricao, flags=re.IGNORECASE)
        return MatrizLinha(
            ordemBloco=bloco["ordem"],
            itemPadrao=str(contexto_tarefa.get("itemPadrao") or ""),
            descricao=descricao,
            tipoTarefa="Execução",
            subtarefaHTA=f"{str(contexto_tarefa.get('subtarefaHTA') or '').rstrip('.')}.1.",
            descricaoTarefa=descricao_tarefa,
        )
    return MatrizLinha(ordemBloco=bloco["ordem"], descricao=descricao, tipoTarefa=tipo_tarefa)


def _criar_linhas_de_fallback(bloco: dict[str, Any]) -> list[MatrizLinha]:
    """Preserva a estrutura mínima do PDF quando a IA não cobre um bloco."""
    categoria = bloco.get("categoria")
    linhas_fonte = [linha.strip() for linha in str(bloco.get("texto") or "").splitlines() if linha.strip()]
    if (
        (bloco.get("tituloEstrutural") or categoria in {"secao_principal", "subsecao_numerada"})
        and categoria not in {"atividade_tabela_2", "atividade_anomalia"}
        and linhas_fonte
    ):
        item_padrao = str(bloco.get("itemPadraoDetectado") or "")
        descricao_titulo = re.sub(
            r"^\s*\d+(?:\.\d+)*\.?\s*",
            "",
            linhas_fonte[0],
        ).strip()
        linhas = [
            MatrizLinha(
                ordemBloco=bloco["ordem"],
                itemPadrao=item_padrao,
                descricao=descricao_titulo or linhas_fonte[0],
                tipoTarefa="Título/Subtítulo",
            )
        ]
        conteudo = " ".join(linhas_fonte[1:]).strip()
        if conteudo:
            linhas.append(MatrizLinha(ordemBloco=bloco["ordem"], descricao=conteudo, tipoTarefa="Informação"))
        return linhas
    if categoria == "titulo_tabela" and linhas_fonte:
        return [
            MatrizLinha(
                ordemBloco=bloco["ordem"],
                descricao=linhas_fonte[0],
                tipoTarefa="Título/Subtítulo",
            )
        ]
    if categoria == "como_fazer" and bloco.get("contextoTarefa"):
        linha_base = _criar_linha_de_fallback(bloco)
        acoes = [
            acao.strip(" ;")
            for acao in re.split(r"(?:[;.]?\s*[•·]\s*)", linha_base.descricaoTarefa)
            if acao.strip(" ;")
        ]
        subtarefa_base = str((bloco.get("contextoTarefa") or {}).get("subtarefaHTA") or "").rstrip(".")
        return [
            linha_base.model_copy(
                update={
                    "descricao": f"COMO FAZER: {acao}" if indice == 1 else f"·{acao}",
                    "subtarefaHTA": f"{subtarefa_base}.{indice}.",
                    "descricaoTarefa": acao,
                }
            )
            for indice, acao in enumerate(acoes, start=1)
        ]
    return [_criar_linha_de_fallback(bloco)]


def _bloco_tem_contrato_deterministico(bloco: dict[str, Any]) -> bool:
    categoria = bloco.get("categoria")
    return bool(
        bloco.get("tituloEstrutural")
        or bloco.get("listaAgrupada")
        or categoria
        in {
            "padrao_documento",
            "titulo_tabela",
            "atividade_tabela_2",
            "cabecalho_tabela",
            "objetivo",
            "aplicacao",
            "tabela_tecnica",
            "definicoes",
            "nao_aplicavel",
        }
        or (categoria in {"como_fazer", "porque_fazer"} and bloco.get("contextoTarefa"))
    )


def _normalizar_texto_para_fundamentacao(valor: str) -> str:
    texto = unicodedata.normalize("NFKD", valor)
    texto = "".join(caractere for caractere in texto if not unicodedata.combining(caractere))
    return " ".join(re.findall(r"[a-z0-9]+", texto.lower()))


def _linha_e_fundamentada_no_bloco(linha: MatrizLinha, bloco: dict[str, Any]) -> bool:
    descricao = _normalizar_texto_para_fundamentacao(linha.descricao)
    fonte = _normalizar_texto_para_fundamentacao(str(bloco.get("texto") or ""))
    if not descricao or not fonte:
        return False
    if descricao in fonte:
        return True
    palavras_descricao = {palavra for palavra in descricao.split() if len(palavra) >= 4}
    palavras_relevantes = palavras_descricao - _PALAVRAS_GENERICAS
    if not palavras_relevantes:
        return False
    return len(palavras_relevantes & set(fonte.split())) / len(palavras_relevantes) >= 0.5


def _remover_linhas_nao_fundamentadas(blocos: list[dict[str, Any]], matriz: MatrizOutput) -> MatrizOutput:
    blocos_por_ordem = {bloco["ordem"]: bloco for bloco in blocos}
    linhas = []
    for linha in matriz.linhas:
        bloco = blocos_por_ordem.get(linha.ordemBloco)
        if bloco and _linha_e_fundamentada_no_bloco(linha, bloco):
            linhas.append(linha)
        else:
            logger.info("Descartando linha da IA sem fundamentação no PDF ordemBloco=%s", linha.ordemBloco)
    return MatrizOutput(linhas=linhas)


def _preencher_item_padrao_detectado(blocos: list[dict[str, Any]], matriz: MatrizOutput) -> MatrizOutput:
    blocos_por_ordem = {bloco["ordem"]: bloco for bloco in blocos}
    linhas_com_item: list[MatrizLinha] = []

    for linha in matriz.linhas:
        bloco = blocos_por_ordem.get(linha.ordemBloco, {})
        item_padrao = bloco.get("itemPadraoDetectado")
        if linha.tipoTarefa != "Título/Subtítulo" or linha.itemPadrao or not item_padrao:
            linhas_com_item.append(linha)
            continue

        descricao_sem_item = re.sub(
            rf"^\s*{re.escape(item_padrao)}\s*(?:[-–—]\s*)?",
            "",
            linha.descricao,
        ).strip()
        linhas_com_item.append(
            linha.model_copy(
                update={
                    "itemPadrao": item_padrao,
                    "descricao": descricao_sem_item or linha.descricao,
                }
            )
        )

    return MatrizOutput(linhas=linhas_com_item)


def _converter_com_openai(prompt_usuario: dict[str, Any]) -> MatrizOutput:
    client = get_openai_client()
    if client is None:
        raise LLMConversionError("OPENAI_API_KEY não está configurada no backend.")

    try:
        response = client.responses.parse(
            model=get_settings().openai_model,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(prompt_usuario, ensure_ascii=False)},
            ],
            text_format=MatrizOutput,
        )
        resultado = response.output_parsed
        if resultado is None:
            raise LLMConversionError("A OpenAI não retornou uma saída estruturada.")
        return MatrizOutput.model_validate(resultado)
    except LLMConversionError:
        raise
    except Exception as exc:
        raise LLMConversionError("Falha ao obter JSON estruturado da OpenAI.") from exc


def _solicitar_ollama_em_stream(
    endpoint: str,
    payload: dict[str, Any],
    timeout_seconds: int,
    on_progress: OllamaProgressCallback | None,
    max_response_characters: int | None = None,
    max_request_seconds: int | None = None,
) -> str:
    if on_progress:
        on_progress("conectando", 0, 0)

    partes_de_resposta: list[str] = []
    trechos_recebidos = 0
    caracteres_recebidos = 0
    ultimo_status_em = float("-inf")
    inicio_requisicao = time.monotonic()
    payload_com_stream = {**payload, "stream": True}

    with httpx.stream("POST", endpoint, json=payload_com_stream, timeout=timeout_seconds) as response:
        response.raise_for_status()
        if on_progress:
            on_progress("aguardando_resposta", 0, 0)
        for linha in response.iter_lines():
            dados = linha.removeprefix("data: ").strip() if linha.startswith("data: ") else linha.strip()
            if not dados:
                continue
            if dados == "[DONE]":
                break

            evento = json.loads(dados)
            if not isinstance(evento, dict):
                continue
            if "error" in evento:
                raise LLMConversionError(f"Ollama retornou um erro: {evento['error']}")

            escolhas = evento.get("choices", [])
            if not escolhas:
                continue
            primeira_escolha = escolhas[0]
            delta = primeira_escolha.get("delta") or primeira_escolha.get("message") or {}
            if not isinstance(delta, dict):
                continue
            conteudo = delta.get("content") or ""
            raciocinio = delta.get("reasoning_content") or delta.get("reasoning") or ""
            agora = time.monotonic()
            if max_request_seconds and agora - inicio_requisicao > max_request_seconds:
                raise LLMConversionError(
                    f"Ollama excedeu o limite seguro de {max_request_seconds} segundos para um lote."
                )

            if raciocinio and on_progress and agora - ultimo_status_em >= 1:
                on_progress("raciocinando", trechos_recebidos, caracteres_recebidos)
                ultimo_status_em = agora
            if not conteudo:
                continue

            partes_de_resposta.append(conteudo)
            trechos_recebidos += 1
            caracteres_recebidos += len(conteudo)
            if max_response_characters and caracteres_recebidos > max_response_characters:
                raise LLMConversionError(
                    f"Ollama excedeu o limite seguro de {max_response_characters} caracteres na resposta."
                )
            if on_progress and (trechos_recebidos == 1 or agora - ultimo_status_em >= 1):
                on_progress("gerando_resposta", trechos_recebidos, caracteres_recebidos)
                ultimo_status_em = agora

    if on_progress:
        on_progress("resposta_completa", trechos_recebidos, caracteres_recebidos)
    return "".join(partes_de_resposta)


def _converter_com_ollama(
    prompt_usuario: dict[str, Any], on_progress: OllamaProgressCallback | None = None
) -> MatrizOutput:
    settings = get_settings()
    endpoint = f"{settings.ollama_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": settings.ollama_model,
        "messages": [
            {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{JSON_OUTPUT_INSTRUCTION}"},
            {"role": "user", "content": json.dumps(prompt_usuario, ensure_ascii=False)},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }

    try:
        content = _solicitar_ollama_em_stream(
            endpoint,
            payload,
            settings.ollama_timeout_seconds,
            on_progress,
            settings.ollama_max_response_characters,
            settings.ollama_max_request_seconds,
        )
        try:
            return _matriz_de_conteudo_json(content)
        except LLMConversionError:
            if on_progress:
                on_progress("corrigindo_formato", 0, 0)
            retry_payload = {
                **payload,
                "messages": [
                    *payload["messages"],
                    {"role": "assistant", "content": content},
                    {"role": "user", "content": JSON_RETRY_INSTRUCTION},
                ],
            }
            retry_content = _solicitar_ollama_em_stream(
                endpoint,
                retry_payload,
                settings.ollama_timeout_seconds,
                on_progress,
                settings.ollama_max_response_characters,
                settings.ollama_max_request_seconds,
            )
            return _matriz_de_conteudo_json(retry_content)
    except httpx.ConnectError as exc:
        raise LLMConversionError(
            "Ollama não está disponível. Inicie o Ollama e execute o download do modelo configurado."
        ) from exc
    except (httpx.HTTPError, AttributeError, KeyError, IndexError, TypeError, ValueError) as exc:
        logger.exception("Falha ao processar a resposta em streaming do Ollama.")
        raise LLMConversionError("Falha ao obter JSON estruturado do Ollama.") from exc


def _converter_prompt(
    prompt_usuario: dict[str, Any], on_progress: OllamaProgressCallback | None = None
) -> MatrizOutput:
    if get_settings().llm_provider == "ollama":
        return _converter_com_ollama(prompt_usuario, on_progress)
    return _converter_com_openai(prompt_usuario)


def converter_blocos_com_ia(
    blocos: list[dict[str, Any]],
    regras_parser: list[dict[str, Any]],
    exemplos_parser: list[dict[str, Any]],
    contexto: dict[str, Any],
    on_progress: OllamaProgressCallback | None = None,
) -> list[dict[str, str]]:
    """Converte um lote pelo provedor de IA configurado."""
    blocos_deterministicos = [bloco for bloco in blocos if _bloco_tem_contrato_deterministico(bloco)]
    blocos_ia = [bloco for bloco in blocos if not _bloco_tem_contrato_deterministico(bloco)]
    matriz = MatrizOutput(
        linhas=[
            linha
            for bloco in blocos_deterministicos
            for linha in _criar_linhas_de_fallback(bloco)
        ]
    )

    if blocos_ia:
        prompt_usuario = _criar_prompt(blocos_ia, regras_parser, exemplos_parser, contexto)
        try:
            matriz_ia = _normalizar_ordens_da_resposta(
                blocos_ia,
                _converter_prompt(prompt_usuario, on_progress),
            )
        except LLMConversionError as exc:
            logger.warning("Falha da IA; aplicando fallback do parser erro=%s", exc)
            matriz_ia = MatrizOutput(linhas=[])
        matriz_ia = _remover_linhas_nao_fundamentadas(blocos_ia, matriz_ia)

        blocos_sem_saida = _obter_blocos_sem_saida(blocos_ia, matriz_ia)
        if blocos_sem_saida:
            if on_progress:
                on_progress("corrigindo_cobertura", 0, 0)
            prompt_correcao = _criar_prompt(blocos_sem_saida, regras_parser, exemplos_parser, contexto)
            prompt_correcao["instrucao"] = COVERAGE_RETRY_INSTRUCTION
            try:
                matriz_correcao = _normalizar_ordens_da_resposta(
                    blocos_sem_saida,
                    _converter_prompt(prompt_correcao, on_progress),
                )
            except LLMConversionError as exc:
                logger.warning("Recuperação da IA falhou; aplicando fallback erro=%s", exc)
                matriz_correcao = MatrizOutput(linhas=[])
            matriz_correcao = _remover_linhas_nao_fundamentadas(blocos_sem_saida, matriz_correcao)
            matriz_ia = MatrizOutput(linhas=[*matriz_ia.linhas, *matriz_correcao.linhas])

        blocos_sem_saida = _obter_blocos_sem_saida(blocos_ia, matriz_ia)
        if blocos_sem_saida:
            logger.warning(
                "IA não retornou saída para blocos após recuperação; aplicando fallback do parser ordens=%s",
                [bloco["ordem"] for bloco in blocos_sem_saida],
            )
            matriz_ia = MatrizOutput(
                linhas=[
                    *matriz_ia.linhas,
                    *[
                        linha
                        for bloco in blocos_sem_saida
                        for linha in _criar_linhas_de_fallback(bloco)
                    ],
                ]
            )
        matriz = MatrizOutput(linhas=[*matriz.linhas, *matriz_ia.linhas])

    ordem_original = {bloco["ordem"]: indice for indice, bloco in enumerate(blocos)}
    matriz = MatrizOutput(
        linhas=sorted(matriz.linhas, key=lambda linha: ordem_original.get(linha.ordemBloco, len(blocos)))
    )

    matriz = _preencher_item_padrao_detectado(blocos, matriz)
    _validar_cobertura_dos_blocos(blocos, matriz)
    return [
        linha.model_dump()
        for linha in matriz.linhas
        if linha.descricao.strip() or (linha.tipoTarefa == "Padrão/Anexo" and linha.itemPadrao.strip())
    ]
