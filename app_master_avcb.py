import streamlit as st
import base64
from openai import OpenAI
import fitz  # PyMuPDF
from fpdf import FPDF  # <--- NOVA BIBLIOTECA
import datetime

# --- CONFIGURAÇÕES ---
st.set_page_config(page_title="Master Auditor AVCB/CLCB", page_icon="🏢", layout="wide")
# --- SISTEMA DE LOGIN ---
def check_password():
    """Retorna True se a senha estiver correta."""
    def password_entered():
        if st.session_state["password"] == st.secrets["PASSWORD"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Não armazena a senha
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # Primeira vez: mostra o campo de senha
        st.text_input("🔑 Digite a senha de acesso:", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        # Senha errada: pede de novo
        st.text_input("🔑 Digite a senha de acesso:", type="password", on_change=password_entered, key="password")
        st.error("😕 Senha incorreta")
        return False
    else:
        # Senha correta
        return True

# Se a senha não estiver correta, para o app aqui.
if not check_password():
    st.stop()

# --- CONFIGURAÇÃO API (MODO SEGURO) ---
# A chave será pega dos "Segredos" da nuvem, não do código.
try:
    api_key = st.secrets["OPENAI_API_KEY"]
except:
    # Caso rode localmente sem configurar segredos (fallback)
    st.error("Chave de API não encontrada. Configure os 'secrets'.")
    st.stop()

client = OpenAI(api_key=api_key)


# --- CLASSE PARA GERAR PDF (NOVIDADE) ---
class RelatorioPDF(FPDF):
    def header(self):
        # Você pode colocar um logo.png na pasta e descomentar a linha abaixo
        # self.image('logo.png', 10, 8, 33)
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'Relatório de Auditoria Técnica - AVCB/CLCB', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')

    def chapter_body(self, body):
        self.set_font('Arial', '', 11)
        # O FPDF tem problemas com caracteres especiais (UTF-8), então precisamos tratar
        # Uma forma simples é usar encode('latin-1', 'replace') para evitar erro
        texto_tratado = body.encode('latin-1', 'replace').decode('latin-1')
        self.multi_cell(0, 10, texto_tratado)
        self.ln()


# --- CLASSE DE MEMÓRIA (MANTIDA IGUAL) ---
class BibliotecaNormas:
    def __init__(self):
        self.paginas_normas = []

    def adicionar_pdf(self, arquivo_pdf):
        try:
            doc = fitz.open(stream=arquivo_pdf.read(), filetype="pdf")
            nome_norma = arquivo_pdf.name

            for num_pagina, pagina in enumerate(doc):
                texto = pagina.get_text()
                if len(texto) > 50:
                    self.paginas_normas.append({
                        "fonte": nome_norma,
                        "pagina": num_pagina + 1,
                        "conteudo": texto
                    })
            return len(doc)
        except Exception as e:
            st.error(f"Erro ao ler {arquivo_pdf.name}: {e}")
            return 0

    def buscar_contexto(self, termo_pesquisa, limite_paginas=5):
        resultados = []
        termos = termo_pesquisa.lower().split()

        for item in self.paginas_normas:
            pontuacao = 0
            conteudo_lower = item["conteudo"].lower()
            for t in termos:
                if t in conteudo_lower: pontuacao += 1
            if pontuacao > 0: resultados.append((pontuacao, item))

        resultados.sort(key=lambda x: x[0], reverse=True)
        contexto_final = ""
        for _, item in resultados[:limite_paginas]:
            contexto_final += f"\n--- FONTE: {item['fonte']} (Pág {item['pagina']}) ---\n{item['conteudo']}\n"
        return contexto_final


if 'banco_normas' not in st.session_state:
    st.session_state.banco_normas = BibliotecaNormas()


# --- FUNÇÕES VISUAIS ---
def pdf_to_base64_first_page(uploaded_file):
    try:
        uploaded_file.seek(0)
        doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
        page = doc.load_page(0)
        pix = page.get_pixmap()
        img_data = pix.tobytes("png")
        return base64.b64encode(img_data).decode('utf-8')
    except:
        return None


# --- INTERFACE ---
st.title("🏢 Master Auditor: AVCB & CLCB (Gerador de Laudo)")

# --- SIDEBAR (UPLOAD NORMAS) ---
with st.sidebar:
    st.header("📚 Biblioteca de ITs")
    st.info("Faça upload de TODAS as ITs (IT-17, IT-22, etc).")
    uploaded_its = st.file_uploader("Adicionar Normas", type="pdf", accept_multiple_files=True)

    if uploaded_its:
        if st.button("🔄 Processar ITs"):
            st.session_state.banco_normas = BibliotecaNormas()
            total_pags = 0
            bar = st.progress(0)
            for i, arquivo in enumerate(uploaded_its):
                pags = st.session_state.banco_normas.adicionar_pdf(arquivo)
                total_pags += pags
                bar.progress((i + 1) / len(uploaded_its))
            st.success(f"Indexado: {total_pags} páginas.")

# --- ÁREA PRINCIPAL ---
col1, col2 = st.columns(2)
with col1:
    st.subheader("📁 Projeto Técnico")
    doc_projeto = st.file_uploader("Upload Projeto", type=["pdf"], key="proj")
with col2:
    st.subheader("📄 ART / RRT")
    doc_art = st.file_uploader("Upload ART", type=["pdf"], key="art")

if st.button("🔍 Auditar e Gerar Laudo", type="primary"):
    if doc_projeto and doc_art:
        with st.status("🧠 Auditando...", expanded=True) as status:

            # 1. Leitura Visual
            status.write("👁️ Lendo Projeto e ART...")
            img_proj = pdf_to_base64_first_page(doc_projeto)
            img_art = pdf_to_base64_first_page(doc_art)

            # 2. Identificação
            status.write("🔎 Identificando sistemas de segurança...")
            prompt_id = "Liste palavras-chave dos sistemas (Hidrante, Alarme, etc)."
            resp_id = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": [{"type": "text", "text": prompt_id}, {"type": "image_url",
                                                                                             "image_url": {
                                                                                                 "url": f"data:image/jpeg;base64,{img_proj}"}}]}]
            )
            palavras_chave = resp_id.choices[0].message.content

            # 3. Busca Contexto
            status.write(f"📚 Consultando normas para: {palavras_chave}...")
            contexto = st.session_state.banco_normas.buscar_contexto(palavras_chave)

            # 4. Auditoria
            status.write("⚖️ Gerando Parecer Técnico...")
            prompt_final = f"""
            Você é um Engenheiro Auditor Especialista.
            CONTEXTO NORMAS: {contexto}

            TAREFA:
            Analise o Projeto e a ART. Compare com as normas.
            Gere um RELATÓRIO TÉCNICO COMPLETO.

            Estrutura:
            1. Identificação da Obra (Visual)
            2. Sistemas Identificados
            3. Análise da ART (Conformidade IT-01)
            4. Análise Técnica (Dimensionamentos vs Normas)
            5. Conclusão (APROVADO/REPROVADO com lista de pendências)
            """

            resp_final = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": prompt_final},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_proj}"}},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_art}"}}
                ]}],
                max_tokens=2500
            )

            resultado_texto = resp_final.choices[0].message.content
            status.update(label="Concluído!", state="complete", expanded=False)

            st.markdown("### 📝 Prévia do Laudo")
            st.markdown(resultado_texto)

            # --- 5. GERAÇÃO DO PDF (AQUI ESTÁ A MÁGICA) ---
            pdf = RelatorioPDF()
            pdf.add_page()

            # Cabeçalho do Laudo
            pdf.set_font("Arial", size=10)
            pdf.cell(200, 10, txt=f"Data da Auditoria: {datetime.date.today().strftime('%d/%m/%Y')}", ln=True,
                     align='R')
            pdf.ln(10)

            # Corpo do Laudo (O texto da IA)
            pdf.chapter_body(resultado_texto)

            # Gera o arquivo binário
            pdf_bytes = pdf.output(dest='S').encode('latin-1')  # 'S' retorna como string/bytes

            st.divider()
            st.download_button(
                label="📥 BAIXAR LAUDO TÉCNICO (PDF)",
                data=pdf_bytes,
                file_name="Laudo_Auditoria_AVCB.pdf",
                mime="application/pdf"
            )

    else:

        st.warning("Envie os documentos necessários.")
