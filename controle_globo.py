import os
import pandas as pd
import glob
import pdfplumber
import re

def parse_fatura_globo(globo_folder):
    """Lê arquivos PDF na pasta da Globo Eireli para extrair compensações por mês."""
    faturas = {}
    pdf_files = glob.glob(os.path.join(globo_folder, "*.pdf"))
    
    for pdf_path in pdf_files:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                text = pdf.pages[0].extract_text()
                
                # Extrair referência ex: JUN/2026 27/06/2026
                ref_match = re.search(r'([A-Z]{3}/\d{4})\s+\d{2}/\d{2}/\d{4}', text)
                if not ref_match:
                    continue
                ref_str = ref_match.group(1) # ex: JUN/2026
                
                # Converter JUN/2026 -> 06/2026
                meses = {'JAN': '01', 'FEV': '02', 'MAR': '03', 'ABR': '04', 'MAI': '05', 'JUN': '06',
                         'JUL': '07', 'AGO': '08', 'SET': '09', 'OUT': '10', 'NOV': '11', 'DEZ': '12'}
                partes = ref_str.split('/')
                mes_num = meses.get(partes[0].upper(), '01')
                comp_key = f"{mes_num}/{partes[1]}"
                
                comp_gdi = 0.0
                comp_gdii = 0.0
                consumo = 0.0
                
                match_gdi = re.search(r'Energia compensada GD I\s+kWh\s+([\d\.]+)', text)
                if match_gdi:
                    comp_gdi = float(match_gdi.group(1).replace('.', '').replace(',', '.'))
                    
                match_gdii = re.search(r'Energia compensada GD II\s+kWh\s+([\d\.]+)', text)
                if match_gdii:
                    comp_gdii = float(match_gdii.group(1).replace('.', '').replace(',', '.'))
                    
                match_cons = re.search(r'Energia kWh\s+\w+\s+[\d\.]+\s+[\d\.]+\s+[\d\.]+\s+([\d\.]+)', text)
                if match_cons:
                    consumo = float(match_cons.group(1).replace('.', '').replace(',', '.'))
                    
                faturas[comp_key] = {
                    'comp_gdi': comp_gdi,
                    'comp_gdii': comp_gdii,
                    'total_compensado': comp_gdi + comp_gdii,
                    'consumo_fatura': consumo
                }
        except Exception as e:
            print(f"Erro ao ler fatura PDF {pdf_path}: {e}")
            
    return faturas

def atualizar_controle_globo(competencia_fatura):
    base_dir = "Downloads_Cemig"
    globo_folder = os.path.join(base_dir, "GLOBO EIRELI")
    out_folder = "GLOBO EIRELI"
    out_file = os.path.join(out_folder, "Controle_Globo_Eireli.xlsx")
    globo_uc = "3000287185"

    if not os.path.exists(base_dir):
        return

    if not os.path.exists(out_folder):
        os.makedirs(out_folder)

    usinas = [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))]
    
    novas_linhas = []
    
    for usina in usinas:
        if usina == 'GLOBO EIRELI':
            continue
            
        file_path = os.path.join(base_dir, usina, f"CONSULTA_SALDO_{usina}.xlsx")
        if not os.path.exists(file_path):
            import glob
            excels = glob.glob(os.path.join(base_dir, usina, "*.xlsx"))
            if excels:
                file_path = excels[0]
            else:
                continue
            
        try:
            try:
                df = pd.read_excel(file_path)
            except PermissionError:
                # Se o arquivo estiver aberto no Excel, tenta ler de um arquivo temporario
                import tempfile, shutil
                temp_dir = tempfile.gettempdir()
                temp_path = os.path.join(temp_dir, "temp_saldo.xlsx")
                shutil.copyfile(file_path, temp_path)
                df = pd.read_excel(temp_path)
                
            col_uc = [c for c in df.columns if 'Unidade' in c][0]
            col_periodo = [c for c in df.columns if 'Per' in c and 'Saldo' not in c][0]
            
            df[col_periodo] = df[col_periodo].astype(str).str.strip()
            
            df_filtrado = df[(df[col_uc].astype(str).str.contains(globo_uc, na=False)) & (df[col_periodo] == competencia_fatura)].copy()
            
            if not df_filtrado.empty:
                df_filtrado[col_uc] = usina
                novas_linhas.append(df_filtrado)
                
        except Exception as e:
            print(f"Erro processando {usina} para controle GLOBO EIRELI: {e}")
            
    if not novas_linhas:
        print(f"Nenhum dado de injeção encontrado para a GLOBO EIRELI no periodo {competencia_fatura}.")
        return

    df_novos = pd.concat(novas_linhas, ignore_index=True)
    
    col_uc = [c for c in df_novos.columns if 'Unidade' in c][0]
    col_periodo = [c for c in df_novos.columns if 'Per' in c and 'Saldo' not in c][0]
    colunas_desejadas = ['Modalidade', col_uc, col_periodo, 'Quota', 'Posto Horário', 'Saldo Anterior', 'Saldo Expirado', 'Consumo', 'Geração', 'Compensação', 'Transferido', 'Recebimento', 'Saldo Atual', 'Quantidade Saldo a Expirar', 'Período Saldo a Expirar']
    colunas_presentes = [c for c in colunas_desejadas if c in df_novos.columns]
    df_novos_base = df_novos[colunas_presentes].copy()
    
    df_existente_base = pd.DataFrame()
    df_existente_socio = pd.DataFrame()
    
    if os.path.exists(out_file):
        try:
            df_existente_base = pd.read_excel(out_file, sheet_name='Base_Cemig')
            if not df_existente_base.empty:
                col_periodo_exist = [c for c in df_existente_base.columns if 'Per' in c and 'Saldo' not in c][0]
                df_existente_base[col_periodo_exist] = df_existente_base[col_periodo_exist].astype(str).str.strip()
                df_existente_base = df_existente_base[df_existente_base[col_periodo_exist] != competencia_fatura]
        except:
            pass
            
        try:
            df_existente_socio = pd.read_excel(out_file, sheet_name='controle_socio')
            if not df_existente_socio.empty:
                col_periodo_socio = [c for c in df_existente_socio.columns if 'Per' in c][0]
                df_existente_socio[col_periodo_socio] = df_existente_socio[col_periodo_socio].astype(str).str.strip()
                df_existente_socio = df_existente_socio[df_existente_socio[col_periodo_socio] != competencia_fatura]
        except:
            pass

    if not df_existente_base.empty:
        df_final_base = pd.concat([df_existente_base, df_novos_base], ignore_index=True)
    else:
        df_final_base = df_novos_base
        
    # Extrair fatura PDF
    dados_faturas = parse_fatura_globo(globo_folder)
    info_fat = dados_faturas.get(competencia_fatura, {})
    
    # Criar linhas para a aba controle_socio
    df_novos_socio = df_novos_base[[col_periodo, col_uc, 'Quota', 'Recebimento', 'Saldo Atual']].copy()
    df_novos_socio.rename(columns={col_periodo: 'Período', col_uc: 'Usina', 'Recebimento': 'Energia Injetada (Recebimento kWh)'}, inplace=True)
    
    # Identificar tipo de usina
    df_novos_socio['Modalidade'] = df_novos_socio['Usina'].apply(lambda u: 'GD II' if 'FONTE LIMPA II' in u else 'GD I')
    
    comp_gdi_fat = info_fat.get('comp_gdi', 0.0)
    comp_gdii_fat = info_fat.get('comp_gdii', 0.0)
    
    # Adicionar colunas do Balanço da Fatura
    df_novos_socio['Compensado Fatura GD I (Total)'] = comp_gdi_fat
    df_novos_socio['Compensado Fatura GD II (Total)'] = comp_gdii_fat
    df_novos_socio['Valor R$'] = "" 
    
    if not df_existente_socio.empty:
        df_final_socio = pd.concat([df_existente_socio, df_novos_socio], ignore_index=True)
    else:
        df_final_socio = df_novos_socio

    try:
        with pd.ExcelWriter(out_file, engine='openpyxl') as writer:
            df_final_base.to_excel(writer, sheet_name='Base_Cemig', index=False)
            df_final_socio.to_excel(writer, sheet_name='controle_socio', index=False)
        print(f"Planilha atualizada com sucesso em: {out_file}")
    except PermissionError:
        print(f"Atenção: A planilha {out_file} está aberta no Excel. Feche-a para permitir a atualização.")
    except Exception as e:
        print(f"Erro ao salvar: {e}")

if __name__ == '__main__':
    atualizar_controle_globo('05/2026')
    atualizar_controle_globo('06/2026')
