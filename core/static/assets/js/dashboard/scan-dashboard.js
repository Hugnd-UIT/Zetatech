(function() {
    const runtime = window.zetatechRuntime;

window.initializeDashboardChartInteractions = function() {
    bindChartHover('dashboard-risk-bars', 'dashboard-risk-caption');
    bindChartHover('dashboard-trend-bars', 'dashboard-trend-caption');
    resetDashboardChartCaptions();
}

window.openDashboardScanFromChart = function(scanId, source = 'chart') {
    const parsed = Number(scanId);
    if (!Number.isFinite(parsed) || parsed <= 0) return;
    setChartCaption('dashboard-risk-caption', `Opening #${parsed} (${source})`);
    setChartCaption('dashboard-trend-caption', `Opening #${parsed} (${source})`);
    setTimeout(resetDashboardChartCaptions, 1200);
    viewScan(parsed);
};

function renderRecent(sessions) {
    const list = document.getElementById('dashboard-recent-list');
    const rate = document.getElementById('dashboard-completed-rate');
    if (!list) return;

    if (!sessions || sessions.length === 0) {
        list.innerHTML = '<div class="recent-empty">No scans yet</div>';
        if (rate) rate.textContent = '0% completed';
        return;
    }

    const done = sessions.filter(s => String(s.status).toLowerCase() === 'completed').length;
    const pct = Math.round((done / sessions.length) * 100);
    if (rate) rate.textContent = `${pct}% completed`;

    const max = sessions.reduce((top, session) => {
        const count = parseInt(session.total_found || 0, 10) || 0;
        return Math.max(top, count);
    }, 1);

    list.innerHTML = sessions.slice(0, 3).map(s => {
        const id = parseInt(s.id, 10) || 0;
        const sCls = String(s.status || 'unknown').toLowerCase();
        const sLbl = sCls === 'merged' ? 'MERGED' : sCls.toUpperCase();
        const found = parseInt(s.total_found || 0, 10) || 0;
        const high = parseInt(s.high_risk_count || 0, 10) || 0;
        const fPct = max > 0 ? Math.min(100, Math.round((found / max) * 100)) : 0;
        const fLvl = fPct >= 70 ? 'high' : (fPct >= 35 ? 'medium' : 'low');
        const rLvl = high >= 20 ? 'high' : (high >= 5 ? 'medium' : 'low');
        const rPct = found > 0 ? Math.min(100, Math.round((high / found) * 100)) : 0;
        const date = new Date(s.created_at || s.start_time).toLocaleString();
        return `
            <div class="recent-row recent-history-row" tabindex="0" onclick="openDashboardScanFromChart(${id}, 'recent')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();openDashboardScanFromChart(${id}, 'recent');}">
                <span class="recent-title recent-history-id">#${id}</span>
                <span class="status-badge ${escapeHtml(sCls)}">${escapeHtml(sLbl)}</span>
                <div class="history-found-cell" title="${found} plugins found (relative density ${fPct}%)">
                    <span class="history-found-count">${escapeHtml(String(found))}</span>
                    <span class="history-found-label">plugins</span>
                    <span class="history-found-track"><span class="history-found-fill ${fLvl}" style="width: ${fPct}%;"></span></span>
                </div>
                <div class="history-risk-cell" title="${high} high risk / ${found} total (${rPct}%)">
                    <span class="history-risk-pill ${rLvl}">${escapeHtml(String(high))}</span>
                    <span class="history-risk-meter"><span class="history-risk-fill ${rLvl}" style="width: ${rPct}%;"></span></span>
                </div>
                <span class="recent-meta history-date-stamp recent-history-date">${escapeHtml(date)}</span>
                <button class="history-action-open dashboard-history-open" type="button" onclick="event.stopPropagation();openDashboardScanFromChart(${id}, 'recent')" title="Open Scan" aria-label="Open scan #${id}">
                    <span>OPEN</span>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>
                </button>
            </div>
        `;
    }).join('');
}

window.renderRecentFavorites = function(favorites) {
    const list = document.getElementById('dashboard-favorites-list');
    if (!list) return;

    if (!favorites || favorites.length === 0) {
        list.innerHTML = '<div class="recent-empty">No favorites yet</div>';
        return;
    }

    list.innerHTML = favorites.slice(0, 3).map(plugin => {
        const rawSlug = String(plugin.slug || 'unknown-plugin');
        const slug = escapeHtml(rawSlug);
        const slugJs = JSON.stringify(rawSlug);
        const score = parseInt(plugin.score || 0, 10) || 0;
        const level = score >= 40 ? 'high' : (score >= 20 ? 'medium' : 'low');
        const ratio = Math.max(0, Math.min(100, score));
        const ver = `v${String(plugin.version || 'n/a')}`;
        return `
            <div class="recent-row recent-favorites-row" tabindex="0" onclick='openPluginModalBySlug(${slugJs})' onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();openPluginModalBySlug(${slugJs});}">
                <span class="recent-title recent-favorites-slug">${slug}</span>
                <span class="recent-meta history-date-stamp recent-favorites-version">${escapeHtml(ver)}</span>
                <div class="history-risk-cell recent-favorites-risk" title="Risk score ${score}">
                    <span class="history-risk-pill ${level}">${score}</span>
                    <span class="history-risk-meter"><span class="history-risk-fill ${level}" style="width: ${ratio}%;"></span></span>
                </div>
                <button class="history-action-open dashboard-history-open" type="button" onclick='event.stopPropagation();openPluginModalBySlug(${slugJs})' title="Open Favorite" aria-label="Open favorite ${slug}">
                    <span>OPEN</span>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>
                </button>
            </div>
        `;
    }).join('');
}

async function loadFavs() {
    try {
        const res = await fetch('/api/favorites');
        if (!res.ok) throw new Error(`Favorites fetch failed: ${res.status}`);
        const data = await res.json();
        renderRecentFavorites(data.favorites || []);
    } catch (error) {
        renderRecentFavorites([]);
    }
}

function renderRisk(sessions) {
    const bars = document.getElementById('dashboard-risk-bars');
    const caption = document.getElementById('dashboard-risk-caption');
    if (!bars) return;

    if (!sessions || sessions.length === 0) {
        bars.innerHTML = '';
        if (caption) caption.textContent = 'No history';
        return;
    }

    const recent = sessions.slice(0, 8).reverse();
    const maxFound = Math.max(1, ...recent.map(s => parseInt(s.total_found || 0)));

    bars.innerHTML = recent.map((s) => {
        const id = parseInt(s.id);
        const found = parseInt(s.total_found || 0);
        const high = parseInt(s.high_risk_count || 0);
        const ratio = found > 0 ? high / found : 0;
        const height = Math.max(10, Math.round((found / maxFound) * 100));
        const level = ratio >= 0.35 ? 'high' : (ratio >= 0.15 ? 'medium' : 'low');
        const title = `Scan #${id} | Found ${found} | High ${high}`;
        const text = `#${id} risk ${high}/${found}`;
        return `
            <button class="bar-item chart-point ${level}" type="button" data-scan-id="${id}" data-caption="${text}" style="--h:${height}%" title="${title}" onclick="openDashboardScanFromChart(${id}, 'risk')"></button>
        `;
    }).join('');

    if (caption) {
        const highSum = recent.reduce((acc, s) => acc + parseInt(s.high_risk_count || 0), 0);
        caption.textContent = `${highSum} high-risk total - click a bar`;
    }
}

window.renderTrendBars = function() {
    const bars = document.getElementById('dashboard-trend-bars');
    const caption = document.getElementById('dashboard-trend-caption');
    if (!bars) return;

    const points = runtime.getDashboardTrendPoints();
    if (!points.length) {
        bars.innerHTML = '';
        if (caption) caption.textContent = 'No trend data';
        return;
    }

    const maxVal = Math.max(1, ...points.map(item => item.value));
    bars.innerHTML = points.map((item) => {
        const value = Number(item.value || 0);
        const h = Math.max(8, Math.round((value / maxVal) * 100));
        const scanId = Number(item.scanId || 0);
        if (scanId > 0) {
            const title = `Scan #${scanId} | Found ${value}`;
            const text = `#${scanId} found ${value}`;
            return `<button class="spark-item chart-point" type="button" data-scan-id="${scanId}" data-caption="${text}" style="--h:${h}%" title="${title}" onclick="openDashboardScanFromChart(${scanId}, 'trend')"></button>`;
        }
        return `<div class="spark-item" style="--h:${h}%" title="Live found: ${value}"></div>`;
    }).join('');

    if (caption) caption.textContent = `Recent ${points.length} sessions - click a bar`;
}

function renderTrend(sessions) {
    runtime.setDashboardTrendPoints((sessions || []).slice(0, 8).reverse().map((s) => ({
        value: parseInt(s.total_found || 0),
        scanId: parseInt(s.id || 0)
    })).slice(-8));
    window.renderTrendBars();
}

window.appendTrendPoint = function(value) {
    const parsed = parseInt(value || 0);
    if (!Number.isFinite(parsed)) return;
    const points = [...runtime.getDashboardTrendPoints()];
    points.push({
        value: parsed,
        scanId: Number(runtime.getCurrentScanIdForTrend()) || 0
    });
    runtime.setDashboardTrendPoints(points.slice(-8));
    window.renderTrendBars();
}

window.refreshDashboardFavorites = loadFavs;

window.refreshScanDashboard = function(sessions) {
    const safe = sessions || [];
    const total = safe.length;
    const highTotal = safe.reduce((acc, s) => acc + parseInt(s.high_risk_count || 0), 0);
    setDashboardMetric('dashboard-total-scans', total);
    setDashboardMetric('dashboard-high-risk', highTotal);
    renderRecent(safe);
    loadFavs();
    renderRisk(safe);
    renderTrend(safe);
    resetDashboardChartCaptions();
}
})();
