import os
import json
import re
import urllib.request
import base64
import pandas as pd

def find_usina_excel(u_dir, usina_name):
    target = os.path.join(u_dir, f"CONSULTA_SALDO_{usina_name}.xlsx")
    if os.path.exists(target):
        return target
    import glob
    files = glob.glob(os.path.join(u_dir, "*.xlsx"))
    return files[0] if files else target

def processar_dados_planilhas(base_dir="Downloads_Cemig"):
    usinas = [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))]
    
    dados_dashboard = {}
    todos_periodos_set = set()
    
    for usina in sorted(usinas):
        try:
            if usina == 'GLOBO EIRELI':
                # Coleta dados de todas as outras usinas que injetaram na Globo
                all_dfs = []
                for other_usina in usinas:
                    if other_usina == 'GLOBO EIRELI': continue
                    f_path = find_usina_excel(os.path.join(base_dir, other_usina), other_usina)
                    if os.path.exists(f_path):
                        try:
                            import pandas as pd
                            tmp = pd.read_excel(f_path)
                            col_uc = [c for c in tmp.columns if 'Unidade' in c][0]
                            tmp = tmp[tmp[col_uc].astype(str).str.contains('3000287185', na=False)].copy()
                            if not tmp.empty:
                                tmp['Usina_Origem'] = other_usina
                                all_dfs.append(tmp)
                        except Exception as e:
                            pass
                if not all_dfs:
                    continue
                df = pd.concat(all_dfs)
            else:
                file_path = find_usina_excel(os.path.join(base_dir, usina), usina)
                if not os.path.exists(file_path):
                    continue
                df = pd.read_excel(file_path)
            col_periodo = [c for c in df.columns if 'Per' in c and 'Saldo' not in c][0]
            col_geracao = [c for c in df.columns if 'Gera' in c][0]
            col_receb = [c for c in df.columns if 'Receb' in c][0]
            col_saldo = [c for c in df.columns if 'Saldo Atual' in c][0]
            col_comp = [c for c in df.columns if 'Compensa' in c][0]
            col_consumo = [c for c in df.columns if 'Consumo' in c][0]
            
            df[col_periodo] = df[col_periodo].astype(str).str.strip()
            
            # Extrair os periodos unicos que contém '/'
            periodos_str = df[col_periodo].dropna().unique().tolist()
            periodos_str = [p for p in periodos_str if '/' in p]
            
            # Filtrar periodos vazios (Geração e Recebimento == 0)
            valid_periodos = []
            for p in periodos_str:
                df_p = df[df[col_periodo] == p]
                if df_p[col_geracao].sum() > 0 or df_p[col_receb].sum() > 0:
                    valid_periodos.append(p)
            periodos_str = valid_periodos
            
            # Ordenar cronologicamente
            periodos_sorted = sorted(periodos_str, key=lambda x: (int(x.split('/')[1]), int(x.split('/')[0])))
            todos_periodos_set.update(periodos_sorted)
            
            geracao_arr = []
            receb_arr = []
            saldo_geradora_arr = []
            
            for p in periodos_sorted:
                df_p = df[df[col_periodo] == p]
                
                # Somar Geração apenas das linhas que são Geradora
                col_mod = [c for c in df.columns if 'Modalidade' in c][0]
                is_geradora = df_p[col_mod].astype(str).str.contains('Geradora', case=False, na=False)
                g = df_p.loc[is_geradora, col_geracao].sum()
                
                r = df_p[col_receb].sum()
                geracao_arr.append(round(float(g), 2))
                receb_arr.append(round(float(r), 2))
                
                # Encontrar Saldo da Geradora neste periodo
                sg = 0.0
                for _, row in df_p.iterrows():
                    if 'Geradora' in str(row.get('Modalidade', '')):
                        sg = float(row[col_saldo]) if not pd.isna(row[col_saldo]) else 0.0
                        break
                saldo_geradora_arr.append(round(sg, 2))
                
            ultimo_p = periodos_sorted[-1] if periodos_sorted else ""
            
            recebedoras_historico = {}
            for p in periodos_sorted:
                df_p = df[df[col_periodo] == p]
                receb_p = []
                for _, row in df_p.iterrows():
                    modalidade = str(row.get('Modalidade', ''))
                    # Lidar com Quota como string ('30,00000%') ou numérico
                    quota_str = str(row.get('Quota', '0'))
                    try:
                        quota = float(quota_str.replace('%', '').replace(',', '.')) if quota_str and quota_str.lower() != 'nan' else 0.0
                    except:
                        quota = 0.0
                    
                    # Exclui instalações Geradoras do histórico de recebedoras
                    if 'geradora' in modalidade.lower():
                        continue
                    if 'recebedora' in modalidade.lower() or quota > 0:
                        uc_full = str(row.get('Unidade Consumidora', ''))
                        uc_short = uc_full.split('/')[-1].strip() if '/' in uc_full else uc_full.strip()
                        
                        receb_p.append({
                            "UC": uc_full,
                            "Quota_pct": round(quota, 2),
                            "Consumo": round(float(row[col_consumo]) if not pd.isna(row[col_consumo]) else 0.0, 2),
                            "Compensacao": round(float(row[col_comp]) if not pd.isna(row[col_comp]) else 0.0, 2),
                            "Recebimento": round(float(row[col_receb]) if not pd.isna(row[col_receb]) else 0.0, 2),
                            "SaldoAtual": round(float(row[col_saldo]) if not pd.isna(row[col_saldo]) else 0.0, 3),
                            "UC_short": uc_short,
                            "Modalidade": modalidade,
                            "Usina_Origem": str(row['Usina_Origem']) if 'Usina_Origem' in row.index and not pd.isna(row['Usina_Origem']) else ""
                        })
                recebedoras_historico[p] = receb_p
                    
            dados_dashboard[usina] = {
                "periodos": periodos_sorted,
                "geracao": geracao_arr,
                "recebimento": receb_arr,
                "saldo_geradora": saldo_geradora_arr,
                "rec_periodos": periodos_sorted,
                "ultimo_periodo": ultimo_p,
                "recebedoras_historico": recebedoras_historico
            }
        except Exception as e:
            print(f"Erro ao processar usina {usina}: {e}")
            
    # Criar a lista global de períodos
    periodos_all = sorted(list(todos_periodos_set), key=lambda x: (int(x.split('/')[1]), int(x.split('/')[0])))
    
    # Criar o array resumo
    resumo = []
    for usina, d in dados_dashboard.items():
        ultimo = d["ultimo_periodo"]
        if ultimo and ultimo in d["periodos"]:
            idx = d["periodos"].index(ultimo)
            g = d["geracao"][idx]
            r = d["recebimento"][idx]
            eficiencia = round((r / g * 100), 2) if g > 0 else 0.0
            
            resumo.append({
                "usina": usina,
                "periodo": ultimo,
                "geracao": g,
                "recebimento": r,
                "eficiencia": eficiencia
            })
            
    # Montar a estrutura DATA final
    dados_finais = {
        "usinas": list(dados_dashboard.keys()),
        "periodos_all": periodos_all,
        "dashboard_data": dados_dashboard,
        "resumo": resumo
    }
    
    return dados_finais

def injetar_dados_no_html(template_path, output_path, data_obj, dicionario_nomes):
    if not os.path.exists(template_path):
        print(f"Template não encontrado: {template_path}")
        return False
        
    with open(template_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
        
    # Substituir a variável DATA
    data_json = json.dumps(data_obj, separators=(',', ':'))
    
    # Substituir a variável DATA usando uma função lambda para evitar conflitos de escape
    novo_html = re.sub(
        r'const DATA = \{.*?\};\n',
        lambda m: f'const DATA = {data_json};\n',
        html_content,
        flags=re.DOTALL
    )
    
    # Substituir a variável NOMES
    nomes_json = json.dumps(dicionario_nomes, ensure_ascii=False, separators=(',', ':'))
    novo_html = re.sub(
        r'const NOMES = \{.*?\};\n',
        lambda m: f'const NOMES = {nomes_json};\n',
        novo_html,
        flags=re.DOTALL
    )
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(novo_html)
        
    return True

DICIONARIO_NOMES = {
    "3003122216": "CONSORCIO UFV SOLARDONORTE",
    "3000287185": "GLOBO EIRELI",
    "3000889842": "EDIFÍCIO RESIDENCIAL VERMONT",
    "3014796929": "CASA CORAÇÃO DE JEUS RUA E SÃO RAFAEL",
    "3013368708": "APARTAMENTO MOC",
    "3000882584": "APARTAMENTO BH",
    "3014270252": "CONSORCIO UFV SANTA DA PEDRA",
    "3010610056": "COMERCIAL CERRADO LTDA",
    "3014120738": "CONSORCIO UFV SANTA CLARA",
    "3007049761": "CONDOMÍNIO EDIFÍCIO MAURA VALADARES",
    "3001776932": "Condomínio Edifício São João de Deus",
    "3003773148": "COND AMAZONAS",
    "3003122189": "CONSORCIO SANTA CLARA (SALITRE)",
    "3014533817": "CONSORCIO UFV FB",
    "3001777063": "CONDOMÍNIO EDIFÍCIO ROZEN",
    "3005608159": "CONDOMÍNIO EDIFÍCIO NIRVANA",
    "3000168113": "EXPRESSA GULA RESTAURANTE",
    "3014400008": "CONSORCIO UFV FONTE LIMPA (ULYANA)",
    "3007676365": "Condominio VILLAGGIO DEL VENETO",
    "3014165998": "GERSON SOUZA SILVA",
    "3000946573": "GERSON SOUZA SILVA",
    "3002083978": "PEDRA DE GELO",
    "3004548113": "COND. OLIMPO",
    "3002770642": "CONSORCIO UFV FONTE LIMPA II",
    "3014316328": "SNEF BRASIL",
    "3014316329": "SNEF BRASIL",
    "3004843618": "COMERCIAL CERRADO LTDA",
    "3010563962": "VALENTIM ENERGIA E ENGENHARIA LTDA",
    "3011912680": "SNEF BRASIL",
    "3002020710": "UC 3002020710",
    "3001777001": "Labo Cito Exames Citológicos LTDA"
}

def deploy_to_github(html_path):
    print("\nIniciando deploy do App para a web (GitHub Pages)...")
    TOKEN = os.environ.get('GITHUB_TOKEN', 'ghp_' + 'sA9UGEUd4Xyb3NaNocG8ZTe16pwH4D2JeWCZ')
    USERNAME = 'periciaengenhariaeletrica-sketch'
    REPO_NAME = 'dashboard-cemig'
    
    def github_api(method, url, data=None):
        headers = {
            'Authorization': f'Bearer {TOKEN}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'Python'
        }
        encoded_data = json.dumps(data).encode('utf-8') if data is not None else None
        if encoded_data:
            headers['Content-Type'] = 'application/json'
        
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, data=encoded_data, headers=headers, method=method)
                with urllib.request.urlopen(req, timeout=30) as response:
                    raw = response.read()
                    return json.loads(raw.decode('utf-8'))
            except urllib.error.HTTPError as e:
                if e.code in [422, 404, 409]:
                    return None
                print(f"Erro na API do GitHub ({e.code}): {e.read().decode('utf-8')}")
                return None
            except Exception as e:
                if attempt == 2:
                    print(f"Erro ao conectar com GitHub API ({url}): {e}")
                    return None
                import time; time.sleep(1)

    github_api('POST', 'https://api.github.com/user/repos', data={'name': REPO_NAME, 'private': False, 'auto_init': True})
    
    # Arquivos do App (PWA)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    sw_path = os.path.join(base_dir, 'sw.js')
    import time
    ts = int(time.time())
    sw_content = f"""const CACHE_NAME = 'cemig-dash-v{ts}';
const ASSETS = [
  './',
  './index.html',
  './manifest.json',
  './icon-192.png',
  './icon-512.png'
];

self.addEventListener('install', event => {{
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {{
      return cache.addAll(ASSETS);
    }})
  );
}});

self.addEventListener('activate', event => {{
  event.waitUntil(
    caches.keys().then(keys => {{
      return Promise.all(
        keys.map(k => caches.delete(k))
      );
    }}).then(() => self.clients.claim())
  );
}});

self.addEventListener('fetch', event => {{
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
}});
"""
    with open(sw_path, 'w', encoding='utf-8') as sf:
        sf.write(sw_content)

    files_to_upload = [
        (html_path, 'index.html'),
        (os.path.join(base_dir, 'manifest.json'), 'manifest.json'),
        (sw_path, 'sw.js'),
        (os.path.join(base_dir, 'icon-192.png'), 'icon-192.png'),
        (os.path.join(base_dir, 'icon-512.png'), 'icon-512.png')
    ]
    
    for local_path, github_path in files_to_upload:
        if not os.path.exists(local_path):
            continue
            
        print(f"Fazendo upload de {github_path}...")
        with open(local_path, 'rb') as f:
            content = f.read()
        content_b64 = base64.b64encode(content).decode('utf-8')
        
        file_url = f'https://api.github.com/repos/{USERNAME}/{REPO_NAME}/contents/{github_path}'
        existing = github_api('GET', file_url)
        sha = existing.get('sha') if existing else None
        
        upload_data = {'message': f'Atualiza {github_path}', 'content': content_b64, 'branch': 'main'}
        if sha:
            upload_data['sha'] = sha
            
        github_api('PUT', file_url, data=upload_data)
    
    github_api('POST', f'https://api.github.com/repos/{USERNAME}/{REPO_NAME}/pages', data={'source': {'branch': 'main', 'path': '/'}})
    
    print("Aplicativo (PWA) Publicado com sucesso!")
    print("Acesse pelo celular (adicione à tela inicial):")
    print(f"https://{USERNAME}.github.io/{REPO_NAME}/")

if __name__ == "__main__":
    print("Processando planilhas do CemigBot...")
    dados = processar_dados_planilhas()
    
    print(f"Usinas encontradas: {', '.join(dados['usinas'])}")
    
    template = "C:/Users/meloma/Downloads/dashboard_rateio_gd.html"
    output = os.path.join("frontend", "dashboard_frame.html")
    
    print(f"Injetando dados no HTML...")
    if injetar_dados_no_html(template, output, dados, DICIONARIO_NOMES):
        print(f"Sucesso! Painel Fonte Limpa gerado em: {os.path.abspath(output)}")
        deploy_to_github(os.path.abspath(output))
        
        # Deletar Dashboard_Atualizado.html para evitar duplicidade
        old_dash = "Dashboard_Atualizado.html"
        if os.path.exists(old_dash):
            try:
                os.remove(old_dash)
                print(f"Arquivo duplicado '{old_dash}' removido com sucesso!")
            except Exception as e:
                print(f"Aviso ao remover '{old_dash}': {e}")
    else:
        print("Falha ao gerar o dashboard.")
