"""Segmenta o texto e monta blocos contextualizados para o pipeline de IA."""

import re

from app.services.pdf_text_service import (
    _ACTION_IMPERATIVE_RE,
    _ACTION_START_RE,
    _ANEXO_DOCUMENTO_RE,
    _ANEXO_LETTER_ITEM_RE,
    _ANEXO_OPERATIONAL_HEADING_RE,
    _ATIVIDADE_TABELA_RE,
    _FIGURE_CAPTION_RE,
    _IMAGE_MARKER_RE,
    _LETTERED_LIST_ITEM_RE,
    _LIST_ITEM_RE,
    _MAX_BLOCK_CHARACTERS,
    _NOTICE_RE,
    _OBSERVATION_RE,
    _OPERATIONAL_RESPONSIBLE_CELL_RE,
    _OPERATIONAL_STAGE_RE,
    _OPERATIONAL_TABLE_ROW_RE,
    _PROCESS_REFERENCE_RE,
    _SECTION_RE,
    _TABLE_EXECUTOR_MARKER_RE,
    _TABLE_RE,
    _TABLE_REGISTER_SUFFIX_RE,
    _TECHNICAL_MARKER_RE,
    _agrupar_cabecalho_documento,
    _agrupar_fragmentos_logicos,
    _aplicar_hierarquia_local_do_anexo,
    _conteudo_item_numerado,
    _eh_titulo_estrutural,
    _formatar_item_do_anexo,
    _identificar_anexo_pelo_nome,
    _inicia_secao_documento_fora_da_tabela,
    _is_image_marker,
    _item_numerado_da_linha,
    _item_numerado_tem_acao_explicita,
    _juntar_linhas_do_bloco,
    _linha_numerada_e_instrucao,
    _marcar_sufixo_de_interface,
    _remover_sumario_inicial,
    _texto_tem_acoes_explicitas,
    detectar_categoria,
    detectar_escopo,
    extrair_item_padrao,
    extrair_palavras_chave,
)
from app.utils.text_utils import normalize_whitespace, normalized_for_match


def _expandir_linhas_especiais(texto: str) -> list[str]:
    """Separa marcadores semânticos que o PDF pode entregar na mesma linha."""
    linhas_expandidas: list[str] = []
    for linha_original in texto.splitlines():
        partes = re.split(r"\s+(?=Figura\s+\d+\s*[-–—:])", linha_original)
        for parte in partes:
            linhas_expandidas.extend(
                re.split(
                    r"\s+(?=(?:Lista\s+de\s+verificação|Observaç(?:ão|ões)\s+(?:preliminares|\d+))\s*[:.])",
                    parte,
                    flags=re.IGNORECASE,
                )
            )
    return linhas_expandidas


def _segmentar_blocos_iniciais(
    texto: str,
    *,
    anexo_standalone: bool,
    fluxograma_standalone: bool,
) -> list[list[str]]:
    """Cria blocos visuais antes das regras contextuais de classificação."""
    blocos: list[list[str]] = []
    atual: list[str] = []
    escopo_tabela_linear: str | None = None

    for linha in _expandir_linhas_especiais(texto):
        if _is_image_marker(linha):
            if atual:
                blocos.append(atual)
                atual = []
            blocos.append([normalize_whitespace(linha)])
            continue
        if not linha.strip():
            if atual:
                blocos.append(atual)
                atual = []
            continue

        escopo_da_linha = detectar_escopo(linha)
        if escopo_da_linha in {"tabela_2", "tabela_5"}:
            escopo_tabela_linear = escopo_da_linha
        elif escopo_tabela_linear and _inicia_secao_documento_fora_da_tabela(
            linha
        ):
            escopo_tabela_linear = None

        titulo_estrutural = _eh_titulo_estrutural(linha)
        titulo_tabela = _TABLE_RE.match(linha) is not None
        item_de_tabela = (
            escopo_tabela_linear == "tabela_2"
            and _ATIVIDADE_TABELA_RE.match(linha) is not None
        )
        marcador_procedimento = (
            normalized_for_match(linha).rstrip(".") == "PROCEDIMENTO"
        )
        legenda_figura = _FIGURE_CAPTION_RE.match(linha) is not None
        lista_verificacao = (
            normalized_for_match(linha).rstrip(".:") == "LISTA DE VERIFICACAO"
        )
        observacao_numerada = (
            re.match(r"^OBSERVA(?:ÇÃO|CAO)\s+\d+\s*[:.]", linha, re.IGNORECASE)
            is not None
        )
        observacao_simples = _OBSERVATION_RE.match(linha) is not None
        item_de_lista_standalone = bool(
            anexo_standalone and _LIST_ITEM_RE.match(linha)
        )
        item_de_lista_alfabetico = (
            _LETTERED_LIST_ITEM_RE.match(linha) is not None
        )
        item_de_lista_apos_secao = bool(
            atual
            and _LIST_ITEM_RE.match(linha)
            and _SECTION_RE.match(atual[0])
        )
        titulo_raiz_standalone = bool(
            anexo_standalone and re.match(r"^\s*\d+\s*[-–—]\s*\S+", linha)
        )
        inicio_de_bloco = bool(
            _SECTION_RE.match(linha)
            or titulo_tabela
            or item_de_tabela
            or item_de_lista_standalone
            or item_de_lista_alfabetico
            or item_de_lista_apos_secao
            or titulo_raiz_standalone
            or _OPERATIONAL_TABLE_ROW_RE.match(linha)
            or _OPERATIONAL_STAGE_RE.match(linha)
            or marcador_procedimento
            or legenda_figura
            or lista_verificacao
            or observacao_numerada
            or observacao_simples
            or _NOTICE_RE.match(linha)
            or _PROCESS_REFERENCE_RE.match(linha)
            or _TECHNICAL_MARKER_RE.match(linha)
            or fluxograma_standalone
        )
        if inicio_de_bloco and atual:
            blocos.append(atual)
            atual = []
        atual.append(linha)
        if titulo_estrutural or titulo_tabela or marcador_procedimento:
            blocos.append(atual)
            atual = []
            continue
        if sum(len(trecho) + 1 for trecho in atual) >= _MAX_BLOCK_CHARACTERS:
            blocos.append(atual)
            atual = []

    if atual:
        blocos.append(atual)
    return blocos


def _preparar_blocos_para_classificacao(
    texto: str,
    *,
    anexo_standalone: bool,
    fluxograma_standalone: bool,
    identificador_anexo: str,
    titulo_anexo: str,
) -> list[list[str]]:
    """Aplica agrupamentos e inclui o cabeçalho do anexo."""
    blocos = _segmentar_blocos_iniciais(
        texto,
        anexo_standalone=anexo_standalone,
        fluxograma_standalone=fluxograma_standalone,
    )
    blocos = _agrupar_fragmentos_logicos(
        blocos,
        agrupar_listas_visuais=not anexo_standalone,
    )
    blocos = _agrupar_cabecalho_documento(blocos)
    blocos = _remover_sumario_inicial(blocos)
    if not anexo_standalone:
        return blocos

    if blocos:
        primeiro_texto = _juntar_linhas_do_bloco(blocos[0])
        letras = [
            caractere for caractere in primeiro_texto if caractere.isalpha()
        ]
        primeiro_e_titulo = (
            bool(letras)
            and sum(c.isupper() for c in letras) / len(letras) >= 0.85
        )
        primeiro_e_titulo = primeiro_e_titulo and not bool(
            _SECTION_RE.match(primeiro_texto)
        )
        primeiro_e_titulo = primeiro_e_titulo and not _is_image_marker(
            primeiro_texto
        )
        if primeiro_e_titulo:
            titulo_anexo = primeiro_texto
            blocos = blocos[1:]
        elif titulo_anexo and normalized_for_match(
            primeiro_texto
        ) == normalized_for_match(titulo_anexo):
            blocos = blocos[1:]

    cabecalho_anexo = [f"ANEXO {identificador_anexo}"]
    if titulo_anexo:
        cabecalho_anexo.append(titulo_anexo)
    blocos.insert(0, cabecalho_anexo)
    return blocos


def _analisar_hierarquia_dos_blocos(
    blocos: list[list[str]],
) -> tuple[str, list[int], set[tuple[int, str]]]:
    """Mapeia anexos, itens numerados e pais que possuem subitens."""
    numero_tabela_desvios = ""
    for bloco in blocos:
        texto_bloco = _juntar_linhas_do_bloco(bloco)
        tabela_encontrada = re.match(
            r"^TABELA\s*(\d+)\b",
            normalized_for_match(texto_bloco),
        )
        if (
            tabela_encontrada
            and detectar_escopo(texto_bloco) == "tabela_desvios"
        ):
            numero_tabela_desvios = tabela_encontrada.group(1)
            break

    segmentos_de_anexo: list[int] = []
    segmento_atual = 0
    for bloco in blocos:
        primeira_linha = normalize_whitespace(bloco[0]) if bloco else ""
        if _ANEXO_DOCUMENTO_RE.match(primeira_linha):
            segmento_atual += 1
        segmentos_de_anexo.append(segmento_atual)

    itens_numerados = [
        (segmentos_de_anexo[indice], _item_numerado_da_linha(bloco[0]))
        for indice, bloco in enumerate(blocos)
        if bloco and _item_numerado_da_linha(bloco[0])
    ]
    itens_com_subitens = {
        (segmento, item)
        for segmento, item in itens_numerados
        if any(
            outro_segmento == segmento and outro.startswith(f"{item}.")
            for outro_segmento, outro in itens_numerados
            if outro != item
        )
    }
    return numero_tabela_desvios, segmentos_de_anexo, itens_com_subitens


def _classificar_blocos(
    blocos: list[list[str]],
    *,
    identificador_anexo: str,
    anexo_standalone: bool,
    fluxograma_standalone: bool,
    numero_tabela_desvios: str,
    segmentos_de_anexo: list[int],
    itens_com_subitens: set[tuple[int, str]],
) -> list[dict]:
    """Classifica os blocos mantendo o contexto acumulado durante a leitura."""
    resultado: list[dict] = []
    escopo_contextual = (
        f"anexo_fluxograma_{identificador_anexo.lower()}"
        if fluxograma_standalone
        else f"anexo_arquivo_{identificador_anexo.lower()}"
        if anexo_standalone
        else "documento_principal"
    )
    secao_contextual = ""
    atividade_contextual: dict[str, str] | None = None
    secao_principal_contextual = ""
    secao_atividade_operacional = ""
    etapa_operacional = 0
    titulo_contextual = ""
    ultimo_item_operacional = ""
    lista_tarefas_raiz = ""
    tarefa_lista_contextual = ""
    em_lista_verificacao = False
    aguardando_atividade_tabela = False
    executante_tabela_pendente = ""
    anexos_documento_vistos: set[str] = set()
    escopos_explicitos = {
        "anexo",
        "tabela_2",
        "tabela_5",
        "tabela_desvios",
        "tabelas_tecnicas",
    }
    for ordem, linhas in enumerate(blocos, start=1):
        bloco_texto = _juntar_linhas_do_bloco(linhas)
        if not bloco_texto:
            continue

        # 1. Resolve o escopo e a categoria base usando o contexto anterior.
        executante_tabela = ""
        marcador_executante = _TABLE_EXECUTOR_MARKER_RE.search(bloco_texto)
        if marcador_executante:
            executante_tabela = normalize_whitespace(
                marcador_executante.group("executante")
            )
            bloco_texto = _TABLE_EXECUTOR_MARKER_RE.sub(
                " ", bloco_texto
            ).strip()
        escopo_detectado = detectar_escopo(bloco_texto)
        if escopo_detectado == "tabela_desvios":
            tabela_encontrada = re.match(
                r"^TABELA\s*(\d+)\b", normalized_for_match(bloco_texto)
            )
            if tabela_encontrada:
                numero_tabela_desvios = tabela_encontrada.group(1)
        if fluxograma_standalone:
            escopo_contextual = (
                f"anexo_fluxograma_{identificador_anexo.lower()}"
            )
        elif anexo_standalone:
            escopo_contextual = f"anexo_arquivo_{identificador_anexo.lower()}"
        elif (
            escopo_detectado in escopos_explicitos
            or escopo_detectado.startswith("anexo_")
        ):
            escopo_contextual = escopo_detectado
        elif (
            escopo_detectado == "documento_principal"
            and not escopo_contextual.startswith(
                ("anexo", "tabela_", "tabelas_")
            )
        ):
            escopo_contextual = escopo_detectado
        elif escopo_contextual.startswith(
            ("tabela_", "tabelas_")
        ) and _inicia_secao_documento_fora_da_tabela(bloco_texto):
            escopo_contextual = "documento_principal"
        if escopo_contextual != "tabela_2":
            atividade_contextual = None
        categoria = detectar_categoria(bloco_texto)
        etapa_encontrada = _OPERATIONAL_STAGE_RE.match(bloco_texto)
        passo_operacional = _OPERATIONAL_TABLE_ROW_RE.match(bloco_texto)
        if etapa_encontrada:
            etapa_operacional = int(etapa_encontrada.group(1))
            secao_atividade_operacional = secao_contextual
            categoria = "etapa_operacional"
        elif passo_operacional:
            categoria = "passo_tabela_operacional"
        elif (
            etapa_operacional
            and linhas
            and all(
                _OPERATIONAL_RESPONSIBLE_CELL_RE.fullmatch(
                    normalize_whitespace(linha)
                )
                for linha in linhas
            )
        ):
            categoria = "fragmento_interface"
        if categoria == "anexo_documento":
            identificador_anexo = normalize_whitespace(linhas[0]).upper()
            if identificador_anexo in anexos_documento_vistos:
                categoria = "anexo_cabecalho_repetido"
            else:
                anexos_documento_vistos.add(identificador_anexo)
        elif categoria == "padrao_documento" and escopo_contextual.startswith(
            "anexo_"
        ):
            categoria = "cabecalho_documento_repetido"

        # 2. Relaciona o bloco à numeração e à hierarquia do documento.
        item_numerado_fonte = _item_numerado_da_linha(linhas[0])
        tem_subitens = (
            segmentos_de_anexo[ordem - 1],
            item_numerado_fonte,
        ) in itens_com_subitens
        resumo_anexo = (
            max(segmentos_de_anexo, default=1) > 1
            and segmentos_de_anexo[ordem - 1] == 1
        )
        instrucao_numerada = _linha_numerada_e_instrucao(
            linhas[0], tem_subitens, resumo_anexo
        )
        if categoria == "secao_principal":
            secao_principal_contextual = normalized_for_match(bloco_texto)
        elif categoria == "geral" and secao_principal_contextual.endswith(
            "OBJETIVO"
        ):
            categoria = "objetivo"
        elif categoria == "geral" and secao_principal_contextual.endswith(
            "APLICACAO"
        ):
            categoria = "aplicacao"
        elif categoria == "geral" and secao_principal_contextual.endswith(
            "DEFINICOES"
        ):
            categoria = "definicoes"
        if escopo_contextual == "tabelas_tecnicas" and categoria not in {
            "titulo_tabela",
            "cabecalho_tabela",
            "imagem",
            "legenda_figura",
        }:
            categoria = "tabela_tecnica"
        if escopo_contextual == "tabela_desvios":
            normalizado_bloco = normalized_for_match(bloco_texto)
            if normalizado_bloco == "RESULTADO ESPERADO | ACOES PARA DESVIOS":
                categoria = "cabecalho_tabela_desvios"
            elif normalizado_bloco.startswith("RESULTADO ESPERADO |"):
                categoria = "linha_tabela_desvios"
        if escopo_contextual == "tabela_2" and categoria == "secao_principal":
            categoria = "atividade_tabela_2"
        if escopo_contextual == "tabela_5" and categoria == "secao_principal":
            categoria = "item_numerado_tabela_5"
        if categoria == "geral" and _LIST_ITEM_RE.match(linhas[0]):
            if escopo_contextual == "tabela_2":
                categoria = "atividade_tabela_2"
            elif escopo_contextual == "tabela_5":
                categoria = "atividade_anomalia"
        if instrucao_numerada and escopo_contextual not in {
            "tabela_2",
            "tabela_5",
        }:
            categoria = "instrucao_operacional"
        elif (
            escopo_contextual.startswith("anexo_")
            and categoria == "subsecao_numerada"
            and not tem_subitens
            and not _ANEXO_OPERATIONAL_HEADING_RE.match(linhas[0])
        ):
            categoria = "item_numerado_anexo"
        itens_de_lista = sum(
            _LIST_ITEM_RE.match(linha) is not None for linha in linhas
        )
        lista_agrupada = (
            itens_de_lista >= 2 and escopo_contextual != "tabela_2"
        )
        if lista_agrupada:
            if categoria == "passo_tabela_operacional":
                pass
            elif escopo_contextual not in {"tabelas_tecnicas", "tabela_5"}:
                categoria = "lista_informativa"
            elif (
                categoria == "cabecalho_tabela"
                and escopo_contextual != "tabela_2"
            ):
                categoria = "tabela_tecnica"
        if (
            categoria in {"lista_informativa", "tabela_tecnica"}
            and "RESPONSAVEIS PELA EXECUCAO" in titulo_contextual
            and all(
                termo in normalized_for_match(bloco_texto)
                for termo in ("QUEM", "O QUE")
            )
        ):
            categoria = "fragmento_interface"
        item_padrao_fonte = extrair_item_padrao(bloco_texto)
        if (
            anexo_standalone
            and not item_padrao_fonte
            and re.match(r"^\s*\d+\s*[-–—]\s*\S+", bloco_texto)
        ):
            item_padrao_fonte = f"{item_numerado_fonte}-"
        item_padrao_detectado = _formatar_item_do_anexo(
            item_padrao_fonte, escopo_contextual
        )
        if categoria == "linha_tabela_desvios":
            partes_item = [
                secao_contextual.rstrip("."),
                f"Tabela {numero_tabela_desvios}".strip(),
            ]
            item_padrao_detectado = (
                ".".join(parte for parte in partes_item if parte).rstrip(".")
                + "."
            )
        item_letra_documento = (
            _LETTERED_LIST_ITEM_RE.match(bloco_texto)
            if not anexo_standalone
            else None
        )
        if item_letra_documento:
            letra_item = item_letra_documento.group(1).lower()
            item_padrao_detectado = (
                f"{secao_contextual.rstrip('.')}.{letra_item}."
                if secao_contextual
                else f"{letra_item}."
            )
        item_sem_ponto = item_padrao_detectado.rstrip(".")
        if (
            item_sem_ponto
            and "LISTA DE TAREFAS" in normalized_for_match(bloco_texto)
            and categoria in {"subsecao_numerada", "secao_principal"}
        ):
            lista_tarefas_raiz = item_sem_ponto
            tarefa_lista_contextual = ""
            em_lista_verificacao = False
            categoria = "lista_tarefas"
        elif (
            lista_tarefas_raiz
            and item_sem_ponto
            and item_sem_ponto.startswith(f"{lista_tarefas_raiz}.")
            and len(item_sem_ponto.split("."))
            == len(lista_tarefas_raiz.split(".")) + 1
        ):
            categoria = "instrucao_operacional"
            tarefa_lista_contextual = item_sem_ponto
            secao_contextual = item_sem_ponto
            em_lista_verificacao = False
        elif categoria == "lista_verificacao" and tarefa_lista_contextual:
            item_padrao_detectado = f"{tarefa_lista_contextual}."
            secao_contextual = tarefa_lista_contextual
            em_lista_verificacao = True
        elif (
            tarefa_lista_contextual and em_lista_verificacao and item_sem_ponto
        ):
            secao_contextual = tarefa_lista_contextual
            conteudo_local = _conteudo_item_numerado(bloco_texto)
            if _ACTION_START_RE.match(
                conteudo_local
            ) or _texto_tem_acoes_explicitas(conteudo_local):
                categoria = "instrucao_operacional"
            else:
                categoria = "geral"
        item_letra_anexo = (
            _ANEXO_LETTER_ITEM_RE.match(bloco_texto)
            if anexo_standalone
            else None
        )
        if passo_operacional:
            numero_passo = passo_operacional.group(1)
            base_item = secao_atividade_operacional or secao_contextual
            item_padrao_detectado = (
                f"{base_item.rstrip('.')}.{numero_passo}."
                if base_item
                else numero_passo
            )
            item_padrao_fonte = ""
        elif item_letra_anexo:
            item_padrao_fonte = ""
            if (
                re.search(r"\.{3,}", bloco_texto)
                or "RECURSOS NECESSARIOS" in titulo_contextual
            ):
                item_padrao_detectado = ""
                categoria = "geral"
            else:
                letra_item = (
                    item_letra_anexo.group(1) or item_letra_anexo.group(2)
                ).lower()
                item_padrao_detectado = (
                    f"{secao_contextual.rstrip('.')}.({letra_item})"
                    if secao_contextual
                    else f"({letra_item})"
                )
                categoria = "instrucao_operacional"
                ultimo_item_operacional = item_padrao_detectado

        # 3. Aplica as regras de ação e as exceções próprias de anexos.
        candidato_acao = _texto_tem_acoes_explicitas(bloco_texto) or (
            bool(item_padrao_detectado)
            and not _eh_titulo_estrutural(linhas[0])
            and _item_numerado_tem_acao_explicita(bloco_texto)
        )
        if (
            bloco_texto
            and candidato_acao
            and categoria
            in {
                "geral",
                "subsecao_numerada",
                "registros",
                "itens_criticos",
                "item_numerado_anexo",
            }
            and not _ANEXO_OPERATIONAL_HEADING_RE.match(linhas[0])
        ):
            categoria = "instrucao_operacional"
        conteudo_numerado = _conteudo_item_numerado(bloco_texto)
        conteudo_operacional = (
            conteudo_numerado
            or re.sub(
                r"^\s*[•·▪◦*\-]\s*",
                "",
                bloco_texto,
            ).strip()
        )
        remissao_etapa = (
            normalized_for_match(conteudo_operacional)
            .lstrip("-–— ")
            .startswith("SEGUIR ETAPA")
        )
        inicio_condicional = (
            re.match(
                r"^(?:Antes de|Após|Em caso|Caso|Se houver|Quando)\b",
                conteudo_operacional,
                re.IGNORECASE,
            )
            is not None
        )
        if anexo_standalone and remissao_etapa:
            categoria = "geral"
            candidato_acao = False
        elif anexo_standalone and categoria == "item_numerado_anexo":
            if candidato_acao:
                categoria = "instrucao_operacional"
            else:
                categoria = "subsecao_numerada"
        if anexo_standalone and item_padrao_fonte.rstrip(".") in {
            "1",
            "2",
            "1-",
            "2-",
        }:
            categoria = "subsecao_numerada"
        if (
            anexo_standalone
            and secao_contextual.rstrip(".") == "1.1"
            and item_padrao_fonte
            and len(item_padrao_fonte.rstrip(".").split(".")) > 2
            and not candidato_acao
        ):
            categoria = "geral"
        if (
            anexo_standalone
            and len(secao_contextual.rstrip(".").split(".")) >= 3
            and secao_contextual.rstrip(".").endswith(".1")
            and re.match(r"^Antes de iniciar\b", bloco_texto, re.IGNORECASE)
        ):
            categoria = "instrucao_operacional"
            candidato_acao = True
        if (
            anexo_standalone
            and inicio_condicional
            and _ACTION_IMPERATIVE_RE.search(bloco_texto)
        ):
            candidato_acao = True
            categoria = "instrucao_operacional"
        if (
            fluxograma_standalone
            and categoria
            in {"geral", "lista_informativa", "subsecao_numerada"}
            and not candidato_acao
            and not normalized_for_match(bloco_texto).startswith(
                ("OBS", "ORIENTAR", "INFORMAR")
            )
        ):
            categoria = "fragmento_interface"
        if (
            anexo_standalone
            and not item_padrao_fonte
            and "ITENS CRITICOS" in titulo_contextual
            and inicio_condicional
            and (
                len(secao_contextual.rstrip(".").split(".")) <= 2
                or normalized_for_match(conteudo_operacional).startswith(
                    "EM CASO DE MANUTENCAO"
                )
            )
        ):
            item_padrao_detectado = ""
            categoria = "geral"
            candidato_acao = False
        if (
            anexo_standalone
            and ultimo_item_operacional
            and not item_padrao_detectado
            and inicio_condicional
            and _ACTION_IMPERATIVE_RE.search(bloco_texto)
            and "ITENS CRITICOS" not in titulo_contextual
        ):
            item_padrao_detectado = ultimo_item_operacional
            categoria = "instrucao_operacional"
            candidato_acao = True
        texto_sem_numeracao = re.sub(
            r"^\s*\d+(?:\.\d+)*\.?\s*",
            "",
            bloco_texto,
        )
        if texto_sem_numeracao.lower().startswith("não "):
            categoria = "geral"
        if _NOTICE_RE.match(bloco_texto):
            categoria = "aviso_informativo"
            candidato_acao = False
        titulo_estrutural = (
            _eh_titulo_estrutural(linhas[0])
            and not instrucao_numerada
            and categoria != "item_numerado_anexo"
            and not remissao_etapa
        )
        contexto_lista_informativa = any(
            marcador in titulo_contextual
            for marcador in (
                "RECURSOS NECESSARIOS",
                "ITENS CRITICOS",
                "PREMISSAS",
            )
        )
        item_contextual = item_padrao_detectado.rstrip(".")
        eh_descendente_lista = bool(
            contexto_lista_informativa
            and secao_contextual
            and item_contextual.startswith(f"{secao_contextual.rstrip('.')}.")
        )
        if eh_descendente_lista and categoria == "subsecao_numerada":
            categoria = "geral"
        if categoria == "subsecao_numerada" and len(bloco_texto) <= 120:
            titulo_estrutural = not eh_descendente_lista
        if categoria in {"recursos_necessarios", "itens_criticos"}:
            titulo_estrutural = True
        if (
            anexo_standalone
            and categoria == "subsecao_numerada"
            and len(bloco_texto) <= 180
        ):
            titulo_estrutural = True
        if categoria == "etapa_operacional":
            titulo_estrutural = True
        if (
            tarefa_lista_contextual
            and categoria == "instrucao_operacional"
            and item_sem_ponto == tarefa_lista_contextual
        ):
            titulo_estrutural = False

        # 4. Atualiza o contexto que será herdado pelos próximos blocos.
        if (
            bloco_texto
            and item_padrao_detectado
            and (titulo_estrutural or tem_subitens)
        ):
            secao_contextual = item_padrao_detectado.rstrip(".")
            titulo_contextual = normalized_for_match(bloco_texto)
            if anexo_standalone and len(secao_contextual.split(".")) == 1:
                ultimo_item_operacional = ""
        contexto_tarefa: dict[str, str] = {}
        if categoria == "lista_tarefas":
            contexto_tarefa = {
                "listaTarefasRaiz": lista_tarefas_raiz,
                "nivelLista": "raiz",
            }
        elif tarefa_lista_contextual and categoria == "lista_verificacao":
            contexto_tarefa = {
                "listaTarefasRaiz": lista_tarefas_raiz,
                "tarefaLista": tarefa_lista_contextual,
                "nivelLista": "lista_verificacao",
            }
        elif (
            tarefa_lista_contextual
            and em_lista_verificacao
            and categoria == "instrucao_operacional"
            and not normalized_for_match(bloco_texto).startswith("OBSERVACAO")
        ):
            contexto_tarefa = {
                "listaTarefasRaiz": lista_tarefas_raiz,
                "tarefaLista": tarefa_lista_contextual,
                "nivelLista": "item_lista_verificacao",
            }
        elif (
            tarefa_lista_contextual
            and categoria == "instrucao_operacional"
            and item_sem_ponto == tarefa_lista_contextual
        ):
            contexto_tarefa = {
                "listaTarefasRaiz": lista_tarefas_raiz,
                "tarefaLista": tarefa_lista_contextual,
                "nivelLista": "tarefa",
            }
        elif tarefa_lista_contextual and categoria == "aviso_informativo":
            contexto_tarefa = {
                "listaTarefasRaiz": lista_tarefas_raiz,
                "tarefaLista": tarefa_lista_contextual,
                "nivelLista": "item_lista_verificacao",
            }
        atividade_encontrada = (
            _ATIVIDADE_TABELA_RE.match(linhas[0])
            if escopo_contextual == "tabela_2"
            else None
        )
        if categoria == "atividade_tabela_2" and atividade_encontrada:
            indice_atividade = atividade_encontrada.group(1)
            atividade_contextual = {
                "itemPadrao": f"{secao_contextual}.{indice_atividade}"
                if secao_contextual
                else "",
                "subtarefaHTA": f"{indice_atividade}.",
            }
            contexto_tarefa = atividade_contextual
        elif (
            escopo_contextual == "tabela_2"
            and categoria in {"como_fazer", "porque_fazer"}
            and atividade_contextual
        ):
            contexto_tarefa = atividade_contextual
        if categoria == "passo_tabela_operacional":
            contexto_tarefa = {
                "itemPadrao": item_padrao_detectado,
                "grupoOperacional": (
                    secao_atividade_operacional
                    if etapa_operacional <= 1
                    else (
                        f"__etapa_{etapa_operacional}_"
                        f"{secao_atividade_operacional}"
                    )
                ),
            }
        if categoria == "cabecalho_tabela" and all(
            termo in normalized_for_match(bloco_texto)
            for termo in ("O QUE FAZER", "EXECUTANTE", "ONDE REGISTRAR")
        ):
            aguardando_atividade_tabela = True
            executante_tabela_pendente = ""
        elif aguardando_atividade_tabela and categoria == "geral":
            celulas_mescladas = _TABLE_REGISTER_SUFFIX_RE.match(bloco_texto)
            if celulas_mescladas:
                executante_tabela_pendente = normalize_whitespace(
                    celulas_mescladas.group("executante")
                )
        elif (
            aguardando_atividade_tabela
            and categoria == "instrucao_operacional"
        ):
            executante_tabela = executante_tabela or executante_tabela_pendente
            aguardando_atividade_tabela = False
            executante_tabela_pendente = ""

        # 5. Materializa o contrato consumido pelo pipeline e pela IA.
        resultado.append(
            {
                "ordem": ordem,
                "texto": bloco_texto,
                "itemPadraoDetectado": item_padrao_detectado,
                "itemPadraoFonte": item_padrao_fonte,
                "categoria": categoria,
                "escopo": escopo_contextual,
                "palavras_chave": extrair_palavras_chave(bloco_texto),
                "contextoTarefa": contexto_tarefa,
                "executanteDetectado": executante_tabela,
                "secaoContextual": secao_contextual,
                "tituloEstrutural": titulo_estrutural,
                "listaAgrupada": lista_agrupada,
                "temSubitens": tem_subitens,
                "acaoUnica": bool(item_letra_anexo),
                "anexoStandalone": anexo_standalone,
                "tipoDocumento": (
                    "fluxograma"
                    if fluxograma_standalone
                    else "anexo"
                    if anexo_standalone
                    else "procedimento"
                ),
                "identificadorAnexo": identificador_anexo,
                "etapaOperacional": etapa_operacional,
                "imagemIndice": (
                    int(_IMAGE_MARKER_RE.fullmatch(bloco_texto).group(1))
                    if categoria == "imagem"
                    and _IMAGE_MARKER_RE.fullmatch(bloco_texto)
                    else None
                ),
            }
        )
    _aplicar_hierarquia_local_do_anexo(resultado)
    _marcar_sufixo_de_interface(resultado)
    return resultado


def separar_blocos(texto: str, nome_arquivo: str = "") -> list[dict]:
    """Separa segmentos técnicos adequados à conversão pela IA."""
    identificador_anexo, titulo_anexo = _identificar_anexo_pelo_nome(
        nome_arquivo
    )
    anexo_standalone = bool(identificador_anexo)
    fluxograma_standalone = anexo_standalone and bool(
        re.search(r"\bFLUXOGRAMA\b", nome_arquivo, re.IGNORECASE)
    )
    blocos = _preparar_blocos_para_classificacao(
        texto,
        anexo_standalone=anexo_standalone,
        fluxograma_standalone=fluxograma_standalone,
        identificador_anexo=identificador_anexo,
        titulo_anexo=titulo_anexo,
    )
    numero_tabela_desvios, segmentos_de_anexo, itens_com_subitens = (
        _analisar_hierarquia_dos_blocos(blocos)
    )
    return _classificar_blocos(
        blocos,
        identificador_anexo=identificador_anexo,
        anexo_standalone=anexo_standalone,
        fluxograma_standalone=fluxograma_standalone,
        numero_tabela_desvios=numero_tabela_desvios,
        segmentos_de_anexo=segmentos_de_anexo,
        itens_com_subitens=itens_com_subitens,
    )
