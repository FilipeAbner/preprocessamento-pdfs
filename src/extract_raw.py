import fitz
import re
import json
import unicodedata


def extrair_texto_pdf(caminho_pdf, caminho_saida):
    try:
        with fitz.open(caminho_pdf) as documento:
            texto_completo = ""
            for pagina in documento:
                texto_completo += pagina.get_text()

        with open(caminho_saida, "w", encoding="utf-8") as arquivo_saida:
            arquivo_saida.write(texto_completo)

        return f"Texto extraído foi salvo em '{caminho_saida}'."
    except FileNotFoundError:
        return f"Erro: O arquivo '{caminho_pdf}' não foi encontrado."
    except Exception as erro:
        return f"Ocorreu um erro: {erro}"


def limpar_texto(texto):
    texto = re.sub(r"\d{2}/\d{2}/\d{2}, \d{2}:\d{2}\s*SEI/IFNMG.*", "", texto)
    texto = re.sub(r"https://sei.ifnmg.edu.br/sei/controlador.php.*", "", texto)
    texto = re.sub(r"\b\d{1,2}/\d{1,2}\b", "", texto)  # Ex: 3/59
    texto = re.sub(r"\n{2,}", "\n", texto)
    return texto.strip()


def normalizar_texto(texto):
    texto = texto.replace('“', '"').replace('”', '"').replace("‘", "'").replace("’", "'")
    return texto


def normalizar_texto_sigla(texto):
    nfkd_form = unicodedata.normalize('NFKD', texto)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])


def capturar_linhas_siglas(texto, max_linhas=400):
    padrao = re.compile(r'([A-ZÁ-Ü][ ,A-ZÁ-Üa-zà-ü\-]+)\((\b[A-Z]{2,}\b)\)', re.UNICODE)
    linhas = texto.split('\n')[:max_linhas]
    linhas_siglas = []
    for linha in linhas:
        for match in padrao.finditer(linha):
            nome = match.group(1).strip()
            sigla = match.group(2).strip()
            linhas_siglas.append((linha.strip(), nome, sigla))
    return linhas_siglas


def substituir_siglas(texto, siglas):
    # Substitui todas as ocorrências da sigla isolada pela forma expandida
    for sigla, expandido in siglas.items():
        texto = re.sub(rf'\b{sigla}\b', expandido, texto)
    return texto


def substituir_siglas_detectadas(texto, linhas_siglas, ignorar_siglas={'IFNMG'}):
    # Cria dicionário sigla: nome
    siglas_dict = {sigla: nome.strip() + f' ({sigla})' for _, nome, sigla in linhas_siglas if sigla not in ignorar_siglas}
    for sigla, nome_extenso in siglas_dict.items():
        texto = re.sub(rf'\b{sigla}\b', nome_extenso, texto)
    return texto


def separar_blocos(texto):
    padrao_capitulo = re.compile(r'(CAP[IÍ]TULO [IVXLC]+[^\n]*)', re.IGNORECASE)
    # padrao_secao = re.compile(r'(CAP[IÍ]TULO [IVXLC]+[^\n]*)', re.IGNORECASE)
    padrao_artigo = re.compile(r'(Art\. ?\d+º?)', re.IGNORECASE)
    padrao_paragrafo = re.compile(r'(§ ?\d*º?)', re.IGNORECASE)

    blocos = []
    linhas = texto.split('\n')
    # capitulo = secao = artigo = paragrafo = None
    capitulo = artigo = paragrafo = None
    buffer = []

    for linha in linhas:
        if padrao_capitulo.match(linha):
            if buffer:
                blocos.append({
                    'capitulo': capitulo,
                    # 'secao': secao,
                    'artigo': artigo,
                    'paragrafo': paragrafo,
                    'texto': '\n'.join(buffer).strip()
                })
                buffer = []
            capitulo = linha.strip()
            # secao = artigo = paragrafo = None
            artigo = paragrafo = None
        # elif padrao_secao.match(linha):
        #     if buffer:
        #         blocos.append({
        #             'capitulo': capitulo,
        #             'secao': secao,
        #             'artigo': artigo,
        #             'paragrafo': paragrafo,
        #             'texto': '\n'.join(buffer).strip()
        #         })
        #         buffer = []
        #     secao = linha.strip()
        #     artigo = paragrafo = None
        elif padrao_artigo.match(linha):
            if buffer:
                blocos.append({
                    'capitulo': capitulo,
                    # 'secao': secao,
                    'artigo': artigo,
                    'paragrafo': paragrafo,
                    'texto': '\n'.join(buffer).strip()
                })
                buffer = []
            artigo = linha.strip()
            paragrafo = None
        elif padrao_paragrafo.match(linha):
            if buffer:
                blocos.append({
                    'capitulo': capitulo,
                    # 'secao': secao,
                    'artigo': artigo,
                    'paragrafo': paragrafo,
                    'texto': '\n'.join(buffer).strip()
                })
                buffer = []
            paragrafo = linha.strip()
        else:
            buffer.append(linha)
    if buffer:
        blocos.append({
            'capitulo': capitulo,
            # 'secao': secao,
            'artigo': artigo,
            'paragrafo': paragrafo,
            'texto': '\n'.join(buffer).strip()
        })
    return blocos


def enriquecer_blocos(blocos, metadados):
    for bloco in blocos:
        bloco.update(metadados)
    return blocos


def processar_arquivo_extraido(caminho_entrada, caminho_saida_json, metadados):
    with open(caminho_entrada, 'r', encoding='utf-8') as f:
        texto = f.read()
    texto = limpar_texto(texto)
    texto = normalizar_texto(texto)
    linhas_siglas = capturar_linhas_siglas(texto)
    texto = substituir_siglas_detectadas(texto, linhas_siglas)
    blocos = separar_blocos(texto)
    blocos = enriquecer_blocos(blocos, metadados)
    with open(caminho_saida_json, 'w', encoding='utf-8') as f:
        json.dump(blocos, f, ensure_ascii=False, indent=2)
    return f"Processamento concluído. {len(blocos)} blocos salvos em {caminho_saida_json}"


if __name__ == "__main__":
    caminho_pdf = "data/input/Regulamento_Estagio.pdf"
    caminho_txt = "data/output/extracao_estagio.txt"
    caminho_json = "data/output/extracao_estagio_estruturada.json"
    metadados = {
        'doc_id': '1539646',
        'nome_doc': 'Regulamento de Estágio de Discentes do IFNMG',
        'versao': '2023',
        'data_publicacao': '04/05/2023'
    }

    # Extrai texto do PDF (caso não extraído ainda)
    extrair_texto_pdf(caminho_pdf, caminho_txt)

    resultado = processar_arquivo_extraido(caminho_txt, caminho_json, metadados)
    print(resultado)
