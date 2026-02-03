# Processador de Atendimentos (XLS) + Cadastro de Convênios (Streamlit)

Este app faz:
- Upload do relatório **Atendimentos Analítico** (.xls/.xlsx)
- Importa os registros e calcula **total por guia**
- Mantém um cadastro persistente de **Convênio → meio de faturamento** (AMHPDF, HOSPITAL, DIRETO)
- Ao carregar um novo relatório, só pede cadastro para convênios ainda não conhecidos
- Mostra um resumo com:
  - Total do relatório
  - Total por AMHPDF / HOSPITAL / DIRETO
  - Total de **Outros** (não cadastrados)

## Estrutura
- `app.py` — interface Streamlit (abas: Processar relatório / Convênios)
- `github_storage.py` — leitura/escrita no GitHub via Contents API
- `data/convenios_faturamento.json` — base persistente (arquivo JSON)

## Rodar localmente
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Persistência no GitHub (recomendado)
No Streamlit Cloud, configure os secrets:
```toml
GITHUB_TOKEN = "ghp_..."  # PAT com permissão no repo
GITHUB_REPO = "seu_usuario/seu_repo"
GITHUB_BRANCH = "main"
CONVENIOS_PATH = "data/convenios_faturamento.json"  # opcional
```

> Sem token/repo, o app salva em `data/` localmente (não persistente no Streamlit Cloud).
