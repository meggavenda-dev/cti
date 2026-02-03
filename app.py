import streamlit as st
import pandas as pd
import json
from github import Github

# --- CONFIGURAÇÕES DE COLUNAS (AJUSTE AQUI SEU EXCEL) ---
COL_CONVENIO = "Convenio"
COL_VALOR = "Valor"

# --- CONFIGURAÇÕES DO GITHUB (VIA SECRETS) ---
try:
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
    REPO_NAME = st.secrets["REPO_NAME"]
    FILE_PATH = "cadastro_convenios.json"
    
    g = Github(GITHUB_TOKEN)
    repo = g.get_repo(REPO_NAME)
except Exception as e:
    st.error("Erro nas Secrets do Streamlit ou Conexão com GitHub. Verifique as configurações.")
    st.stop()

# --- FUNÇÕES DE PERSISTÊNCIA ---
def load_convenios_from_github():
    try:
        content = repo.get_contents(FILE_PATH)
        return json.loads(content.decoded_content.decode())
    except Exception:
        # Se o arquivo não existir, retorna um dicionário vazio
        return {}

def save_convenios_to_github(dados):
    try:
        content = repo.get_contents(FILE_PATH)
        repo.update_file(FILE_PATH, "Atualizando base de convênios", json.dumps(dados, indent=4), content.sha)
        return True
    except Exception as e:
        st.error(f"Erro ao salvar no GitHub: {e}")
        return False

# --- INICIALIZAÇÃO DA INTERFACE ---
st.set_page_config(page_title="Gestão de Faturamento GABMA", layout="wide")
st.title("🏥 Sistema de Gestão de Faturamento - Guilherme")

aba_processar, aba_convenios = st.tabs(["📊 Processar Relatório", "⚙️ Gerenciar Convênios"])

# Carregar base de dados persistente
if 'base_convenios' not in st.session_state:
    st.session_state.base_convenios = load_convenios_from_github()

# --- ABA DE GERENCIAMENTO DE CONVÊNIOS ---
with aba_convenios:
    st.header("Base de Convênios Cadastrados")
    if st.session_state.base_convenios:
        df_base = pd.DataFrame(list(st.session_state.base_convenios.items()), columns=["Convênio", "Meio de Faturamento"])
        st.table(df_base)
        
        if st.button("Limpar Base (Cuidado!)"):
            if save_convenios_to_github({}):
                st.session_state.base_convenios = {}
                st.rerun()
    else:
        st.info("Nenhum convênio cadastrado ainda.")

# --- ABA DE PROCESSAMENTO ---
with aba_processar:
    uploaded_file = st.file_uploader("Faça upload do relatório (Excel ou CSV)", type=["xlsx", "csv"])
    
    if uploaded_file:
        # Leitura do arquivo
        try:
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)
            
            st.success("Arquivo carregado com sucesso!")
        except Exception as e:
            st.error(f"Erro ao ler o arquivo: {e}")
            st.stop()

        # Validação de Colunas
        if COL_CONVENIO not in df.columns or COL_VALOR not in df.columns:
            st.error(f"As colunas '{COL_CONVENIO}' e '{COL_VALOR}' não foram encontradas no arquivo.")
            st.write("Colunas detectadas:", list(df.columns))
            st.stop()

        # Identificar Convênios Únicos e Pendentes
        convenios_unicos = df[COL_CONVENIO].unique()
        pendentes = [c for c in convenios_unicos if c not in st.session_state.base_convenios]

        if pendentes:
            st.warning(f"⚠️ {len(pendentes)} novos convênios encontrados. Por favor, vincule-os:")
            
            # Criar um formulário para não recarregar a cada clique
            with st.form("form_novos_convenios"):
                novos_vincunlos = {}
                for conv in pendentes:
                    tipo = st.selectbox(f"Faturamento para: {conv}", ["AMHPDF", "HOSPITAL", "DIRETO", "OUTROS"], key=f"sel_{conv}")
                    novos_vincunlos[conv] = tipo
                
                if st.form_submit_button("Salvar Todos os Novos Convênios"):
                    st.session_state.base_convenios.update(novos_vincunlos)
                    if save_convenios_to_github(st.session_state.base_convenios):
                        st.success("Convênios salvos com sucesso!")
                        st.rerun()

        # --- CÁLCULOS ---
        # Mapeia o tipo com base na persistência, se não achar vira 'OUTROS'
        df['Meio_Faturamento'] = df[COL_CONVENIO].map(st.session_state.base_convenios).fillna('OUTROS')
        
        # Totalização
        total_geral = df[COL_VALOR].sum()
        resumo = df.groupby('Meio_Faturamento')[COL_VALOR].sum().to_dict()

        # --- DASHBOARD DE RESULTADOS ---
        st.divider()
        st.subheader("Resumo do Faturamento")
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("TOTAL GERAL", f"R$ {total_geral:,.2f}")
        m2.metric("AMHPDF", f"R$ {resumo.get('AMHPDF', 0):,.2f}")
        m3.metric("HOSPITAL", f"R$ {resumo.get('HOSPITAL', 0):,.2f}")
        m4.metric("DIRETO", f"R$ {resumo.get('DIRETO', 0):,.2f}")

        # Alerta para valores não vinculados
        if 'OUTROS' in resumo and resumo['OUTROS'] > 0:
            st.error(f"⚠️ Valor em 'OUTROS' (Não Vinculado): R$ {resumo['OUTROS']:,.2f}")
            
        # Exibir a tabela processada para conferência
        with st.expander("Ver Detalhes do Processamento"):
            st.dataframe(df[[COL_CONVENIO, COL_VALOR, 'Meio_Faturamento']])
