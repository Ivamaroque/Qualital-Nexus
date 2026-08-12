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
    "Você é um conversor técnico do Qualital Nexus. Sua função é converter blocos de documentos "
    "técnicos em linhas para a Matriz de Priorização. Siga as regras do parser, os exemplos "
    "do parser e preserve a granularidade do documento. Não invente conteúdo. Não resuma "
    "excessivamente. Quando um parágrafo contiver várias ações explícitas, gere uma linha de Execução "
    "para cada ação e repita a descrição integral do bloco em todas elas. Em descricaoTarefa, preserve "
    "obrigatoriamente o verbo, o objeto, as condições, os limites e as referências da ação. Não use "
    "pronomes vagos quando o objeto estiver explícito no bloco. Não crie linhas para "
    "cabeçalho, rodapé, página, INTERNA ou aprovação. "
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
    "atividade_anomalia": "Informação",
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
            "secaoContextual": bloco.get("secaoContextual", ""),
            "tituloEstrutural": bool(bloco.get("tituloEstrutural")),
            "listaAgrupada": bool(bloco.get("listaAgrupada")),
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
            "exatamente como recebido, inclusive prefixos e pontos finais; nunca renumere itens. Use-o somente na linha de "
            "título da seção, removendo apenas a numeração do início da descricao; para linhas de conteúdo "
            "da mesma seção deixe itemPadrao vazio. Para cada ação explícita, gere uma linha Execução, repita em descricao "
            "o texto integral do bloco sem resumir nem parafrasear, use descricaoTarefa no infinitivo e deixe subtarefaHTA "
            "vazio: a hierarquia numérica "
            "será atribuída na consolidação global. Nos demais tipos, deixe subtarefaHTA e descricaoTarefa vazios."
        ),
        "orientacoes_parser": orientacoes_parser,
        "exemplos_parser": exemplos_compactos,
        "requisitos_conteudo": (
            "Cada texto de saída precisa ser comprovável pelo bloco de origem. Nunca gere nomes de regras, "
            "categorias, contratos, metadados, rótulos isolados de telas ou exemplos do parser. Não repita frases. "
            "Uma descrição informativa deve preservar literalmente o conteúdo de origem. Em tabela operacional, "
            "a atividade é Título/Subtítulo, COMO FAZER é Execução e PORQUE FAZER é Informação. Só use Padrão/Anexo "
            "quando a categoria do bloco indicar um documento ou anexo real; referências a códigos PE dentro de frases "
            "continuam como Informação ou Execução."
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
    """Converte índices locais que alguns modelos retornam para a ordem global do documento."""
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
        descricao = "Bloco sem texto extraível no documento."
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


_ACTION_VERB_RE = (
    r"(?:abra|abrir|acione|acionar|ajuste|ajustar|alinhe|alinhar|aperte|apertar|aplique|aplicar|"
    r"atue|atuar|avalie|avaliar|baixe|baixar|bloqueie|bloquear|clique|clicar|colete|coletar|"
    r"comunique|comunicar|continue|continuar|digite|digitar|escolha|escolher|feche|fechar|"
    r"informe|informar|inspecione|inspecionar|levante|levantar|observe|observar|recoloque|recolocar|"
    r"retorne|retornar|retire|retirar|suba|subir|teste|testar|utilize|utilizar|varie|variar|"
    r"confirmar|contatar|desligar|emitir|encaminhar|entrar\s+em\s+contato|estabelecer|executar|"
    r"fechar|informar|iniciar|inspecionar|instalar|liberar|manter|medir|monitorar|operar|parar|"
    r"preencher|proceder|registrar|remover|reparar|restabelecer|retirar|seguir|sinalizar|"
    r"solicitar|tomar|transportar|verificar)"
)
_GERUND_TO_INFINITIVE = {
    "acompanhando": "Acompanhar",
    "alinhando": "Alinhar",
    "atuando": "Atuar",
    "definindo": "Definir",
    "direcionando": "Direcionar",
    "informando": "Informar",
    "lendo": "Ler",
    "monitorando": "Monitorar",
    "registrando": "Registrar",
    "retirando": "Retirar",
    "seguindo": "Seguir",
    "transferindo": "Transferir",
}
_IMPERATIVE_TO_INFINITIVE = {
    "abra": "Abrir",
    "acione": "Acionar",
    "aperte": "Apertar",
    "baixe": "Baixar",
    "clique": "Clicar",
    "continue": "Continuar",
    "digite": "Digitar",
    "escolha": "Escolher",
    "feche": "Fechar",
    "informe": "Informar",
    "inspecione": "Inspecionar",
    "levante": "Levantar",
    "observe": "Observar",
    "recoloque": "Recolocar",
    "retorne": "Retornar",
    "retire": "Retirar",
    "suba": "Subir",
    "teste": "Testar",
    "utilize": "Utilizar",
    "varie": "Variar",
    "verifique": "Verificar",
}
_CONDITIONAL_PREFIX_RE = re.compile(
    r"^(?:ap[oó]s\b|antes\s+de\b|caso\b|com\s+base\b|depois\s+de\b|"
    r"durante\b|em\s+casos?\b|enquanto\b|no\s+caso\b|nos\s+casos?\b|"
    r"ocorrendo\b|para\s+(?:o|a|os|as)\b|quando\b|se\b)",
    re.IGNORECASE,
)
_TECHNICAL_NOUN_PATTERN = (
    r"(?:c[aâ]maras?|compressor(?:es)?|dutos?|equipamentos?|gasodutos?|linhas?|"
    r"sistemas?|tanques?|tubula[cç](?:[aã]o|[oõ]es)|v[aá]lvulas?|vasos?)"
)
_TECHNICAL_ENTITY_RE = re.compile(
    rf"\b(?P<article>o|a|os|as)\s+(?P<entity>{_TECHNICAL_NOUN_PATTERN}"
    r"(?:\s+(?:de|do|da|dos|das)\s+(?:\"[^\"]+\"|[\wÀ-ÿ-]+)){0,3})",
    re.IGNORECASE,
)
_TECHNICAL_NOUN_RE = re.compile(
    rf"\b(?P<entity>{_TECHNICAL_NOUN_PATTERN}"
    r"(?:\s+(?:de|do|da|dos|das)\s+(?:\"[^\"]+\"|[\wÀ-ÿ-]+)){0,3})",
    re.IGNORECASE,
)


def _texto_fonte_sem_item(bloco: dict[str, Any]) -> str:
    texto = " ".join(str(bloco.get("texto") or "").split())
    item = str(bloco.get("itemPadraoFonte") or bloco.get("itemPadraoDetectado") or "")
    if item:
        texto = re.sub(rf"^\s*{re.escape(item)}\s*(?:[-–—]\s*)?", "", texto).strip()
    return texto


def _normalizar_acao_para_infinitivo(texto: str) -> str:
    acao = texto.strip(" ;,.·")
    acao = re.sub(r"^(?:COMO\s+FAZER\s*:\s*)", "", acao, flags=re.IGNORECASE)
    modal = re.match(r"^(?:deverá|deverão|deve-se|devem-se|recomenda-se|poderá)\s+(.+)$", acao, re.IGNORECASE)
    if modal:
        acao = modal.group(1).strip()
    acao = re.sub(r"^ser\s+solicitad[oa]\b", "Solicitar", acao, flags=re.IGNORECASE)
    acao = re.sub(r"^ser\s+bloquead[oa]\b", "Bloquear", acao, flags=re.IGNORECASE)
    acao = re.sub(r"^ser\s+tomad[oa]s?\b", "Tomar", acao, flags=re.IGNORECASE)
    acao = re.sub(r"^ser\s+colocad[oa]\b", "Colocar", acao, flags=re.IGNORECASE)
    # Recupera o erro textual comum "deve-se para X, alinhar..." somente quando
    # a continuação comprova que se trata do verbo "parar", não da preposição.
    acao = re.sub(
        rf"^para\s+((?:o|a|os|as)\b[^,.;]+)(?=,\s*{_ACTION_VERB_RE}\b)",
        r"Parar \1",
        acao,
        flags=re.IGNORECASE,
    )
    primeira_palavra = acao.split(maxsplit=1)[0] if acao else ""
    infinitivo = (
        _GERUND_TO_INFINITIVE.get(primeira_palavra.lower())
        or _IMPERATIVE_TO_INFINITIVE.get(primeira_palavra.lower())
    )
    if infinitivo:
        acao = infinitivo + acao[len(primeira_palavra):]
    if acao:
        acao = acao[0].upper() + acao[1:]
    return acao.rstrip(" ;") + ("." if acao and acao[-1] not in ".!?" else "")


def _extrair_contexto_condicional(prefixo: str) -> str:
    contexto = re.sub(r"^\s*\d+(?:\.\d+)*\.?\s*", "", prefixo).strip(" ,;.")
    if not _CONDITIONAL_PREFIX_RE.match(contexto):
        return ""
    partes = contexto.rsplit(",", maxsplit=1)
    sujeito_final = partes[1].strip() if len(partes) == 2 else ""
    if len(partes) == 2 and (
        re.fullmatch(
            r"(?:o|a|os|as)\s+(?:[\wÀ-ÿ./-]+\s*){1,8}",
            sujeito_final,
            re.IGNORECASE,
        )
        or re.fullmatch(r"(?:este|esta|estes|estas)", sujeito_final, re.IGNORECASE)
    ):
        contexto = partes[0].strip()
    contexto = re.sub(
        r"(?:,\s*)?\b(?:apenas|somente|s[oó])$",
        "",
        contexto,
        flags=re.IGNORECASE,
    ).strip(" ,")
    return contexto


def _ultima_entidade_tecnica(texto: str) -> str:
    encontradas = list(_TECHNICAL_ENTITY_RE.finditer(texto))
    if encontradas:
        encontrada = encontradas[-1]
        return f"{encontrada.group('article')} {encontrada.group('entity')}"
    substantivos = list(_TECHNICAL_NOUN_RE.finditer(texto))
    if not substantivos:
        return ""
    entidade = substantivos[-1].group("entity")
    palavra = entidade.split(maxsplit=1)[0].lower()
    feminina = palavra.startswith(
        ("câmara", "camara", "linha", "tubulação", "tubulacao", "válvula", "valvula")
    )
    artigo = "a" if feminina else "o"
    if palavra.endswith("s"):
        artigo = "as" if artigo == "a" else "os"
    return f"{artigo} {entidade}"


def _anexar_contexto_condicional(acao: str, contexto: str) -> str:
    if not acao or not contexto:
        return acao
    contexto_normalizado = _normalizar_texto_para_fundamentacao(contexto)
    if contexto_normalizado and contexto_normalizado in _normalizar_texto_para_fundamentacao(acao):
        return acao
    contexto = contexto[0].lower() + contexto[1:] if contexto else contexto
    return f"{acao.rstrip('.;')}, {contexto}."


def _resolver_referencias_locais(acao: str, fonte_anterior: str) -> str:
    entidade = _ultima_entidade_tecnica(fonte_anterior)
    if not entidade:
        return acao
    acao = re.sub(r"\bque\s+a\s+mesma\b", f"que {entidade}", acao, flags=re.IGNORECASE)
    acao = re.sub(r"^Bloquear\s+em\b", f"Bloquear {entidade} em", acao, flags=re.IGNORECASE)
    return acao


def _normalizar_acao_com_contexto(texto: str) -> str:
    trecho = texto.strip(" ,;.")
    inicio_acao = re.search(rf"\b{_ACTION_VERB_RE}\b", trecho, re.IGNORECASE)
    if not inicio_acao or inicio_acao.start() == 0:
        return _normalizar_acao_para_infinitivo(trecho)
    contexto = _extrair_contexto_condicional(trecho[: inicio_acao.start()])
    if not contexto:
        return _normalizar_acao_para_infinitivo(trecho)
    acao = _normalizar_acao_para_infinitivo(trecho[inicio_acao.start() :])
    return _anexar_contexto_condicional(acao, contexto)


def _separar_acoes_coordenadas(texto: str) -> list[str]:
    partes = re.split(
        rf",\s*(?={_ACTION_VERB_RE}\b)|\s+e\s+(?={_ACTION_VERB_RE}\b)",
        texto,
        flags=re.IGNORECASE,
    )
    return [parte.strip() for parte in partes if parte.strip()]


def _extrair_acoes_explicitas(texto: str) -> list[str]:
    sentencas = re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚ])", " ".join(texto.split()))
    acoes: list[str] = []
    for sentenca in sentencas:
        sentenca = re.sub(r"^\s*[-–—•·]\s*", "", sentenca)
        if re.search(r"\bnão\s+dev(?:e|em|erá|erão)\b", sentenca, re.IGNORECASE):
            continue
        sentenca = re.sub(
            rf"\b(deve-se|dever[aá]|dever[aã]o)\s+para\s+"
            rf"((?:o|a|os|as)\b[^,.;]+)(?=,\s*{_ACTION_VERB_RE}\b)",
            r"\1 parar \2",
            sentenca,
            flags=re.IGNORECASE,
        )
        modal = re.search(r"\b(?:deverá|deverão|deve-se|devem-se|recomenda-se|poderá)\s+(.+)", sentenca, re.IGNORECASE)
        inicio = re.match(rf"^\s*{_ACTION_VERB_RE}\b.+", sentenca, re.IGNORECASE)
        acao_interna = re.search(rf"\b{_ACTION_VERB_RE}\b.+", sentenca, re.IGNORECASE)
        trecho = modal.group(1) if modal else sentenca if inicio else acao_interna.group(0) if acao_interna else ""
        if not trecho:
            continue
        inicio_trecho = (
            modal.start()
            if modal
            else inicio.start()
            if inicio
            else acao_interna.start()
            if acao_interna
            else 0
        )
        fonte_anterior = sentenca[:inicio_trecho]
        contexto = _extrair_contexto_condicional(fonte_anterior)
        for parte in _separar_acoes_coordenadas(trecho):
            acao = _normalizar_acao_para_infinitivo(parte)
            if acao:
                acao = _resolver_referencias_locais(acao, fonte_anterior)
                acao = _anexar_contexto_condicional(acao, contexto)
                acoes.append(acao)
    if len(acoes) > 1:
        # Uma remissão normativa introduz contexto; ações concretas subsequentes
        # é que se tornam subtarefas de execução independentes.
        acoes = [
            acao
            for acao in acoes
            if not re.match(r"^Seguir o que se estabelece\b", acao, re.IGNORECASE)
        ]
    return acoes


def _extrair_acoes_como_fazer(texto: str) -> list[str]:
    conteudo = re.sub(r"^\s*COMO\s+FAZER\s*:\s*", "", " ".join(texto.split()), flags=re.IGNORECASE)
    partes = [parte for parte in re.split(r"\s*[;·•]\s*", conteudo) if parte.strip()]
    expandidas: list[str] = []
    for parte in partes:
        parte = re.sub(
            r"\s+e,\s+(?=(?:ap[oó]s|antes|caso|em|no|na|nos|nas|quando|se)\b)",
            ";",
            parte,
            flags=re.IGNORECASE,
        )
        coordenadas = re.split(
            r"\s+e\s+(?=(?:registrando|atuando|informando|solicitando)\b)|\s*;\s*",
            parte,
            flags=re.IGNORECASE,
        )
        coordenadas = [acao.strip() for acao in coordenadas if acao.strip()]
        if len(coordenadas) > 1:
            ultima = coordenadas[-1]
            complemento = ultima.split(maxsplit=1)[1] if len(ultima.split(maxsplit=1)) == 2 else ""
            if complemento:
                coordenadas = [
                    f"{acao} {complemento}" if len(acao.split()) == 1 else acao
                    for acao in coordenadas
                ]
        expandidas.extend(_normalizar_acao_com_contexto(acao) for acao in coordenadas)
    return [acao for acao in expandidas if acao]


def _criar_linhas_de_fallback(bloco: dict[str, Any]) -> list[MatrizLinha]:
    """Preserva a estrutura mínima do PDF quando a IA não cobre um bloco."""
    categoria = bloco.get("categoria")
    linhas_fonte = [linha.strip() for linha in str(bloco.get("texto") or "").splitlines() if linha.strip()]
    if categoria == "anexo_documento" and linhas_fonte:
        anexo = re.match(r"^ANEXO\s+([A-Z])$", linhas_fonte[0], re.IGNORECASE)
        if anexo:
            identificador = f"Anexo {anexo.group(1).upper()}"
            return [
                MatrizLinha(
                    ordemBloco=bloco["ordem"],
                    itemPadrao=identificador,
                    descricao="",
                    tipoTarefa="Padrão/Anexo",
                ),
                MatrizLinha(
                    ordemBloco=bloco["ordem"],
                    descricao=linhas_fonte[0],
                    tipoTarefa="Título/Subtítulo",
                ),
            ]
    if categoria == "anexo_cabecalho_repetido" and linhas_fonte:
        return [
            MatrizLinha(
                ordemBloco=bloco["ordem"],
                descricao=linhas_fonte[0],
                tipoTarefa="Título/Subtítulo",
            )
        ]
    if categoria in {"cabecalho_documento_repetido", "fragmento_interface"}:
        return [MatrizLinha(ordemBloco=bloco["ordem"], descricao="", tipoTarefa="Ignorar")]
    if (
        (
            bloco.get("tituloEstrutural")
            or categoria == "secao_principal"
            or (categoria == "subsecao_numerada" and len(" ".join(linhas_fonte)) <= 120)
        )
        and categoria not in {"atividade_tabela_2", "atividade_anomalia"}
        and linhas_fonte
    ):
        item_padrao = str(bloco.get("itemPadraoDetectado") or "")
        descricao_titulo = linhas_fonte[0]
        if re.match(r"^\s*\d+[A-Z]\s*[-–—]", descricao_titulo, re.IGNORECASE):
            descricao_titulo = re.sub(
                r"^\s*\d+[A-Z]\s*[-–—]\s*",
                "",
                descricao_titulo,
                flags=re.IGNORECASE,
            ).strip()
        else:
            descricao_titulo = re.sub(
                r"^\s*\d+(?:\.\d+)*\.?\s*",
                "",
                descricao_titulo,
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
    if categoria == "tabela_tecnica" and linhas_fonte:
        descricao = "\n".join(linhas_fonte) if bloco.get("listaAgrupada") else " ".join(linhas_fonte)
        partes = re.split(
            r"\s+(?=O set, ajustado\b)|\s+(?=Os sets podem ser alterados\b)",
            descricao,
            flags=re.IGNORECASE,
        )
        return [
            MatrizLinha(ordemBloco=bloco["ordem"], descricao=parte.strip(), tipoTarefa="Informação")
            for parte in partes
            if parte.strip()
        ]
    if categoria == "definicoes" and linhas_fonte:
        descricao = " ".join(linhas_fonte)
        if re.search(r"https?://", descricao, re.IGNORECASE):
            partes = re.split(r"\s+(?=[A-Z][A-Z0-9.]{1,12}\s*[-–—])", descricao)
            return [
                MatrizLinha(ordemBloco=bloco["ordem"], descricao=parte.strip(), tipoTarefa="Informação")
                for parte in partes
                if parte.strip()
            ]
    if categoria == "como_fazer" and bloco.get("contextoTarefa"):
        linha_base = _criar_linha_de_fallback(bloco)
        acoes = _extrair_acoes_como_fazer(linha_base.descricaoTarefa) or [linha_base.descricaoTarefa]
        separadores_visuais = re.search(r"[;·•]", linha_base.descricaoTarefa) is not None
        subtarefa_base = str((bloco.get("contextoTarefa") or {}).get("subtarefaHTA") or "").rstrip(".")
        return [
            linha_base.model_copy(
                update={
                    "descricao": (
                        f"COMO FAZER: {acao}" if indice == 1 else f"·{acao}"
                    )
                    if separadores_visuais
                    else linha_base.descricao,
                    "subtarefaHTA": f"{subtarefa_base}.{indice}.",
                    "descricaoTarefa": acao,
                }
            )
            for indice, acao in enumerate(acoes, start=1)
        ]
    if categoria == "instrucao_operacional":
        descricao = _texto_fonte_sem_item(bloco)
        item_padrao = str(bloco.get("itemPadraoDetectado") or bloco.get("secaoContextual") or "")
        acoes = (
            [_normalizar_acao_para_infinitivo(descricao)]
            if bloco.get("acaoUnica")
            else _extrair_acoes_explicitas(descricao)
        )
        if not acoes:
            return [
                MatrizLinha(
                    ordemBloco=bloco["ordem"],
                    itemPadrao=item_padrao,
                    descricao=descricao,
                    tipoTarefa="Informação",
                )
            ]
        return [
            MatrizLinha(
                ordemBloco=bloco["ordem"],
                itemPadrao=item_padrao,
                descricao=descricao,
                tipoTarefa="Execução",
                descricaoTarefa=acao,
            )
            for acao in acoes
        ]
    linha = _criar_linha_de_fallback(bloco)
    if categoria in {"geral", "subsecao_numerada", "item_numerado_anexo"} and bloco.get("itemPadraoDetectado"):
        return [
            linha.model_copy(
                update={
                    "itemPadrao": str(bloco["itemPadraoDetectado"]),
                    "descricao": _texto_fonte_sem_item(bloco),
                }
            )
        ]
    if bloco.get("listaAgrupada"):
        lista_numerada = re.match(r"^\s*(\d+)\s*(-\s+.+)", linha.descricao, re.DOTALL)
        if lista_numerada:
            return [
                linha.model_copy(
                    update={
                        "itemPadrao": lista_numerada.group(1),
                        "descricao": lista_numerada.group(2),
                    }
                )
            ]
    return [linha]


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
            "geral",
            "lista_informativa",
            "observacao",
            "recursos_necessarios",
            "registros",
            "responsavel_unidade",
            "set_intertravamento",
            "subsecao_numerada",
            "anexo_documento",
            "anexo_cabecalho_repetido",
            "cabecalho_documento_repetido",
            "fragmento_interface",
            "item_numerado_anexo",
            "instrucao_operacional",
        }
        or (categoria in {"como_fazer", "porque_fazer"} and bloco.get("contextoTarefa"))
    )


def _normalizar_texto_para_fundamentacao(valor: str) -> str:
    texto = unicodedata.normalize("NFKD", valor)
    texto = "".join(caractere for caractere in texto if not unicodedata.combining(caractere))
    return " ".join(re.findall(r"[a-z0-9]+", texto.lower()))


def _texto_e_fundamentado_no_bloco(valor: str, fonte: str, limite: float = 0.5) -> bool:
    texto = _normalizar_texto_para_fundamentacao(valor)
    fonte_normalizada = _normalizar_texto_para_fundamentacao(fonte)
    if not texto or not fonte_normalizada:
        return False
    if texto in fonte_normalizada:
        return True
    palavras_texto = {palavra for palavra in texto.split() if len(palavra) >= 4}
    palavras_relevantes = palavras_texto - _PALAVRAS_GENERICAS
    if not palavras_relevantes:
        return False
    radicais_texto = {palavra[:5] for palavra in palavras_relevantes}
    radicais_fonte = {
        palavra[:5]
        for palavra in fonte_normalizada.split()
        if len(palavra) >= 4 and palavra not in _PALAVRAS_GENERICAS
    }
    return len(radicais_texto & radicais_fonte) / len(radicais_texto) >= limite


def _linha_e_fundamentada_no_bloco(linha: MatrizLinha, bloco: dict[str, Any]) -> bool:
    fonte = str(bloco.get("texto") or "")
    if not _texto_e_fundamentado_no_bloco(linha.descricao, fonte):
        return False
    if linha.tipoTarefa != "Execução" or not linha.descricaoTarefa.strip():
        return True
    return _texto_e_fundamentado_no_bloco(linha.descricaoTarefa, fonte, limite=0.45)


def _remover_linhas_nao_fundamentadas(blocos: list[dict[str, Any]], matriz: MatrizOutput) -> MatrizOutput:
    blocos_por_ordem = {bloco["ordem"]: bloco for bloco in blocos}
    linhas = []
    for linha in matriz.linhas:
        bloco = blocos_por_ordem.get(linha.ordemBloco)
        if bloco and _linha_e_fundamentada_no_bloco(linha, bloco):
            linhas.append(linha)
        else:
            logger.info("Descartando linha da IA sem fundamentação no documento ordemBloco=%s", linha.ordemBloco)
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


def _garantir_granularidade_operacional(blocos: list[dict[str, Any]], matriz: MatrizOutput) -> MatrizOutput:
    """Impede que a IA comprima várias ações explícitas em uma única linha."""
    por_ordem: dict[int, list[MatrizLinha]] = {}
    for linha in matriz.linhas:
        por_ordem.setdefault(linha.ordemBloco, []).append(linha)

    consolidadas: list[MatrizLinha] = []
    for bloco in blocos:
        ordem = bloco["ordem"]
        existentes = por_ordem.get(ordem, [])
        if bloco.get("categoria") != "instrucao_operacional":
            consolidadas.extend(existentes)
            continue

        fallback = _criar_linhas_de_fallback(bloco)
        execucoes_esperadas = [linha for linha in fallback if linha.tipoTarefa == "Execução"]
        execucoes_ia = [
            linha
            for linha in existentes
            if linha.tipoTarefa == "Execução" and linha.descricaoTarefa.strip()
        ]
        if len(execucoes_ia) < len(execucoes_esperadas):
            consolidadas.extend(fallback)
            continue

        descricao = _texto_fonte_sem_item(bloco)
        item = str(bloco.get("itemPadraoDetectado") or bloco.get("secaoContextual") or "")
        consolidadas.extend(
            linha.model_copy(
                update={
                    "itemPadrao": item,
                    "descricao": descricao,
                    "subtarefaHTA": "",
                }
            )
            for linha in execucoes_ia[: len(execucoes_esperadas)]
        )
    return MatrizOutput(linhas=consolidadas)


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

    matriz = _garantir_granularidade_operacional(blocos, matriz)
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
