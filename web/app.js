/* =========================================
   app.js  — 多頁面 Dashboard 邏輯
   ========================================= */

document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    // 預設載入第一個頁面
    loadPage('tw');
});

/* ===== Tab 切換 ===== */
function initTabs() {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const tab = btn.dataset.tab;
            // 切換 active
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            document.querySelectorAll('.tab-page').forEach(p => p.classList.remove('active'));
            document.getElementById(`page-${tab}`).classList.add('active');
            loadPage(tab);
        });
    });
}

/* 載入紀錄 (避免重複 fetch 檔案列表) */
const loadedPages = {};

async function loadPage(tab) {
    if (loadedPages[tab]) return; // 已載入過列表就不再重複
    loadedPages[tab] = true;

    const dirMap = { tw: 'json', global: 'global_json', reports: 'reports', qd: 'qd' };
    const dir = dirMap[tab];
    const statusEl = document.getElementById(`${tab}-status`);
    const selectEl = document.getElementById(`${tab}-date-select`);

    try {
        statusEl.textContent = '載入檔案列表中...';
        const res = await fetch(`/api/list?dir=${dir}`);
        const data = await res.json();

        if (!data.files || data.files.length === 0) {
            statusEl.textContent = '⚠ 此目錄尚無檔案';
            return;
        }

        // 填充下拉選單
        selectEl.innerHTML = '';
        data.files.forEach((f, i) => {
            const opt = document.createElement('option');
            opt.value = f.name;
            opt.textContent = f.name;
            selectEl.appendChild(opt);
        });

        // 監聽切換
        selectEl.addEventListener('change', () => {
            loadFile(tab, dir, selectEl.value, statusEl);
        });

        // 自動載入最新檔案 (第一筆)
        loadFile(tab, dir, data.files[0].name, statusEl);
    } catch (err) {
        statusEl.textContent = `❌ 無法連線 (${err.message})`;
        loadedPages[tab] = false; // 允許重試
    }
}

async function loadFile(tab, dir, filename, statusEl) {
    statusEl.textContent = `載入 ${filename}...`;
    try {
        const res = await fetch(`/api/file?dir=${dir}&name=${encodeURIComponent(filename)}`);

        if (tab === 'tw') {
            const data = await res.json();
            renderTWDashboard(data);
        } else if (tab === 'global') {
            const data = await res.json();
            renderGlobalDashboard(data);
        } else if (tab === 'reports') {
            // iframe 直接設定 src
            document.getElementById('reportIframe').src = `/api/file?dir=${dir}&name=${encodeURIComponent(filename)}`;
        } else if (tab === 'qd') {
            const text = await res.text();
            renderMarkdown(text);
        }

        statusEl.textContent = `✅ ${filename}`;
    } catch (err) {
        statusEl.textContent = `❌ 載入失敗 (${err.message})`;
    }
}

/* ===== 台灣風險 Dashboard ===== */
function renderTWDashboard(data) {
    if (data['總覽']) renderOverview(data['總覽']);
    if (data['個股籌碼']) renderStocks(data['個股籌碼']);
}

function renderOverview(overviewData) {
    const container = document.getElementById('overviewCards');
    container.innerHTML = '';
    const validData = overviewData.filter(item => item['類別'] && item['指標']);

    validData.forEach((item, index) => {
        const card = document.createElement('div');
        card.className = 'indicator-card fade-in';
        card.style.animationDelay = `${index * 0.04}s`;

        let valueStr = item['當日數值'];
        if (valueStr === null || valueStr === undefined) valueStr = 'N/A';
        let changeStr = item['單日變動'] || '';
        let changeClass = '';

        if (typeof changeStr === 'string') {
            if (changeStr.includes('+')) changeClass = 'bg-danger text-danger';
            else if (changeStr.includes('-')) changeClass = 'bg-success text-success';
        } else if (typeof changeStr === 'number') {
            if (changeStr > 0) { changeClass = 'bg-danger text-danger'; changeStr = `+${changeStr.toFixed(2)}%`; }
            else if (changeStr < 0) { changeClass = 'bg-success text-success'; changeStr = `${changeStr.toFixed(2)}%`; }
        }

        const avg5d = item['5日平均'] || item['5日總和'] || '-';
        const avg20d = item['20日平均'] || item['20日總和'] || '-';

        card.innerHTML = `
            <div class="card-header">
                <p class="card-title">${item['類別']} | ${item['指標']}</p>
            </div>
            <div class="card-value">
                ${valueStr}
                ${changeStr ? `<span class="card-change ${changeClass}">${changeStr}</span>` : ''}
            </div>
            <div class="card-meta">
                <span>5D: ${avg5d}</span>
                <span>20D: ${avg20d}</span>
            </div>
        `;
        container.appendChild(card);
    });
}

function renderStocks(stocksData) {
    const tbody = document.getElementById('stocksTableBody');
    tbody.innerHTML = '';
    const validData = stocksData.filter(item => item['股票代號']);

    validData.forEach((item, index) => {
        const tr = document.createElement('tr');
        tr.className = 'fade-in';
        tr.style.animationDelay = `${index * 0.03}s`;

        const pctChange = item['漲跌幅(%)'];
        const pctClass = pctChange > 0 ? 'text-danger' : (pctChange < 0 ? 'text-success' : '');
        const pctStr = pctChange !== null && pctChange !== undefined ? `${pctChange > 0 ? '+' : ''}${parseFloat(pctChange).toFixed(2)}%` : '-';

        const foreignDaily = item['外資當日(張)'];
        const foreignClass = foreignDaily > 0 ? 'text-danger' : (foreignDaily < 0 ? 'text-success' : '');
        const foreignStr = foreignDaily !== null ? `${foreignDaily > 0 ? '+' : ''}${foreignDaily}` : '-';

        const trustDaily = item['投信當日(張)'];
        const trustClass = trustDaily > 0 ? 'text-danger' : (trustDaily < 0 ? 'text-success' : '');
        const trustStr = trustDaily !== null ? `${trustDaily > 0 ? '+' : ''}${trustDaily}` : '-';

        const score = item['籌碼評價'] || '-';
        let scoreClass = 'bg-warning text-warning';
        if (score.includes('買') || score.includes('多')) scoreClass = 'bg-danger text-danger';
        if (score.includes('賣') || score.includes('空')) scoreClass = 'bg-success text-success';

        tr.innerHTML = `
            <td><span class="stock-code">${item['股票代號']}</span></td>
            <td><span class="stock-name">${item['股票名稱'] || '-'}</span></td>
            <td style="font-weight:600;">${item['收盤價'] !== null ? item['收盤價'] : '-'}</td>
            <td class="${pctClass}">${pctStr}</td>
            <td class="${foreignClass}">${foreignStr}</td>
            <td class="${trustClass}">${trustStr}</td>
            <td>${item['融資增減(張)'] !== null ? item['融資增減(張)'] : '-'}</td>
            <td>${item['MA20乖離(%)'] !== null && item['MA20乖離(%)'] !== undefined && !isNaN(item['MA20乖離(%)']) ? `${item['MA20乖離(%)'] > 0 ? '+' : ''}${parseFloat(item['MA20乖離(%)']).toFixed(2)}%` : '-'}</td>
            <td><span class="chip ${scoreClass}">${score}</span></td>
        `;
        tbody.appendChild(tr);
    });
}

/* ===== 全球市場 Dashboard ===== */
function renderGlobalDashboard(data) {
    if (data.macro_data) renderMacro(data.macro_data);
    if (data.market_data) renderGlobalMarkets(data.market_data);
}

function renderMacro(macroData) {
    const container = document.getElementById('macroCards');
    container.innerHTML = '';

    Object.values(macroData).forEach((item, index) => {
        const card = document.createElement('div');
        card.className = 'indicator-card fade-in macro-card';
        card.style.animationDelay = `${index * 0.05}s`;

        const valStr = item.price.toFixed(2) + item.unit;
        let changeStr = item.change > 0 ? `+${item.change.toFixed(2)}` : `${item.change.toFixed(2)}`;
        if (item.unit === '%') changeStr += ' pt';

        let changeClass = 'text-secondary';
        if (item.change > 0) changeClass = 'text-success';
        else if (item.change < 0) changeClass = 'text-danger';

        card.innerHTML = `
            <div class="card-header">
                <p class="card-title font-bold text-white">${item.name}</p>
                <span class="micro-date">${item.date}</span>
            </div>
            <div class="card-value">${valStr}</div>
            <div class="card-meta">
                <span>變動幅度:</span>
                <span class="${changeClass} font-bold">${changeStr}</span>
            </div>
        `;
        container.appendChild(card);
    });
}

const CATEGORY_MAP = {
    'Americas': '美洲股市',
    'Europe': '歐洲股市',
    'AsiaPacific': '亞太股市',
    'Commodities': '原物料',
    'Rates_Forex': '美國公債與外匯'
};

function renderGlobalMarkets(marketData) {
    const container = document.getElementById('globalMarketContainer');
    container.innerHTML = '';

    Object.keys(marketData).forEach((cat, idx) => {
        const section = document.createElement('div');
        section.className = 'global-category-block glass-panel mb-4 fade-in';
        section.style.animationDelay = `${idx * 0.08}s`;

        const title = document.createElement('h3');
        title.className = 'category-title text-center mb-4';
        title.textContent = CATEGORY_MAP[cat] || cat;
        section.appendChild(title);

        const grid = document.createElement('div');
        grid.className = 'market-mini-cards-grid';

        marketData[cat].forEach(item => {
            const card = document.createElement('div');
            card.className = 'market-mini-card text-center';
            const priceStr = item.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            let changeStr = item.change > 0 ? `+${item.change.toFixed(2)}${item.unit}` : `${item.change.toFixed(2)}${item.unit}`;
            let changeClass = 'text-secondary';
            if (item.change > 0) changeClass = 'text-success';
            else if (item.change < 0) changeClass = 'text-danger';

            card.innerHTML = `
                <div class="mini-name">${item.name}</div>
                <div class="micro-date">${item.date}</div>
                <div class="mini-price">${priceStr}</div>
                <div class="mini-change ${changeClass}">${changeStr}</div>
            `;
            grid.appendChild(card);
        });

        section.appendChild(grid);
        container.appendChild(section);
    });
}

/* ===== Markdown → HTML 簡易渲染 ===== */
function renderMarkdown(md) {
    const container = document.getElementById('qdContent');
    let html = md
        // Headers
        .replace(/^### (.+)$/gm, '<h3>$1</h3>')
        .replace(/^## (.+)$/gm, '<h2 class="md-h2">$1</h2>')
        .replace(/^# (.+)$/gm, '<h1 class="md-h1">$1</h1>')
        // Bold
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        // List items
        .replace(/^- (.+)$/gm, '<li>$1</li>')
        // Paragraphs & line breaks
        .replace(/\n\n/g, '</p><p>')
        .replace(/\n/g, '<br>');

    // Wrap consecutive <li> in <ul>
    html = html.replace(/(<li>.*?<\/li>(?:<br>)?)+/gs, (match) => {
        return '<ul class="md-list">' + match.replace(/<br>/g, '') + '</ul>';
    });

    container.innerHTML = `<div class="md-rendered"><p>${html}</p></div>`;
}
