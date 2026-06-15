import streamlit as st
import pandas as pd
import networkx as nx
import io
import tempfile
import os
import unicodedata
import time
import ast
import json
from fpdf import FPDF

# --- Importação da IA ---
try:
    import google.generativeai as genai
    GENAI_INSTALADO = True
except ImportError:
    GENAI_INSTALADO = False

# --- Importa as nossas próprias funções locais ---
try:
    from app_functions import *
    API_INSTALADA = True
except ImportError:
    API_INSTALADA = False

# ==========================================
# CONFIGURAÇÃO DA PÁGINA
# ==========================================
st.set_page_config(
    page_title="Dashboard de Validação | Mindsight", 
    page_icon="mindsight-logo.png", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# INICIALIZAÇÃO DO ESTADO DE MEMÓRIA E SECRETS
# ==========================================
if 'dados_carregados' not in st.session_state:
    st.session_state['dados_carregados'] = False
if 'dados_clima_carregados' not in st.session_state:
    st.session_state['dados_clima_carregados'] = False
if 'is_fetching' not in st.session_state:
    st.session_state['is_fetching'] = False

try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    GEMINI_API_KEY = None

# ==========================================
# INJEÇÃO DE CSS PREMIUM (PALETA MINDSIGHT)
# ==========================================
st.markdown("""
    <style>
    .stApp { background-color: #09030f; color: #ffffff; }
    header[data-testid="stHeader"] { background-color: transparent !important; }
    [data-testid="stSidebar"] { background-color: #120520 !important; }
    div.stButton > button:first-child {
        background: linear-gradient(90deg, #6200ea 0%, #b500ff 100%);
        color: white; border: none; border-radius: 6px; font-weight: bold;
        box-shadow: 0px 4px 10px rgba(181, 0, 255, 0.3); transition: all 0.3s ease;
    }
    div.stButton > button:first-child:hover {
        background: linear-gradient(90deg, #b500ff 0%, #6200ea 100%);
        transform: translateY(-2px); box-shadow: 0px 6px 15px rgba(181, 0, 255, 0.5);
    }
    div.stButton > button:first-child:disabled { background: #333333; color: #888888; box-shadow: none; transform: none; }
    .btn-reset > div > button {
        background: transparent !important; border: 1px solid #b500ff !important;
        box-shadow: none !important; color: #b500ff !important;
    }
    .btn-reset > div > button:hover { background: rgba(181, 0, 255, 0.1) !important; }
    div[data-testid="stMetricValue"] { color: #d884ff; }
    div[data-testid="stMetricValue"] > div {
        white-space: normal !important; word-wrap: break-word !important;
        overflow: visible !important; text-overflow: clip !important; line-height: 1.2;
    }
    .stTabs [data-baseweb="tab-list"] { gap: 20px; }
    .stTabs [data-baseweb="tab"] { color: #b0b0b0; }
    .stTabs [aria-selected="true"] { color: #b500ff !important; border-bottom-color: #b500ff !important; }
    </style>
""", unsafe_allow_html=True)

st.title("🔍 Dashboard de Validação")

@st.dialog("ℹ️ Como obter os Tokens e o ID da Pesquisa?")
def mostrar_tutorial_tokens():
    st.markdown("""
    **1. Token do People Hub**
    * Acesse o Django do People Hub do cliente.
    * Clique em **Mindsight token extension libs** > Novo token > Salvar.
    * **Renovar token:** Marque a caixinha do usuário > "Ação" > **Recreate token**.

    **2. Token do Pesquisas**
    * Acesse o Django do Pesquisas e siga os mesmos passos acima.

    **3. ID da Campanha (Pesquisa)**
    * No Django do Pesquisas, vá em **Campaigns**. Clique na pesquisa que deseja validar.
    * O número da pesquisa é o que está na URL após "campaign/". Ex: em `...campaign/2/change/`, o ID é **2**.
    """, unsafe_allow_html=True)

st.sidebar.image("preview_mind.png", use_container_width=True)
st.sidebar.header("🔑 Credenciais de Acesso")

if st.sidebar.button("ℹ️ Como obter os Tokens e o ID?", use_container_width=True, disabled=st.session_state['is_fetching']):
    mostrar_tutorial_tokens()

st.sidebar.markdown("Preencha as informações para buscar os dados via API.")
tenant = st.sidebar.text_input("Tenant do Cliente", placeholder="ex: universal", key="input_tenant")
token_hub = st.sidebar.text_input("Token do People Hub", placeholder="Insira o token do Hub", key="input_token_hub")
token_pesquisas = st.sidebar.text_input("Token do Pesquisas", placeholder="Insira o token de Pesquisas", key="input_token_pesquisas")
id_campanha = st.sidebar.text_input("ID da Campanha (Pesquisa)", placeholder="ex: 2", key="input_id_campanha")

st.sidebar.markdown("---")
st.sidebar.header("🤖 Auditoria Inteligente")
if GEMINI_API_KEY:
    st.sidebar.success("✅ Motor semântico conectado via Secrets!")
else:
    st.sidebar.warning("⚠️ Auditoria avançada desativada (Chave não encontrada).")

st.sidebar.markdown("---")
st.sidebar.markdown('<div class="btn-reset">', unsafe_allow_html=True)
if st.sidebar.button("🔄 Iniciar Nova Validação (Limpar Dados)", use_container_width=True):
    st.session_state.clear()
    st.rerun()
st.sidebar.markdown('</div>', unsafe_allow_html=True)

# ==========================================
# CRIAÇÃO DAS ABAS PRINCIPAIS
# ==========================================
aba_estrutura, aba_clima = st.tabs([
    "🌳 Validação de Estrutura e Hierarquia", 
    "🌤️ Validação de Pesquisa de Clima"
])

# ==========================================
# FUNÇÕES AUXILIARES SEGURAS
# ==========================================
@st.cache_data
def load_data(file):
    if file.name.endswith('.csv'): return pd.read_csv(file)
    else: return pd.read_excel(file)

def filtrar_por_data(df, data_ref):
    """Filtro de data imune a fusos horários e inversões de mês/dia"""
    if df.empty or 'start_date' not in df.columns: 
        return df
    
    df = df.copy()
    data_ref = pd.to_datetime(data_ref).normalize()
    
    # A MÁGICA: Tiramos o dayfirst=True para ele respeitar o YYYY-MM-DD da API
    df['start_dt'] = pd.to_datetime(df['start_date'], format='mixed', errors='coerce')
    if df['start_dt'].dt.tz is not None:
        df['start_dt'] = df['start_dt'].dt.tz_localize(None)
    df['start_dt'] = df['start_dt'].dt.normalize()
    
    if 'end_date' not in df.columns:
        df['end_dt'] = pd.NaT
    else:
        df['end_dt'] = pd.to_datetime(df['end_date'], format='mixed', errors='coerce')
        if df['end_dt'].dt.tz is not None:
            df['end_dt'] = df['end_dt'].dt.tz_localize(None)
        df['end_dt'] = df['end_dt'].dt.normalize()
        
    mask = (df['start_dt'] <= data_ref) & (df['end_dt'].isna() | (df['end_dt'] >= data_ref))
    return df.drop(columns=['start_dt', 'end_dt'])[mask]

def padronizar_id(serie):
    """Transforma 00123, 123.0 e '123' na exata mesma coisa: '123'"""
    def safe_convert(val):
        if pd.isna(val): return ""
        val_str = str(val).strip()
        if val_str.endswith('.0'): val_str = val_str[:-2]
        try: return str(int(val_str))
        except: return val_str
    return serie.apply(safe_convert)

def remover_acentos(texto):
    if pd.isna(texto): return ""
    return ''.join(c for c in unicodedata.normalize('NFD', str(texto)) if unicodedata.category(c) != 'Mn')

def safe_html(text):
    if pd.isna(text): return ""
    return str(text).replace("'", "&#39;").replace('"', '&quot;').replace('\n', ' ')

def gerar_sufixo_invisivel(alvo, is_expanded):
    if not alvo or not is_expanded: return ""
    bin_str = format(abs(hash(str(alvo))), 'b')
    return "".join("\u200B" if bit == '0' else "\u200C" for bit in bin_str)

def clean_val(val):
    if pd.isna(val): return val
    s = str(val).strip()
    if s.endswith('.0'): s = s[:-2]
    return s

def cor_fundo_erro(df):
    return ['background-color: #2b0000; color: #ffcccc'] * len(df)


# ==========================================
# ABA 1: ESTRUTURA E HIERARQUIA
# ==========================================
with aba_estrutura:
    st.header("🌳 Validação de Estrutura Organizacional")
    
    if not API_INSTALADA:
        st.error("🚨 O arquivo de funções (`app_functions.py`) não foi encontrado!")
        st.stop()
    
    data_pesquisa = st.date_input("Selecione a Data da Pesquisa para Validação")
    st.markdown("### 📥 Importação de Bases via API")
    
    if st.button("🚀 Puxar Dados da Estrutura", use_container_width=True):
        if not tenant or not token_hub:
            st.warning("⚠️ Por favor, preencha o **Tenant** e o **Token do People Hub** na barra lateral antes de puxar os dados.")
        else:
            st.session_state['is_fetching'] = True
            progresso_visual = st.progress(0)
            historico_sucesso = st.empty()
            logs = ""

            try:
                with st.spinner("⏳ Baixando **Funcionários**..."):
                    st.session_state['df_funcionarios'] = get_hub_employees_api(tenant, token_hub)
                progresso_visual.progress(16)
                logs += "✅ Funcionários baixados com sucesso!<br>"
                historico_sucesso.markdown(logs, unsafe_allow_html=True)

                with st.spinner("⏳ Baixando **Gestores dos Funcionários**..."):
                    st.session_state['df_gestores'] = get_hub_managers_api(tenant, token_hub)
                progresso_visual.progress(33)
                logs += "✅ Gestores baixados com sucesso!<br>"
                historico_sucesso.markdown(logs, unsafe_allow_html=True)

                with st.spinner("⏳ Baixando **Instâncias de Áreas**..."):
                    st.session_state['df_instancias'] = get_hub_area_instances_api(tenant, token_hub)
                progresso_visual.progress(50)
                logs += "✅ Instâncias de Áreas baixadas com sucesso!<br>"
                historico_sucesso.markdown(logs, unsafe_allow_html=True)

                with st.spinner("⏳ Baixando **Áreas dos Funcionários**..."):
                    st.session_state['df_areas_func'] = get_hub_areas_api(tenant, token_hub)
                progresso_visual.progress(66)
                logs += "✅ Áreas dos Funcionários baixadas com sucesso!<br>"
                historico_sucesso.markdown(logs, unsafe_allow_html=True)

                with st.spinner("⏳ Baixando **Registros de Funcionários**..."):
                    st.session_state['df_reg_func'] = get_hub_companies_api(tenant, token_hub)
                progresso_visual.progress(83)
                logs += "✅ Registros de Funcionários baixados com sucesso!<br>"
                historico_sucesso.markdown(logs, unsafe_allow_html=True)

                with st.spinner("⏳ Baixando **Hierarquia de Áreas**..."):
                    st.session_state['df_hierarquia'] = get_hub_area_hierarchy_api(tenant, token_hub)
                progresso_visual.progress(100)
                logs += "✅ Hierarquia de Áreas baixada com sucesso!<br>"
                historico_sucesso.markdown(logs, unsafe_allow_html=True)

                st.session_state['is_fetching'] = False
                st.session_state['dados_carregados'] = True
                st.toast('🎉 Dados da estrutura importados com sucesso!', icon='🎉')
                time.sleep(1)
                st.rerun()

            except Exception as e:
                st.session_state['is_fetching'] = False
                st.error(f"❌ Ocorreu um erro ao comunicar com a API: {e}")
                progresso_visual.empty()

    if st.session_state.get('dados_carregados'):
        df_areas_func = st.session_state.get('df_areas_func', pd.DataFrame())
        df_hierarquia = st.session_state.get('df_hierarquia', pd.DataFrame())
        df_instancias = st.session_state.get('df_instancias', pd.DataFrame())
        df_funcionarios = st.session_state.get('df_funcionarios', pd.DataFrame())
        df_reg_func = st.session_state.get('df_reg_func', pd.DataFrame())
        df_gestores = st.session_state.get('df_gestores', pd.DataFrame())
        
        df_areas_func_filtrado = filtrar_por_data(df_areas_func, data_pesquisa)
        df_hierarquia_filtrado = filtrar_por_data(df_hierarquia, data_pesquisa)
        df_reg_func_filtrado = filtrar_por_data(df_reg_func, data_pesquisa)
        df_gestores_filtrado = filtrar_por_data(df_gestores, data_pesquisa)

        if 'name' in df_funcionarios.columns:
            df_funcionarios['Nome Completo'] = df_funcionarios['name'].fillna('Desconhecido')
        else:
            primeiro_nome = df_funcionarios.get('first_name', pd.Series(dtype=str)).fillna('')
            ultimo_nome = df_funcionarios.get('last_name', pd.Series(dtype=str)).fillna('')
            df_funcionarios['Nome Completo'] = (primeiro_nome + " " + ultimo_nome).str.strip()
            df_funcionarios['Nome Completo'] = df_funcionarios['Nome Completo'].replace('', 'Desconhecido')

        # === AQUI ESTAVA O PROBLEMA DA TABELA VAZIA ===
        # Cria a coluna limpa na tabela mãe para os filtros de exibição
        df_funcionarios['id_clean'] = padronizar_id(df_funcionarios.get('id', pd.Series(dtype=str)))
        
        id_col = df_funcionarios['id_clean']
        nome_col = df_funcionarios.get('Nome Completo', pd.Series(dtype=str))
        mapa_nomes_func = dict(zip(id_col, nome_col))
        
        # Pega IDs Ativos limpinhos e remove vazios
        ativos_ids = set(padronizar_id(df_reg_func_filtrado.get('person', pd.Series())).unique()) - {""}
        
        mapa_datas_inicio = {}
        if 'person' in df_reg_func_filtrado.columns and 'start_date' in df_reg_func_filtrado.columns:
            df_reg_func_filtrado['person_str'] = padronizar_id(df_reg_func_filtrado['person'])
            
            # Aqui também tiramos o dayfirst=True para a data de inicio aparecer certa na tela
            df_reg_func_filtrado['start_date'] = pd.to_datetime(df_reg_func_filtrado['start_date'], format='mixed', errors='coerce')
            mapa_datas_inicio = df_reg_func_filtrado.groupby('person_str')['start_date'].max().dt.strftime('%d/%m/%Y').to_dict()

        mapa_nome_para_id = dict(zip(df_instancias.get('name', []), df_instancias.get('id', [])))
        def traduzir_area_para_id(val):
            if isinstance(val, str) and val in mapa_nome_para_id:
                return mapa_nome_para_id[val]
            return val 

        df_areas_func_filtrado['area_id'] = df_areas_func_filtrado.get('area', pd.Series()).apply(traduzir_area_para_id)

        # ==================================
        # KPIs EXECUTIVOS
        # ==================================
        st.markdown("---")
        col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
        col_kpi1.metric("👥 Total Colaboradores Ativos", len(ativos_ids))
        col_kpi2.metric("🏢 Total de Áreas Identificadas", len(df_instancias))
        total_gestores = len(df_gestores_filtrado['manager'].dropna().unique()) if 'manager' in df_gestores_filtrado.columns else 0
        col_kpi3.metric("👔 Total de Gestores Identificados", total_gestores)

        # --- 1. ÁREAS ---
        st.markdown("---")
        st.subheader("1. Validação de Hierarquia de Áreas")
        
        mapa_nomes_areas = dict(zip(df_instancias.get('id', []), df_instancias.get('name', [])))
        
        contagem_direta_areas = {}
        if 'area_id' in df_areas_func_filtrado.columns and 'person' in df_areas_func_filtrado.columns:
            contagem_direta_areas = df_areas_func_filtrado.groupby('area_id')['person'].nunique().to_dict()

        G_areas = nx.DiGraph()
        all_defined_area_ids = df_instancias.get('id', pd.Series()).unique()
        G_areas.add_nodes_from(all_defined_area_ids)

        if 'parent' in df_hierarquia_filtrado.columns and 'area' in df_hierarquia_filtrado.columns:
            for _, row in df_hierarquia_filtrado.iterrows():
                parent, row_area = row['parent'], row['area']
                if pd.notna(parent) and pd.notna(row_area):
                    G_areas.add_edge(parent, row_area)
                
        for area_id in contagem_direta_areas.keys():
            if not G_areas.has_node(area_id):
                G_areas.add_node(area_id)

        ciclos_areas = list(nx.simple_cycles(G_areas))
        if ciclos_areas:
            st.error(f"🚨 **ATENÇÃO: Loops de Hierarquia de Áreas Detectados! ({len(ciclos_areas)} loop(s))**")
            for ciclo in ciclos_areas:
                caminho = " ➔ ".join([str(mapa_nomes_areas.get(no, no)) for no in ciclo]) + f" ➔ {mapa_nomes_areas.get(ciclo[0], ciclo[0])}"
                st.warning(f"Loop: {caminho}")

        def calcular_total_areas_seguro(node, visited=None):
            if visited is None: visited = set()
            if node in visited: return 0
            visited.add(node)
            total = contagem_direta_areas.get(node, 0)
            for child in G_areas.successors(node):
                total += calcular_total_areas_seguro(child, visited.copy())
            return total

        areas_raiz = [node for node in G_areas.nodes() if G_areas.in_degree(node) == 0]
        areas_alcancaveis = set()
        for raiz in areas_raiz:
            areas_alcancaveis.update(nx.descendants(G_areas, raiz))
            areas_alcancaveis.add(raiz)
            
        areas_isoladas = set(G_areas.nodes()) - areas_alcancaveis
        pseudo_raizes_areas = []
        if areas_isoladas:
            for comp in nx.weakly_connected_components(G_areas.subgraph(areas_isoladas)):
                pseudo_raizes_areas.append(list(comp)[0]) 
                
        todas_raizes_areas = areas_raiz + list(set(pseudo_raizes_areas))
        todas_raizes_areas.sort(key=lambda x: calcular_total_areas_seguro(x), reverse=True)

        col_titulo_area, col_busca_area = st.columns([2, 1])
        with col_titulo_area:
            st.markdown("**Visualização da Estrutura de Áreas**")
        with col_busca_area:
            opcoes_areas = [None] + sorted(list(G_areas.nodes()), key=lambda x: str(mapa_nomes_areas.get(x, x)))
            alvo_area = st.selectbox(
                "🔍 Buscar Área (Digite ou selecione):", 
                options=opcoes_areas, 
                format_func=lambda x: "--- Selecione uma Área ---" if x is None else f"{mapa_nomes_areas.get(x, x)} (ID: {x})"
            )
        
        ancestrais_area = nx.ancestors(G_areas, alvo_area) if alvo_area else set()
        
        def render_tree_areas(node, visited=None, level=0):
            if visited is None: visited = set()
            if node in visited: return
            visited.add(node)
            
            is_alvo = (node == alvo_area)
            nome = mapa_nomes_areas.get(node, f"Área ID {node}")
            
            if is_alvo:
                nome_expander = f"✨ <span style='color: #b500ff;'>**{nome}**</span> ✨"
                nome_leaf = f"<span style='text-shadow: 0 0 10px #b500ff, 0 0 20px #b500ff; color: white; font-weight: bold;'>✨ {nome} ✨</span>"
            else:
                nome_expander = f"**{nome}**"
                nome_leaf = f"**{nome}**"
                
            qtd_direta = contagem_direta_areas.get(node, 0)
            qtd_total = calcular_total_areas_seguro(node)
            alerta_vazio = " 🔴 **Sem funcionários**" if qtd_total == 0 else ""
            
            children = list(G_areas.successors(node))
            children.sort(key=lambda x: calcular_total_areas_seguro(x), reverse=True)
            
            is_expanded = (node in ancestrais_area)
            sufixo_invisivel = gerar_sufixo_invisivel(alvo_area, is_expanded)
            
            if children:
                label = f"[Nível {level}] 🏢 {nome_expander} — `{qtd_total} Total` (_{qtd_direta} diretos_){alerta_vazio}{sufixo_invisivel}"
                with st.expander(label, expanded=is_expanded):
                    for child in children:
                        render_tree_areas(child, visited.copy(), level + 1)
            else:
                if is_alvo:
                    st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; [Nível {level}] 🏢 {nome_leaf} — `{qtd_total} Total` (_{qtd_direta} diretos_){alerta_vazio}", unsafe_allow_html=True)
                else:
                    st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; [Nível {level}] 🏢 {nome_leaf} — `{qtd_total} Total` (_{qtd_direta} diretos_){alerta_vazio}")

        if len(todas_raizes_areas) > 3:
            st.warning(f"⚠️ **Atenção:** Foram encontradas **{len(todas_raizes_areas)} áreas no Nível 0** (Áreas sem uma área superior). Verifique se a parametrização de hierarquia no sistema está correta (normalmente existe uma área global principal acima das demais).")

        with st.expander("📂 Mostrar / Ocultar Estrutura de Áreas Completa", expanded=True):
            for raiz in todas_raizes_areas:
                render_tree_areas(raiz, level=0)

        st.markdown("**⚠️ Funcionários Ativos sem Área Vinculada**")
        com_area_ids = set(padronizar_id(df_areas_func_filtrado.get('person', pd.Series())).unique()) - {""}
        sem_area_ids = ativos_ids - com_area_ids
        
        df_exibicao_area = pd.DataFrame(columns=['Nome Completo', 'email', 'Data de Início'])
        if sem_area_ids:
            st.warning(f"**{len(sem_area_ids)}** funcionário(s) com contrato ativo sem área vinculada nesta data.")
            # Filtra de forma garantida pela id_clean
            df_func_sem_area = df_funcionarios[df_funcionarios['id_clean'].isin(sem_area_ids)].copy()
            df_func_sem_area['Data de Início'] = df_func_sem_area['id_clean'].map(mapa_datas_inicio)
            
            if 'email' not in df_func_sem_area.columns: df_func_sem_area['email'] = ''
            df_exibicao_area = df_func_sem_area[['Nome Completo', 'email', 'Data de Início']]
            
            st.dataframe(df_exibicao_area.style.apply(cor_fundo_erro, axis=1), use_container_width=True, hide_index=True)
        else:
            st.toast("✅ Todos os funcionários ativos possuem uma área vinculada.", icon="✅")

        # --- 2. GESTORES ---
        st.markdown("---")
        st.subheader("2. Validação de Hierarquia de Gestores")

        contagem_direta_gestores = {}
        G_gestores = nx.DiGraph()

        if 'manager' in df_gestores_filtrado.columns and 'person' in df_gestores_filtrado.columns:
            contagem_direta_gestores = df_gestores_filtrado.groupby('manager')['person'].nunique().to_dict()
            for _, row in df_gestores_filtrado.iterrows():
                gestor, subordinado = row['manager'], row['person']
                if pd.notna(gestor) and pd.notna(subordinado):
                    G_gestores.add_edge(gestor, subordinado)
                    
            for subordinado in df_gestores_filtrado['person'].dropna().unique():
                if not G_gestores.has_node(subordinado):
                    G_gestores.add_node(subordinado)

        ciclos_gestores = list(nx.simple_cycles(G_gestores))
        if ciclos_gestores:
            st.error(f"🚨 **ATENÇÃO: Ciclos de Gestão Detectados! ({len(ciclos_gestores)} ciclo(s))**")
            for ciclo in ciclos_gestores:
                caminho = " ➔ ".join([str(mapa_nomes_func.get(padronizar_id(pd.Series([no]))[0], f"ID {no}")) for no in ciclo]) + f" ➔ {mapa_nomes_func.get(padronizar_id(pd.Series([ciclo[0]]))[0], f'ID {ciclo[0]}')}"
                st.warning(f"Ciclo: {caminho}")

        def calcular_total_gestores_seguro(node, visited=None):
            if visited is None: visited = set()
            if node in visited: return 0
            visited.add(node)
            total = contagem_direta_gestores.get(node, 0)
            for child in G_gestores.successors(node):
                total += calcular_total_gestores_seguro(child, visited.copy())
            return total

        gestores_raiz = [node for node in G_gestores.nodes() if G_gestores.in_degree(node) == 0]
        gestores_alcancaveis = set()
        for raiz in gestores_raiz:
            gestores_alcancaveis.update(nx.descendants(G_gestores, raiz))
            gestores_alcancaveis.add(raiz)
            
        gestores_isolados = set(G_gestores.nodes()) - gestores_alcancaveis
        pseudo_raizes_gestores = []
        if gestores_isolados:
            for comp in nx.weakly_connected_components(G_gestores.subgraph(gestores_isolados)):
                pseudo_raizes_gestores.append(list(comp)[0])
                
        todas_raizes_gestores = gestores_raiz + list(set(pseudo_raizes_gestores))
        todas_raizes_gestores.sort(key=lambda x: calcular_total_gestores_seguro(x), reverse=True)

        col_titulo_gestor, col_busca_gestor = st.columns([2, 1])
        with col_titulo_gestor:
            st.markdown("**Visualização da Estrutura de Gestão**")
        with col_busca_gestor:
            opcoes_gestores = [None] + sorted(list(G_gestores.nodes()), key=lambda x: str(mapa_nomes_func.get(padronizar_id(pd.Series([x]))[0], x)))
            alvo_gestor = st.selectbox(
                "🔍 Buscar Gestor/Colaborador:", 
                options=opcoes_gestores, 
                format_func=lambda x: "--- Selecione um Nome ---" if x is None else f"{mapa_nomes_func.get(padronizar_id(pd.Series([x]))[0], x)} (ID: {x})"
            )

        ancestrais_gestor = nx.ancestors(G_gestores, alvo_gestor) if alvo_gestor else set()

        def render_tree_gestores(node, visited=None, level=0):
            if visited is None: visited = set()
            if node in visited: return
            visited.add(node)
            
            is_alvo = (node == alvo_gestor)
            nome = mapa_nomes_func.get(padronizar_id(pd.Series([node]))[0], f"Colaborador ID {node}")
            
            if is_alvo:
                nome_expander = f"✨ <span style='color: #b500ff;'>**{nome}**</span> ✨"
                nome_leaf = f"<span style='text-shadow: 0 0 10px #b500ff, 0 0 20px #b500ff; color: white; font-weight: bold;'>✨ {nome} ✨</span>"
            else:
                nome_expander = f"**{nome}**"
                nome_leaf = f"**{nome}**"
                
            qtd_direta = contagem_direta_gestores.get(node, 0)
            qtd_total = calcular_total_gestores_seguro(node)
            
            children = list(G_gestores.successors(node))
            children.sort(key=lambda x: calcular_total_gestores_seguro(x), reverse=True)
            
            is_expanded = (node in ancestrais_gestor)
            sufixo_invisivel = gerar_sufixo_invisivel(alvo_gestor, is_expanded)
            
            if children:
                label = f"[Nível {level}] 👤 {nome_expander} — `{qtd_total} liderados totais` (_{qtd_direta} diretos_){sufixo_invisivel}"
                with st.expander(label, expanded=is_expanded):
                    for child in children:
                        render_tree_gestores(child, visited.copy(), level + 1)
            else:
                if is_alvo:
                    st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; [Nível {level}] 👤 {nome_leaf}", unsafe_allow_html=True)
                else:
                    st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; [Nível {level}] 👤 {nome_leaf}")

        if len(todas_raizes_gestores) > 5:
            st.warning(f"⚠️ **Atenção:** Foram encontrados **{len(todas_raizes_gestores)} gestores no Nível 0** (ou seja, são gestores sem gestores). Verifique se isso está correto.")

        with st.expander("📂 Mostrar / Ocultar Estrutura de Gestão Completa", expanded=True):
            for raiz in todas_raizes_gestores:
                render_tree_gestores(raiz, level=0)

        st.markdown("**⚠️ Funcionários Ativos sem Gestor Vinculado**")
        
        com_gestor_ids = set(padronizar_id(df_gestores_filtrado.get('person', pd.Series())).unique()) - {""}
        sem_gestor_ids = ativos_ids - com_gestor_ids
        
        df_exibicao_gestor = pd.DataFrame(columns=['Nome Completo', 'email', 'Data de Início', 'É Topo de Cadeia?'])
        if sem_gestor_ids:
            st.warning(f"**{len(sem_gestor_ids)}** funcionário(s) com contrato ativo sem gestor superior nesta data.")
            
            df_func_sem_gestor = df_funcionarios[df_funcionarios['id_clean'].isin(sem_gestor_ids)].copy()
            df_func_sem_gestor['Data de Início'] = df_func_sem_gestor['id_clean'].map(mapa_datas_inicio)
            df_func_sem_gestor['É Topo de Cadeia?'] = df_func_sem_gestor.get('id', pd.Series()).apply(lambda x: "Sim" if x in gestores_raiz else "Não")
            
            if 'email' not in df_func_sem_gestor.columns: df_func_sem_gestor['email'] = ''
            df_exibicao_gestor = df_func_sem_gestor[['Nome Completo', 'email', 'Data de Início', 'É Topo de Cadeia?']]
            
            st.dataframe(df_exibicao_gestor.style.apply(cor_fundo_erro, axis=1), use_container_width=True, hide_index=True)
        else:
            st.toast("✅ Todos os funcionários ativos possuem um gestor vinculado.", icon="✅")

        # --- 3. EXPORTAÇÕES GERAIS ---
        def construir_tabela_arvore_areas(node, visited=None, level=0, rows=None):
            if visited is None: visited = set()
            if rows is None: rows = []
            if node in visited:
                rows.append({f"Nível {level}": f"🔄 Loop bloqueado: {mapa_nomes_areas.get(node, node)}"})
                return rows
            visited.add(node)
            nome = mapa_nomes_areas.get(node, f"ID {node}")
            qtd_total = calcular_total_areas_seguro(node)
            row = {f"Nível {i}": "" for i in range(level)}
            row[f"Nível {level}"] = f"{nome} ({qtd_total} func.)"
            rows.append(row)
            for child in G_areas.successors(node):
                construir_tabela_arvore_areas(child, visited.copy(), level + 1, rows)
            return rows

        def construir_tabela_arvore_gestores(node, visited=None, level=0, rows=None):
            if visited is None: visited = set()
            if rows is None: rows = []
            if node in visited:
                rows.append({f"Nível {level}": f"🔄 Loop bloqueado: {mapa_nomes_func.get(node, node)}"})
                return rows
            visited.add(node)
            nome = mapa_nomes_func.get(node, f"ID {node}")
            qtd_total = calcular_total_gestores_seguro(node)
            row = {f"Nível {i}": "" for i in range(level)}
            if qtd_total > 0: row[f"Nível {level}"] = f"{nome} ({qtd_total} liderados)"
            else: row[f"Nível {level}"] = nome
            rows.append(row)
            for child in G_gestores.successors(node):
                construir_tabela_arvore_gestores(child, visited.copy(), level + 1, rows)
            return rows

        linhas_arvore_areas = []
        for raiz in todas_raizes_areas: linhas_arvore_areas.extend(construir_tabela_arvore_areas(raiz))
        df_excel_arvore_areas = pd.DataFrame(linhas_arvore_areas).fillna("")

        linhas_arvore_gestores = []
        for raiz in todas_raizes_gestores: linhas_arvore_gestores.extend(construir_tabela_arvore_gestores(raiz))
        df_excel_arvore_gestores = pd.DataFrame(linhas_arvore_gestores).fillna("")

        st.markdown("---")
        st.subheader("📥 3. Exportação de Arquivos Estáticos")
        
        col1, col2 = st.columns(2)
        output_excel = io.BytesIO()
        with pd.ExcelWriter(output_excel, engine='xlsxwriter') as writer:
            if not df_exibicao_area.empty: df_exibicao_area.to_excel(writer, index=False, sheet_name='Pendências_Sem_Area')
            if not df_exibicao_gestor.empty: df_exibicao_gestor.to_excel(writer, index=False, sheet_name='Pendências_Sem_Gestor')
            if df_exibicao_area.empty and df_exibicao_gestor.empty:
                pd.DataFrame({'Status': ['Tudo certo! Nenhuma pendência.']}).to_excel(writer, index=False, sheet_name='Pendências')
            if not df_excel_arvore_areas.empty: df_excel_arvore_areas.to_excel(writer, index=False, sheet_name='Arvore_Areas')
            if not df_excel_arvore_gestores.empty: df_excel_arvore_gestores.to_excel(writer, index=False, sheet_name='Arvore_Gestores')
                
        excel_data = output_excel.getvalue()
        col1.download_button(label="📊 Exportar para Excel (.xlsx)", data=excel_data, file_name=f"Estrutura_{data_pesquisa.strftime('%Y%m%d')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(200, 10, txt=f"Relatorio de Inconsistencias - {data_pesquisa.strftime('%d/%m/%Y')}", ln=True, align='C')
        pdf.ln(10)
        
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(200, 10, txt="1. Funcionarios Ativos sem Area Vinculada", ln=True)
        pdf.set_font("Arial", size=10)
        if df_exibicao_area.empty:
            pdf.cell(200, 10, txt="Nenhuma pendencia encontrada.", ln=True)
        else:
            for _, row in df_exibicao_area.iterrows():
                texto = f"- {row['Nome Completo']} | E-mail: {row.get('email','')} | Inicio: {row['Data de Início']}"
                pdf.cell(200, 6, txt=remover_acentos(texto), ln=True)
        
        pdf.ln(10)
        
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(200, 10, txt="2. Funcionarios Ativos sem Gestor Vinculado", ln=True)
        pdf.set_font("Arial", size=10)
        if df_exibicao_gestor.empty:
            pdf.cell(200, 10, txt="Nenhuma pendencia encontrada.", ln=True)
        else:
            for _, row in df_exibicao_gestor.iterrows():
                texto = f"- {row['Nome Completo']} | E-mail: {row.get('email','')} | Inicio: {row['Data de Início']} | Topo: {row['É Topo de Cadeia?']}"
                pdf.cell(200, 6, txt=remover_acentos(texto), ln=True)
                
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            pdf.output(tmp.name)
            with open(tmp.name, "rb") as f:
                pdf_data = f.read()
        os.remove(tmp.name) 

        col2.download_button(label="📄 Exportar Pendências para PDF (.pdf)", data=pdf_data, file_name=f"Pendencias_Estrutura_{data_pesquisa.strftime('%Y%m%d')}.pdf", mime="application/pdf", use_container_width=True)

# ==========================================
# ABA 2: PESQUISA DE CLIMA
# ==========================================
with aba_clima:
    st.header("🌤️ Validação da Estrutura da Pesquisa de Clima")
    
    if not API_INSTALADA:
        st.error("🚨 O arquivo de funções (`app_functions.py`) não foi encontrado!")
        st.stop()

    st.markdown("### 📥 Importação de Bases da Pesquisa")
    
    if st.button("🚀 Puxar Dados da Pesquisa de Clima", use_container_width=True):
        if not tenant or not token_pesquisas or not id_campanha:
            st.warning("⚠️ Por favor, preencha o **Tenant**, o **Token do Pesquisas** e o **ID da Campanha** na barra lateral.")
        elif not id_campanha.strip().isdigit():
            st.error("🚨 O **ID da Campanha** deve ser um número inteiro (ex: 123).")
        elif not st.session_state.get('dados_carregados'):
            st.error("🚨 **Atenção:** Você precisa primeiro **Puxar Dados da Estrutura** na aba anterior, pois usaremos os funcionários do Hub para cruzar com a pesquisa!")
        else:
            st.session_state['is_fetching'] = True
            progresso_clima = st.progress(0)
            hist_clima = st.empty()
            logs_clima = ""

            try:
                id_camp_int = int(id_campanha.strip())

                with st.spinner("⏳ Baixando **Campanhas**..."):
                    st.session_state['df_pesquisa_camp'] = get_pesquisa_campaigns_api(tenant, token_pesquisas)
                progresso_clima.progress(25)
                logs_clima += "✅ Campanhas baixadas com sucesso!<br>"
                hist_clima.markdown(logs_clima, unsafe_allow_html=True)

                with st.spinner("⏳ Baixando **Perguntas (Choices)**..."):
                    st.session_state['df_pesquisa_choice'] = get_pesquisa_choice_question_api(tenant, token_pesquisas)
                progresso_clima.progress(50)
                logs_clima += "✅ Perguntas baixadas com sucesso!<br>"
                hist_clima.markdown(logs_clima, unsafe_allow_html=True)

                with st.spinner("⏳ Baixando **Contatos da Campanha**..."):
                    st.session_state['df_pesquisa_contatos'] = get_pesquisa_contact_api(tenant, token_pesquisas, id_camp_int)
                progresso_clima.progress(75)
                logs_clima += "✅ Contatos baixados com sucesso!<br>"
                hist_clima.markdown(logs_clima, unsafe_allow_html=True)

                with st.spinner("⏳ Baixando **Estrutura da Pesquisa (Surveys)**..."):
                    st.session_state['df_pesquisa_survey'] = get_pesquisa_survey_api(tenant, token_pesquisas)
                progresso_clima.progress(100)
                logs_clima += "✅ Estrutura mapeada com sucesso!<br>"
                hist_clima.markdown(logs_clima, unsafe_allow_html=True)

                st.session_state['dados_clima_carregados'] = True
                st.session_state['is_fetching'] = False
                st.toast("🎉 Dados da pesquisa importados com sucesso!", icon='🎉')
                time.sleep(1)
                st.rerun()

            except Exception as e:
                st.session_state['is_fetching'] = False
                st.error(f"❌ Ocorreu um erro ao comunicar com a API: {e}")
                progresso_clima.empty()

    if st.session_state.get('dados_clima_carregados'):
        df_camp = st.session_state.get('df_pesquisa_camp', pd.DataFrame())
        df_choice_total = st.session_state.get('df_pesquisa_choice', pd.DataFrame())
        df_survey_full = st.session_state.get('df_pesquisa_survey', pd.DataFrame())
        df_contatos = st.session_state.get('df_pesquisa_contatos', pd.DataFrame())
        df_func = st.session_state.get('df_funcionarios', pd.DataFrame())

        nome_pesquisa = "Nome Indisponível"
        df_choice = pd.DataFrame()

        if not df_camp.empty and 'id' in df_camp.columns:
            pesquisa_atual = df_camp[df_camp['id'].astype(str) == str(id_campanha).strip()]
            if not pesquisa_atual.empty and 'name' in pesquisa_atual.columns:
                nome_pesquisa = pesquisa_atual['name'].values[0]

        # --- LÓGICA DE FILTRO SEGURA DA SURVEY ---
        id_survey_vinculada = None
        try:
            if not df_camp.empty and 'id' in df_camp.columns:
                pesquisa_atual = df_camp[df_camp['id'].astype(str) == str(id_campanha).strip()]
                if not pesquisa_atual.empty and 'survey.id' in pesquisa_atual.columns:
                    id_survey_vinculada = pesquisa_atual['survey.id'].values[0]
                    
            if id_survey_vinculada is not None and not df_survey_full.empty and 'id' in df_survey_full.columns:
                df_survey_filtrado = df_survey_full.loc[df_survey_full['id'] == int(id_survey_vinculada)]
                
                if not df_survey_filtrado.empty and 'questions.title' in df_survey_filtrado.columns:
                    lista_titulos_validos = df_survey_filtrado['questions.title'].dropna().unique().tolist()
                    
                    if not df_choice_total.empty and 'title' in df_choice_total.columns:
                        df_choice = df_choice_total[df_choice_total['title'].isin(lista_titulos_validos)].copy()
                    else:
                        st.warning("A base de perguntas (choices) puxada da API está vazia.")
                else:
                    st.warning(f"A Survey vinculada (ID {id_survey_vinculada}) não tem perguntas associadas no sistema ou a coluna questions.title está ausente.")
            else:
                st.error("Não foi possível encontrar o vínculo da Campanha com a Survey (coluna 'survey.id') ou a tabela de Surveys está vazia.")
        except Exception as e:
            st.error(f"🚨 Erro inesperado ao aplicar o filtro de perguntas: {e}")

        if 'email' not in df_contatos.columns: df_contatos['email'] = ''
        if 'first name' not in df_contatos.columns: df_contatos['first name'] = ''
        if 'last name' not in df_contatos.columns: df_contatos['last name'] = ''
        if 'email' not in df_func.columns: df_func['email'] = ''

        df_contatos_validos = df_contatos[~df_contatos['email'].astype(str).str.contains('@mindsight', case=False, na=False)].copy()
        
        st.markdown("---")
        
        col_kpi1_c, col_kpi2_c = st.columns(2)
        col_kpi1_c.markdown(f"""
            <div style="display: flex; flex-direction: column; gap: 0.2rem;">
                <p style="font-size: 0.9rem; color: #b0b0b0; margin: 0; padding: 0;">📋 Nome da Pesquisa</p>
                <p style="font-size: 2rem; color: #d884ff; font-weight: 600; margin: 0; padding: 0; line-height: 1.2; white-space: normal; word-wrap: break-word;">{nome_pesquisa}</p>
            </div>
        """, unsafe_allow_html=True)
        col_kpi2_c.metric("📨 Total de Contatos Válidos", len(df_contatos_validos))

        # ========================================================
        # VALIDAÇÃO 1: CRUZAMENTO DE CONTATOS (PESQUISA VS HUB)
        # ========================================================
        st.markdown("---")
        st.subheader("1. Validação de Contatos no People Hub")

        if 'Nome Completo' not in df_func.columns: 
            df_func['Nome Completo'] = df_func.get('name', pd.Series(dtype=str)).fillna('')

        df_func['email_clean'] = df_func['email'].astype(str).str.lower().str.strip()
        df_func['nome_clean'] = df_func['Nome Completo'].astype(str).str.lower().str.strip()
        
        df_contatos_validos['email_clean'] = df_contatos_validos['email'].astype(str).str.lower().str.strip()
        df_contatos_validos['Nome Completo'] = df_contatos_validos['first name'].astype(str).str.strip() + " " + df_contatos_validos['last name'].astype(str).str.strip()
        df_contatos_validos['nome_clean'] = df_contatos_validos['Nome Completo'].str.lower().str.strip()

        dict_email_hub = df_func.drop_duplicates('email_clean').set_index('email_clean').to_dict('index')
        dict_nome_hub = df_func.drop_duplicates('nome_clean').set_index('nome_clean').to_dict('index')
        
        mapa_instancias = {}
        if 'df_instancias' in st.session_state and not st.session_state['df_instancias'].empty:
            if 'id' in st.session_state['df_instancias'].columns and 'name' in st.session_state['df_instancias'].columns:
                for _, row in st.session_state['df_instancias'].iterrows():
                    id_str = clean_val(row.get('id'))
                    name_str = clean_val(row.get('name'))
                    if id_str: mapa_instancias[id_str] = name_str
                    if name_str: mapa_instancias[name_str] = name_str

        df_areas_f = filtrar_por_data(st.session_state.get('df_areas_func', pd.DataFrame()), data_pesquisa)
        hub_person_area = {}
        if 'person' in df_areas_f.columns and 'area' in df_areas_f.columns:
            for _, row in df_areas_f.iterrows():
                p_str = padronizar_id(pd.Series([row.get('person')]))[0]
                a_str = clean_val(row.get('area'))
                hub_person_area[p_str] = mapa_instancias.get(a_str, a_str) 

        mapa_nomes_func_global = {}
        id_col_f = padronizar_id(df_func.get('id', pd.Series(dtype=str)))
        nome_col_f = df_func.get('Nome Completo', pd.Series(dtype=str))
        for i, val in zip(id_col_f, nome_col_f):
            mapa_nomes_func_global[i] = val

        df_gestores_f = filtrar_por_data(st.session_state.get('df_gestores', pd.DataFrame()), data_pesquisa)
        hub_person_manager = {}
        if 'person' in df_gestores_f.columns and 'manager' in df_gestores_f.columns:
            for _, row in df_gestores_f.iterrows():
                p_str = padronizar_id(pd.Series([row.get('person')]))[0]
                m_str = padronizar_id(pd.Series([row.get('manager')]))[0]
                hub_person_manager[p_str] = mapa_nomes_func_global.get(m_str, "Gestor Desconhecido")

        encontrados_email = []
        encontrados_nome = []
        nao_encontrados = []

        for _, row in df_contatos_validos.iterrows():
            e_clean = row['email_clean']
            n_clean = row['nome_clean']
            nome_original = row['Nome Completo']
            email_original = row['email']
            
            if e_clean and e_clean in dict_email_hub:
                hub_id = padronizar_id(pd.Series([dict_email_hub[e_clean].get('id')]))[0]
                area_nome = hub_person_area.get(hub_id, "Sem Área")
                manager_nome = hub_person_manager.get(hub_id, "Sem Gestor")
                
                encontrados_email.append({'Nome completo': nome_original, 'Email': email_original, 'Área': area_nome, 'Gestor': manager_nome})
            elif n_clean and n_clean in dict_nome_hub:
                email_hub = dict_nome_hub[n_clean].get('email', '')
                hub_id = padronizar_id(pd.Series([dict_nome_hub[n_clean].get('id')]))[0]
                area_nome = hub_person_area.get(hub_id, "Sem Área")
                manager_nome = hub_person_manager.get(hub_id, "Sem Gestor")
                
                encontrados_nome.append({'Nome completo': nome_original, 'Email no Pesquisas': email_original, 'Email no People Hub': email_hub, 'Área': area_nome, 'Gestor': manager_nome})
            else:
                nao_encontrados.append({'Nome completo': nome_original, 'Email no Pesquisas': email_original})

        if len(encontrados_email) == len(df_contatos_validos) and len(df_contatos_validos) > 0:
            st.success("✅ Todos os contatos da pesquisa foram encontrados perfeitamente pelo **E-mail** no People Hub.")
        else:
            if encontrados_nome:
                st.warning(f"⚠️ **{len(encontrados_nome)} contato(s)** foram encontrados apenas pelo **Nome** (E-mail estava diferente ou vazio no Hub). Verifique se são as pessoas corretas:")
                st.dataframe(pd.DataFrame(encontrados_nome).style.apply(cor_fundo_erro, axis=1), hide_index=True)
            if nao_encontrados:
                st.error(f"🚨 **{len(nao_encontrados)} contato(s)** NÃO FORAM ENCONTRADOS nem por e-mail e nem por nome no People Hub!")
                st.dataframe(pd.DataFrame(nao_encontrados).style.apply(cor_fundo_erro, axis=1), hide_index=True)

        # ========================================================
        # VALIDAÇÃO 2 e 3: ESTRUTURA DE PERGUNTAS E SEMÂNTICA
        # ========================================================
        st.markdown("---")
        st.subheader("2. Validação das Alternativas e Escalas (Choices)")

        qtd_erros_perguntas = 0
        lista_problemas_perguntas = []
        
        perguntas_preparadas = []
        if 'title' in df_choice.columns:
            for _, row in df_choice.iterrows():
                titulo = row.get('title', 'Pergunta Desconhecida')
                choices_str = row.get('question_object.choices', '[]')
                try:
                    choices = ast.literal_eval(choices_str) if isinstance(choices_str, str) else choices_str
                except:
                    choices = []

                if not isinstance(choices, list) or len(choices) == 0:
                    continue
                
                choices_parsed = []
                for c in choices:
                    val_str = str(c.get('value', ''))
                    desc = str(c.get('description', '')).strip()
                    try: val_num = float(val_str)
                    except: val_num = None
                    if val_num is not None:
                        choices_parsed.append({'val': val_num, 'desc': desc})
                
                if len(choices_parsed) > 1:
                    choices_parsed.sort(key=lambda x: x['val'])
                    escala_formatada = [f"{c['val']} - {c['desc']}" for c in choices_parsed]
                    perguntas_preparadas.append({
                        "pergunta": titulo,
                        "escala_com_valores": escala_formatada
                    })

        # --- FLUXO DE INTELIGÊNCIA ARTIFICIAL ---
        if GEMINI_API_KEY and perguntas_preparadas:
            if not GENAI_INSTALADO:
                st.error("🚨 A biblioteca `google-generativeai` não está instalada. Execute `pip install google-generativeai` no terminal.")
            else:
                with st.spinner("Processando o contexto das perguntas e validando a ordem lógica..."):
                    try:
                        genai.configure(api_key=GEMINI_API_KEY)
                        model = genai.GenerativeModel('gemini-2.5-flash', generation_config={"response_mime_type": "application/json"})
                        
                        prompt = f"""
                        Você é um auditor de Experiência do Colaborador validando pesquisas de clima.
                        Receberá um JSON com perguntas e suas alternativas numéricas associadas.
                        
                        Sua tarefa é fazer 2 análises para cada pergunta:

                        REGRA 1 - ORDEM DA ESCALA:
                        A estrutura lógica de pesquisas exige que o menor valor numérico represente SEMPRE a maior discordância/negatividade e o maior valor numérico represente SEMPRE a maior concordância/positividade.
                        - Verifique se os números das opções quebram essa regra (ex: "Concordo" com valor muito baixo, "Discordo" com valor alto, ou valores repetidos).
                        - Se quebrarem, erro_ordem_escala = true.
                        
                        REGRA 2 - SEMÂNTICA (MAPEAMENTO DE INSATISFAÇÃO PARA DATAOPS):
                        Identifique se a frase da pergunta tem viés "Positiva" ou "Negativa".
                        Liste as opções que representam uma atitude negativa/insatisfação.
                        ATENÇÃO: Opções neutras NUNCA representam insatisfação. Devem ser ignoradas.
                        - Se a pergunta é Positiva, as respostas de discordância indicam insatisfação.
                        - Se a pergunta é Negativa, as respostas de concordância indicam insatisfação.
                        
                        Dados: {json.dumps(perguntas_preparadas, ensure_ascii=False)}
                        
                        Retorne ESTRITAMENTE um array JSON contendo objetos com estas exatas chaves:
                        "pergunta": (string),
                        "erro_ordem_escala": (boolean, true ou false),
                        "detalhe_erro_ordem": (string clara e educativa. Você OBRIGATORIAMENTE deve citar de forma explícita o NOME exato da alternativa e seu VALOR numérico exato que causou o problema. Exemplo: 'A opção "Concordo totalmente" recebeu o valor 1.0, o que está invertido' ou 'O valor 1.0 está repetido nas opções X e Y'. Explique amigavelmente a lógica correta em no máximo 3 frases, ou null se estiver ok),
                        "polaridade": (string "Positiva" ou "Negativa"),
                        "opcoes_insatisfacao": (array de strings com os nomes exatos das opções que indicam insatisfação)
                        """
                        
                        resposta_ia = model.generate_content(prompt)
                        analise_ia = json.loads(resposta_ia.text)
                        
                        erros_escala = [item for item in analise_ia if item.get('erro_ordem_escala')]
                        
                        st.markdown("#### 🧠 Resultado da Auditoria Inteligente")
                        
                        # Bloco 1: Exibição Crítica (Erros de Escala Desordenada/Invertida)
                        if erros_escala:
                            st.error(f"🚨 Encontramos {len(erros_escala)} pergunta(s) com a numeração das alternativas errada ou invertida!")
                            for item in erros_escala:
                                qtd_erros_perguntas += 1
                                lista_problemas_perguntas.append({
                                    'Nome da Pergunta': item['pergunta'],
                                    'Problema': f"[Ordem da Escala] {item['detalhe_erro_ordem']}"
                                })
                                with st.expander(f"⚠️ **Erro em:** {item['pergunta']}", expanded=True):
                                    st.markdown(f"**O que aconteceu?** {item['detalhe_erro_ordem']}")
                        else:
                            st.success("✅ A numeração das alternativas de todas as escalas está perfeitamente em ordem.")

                        # Bloco 2: Mapeamento Semântico para a equipe de DataOps
                        st.markdown("---")
                        st.markdown("##### 📌 Mapeamento Semântico (Apoio DataOps)")
                        st.info("Abaixo estão as opções que indicam **insatisfação** para cada pergunta. Utilize isso como guia para a parametrização dos itens da escala no People Hub.")
                        
                        perguntas_positivas = [item for item in analise_ia if item.get('polaridade', 'Positiva') == 'Positiva']
                        perguntas_negativas = [item for item in analise_ia if item.get('polaridade', 'Positiva') == 'Negativa']
                        
                        if perguntas_positivas:
                            with st.expander(f"🔹 Ver {len(perguntas_positivas)} Perguntas Positivas (Insatisfação = Discordar)", expanded=False):
                                for item in perguntas_positivas:
                                    insatisfacao = ", ".join(item.get('opcoes_insatisfacao', []))
                                    if not insatisfacao: insatisfacao = "Nenhuma identificada"
                                    st.markdown(f"**{item['pergunta']}**")
                                    st.markdown(f"↳ *Opções de insatisfação:* `{insatisfacao}`")
                                    st.markdown("---")
                                    
                        if perguntas_negativas:
                            with st.expander(f"🔻 Ver {len(perguntas_negativas)} Perguntas Negativas (Insatisfação = Concordar)", expanded=False):
                                for item in perguntas_negativas:
                                    insatisfacao = ", ".join(item.get('opcoes_insatisfacao', []))
                                    if not insatisfacao: insatisfacao = "Nenhuma identificada"
                                    st.markdown(f"**{item['pergunta']}**")
                                    st.markdown(f"↳ *Opções de insatisfação:* `{insatisfacao}`")
                                    st.markdown("---")
                                
                    except Exception as e:
                        st.error(f"Erro na análise do motor inteligente: Verifique a conexão. Detalhes: {e}")

        # --- FLUXO PADRÃO (Plano B: Matemática Básica Sem IA) ---
        elif perguntas_preparadas:
            def score_sentimento(texto):
                if pd.isna(texto): return 0
                texto = str(texto).lower()
                pos = ['concordo', 'concorda', 'sempre', 'satisfeito', 'bom', 'ótimo', 'otimo', 'excelente', 'totalmente', 'muito', 'bastante', 'identifico']
                neg = ['discordo', 'discorda', 'nunca', 'insatisfeito', 'ruim', 'péssimo', 'pessimo', 'nada', 'nenhum', 'raramente', 'pouco']
                score = 0
                for w in pos: 
                    if w in texto: score += 1
                for w in neg: 
                    if w in texto: score -= 1
                if 'não ' in texto or 'nao ' in texto: score -= 1.5 
                return score

            for p in perguntas_preparadas:
                titulo = p['pergunta']
                alternativas_texto = [alt.split(' - ', 1)[1] if ' - ' in alt else alt for alt in p['escala_com_valores']]
                
                primeira_opcao = alternativas_texto[0]
                ultima_opcao = alternativas_texto[-1]
                
                score_primeira = score_sentimento(primeira_opcao)
                score_ultima = score_sentimento(ultima_opcao)
                
                if score_primeira > score_ultima:
                    qtd_erros_perguntas += 1
                    msg = f"Possível Erro na Numeração! O menor valor está atrelado a '{primeira_opcao}' e o maior a '{ultima_opcao}'."
                    lista_problemas_perguntas.append({'Nome da Pergunta': titulo, 'Problema': msg})
                    with st.expander(f"❌ Problemas encontrados em: {titulo}", expanded=False):
                        st.markdown(f"- {msg}")

            if qtd_erros_perguntas == 0 and len(df_choice) > 0 and not GEMINI_API_KEY:
                st.success("✅ Nenhuma anomalia grave na ordem das alternativas encontrada.")

        # ========================================================
        # 4. EXPORTAÇÃO DOS DADOS DA PESQUISA (EXCEL)
        # ========================================================
        st.markdown("---")
        st.subheader("📥 3. Exportação dos Dados de Clima")
        
        df_export_enc_email = pd.DataFrame(encontrados_email)
        df_export_enc_nome = pd.DataFrame(encontrados_nome)
        df_export_nao_enc = pd.DataFrame(nao_encontrados)
        df_export_perguntas = pd.DataFrame(lista_problemas_perguntas)
        
        nome_aba_email = 'Contatos encontrados por Email'[:31] 
        nome_aba_nome = 'Contatos encontrados por Nome'[:31]
        nome_aba_nao_enc = 'Contatos não encontrados no Hub'[:31]
        nome_aba_perguntas = 'Perguntas possíveis problemas'[:31]

        output_clima = io.BytesIO()
        with pd.ExcelWriter(output_clima, engine='xlsxwriter') as writer:
            if not df_export_enc_email.empty:
                df_export_enc_email.to_excel(writer, index=False, sheet_name=nome_aba_email)
            if not df_export_enc_nome.empty:
                df_export_enc_nome.to_excel(writer, index=False, sheet_name=nome_aba_nome)
            if not df_export_nao_enc.empty:
                df_export_nao_enc.to_excel(writer, index=False, sheet_name=nome_aba_nao_enc)
            if not df_export_perguntas.empty:
                df_export_perguntas.to_excel(writer, index=False, sheet_name=nome_aba_perguntas)
                
            if df_export_enc_nome.empty and df_export_nao_enc.empty and df_export_perguntas.empty:
                pd.DataFrame({'Status': ['Pesquisa validada sem nenhum erro!']}).to_excel(writer, index=False, sheet_name='Status')

        excel_clima_data = output_clima.getvalue()
        
        st.download_button(
            label="📊 Exportar Relatório de Clima para Excel (.xlsx)", 
            data=excel_clima_data, 
            file_name=f"Relatorio_Clima_Campanha_{id_campanha}.xlsx", 
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
