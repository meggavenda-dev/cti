import re
import json
from pathlib import Path
from io import BytesIO
from typing import Dict, Tuple, Optional

import pandas as pd
import streamlit as st

from github_storage import github_get_json, github_put_json

FATURAMENTO_OPCOES = ["", "AMHPDF", "HOSPITAL", "DIRETO"]
DEFAULT_DATA_PATH = "data/convenios_faturamento.json"


def normalize_convenio(s: str) -> str:
    """Normaliza o nome do convênio para ser usado como chave de cadastro."""
    if s is None:
        return ""
    s = str(s).strip()
    # remove códigos entre parênteses (ex.: (1001))
    s = re.sub(r"\s*\([^)]*\)\s*", "", s)
    # normaliza espaços
    s = re.sub(r"\s+", " ", s)
    return s


def parse_brl_value(x) -> float:
    """Converte valores em formato brasileiro para float (ex.: '1.234,56')."""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)

    s = str(x).strip()
    if s == "":
        return 0.0

    # remove R$ e espaços
    s = s.replace("R$", "").strip()
    # remove separador de milhar e troca vírgula por ponto
    s = s.replace(".", "").replace(",", ".")

    try:
        return float(s)
    except ValueError:
        return 0.0


def find_header_and_total_row(raw: pd.DataFrame) -> Tuple[int, Optional[int], Optional[float]]:
    """Encontra a linha de cabeçalho e (se existir) a linha do total do relatório."""
    header_idx = None
    total_idx = None
    total_val = None

    # procura cabeçalho (linha com 'Atendimento' e 'Nr. Guia')
    for i in range(len(raw)):
        row = raw.iloc[i]
        first = row.iloc[0]
        if isinstance(first, str) and first.strip().lower() == "atendimento":
            joined = " | ".join([str(v) for v in row.values if pd.notna(v)])
            if "nr. guia" in joined.lower() or "nº guia" in joined.lower():
                header_idx = i
                break

    # procura linha do total ("Total R$ ...")
    for i in range(len(raw)):
        row = raw.iloc[i]
        for v in row.values:
            if isinstance(v, str) and "total r$" in v.lower():
                total_idx = i
                m = re.search(r"total\s*r\$\s*(.*)$", v, flags=re.IGNORECASE)
                if m:
                    total_val = parse_brl_value(m.group(1))
                break
        if total_idx is not None:
            break

    if header_idx is None:
        raise ValueError("Não consegui identificar a linha de cabeçalho do relatório.")

    return header_idx, total_idx, total_val


def parse_atendimentos_xls(file_bytes: bytes, filename: str = "") -> Tuple[pd.DataFrame, Optional[float]]:
    """
    Lê o XLS/XLSX e devolve um DataFrame limpo + total do relatório (se encontrado).
    - .xls  -> xlrd
    - .xlsx -> openpyxl
    """
    engine = "xlrd" if filename.lower().endswith(".xls") else "openpyxl"
    raw = pd.read_excel(BytesIO(file_bytes), engine=engine, header=None)

    header_idx, total_idx, report_total = find_header_and_total_row(raw)

    header_row = raw.iloc[header_idx]
    col_map = {j: str(v).strip() for j, v in header_row.items() if pd.notna(v) and str(v).strip() != ""}
    wanted_cols = list(col_map.keys())

    start = header_idx + 1
    end = total_idx if total_idx is not None else len(raw)

    df = raw.iloc[start:end, wanted_cols].copy()
    df.rename(columns=col_map, inplace=True)

    # normalizações importantes
    df["Operadora"] = df["Operadora"].astype(str).str.strip()
    df["ConvenioKey"] = df["Operadora"].apply(normalize_convenio)
    df["Valor Total"] = df["Valor Total"].apply(parse_brl_value)

    # remove linhas vazias (sem guia e sem valor)
    df = df[~((df["Nr. Guia"].isna()) & (df["Valor Total"] == 0))]

    return df, report_total


def load_convenios_mapping() -> Dict[str, str]:
    """Carrega mapeamento de convênios -> faturamento do GitHub (ou local, se sem token)."""
    token = st.secrets.get("GITHUB_TOKEN", None)
    repo = st.secrets.get("GITHUB_REPO", None)
    branch = st.secrets.get("GITHUB_BRANCH", "main")
    path = st.secrets.get("CONVENIOS_PATH", DEFAULT_DATA_PATH)

    if token and repo:
        data = github_get_json(repo=repo, path=path, token=token, branch=branch, default={})
        return {k: (v or "") for k, v in data.items()}

    # fallback local (não persistente em Streamlit Cloud)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {k: (v or "") for k, v in data.items()}
    except Exception:
        return {}


def save_convenios_mapping(mapping: Dict[str, str]) -> None:
    """Salva mapeamento no GitHub (preferencial) e também localmente."""
    token = st.secrets.get("GITHUB_TOKEN", None)
    repo = st.secrets.get("GITHUB_REPO", None)
    branch = st.secrets.get("GITHUB_BRANCH", "main")
    path = st.secrets.get("CONVENIOS_PATH", DEFAULT_DATA_PATH)

    cleaned = {k: (v if v in FATURAMENTO_OPCOES else "") for k, v in mapping.items() if k}

    # escreve local (para rodar localmente)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)

    # escreve no GitHub (persistente)
    if token and repo:
        github_put_json(
            repo=repo,
            path=path,
            token=token,
            branch=branch,
            data=cleaned,
            commit_message="Atualiza cadastro de convênios (faturamento)",
        )


@st.dialog("Resumo do relatório", width="medium")
def resumo_dialog(resumo: Dict[str, float], report_total: Optional[float], calc_total: float):
    cols = st.columns(2)
    cols[0].metric("Total (calculado)", format_brl(calc_total))
    if report_total is not None:
        cols[1].metric("Total (informado no relatório)", format_brl(report_total))
    st.divider()
    for k in ["AMHPDF", "HOSPITAL", "DIRETO", "OUTROS"]:
        st.metric(f"Total via {k}", format_brl(resumo.get(k, 0.0)))
    st.caption("Feche esta janela clicando fora ou pressione ESC.")


def format_brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def main():
    st.set_page_config(page_title="Processador de Atendimentos - Convênios", layout="wide")
    st.title("📄 Processador de Atendimentos (XLS) + Cadastro de Convênios")

    with st.sidebar:
        st.header("⚙️ Configuração")
        token_ok = bool(st.secrets.get("GITHUB_TOKEN", "")) and bool(st.secrets.get("GITHUB_REPO", ""))
        if token_ok:
            st.success("Persistência no GitHub: OK")
            st.caption(f"Repo: {st.secrets.get('GITHUB_REPO')}")
        else:
            st.warning(
                "Sem GITHUB_TOKEN/GITHUB_REPO em secrets. Vou salvar somente localmente "
                "(não persistente no Streamlit Cloud)."
            )

    tab_proc, tab_conv, tab_help = st.tabs(["🧾 Processar relatório", "🏷️ Convênios", "❓ Ajuda"])

    # --- Carrega mapping ---
    if "convenios_mapping" not in st.session_state:
        st.session_state.convenios_mapping = load_convenios_mapping()

    mapping = st.session_state.convenios_mapping

    # --- Aba Convênios ---
    with tab_conv:
        st.subheader("Cadastro de convênios → meio de faturamento")
        st.write(
            "Aqui você cadastra **uma única vez** o meio de faturamento para cada convênio. "
            "Depois, qualquer novo relatório reaproveita automaticamente."
        )

        df_map = pd.DataFrame(
            sorted([(k, v) for k, v in mapping.items()], key=lambda x: x[0].lower()),
            columns=["Convênio (chave)", "Faturamento"],
        )

        edited = st.data_editor(
            df_map,
            num_rows="dynamic",
            hide_index=True,
            column_config={
                "Faturamento": st.column_config.SelectboxColumn(
                    "Faturamento",
                    options=FATURAMENTO_OPCOES,
                    help="Escolha: AMHPDF, HOSPITAL, DIRETO (ou deixe em branco)",
                )
            },
            use_container_width=True,
        )

        col1, col2 = st.columns([1, 3])
        with col1:
            if st.button("💾 Salvar cadastro", type="primary"):
                new_map = {
                    str(r["Convênio (chave)"]).strip(): str(r["Faturamento"]).strip()
                    for _, r in edited.iterrows()
                    if str(r["Convênio (chave)"]).strip()
                }
                st.session_state.convenios_mapping = new_map
                save_convenios_mapping(new_map)
                st.success("Cadastro salvo!")
        with col2:
            st.caption(
                "Dica: a **chave** do convênio é o nome já sem códigos entre parênteses. "
                "Ex.: 'BRADESCO - DIRETO(1001)' vira 'BRADESCO - DIRETO'."
            )

    # --- Aba Processamento ---
    with tab_proc:
        st.subheader("Importar XLS e calcular totais por guia")
        up = st.file_uploader("Envie o arquivo .xls/.xlsx (Atendimentos Analítico)", type=["xls", "xlsx"])

        if up is None:
            st.info("Envie um arquivo para começar.")
        else:
            try:
                df, report_total = parse_atendimentos_xls(up.getvalue(), filename=up.name)
            except Exception as e:
                st.error(f"Falha ao ler o arquivo: {e}")
                st.stop()

            st.caption(
                f"Linhas importadas: {len(df):,} | Convênios únicos: {df['ConvenioKey'].nunique():,} | "
                f"Guias únicas: {df['Nr. Guia'].nunique():,}"
            )

            # convênios novos
            convenios_arquivo = sorted(df["ConvenioKey"].dropna().astype(str).unique().tolist())
            novos = [c for c in convenios_arquivo if c not in mapping]

            if novos:
                st.warning(f"Encontrados {len(novos)} convênios ainda sem meio de faturamento cadastrado.")
                df_novos = pd.DataFrame({"Convênio (chave)": novos, "Faturamento": [""] * len(novos)})

                edited_novos = st.data_editor(
                    df_novos,
                    hide_index=True,
                    column_config={
                        "Faturamento": st.column_config.SelectboxColumn(
                            "Faturamento",
                            options=FATURAMENTO_OPCOES,
                            help="Defina o meio de faturamento para cada convênio.",
                        )
                    },
                    use_container_width=True,
                )

                if st.button("💾 Salvar novos convênios"):
                    for _, r in edited_novos.iterrows():
                        k = str(r["Convênio (chave)"]).strip()
                        v = str(r["Faturamento"]).strip()
                        if k and k not in mapping:
                            mapping[k] = v

                    st.session_state.convenios_mapping = mapping
                    save_convenios_mapping(mapping)
                    st.success("Novos convênios salvos!")

            # agrega por guia (e convênio)
            df_guia = (
                df.groupby(["Nr. Guia", "ConvenioKey"], as_index=False)["Valor Total"].sum()
                .rename(columns={"ConvenioKey": "Convênio", "Valor Total": "Total da Guia"})
            )
            df_guia["Faturamento"] = df_guia["Convênio"].map(mapping).fillna("")

            calc_total = float(df_guia["Total da Guia"].sum())
            resumo = {
                "AMHPDF": float(df_guia.loc[df_guia["Faturamento"] == "AMHPDF", "Total da Guia"].sum()),
                "HOSPITAL": float(df_guia.loc[df_guia["Faturamento"] == "HOSPITAL", "Total da Guia"].sum()),
                "DIRETO": float(df_guia.loc[df_guia["Faturamento"] == "DIRETO", "Total da Guia"].sum()),
                "OUTROS": float(df_guia.loc[df_guia["Faturamento"] == "", "Total da Guia"].sum()),
            }

            st.divider()
            st.subheader("Resumo")
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Total (calculado)", format_brl(calc_total))
            c2.metric("Total AMHPDF", format_brl(resumo["AMHPDF"]))
            c3.metric("Total HOSPITAL", format_brl(resumo["HOSPITAL"]))
            c4.metric("Total DIRETO", format_brl(resumo["DIRETO"]))
            c5.metric("Outros / não vinculados", format_brl(resumo["OUTROS"]))

            if report_total is not None:
                diff = calc_total - report_total
                st.caption(
                    f"Total informado no relatório: {format_brl(report_total)} | "
                    f"Diferença (calculado - informado): {format_brl(diff)}"
                )

            colA, colB = st.columns([1, 1])
            with colA:
                if st.button("🪟 Abrir resumo em janela"):
                    resumo_dialog(resumo=resumo, report_total=report_total, calc_total=calc_total)
            with colB:
                st.download_button(
                    "⬇️ Baixar totais por guia (CSV)",
                    data=df_guia.to_csv(index=False).encode("utf-8"),
                    file_name="totais_por_guia.csv",
                    mime="text/csv",
                )

            st.subheader("Totais por guia")
            st.dataframe(
                df_guia.sort_values("Total da Guia", ascending=False),
                use_container_width=True,
                hide_index=True,
            )

   
    with tab_help:
        st.subheader("Como configurar a persistência no GitHub")
    
        md = "\n".join(
            [
                "1. Crie um repositório no GitHub e coloque estes arquivos.",
                "2. Gere um **Personal Access Token** (PAT) com permissão de escrita no repositório.",
                "3. No Streamlit Cloud, configure os secrets:",
                "",
                "```toml",
                'GITHUB_TOKEN = "ghp_..."',
                'GITHUB_REPO = "seu_usuario/seu_repo"',
                'GITHUB_BRANCH = "main"',
                'CONVENIOS_PATH = "data/convenios_faturamento.json"  # opcional',
                "```",
                "",
                "> Se você rodar localmente, também funciona usando somente o arquivo em `data/`.",
            ]
        )
        st.markdown(md)

if __name__ == "__main__":
    main()
