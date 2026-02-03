import streamlit as st
import pandas as pd
import json
from github import Github

# --- CONFIGURAÇÕES DO GITHUB ---
GITHUB_TOKEN = "SEU_TOKEN_AQUI"
REPO_NAME = "seu-usuario/seu-repositorio"
FILE_PATH = "cadastro_convenios.json"

g = Github(GITHUB_TOKEN)
repo = g.get_repo(REPO_NAME)

# --- FUNÇÕES DE PERSISTÊNCIA ---
def load_convenios_from_github():
    try:
        content = repo.get_contents(FILE_PATH)
        return json.loads(content.decoded_content.decode())
    except:
        return {}

def save_convenios_to_github(dados):
    content = repo.get_contents(FILE_PATH)
    repo.update_file(FILE_PATH, "Atualizando convênios", json.dumps(dados), content.sha)

# --- INTERFACE ---
st.title("Sistema de Gestão de Faturamento - Guilherme")

aba_processar, aba_convenios = st.tabs(["Processar Relatório", "Cadastrar Convênios"])

base_convenios = load_convenios_from_github()

with aba_convenios:
    st.header("Configuração de Convênios")
    # Aqui você pode listar os convênios novos detectados no upload
    st.write("Convênios cadastrados:", base_convenios)

with aba_processar:
    uploaded_file = st.file_file_uploader("Escolha o arquivo do relatório", type=["xlsx", "csv"])
    
    if uploaded_file:
        df = pd.read_excel(uploaded_file) # Ajustar dependendo da estrutura da sua tabela
        
        # Identificar convênios únicos no arquivo
        convenios_no_arquivo = df['Convenio'].unique()
        
        # Verificar se há novos convênios para cadastrar
        novos = [c for c in convenios_no_arquivo if c not in base_convenios]
        
        if novos:
            st.warning(f"Detectamos {len(novos)} novos convênios. Vincule-os abaixo:")
            for n in novos:
                tipo = st.selectbox(f"Tipo para {n}", ["AMHPDF", "HOSPITAL", "DIRETO", "OUTROS"], key=n)
                if st.button(f"Salvar {n}"):
                    base_convenios[n] = tipo
                    save_convenios_to_github(base_convenios)
                    st.success(f"{n} salvo!")
        
        # --- CÁLCULOS ---
        df['Tipo'] = df['Convenio'].map(base_convenios).fillna('OUTROS')
        
        total_geral = df['Valor'].sum()
        resumo = df.groupby('Tipo')['Valor'].sum().to_dict()

        # --- DASHBOARD DE RESULTADOS ---
        st.divider()
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("TOTAL GERAL", f"R$ {total_geral:,.2f}")
        col2.metric("AMHPDF", f"R$ {resumo.get('AMHPDF', 0):,.2f}")
        col3.metric("HOSPITAL", f"R$ {resumo.get('HOSPITAL', 0):,.2f}")
        col4.metric("DIRETO", f"R$ {resumo.get('DIRETO', 0):,.2f}")
        
        if 'OUTROS' in resumo:
            st.error(f"Valor Pendente (Outros): R$ {resumo['OUTROS']:,.2f}")
