const formatCurrency = (value) => {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value);
};

let manualClients = [];
let allClients = [];
let selectedPeriod = null;

function renderPeriodSelector() {
    const container = document.getElementById('period-selector');
    if (!container) return;
    container.innerHTML = '';
    
    const periods = [];
    const now = new Date();
    // Default to the month before current, as reports are usually generated for the past month
    let targetMonthDate = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    let targetM = String(targetMonthDate.getMonth() + 1).padStart(2, '0');
    let targetY = targetMonthDate.getFullYear();
    selectedPeriod = `${targetM}/${targetY}`;

    // Generate last 10 months and next 2 months
    for(let i = -10; i <= 2; i++) {
        let d = new Date(now.getFullYear(), now.getMonth() + i, 1);
        let m = String(d.getMonth() + 1).padStart(2, '0');
        let y = d.getFullYear();
        periods.push(`${m}/${y}`);
    }
    
    periods.forEach(p => {
        const isSelected = (p === selectedPeriod);
        container.innerHTML += `
            <div class="period-box ${isSelected ? 'selected' : ''}" onclick="selectPeriod('${p}')">
                ${p}
            </div>
        `;
    });
}

window.selectPeriod = function(p) {
    selectedPeriod = p;
    document.querySelectorAll('.period-box').forEach(el => {
        if(el.innerText.trim() === p) el.classList.add('selected');
        else el.classList.remove('selected');
    });
}

// Switch Tabs
function switchTab(tabId) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.nav-links li').forEach(el => el.classList.remove('active'));
    
    const targetTab = document.getElementById(`tab-${tabId}`);
    if (targetTab) targetTab.classList.add('active');
    if (window.event && window.event.currentTarget) window.event.currentTarget.classList.add('active');
    
    if (tabId === 'dashboard') {
        const iframe = document.querySelector('#tab-dashboard iframe');
        if (iframe) {
            iframe.src = '/static/dashboard_frame.html?v=' + Date.now();
        }
    }
    
    const titles = {
        'dashboard': { title: 'Visão Geral', sub: 'Acompanhe a economia e faturamento dos seus consórcios.' },
        'emitir': { title: 'Emitir Relatórios', sub: 'Faça upload da planilha para gerar as faturas.' },
        'notas': { title: 'Controle Contábil', sub: 'Exporte as planilhas consolidadas.' },
        'rateio': { title: 'Rateio de Energia', sub: 'Visualize e edite as porcentagens de rateio dos clientes.' }
    };
    
    document.getElementById('page-title').innerText = titles[tabId].title;
    document.getElementById('page-subtitle').innerText = titles[tabId].sub;

    if(tabId === 'dashboard') loadDashboard();
    if(tabId === 'emitir' && allClients.length === 0) loadDashboard();
    if(tabId === 'rateio') loadRateios();
}

// Load Dashboard Data
async function loadDashboard() {
    try {
        const res = await fetch('/api/dashboard');
        const data = await res.json();
        
        allClients = data.clientes; // Store for the selection list
        renderClientList();
        renderPeriodSelector();
    } catch(e) {
        console.error("Erro ao carregar dashboard:", e);
    }
}

// Upload Setup REMOVED (Scraping automated)

async function fetchManualClients() {
    const res = await fetch('/api/clientes_manuais');
    manualClients = await res.json();
    
    const container = document.getElementById('manual-inputs-container');
    if (!container) return;
    container.innerHTML = '';
    
    if(manualClients.length === 0) {
        container.innerHTML = '<p style="color:#10b981;">Nenhuma entrada manual necessária!</p>';
        return;
    }
    
    manualClients.forEach(c => {
        container.innerHTML += `
            <div class="input-group">
                <label>${c.razao_social}</label>
                <input type="number" id="input-${c.cnpj.replace(/\D/g, '')}" placeholder="Digite o valor compensado (kWh)">
            </div>
        `;
    });
}

function nextStep(step) {
    document.querySelectorAll('.wizard-step').forEach(el => {
        el.classList.remove('active');
        el.classList.add('locked');
    });
    
    const target = document.getElementById(`step-${step}`);
    if(target) {
        target.classList.remove('locked');
        target.classList.add('active');
    }
}

function renderClientList() {
    const list = document.getElementById('client-selection-list');
    if (!list) return;
    list.innerHTML = '';
    
    allClients.forEach(c => {
        list.innerHTML += `
            <label class="client-label">
                <input type="checkbox" class="client-checkbox" value="${c.cnpj}"> 
                ${c.razao_social}
            </label>
        `;
    });
}

function toggleAllClients(checkAllBox) {
    const isChecked = checkAllBox.checked;
    const labels = document.querySelectorAll('.client-label');
    const checkboxes = document.querySelectorAll('.client-checkbox');
    
    labels.forEach(l => {
        if (isChecked) {
            l.classList.add('disabled');
        } else {
            l.classList.remove('disabled');
        }
    });
    
    checkboxes.forEach(cb => {
        if (isChecked) {
            cb.checked = true;
            cb.disabled = true;
        } else {
            cb.disabled = false;
        }
    });
}

async function baixarEGerar() {
    const btn = document.getElementById('btn-gerar');
    const prog = document.getElementById('progress-container');
    const text = document.getElementById('progress-text');
    btn.disabled = true;
    prog.style.display = 'block';
    text.innerText = "Baixando planilhas e gerando relatórios... Olhe a janela do navegador!";
    
    let selecionados = [];
    const checkAll = document.getElementById('check-all').checked;
    if (!checkAll) {
        document.querySelectorAll('.client-checkbox:checked').forEach(cb => {
            selecionados.push(cb.value);
        });
        if (selecionados.length === 0) {
            showToast("Selecione pelo menos um cliente.");
            btn.disabled = false;
            prog.style.display = 'none';
            return;
        }
    }
    
    const tarifaCemigVal = document.getElementById('tarifa-cemig-input').value;
    const tarifaFioBVal = document.getElementById('tarifa-fiob-input').value;
    
    const payload = {
        clientes_selecionados: selecionados,
        periodo_referencia: selectedPeriod,
        tarifa_cemig: tarifaCemigVal ? parseFloat(tarifaCemigVal) : null,
        tarifa_fiob: tarifaFioBVal ? parseFloat(tarifaFioBVal) : null
    };
    
    try {
        const response = await fetch('/api/baixar_e_gerar', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showToast("Sucesso! Relatórios gerados!");
            nextStep(3);
        } else {
            showToast("Erro: " + result.message);
            btn.disabled = false;
            prog.style.display = 'none';
        }
    } catch (err) {
        console.error(err);
        showToast("Erro de comunicação com servidor");
        btn.disabled = false;
        prog.style.display = 'none';
    }
}

function showToast(msg) {
    const toast = document.getElementById('toast');
    toast.innerText = msg;
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 4000);
}

// --- RATEIO TAB LOGIC ---
window.rateioDataCache = null;

async function loadRateios() {
    const container = document.getElementById('rateio-container');
    container.innerHTML = '<div class="loader"></div><span style="color: var(--text-secondary);">Carregando rateios...</span>';
    
    try {
        const res = await fetch('/api/rateio');
        const payload = await res.json();
        if (payload.status !== 'success') {
            container.innerHTML = `<span style="color: #ef4444;">Erro: ${payload.message}</span>`;
            return;
        }
        
        window.rateioDataCache = payload;
        renderRateioTable();
    } catch (e) {
        console.error(e);
        container.innerHTML = `<span style="color: #ef4444;">Erro de conexão ao buscar rateios.<br><small>${e.message}</small></span>`;
    }
}

function renderRateioTable() {
    const container = document.getElementById('rateio-container');
    const { data, nomes, uc_to_cliente, rateios_custom } = window.rateioDataCache;
    
    if (!data.dashboard_data || Object.keys(data.dashboard_data).length === 0) {
        container.innerHTML = '<span style="color: var(--text-secondary);">Nenhum dado encontrado nas planilhas.</span>';
        return;
    }
    
    let html = '';
    
    for (const usina of data.usinas) {
        const usinaData = data.dashboard_data[usina];
        const ultimoPeriodo = usinaData.ultimo_periodo;
        if (!ultimoPeriodo) continue;
        
        const historico = usinaData.recebedoras_historico[ultimoPeriodo];
        if (!historico || historico.length === 0) continue;
        
        html += `
        <div style="background: rgba(30,41,59,0.5); border-radius: 8px; margin-bottom: 30px; overflow: hidden; border: 1px solid rgba(255,255,255,0.05);">
            <div style="background: rgba(16,185,129,0.1); padding: 15px 20px; border-bottom: 1px solid rgba(16,185,129,0.2);">
                <h3 style="color: #10b981; margin: 0; display: flex; align-items: center; gap: 10px;">
                    <i class='bx bxs-sun'></i> ${usina} <span style="font-size: 0.8em; color: var(--text-secondary); margin-left: auto;">Referência: ${ultimoPeriodo}</span>
                </h3>
            </div>
            <div style="overflow-x: auto;">
                <table style="width: 100%; border-collapse: collapse; text-align: left; font-size: 13px;">
                    <thead>
                        <tr style="background: rgba(15,23,42,0.8); border-bottom: 2px solid rgba(255,255,255,0.05);">
                            <th style="padding: 12px; color: #94a3b8; font-weight: 600;">UC's GERADORA</th>
                            <th style="padding: 12px; color: #94a3b8; font-weight: 600;">MODALIDADE</th>
                            <th style="padding: 12px; color: #94a3b8; font-weight: 600;">CONSORCIADOS</th>
                            <th style="padding: 12px; color: #94a3b8; font-weight: 600;">CNPJ</th>
                            <th style="padding: 12px; color: #94a3b8; font-weight: 600;">EMAIL</th>
                            <th style="padding: 12px; color: #94a3b8; font-weight: 600;">PORCENTAGEM</th>
                            <th style="padding: 12px; color: #94a3b8; font-weight: 600;">NOVA PORCENTAGEM</th>
                            <th style="padding: 12px; color: #94a3b8; font-weight: 600;">SALDO (Kw)</th>
                            <th style="padding: 12px; color: #94a3b8; font-weight: 600;">ALTERAÇÃO DE RATEIO</th>
                        </tr>
                    </thead>
                    <tbody>
        `;
        
        historico.forEach(row => {
            const ucStr = row.UC_short;
            const modalidade = row.Modalidade || (row.Quota_pct === 0 ? 'GERADORA' : 'RECEBEDORA');
            
            // Lookups
            const clienteInfo = uc_to_cliente[ucStr] || {};
            const custom = rateios_custom[ucStr] || {};
            
            const consorciado = nomes[ucStr] || clienteInfo.razao_social || 'N/A';
            const cnpj = clienteInfo.cnpj || 'N/A';
            
            const emailVal = custom.email || '';
            const novaPorcVal = custom.nova_porcentagem || '';
            const alteracaoVal = custom.alteracao || '';
            
            const pctStr = row.Quota_pct > 0 ? row.Quota_pct.toFixed(2) + '%' : '0.00%';
            
            html += `
                <tr style="border-bottom: 1px solid rgba(255,255,255,0.05); transition: all 0.2s; hover: background: rgba(255,255,255,0.02);" data-uc="${ucStr}">
                    <td style="padding: 12px; color: white;">${ucStr}</td>
                    <td style="padding: 12px;"><span style="background: ${modalidade.includes('GERADORA') ? 'rgba(59,130,246,0.1)' : 'rgba(16,185,129,0.1)'}; color: ${modalidade.includes('GERADORA') ? '#3b82f6' : '#10b981'}; padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: 600;">${modalidade}</span></td>
                    <td style="padding: 12px; color: white;">${consorciado}</td>
                    <td style="padding: 12px; color: var(--text-secondary);">${cnpj}</td>
                    <td style="padding: 12px;"><input type="text" class="input-email" value="${emailVal}" placeholder="email@exemplo.com" style="width: 150px; padding: 6px; background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.1); border-radius: 4px; color: white; font-size: 12px;"></td>
                    <td style="padding: 12px; font-weight: bold; color: ${row.Quota_pct > 0 ? '#38bdf8' : '#ef4444'};">${pctStr}</td>
                    <td style="padding: 12px;"><input type="text" class="input-nova-porc" value="${novaPorcVal}" placeholder="Ex: 5%" style="width: 80px; padding: 6px; background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.1); border-radius: 4px; color: white; font-size: 12px;"></td>
                    <td style="padding: 12px; color: white; font-weight: bold;">${row.SaldoAtual}</td>
                    <td style="padding: 12px;"><input type="text" class="input-alteracao" value="${alteracaoVal}" placeholder="Obs..." style="width: 200px; padding: 6px; background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.1); border-radius: 4px; color: white; font-size: 12px;"></td>
                </tr>
            `;
        });
        
        html += `
                    </tbody>
                </table>
            </div>
        </div>
        `;
    }
    
    container.innerHTML = html;
}

async function saveRateios() {
    const btn = document.querySelector('#tab-rateio .btn-primary');
    btn.innerHTML = '<i class="bx bx-loader-alt bx-spin"></i> Salvando...';
    btn.disabled = true;
    
    const container = document.getElementById('rateio-container');
    const rows = container.querySelectorAll('tbody tr');
    
    const payload = {};
    
    rows.forEach(row => {
        const uc = row.getAttribute('data-uc');
        const email = row.querySelector('.input-email').value;
        const novaPorc = row.querySelector('.input-nova-porc').value;
        const alteracao = row.querySelector('.input-alteracao').value;
        
        payload[uc] = {
            email: email,
            nova_porcentagem: novaPorc,
            alteracao: alteracao
        };
    });
    
    try {
        const res = await fetch('/api/rateio/save', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const result = await res.json();
        if(res.ok) {
            showToast("Rateios e observações salvos com sucesso!");
        } else {
            showToast("Erro: " + result.message);
        }
    } catch(e) {
        console.error(e);
        showToast("Erro de comunicação com o servidor.");
    } finally {
        btn.innerHTML = '<i class="bx bx-save"></i> Salvar Rateios';
        btn.disabled = false;
    }
}

// Init
loadDashboard();
