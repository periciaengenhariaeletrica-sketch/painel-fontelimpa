import os
import json
import asyncio
from fastapi import FastAPI, UploadFile, File, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
import shutil
import glob
from pathlib import Path

# Fix Windows event loop for Playwright/asyncio
import sys
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import gerar_relatorios  # O nosso script gerador
import scraper_cemig
import pandas as pd
import gerar_dashboard

app = FastAPI(title="CemigDash")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "db_clientes.json")
DOWNLOADS_DIR = os.path.join(BASE_DIR, "Downloads_Cemig")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

# Serve frontend static files
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

def get_db():
    if not os.path.exists(DB_PATH):
        return {"clientes": {}, "entradas_manuais": {}}
    with open(DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(data):
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    with open(os.path.join(FRONTEND_DIR, "index.html"), "r", encoding="utf-8") as f:
        return f.read()

@app.get("/api/dashboard")
async def get_dashboard_data():
    db = get_db()
    clientes = db.get("clientes", {})
    
    total_economizado = 0
    faturas_geradas = 0
    clientes_ativos = len([c for c in clientes.values() if "razao_social" in c])
    
    historico_mensal_consolidado = {}
    
    for cnpj, info in clientes.items():
        total_economizado += info.get("economia_acumulada", 0)
        hist = info.get("historico_mensal", [])
        faturas_geradas += len(hist)
        
        for h in hist:
            periodo = h["periodo"]
            eco = h.get("economia_mes", 0)
            historico_mensal_consolidado[periodo] = historico_mensal_consolidado.get(periodo, 0) + eco
            
    # Sort history by period
    def sort_key(p):
        try:
            m, y = p.split("/")
            return (int(y), int(m))
        except:
            return (0,0)
            
    sorted_periods = sorted(historico_mensal_consolidado.keys(), key=sort_key)[-6:] # last 6 months
    chart_data = [{"name": p, "value": historico_mensal_consolidado[p]} for p in sorted_periods]
    
    return {
        "kpis": {
            "total_economizado": total_economizado,
            "clientes_ativos": clientes_ativos,
            "faturas_geradas": faturas_geradas
        },
        "chart_data": chart_data,
        "clientes": [{"razao_social": c["razao_social"], "cnpj": c["cnpj"], "economia_acumulada": c.get("economia_acumulada", 0)} for c in clientes.values()]
    }

@app.get("/api/clientes_manuais")
async def get_clientes_manuais():
    db = get_db()
    clientes = db.get("clientes", {})
    manuais = []
    for cnpj, info in clientes.items():
        if info.get("pede_entrada_manual", False):
            manuais.append({"cnpj": cnpj, "razao_social": info["razao_social"]})
    return manuais

@app.post("/api/upload_planilha")
async def upload_planilha(file: UploadFile = File(...)):
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)
    file_location = os.path.join(DOWNLOADS_DIR, file.filename)
    with open(file_location, "wb+") as file_object:
        shutil.copyfileobj(file.file, file_object)
        
    return {"info": f"Planilha '{file.filename}' salva com sucesso!"}

@app.post("/api/gerar_relatorios")
async def rodar_geracao(request: Request):
    data = await request.json()
    entradas = data.get("entradas_manuais", {})
    selecionados = data.get("clientes_selecionados", [])
    
    # Pre-save entradas manuais no banco
    if entradas:
        db = get_db()
        # Find latest period
        periodo = gerar_relatorios.find_latest_period_and_files()[0]
        if periodo:
            if "entradas_manuais" not in db: db["entradas_manuais"] = {}
            if periodo not in db["entradas_manuais"]: db["entradas_manuais"][periodo] = {}
            
            for cnpj, val in entradas.items():
                db["entradas_manuais"][periodo][cnpj] = float(val)
            
            save_db(db)
    
    try:
        # Chama a função principal passando apenas os selecionados
        await gerar_relatorios.process_reports(selected_cnpjs=selecionados if selecionados else None)
        return {"status": "success", "message": "Relatórios gerados com sucesso e salvos na pasta!"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.post("/api/baixar_e_gerar")
async def baixar_e_gerar(request: Request):
    data = await request.json()
    selecionados = data.get("clientes_selecionados", [])
    periodo_referencia = data.get("periodo_referencia")
    tarifa_cemig = data.get("tarifa_cemig")
    tarifa_fiob = data.get("tarifa_fiob")
    
    db = get_db()
    clientes = db.get("clientes", {})
    
    # 1. Descobrir quais consórcios precisam ser baixados
    consorcios_necessarios = set()
    
    if not selecionados:
        # Se vazio, processar todos
        selecionados = list(clientes.keys())
        
    for cnpj in selecionados:
        info = clientes.get(cnpj, {})
        consorcios_cli = info.get("consorcios_scraper", [])
        for c in consorcios_cli:
            consorcios_necessarios.add(c)
            
    if not consorcios_necessarios:
        return JSONResponse(status_code=400, content={"status": "error", "message": "Nenhum consórcio configurado para os clientes selecionados."})
        
    # 2. NÃO vamos limpar a pasta de downloads antiga para garantir o histórico
    # (A pedido do usuário, os arquivos passados não devem ser deletados)
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)
                
    # 3. Rodar o scraper de forma assíncrona
    consorcios_lista = list(consorcios_necessarios)
    print(f"Iniciando download dos consórcios: {consorcios_lista}")
    await scraper_cemig.baixar_multiplos_consorcios(consorcios_lista)
    
    # 4. Gerar relatórios
    try:
        await gerar_relatorios.process_reports(selected_cnpjs=selecionados, periodo_referencia=periodo_referencia, tarifa_cemig_global=tarifa_cemig, tarifa_fiob_global=tarifa_fiob)
        return {"status": "success", "message": "Planilhas baixadas e relatórios gerados com sucesso!"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"status": "error", "message": f"Erro na geração: {str(e)}"})

@app.get("/api/dashboard_cemig")
async def get_dashboard_data():
    try:
        dados = gerar_dashboard.processar_dados_planilhas("Downloads_Cemig")
        nomes = gerar_dashboard.DICIONARIO_NOMES
        return {"status": "success", "data": dados, "nomes": nomes}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.get("/api/rateio")
async def get_rateio():
    try:
        dados = gerar_dashboard.processar_dados_planilhas(DOWNLOADS_DIR)
        db = get_db()
        clientes = db.get("clientes", {})
        rateios_custom = db.get("rateios_custom", {})
        
        # Mapear UC para cliente e CNPJ
        uc_to_cliente = {}
        for cnpj, info in clientes.items():
            for uc in info.get("ucs", []):
                uc_str = str(uc)
                if uc_str not in uc_to_cliente:
                    uc_to_cliente[uc_str] = {"cnpj": cnpj, "razao_social": info.get("razao_social", "")}
                    
        return {
            "status": "success", 
            "data": dados, 
            "nomes": gerar_dashboard.DICIONARIO_NOMES,
            "uc_to_cliente": uc_to_cliente,
            "rateios_custom": rateios_custom
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.post("/api/rateio/save")
async def save_rateio(request: Request):
    try:
        payload = await request.json()
        db = get_db()
        if "rateios_custom" not in db:
            db["rateios_custom"] = {}
            
        for uc, custom_data in payload.items():
            if uc not in db["rateios_custom"]:
                db["rateios_custom"][uc] = {}
            # custom_data is a dict like {"nova_porcentagem": "96%", "alteracao": "...", "email": "..."}
            db["rateios_custom"][uc].update(custom_data)
            
        save_db(db)
        return {"status": "success", "message": "Rateio salvo com sucesso!"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.get("/api/download_notas")
async def download_notas():
    # Encontra o arquivo de notas mais recente
    arquivos = glob.glob(os.path.join(BASE_DIR, "Controle_Emissao_Notas_*.xlsx"))
    if not arquivos:
        return JSONResponse(status_code=404, content={"message": "Nenhuma planilha encontrada."})
    
    latest = max(arquivos, key=os.path.getctime)
    return FileResponse(path=latest, filename=os.path.basename(latest), media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

if __name__ == "__main__":
    print("Iniciando CemigDash...")
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("api:app", host="0.0.0.0", port=port, reload=False, loop="asyncio")
