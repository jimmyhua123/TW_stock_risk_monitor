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

    const dirMap = {
        tw: 'json',
        global: 'global_json',
        coverage: 'coverage_json',
        derivatives: 'derivatives_json',
        reports: 'reports',
        qd: 'qd'
    };
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

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

/* ===== 台灣風險 Dashboard ===== */
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

/* ===== 全球市場 Dashboard ===== */
function renderGlobalDashboard(data) {
    if (data.macro_data) renderMacro(data.macro_data);
    if (data.market_data) renderGlobalMarkets(data.market_data);
}

function renderMacro(macroData) {
    const container = document.getElementById('macroCards');
    container.innerHTML = '';

    Object.values(macroData).forEach((item, index) => {
        if (!item) return;
        const card = document.createElement('div');
        card.className = 'indicator-card fade-in macro-card';
        card.style.animationDelay = `${index * 0.05}s`;

        const price = item.price;
        const change = item.change;
        const unit = item.unit || '';

        const valStr = (price !== null && price !== undefined) ? price.toFixed(2) + unit : 'N/A';
        let changeStr = '-';
        let changeClass = 'text-secondary';

        if (change !== null && change !== undefined) {
            changeStr = change > 0 ? `+${change.toFixed(2)}` : `${change.toFixed(2)}`;
            if (unit === '%') changeStr += ' pt';

            if (change > 0) changeClass = 'text-success';
            else if (change < 0) changeClass = 'text-danger';
        }

        card.innerHTML = `
            <div class="card-header">
                <p class="card-title font-bold text-white">${item.name || 'Unknown'}</p>
                <span class="micro-date">${item.date || '-'}</span>
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
            if (!item) return;
            const card = document.createElement('div');
            card.className = 'market-mini-card text-center';

            const price = item.price;
            const change = item.change;
            const unit = item.unit || '';

            // 使用超強防呆，確保 price 是數字且不為 null
            const priceStr = (price !== null && price !== undefined) 
                ? price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) 
                : '-';
            
            let changeStr = '-';
            let changeClass = 'text-secondary';

            if (change !== null && change !== undefined) {
                changeStr = change > 0 ? `+${change.toFixed(2)}${unit}` : `${change.toFixed(2)}${unit}`;
                if (change > 0) changeClass = 'text-success';
                else if (change < 0) changeClass = 'text-danger';
            }

            card.innerHTML = `
                <div class="mini-name">${item.name || 'Unknown'}</div>
                <div class="micro-date">${item.date || '-'}</div>
                <div class="mini-price">${priceStr}</div>
                <div class="mini-change ${changeClass}">${changeStr}</div>
            `;
            grid.appendChild(card);
        });

        section.appendChild(grid);
        container.appendChild(section);
    });
}

/* ===== 題材補充 Dashboard ===== */
function renderCoverageDashboard(data) {
    const summaryEl = document.getElementById('coverageSummary');
    const container = document.getElementById('coverageContainer');
    const items = Array.isArray(data.items) ? data.items : [];
    const foundItems = items.filter(item => item.found);
    const missingItems = items.filter(item => !item.found);

    summaryEl.innerHTML = `
        <div class="coverage-summary-card glass-panel">
            <div>
                <div class="summary-label">資料來源</div>
                <div class="summary-value">${escapeHtml(data.source || 'Timeverse/My-TW-Coverage')}</div>
            </div>
            <div>
                <div class="summary-label">日期</div>
                <div class="summary-value">${escapeHtml(data.date || '-')}</div>
            </div>
            <div>
                <div class="summary-label">匹配</div>
                <div class="summary-value">${foundItems.length}/${items.length}</div>
            </div>
            <div>
                <div class="summary-label">授權</div>
                <div class="summary-value">${escapeHtml(data.source_license || 'MIT')}</div>
            </div>
        </div>
    `;

    container.innerHTML = '';
    if (!items.length) {
        container.innerHTML = '<div class="empty-state glass-panel">沒有可顯示的題材資料</div>';
        return;
    }

    foundItems.forEach((item, index) => {
        const card = document.createElement('article');
        card.className = 'coverage-card fade-in';
        card.style.animationDelay = `${index * 0.03}s`;
        card.innerHTML = renderCoverageItem(item);
        container.appendChild(card);
    });

    if (missingItems.length) {
        const missing = document.createElement('div');
        missing.className = 'coverage-missing glass-panel';
        missing.innerHTML = `
            <div class="summary-label">未匹配</div>
            <div class="coverage-tags">
                ${missingItems.map(item => `<span class="coverage-tag muted">${escapeHtml(item.code)} ${escapeHtml(item.name || '')}</span>`).join('')}
            </div>
        `;
        container.appendChild(missing);
    }
}

function renderCoverageItem(item) {
    const themes = Array.isArray(item.themes) ? item.themes.slice(0, 12) : [];
    const partners = Array.isArray(item.customers_suppliers) ? item.customers_suppliers.slice(0, 10) : [];

    return `
        <div class="coverage-card-header">
            <div>
                <div class="coverage-code">${escapeHtml(item.code)}</div>
                <h3>${escapeHtml(item.company || item.name || '-')}</h3>
            </div>
            <div class="coverage-industry">${escapeHtml(item.industry || '-')}</div>
        </div>
        <div class="coverage-meta">${escapeHtml(item.sector || '-')}</div>
        <p class="coverage-summary-text">${escapeHtml(item.business_summary || '-')}</p>
        <div class="coverage-block">
            <div class="coverage-label">題材</div>
            <div class="coverage-tags">${renderTags(themes)}</div>
        </div>
        <div class="coverage-block">
            <div class="coverage-label">客戶 / 供應商</div>
            <div class="coverage-tags">${renderTags(partners)}</div>
        </div>
    `;
}

function renderTags(tags) {
    if (!tags.length) return '<span class="coverage-tag muted">-</span>';
    return tags.map(tag => `<span class="coverage-tag">${escapeHtml(tag)}</span>`).join('');
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

/* ===== TW dashboard coverage integration ===== */
let coverageIndexPromise = null;

async function loadCoverageIndex() {
    if (coverageIndexPromise) return coverageIndexPromise;

    coverageIndexPromise = (async () => {
        try {
            const listRes = await fetch('/api/list?dir=coverage_json');
            const listData = await listRes.json();
            const latest = Array.isArray(listData.files) && listData.files.length ? listData.files[0].name : null;
            if (!latest) return new Map();

            const fileRes = await fetch(`/api/file?dir=coverage_json&name=${encodeURIComponent(latest)}`);
            const data = await fileRes.json();
            const items = Array.isArray(data.items) ? data.items : [];
            return new Map(
                items
                    .filter(item => item && item.found && item.code)
                    .map(item => [String(item.code).padStart(4, '0'), item])
            );
        } catch (err) {
            console.warn('Coverage index unavailable:', err);
            return new Map();
        }
    })();

    return coverageIndexPromise;
}

function ensureStockThemeHeader() {
    const headerRow = document.querySelector('#page-tw .data-table thead tr');
    if (!headerRow || headerRow.querySelector('[data-column="themes"]')) return;

    const th = document.createElement('th');
    th.dataset.column = 'themes';
    th.textContent = '題材';
    headerRow.appendChild(th);
}

async function renderTWDashboard(data) {
    if (data['總覽']) renderOverview(data['總覽']);

    const stocks = data['個股籌碼'] || data['個股監控'];
    if (stocks) {
        const coverageByCode = await loadCoverageIndex();
        renderStocks(stocks, coverageByCode);
    }
}

function renderStocks(stocksData, coverageByCode = new Map()) {
    ensureStockThemeHeader();

    const tbody = document.getElementById('stocksTableBody');
    tbody.innerHTML = '';
    const validData = stocksData.filter(item => item['股票代號']);

    validData.forEach((item, index) => {
        const tr = document.createElement('tr');
        tr.className = 'fade-in';
        tr.style.animationDelay = `${index * 0.03}s`;

        const code = String(item['股票代號']).padStart(4, '0');
        const pctChange = item['漲跌幅(%)'];
        const pctClass = pctChange > 0 ? 'text-danger' : (pctChange < 0 ? 'text-success' : '');
        const pctStr = pctChange !== null && pctChange !== undefined ? `${pctChange > 0 ? '+' : ''}${parseFloat(pctChange).toFixed(2)}%` : '-';

        const foreignDaily = item['外資當日(張)'];
        const foreignClass = foreignDaily > 0 ? 'text-danger' : (foreignDaily < 0 ? 'text-success' : '');
        const foreignStr = foreignDaily !== null && foreignDaily !== undefined ? `${foreignDaily > 0 ? '+' : ''}${foreignDaily}` : '-';

        const trustDaily = item['投信當日(張)'];
        const trustClass = trustDaily > 0 ? 'text-danger' : (trustDaily < 0 ? 'text-success' : '');
        const trustStr = trustDaily !== null && trustDaily !== undefined ? `${trustDaily > 0 ? '+' : ''}${trustDaily}` : '-';

        const marginDaily = item['融資增減(張)'];
        const marginStr = marginDaily !== null && marginDaily !== undefined ? marginDaily : '-';

        const ma20 = item['MA20乖離(%)'];
        const ma20Str = ma20 !== null && ma20 !== undefined && !isNaN(ma20)
            ? `${ma20 > 0 ? '+' : ''}${parseFloat(ma20).toFixed(2)}%`
            : '-';

        tr.innerHTML = `
            <td><span class="stock-code">${escapeHtml(code)}</span></td>
            <td><span class="stock-name">${escapeHtml(item['股票名稱'] || '-')}</span></td>
            <td style="font-weight:600;">${item['收盤價'] !== null && item['收盤價'] !== undefined ? escapeHtml(item['收盤價']) : '-'}</td>
            <td class="${pctClass}">${pctStr}</td>
            <td class="${foreignClass}">${foreignStr}</td>
            <td class="${trustClass}">${trustStr}</td>
            <td>${escapeHtml(marginStr)}</td>
            <td>${ma20Str}</td>
            <td>${renderStockThemeTags(coverageByCode.get(code))}</td>
        `;
        tbody.appendChild(tr);
    });
}

function renderStockThemeTags(coverage) {
    const themes = coverage && Array.isArray(coverage.themes) ? coverage.themes.slice(0, 4) : [];
    if (!themes.length) return '<span class="stock-theme-empty">-</span>';

    return `
        <div class="stock-theme-tags">
            ${themes.map(theme => `<span class="stock-theme-tag">${escapeHtml(theme)}</span>`).join('')}
        </div>
    `;
}

function renderDerivativesDashboard(data) {
    const summaryEl = document.getElementById('derivativesSummary');
    const signalsEl = document.getElementById('derivativesSignals');
    const futures = data.futures || {};
    const positioning = data.positioning || {};
    const options = data.options || {};
    const summary = data.summary || {};

    const riskScore = Number(summary.risk_score ?? 0);
    const riskClass = riskScore >= 70 ? 'derivatives-risk-high' : (riskScore >= 45 ? 'derivatives-risk-medium' : 'derivatives-risk-low');

    summaryEl.innerHTML = `
        <div class="derivatives-hero glass-panel ${riskClass}">
            <div>
                <div class="summary-label">風險分數</div>
                <div class="derivatives-score">${Number.isFinite(riskScore) ? riskScore : '-'}</div>
            </div>
            <div>
                <div class="summary-label">市場傾向</div>
                <div class="derivatives-bias">${formatSignal(summary.bias)}</div>
            </div>
            <div>
                <div class="summary-label">資料日期</div>
                <div class="summary-value">${escapeHtml(data.date || '-')}</div>
            </div>
            <div>
                <div class="summary-label">更新時間</div>
                <div class="summary-value">${escapeHtml(data.update_time || '-')}</div>
            </div>
        </div>
        <div class="derivatives-card-grid">
            ${renderDerivativeMetricCard('台指期基差', formatSignedNumber(futures.basis, 2), `${formatSignedNumber(futures.basis_pct, 2)}%`, futures.basis_signal)}
            ${renderDerivativeMetricCard('外資期貨淨部位', formatSignedNumber(positioning.foreign_tx_net_open_interest, 0), '口', positioning.foreign_tx_net_signal)}
            ${renderDerivativeMetricCard('Put / Call Ratio', formatNumber(options.pc_ratio, 2), `5D ${formatNumber(options.pc_ratio_5d_avg, 2)}`, options.pc_ratio_signal)}
        </div>
    `;

    const signals = Array.isArray(summary.signals) ? summary.signals : [];
    signalsEl.innerHTML = `
        <div class="derivatives-signal-panel glass-panel">
            <div class="derivatives-panel-title">訊號拆解</div>
            ${signals.length ? signals.map(renderDerivativeSignal).join('') : '<div class="empty-state">沒有可顯示的期權訊號</div>'}
        </div>
    `;
}

function renderDerivativeMetricCard(title, value, subValue, signal) {
    return `
        <article class="derivatives-metric-card">
            <div class="derivatives-metric-title">${escapeHtml(title)}</div>
            <div class="derivatives-metric-value">${escapeHtml(value)}</div>
            <div class="derivatives-metric-footer">
                <span>${escapeHtml(subValue)}</span>
                <span class="derivatives-signal-chip ${signalClass(signal)}">${formatSignal(signal)}</span>
            </div>
        </article>
    `;
}

function renderDerivativeSignal(item) {
    return `
        <div class="derivatives-signal-row">
            <span>${escapeHtml(item.name || '-')}</span>
            <span class="derivatives-signal-chip ${signalClass(item.signal)}">${formatSignal(item.signal)}</span>
        </div>
    `;
}

function formatSignal(signal) {
    const map = {
        risk_off: '風險偏空',
        risk_on: '風險偏多',
        neutral: '中性',
        bearish: '偏空',
        bullish: '偏多',
        hedging_pressure: '避險壓力',
    };
    return map[signal] || signal || '-';
}

function signalClass(signal) {
    if (['risk_off', 'bearish', 'hedging_pressure'].includes(signal)) return 'signal-bearish';
    if (['risk_on', 'bullish'].includes(signal)) return 'signal-bullish';
    return 'signal-neutral';
}

function formatNumber(value, digits = 2) {
    const num = Number(value);
    if (!Number.isFinite(num)) return '-';
    return num.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function formatSignedNumber(value, digits = 2) {
    const num = Number(value);
    if (!Number.isFinite(num)) return '-';
    const formatted = num.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
    return num > 0 ? `+${formatted}` : formatted;
}

async function loadFile(tab, dir, filename, statusEl) {
    statusEl.textContent = `載入 ${filename}...`;
    try {
        const res = await fetch(`/api/file?dir=${dir}&name=${encodeURIComponent(filename)}`);

        if (tab === 'tw') {
            const data = await res.json();
            await renderTWDashboard(data);
        } else if (tab === 'global') {
            const data = await res.json();
            renderGlobalDashboard(data);
        } else if (tab === 'coverage') {
            const data = await res.json();
            renderCoverageDashboard(data);
        } else if (tab === 'derivatives') {
            const data = await res.json();
            renderDerivativesDashboard(data);
        } else if (tab === 'reports') {
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
