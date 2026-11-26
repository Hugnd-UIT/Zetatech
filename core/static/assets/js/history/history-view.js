(function() {
    const runtime = window.zetatechRuntime;

window.updateTablePagination = function(prefix, totalItems, currentPage, pageSize) {
    const paginationEl = document.getElementById(`${prefix}-pagination`);
    const infoEl = document.getElementById(`${prefix}-page-info`);
    const currentEl = document.getElementById(`${prefix}-page-current`);
    const prevBtn = document.getElementById(`${prefix}-page-prev`);
    const nextBtn = document.getElementById(`${prefix}-page-next`);

    if (!paginationEl || !infoEl || !currentEl || !prevBtn || !nextBtn) return;

    const total = Math.max(0, parseInt(totalItems || 0, 10) || 0);
    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    const safePage = Math.min(Math.max(1, currentPage), totalPages);

    if (total <= pageSize) {
        paginationEl.style.display = 'none';
    } else {
        paginationEl.style.display = 'flex';
    }

    const start = total === 0 ? 0 : (safePage - 1) * pageSize + 1;
    const end = total === 0 ? 0 : Math.min(total, safePage * pageSize);

    infoEl.textContent = `Showing ${start}-${end} of ${total}`;
    currentEl.textContent = `${safePage} / ${totalPages}`;
    prevBtn.disabled = safePage <= 1;
    nextBtn.disabled = safePage >= totalPages;
}

window.changeHistoryPage = function(delta) {
    const totalPages = Math.max(1, Math.ceil((runtime.getHistoryFilteredCache().length || 0) / runtime.getHistoryPageSize()));
    runtime.setHistoryCurrentPage(Math.min(Math.max(1, runtime.getHistoryCurrentPage() + delta), totalPages));
    renderHistoryRows(runtime.getHistoryFilteredCache());
}

function modeFor(session) {
    const cfg = session && session.config ? session.config : {};
    return cfg.themes ? 'theme' : 'plugin';
}

function riskFor(session) {
    const high = parseInt((session && session.high_risk_count) || 0, 10) || 0;
    if (high >= 20) return 'high';
    if (high >= 5) return 'medium';
    return 'low';
}

function filterState() {
    const qEl = document.getElementById('history-filter-query');
    const sEl = document.getElementById('history-filter-status');
    const mEl = document.getElementById('history-filter-mode');
    const rEl = document.getElementById('history-filter-risk');

    return {
        query: String(qEl ? qEl.value : '').trim().toLowerCase(),
        status: String(sEl ? sEl.value : 'all').toLowerCase(),
        mode: String(mEl ? mEl.value : 'all').toLowerCase(),
        risk: String(rEl ? rEl.value : 'all').toLowerCase()
    };
}

function filterSessions(sessions, stateInput) {
    const state = stateInput || filterState();

    return (sessions || []).filter((session) => {
        const status = String((session && session.status) || '').toLowerCase();
        const mode = modeFor(session);
        const risk = riskFor(session);
        const date = new Date((session && (session.created_at || session.start_time)) || Date.now()).toLocaleString().toLowerCase();
        const id = String((session && session.id) || '').toLowerCase();

        if (state.status !== 'all' && status !== state.status) return false;
        if (state.mode !== 'all' && mode !== state.mode) return false;
        if (state.risk !== 'all' && risk !== state.risk) return false;

        if (state.query) {
            const text = `${id} ${status} ${mode} ${date}`;
            if (!text.includes(state.query)) return false;
        }

        return true;
    });
}

window.renderHistoryRows = function(sessions) {
    const list = document.getElementById('history-list');
    if (!list) return;

    const safeSessions = sessions || [];
    runtime.setHistoryFilteredCache(safeSessions);

    const totalPages = Math.max(1, Math.ceil(safeSessions.length / runtime.getHistoryPageSize()));
    runtime.setHistoryCurrentPage(Math.min(Math.max(1, runtime.getHistoryCurrentPage()), totalPages));
    const pageStart = (runtime.getHistoryCurrentPage() - 1) * runtime.getHistoryPageSize();
    const pagedSessions = safeSessions.slice(pageStart, pageStart + runtime.getHistoryPageSize());

    updateTablePagination('history', safeSessions.length, runtime.getHistoryCurrentPage(), runtime.getHistoryPageSize());

    if (safeSessions.length === 0) {
        list.innerHTML = '<tr><td colspan="8" class="favorites-empty">No scans match the current filters</td></tr>';
        return;
    }

    const maxFound = safeSessions.reduce((top, session) => {
        const count = parseInt(session.total_found || 0, 10) || 0;
        return Math.max(top, count);
    }, 1);

    const maxHigh = safeSessions.reduce((top, session) => {
        const count = parseInt(session.high_risk_count || 0, 10) || 0;
        return Math.max(top, count);
    }, 1);

    list.innerHTML = pagedSessions.map(s => {
        const sid = parseInt(s.id, 10);
        const found = parseInt(s.total_found || 0, 10) || 0;
        const high = parseInt(s.high_risk_count || 0, 10) || 0;
        const fPct = maxFound > 0 ? Math.min(100, Math.round((found / maxFound) * 100)) : 0;
        const fLvl = fPct >= 70 ? 'high' : (fPct >= 35 ? 'medium' : 'low');
        const rLvl = high >= 20 ? 'high' : (high >= 5 ? 'medium' : 'low');
        const rPct = maxHigh > 0 ? Math.min(100, Math.round((high / maxHigh) * 100)) : 0;
        const cfg = s.config || {};
        const theme = Boolean(cfg.themes);
        const modeLbl = theme ? 'THEME' : 'PLUGIN';
        const modeCls = theme ? 'theme' : 'plugin';
        const sCls = String(s.status || 'unknown').toLowerCase();
        const sLbl = sCls === 'merged' ? 'MERGED' : sCls.toUpperCase();

        return `
            <tr class="history-row" tabindex="0" onclick="viewScan(${sid})" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();viewScan(${sid});}">
                <td class="history-col-id">#${escapeHtml(String(s.id))}</td>
                <td class="history-col-status"><span class="status-badge ${escapeHtml(sCls)}">${escapeHtml(sLbl)}</span></td>
                <td class="history-col-found">
                    <div class="history-found-cell" title="${found} plugins found (relative density ${fPct}%)">
                        <span class="history-found-count">${escapeHtml(String(found))}</span>
                        <span class="history-found-label">plugins</span>
                        <span class="history-found-track"><span class="history-found-fill ${fLvl}" style="width: ${fPct}%;"></span></span>
                    </div>
                </td>
                <td class="history-col-risk">
                    <div class="history-risk-cell" title="${high} high risk (relative to max ${maxHigh}: ${rPct}%)">
                        <span class="history-risk-pill ${rLvl}">${escapeHtml(String(high))}</span>
                        <span class="history-risk-meter"><span class="history-risk-fill ${rLvl}" style="width: ${rPct}%;"></span></span>
                    </div>
                </td>
                <td class="history-col-date"><span class="history-date-stamp">${escapeHtml(new Date(s.created_at || s.start_time).toLocaleString())}</span></td>
                <td class="history-col-semgrep">
                    <div id="history-semgrep-${sid}" class="history-semgrep-cell empty" title="Semgrep status pending">
                        <span id="history-semgrep-count-${sid}" class="history-semgrep-pill">--</span>
                        <span class="history-semgrep-meter"><span id="history-semgrep-fill-${sid}" class="history-semgrep-fill" style="width: 0%;"></span></span>
                        <span id="history-semgrep-state-${sid}" class="history-semgrep-state">WAIT</span>
                    </div>
                </td>
                <td class="history-col-mode">
                    <span class="history-mode-chip ${modeCls}">${escapeHtml(modeLbl)}</span>
                </td>
                <td class="history-col-actions">
                    <div class="history-actions">
                        <span class="history-action-open" aria-hidden="true">
                            <span>Open</span>
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>
                        </span>
                        <button onclick="event.stopPropagation(); deleteScan(${sid})" class="action-btn history-action-delete" title="Delete Scan" aria-label="Delete scan #${sid}">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>
                        </button>
                    </div>
                </td>
            </tr>
        `;
    }).join('');

    hydrateHistorySemgrepBadges(pagedSessions);
}

window.applyHistoryFilters = function() {
    runtime.setHistoryCurrentPage(1);
    const filtered = filterSessions(runtime.getHistorySessionsCache(), filterState());
    renderHistoryRows(filtered);
};

window.initializeHistoryFilters = function() {
    if (window.__historyFiltersInitialized) return;
    const queryEl = document.getElementById('history-filter-query');
    const statusEl = document.getElementById('history-filter-status');
    const modeEl = document.getElementById('history-filter-mode');
    const riskEl = document.getElementById('history-filter-risk');

    const ctrls = [queryEl, statusEl, modeEl, riskEl].filter(Boolean);
    if (ctrls.length === 0) return;

    ctrls.forEach((ctrl) => {
        const evt = ctrl.tagName === 'SELECT' ? 'change' : 'input';
        ctrl.addEventListener(evt, applyHistoryFilters);
    });

    window.__historyFiltersInitialized = true;
};
})();
