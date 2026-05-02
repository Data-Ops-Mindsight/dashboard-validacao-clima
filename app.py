import streamlit as st
import pandas as pd
import networkx as nx
import io
import tempfile
import os
import unicodedata
import time
import ast
from fpdf import FPDF

# --- Importa as nossas próprias funções locais ---
from app_functions import *
API_INSTALADA = True

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
# INICIALIZAÇÃO DO ESTADO DE MEMÓRIA
# ==========================================
if 'dados_carregados' not in st.session_state:
    st.session_state['dados_carregados'] = False
if 'dados_clima_carregados' not in st.session_state:
    st.session_state['dados_clima_carregados'] = False
if 'is_fetching' not in st.session_state:
    st.session_state['is_fetching'] = False

# ==========================================
# INJEÇÃO DE CSS PREMIUM (PALETA MINDSIGHT)
# ==========================================
st.markdown("""
    <style>
    /* Fundo Escuro Minimalista e Remoção do Topo (Deploy) */
    .stApp {
        background-color: #09030f;
        color: #ffffff;
    }
    header[data-testid="stHeader"] {
        background-color: transparent !important;
    }
    /* Menu Lateral Escuro com nuance roxa */
    [data-testid="stSidebar"] {
        background-color: #120520 !important;
    }
    /* Estilização dos Botões com Gradiente Roxo */
    div.stButton > button:first-child {
        background: linear-gradient(90deg, #6200ea 0%, #b500ff 100%);
        color: white;
        border: none;
        border-radius: 6px;
        font-weight: bold;
        box-shadow: 0px 4px 10px rgba(181, 0, 255, 0.3);
        transition: all 0.3s ease;
    }
    div.stButton > button:first-child:hover {
        background: linear-gradient(90deg, #b500ff 0%, #6200ea 100%);
        transform: translateY(-2px);
        box-shadow: 0px 6px 15px rgba(181, 0, 255, 0.5);
    }
    div.stButton > button:first-child:disabled {
        background: #333333;
        color: #888888;
        box-shadow: none;
        transform: none;
    }
    /* Botão de Reset Secundário na Sidebar */
    .btn-reset > div > button {
        background: transparent !important;
        border: 1px solid #b500ff !important;
        box-shadow: none !important;
        color: #b500ff !important;
    }
    .btn-reset > div > button:hover {
        background: rgba(181, 0, 255, 0.1) !important;
    }
    /* Números dos KPIs */
    div[data-testid="stMetricValue"] {
        color: #d884ff;
    }
    /* Tabs (Abas) */
    .stTabs [data-baseweb="tab-list"] {
        gap: 20px;
    }
    .stTabs [data-baseweb="tab"] {
        color: #b0b0b0;
    }
    .stTabs [aria-selected="true"] {
        color: #b500ff !important;
        border-bottom-color: #b500ff !important;
    }
    </style>
""", unsafe_allow_html=True)

st.title("🔍 Dashboard de Validação")

# ==========================================
# FUNÇÃO DA TELA FLUTUANTE (MODAL/DIALOG)
# ==========================================
@st.dialog("ℹ️ Como obter os Tokens e o ID da Pesquisa?")
def mostrar_tutorial_tokens():
    st.markdown("""
    **1. Token do People Hub**
    * Acesse o Django do People Hub do cliente (ex: <span style="word-break: break-all; color:#d884ff;">*https://hub.mindsight.com.br/tenant/staff/*</span>).
    * Clique em **Mindsight token extension libs**.
    * **Novo token:** Clique em *Adicionar mindsight token extension*, busque seu usuário na lupa, selecione-o e clique em *Salvar*. O token irá para o seu e-mail (válido por 14 dias).
    * **Renovar token:** Marque a caixinha do seu usuário, vá na seleção "Ação" e escolha **Recreate token**.

    **2. Token do Pesquisas**
    * Acesse o Django do Pesquisas (ex: <span style="word-break: break-all; color:#d884ff;">*https://pesquisa.mindsight.com.br/tenant/admin/*</span>).
    * Siga os mesmos passos acima para gerar ou renovar seu token.

    **3. ID da Campanha (Pesquisa)**
    * No Django do Pesquisas, vá em **Campaigns**.
    * Clique na pesquisa que deseja validar.
    * O número da pesquisa é o que está na URL após "campaign/". 
    * *Ex:* Em <span style="word-break: break-all; color:#d884ff;">*https://pesquisa.mindsight.com.br/tenant/admin/survey/campaign/2/change/*</span>, o ID é **2**.
    """, unsafe_allow_html=True)

# ==========================================
# BARRA LATERAL: LOGO E CREDENCIAIS
# ==========================================
st.sidebar.image("preview_mind.png", width='stretch')

st.sidebar.header("🔑 Credenciais de Acesso")

# Botão do tutorial fica desabilitado se estiver puxando dados (evita interrupção)
if st.sidebar.button("ℹ️ Como obter os Tokens e o ID?", width='stretch', disabled=st.session_state['is_fetching']):
    mostrar_tutorial_tokens()

st.sidebar.markdown("Preencha as informações para buscar os dados via API.")

# Usando keys para podermos limpar os campos via código
tenant = st.sidebar.text_input("Tenant do Cliente", placeholder="ex: universal", key="input_tenant")
token_hub = st.sidebar.text_input("Token do People Hub", placeholder="Insira o token do Hub", key="input_token_hub")
token_pesquisas = st.sidebar.text_input("Token do Pesquisas", placeholder="Insira o token de Pesquisas", key="input_token_pesquisas")
id_campanha = st.sidebar.text_input("ID da Campanha (Pesquisa)", placeholder="ex: 2", key="input_id_campanha")

st.sidebar.markdown("---")
st.sidebar.markdown('<div class="btn-reset">', unsafe_allow_html=True)
if st.sidebar.button("🔄 Iniciar Nova Validação (Limpar Dados)", width='stretch'):
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

# Funções auxiliares 
@st.cache_data
def load_data(file):
    if file.name.endswith('.csv'): return pd.read_csv(file)
    else: return pd.read_excel(file)

def filtrar_por_data(df, data_ref):
    if 'start_date' not in df.columns or 'end_date' not in df.columns: return df
    df = df.copy()
    df['start_date'] = pd.to_datetime(df['start_date'], format='mixed', dayfirst=True, errors='coerce')
    df['end_date'] = pd.to_datetime(df['end_date'], format='mixed', dayfirst=True, errors='coerce')
    data_ref = pd.to_datetime(data_ref)
    mask = (df['start_date'] <= data_ref) & (df['end_date'].isna() | (df['end_date'] >= data_ref))
    return df[mask]

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
        st.error("🚨 Biblioteca `mindsight_api_requests` não encontrada! Instale-a no terminal para usar a API.")
        st.stop()
    
    data_pesquisa = st.date_input("Selecione a Data da Pesquisa para Validação")
    st.markdown("### 📥 Importação de Bases via API")
    
    if st.button("🚀 Puxar Dados da Estrutura", width='stretch'):
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
        df_areas_func = st.session_state['df_areas_func']
        df_hierarquia = st.session_state['df_hierarquia']
        df_instancias = st.session_state['df_instancias']
        df_funcionarios = st.session_state['df_funcionarios']
        df_reg_func = st.session_state['df_reg_func']
        df_gestores = st.session_state['df_gestores']
        
        df_areas_func_filtrado = filtrar_por_data(df_areas_func, data_pesquisa)
        df_hierarquia_filtrado = filtrar_por_data(df_hierarquia, data_pesquisa)
        df_reg_func_filtrado = filtrar_por_data(df_reg_func, data_pesquisa)
        df_gestores_filtrado = filtrar_por_data(df_gestores, data_pesquisa)

        df_funcionarios['Nome Completo'] = df_funcionarios['first_name'].fillna('') + " " + df_funcionarios['last_name'].fillna('')
        mapa_nomes_func = dict(zip(df_funcionarios['id'], df_funcionarios['Nome Completo']))
        ativos_ids = set(df_reg_func_filtrado['person'].dropna().unique())
        mapa_datas_inicio = df_reg_func_filtrado.groupby('person')['start_date'].max().dt.strftime('%d/%m/%Y').to_dict()

        mapa_nome_para_id = dict(zip(df_instancias['name'], df_instancias['id']))
        def traduzir_area_para_id(val):
            if isinstance(val, str) and val in mapa_nome_para_id:
                return mapa_nome_para_id[val]
            return val 

        df_areas_func_filtrado['area_id'] = df_areas_func_filtrado['area'].apply(traduzir_area_para_id)

        # ==================================
        # KPIs EXECUTIVOS
        # ==================================
        st.markdown("---")
        col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
        col_kpi1.metric("👥 Total Colaboradores Ativos", len(ativos_ids))
        col_kpi2.metric("🏢 Total de Áreas Identificadas", len(df_instancias))
        col_kpi3.metric("👔 Total de Gestores Identificados", len(df_gestores_filtrado['manager'].dropna().unique()))

        # --- 1. ÁREAS ---
        st.markdown("---")
        st.subheader("1. Validação de Hierarquia de Áreas")
        
        mapa_nomes_areas = dict(zip(df_instancias['id'], df_instancias['name']))
        contagem_direta_areas = df_areas_func_filtrado.groupby('area_id')['person'].nunique().to_dict()

        G_areas = nx.DiGraph()
        all_defined_area_ids = df_instancias['id'].unique()
        G_areas.add_nodes_from(all_defined_area_ids)

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
        com_area_ids = set(df_areas_func_filtrado['person'].dropna().unique())
        sem_area_ids = ativos_ids - com_area_ids
        
        df_exibicao_area = pd.DataFrame(columns=['Nome Completo', 'email', 'Data de Início'])
        if sem_area_ids:
            st.warning(f"**{len(sem_area_ids)}** funcionário(s) com contrato ativo sem área vinculada nesta data.")
            df_func_sem_area = df_funcionarios[df_funcionarios['id'].isin(sem_area_ids)].copy()
            df_func_sem_area['Data de Início'] = df_func_sem_area['id'].map(mapa_datas_inicio)
            df_exibicao_area = df_func_sem_area[['Nome Completo', 'email', 'Data de Início']]
            
            st.dataframe(df_exibicao_area.style.apply(cor_fundo_erro, axis=1), width='stretch', hide_index=True)
        else:
            st.toast("✅ Todos os funcionários ativos possuem uma área vinculada.", icon="✅")

        # --- 2. GESTORES ---
        st.markdown("---")
        st.subheader("2. Validação de Hierarquia de Gestores")

        contagem_direta_gestores = df_gestores_filtrado.groupby('manager')['person'].nunique().to_dict()

        G_gestores = nx.DiGraph()
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
                caminho = " ➔ ".join([str(mapa_nomes_func.get(no, f"ID {no}")) for no in ciclo]) + f" ➔ {mapa_nomes_func.get(ciclo[0], f'ID {ciclo[0]}')}"
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
            opcoes_gestores = [None] + sorted(list(G_gestores.nodes()), key=lambda x: str(mapa_nomes_func.get(x, x)))
            alvo_gestor = st.selectbox(
                "🔍 Buscar Gestor/Colaborador:", 
                options=opcoes_gestores, 
                format_func=lambda x: "--- Selecione um Nome ---" if x is None else f"{mapa_nomes_func.get(x, x)} (ID: {x})"
            )

        ancestrais_gestor = nx.ancestors(G_gestores, alvo_gestor) if alvo_gestor else set()

        def render_tree_gestores(node, visited=None, level=0):
            if visited is None: visited = set()
            if node in visited: return
            visited.add(node)
            
            is_alvo = (node == alvo_gestor)
            nome = mapa_nomes_func.get(node, f"Colaborador ID {node}")
            
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
        
        com_gestor_ids = set(df_gestores_filtrado['person'].dropna().unique())
        sem_gestor_ids = ativos_ids - com_gestor_ids
        
        df_exibicao_gestor = pd.DataFrame(columns=['Nome Completo', 'email', 'Data de Início', 'É Topo de Cadeia?'])
        if sem_gestor_ids:
            st.warning(f"**{len(sem_gestor_ids)}** funcionário(s) com contrato ativo sem gestor superior nesta data.")
            
            df_func_sem_gestor = df_funcionarios[df_funcionarios['id'].isin(sem_gestor_ids)].copy()
            df_func_sem_gestor['Data de Início'] = df_func_sem_gestor['id'].map(mapa_datas_inicio)
            df_func_sem_gestor['É Topo de Cadeia?'] = df_func_sem_gestor['id'].apply(lambda x: "Sim" if x in gestores_raiz else "Não")
            df_exibicao_gestor = df_func_sem_gestor[['Nome Completo', 'email', 'Data de Início', 'É Topo de Cadeia?']]
            
            st.dataframe(df_exibicao_gestor.style.apply(cor_fundo_erro, axis=1), width='stretch', hide_index=True)
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
        col1.download_button(label="📊 Exportar para Excel (.xlsx)", data=excel_data, file_name=f"Estrutura_{data_pesquisa.strftime('%Y%m%d')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width='stretch')

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
                texto = f"- {row['Nome Completo']} | E-mail: {row['email']} | Inicio: {row['Data de Início']}"
                pdf.cell(200, 6, txt=remover_acentos(texto), ln=True)
        
        pdf.ln(10)
        
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(200, 10, txt="2. Funcionarios Ativos sem Gestor Vinculado", ln=True)
        pdf.set_font("Arial", size=10)
        if df_exibicao_gestor.empty:
            pdf.cell(200, 10, txt="Nenhuma pendencia encontrada.", ln=True)
        else:
            for _, row in df_exibicao_gestor.iterrows():
                texto = f"- {row['Nome Completo']} | E-mail: {row['email']} | Inicio: {row['Data de Início']} | Topo: {row['É Topo de Cadeia?']}"
                pdf.cell(200, 6, txt=remover_acentos(texto), ln=True)
                
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            pdf.output(tmp.name)
            with open(tmp.name, "rb") as f:
                pdf_data = f.read()
        os.remove(tmp.name) 

        col2.download_button(label="📄 Exportar Pendências para PDF (.pdf)", data=pdf_data, file_name=f"Pendencias_Estrutura_{data_pesquisa.strftime('%Y%m%d')}.pdf", mime="application/pdf", width='stretch')

        # --- 4. EXPORTAÇÃO DINÂMICA (HTML) COM PLACEHOLDER VARIÁVEL ---
        st.markdown("---")
        st.subheader("🌐 4. Exportação do Organograma Interativo")

        def render_html_page(rows_data, title, placeholder_text):
            return f"""<!DOCTYPE html>
    <html>
      <head>
        <meta charset="utf-8">
        <title>{title}</title>
        <script type="text/javascript" src="https://www.gstatic.com/charts/loader.js"></script>
        <script type="text/javascript">
          google.charts.load('current', {{packages:["orgchart"]}});
          google.charts.setOnLoadCallback(drawChart);
          
          var chart;
          var data;
          var searchMatches = [];
          var currentMatchIndex = -1;
          var lastSearchTerm = "";
          
          function drawChart() {{
            data = new google.visualization.DataTable();
            data.addColumn('string', 'Name');
            data.addColumn('string', 'Manager');
            data.addColumn('string', 'ToolTip');
            data.addRows([{rows_data}]);
            chart = new google.visualization.OrgChart(document.getElementById('chart_div'));
            chart.draw(data, {{allowHtml:true, allowCollapse:true, size:'medium'}});
            
            collapseRoots();
          }}
          
          function collapseRoots() {{
              for (var i = 0; i < data.getNumberOfRows(); i++) {{
                  var parentId = data.getValue(i, 1);
                  if (!parentId || parentId === '') {{
                      chart.collapse(i, true);
                  }}
              }}
          }}

          function expandPathTo(row) {{
              var parentId = data.getValue(row, 1);
              if (!parentId || parentId === '') return;
              for (var i = 0; i < data.getNumberOfRows(); i++) {{
                  if (data.getValue(i, 0) === parentId) {{
                      expandPathTo(i);
                      chart.collapse(i, false);
                      break;
                  }}
              }}
          }}

          function searchChart() {{
            var input = document.getElementById('searchInput').value.toLowerCase().trim();
            
            if (!input) {{ 
                chart.setSelection([]); 
                lastSearchTerm = "";
                document.getElementById('searchInfo').innerText = "";
                return; 
            }}
            
            if (input !== lastSearchTerm) {{
                lastSearchTerm = input;
                searchMatches = [];
                currentMatchIndex = 0;
                
                for (var i = 0; i < data.getNumberOfRows(); i++) {{
                  var cellHtml = data.getFormattedValue(i, 0);
                  var tempDiv = document.createElement('div');
                  tempDiv.innerHTML = cellHtml;
                  var text = tempDiv.textContent || tempDiv.innerText || "";
                  
                  if (text.toLowerCase().indexOf(input) > -1) {{
                    searchMatches.push(i);
                  }}
                }}
            }} else {{
                if (searchMatches.length > 0) {{
                    currentMatchIndex = (currentMatchIndex + 1) % searchMatches.length;
                }}
            }}
            
            if (searchMatches.length > 0) {{
                var targetRow = searchMatches[currentMatchIndex];
                
                expandPathTo(targetRow);
                chart.setSelection([{{'row': targetRow}}]);
                
                document.getElementById('searchInfo').innerText = "Resultado " + (currentMatchIndex + 1) + " de " + searchMatches.length;
                
                setTimeout(function() {{
                    var selectedNodes = document.getElementsByClassName('google-visualization-orgchart-nodesel');
                    if(selectedNodes.length > 0) {{
                        selectedNodes[0].scrollIntoView({{behavior: "smooth", block: "center", inline: "center"}});
                    }}
                }}, 200);
            }} else {{
                document.getElementById('searchInfo').innerText = "0 resultados";
                alert('Nenhum resultado encontrado para: ' + input);
            }}
          }}
          
          function resetChart() {{
              document.getElementById('searchInput').value = "";
              lastSearchTerm = "";
              searchMatches = [];
              document.getElementById('searchInfo').innerText = "";
              chart.setSelection([]);
              collapseRoots();
              window.scrollTo({{top: 0, left: 0, behavior: 'smooth'}});
          }}
        </script>
        <style>
          body {{ background-color: #09030f; font-family: sans-serif; padding: 20px; margin: 0; color: #fff; }}
          h2, p {{ text-align: center; color: #fff; }}
          
          .top-panel {{
              display: flex; flex-direction: column; align-items: center; margin-bottom: 20px;
              background-color: #120520; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(181,0,255,0.1);
          }}
          .search-controls {{ display: flex; gap: 10px; align-items: center; justify-content: center; }}
          #searchInput {{ padding: 12px; width: 350px; border: 1px solid #b500ff; border-radius: 4px; font-size: 14px; background: #000; color: white; }}
          .search-btn {{ padding: 12px 25px; background: linear-gradient(90deg, #6200ea 0%, #b500ff 100%); color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; font-weight: bold; transition: background 0.3s; }}
          .search-btn:hover {{ background-color: #1a4f58; }}
          .reset-btn {{ padding: 12px 25px; background-color: transparent; color: #b500ff; border: 1px solid #b500ff; border-radius: 4px; cursor: pointer; font-size: 14px; font-weight: bold; transition: background 0.3s; }}
          .reset-btn:hover {{ background-color: rgba(181, 0, 255, 0.1); }}
          #searchInfo {{ margin-top: 10px; font-size: 14px; font-weight: bold; color: #d884ff; height: 20px; }}
          
          .chart-container {{ width: 100%; overflow-x: auto; text-align: center; padding: 20px 0; box-sizing: border-box; }}
          .google-visualization-orgchart-table {{ margin: 0 auto !important; border-collapse: separate !important; }}
          
          .google-visualization-orgchart-node {{
             border: 2px solid #6200ea !important; border-radius: 6px !important; background-color: #1a0a2e !important;
             box-shadow: 2px 2px 8px rgba(0,0,0,0.5); padding: 12px !important; min-width: 160px; transition: all 0.3s;
          }}
          
          .google-visualization-orgchart-nodesel {{
              border: 3px solid #b500ff !important; background-color: #3b1154 !important;
              transform: scale(1.1); box-shadow: 0px 0px 20px rgba(181, 0, 255, 0.6) !important; z-index: 10;
          }}
          
          .nome-node {{ font-weight: bold; color: #d884ff; font-size: 13px; margin-bottom: 6px; text-transform: uppercase; }}
          .desc-node {{ color: #ccc; font-size: 11px; margin-bottom: 4px; }}
          .email-node {{ color: #aaa; font-size: 10px; font-style: italic; }}
        </style>
      </head>
      <body>
        <h2>{title}</h2>
        
        <div class="top-panel">
            <div class="search-controls">
                <input type="text" id="searchInput" placeholder="{placeholder_text}" onkeyup="if(event.key === 'Enter') searchChart()">
                <button class="search-btn" onclick="searchChart()">🔍 Buscar</button>
                <button class="reset-btn" onclick="resetChart()">🔄 Resetar Organograma</button>
            </div>
            <div id="searchInfo"></div>
        </div>
        
        <div class="chart-container">
            <div id="chart_div"></div>
        </div>
        
      </body>
    </html>"""

        def exportar_orgchart_areas():
            rows = []
            visited = set()
            tem_multiplas_raizes = len(todas_raizes_areas) > 1
            if tem_multiplas_raizes: rows.append(f"[{{v:'Raiz_Global', f:'<div class=\"nome-node\">🏢 TODAS AS ÁREAS</div>'}}, '', '']")
            def traverse(node, parent):
                if node in visited: return
                visited.add(node)
                nome = safe_html(mapa_nomes_areas.get(node, f"ID {node}"))
                qtd = calcular_total_areas_seguro(node)
                html_f = f"<div class=\"nome-node\">{nome}</div><div class=\"desc-node\">Total: {qtd} func.</div>"
                parent_id = str(parent) if parent else ('Raiz_Global' if tem_multiplas_raizes else '')
                rows.append(f"[{{v:'{node}', f:'{html_f}'}}, '{parent_id}', '']")
                
                children = list(G_areas.successors(node))
                children.sort(key=lambda x: calcular_total_areas_seguro(x), reverse=True)
                for child in children:
                    if child not in visited: traverse(child, node)
            for raiz in todas_raizes_areas: traverse(raiz, None)
            return ",\n".join(rows)

        def exportar_orgchart_gestores():
            rows = []
            visited = set()
            tem_multiplas_raizes = len(todas_raizes_gestores) > 1
            if tem_multiplas_raizes: rows.append(f"[{{v:'Raiz_Global', f:'<div class=\"nome-node\">DIRETORIA GERAL</div>'}}, '', '']")
            def traverse(node, parent):
                if node in visited: return
                visited.add(node)
                nome = safe_html(mapa_nomes_func.get(node, f"ID {node}"))
                qtd = calcular_total_gestores_seguro(node)
                email = ""
                df_f = df_funcionarios[df_funcionarios['id'] == node]
                if not df_f.empty and 'email' in df_f.columns:
                    val = df_f['email'].values[0]
                    if pd.notna(val): email = safe_html(val)
                html_f = f"<div class=\"nome-node\">{nome}</div><div class=\"desc-node\">{qtd} liderados</div><div class=\"email-node\">{email}</div>"
                parent_id = str(parent) if parent else ('Raiz_Global' if tem_multiplas_raizes else '')
                rows.append(f"[{{v:'{node}', f:'{html_f}'}}, '{parent_id}', '']")
                
                children = list(G_gestores.successors(node))
                children.sort(key=lambda x: calcular_total_gestores_seguro(x), reverse=True)
                for child in children:
                    if child not in visited: traverse(child, node)
            for raiz in todas_raizes_gestores: traverse(raiz, None)
            return ",\n".join(rows)

        col3, col4 = st.columns(2)
        
        html_areas = render_html_page(
            exportar_orgchart_areas(), 
            f"Organograma de Áreas - {data_pesquisa.strftime('%d/%m/%Y')}", 
            placeholder_text="Busque por uma área (Ex: Emergencial)..."
        )
        html_gestores = render_html_page(
            exportar_orgchart_gestores(), 
            f"Organograma de Gestores - {data_pesquisa.strftime('%d/%m/%Y')}", 
            placeholder_text="Busque por um gestor..."
        )
        
        col3.download_button(
            label="🌍 Baixar Arquivo Dinâmico de Áreas (.html)",
            data=html_areas,
            file_name=f"OrgChart_Areas_{data_pesquisa.strftime('%Y%m%d')}.html",
            mime="text/html",
            width='stretch'
        )
        col4.download_button(
            label="🌍 Baixar Arquivo Dinâmico de Gestores (.html)",
            data=html_gestores,
            file_name=f"OrgChart_Gestores_{data_pesquisa.strftime('%Y%m%d')}.html",
            mime="text/html",
            width='stretch'
        )

# ==========================================
# ABA 2: PESQUISA DE CLIMA
# ==========================================
with aba_clima:
    st.header("🌤️ Validação da Estrutura da Pesquisa de Clima")
    
    if not API_INSTALADA:
        st.error("🚨 Biblioteca `mindsight_api_requests` não encontrada! Instale-a no terminal para usar a API.")
        st.stop()

    st.markdown("### 📥 Importação de Bases da Pesquisa")
    
    if st.button("🚀 Puxar Dados da Pesquisa de Clima", width='stretch'):
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
                progresso_clima.progress(33)
                logs_clima += "✅ Campanhas baixadas com sucesso!<br>"
                hist_clima.markdown(logs_clima, unsafe_allow_html=True)

                with st.spinner("⏳ Baixando **Perguntas (Choices)**..."):
                    st.session_state['df_pesquisa_choice'] = get_pesquisa_choice_question_api(tenant, token_pesquisas)
                progresso_clima.progress(66)
                logs_clima += "✅ Perguntas baixadas com sucesso!<br>"
                hist_clima.markdown(logs_clima, unsafe_allow_html=True)

                with st.spinner("⏳ Baixando **Contatos da Campanha**..."):
                    st.session_state['df_pesquisa_contatos'] = get_pesquisa_contact_api(tenant, token_pesquisas, id_camp_int)
                progresso_clima.progress(100)
                logs_clima += "✅ Contatos baixados com sucesso!<br>"
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
        df_camp = st.session_state['df_pesquisa_camp']
        df_choice = st.session_state['df_pesquisa_choice']
        df_contatos = st.session_state['df_pesquisa_contatos']
        df_func = st.session_state['df_funcionarios']

        try:
            pesquisa_atual = df_camp.loc[df_camp['id'] == int(id_campanha)] if not df_camp.empty else pd.DataFrame()
            nome_pesquisa = pesquisa_atual['name'].values[0] if not pesquisa_atual.empty else "Nome Indisponível"
        except:
            nome_pesquisa = "Nome Indisponível"

        if 'email' not in df_contatos.columns: df_contatos['email'] = ''
        if 'first name' not in df_contatos.columns: df_contatos['first name'] = ''
        if 'last name' not in df_contatos.columns: df_contatos['last name'] = ''
        if 'email' not in df_func.columns: df_func['email'] = ''

        df_contatos_validos = df_contatos[~df_contatos['email'].astype(str).str.contains('@mindsight', case=False, na=False)].copy()
        
        st.markdown("---")
        
        # --- KPIs CLIMA ---
        col_kpi1_c, col_kpi2_c = st.columns(2)
        
        # Bloco HTML personalizado para o Nome da Pesquisa não ser cortado
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

        df_func['email_clean'] = df_func['email'].astype(str).str.lower().str.strip()
        df_func['nome_clean'] = df_func['Nome Completo'].astype(str).str.lower().str.strip()
        
        df_contatos_validos['email_clean'] = df_contatos_validos['email'].astype(str).str.lower().str.strip()
        df_contatos_validos['Nome Completo'] = df_contatos_validos['first name'].astype(str).str.strip() + " " + df_contatos_validos['last name'].astype(str).str.strip()
        df_contatos_validos['nome_clean'] = df_contatos_validos['Nome Completo'].str.lower().str.strip()

        dict_email_hub = df_func.drop_duplicates('email_clean').set_index('email_clean').to_dict('index')
        dict_nome_hub = df_func.drop_duplicates('nome_clean').set_index('nome_clean').to_dict('index')
        
        mapa_instancias = {}
        for _, row in st.session_state['df_instancias'].iterrows():
            id_str = clean_val(row.get('id'))
            name_str = clean_val(row.get('name'))
            if id_str: mapa_instancias[id_str] = name_str
            if name_str: mapa_instancias[name_str] = name_str

        df_areas_f = filtrar_por_data(st.session_state['df_areas_func'], data_pesquisa)
        hub_person_area = {}
        for _, row in df_areas_f.iterrows():
            p_str = clean_val(row.get('person'))
            a_str = clean_val(row.get('area'))
            hub_person_area[p_str] = mapa_instancias.get(a_str, a_str) 

        mapa_nomes_func_global = {}
        for _, row in df_func.iterrows():
            id_str = clean_val(row.get('id'))
            mapa_nomes_func_global[id_str] = row.get('Nome Completo', '')

        df_gestores_f = filtrar_por_data(st.session_state['df_gestores'], data_pesquisa)
        hub_person_manager = {}
        for _, row in df_gestores_f.iterrows():
            p_str = clean_val(row.get('person'))
            m_str = clean_val(row.get('manager'))
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
                hub_id = clean_val(dict_email_hub[e_clean].get('id'))
                area_nome = hub_person_area.get(hub_id, "Sem Área")
                manager_nome = hub_person_manager.get(hub_id, "Sem Gestor")
                
                encontrados_email.append({
                    'Nome completo': nome_original,
                    'Email': email_original,
                    'Área': area_nome,
                    'Gestor': manager_nome
                })
            elif n_clean and n_clean in dict_nome_hub:
                email_hub = dict_nome_hub[n_clean].get('email', '')
                hub_id = clean_val(dict_nome_hub[n_clean].get('id'))
                area_nome = hub_person_area.get(hub_id, "Sem Área")
                manager_nome = hub_person_manager.get(hub_id, "Sem Gestor")
                
                encontrados_nome.append({
                    'Nome completo': nome_original,
                    'Email no Pesquisas': email_original,
                    'Email no People Hub': email_hub,
                    'Área': area_nome,
                    'Gestor': manager_nome
                })
            else:
                nao_encontrados.append({
                    'Nome completo': nome_original,
                    'Email no Pesquisas': email_original
                })

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
            if 'não ' in texto or 'nao ' in texto: 
                score -= 1.5 
            return score

        qtd_erros_perguntas = 0
        lista_problemas_perguntas = []

        for _, row in df_choice.iterrows():
            titulo = row.get('title', 'Pergunta Desconhecida')
            choices_str = row.get('question_object.choices', '[]')
            
            try:
                if isinstance(choices_str, str): choices = ast.literal_eval(choices_str)
                else: choices = choices_str
            except:
                choices = []

            if not isinstance(choices, list) or len(choices) == 0:
                continue
                
            issues = []
            valores_vistos = {}
            descricoes_vistas = {}
            choices_parsed = []

            for c in choices:
                val_str = str(c.get('value', ''))
                desc = str(c.get('description', '')).strip()
                
                try: val_num = float(val_str)
                except: val_num = None
                
                if val_num is not None:
                    choices_parsed.append({'val': val_num, 'desc': desc})
                    if val_num < 0:
                        issues.append(f"Valor negativo encontrado: {val_num} na opção '{desc}'")

                if val_str in valores_vistos and valores_vistos[val_str] != desc:
                    issues.append(f"Valor {val_str} está sendo usado para descrições diferentes: '{desc}' e '{valores_vistos[val_str]}'")
                elif val_str in valores_vistos and valores_vistos[val_str] == desc:
                    issues.append(f"Alternativa duplicada exata: '{desc}' com valor {val_str}")

                if desc in descricoes_vistas and descricoes_vistas[desc] != val_str:
                    issues.append(f"A descrição '{desc}' possui valores numéricos diferentes associados a ela: {val_str} e {descricoes_vistas[desc]}")

                valores_vistos[val_str] = desc
                descricoes_vistas[desc] = val_str

            if len(choices_parsed) > 1:
                choices_parsed.sort(key=lambda x: x['val'])
                primeira_opcao = choices_parsed[0]['desc']
                ultima_opcao = choices_parsed[-1]['desc']
                
                score_primeira = score_sentimento(primeira_opcao)
                score_ultima = score_sentimento(ultima_opcao)
                
                if score_primeira > score_ultima and (score_primeira > 0 or score_ultima < 0):
                    issues.append(f"Possível Inversão de Escala! O menor valor ({choices_parsed[0]['val']}) é '{primeira_opcao}' e o maior valor ({choices_parsed[-1]['val']}) é '{ultima_opcao}'.")

            if issues:
                qtd_erros_perguntas += 1
                for issue in issues:
                    lista_problemas_perguntas.append({'Nome da Pergunta': titulo, 'Problema': issue})
                    
                with st.expander(f"❌ Problemas encontrados em: {titulo}", expanded=False):
                    for issue in issues:
                        st.markdown(f"- {issue}")

        if qtd_erros_perguntas == 0 and len(df_choice) > 0:
            st.success("✅ Nenhuma anomalia de valores, duplicatas ou inversão de escala foi encontrada nas perguntas analisadas!")

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
            width='stretch'
        )
