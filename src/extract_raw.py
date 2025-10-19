import fitz
import re
import json
import unicodedata
from typing import List, Dict, Any, Optional

def extrair_texto_pdf(caminho_pdf: str) -> List[Dict[str, Any]]:
    """Extrai texto de cada página do PDF usando PyMuPDF (fitz).

    Retorna lista de dicionários: {"page": int, "raw_text": str}
    """
    paginas = []
    with fitz.open(caminho_pdf) as documento:
        for i, pagina in enumerate(documento, start=1):
            texto = pagina.get_text() or ""
            paginas.append({"page": i, "raw_text": texto})
    return paginas

def limpar_texto(texto: str) -> str:
    texto = re.sub(r"\d{2}/\d{2}/\d{2}, \d{2}:\d{2}\s*SEI/IFNMG.*", "", texto)
    texto = re.sub(r"https://sei.ifnmg.edu.br/sei/controlador.php.*", "", texto)
    texto = re.sub(r"\b\d{1,2}/\d{1,2}\b", "", texto)  # Ex: 3/59
    texto = re.sub(r"\n{2,}", "\n", texto)
    return texto.strip()

def normalizar_texto(texto: str) -> str:
    texto = texto.replace('\u201c', '"').replace('\u201d', '"').replace("\u2018", "'").replace("\u2019", "'")
    return texto

def normalizar_texto_sigla(texto: str) -> str:
    nfkd_form = unicodedata.normalize('NFKD', texto)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

def capturar_linhas_siglas(texto: str, max_linhas: int = 400) -> List[tuple]:
    padrao = re.compile(r'([A-Z\u00c1-\u00dc][ ,A-Z\u00c1-\u00dca-z\u00e0-\u00fc\\-]+)\\((\\b[A-Z]{2,}\\b)\\)', re.UNICODE)
    linhas = texto.split('\n')[:max_linhas]
    linhas_siglas = []
    for linha in linhas:
        for match in padrao.finditer(linha):
            nome = match.group(1).strip()
            sigla = match.group(2).strip()
            linhas_siglas.append((linha.strip(), nome, sigla))
    return linhas_siglas

def substituir_siglas_detectadas(texto: str, linhas_siglas: List[tuple], ignorar_siglas: Optional[set] = None) -> str:
    if ignorar_siglas is None:
        ignorar_siglas = {'IFNMG'}
    siglas_dict = {sigla: nome.strip() + f' ({sigla})' for _, nome, sigla in linhas_siglas if sigla not in ignorar_siglas}
    for sigla, nome_extenso in siglas_dict.items():
        texto = re.sub(rf'\b{sigla}\b', nome_extenso, texto)
    return texto

def separar_blocos(texto: str) -> List[Dict[str, Any]]:
    padrao_capitulo = re.compile(r'(CAP[I\u00cd]TULO [IVXLC]+[^\n]*)', re.IGNORECASE)
    padrao_artigo = re.compile(r'(Art\\. ?\\d+\u00ba?)', re.IGNORECASE)
    padrao_paragrafo = re.compile(r'(\u00a7 ?\\d*\u00ba?)', re.IGNORECASE)

    blocos: List[Dict[str, Any]] = []
    linhas = texto.split('\n')
    capitulo = artigo = paragrafo = None
    buffer: List[str] = []

    for linha in linhas:
        if padrao_capitulo.match(linha):
            if buffer:
                blocos.append({'capitulo': capitulo, 'artigo': artigo, 'paragrafo': paragrafo, 'texto': '\n'.join(buffer).strip()})
                buffer = []
            capitulo = linha.strip()
            artigo = paragrafo = None
        elif padrao_artigo.match(linha):
            if buffer:
                blocos.append({'capitulo': capitulo, 'artigo': artigo, 'paragrafo': paragrafo, 'texto': '\n'.join(buffer).strip()})
                buffer = []
            artigo = linha.strip()
            paragrafo = None
        elif padrao_paragrafo.match(linha):
            if buffer:
                blocos.append({'capitulo': capitulo, 'artigo': artigo, 'paragrafo': paragrafo, 'texto': '\n'.join(buffer).strip()})
                buffer = []
            paragrafo = linha.strip()
        else:
            buffer.append(linha)
    if buffer:
        blocos.append({'capitulo': capitulo, 'artigo': artigo, 'paragrafo': paragrafo, 'texto': '\n'.join(buffer).strip()})
    return blocos

def enriquecer_blocos(blocos: List[Dict[str, Any]], metadados: Dict[str, Any]) -> List[Dict[str, Any]]:
    for bloco in blocos:
        bloco.update(metadados)
    return blocos

def extract_raw(pdf_path: str, doc_id: str, output_txt: Optional[str] = None, output_json: Optional[str] = None) -> Dict[str, Any]:
    """API compatível que extrai texto bruto e opcionalmente produz arquivos de saída estruturados.

    - pdf_path: caminho para o arquivo PDF
    - doc_id: identificador do documento (adicionado aos blocos)
    - output_txt: se fornecido, salva o texto extraído concatenado neste arquivo
    - output_json: se fornecido, salva os blocos estruturados neste arquivo

    Retorna um dicionário com chaves: pages (lista de páginas) e blocks (lista de blocos, se gerados)
    """
    import os

    paginas = extrair_texto_pdf(pdf_path)
    # concatena todo o texto para processamento estruturado
    texto_completo = "\n".join([p['raw_text'] for p in paginas if p.get('raw_text')])

    # Cria pasta de output padrão em data/output, se necessário
    repo_root = os.path.dirname(os.path.dirname(__file__))
    default_out_dir = os.path.join(repo_root, 'data', 'output')
    os.makedirs(default_out_dir, exist_ok=True)

    if output_txt is None:
        output_txt = os.path.join(default_out_dir, f"{doc_id}_extracted.txt")
    if output_json is None:
        output_json = os.path.join(default_out_dir, f"{doc_id}_structured.json")

    with open(output_txt, 'w', encoding='utf-8') as f:
        f.write(texto_completo)

    texto_limpo = limpar_texto(texto_completo)
    texto_limpo = normalizar_texto(texto_limpo)
    linhas_siglas = capturar_linhas_siglas(texto_limpo)
    texto_subs = substituir_siglas_detectadas(texto_limpo, linhas_siglas)
    blocos = separar_blocos(texto_subs)
    metadados = {'doc_id': doc_id}
    blocos = enriquecer_blocos(blocos, metadados)

    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(blocos, f, ensure_ascii=False, indent=2)

    return {"pages": paginas, "blocks": blocos, "output_txt": output_txt, "output_json": output_json}

if __name__ == '__main__':
    import os
    repo_root = os.path.dirname(os.path.dirname(__file__))
    pdf_path = os.path.join(repo_root, 'data', 'input', 'Regulamento_Estagio.pdf')
    resultado = extract_raw(pdf_path, doc_id='1539646')
    print(f"Extração concluída: {len(resultado['pages'])} páginas, {len(resultado['blocks'])} blocos")
    print(f"Arquivos gravados: txt -> {resultado['output_txt']}, json -> {resultado['output_json']}")
