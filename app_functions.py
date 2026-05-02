import pandas as pd
import requests
import io
from typing import Optional

# ==========================================
# 🛠️ FUNÇÕES AUXILIARES E MOTOR DA API
# ==========================================
def getFirstName(name: str):
    if pd.isna(name) or not isinstance(name, str): return ""
    return name.strip().split()[0]

def getLastName(name: str):
    if pd.isna(name) or not isinstance(name, str): return ""
    parts = name.strip().split()
    return " ".join(parts[1:]) if len(parts) > 1 else ""

def get_ID_from_url(url):
    if pd.isna(url) or not isinstance(url, str): return url
    parts = [p for p in str(url).split('/') if p]
    if parts and parts[-1].isdigit():
        return int(parts[-1])
    return url

def get_dataframe_from_api(
    system: str, 
    tenant: str, 
    endpoint: str, 
    token: str, 
    page_size: Optional[int] = None, 
    **kwargs
) -> pd.DataFrame:
    """
    Faz a requisição para a API da Mindsight. Se retornar erro, lança uma exceção
    para que o app principal (app.py) trave e exiba o erro na tela.
    """
    # Remove barras duplicadas caso a rota venha com barra no final
    endpoint = endpoint.strip('/')
    base_url = f"https://{system}.mindsight.com.br/{tenant}/api/v1/{endpoint}/"

    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": "application/json"
    }
    
    params = {}
    if page_size:
        params['page_size'] = page_size
        
    all_data = []
    url = base_url
    
    while url:
        response = requests.get(url, headers=headers, params=params if url == base_url else None)
        
        # Se a API recusar a conexão, LANÇA O ERRO direto pro app.py (sem atualizar a tela!)
        if response.status_code != 200:
            raise Exception(f"Erro HTTP {response.status_code} ({response.reason}) na URL:\n{url}\n\nResposta da API: {response.text[:300]}")
            
        # Tentativa 1: Formato JSON Padrão
        try:
            data = response.json()
        except Exception:
            # Tentativa 2: Formato de Arquivo (CSV ou Excel) comum em rotas de 'export'
            content_type = response.headers.get('Content-Type', '').lower()
            try:
                if 'excel' in content_type or 'spreadsheet' in content_type:
                    return pd.read_excel(io.BytesIO(response.content))
                else:
                    # Se falhar o JSON, tenta ler como CSV nativo usando delimitador automático
                    return pd.read_csv(io.StringIO(response.text), sep=None, engine='python')
            except Exception as e:
                raise Exception(f"A API retornou sucesso, mas o formato é desconhecido e não pôde ser lido. Tipo: {content_type}. Erro: {e}")
        
        # Processamento de páginas JSON
        if isinstance(data, dict) and 'results' in data:
            all_data.extend(data['results'])
            url = data.get('next') 
        elif isinstance(data, list):
            all_data.extend(data)
            url = None
        else:
            all_data.append(data)
            url = None
                
    if not all_data:
        return pd.DataFrame()
        
    return pd.json_normalize(all_data)


# ==========================================
# 🏢 FUNÇÕES DO PEOPLE HUB
# ==========================================
def get_hub_employees_api(tenant: str, token: str, page_size: Optional[int] = None, max_workers: Optional[int] = None, parallel: bool = True, ignore_page_size_limits: bool = False) -> pd.DataFrame:
    standard_columns = ['id','name','user','email','gender','birth_date','age','humanized_company_time','position','manager','variable_salary',
                        'photo','alert_set','area','work_type','work_city','is_manager','start_date','date_of_hire','cpf','salary']
    df_employees_api = get_dataframe_from_api('hub', tenant, 'people/get_all_employees', token, page_size)
    
    if df_employees_api.empty:
        return pd.DataFrame(columns=standard_columns)
        
    if 'cpf' not in df_employees_api.columns:
        df_employees_api['cpf'] = None
    if 'name' in df_employees_api.columns:
        df_employees_api['first_name'] = df_employees_api['name'].apply(getFirstName)
        df_employees_api['last_name'] = df_employees_api['name'].apply(getLastName)
    if 'user' in df_employees_api.columns:
        df_employees_api['user'] = df_employees_api['user'].apply(get_ID_from_url)
        
    return df_employees_api

def get_hub_contract_types_api(tenant: str, token: str, page_size: Optional[int] = None, **kwargs) -> pd.DataFrame:
    df = get_dataframe_from_api('hub', tenant, 'contract_types', token, page_size)
    if df.empty: return pd.DataFrame(columns=['id', 'description', 'key'])
    return df

def get_hub_companies_api(tenant: str, token: str, page_size: Optional[int] = None, max_workers: Optional[int] = None, parallel: bool = True, ignore_page_size_limits: bool = False) -> pd.DataFrame:
    standard_columns = ['uuid','registration_code','start_date','end_date','entrance_type','termination_type',
                        'person','corporation','name','branch_corporation','unit_name','id','contract_type']
    df_companies_api = get_dataframe_from_api('hub', tenant, 'companies', token, page_size)
    
    if df_companies_api.empty:
        return pd.DataFrame(columns=standard_columns)
        
    if 'api_url' in df_companies_api.columns:
        df_companies_api['id'] = df_companies_api['api_url'].apply(get_ID_from_url)
    if 'person' in df_companies_api.columns:
        df_companies_api['person'] = df_companies_api['person'].apply(get_ID_from_url)
        
    df_hub_contract_types_api = get_hub_contract_types_api(tenant, token, page_size)
    if not df_hub_contract_types_api.empty and 'description' in df_hub_contract_types_api.columns:
        mapping = dict(zip(df_hub_contract_types_api['description'], df_hub_contract_types_api['key']))
        if 'contract' in df_companies_api.columns:
            df_companies_api['contract_type'] = df_companies_api['contract'].map(mapping)
            
    return df_companies_api

def get_hub_managers_api(tenant: str, token: str, page_size: Optional[int] = None, max_workers: Optional[int] = None, parallel: bool = True, ignore_page_size_limits: bool = False) -> pd.DataFrame:
    standard_columns = ['id','api_url','person','manager','start_date','end_date']
    df_managers_api = get_dataframe_from_api('hub', tenant, 'managers', token, page_size)
    
    if df_managers_api.empty:
        return pd.DataFrame(columns=standard_columns)
        
    if 'api_url' in df_managers_api.columns:
        df_managers_api['id'] = df_managers_api['api_url'].apply(get_ID_from_url)
    if 'person' in df_managers_api.columns:
        df_managers_api['person'] = df_managers_api['person'].apply(get_ID_from_url)
    if 'manager.id' in df_managers_api.columns:
        df_managers_api['manager'] = df_managers_api['manager.id']
        
    return df_managers_api

def get_hub_area_instances_api(tenant: str, token: str, page_size: Optional[int] = None, max_workers: Optional[int] = None, parallel: bool = True, ignore_page_size_limits: bool = False) -> pd.DataFrame:
    standard_columns = ['id', 'code', 'name', 'uuid']
    df_area_instances_api = get_dataframe_from_api('hub', tenant, 'area_instances', token, page_size)
    
    if df_area_instances_api.empty:
        return pd.DataFrame(columns=standard_columns)
        
    if 'code' in df_area_instances_api.columns:
        df_area_instances_api['code'] = df_area_instances_api['code'].astype(str)
        
    return df_area_instances_api

def get_hub_area_hierarchy_api(tenant: str, token: str, page_size: Optional[int] = None, max_workers: Optional[int] = None, parallel: bool = True, ignore_page_size_limits: bool = False) -> pd.DataFrame:
    standard_columns = ['start_date','end_date','parent','area','id']
    df_area_hierarchy_api = get_dataframe_from_api('hub', tenant, 'area_hierarchy', token, page_size)
    
    if df_area_hierarchy_api.empty:
        return pd.DataFrame(columns=standard_columns)
        
    df_area_hierarchy_api['id'] = df_area_hierarchy_api['api_url'].apply(get_ID_from_url) if 'api_url' in df_area_hierarchy_api.columns else df_area_hierarchy_api.get('id')
    df_area_hierarchy_api['area'] = df_area_hierarchy_api['area'].apply(get_ID_from_url) if 'area' in df_area_hierarchy_api.columns else None
    df_area_hierarchy_api['parent'] = df_area_hierarchy_api['parent'].apply(get_ID_from_url) if 'parent' in df_area_hierarchy_api.columns else None
    
    df_hub_area_instances_api = get_hub_area_instances_api(tenant, token, page_size)
    if not df_hub_area_instances_api.empty:
        if 'area' in df_area_hierarchy_api.columns and 'id' in df_hub_area_instances_api.columns:
            df_area_hierarchy_api = df_area_hierarchy_api.merge(df_hub_area_instances_api[['name', 'id', 'code']], how='left', left_on='area', right_on='id', suffixes=('', '_area'))
        if 'parent' in df_area_hierarchy_api.columns and 'id' in df_hub_area_instances_api.columns:
            df_area_hierarchy_api = df_area_hierarchy_api.merge(df_hub_area_instances_api[['name', 'id', 'code']], how='left', left_on='parent', right_on='id', suffixes=('', '_parent'))
            
    return df_area_hierarchy_api

def get_hub_areas_api(tenant: str, token: str, page_size: Optional[int] = None, max_workers: Optional[int] = None, parallel: bool = True, ignore_page_size_limits: bool = False) -> pd.DataFrame:
    standard_columns = ['area','is_primary','start_date','end_date','uuid','person','id','name','id_area','code']
    df_areas_api = get_dataframe_from_api('hub', tenant, 'areas', token, page_size)
    
    if df_areas_api.empty:
        return pd.DataFrame(columns=standard_columns)
        
    df_areas_api['id'] = df_areas_api['api_url'].apply(get_ID_from_url) if 'api_url' in df_areas_api.columns else df_areas_api.get('id')
    df_areas_api['person'] = df_areas_api['person'].apply(get_ID_from_url) if 'person' in df_areas_api.columns else None
    
    df_hub_area_instances_api = get_hub_area_instances_api(tenant, token)
    if not df_hub_area_instances_api.empty:
        if 'area' in df_areas_api.columns and 'name' in df_hub_area_instances_api.columns:
            df_areas_api = df_areas_api.merge(df_hub_area_instances_api[['name', 'id', 'code']], how='left', left_on='area', right_on='name', suffixes=('', '_area'))
            
    return df_areas_api

# ==========================================
# 🌤️ FUNÇÕES DE PESQUISA DE CLIMA
# ==========================================
def get_pesquisa_campaigns_api(tenant: str, token: str, page_size: Optional[int] = None, max_workers: Optional[int] = None, parallel: bool = True, ignore_page_size_limits: bool = False) -> pd.DataFrame:
    standard_columns = ['id', 'name', 'description', 'start_date', 'end_date', 'status', 'template', 'survey.id', 'survey.title']
    df_campaigns_api = get_dataframe_from_api('pesquisa', tenant, 'campaigns', token, page_size)
    if df_campaigns_api.empty:
        return pd.DataFrame(columns=standard_columns)
    return df_campaigns_api

def get_pesquisa_choice_question_api(tenant: str, token: str, page_size: Optional[int] = None, max_workers: Optional[int] = None, parallel: bool = True, ignore_page_size_limits: bool = False) -> pd.DataFrame:
    standard_columns = ['id', 'title', 'description', 'image', 'type', 'category', 'created_date', 'modified_date', 'question_object.choices']
    df_choice_question_api = get_dataframe_from_api('pesquisa', tenant, 'choice_question_admin', token, page_size)
    if df_choice_question_api.empty:
        return pd.DataFrame(columns=standard_columns)
    return df_choice_question_api

def get_pesquisa_contact_api(tenant: str, token: str, campaign_id: int, page_size: Optional[int] = None, max_workers: Optional[int] = None, parallel: bool = True, ignore_page_size_limits: bool = False) -> pd.DataFrame:
    standard_columns = ['id', 'first name', 'last name', 'email', 'phone', 'campaign', 'survey_status', 'notification status', 'language', 'first_access', 'created_date', 'modified_date', 'key', 'survey link']
    df_contact_api = get_dataframe_from_api('pesquisa', tenant, f'campaigns/{campaign_id}/export_campaign_contacts', token, page_size)
    if df_contact_api.empty:
        return pd.DataFrame(columns=standard_columns)
    return df_contact_api

def get_pesquisa_survey_api(
    tenant: str,
    token: str,
    page_size: Optional[int] = None,
    max_workers: Optional[int] = None,
    parallel: bool = True,
    ignore_page_size_limits: bool = False
) -> pd.DataFrame:
    """
    Obtém informações das pesquisas via API e explode as perguntas para formato plano.
    """
    standard_columns = ['id', 'title', 'description', 'questions.title', 'questions.type']
    
    # Busca os dados do endpoint survey_admin
    df_survey_api = get_dataframe_from_api('pesquisa', tenant, 'survey_admin', token, page_size)
    
    if df_survey_api.empty:
        return pd.DataFrame(columns=standard_columns)
    
    # Processamento para extrair as perguntas aninhadas
    # Explodimos a coluna 'questions' que contém a lista de dicts
    df_survey_api = df_survey_api.explode('questions')
    
    # Resetamos o index para evitar problemas no normalize
    df_survey_api = df_survey_api.reset_index(drop=True)
    
    # Normalizamos o campo questions (que agora é um dict por linha)
    # Usamos o método to_json/loads para garantir que o normalize trate corretamente o objeto
    json_survey_api = df_survey_api.to_json(orient='records')
    df_survey_api = pd.json_normalize(json.loads(json_survey_api))
    
    return df_survey_api
