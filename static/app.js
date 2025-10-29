class TradingApp {
    constructor() {
        this.currentModelId = null;
        this.isAggregatedView = false;
        this.models = [];
        this.providers = [];
        this.currentMarketType = 'a_share';
        this.chart = null;
        this.refreshIntervals = {
            market: null,
            portfolio: null,
            trades: null
        };
        this.marketStatus = null;
        this.watchlist = [];
        this.instrumentOptions = [];
        this.currencyCode = 'CNY';
        this.currencySymbol = '¥';
        this.defaultWatchlist = ['600519.SH', '600036.SH', '000001.SZ', '300750.SZ'];
        this.isChinese = this.detectLanguage();
        this.init();
    }

    detectLanguage() {
        const lang = document.documentElement.lang || navigator.language || navigator.userLanguage;
        return lang.toLowerCase().includes('zh');
    }

    formatCurrency(value, { currencySymbol } = {}) {
        const symbol = currencySymbol || this.currencySymbol || '¥';
        const numeric = Number(value);
        if (Number.isNaN(numeric)) {
            return `${symbol}0.00`;
        }
        const sign = numeric < 0 ? '-' : '';
        return `${sign}${symbol}${Math.abs(numeric).toFixed(2)}`;
    }

    formatPnl(value, { currencySymbol } = {}) {
        const symbol = currencySymbol || this.currencySymbol || '¥';
        const numeric = Number(value) || 0;
        const base = `${symbol}${Math.abs(numeric).toFixed(2)}`;
        if (numeric === 0) {
            return `${symbol}0.00`;
        }
        return numeric > 0 ? `+${base}` : `-${base}`;
    }

    getPnlClass(value) {
        const numeric = Number(value) || 0;
        if (numeric > 0) {
            return 'positive';
        }
        if (numeric < 0) {
            return 'negative';
        }
        return '';
    }

    getCurrencySymbol(code = 'CNY') {
        const normalized = String(code || 'CNY').toUpperCase();
        switch (normalized) {
            case 'CNY':
            case 'RMB':
                return '¥';
            case 'USD':
                return '$';
            case 'HKD':
                return 'HK$';
            case 'EUR':
                return '€';
            case 'GBP':
                return '£';
            case 'JPY':
                return '¥';
            default:
                return `${normalized} `;
        }
    }

    formatQuantity(value) {
        if (value === null || value === undefined) {
            return '-';
        }
        const numeric = Number(value);
        if (Number.isNaN(numeric)) {
            return value;
        }
        return numeric.toLocaleString('zh-CN', { maximumFractionDigits: 0 });
    }

    formatPriceValue(value, currencySymbol = this.currencySymbol) {
        if (value === null || value === undefined || value === '') {
            return '-';
        }
        const numeric = Number(value);
        if (Number.isNaN(numeric)) {
            return value;
        }
        return `${currencySymbol}${numeric.toFixed(2)}`;
    }

    formatDate(value) {
        if (!value) {
            return '-';
        }
        if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
            return value;
        }
        const parsed = new Date(value);
        if (!Number.isNaN(parsed.getTime())) {
            return parsed.toLocaleDateString('zh-CN', { timeZone: 'Asia/Shanghai' });
        }
        const fallback = new Date(String(value).replace(' ', 'T') + 'Z');
        if (!Number.isNaN(fallback.getTime())) {
            return fallback.toLocaleDateString('zh-CN', { timeZone: 'Asia/Shanghai' });
        }
        return value;
    }

    formatTimestampToDatetime(value) {
        if (!value) {
            return '-';
        }
        let parsed = new Date(value);
        if (Number.isNaN(parsed.getTime())) {
            parsed = new Date(String(value).replace(' ', 'T') + 'Z');
        }
        if (Number.isNaN(parsed.getTime())) {
            return value;
        }
        return parsed.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' });
    }

    formatTimestampToTime(value) {
        if (!value) {
            return '-';
        }
        let parsed = new Date(value);
        if (Number.isNaN(parsed.getTime())) {
            parsed = new Date(String(value).replace(' ', 'T') + 'Z');
        }
        if (Number.isNaN(parsed.getTime())) {
            return '-';
        }
        return parsed.toLocaleTimeString('zh-CN', {
            timeZone: 'Asia/Shanghai',
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    renderPositionStatus(pos = {}) {
        const badges = [];
        const isST = Boolean(pos.is_st) || Boolean(pos.st_flag);
        const suspended = Boolean(pos.suspension) || Boolean(pos.is_suspended);
        if (isST) {
            badges.push('<span class="status-badge status-badge--st">*ST</span>');
        }
        if (suspended) {
            badges.push('<span class="status-badge status-badge--suspended">停牌</span>');
        } else {
            badges.push('<span class="status-badge status-badge--normal">正常</span>');
        }
        if (pos.t1_locked) {
            badges.push('<span class="status-badge status-badge--lock">T+1</span>');
        }
        return badges.join('');
    }

    renderTradeStatus(trade = {}) {
        const status = (trade.status || trade.execution_status || trade.result || '').toString().toLowerCase();
        const message = trade.message || trade.error || trade.reason || trade.note || '';
        if (!status) {
            return { badge: '<span class="status-badge status-badge--normal">已成交</span>', message };
        }
        if (status.includes('reject') || status.includes('拒') || status.includes('fail')) {
            return {
                badge: '<span class="status-badge status-badge--suspended">已拒绝</span>',
                message: message || trade.error_message || '因交易限制未能执行'
            };
        }
        if (status.includes('pending')) {
            return { badge: '<span class="status-badge">挂单中</span>', message };
        }
        if (status.includes('fill') || status.includes('complete') || status.includes('done')) {
            return { badge: '<span class="status-badge status-badge--normal">已成交</span>', message };
        }
        return { badge: `<span class="status-badge">${trade.status || trade.execution_status || '未知'}</span>`, message };
    }

    renderTradeFees(trade = {}, { currencySymbol } = {}) {
        const symbol = currencySymbol || this.currencySymbol || '¥';
        const breakdown = trade.fee_breakdown || trade.fees || {};
        const commission = breakdown.commission ?? breakdown.broker ?? trade.commission_fee ?? trade.commission;
        const transfer = breakdown.transfer ?? breakdown.transfer_fee ?? trade.transfer_fee;
        const stamp = breakdown.stamp ?? breakdown.stamp_duty ?? trade.stamp_duty;

        const items = [
            commission !== undefined ? { label: '佣金', value: commission } : null,
            transfer !== undefined ? { label: '过户费', value: transfer } : null,
            stamp !== undefined ? { label: '印花税', value: stamp } : null
        ].filter(Boolean);

        if (!items.length) {
            const fallback = Number(trade.fee);
            if (Number.isNaN(fallback) || fallback === 0) {
                return '-';
            }
            return this.formatPriceValue(fallback, symbol);
        }

        return `
            <div class="fee-breakdown">
                ${items.map(item => `
                    <div class="fee-breakdown-item">
                        <span>${item.label}</span>
                        <span>${this.formatPriceValue(item.value, symbol)}</span>
                    </div>
                `).join('')}
            </div>
        `;
    }

    init() {
        this.initEventListeners();
        this.loadModels();
        this.loadMarketOverview();
        this.startRefreshCycles();
        this.preloadInstrumentOptions();
        setTimeout(() => this.checkForUpdates(true), 3000);
    }

    initEventListeners() {
        document.getElementById('checkUpdateBtn').addEventListener('click', () => this.checkForUpdates());
        document.getElementById('closeUpdateModalBtn').addEventListener('click', () => this.hideUpdateModal());
        document.getElementById('dismissUpdateBtn').addEventListener('click', () => this.dismissUpdate());

        document.getElementById('addApiProviderBtn').addEventListener('click', () => this.showApiProviderModal());
        document.getElementById('closeApiProviderModalBtn').addEventListener('click', () => this.hideApiProviderModal());
        document.getElementById('cancelApiProviderBtn').addEventListener('click', () => this.hideApiProviderModal());
        document.getElementById('saveApiProviderBtn').addEventListener('click', () => this.saveApiProvider());
        document.getElementById('fetchModelsBtn').addEventListener('click', () => this.fetchModels());

        document.getElementById('addModelBtn').addEventListener('click', () => this.showModal());
        document.getElementById('closeModalBtn').addEventListener('click', () => this.hideModal());
        document.getElementById('cancelBtn').addEventListener('click', () => this.hideModal());
        document.getElementById('submitBtn').addEventListener('click', () => this.submitModel());
        document.getElementById('modelProvider').addEventListener('change', (e) => this.updateModelOptions(e.target.value));
        const refreshInstrumentBtn = document.getElementById('refreshInstrumentBtn');
        if (refreshInstrumentBtn) {
            refreshInstrumentBtn.addEventListener('click', () => this.loadInstrumentOptions(true));
        }

        document.getElementById('refreshBtn').addEventListener('click', () => this.refresh());

        document.getElementById('settingsBtn').addEventListener('click', () => this.showSettingsModal());
        document.getElementById('closeSettingsModalBtn').addEventListener('click', () => this.hideSettingsModal());
        document.getElementById('cancelSettingsBtn').addEventListener('click', () => this.hideSettingsModal());
        document.getElementById('saveSettingsBtn').addEventListener('click', () => this.saveSettings());

        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.switchTab(e.target.dataset.tab));
        });
    }

    async loadModels() {
        try {
            const response = await fetch('/api/models');
            const data = await response.json();
            const models = Array.isArray(data) ? data : [];
            this.models = models;
            this.renderModels(models);
            this.updateWatchlist(models);
            this.loadMarketOverview();

            if (models.length > 0 && !this.currentModelId && !this.isAggregatedView) {
                await this.showAggregatedView();
            } else if (this.currentModelId && !this.isAggregatedView) {
                await this.loadModelData();
            }
        } catch (error) {
            console.error('Failed to load models:', error);
        }
    }

    renderModels(models) {
        const container = document.getElementById('modelList');

        if (!models || models.length === 0) {
            container.innerHTML = '<div class="empty-state">暂无模型</div>';
            return;
        }

        let html = `
            <div class="model-item ${this.isAggregatedView ? 'active' : ''}"
                 onclick="app.showAggregatedView()">
                <div class="model-name">
                    <i class="bi bi-collection"></i> 全部模型汇总
                </div>
                <div class="model-info">
                    <span>${models.length} 个模型</span>
                </div>
            </div>
        `;

        html += models.map(model => {
            const isActive = model.id === this.currentModelId && !this.isAggregatedView;
            const providerLabel = model.provider_name || model.model_name || '—';
            const instrumentList = Array.isArray(model.instruments)
                ? model.instruments
                : (typeof model.instrument_list === 'string' ? model.instrument_list.split(',') : []);
            const instruments = instrumentList
                .map(item => String(item).trim().toUpperCase())
                .filter((item, index, arr) => item && arr.indexOf(item) === index);
            const badges = instruments.slice(0, 4).map(item => `<span class="model-ticker">${item}</span>`).join('');
            const moreTag = instruments.length > 4 ? `<span class="model-ticker">+${instruments.length - 4}</span>` : '';
            const instrumentsHtml = instruments.length
                ? `<div class="model-meta">${badges}${moreTag}</div>`
                : '<div class="model-meta muted">未配置股票池</div>';

            return `
                <div class="model-item ${isActive ? 'active' : ''}"
                     onclick="app.selectModel(${model.id})">
                    <div class="model-name">${model.name}</div>
                    <div class="model-info">
                        <span>${providerLabel}</span>
                        <span class="model-delete" onclick="event.stopPropagation(); app.deleteModel(${model.id})">
                            <i class="bi bi-trash"></i>
                        </span>
                    </div>
                    ${instrumentsHtml}
                </div>
            `;
        }).join('');

        container.innerHTML = html;
    }

    async showAggregatedView() {
        this.isAggregatedView = true;
        this.currentModelId = null;
        this.currentMarketType = 'a_share';
        this.currencyCode = 'CNY';
        this.currencySymbol = this.getCurrencySymbol(this.currencyCode);
        this.loadModels();
        await this.loadAggregatedData();
        this.hideTabsInAggregatedView();
    }

    async selectModel(modelId) {
        this.currentModelId = modelId;
        this.isAggregatedView = false;

        const model = this.models.find(item => item.id === modelId);
        if (model) {
            this.currentMarketType = (model.market_type || 'a_share').toLowerCase();
            const currencyCode = (model.cash_currency || (this.currentMarketType === 'a_share' ? 'CNY' : 'USD')).toUpperCase();
            this.currencyCode = currencyCode;
            this.currencySymbol = this.getCurrencySymbol(currencyCode);
        } else {
            this.currentMarketType = 'a_share';
            this.currencyCode = 'CNY';
            this.currencySymbol = this.getCurrencySymbol(this.currencyCode);
        }

        this.loadModels();
        await this.loadModelData();
        this.showTabsInSingleModelView();
    }

    async loadModelData() {
        if (!this.currentModelId) return;

        try {
            const [portfolioResponse, trades, conversations] = await Promise.all([
                fetch(`/api/models/${this.currentModelId}/portfolio`).then(r => r.json()),
                fetch(`/api/models/${this.currentModelId}/trades?limit=50`).then(r => r.json()),
                fetch(`/api/models/${this.currentModelId}/conversations?limit=20`).then(r => r.json())
            ]);

            const portfolio = portfolioResponse?.portfolio || {};
            const history = portfolioResponse?.account_value_history || [];

            this.currentMarketType = (portfolio.market_type || 'a_share').toLowerCase();
            const currencyCode = (portfolio.cash_currency || (this.currentMarketType === 'a_share' ? 'CNY' : 'USD')).toUpperCase();
            this.currencyCode = currencyCode;
            this.currencySymbol = this.getCurrencySymbol(currencyCode);

            this.updateStats(portfolio, { currencyCode });
            this.updateSingleModelChart(history, portfolio.total_value);
            this.updatePositions(portfolio.positions || [], { currencyCode });
            this.updateTrades(trades || [], { currencyCode });
            this.updateConversations(conversations || []);
        } catch (error) {
            console.error('Failed to load model data:', error);
        }
    }

    async loadAggregatedData() {
        try {
            const response = await fetch('/api/aggregated/portfolio');
            const data = await response.json();

            this.currentMarketType = 'a_share';
            this.currencyCode = 'CNY';
            this.currencySymbol = this.getCurrencySymbol(this.currencyCode);

            this.updateStats(data.portfolio || {}, { isAggregated: true, currencyCode: this.currencyCode });
            this.updateMultiModelChart(data.chart_data || []);
            this.hideTabsInAggregatedView();
        } catch (error) {
            console.error('Failed to load aggregated data:', error);
        }
    }

    hideTabsInAggregatedView() {
        const contentCard = document.querySelector('.content-card .card-tabs')?.parentElement;
        if (contentCard) {
            contentCard.style.display = 'none';
        }
    }

    showTabsInSingleModelView() {
        const contentCard = document.querySelector('.content-card .card-tabs')?.parentElement;
        if (contentCard) {
            contentCard.style.display = 'block';
        }
    }

    updateStats(portfolio = {}, options = {}) {
        const currencyCode = (options.currencyCode || this.currencyCode || 'CNY').toUpperCase();
        this.currencyCode = currencyCode;
        this.currencySymbol = this.getCurrencySymbol(currencyCode);

        const stats = [
            {
                value: portfolio.total_value || 0,
                formatter: (value) => this.formatCurrency(value, { currencySymbol: this.currencySymbol })
            },
            {
                value: portfolio.cash || 0,
                formatter: (value) => this.formatCurrency(value, { currencySymbol: this.currencySymbol })
            },
            {
                value: portfolio.realized_pnl || 0,
                formatter: (value) => this.formatPnl(value, { currencySymbol: this.currencySymbol }),
                className: (value) => this.getPnlClass(value)
            },
            {
                value: portfolio.unrealized_pnl || 0,
                formatter: (value) => this.formatPnl(value, { currencySymbol: this.currencySymbol }),
                className: (value) => this.getPnlClass(value)
            }
        ];

        document.querySelectorAll('.stat-value').forEach((el, index) => {
            const config = stats[index];
            if (!config) {
                return;
            }
            el.textContent = config.formatter(config.value);
            const className = config.className ? config.className(config.value) : '';
            el.className = className ? `stat-value ${className}` : 'stat-value';
        });
    }

    updateSingleModelChart(history = [], currentValue) {
        const chartDom = document.getElementById('accountChart');
        if (!chartDom) {
            return;
        }

        if (this.chart) {
            this.chart.dispose();
        }

        this.chart = echarts.init(chartDom);
        window.addEventListener('resize', () => {
            if (this.chart) {
                this.chart.resize();
            }
        });

        const records = Array.isArray(history) ? [...history] : [];
        const data = records.reverse().map(h => ({
            time: this.formatTimestampToTime(h.timestamp),
            value: Number(h.total_value) || 0
        }));

        if (currentValue !== undefined && currentValue !== null) {
            data.push({
                time: this.formatTimestampToTime(new Date().toISOString()),
                value: Number(currentValue) || 0
            });
        }

        const currencySymbol = this.currencySymbol;

        const option = {
            grid: {
                left: '60',
                right: '20',
                bottom: '40',
                top: '20',
                containLabel: false
            },
            xAxis: {
                type: 'category',
                boundaryGap: false,
                data: data.map(d => d.time),
                axisLine: { lineStyle: { color: '#e5e6eb' } },
                axisLabel: { color: '#86909c', fontSize: 11 }
            },
            yAxis: {
                type: 'value',
                scale: true,
                axisLine: { lineStyle: { color: '#e5e6eb' } },
                axisLabel: {
                    color: '#86909c',
                    fontSize: 11,
                    formatter: (value) => `${currencySymbol}${Number(value).toLocaleString()}`
                },
                splitLine: { lineStyle: { color: '#f2f3f5' } }
            },
            series: [{
                type: 'line',
                data: data.map(d => d.value),
                smooth: true,
                symbol: 'none',
                lineStyle: { color: '#3370ff', width: 2 },
                areaStyle: {
                    color: {
                        type: 'linear',
                        x: 0, y: 0, x2: 0, y2: 1,
                        colorStops: [
                            { offset: 0, color: 'rgba(51, 112, 255, 0.2)' },
                            { offset: 1, color: 'rgba(51, 112, 255, 0)' }
                        ]
                    }
                }
            }],
            tooltip: {
                trigger: 'axis',
                backgroundColor: 'rgba(255, 255, 255, 0.95)',
                borderColor: '#e5e6eb',
                borderWidth: 1,
                textStyle: { color: '#1d2129' },
                formatter: (params) => {
                    const value = Number(params[0].value) || 0;
                    return `${params[0].axisValue}<br/>账户价值: ${currencySymbol}${value.toFixed(2)}`;
                }
            }
        };

        this.chart.setOption(option);

        setTimeout(() => {
            if (this.chart) {
                this.chart.resize();
            }
        }, 100);
    }

    updateMultiModelChart(chartData = []) {
        const chartDom = document.getElementById('accountChart');
        if (!chartDom) {
            return;
        }

        if (this.chart) {
            this.chart.dispose();
        }

        this.chart = echarts.init(chartDom);
        window.addEventListener('resize', () => {
            if (this.chart) {
                this.chart.resize();
            }
        });

        if (!chartData || chartData.length === 0) {
            this.chart.setOption({
                title: {
                    text: '暂无模型数据',
                    left: 'center',
                    top: 'center',
                    textStyle: { color: '#86909c', fontSize: 14 }
                },
                xAxis: { show: false },
                yAxis: { show: false },
                series: []
            });
            return;
        }

        const currencySymbol = this.currencySymbol;

        const colors = [
            '#3370ff', '#ff6b35', '#00b96b', '#722ed1', '#fa8c16',
            '#eb2f96', '#13c2c2', '#faad14', '#f5222d', '#52c41a'
        ];

        const allTimestamps = new Set();
        chartData.forEach(model => {
            (model.data || []).forEach(point => {
                if (point.timestamp) {
                    allTimestamps.add(point.timestamp);
                }
            });
        });

        const timeAxis = Array.from(allTimestamps).sort((a, b) => {
            const timeA = new Date(a.replace(' ', 'T') + 'Z').getTime();
            const timeB = new Date(b.replace(' ', 'T') + 'Z').getTime();
            return timeA - timeB;
        });

        const formattedTimeAxis = timeAxis.map(timestamp => this.formatTimestampToTime(timestamp));

        const series = chartData.map((model, index) => {
            const color = colors[index % colors.length];
            const dataPoints = timeAxis.map(time => {
                const point = (model.data || []).find(p => p.timestamp === time);
                return point ? point.value : null;
            });

            return {
                name: model.model_name,
                type: 'line',
                data: dataPoints,
                smooth: true,
                symbol: 'circle',
                symbolSize: 4,
                lineStyle: { color: color, width: 2 },
                itemStyle: { color: color },
                connectNulls: true
            };
        });

        const option = {
            title: {
                text: '模型表现对比',
                left: 'center',
                top: 10,
                textStyle: { color: '#1d2129', fontSize: 16, fontWeight: 'normal' }
            },
            grid: {
                left: '60',
                right: '20',
                bottom: '80',
                top: '50',
                containLabel: false
            },
            xAxis: {
                type: 'category',
                boundaryGap: false,
                data: formattedTimeAxis,
                axisLine: { lineStyle: { color: '#e5e6eb' } },
                axisLabel: { color: '#86909c', fontSize: 11, rotate: 45 }
            },
            yAxis: {
                type: 'value',
                scale: true,
                axisLine: { lineStyle: { color: '#e5e6eb' } },
                axisLabel: {
                    color: '#86909c',
                    fontSize: 11,
                    formatter: (value) => `${currencySymbol}${Number(value).toLocaleString()}`
                },
                splitLine: { lineStyle: { color: '#f2f3f5' } }
            },
            legend: {
                data: chartData.map(model => model.model_name),
                bottom: 10,
                itemGap: 20,
                textStyle: { color: '#1d2129', fontSize: 12 }
            },
            series,
            tooltip: {
                trigger: 'axis',
                backgroundColor: 'rgba(255, 255, 255, 0.95)',
                borderColor: '#e5e6eb',
                borderWidth: 1,
                textStyle: { color: '#1d2129' },
                formatter: (params) => {
                    let result = `${params[0].axisValue}<br/>`;
                    params.forEach(param => {
                        if (param.value !== null) {
                            const numeric = Number(param.value) || 0;
                            result += `${param.marker}${param.seriesName}: ${currencySymbol}${numeric.toFixed(2)}<br/>`;
                        }
                    });
                    return result;
                }
            }
        };

        this.chart.setOption(option);

        setTimeout(() => {
            if (this.chart) {
                this.chart.resize();
            }
        }, 100);
    }

    updatePositions(positions = [], options = {}) {
        const tbody = document.getElementById('positionsBody');
        if (!tbody) {
            return;
        }

        const currencySymbol = this.getCurrencySymbol(options.currencyCode || this.currencyCode);

        if (!Array.isArray(positions) || positions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="10" class="empty-state">暂无持仓</td></tr>';
            return;
        }

        tbody.innerHTML = positions.map(pos => {
            const symbol = this.getInstrumentCode(pos);
            const board = pos.board || pos.market_board || '-';
            const quantity = this.formatQuantity(pos.quantity);
            const avgPrice = this.formatPriceValue(pos.avg_price, currencySymbol);
            const currentPrice = this.formatPriceValue(pos.current_price, currencySymbol);
            const limitUp = this.formatPriceValue(pos.limit_up_price ?? pos.limit_up, currencySymbol);
            const limitDown = this.formatPriceValue(pos.limit_down_price ?? pos.limit_down, currencySymbol);
            const nextSellable = this.formatDate(pos.next_sellable_date);
            const statusHtml = this.renderPositionStatus(pos);
            const pnlValue = Number(pos.pnl) || 0;
            const pnlDisplay = this.formatPnl(pnlValue, { currencySymbol });
            const pnlClass = this.getPnlClass(pnlValue);

            return `
                <tr>
                    <td><strong>${symbol}</strong></td>
                    <td>${board || '-'}</td>
                    <td>${quantity}</td>
                    <td>${avgPrice}</td>
                    <td>${currentPrice}</td>
                    <td>${limitUp}</td>
                    <td>${limitDown}</td>
                    <td>${nextSellable}</td>
                    <td>${statusHtml}</td>
                    <td class="${pnlClass}"><strong>${pnlDisplay}</strong></td>
                </tr>
            `;
        }).join('');
    }

    updateTrades(trades = [], options = {}) {
        const tbody = document.getElementById('tradesBody');
        if (!tbody) {
            return;
        }

        const currencySymbol = this.getCurrencySymbol(options.currencyCode || this.currencyCode);

        if (!Array.isArray(trades) || trades.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="empty-state">暂无交易记录</td></tr>';
            return;
        }

        tbody.innerHTML = trades.map(trade => {
            const signalMap = {
                buy_to_enter: { badge: 'badge-buy', text: '买入' },
                sell_to_enter: { badge: 'badge-sell', text: '卖出' },
                close_position: { badge: 'badge-close', text: '卖出平仓' }
            };
            const signal = signalMap[trade.signal] || { badge: '', text: trade.signal || '—' };
            const pnlValue = Number(trade.pnl) || 0;
            const pnlDisplay = this.formatPnl(pnlValue, { currencySymbol });
            const pnlClass = this.getPnlClass(pnlValue);
            const statusInfo = this.renderTradeStatus(trade);
            const feesHtml = this.renderTradeFees(trade, { currencySymbol });

            return `
                <tr>
                    <td>${this.formatTimestampToDatetime(trade.timestamp)}</td>
                    <td><strong>${this.getInstrumentCode(trade)}</strong></td>
                    <td><span class="badge ${signal.badge}">${signal.text}</span></td>
                    <td>${statusInfo.badge}${statusInfo.message ? `<div class="trade-error-message">${statusInfo.message}</div>` : ''}</td>
                    <td>${this.formatQuantity(trade.quantity)}</td>
                    <td>${this.formatPriceValue(trade.price, currencySymbol)}</td>
                    <td class="${pnlClass}">${pnlDisplay}</td>
                    <td>${feesHtml}</td>
                </tr>
            `;
        }).join('');
    }

    updateConversations(conversations = []) {
        const container = document.getElementById('conversationsBody');
        if (!container) {
            return;
        }

        if (!Array.isArray(conversations) || conversations.length === 0) {
            container.innerHTML = '<div class="empty-state">暂无对话记录</div>';
            return;
        }

        container.innerHTML = conversations.map(conv => `
            <div class="conversation-item">
                <div class="conversation-time">${this.formatTimestampToDatetime(conv.timestamp)}</div>
                <div class="conversation-content">${conv.ai_response || ''}</div>
            </div>
        `).join('');
    }

    getInstrumentCode(item = {}) {
        const code = item.instrument_code || item.coin || item.symbol || item.ticker || item.code;
        return code ? String(code).toUpperCase() : '-';
    }

    getWatchlist() {
        if (this.watchlist && this.watchlist.length) {
            return this.watchlist;
        }
        return [...this.defaultWatchlist];
    }

    updateWatchlist(models = []) {
        const unique = new Set();
        models.forEach(model => {
            const list = Array.isArray(model.instruments)
                ? model.instruments
                : (typeof model.instrument_list === 'string' ? model.instrument_list.split(',') : []);
            list.forEach(item => {
                const code = String(item).trim().toUpperCase();
                if (code) {
                    unique.add(code);
                }
            });
        });
        this.watchlist = Array.from(unique);
        if (!this.watchlist.length) {
            this.watchlist = [...this.defaultWatchlist];
        }
    }

    async loadMarketOverview() {
        try {
            const [status, quotes] = await Promise.all([
                this.fetchMarketStatus(),
                this.fetchMarketQuotes()
            ]);
            this.marketStatus = status;
            this.updateMarketStatus(status);
            this.renderMarketPrices(quotes);
        } catch (error) {
            console.error('Failed to load market overview:', error);
            this.updateMarketStatus(null, error);
            this.renderMarketPrices({});
        }
    }

    async fetchMarketStatus() {
        const response = await fetch('/api/markets/a-share/status');
        if (!response.ok) {
            throw new Error('无法获取市场状态');
        }
        return response.json();
    }

    async fetchMarketQuotes() {
        const instruments = this.getWatchlist();
        if (!instruments.length) {
            return {};
        }
        const params = new URLSearchParams();
        params.append('market_type', 'a_share');
        instruments.slice(0, 8).forEach(code => params.append('instruments', code));
        const response = await fetch(`/api/market/prices?${params.toString()}`);
        if (!response.ok) {
            throw new Error('无法获取行情数据');
        }
        return response.json();
    }

    updateMarketStatus(status, error) {
        const badge = document.getElementById('marketStatusBadge');
        const textEl = document.getElementById('marketStatusText');
        const subEl = document.getElementById('marketStatusSub');
        if (!badge || !textEl || !subEl) {
            return;
        }

        if (error || !status) {
            badge.className = 'market-status-pill market-status-pill--closed';
            badge.textContent = '异常';
            textEl.textContent = '无法获取市场状态';
            subEl.textContent = '';
            return;
        }

        const marketOpen = Boolean(status.market_open);
        const session = (status.current_session || '').toString();
        const reason = (status.reason || '').toString();
        const { badgeText, badgeClass, description } = this.resolveMarketStatusTexts({ marketOpen, session, reason });

        badge.className = `market-status-pill market-status-pill--${badgeClass}`;
        badge.textContent = badgeText;
        textEl.textContent = description;

        const serverTime = this.formatTimestampToDatetime(status.server_time);
        if (marketOpen) {
            subEl.textContent = serverTime ? `服务器时间：${serverTime}` : '';
        } else if (status.next_open) {
            subEl.textContent = `下一次开盘：${this.formatTimestampToDatetime(status.next_open)}`;
        } else if (serverTime) {
            subEl.textContent = `服务器时间：${serverTime}`;
        } else {
            subEl.textContent = '';
        }
    }

    resolveMarketStatusTexts({ marketOpen, session, reason }) {
        const normalizedReason = (reason || '').toLowerCase();

        if (marketOpen) {
            if (session === 'afternoon') {
                return {
                    badgeText: '下午盘',
                    badgeClass: 'open',
                    description: '下午盘交易进行中'
                };
            }
            return {
                badgeText: '上午盘',
                badgeClass: 'open',
                description: '上午盘交易进行中'
            };
        }

        if (normalizedReason.includes('midday')) {
            return {
                badgeText: '午间休市',
                badgeClass: 'break',
                description: '午间休市'
            };
        }
        if (normalizedReason.includes('pre')) {
            return {
                badgeText: '未开盘',
                badgeClass: 'pending',
                description: '等待开盘'
            };
        }
        if (normalizedReason.includes('post')) {
            return {
                badgeText: '已收盘',
                badgeClass: 'closed',
                description: '当日交易结束'
            };
        }
        if (normalizedReason.includes('holiday')) {
            return {
                badgeText: '节假日',
                badgeClass: 'holiday',
                description: '节假日休市'
            };
        }
        if (normalizedReason.includes('weekend')) {
            return {
                badgeText: '周末休市',
                badgeClass: 'holiday',
                description: '周末休市'
            };
        }

        return {
            badgeText: '休市',
            badgeClass: 'closed',
            description: '当前不在交易时段'
        };
    }

    renderMarketPrices(quotes = {}) {
        const container = document.getElementById('marketPrices');
        if (!container) {
            return;
        }

        const entries = Object.entries(quotes || {});
        if (entries.length === 0) {
            container.innerHTML = '<div class="empty-state">暂无行情数据</div>';
            return;
        }

        const currencySymbol = this.currencySymbol;

        container.innerHTML = entries.map(([code, data]) => {
            const name = data?.name || data?.symbol || '';
            const price = this.formatPriceValue(data?.price, currencySymbol);
            const changeRaw = data?.change_pct ?? data?.change_24h ?? 0;
            const changeValue = Number(changeRaw) || 0;
            const changeClass = changeValue >= 0 ? 'positive' : 'negative';
            const changeIcon = changeValue >= 0 ? '▲' : '▼';
            const suspension = Boolean(data?.suspension) || (data?.trading_status || '').toLowerCase() === 'suspended';
            const statusBadge = suspension ? '<span class="status-badge status-badge--suspended">停牌</span>' : '';
            const board = data?.board ? `<div class="price-board">${data.board}</div>` : '';

            return `
                <div class="price-item">
                    <div class="price-header">
                        <div class="price-symbol">${code}${statusBadge}</div>
                        ${name ? `<div class="price-name">${name}</div>` : ''}
                    </div>
                    <div class="price-body">
                        <div class="price-value">${price}</div>
                        <div class="price-change ${changeClass}">${changeIcon} ${Math.abs(changeValue).toFixed(2)}%</div>
                    </div>
                    ${board}
                </div>
            `;
        }).join('');
    }

    switchTab(tabName) {
        document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));

        const targetBtn = document.querySelector(`[data-tab="${tabName}"]`);
        const targetTab = document.getElementById(`${tabName}Tab`);
        if (targetBtn) {
            targetBtn.classList.add('active');
        }
        if (targetTab) {
            targetTab.classList.add('active');
        }
    }

    async showApiProviderModal() {
        await this.loadProviders();
        document.getElementById('apiProviderModal').classList.add('show');
    }

    hideApiProviderModal() {
        document.getElementById('apiProviderModal').classList.remove('show');
        this.clearApiProviderForm();
    }

    clearApiProviderForm() {
        document.getElementById('providerName').value = '';
        document.getElementById('providerApiUrl').value = '';
        document.getElementById('providerApiKey').value = '';
        document.getElementById('availableModels').value = '';
    }

    async saveApiProvider() {
        const data = {
            name: document.getElementById('providerName').value.trim(),
            api_url: document.getElementById('providerApiUrl').value.trim(),
            api_key: document.getElementById('providerApiKey').value,
            models: document.getElementById('availableModels').value.trim()
        };

        if (!data.name || !data.api_url || !data.api_key) {
            alert('请填写所有必填字段');
            return;
        }

        try {
            const response = await fetch('/api/providers', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });

            if (response.ok) {
                this.hideApiProviderModal();
                this.loadProviders();
                alert('API提供方保存成功');
            }
        } catch (error) {
            console.error('Failed to save provider:', error);
            alert('保存API提供方失败');
        }
    }

    async fetchModels() {
        const apiUrl = document.getElementById('providerApiUrl').value.trim();
        const apiKey = document.getElementById('providerApiKey').value;

        if (!apiUrl || !apiKey) {
            alert('请先填写API地址和密钥');
            return;
        }

        const fetchBtn = document.getElementById('fetchModelsBtn');
        const originalText = fetchBtn.innerHTML;
        fetchBtn.innerHTML = '<i class="bi bi-arrow-clockwise spin"></i> 获取中...';
        fetchBtn.disabled = true;

        try {
            const response = await fetch('/api/providers/models', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ api_url: apiUrl, api_key: apiKey })
            });

            if (response.ok) {
                const data = await response.json();
                if (data.models && data.models.length > 0) {
                    document.getElementById('availableModels').value = data.models.join(', ');
                    alert(`成功获取 ${data.models.length} 个模型`);
                } else {
                    alert('未获取到模型列表，请手动输入');
                }
            } else {
                alert('获取模型列表失败，请检查API地址和密钥');
            }
        } catch (error) {
            console.error('Failed to fetch models:', error);
            alert('获取模型列表失败');
        } finally {
            fetchBtn.innerHTML = originalText;
            fetchBtn.disabled = false;
        }
    }

    async loadProviders() {
        try {
            const response = await fetch('/api/providers');
            const data = await response.json();
            const providers = Array.isArray(data) ? data : [];
            this.providers = providers;
            this.renderProviders(providers);
            this.updateModelProviderSelect(providers);
            return providers;
        } catch (error) {
            console.error('Failed to load providers:', error);
            return this.providers || [];
        }
    }

    renderProviders(providers) {
        const container = document.getElementById('providerList');

        if (providers.length === 0) {
            container.innerHTML = '<div class="empty-state">暂无API提供方</div>';
            return;
        }

        container.innerHTML = providers.map(provider => {
            const models = provider.models ? provider.models.split(',').map(m => m.trim()) : [];
            const modelsHtml = models.map(model => `<span class="model-tag">${model}</span>`).join('');

            return `
                <div class="provider-item">
                    <div class="provider-info">
                        <div class="provider-name">${provider.name}</div>
                        <div class="provider-url">${provider.api_url}</div>
                        <div class="provider-models">${modelsHtml}</div>
                    </div>
                    <div class="provider-actions">
                        <span class="provider-delete" onclick="app.deleteProvider(${provider.id})" title="删除">
                            <i class="bi bi-trash"></i>
                        </span>
                    </div>
                </div>
            `;
        }).join('');
    }

    updateModelProviderSelect(providers) {
        const select = document.getElementById('modelProvider');
        const currentValue = select.value;

        select.innerHTML = '<option value="">请选择API提供方</option>';
        providers.forEach(provider => {
            const option = document.createElement('option');
            option.value = provider.id;
            option.textContent = provider.name;
            select.appendChild(option);
        });

        if (currentValue && providers.find(p => p.id == currentValue)) {
            select.value = currentValue;
            this.updateModelOptions(currentValue);
        }
    }

    updateModelOptions(providerId) {
        const modelSelect = document.getElementById('modelIdentifier');

        if (!providerId) {
            modelSelect.innerHTML = '<option value="">请选择API提供方</option>';
            return;
        }

        const provider = this.providers?.find(p => p.id == providerId);
        if (!provider || !provider.models) {
            modelSelect.innerHTML = '<option value="">该提供方暂无模型</option>';
            return;
        }

        const models = provider.models.split(',').map(m => m.trim()).filter(m => m);
        modelSelect.innerHTML = '<option value="">请选择模型</option>';
        models.forEach(model => {
            const option = document.createElement('option');
            option.value = model;
            option.textContent = model;
            modelSelect.appendChild(option);
        });
    }

    async loadInstrumentOptions(force = false) {
        if (!force && this.instrumentOptions.length > 0) {
            this.renderInstrumentOptions(this.instrumentOptions);
            return this.instrumentOptions;
        }

        const refreshBtn = document.getElementById('refreshInstrumentBtn');
        const originalLabel = refreshBtn ? refreshBtn.innerHTML : '';
        if (refreshBtn) {
            refreshBtn.disabled = true;
            refreshBtn.innerHTML = '<i class="bi bi-arrow-clockwise spin"></i> 刷新中...';
        }

        try {
            const response = await fetch('/api/markets/a-share/symbols');
            if (!response.ok) {
                throw new Error('failed');
            }
            const payload = await response.json();
            const items = this.normalizeInstrumentResponse(payload);
            this.instrumentOptions = items.length ? items : this.defaultWatchlist.map(code => ({ code, name: '', board: '' }));
            this.renderInstrumentOptions(this.instrumentOptions);
            return this.instrumentOptions;
        } catch (error) {
            console.warn('Failed to load instrument list:', error);
            if (!this.instrumentOptions.length) {
                this.instrumentOptions = this.defaultWatchlist.map(code => ({ code, name: '', board: '' }));
                this.renderInstrumentOptions(this.instrumentOptions);
            }
            return this.instrumentOptions;
        } finally {
            if (refreshBtn) {
                refreshBtn.disabled = false;
                refreshBtn.innerHTML = originalLabel;
            }
        }
    }

    normalizeInstrumentResponse(payload) {
        let items = [];
        if (Array.isArray(payload)) {
            items = payload;
        } else if (Array.isArray(payload?.items)) {
            items = payload.items;
        } else if (Array.isArray(payload?.symbols)) {
            items = payload.symbols;
        } else if (Array.isArray(payload?.data)) {
            items = payload.data;
        }

        const normalized = items.map(item => {
            if (typeof item === 'string') {
                return { code: item.toUpperCase(), name: '', board: '' };
            }
            const code = (item.symbol || item.code || item.instrument_code || item.requested_symbol || '').toUpperCase();
            const name = item.name || item.display_name || '';
            const board = item.board || item.market || '';
            return { code, name, board };
        }).filter(item => item.code);

        const unique = [];
        const seen = new Set();
        normalized.forEach(item => {
            if (!seen.has(item.code)) {
                seen.add(item.code);
                unique.push(item);
            }
        });
        return unique;
    }

    renderInstrumentOptions(options = this.instrumentOptions) {
        const select = document.getElementById('instrumentSelect');
        if (!select) {
            return;
        }

        if (!options.length) {
            select.innerHTML = '<option value="">暂无可用股票</option>';
            return;
        }

        select.innerHTML = options.map(item => {
            const namePart = item.name ? ` - ${item.name}` : '';
            const boardPart = item.board ? ` (${item.board})` : '';
            return `<option value="${item.code}">${item.code}${namePart}${boardPart}</option>`;
        }).join('');
    }

    async preloadInstrumentOptions() {
        try {
            await this.loadInstrumentOptions();
        } catch (error) {
            console.warn('Preload instrument list failed:', error);
        }
    }

    async deleteProvider(providerId) {
        if (!confirm('确定要删除这个API提供方吗？')) return;

        try {
            const response = await fetch(`/api/providers/${providerId}`, {
                method: 'DELETE'
            });

            if (response.ok) {
                this.loadProviders();
            }
        } catch (error) {
            console.error('Failed to delete provider:', error);
        }
    }

    async showModal() {
        await Promise.all([
            this.loadProviders(),
            this.loadInstrumentOptions()
        ]);
        document.getElementById('addModelModal').classList.add('show');
    }

    hideModal() {
        document.getElementById('addModelModal').classList.remove('show');
    }

    async submitModel() {
        const providerId = document.getElementById('modelProvider').value;
        const modelName = document.getElementById('modelIdentifier').value;
        const displayName = document.getElementById('modelName').value.trim();
        const initialCapital = parseFloat(document.getElementById('initialCapital').value);
        const instrumentSelect = document.getElementById('instrumentSelect');
        const instruments = instrumentSelect
            ? Array.from(instrumentSelect.selectedOptions).map(option => option.value.trim().toUpperCase()).filter(Boolean)
            : [];

        if (!providerId || !modelName || !displayName) {
            alert('请填写所有必填字段');
            return;
        }

        if (!instruments.length) {
            alert('请至少选择一个股票代码');
            return;
        }

        if (Number.isNaN(initialCapital) || initialCapital <= 0) {
            alert('请输入有效的初始资金');
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
                    market_type: 'a_share',
                    cash_currency: 'CNY',
                    instruments
                })
            });

            if (response.ok) {
                this.hideModal();
                this.loadModels();
                this.clearForm();
            } else {
                const errorBody = await response.json().catch(() => ({}));
                alert(errorBody.error || '添加模型失败');
            }
        } catch (error) {
            console.error('Failed to add model:', error);
            alert('添加模型失败');
        }
    }

    async deleteModel(modelId) {
        if (!confirm('确定要删除这个模型吗？')) return;

        try {
            const response = await fetch(`/api/models/${modelId}`, {
                method: 'DELETE'
            });

            if (response.ok) {
                if (this.currentModelId === modelId) {
                    this.currentModelId = null;
                    this.showAggregatedView();
                } else {
                    this.loadModels();
                }
            }
        } catch (error) {
            console.error('Failed to delete model:', error);
        }
    }

    clearForm() {
        document.getElementById('modelProvider').value = '';
        document.getElementById('modelIdentifier').value = '';
        document.getElementById('modelName').value = '';
        document.getElementById('initialCapital').value = '100000';
        const instrumentSelect = document.getElementById('instrumentSelect');
        if (instrumentSelect) {
            Array.from(instrumentSelect.options).forEach(option => {
                option.selected = false;
            });
        }
    }

    async refresh() {
        await Promise.all([
            this.loadModels(),
            this.isAggregatedView ? this.loadAggregatedData() : this.loadModelData()
        ]);
    }

    startRefreshCycles() {
        this.refreshIntervals.market = setInterval(() => {
            this.loadMarketOverview();
        }, 10000);

        this.refreshIntervals.portfolio = setInterval(() => {
            if (this.isAggregatedView || this.currentModelId) {
                if (this.isAggregatedView) {
                    this.loadAggregatedData();
                } else {
                    this.loadModelData();
                }
            }
        }, 12000);
    }

    stopRefreshCycles() {
        Object.values(this.refreshIntervals).forEach(interval => {
            if (interval) clearInterval(interval);
        });
    }

    async showSettingsModal() {
        try {
            const response = await fetch('/api/settings');
            const settings = await response.json();

            document.getElementById('tradingFrequency').value = settings.trading_frequency_minutes;
            document.getElementById('tradingFeeRate').value = settings.trading_fee_rate;

            document.getElementById('settingsModal').classList.add('show');
        } catch (error) {
            console.error('Failed to load settings:', error);
            alert('加载设置失败');
        }
    }

    hideSettingsModal() {
        document.getElementById('settingsModal').classList.remove('show');
    }

    async saveSettings() {
        const tradingFrequency = parseInt(document.getElementById('tradingFrequency').value);
        const tradingFeeRate = parseFloat(document.getElementById('tradingFeeRate').value);

        if (!tradingFrequency || tradingFrequency < 1 || tradingFrequency > 1440) {
            alert('请输入有效的交易频率（1-1440分钟）');
            return;
        }

        if (tradingFeeRate < 0 || tradingFeeRate > 0.01) {
            alert('请输入有效的交易费率（0-0.01）');
            return;
        }

        try {
            const response = await fetch('/api/settings', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    trading_frequency_minutes: tradingFrequency,
                    trading_fee_rate: tradingFeeRate
                })
            });

            if (response.ok) {
                this.hideSettingsModal();
                alert('设置保存成功');
            } else {
                alert('保存设置失败');
            }
        } catch (error) {
            console.error('Failed to save settings:', error);
            alert('保存设置失败');
        }
    }

    async checkForUpdates(silent = false) {
        try {
            const response = await fetch('/api/check-update');
            const data = await response.json();

            if (data.update_available) {
                this.showUpdateModal(data);
                this.showUpdateIndicator();
            } else if (!silent) {
                if (data.error) {
                    console.warn('Update check failed:', data.error);
                } else {
                    this.showUpdateIndicator(true);
                    setTimeout(() => this.hideUpdateIndicator(), 2000);
                }
            }
        } catch (error) {
            console.error('Failed to check for updates:', error);
            if (!silent) {
                alert('检查更新失败，请稍后重试');
            }
        }
    }

    showUpdateModal(data) {
        const modal = document.getElementById('updateModal');
        const currentVersion = document.getElementById('currentVersion');
        const latestVersion = document.getElementById('latestVersion');
        const releaseNotes = document.getElementById('releaseNotes');
        const githubLink = document.getElementById('githubLink');

        currentVersion.textContent = `v${data.current_version}`;
        latestVersion.textContent = `v${data.latest_version}`;
        githubLink.href = data.release_url || data.repo_url;

        if (data.release_notes) {
            releaseNotes.innerHTML = this.formatReleaseNotes(data.release_notes);
        } else {
            releaseNotes.innerHTML = '<p>暂无更新说明</p>';
        }

        modal.classList.add('show');
    }

    hideUpdateModal() {
        document.getElementById('updateModal').classList.remove('show');
    }

    dismissUpdate() {
        this.hideUpdateModal();
        this.hideUpdateIndicator();

        const tomorrow = new Date();
        tomorrow.setDate(tomorrow.getDate() + 1);
        localStorage.setItem('updateDismissedUntil', tomorrow.getTime().toString());
    }

    formatReleaseNotes(notes) {
        let formatted = notes
            .replace(/### (.*)/g, '<h3>$1</h3>')
            .replace(/## (.*)/g, '<h2>$1</h2>')
            .replace(/# (.*)/g, '<h1>$1</h1>')
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/`(.*?)`/g, '<code>$1</code>')
            .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>')
            .replace(/^\s*-\s+(.*)/gm, '<li>$1</li>')
            .replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>')
            .replace(/\n\n/g, '</p><p>')
            .replace(/^(.*)/, '<p>$1')
            .replace(/(.*)$/, '$1</p>');

        formatted = formatted.replace(/<p>(<h\d+>.*<\/h\d+>)<\/p>/g, '$1');
        formatted = formatted.replace(/<p>(<ul>.*<\/ul>)<\/p>/g, '$1');

        return formatted;
    }

    showUpdateIndicator(forceSuccess = false) {
        const indicator = document.getElementById('updateIndicator');
        if (!indicator) {
            return;
        }
        if (!forceSuccess) {
            const dismissedUntil = localStorage.getItem('updateDismissedUntil');
            if (dismissedUntil && Date.now() < parseInt(dismissedUntil, 10)) {
                return;
            }
        }
        indicator.style.display = 'block';
    }

    hideUpdateIndicator() {
        const indicator = document.getElementById('updateIndicator');
        if (indicator) {
            indicator.style.display = 'none';
        }
    }
}

const app = new TradingApp();
