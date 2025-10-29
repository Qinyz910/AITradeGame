// A-Share UI Extension for TradingApp
// This file extends the TradingApp with A-share specific functionality

// Store original methods
const originalInitEventListeners = TradingApp.prototype.initEventListeners;
const originalRenderModels = TradingApp.prototype.renderModels;
const originalSelectModel = TradingApp.prototype.selectModel;
const originalUpdatePositions = TradingApp.prototype.updatePositions;
const originalUpdateTrades = TradingApp.prototype.updateTrades;
const originalUpdateConversations = TradingApp.prototype.updateConversations;
const originalRenderMarketPrices = TradingApp.prototype.renderMarketPrices;
const originalSubmitModel = TradingApp.prototype.submitModel;
const originalShowModal = TradingApp.prototype.showModal;

// Extend constructor
const originalConstructor = TradingApp.prototype.constructor;
TradingApp.prototype.constructor = function() {
    this.currentMarketType = 'crypto';
    this.models = [];
    this.activeMarketTab = 'crypto';
    this.tickerOptions = [];
    originalConstructor.call(this);
};

// Override initEventListeners to add market type and tab listeners
TradingApp.prototype.initEventListeners = function() {
    originalInitEventListeners.call(this);
    
    // Market Type Selection
    document.querySelectorAll('input[name="marketType"]').forEach(radio => {
        radio.addEventListener('change', (e) => this.handleMarketTypeChange(e.target.value));
    });

    // Market Tabs
    document.querySelectorAll('.market-tab').forEach(tab => {
        tab.addEventListener('click', (e) => this.switchMarketTab(e.target.dataset.market));
    });
};

// Handle market type change in modal
TradingApp.prototype.handleMarketTypeChange = function(marketType) {
    this.currentMarketType = marketType;
    const tickerGroup = document.getElementById('tickerSelectGroup');
    
    // Update radio label styling
    document.querySelectorAll('.radio-label').forEach(label => {
        const input = label.querySelector('input');
        if (input && input.value === marketType) {
            label.classList.add('active');
        } else {
            label.classList.remove('active');
        }
    });
    
    if (marketType === 'ashare') {
        tickerGroup.style.display = 'block';
        if (this.tickerOptions.length === 0) {
            this.loadTickerOptions();
        }
    } else {
        tickerGroup.style.display = 'none';
    }
};

// Load ticker options for A-share
TradingApp.prototype.loadTickerOptions = async function() {
    try {
        const response = await fetch('/api/ashare/tickers');
        if (response.ok) {
            const data = await response.json();
            this.tickerOptions = data.tickers || [];
            this.renderTickerOptions();
        } else {
            console.warn('A-share ticker endpoint not available');
            this.tickerOptions = [];
        }
    } catch (error) {
        console.warn('Failed to load A-share tickers:', error);
        this.tickerOptions = [];
    }
};

// Render ticker options in select
TradingApp.prototype.renderTickerOptions = function() {
    const select = document.getElementById('tickerSelect');
    if (!select) return;
    
    if (this.tickerOptions.length === 0) {
        select.innerHTML = '<option value="">暂无可用股票</option>';
        return;
    }
    
    select.innerHTML = this.tickerOptions.map(ticker => 
        `<option value="${ticker.code}">${ticker.code} - ${ticker.name}</option>`
    ).join('');
};

// Switch market tab in sidebar
TradingApp.prototype.switchMarketTab = function(market) {
    this.activeMarketTab = market;
    
    // Update tabs
    document.querySelectorAll('.market-tab').forEach(tab => {
        if (tab.dataset.market === market) {
            tab.classList.add('active');
        } else {
            tab.classList.remove('active');
        }
    });
    
    // Update panels
    document.querySelectorAll('.market-panel').forEach(panel => {
        if (panel.dataset.panel === market) {
            panel.classList.add('active');
        } else {
            panel.classList.remove('active');
        }
    });
    
    // Load market data for the selected tab
    if (market === 'ashare') {
        this.loadAshareMarketData();
    } else {
        this.loadMarketPrices();
    }
};

// Load A-share market data
TradingApp.prototype.loadAshareMarketData = async function() {
    try {
        const response = await fetch('/api/ashare/market');
        if (response.ok) {
            const data = await response.json();
            this.renderAshareMarketPrices(data);
        } else {
            const panel = document.querySelector('.market-panel[data-panel="ashare"]');
            if (panel) {
                panel.innerHTML = '<div class="empty-state">A股数据暂不可用</div>';
            }
        }
    } catch (error) {
        console.error('Failed to load A-share market data:', error);
        const panel = document.querySelector('.market-panel[data-panel="ashare"]');
        if (panel) {
            panel.innerHTML = '<div class="empty-state">加载失败</div>';
        }
    }
};

// Render A-share market prices
TradingApp.prototype.renderAshareMarketPrices = function(data) {
    const panel = document.querySelector('.market-panel[data-panel="ashare"]');
    if (!panel) return;
    
    const items = data.items || data.stocks || data;
    if (!Array.isArray(items) || items.length === 0) {
        panel.innerHTML = '<div class="empty-state">暂无数据</div>';
        return;
    }
    
    panel.innerHTML = items.map(item => {
        const changeClass = (item.change || item.change_pct || 0) >= 0 ? 'positive' : 'negative';
        const changeIcon = (item.change || 0) >= 0 ? '▲' : '▼';
        const status = item.status || 'normal';
        const statusBadge = status === 'suspended' ? ' <span class="status-badge--suspended">停牌</span>' : '';
        
        return `
            <div class="price-item">
                <div>
                    <div class="price-symbol">${item.symbol || item.ticker || item.code}${statusBadge}</div>
                    <div class="price-change ${changeClass}">${changeIcon} ${Math.abs(item.change || item.change_pct || 0).toFixed(2)}%</div>
                </div>
                <div class="price-value">¥${(item.price || item.current_price || 0).toFixed(2)}</div>
            </div>
        `;
    }).join('');
};

// Override renderModels to include market badges
TradingApp.prototype.renderModels = function(models) {
    this.models = models;
    const container = document.getElementById('modelList');

    if (models.length === 0) {
        container.innerHTML = '<div class="empty-state">暂无模型</div>';
        return;
    }

    // Add aggregated view option at the top
    let html = `
        <div class="model-item ${this.isAggregatedView ? 'active' : ''}"
             onclick="app.showAggregatedView()">
            <div class="model-name">
                <i class="bi bi-bar-chart-fill"></i> 聚合视图
            </div>
            <div class="model-info">
                <span>所有模型汇总</span>
            </div>
        </div>
    `;

    // Add individual models
    html += models.map(model => {
        const marketType = model.market_type || 'crypto';
        const marketBadgeClass = marketType === 'crypto' ? 'model-market-badge--crypto' : 'model-market-badge--ashare';
        const marketLabel = marketType === 'crypto' ? '加密' : 'A股';
        const tickers = model.tickers ? model.tickers.split(',').map(t => t.trim()) : [];
        const tickerHtml = tickers.length > 0 
            ? `<div class="model-ticker-list">${tickers.slice(0, 3).map(t => `<span>${t}</span>`).join('')}${tickers.length > 3 ? '<span>...</span>' : ''}</div>`
            : '';
        
        return `
            <div class="model-item ${model.id === this.currentModelId && !this.isAggregatedView ? 'active' : ''}"
                 onclick="app.selectModel(${model.id})">
                <div class="model-name">${model.name}</div>
                <div class="model-info">
                    <span>${model.model_name}</span>
                    <span class="model-delete" onclick="event.stopPropagation(); app.deleteModel(${model.id})">
                        <i class="bi bi-trash"></i>
                    </span>
                </div>
                <div class="model-meta">
                    <span class="model-market-badge ${marketBadgeClass}">${marketLabel}</span>
                    ${tickerHtml}
                </div>
            </div>
        `;
    }).join('');

    container.innerHTML = html;
};

// Override selectModel to update market type
TradingApp.prototype.selectModel = async function(modelId) {
    this.currentModelId = modelId;
    this.isAggregatedView = false;
    
    // Get the selected model's market type
    const model = this.models.find(m => m.id === modelId);
    if (model) {
        this.currentMarketType = model.market_type || 'crypto';
        this.updateTableHeaders();
    }
    
    this.loadModels();
    await this.loadModelData();
    this.showTabsInSingleModelView();
};

// Update table headers based on market type
TradingApp.prototype.updateTableHeaders = function() {
    const positionsHead = document.getElementById('positionsTableHead');
    const tradesHead = document.getElementById('tradesTableHead');
    const isAshare = this.currentMarketType === 'ashare';
    
    if (positionsHead) {
        // Show/hide A-share columns
        const ashareCols = positionsHead.querySelectorAll('.ashare-col');
        ashareCols.forEach(col => {
            col.style.display = isAshare ? '' : 'none';
        });
        
        // Show/hide leverage column (only for crypto)
        const leverageCol = positionsHead.querySelector('.leverage-col');
        if (leverageCol) {
            leverageCol.style.display = isAshare ? 'none' : '';
        }
    }
    
    if (tradesHead) {
        // Update trade status column visibility
        const statusCol = tradesHead.querySelector('.trade-status-col');
        if (statusCol) {
            statusCol.style.display = isAshare ? '' : 'none';
        }
    }
};

// Override submitModel to include market type and tickers
TradingApp.prototype.submitModel = async function() {
    const providerId = document.getElementById('modelProvider').value;
    const modelName = document.getElementById('modelIdentifier').value;
    const displayName = document.getElementById('modelName').value.trim();
    const initialCapital = parseFloat(document.getElementById('initialCapital').value);
    const marketType = document.querySelector('input[name="marketType"]:checked').value;
    
    let tickers = '';
    if (marketType === 'ashare') {
        const select = document.getElementById('tickerSelect');
        const selected = Array.from(select.selectedOptions).map(opt => opt.value);
        tickers = selected.join(',');
        
        if (!tickers) {
            alert('请至少选择一个股票代码');
            return;
        }
    }

    if (!providerId || !modelName || !displayName) {
        alert('请填写所有必填字段');
        return;
    }

    try {
        const response = await fetch('/api/models', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                provider_id: providerId,
                model_name: modelName,
                name: displayName,
                initial_capital: initialCapital,
                market_type: marketType,
                tickers: tickers
            })
        });

        if (response.ok) {
            this.hideModal();
            this.loadModels();
            this.clearForm();
        }
    } catch (error) {
        console.error('Failed to add model:', error);
        alert('添加模型失败');
    }
};

// Override showModal to reset market type
TradingApp.prototype.showModal = async function() {
    await this.loadProviders();
    
    // Reset market type selection
    const cryptoRadio = document.querySelector('input[name="marketType"][value="crypto"]');
    if (cryptoRadio) {
        cryptoRadio.checked = true;
        this.handleMarketTypeChange('crypto');
    }
    
    document.getElementById('addModelModal').classList.add('show');
};

// Override updateConversations to show market type
TradingApp.prototype.updateConversations = function(conversations = []) {
    const container = document.getElementById('conversationsBody');
    if (!container) return;

    if (!Array.isArray(conversations) || conversations.length === 0) {
        container.innerHTML = '<div class="empty-state">暂无对话记录</div>';
        return;
    }

    container.innerHTML = conversations.map(conv => {
        const timestamp = conv.timestamp ? new Date(conv.timestamp.replace(' ', 'T') + 'Z').toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) : '-';
        const marketType = conv.market_type || this.currentMarketType || 'crypto';
        const marketBadgeClass = marketType === 'ashare' ? 'conversation-market-type conversation-market-type--ashare' : 'conversation-market-type conversation-market-type--crypto';
        const marketText = marketType === 'ashare' ? 'A股' : '加密';

        return `
            <div class="conversation-item">
                <div class="conversation-header">
                    <div class="conversation-time">${timestamp}</div>
                    <span class="${marketBadgeClass}">${marketText}</span>
                </div>
                <div class="conversation-content">${conv.ai_response || ''}</div>
            </div>
        `;
    }).join('');
};

// Override updatePositions to handle A-share columns
TradingApp.prototype.updatePositions = function(positions = [], isAggregated = false) {
    const tbody = document.getElementById('positionsBody');
    if (!tbody) return;

    const isAshare = this.currentMarketType === 'ashare';
    const colCount = isAshare ? 11 : 7;
    const currencySymbol = isAshare ? '¥' : '$'
;

    if (!Array.isArray(positions) || positions.length === 0) {
        const emptyText = isAggregated ? '聚合视图暂无持仓' : '暂无持仓';
        tbody.innerHTML = `<tr><td colspan="${colCount}" class="empty-state">${emptyText}</td></tr>`;
        return;
    }

    tbody.innerHTML = positions.map(pos => {
        const sideClass = pos.side === 'long' ? 'badge-long' : 'badge-short';
        const sideText = pos.side === 'long' ? '做多' : '做空';
        
        const quantity = typeof pos.quantity === 'number' 
            ? pos.quantity.toFixed(isAshare ? 0 : 4)
            : (pos.quantity || '-');
        
        const avgPrice = typeof pos.avg_price === 'number'
            ? `${currencySymbol}${pos.avg_price.toFixed(2)}`
            : '-';
        
        const currentPrice = typeof pos.current_price === 'number'
            ? `${currencySymbol}${pos.current_price.toFixed(2)}`
            : '-';

        let pnlDisplay = '-';
        let pnlClass = '';
        if (pos.pnl !== undefined && pos.pnl !== null) {
            const pnlValue = Number(pos.pnl);
            if (!isNaN(pnlValue)) {
                pnlDisplay = this.formatPnl(pnlValue, true);
                pnlClass = this.getPnlClass(pnlValue, true);
            }
        }

        const leverageCell = isAshare ? '' : `<td>${pos.leverage || 1}x</td>`;
        
        const ashareCells = isAshare ? `
            <td>${pos.board || pos.market_board || '-'}</td>
            <td>${this.renderStatusBadge(pos.status || pos.trading_status, pos.st_flag || pos.is_st)}</td>
            <td>${this.formatPrice(pos.limit_up)}</td>
            <td>${this.formatPrice(pos.limit_down)}</td>
            <td>${this.formatDate(pos.next_sellable_date)}</td>
        ` : '';

        return `
            <tr>
                <td><strong>${pos.coin || pos.ticker || pos.symbol || '-'}</strong></td>
                <td><span class="badge ${sideClass}">${sideText}</span></td>
                <td>${quantity}</td>
                <td>${avgPrice}</td>
                <td>${currentPrice}</td>
                ${leverageCell}
                ${ashareCells}
                <td class="${pnlClass}"><strong>${pnlDisplay}</strong></td>
            </tr>
        `;
    }).join('');
};

// Helper: render status badge for A-share
TradingApp.prototype.renderStatusBadge = function(status, stFlag) {
    if (stFlag === true || stFlag === 'true' || (typeof stFlag === 'string' && stFlag.toUpperCase().includes('ST'))) {
        return '<span class="status-badge status-badge--st">*ST</span>';
    }
    if (!status) {
        return '<span class="status-badge status-badge--normal">正常</span>';
    }
    const normalized = status.toString().toLowerCase();
    if (normalized.includes('suspend') || normalized.includes('停牌')) {
        return '<span class="status-badge status-badge--suspended">停牌</span>';
    }
    if (normalized.includes('normal') || normalized.includes('交易') || normalized.includes('active')) {
        return '<span class="status-badge status-badge--normal">正常</span>';
    }
    return `<span class="status-badge">${status}</span>`;
};

// Helper: format price with currency
TradingApp.prototype.formatPrice = function(value) {
    if (value === null || value === undefined || value === '') {
        return '-';
    }
    const numeric = Number(value);
    if (isNaN(numeric)) {
        return value;
    }
    const symbol = this.currentMarketType === 'ashare' ? '¥' : '$'
;
    return `${symbol}${numeric.toFixed(2)}`;
};

// Helper: format date
TradingApp.prototype.formatDate = function(value) {
    if (!value) return '-';
    const date = new Date(value);
    if (isNaN(date.getTime())) {
        return value;
    }
    return date.toLocaleDateString('zh-CN', { timeZone: 'Asia/Shanghai' });
};

// Override updateTrades to handle A-share trades
TradingApp.prototype.updateTrades = function(trades = []) {
    const tbody = document.getElementById('tradesBody');
    if (!tbody) return;

    const isAshare = this.currentMarketType === 'ashare';
    const colCount = 8;

    if (!Array.isArray(trades) || trades.length === 0) {
        tbody.innerHTML = `<tr><td colspan="${colCount}" class="empty-state">暂无交易记录</td></tr>`;
        return;
    }

    tbody.innerHTML = trades.map(trade => {
        const signalMap = {
            'buy_to_enter': { badge: 'badge-buy', text: '开多' },
            'sell_to_enter': { badge: 'badge-sell', text: '开空' },
            'close_position': { badge: 'badge-close', text: '平仓' }
        };
        const signal = signalMap[trade.signal] || { badge: '', text: trade.signal || '-' };

        const pnlValue = Number(trade.pnl);
        const hasPnl = !isNaN(pnlValue);
        const pnlDisplay = hasPnl ? this.formatPnl(pnlValue, true) : '-';
        const pnlClass = hasPnl ? this.getPnlClass(pnlValue, true) : '';

        const quantity = typeof trade.quantity === 'number'
            ? trade.quantity.toFixed(isAshare ? 0 : 4)
            : (trade.quantity || '-');

        const price = this.formatPrice(trade.price);

        const statusInfo = this.renderTradeStatus(trade);
        const statusCell = `<td class="trade-status-col" style="${isAshare ? '' : 'display:none;'}">${statusInfo.badge}${isAshare && statusInfo.message ? `<div class="trade-error-message">${statusInfo.message}</div>` : ''}</td>`;

        const operationMessage = !isAshare && statusInfo.message
            ? `<div class="trade-error-message">${statusInfo.message}</div>`
            : '';

        const timestamp = trade.timestamp ? new Date(trade.timestamp.replace(' ', 'T') + 'Z').toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) : '-';

        return `
            <tr>
                <td>${timestamp}</td>
                <td><strong>${trade.coin || trade.ticker || trade.symbol || '-'}</strong></td>
                <td><span class="badge ${signal.badge}">${signal.text}</span>${operationMessage}</td>
                ${statusCell}
                <td>${quantity}</td>
                <td>${price}</td>
                <td class="${pnlClass}">${pnlDisplay}</td>
                <td>${this.renderTradeFees(trade, isAshare)}</td>
            </tr>
        `;
    }).join('');
};

// Helper: render trade status
TradingApp.prototype.renderTradeStatus = function(trade) {
    const status = trade.status || trade.execution_status || trade.result;
    const message = trade.message || trade.error || trade.reason || trade.note || '';
    
    if (!status) {
        return { badge: '<span class="status-badge status-badge--normal">已成交</span>', message };
    }

    const normalized = status.toString().toLowerCase();
    if (normalized.includes('reject') || normalized.includes('拒') || normalized.includes('fail')) {
        return {
            badge: '<span class="status-badge status-badge--suspended">已拒绝</span>',
            message: message || trade.error_message || '因交易限制未能执行'
        };
    }
    if (normalized.includes('pending')) {
        return { badge: '<span class="status-badge">挂单中</span>', message };
    }
    if (normalized.includes('fill') || normalized.includes('complete') || normalized.includes('done')) {
        return { badge: '<span class="status-badge status-badge--normal">已成交</span>', message };
    }
    return { badge: `<span class="status-badge">${status}</span>`, message };
};

// Helper: render trade fees
TradingApp.prototype.renderTradeFees = function(trade, isAshare) {
    if (!isAshare) {
        const feeValue = Number(trade.fee);
        if (!isNaN(feeValue)) {
            return this.formatPrice(feeValue);
        }
        return trade.fee || '-';
    }

    const breakdown = trade.fee_breakdown || trade.fees || {};
    const commission = breakdown.commission ?? breakdown.broker ?? trade.commission_fee ?? trade.commission;
    const transfer = breakdown.transfer ?? breakdown.transfer_fee ?? trade.transfer_fee;
    const stamp = breakdown.stamp ?? breakdown.stamp_duty ?? trade.stamp_duty;
    
    const items = [
        commission !== undefined ? { label: '佣金', value: commission } : null,
        transfer !== undefined ? { label: '过户费', value: transfer } : null,
        stamp !== undefined ? { label: '印花税', value: stamp } : null
    ].filter(Boolean);

    if (items.length === 0) {
        const fallback = Number(trade.fee);
        return !isNaN(fallback) ? this.formatPrice(fallback) : (trade.fee || '-');
    }

    return `
        <div class="fee-breakdown">
            ${items.map(item => `
                <div class="fee-breakdown-item">
                    <span>${item.label}</span>
                    <span>${this.formatPrice(item.value)}</span>
                </div>
            `).join('')}
        </div>
    `;
};

// Override renderMarketPrices to use the crypto panel
TradingApp.prototype.renderMarketPrices = function(prices) {
    const panel = document.querySelector('.market-panel[data-panel="crypto"]');
    if (!panel) {
        // Fallback to original behavior if panel doesn't exist
        const container = document.getElementById('marketPrices');
        if (!container) return;
        
        container.innerHTML = Object.entries(prices).map(([coin, data]) => {
            const changeClass = data.change_24h >= 0 ? 'positive' : 'negative';
            const changeIcon = data.change_24h >= 0 ? '▲' : '▼';

            return `
                <div class="price-item">
                    <div>
                        <div class="price-symbol">${coin}</div>
                        <div class="price-change ${changeClass}">${changeIcon} ${Math.abs(data.change_24h).toFixed(2)}%</div>
                    </div>
                    <div class="price-value">${data.price.toFixed(2)}</div>
                </div>
            `;
        }).join('');
        return;
    }

    panel.innerHTML = Object.entries(prices).map(([coin, data]) => {
        const changeClass = data.change_24h >= 0 ? 'positive' : 'negative';
        const changeIcon = data.change_24h >= 0 ? '▲' : '▼';

        return `
            <div class="price-item">
                <div>
                    <div class="price-symbol">${coin}</div>
                    <div class="price-change ${changeClass}">${changeIcon} ${Math.abs(data.change_24h).toFixed(2)}%</div>
                </div>
                <div class="price-value">${data.price.toFixed(2)}</div>
            </div>
        `;
    }).join('');
};

// Initialize extension when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        console.log('[Info] A-share extension loaded');
    });
} else {
    console.log('[Info] A-share extension loaded');
}
