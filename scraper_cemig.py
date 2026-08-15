import os
import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

consorcios = {
    "GLOBO EIRELI": {
        "login": "comercioglobofinanceiro@gmail.com",
        "senha": "120509",
        "pausa_instalacao": True
    },
    "UFV SOLAR DO NORTE": {
        "login": "financeirosolardonorte@gmail.com",
        "senha": "340050cj",
        "pausa_instalacao": True
    },
    "UFV SANTA DA PEDRA (JULIANO)": {
        "login": "ufv.consorciosantadapedra@gmail.com",
        "senha": "340050CJ"
    },
    "UFV SANTA CLARA": {
        "login": "ufv.consorciosantaclara@gmail.com",
        "senha": "340050Cj"
    },
    "UFV FB": {
        "login": "ufv.consorciosolarfb@gmail.com",
        "senha": "FBEnergia@69"
    },
    "UFV FONTE LIMPA I (ULYANA)": {
        "login": "ufv.consorciofontelimpa@gmail.com",
        "senha": "340050cj"
    },
    "UFV FONTE LIMPA II (NOVA SERRANA)": {
        "login": "mario.melo@snef.com.br",
        "senha": "340050Cj"
    },
    "UFV INHAÚMA": {
        "login": "ufv.consorcioinhauma@gmail.com",
        "senha": "340050@Cj"
    }
}

async def processar_consorcio_async(nome, dados, base_dir="Downloads_Cemig"):
    consorcio_dir = os.path.join(base_dir, nome)
    os.makedirs(consorcio_dir, exist_ok=True)
    
    async with Stealth().use_async(async_playwright()) as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--start-maximized'
            ],
            ignore_default_args=["--enable-automation"]
        )
        context = await browser.new_context(no_viewport=True)
        page = await context.new_page()
        
        try:
            print(f"[{nome}] Acessando Cemig...")
            await page.goto("https://atende.cemig.com.br/Login", timeout=60000)
            await page.wait_for_load_state("networkidle")
            
            usuario_locator = page.locator("input[type='text'], input[type='email'], input[name='login'], input[placeholder*='do Usuário'], input[placeholder*='CPF']").first
            await usuario_locator.fill(dados['login'])
            
            senha_locator = page.locator("input[type='password']").first
            await senha_locator.fill(dados['senha'])
            
            print(f"[{nome}] AGUARDANDO RESOLUÇÃO DO CAPTCHA NO NAVEGADOR...")
            
            # Espera o login ser efetuado (mudança de URL)
            for i in range(300):
                if "login" not in page.url.lower():
                    break
                await page.wait_for_timeout(1000)
                
            if "login" in page.url.lower():
                raise Exception("Timeout esperando o Captcha.")
                
            print(f"[{nome}] Login concluído! Navegando...")
            await page.wait_for_load_state("networkidle")
            
            if dados.get("pausa_instalacao"):
                print(f"[{nome}] Consórcio exige troca manual de instalação. Injetando botão de continuar...")
                await page.evaluate("""
                    () => {
                        const btn = document.createElement('button');
                        btn.id = 'btn-continuar-robo';
                        btn.innerText = 'ROBÔ: CLIQUE AQUI QUANDO ESTIVER NA INSTALAÇÃO CORRETA';
                        btn.style.position = 'fixed';
                        btn.style.bottom = '20px';
                        btn.style.right = '20px';
                        btn.style.zIndex = '999999';
                        btn.style.padding = '20px';
                        btn.style.fontSize = '18px';
                        btn.style.fontWeight = 'bold';
                        btn.style.backgroundColor = '#10b981';
                        btn.style.color = 'white';
                        btn.style.border = 'none';
                        btn.style.borderRadius = '10px';
                        btn.style.cursor = 'pointer';
                        btn.style.boxShadow = '0px 4px 15px rgba(0,0,0,0.5)';
                        document.body.appendChild(btn);
                        
                        btn.onclick = () => {
                            window.roboContinuar = true;
                            btn.innerText = 'Continuando...';
                            btn.style.backgroundColor = '#6b7280';
                        };
                    }
                """)
                # Aguarda o clique por até 5 minutos
                for _ in range(300):
                    continuar = await page.evaluate("window.roboContinuar === true")
                    if continuar:
                        break
                    await page.wait_for_timeout(1000)
            else:
                await page.wait_for_timeout(3000)
            
            try:
                await page.locator("text='Serviços'").first.click(timeout=10000)
                await page.wait_for_timeout(2000)
            except:
                pass
                
            pages_antes = len(context.pages)
            await page.locator("text='Mini / Micro Geração Distribuída'").first.click(timeout=15000)
            await page.wait_for_timeout(5000)
            
            if len(context.pages) > pages_antes:
                page = context.pages[-1]
                
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(3000)
            
            await page.locator("text='Consulta Saldo GD'").first.click(timeout=15000)
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(6000)
            
            print(f"[{nome}] Baixando Excel...")
            async with page.expect_download(timeout=90000) as download_info:
                await page.get_by_text("Exportar para Excel", exact=False).first.click()
                
            download = await download_info.value
            file_name = f"CONSULTA_SALDO_{nome}.xlsx"
            download_path = os.path.join(consorcio_dir, file_name)
            
            await download.save_as(download_path)
            print(f"[{nome}] Sucesso no Excel! Salvo em: {download_path}\n")
            
            # Tentar baixar a 2ª Via da Fatura (PDF)
            try:
                print(f"[{nome}] Tentando baixar 2ª via da fatura (PDF)...")
                await page.goto("https://atende.cemig.com.br/SegundaVia", timeout=30000)
                await page.wait_for_load_state("networkidle")
                await page.wait_for_timeout(3000)
                
                pdf_btn = page.locator("a[href*='pdf'], button:has-text('Baixar'), button:has-text('PDF'), .icon-pdf, text='Baixar 2ª Via'").first
                if await pdf_btn.is_visible():
                    async with page.expect_download(timeout=30000) as pdf_info:
                        await pdf_btn.click()
                    pdf_down = await pdf_info.value
                    pdf_path = os.path.join(consorcio_dir, f"fatura_{nome.replace(' ', '_')}.pdf")
                    await pdf_down.save_as(pdf_path)
                    print(f"[{nome}] Fatura PDF salva com sucesso em: {pdf_path}\n")
            except Exception as ep:
                print(f"[{nome}] Aviso: Não foi possível baixar PDF da fatura automaticamente ({ep})\n")
                
            return True
            
        except Exception as e:
            print(f"[{nome}] Erro: {e}")
            return False
        finally:
            await context.close()
            await browser.close()

async def baixar_multiplos_consorcios(lista_nomes):
    for nome in lista_nomes:
        if nome in consorcios:
            dados = consorcios[nome]
            print(f"Iniciando automação para: {nome}")
            sucesso = await processar_consorcio_async(nome, dados)
            if not sucesso:
                print(f"ALERTA: Falha no download de {nome}. A fatura pode ficar incompleta.")
        else:
            print(f"Aviso: Consórcio '{nome}' não encontrado no mapeamento.")
