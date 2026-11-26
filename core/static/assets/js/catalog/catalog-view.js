(function() {
    const runtime = window.zetatechRuntime;

    window.changeCatalogPage = function(delta) {
        const totalPages = Math.max(1, Math.ceil((runtime.getCatalogFilteredCache().length || 0) / runtime.getCatalogPageSize()));
        runtime.setCatalogCurrentPage(Math.min(Math.max(1, runtime.getCatalogCurrentPage() + delta), totalPages));
        window.renderCatalogRows(runtime.getCatalogFilteredCache());
    };

    function getCatalogFilterState() {
        const queryEl = document.getElementById('catalog-filter-query');
        const sortEl = document.getElementById('catalog-filter-sort');
        const typeEl = document.getElementById('catalog-filter-type');
        const orderEl = document.getElementById('catalog-filter-order');

        return {
            query: String(queryEl ? queryEl.value : '').trim().toLowerCase(),
            sort: String(sortEl ? sortEl.value : 'last_seen').toLowerCase(),
            type: String(typeEl ? typeEl.value : 'all').toLowerCase(),
            order: String(orderEl ? orderEl.value : 'desc').toLowerCase(),
        };
    }

    function getCatalogSortValue(item, sortKey) {
        if (sortKey === 'seen_count') return parseInt(item.seen_count || 0, 10) || 0;
        if (sortKey === 'max_score') return parseInt(item.max_score_ever || 0, 10) || 0;
        if (sortKey === 'installs') return parseInt(item.latest_installations || 0, 10) || 0;
        if (sortKey === 'updated_days') {
            const days = parseInt(item.latest_days_since_update, 10);
            return Number.isFinite(days) ? days : Number.POSITIVE_INFINITY;
        }
        if (sortKey === 'slug') return String(item.slug || '').toLowerCase();
        const ts = Date.parse(item.last_seen_at || '');
        return Number.isFinite(ts) ? ts : 0;
    }

    function filterCatalogPlugins(items, filterState) {
        const state = filterState || getCatalogFilterState();
        const filtered = (items || []).filter((item) => {
            const itemType = item && item.is_theme ? 'theme' : 'plugin';
            if (state.type !== 'all' && itemType !== state.type) return false;
            if (!state.query) return true;
            const haystack = `${String(item.slug || '').toLowerCase()} ${itemType}`;
            return haystack.includes(state.query);
        });

        filtered.sort((a, b) => {
            const av = getCatalogSortValue(a, state.sort);
            const bv = getCatalogSortValue(b, state.sort);
            let diff = 0;
            if (typeof av === 'string' || typeof bv === 'string') diff = String(av).localeCompare(String(bv));
            else diff = Number(av) - Number(bv);
            if (state.order === 'desc') diff *= -1;
            if (diff !== 0) return diff;
            return String(a.slug || '').toLowerCase().localeCompare(String(b.slug || '').toLowerCase());
        });

        return filtered;
    }

    window.renderCatalogDashboard = function(items) {
        const dashboard = document.getElementById('catalog-dashboard');
        if (!dashboard) return;

        const rows = Array.isArray(items) ? items : [];
        const total = rows.length;
        if (total === 0) {
            dashboard.innerHTML = '';
            return;
        }

        const high = rows.filter(r => (parseInt(r && (r.latest_score ?? r.max_score_ever) || 0, 10) || 0) >= 40).length;
        const mid = rows.filter(r => {
            const score = parseInt(r && (r.latest_score ?? r.max_score_ever) || 0, 10) || 0;
            return score >= 20 && score < 40;
        }).length;
        const low = Math.max(0, total - high - mid);

        let issue = 0;
        let clean = 0;
        let wait = 0;
        let fail = 0;
        let run = 0;

        rows.forEach((r) => {
            const sem = r && r.semgrep ? r.semgrep : null;
            if (!sem) {
                wait += 1;
                return;
            }

            const status = String(sem.status || '').toLowerCase();
            if (status === 'completed') {
                const count = parseInt(sem.findings_count || 0, 10) || 0;
                if (count > 0) issue += 1;
                else clean += 1;
                return;
            }
            if (status === 'failed') {
                fail += 1;
                return;
            }
            if (status === 'running' || status === 'pending') {
                run += 1;
                return;
            }

            wait += 1;
        });

        const scanned = issue + clean + fail;
        const left = Math.max(0, total - scanned);
        const pct = (value, sum) => {
            if (!sum || sum <= 0) return 0;
            return Math.max(0, Math.min(100, Math.round((value / sum) * 100)));
        };

        dashboard.innerHTML = `
            <div class="details-stat-card details-stat-card-total">
                <div class="details-stat-label">Catalog inventory</div>
                <div class="details-stat-value">${total}</div>
                <div class="details-stat-sub">Unique plugins/themes in database</div>
                <div class="details-stat-track"><span class="details-stat-fill details-fill-blue" style="width:100%"></span></div>
            </div>
            <div class="details-stat-card details-stat-card-progress">
                <div class="details-stat-label">Semgrep progress</div>
                <div class="details-stat-value">${scanned} / ${total}</div>
                <div class="details-stat-sub">Processed / Total • ${left} remaining</div>
                <div class="details-stat-track">
                    <span class="details-stat-fill details-fill-primary" style="width:${pct(scanned, total)}%"></span>
                    <span class="details-stat-fill details-fill-wait" style="width:${pct(left, total)}%"></span>
                </div>
            </div>
            <div class="details-stat-card">
                <div class="details-stat-label">Risk split</div>
                <div class="details-stat-value">${high} / ${mid} / ${low}</div>
                <div class="details-stat-sub">High / Medium / Low</div>
                <div class="details-stat-track">
                    <span class="details-stat-fill details-fill-high" style="width:${pct(high, total)}%"></span>
                    <span class="details-stat-fill details-fill-mid" style="width:${pct(mid, total)}%"></span>
                    <span class="details-stat-fill details-fill-low" style="width:${pct(low, total)}%"></span>
                </div>
            </div>
            <div class="details-stat-card">
                <div class="details-stat-label">Semgrep</div>
                <div class="details-stat-value">${issue} / ${clean} / ${run}</div>
                <div class="details-stat-sub">Issue / Clean / Running</div>
                <div class="details-stat-track">
                    <span class="details-stat-fill details-fill-issue" style="width:${pct(issue, total)}%"></span>
                    <span class="details-stat-fill details-fill-clean" style="width:${pct(clean, total)}%"></span>
                    <span class="details-stat-fill details-fill-wait" style="width:${pct(wait, total)}%"></span>
                    <span class="details-stat-fill details-fill-fail" style="width:${pct(fail, total)}%"></span>
                </div>
            </div>
        `;
    };

    window.renderCatalogRows = function(items) {
        const list = document.getElementById('catalog-list');
        if (!list) return;

        const safeItems = items || [];
        runtime.setCatalogFilteredCache(safeItems);

        const totalPages = Math.max(1, Math.ceil(safeItems.length / runtime.getCatalogPageSize()));
        runtime.setCatalogCurrentPage(Math.min(Math.max(1, runtime.getCatalogCurrentPage()), totalPages));
        const pageStart = (runtime.getCatalogCurrentPage() - 1) * runtime.getCatalogPageSize();
        const pagedItems = safeItems.slice(pageStart, pageStart + runtime.getCatalogPageSize());

        window.updateTablePagination('catalog', safeItems.length, runtime.getCatalogCurrentPage(), runtime.getCatalogPageSize());

        if (safeItems.length === 0) {
            list.innerHTML = '<tr><td colspan="7" class="favorites-empty">No plugins in store</td></tr>';
            return;
        }

        const max = pagedItems.reduce((top, item) => {
            const count = parseInt(item.latest_installations || 0, 10) || 0;
            return Math.max(top, count);
        }, 1);

        list.innerHTML = pagedItems.map((item) => {
            const slug = String(item.slug || 'unknown-plugin');
            const theme = !!item.is_theme;
            const cls = theme ? 'theme' : 'plugin';
            const mode = theme ? 'THEME' : 'PLUGIN';
            const latest = parseInt(item.latest_score || 0, 10) || 0;
            const peak = parseInt(item.max_score_ever || 0, 10) || 0;
            const score = Math.max(latest, peak);
            const sCls = getRiskClassForResult(score);
            const sPct = Math.max(0, Math.min(100, score));
            const installs = parseInt(item.latest_installations || 0, 10) || 0;
            const rawPct = max > 0 ? Math.min(100, Math.round((installs / max) * 100)) : 0;
            const iPct = installs > 0 ? Math.max(4, rawPct) : 0;
            const iLvl = iPct >= 70 ? 'high' : (iPct >= 35 ? 'medium' : 'low');
            const updated = getUpdatedLabel(parseDaysSinceUpdate(item.latest_days_since_update));

            const sem = item.semgrep || null;
            const sCount = sem ? (parseInt(sem.findings_count || 0, 10) || 0) : (parseInt(item.latest_semgrep_findings || 0, 10) || 0);
            const sStat = sem ? String(sem.status || '').toLowerCase() : '';
            let sTone = 'empty';
            let sState = 'WAIT';
            let sProg = 0;
            if (sStat === 'completed') {
                sTone = sCount > 0 ? 'alert' : 'complete';
                sState = sCount > 0 ? 'ISSUE' : 'CLEAN';
                sProg = 100;
            } else if (sStat === 'running' || sStat === 'pending') {
                sTone = 'running';
                sState = 'SCANNING';
                sProg = 35;
            } else if (sStat === 'failed') {
                sTone = 'alert';
                sState = 'FAIL';
                sProg = 100;
            }

            const sid = parseInt(item.last_seen_session_id || 0, 10) || 0;
            const link = theme ? `https://wordpress.org/themes/${slug}/` : `https://wordpress.org/plugins/${slug}/`;
            const seen = item.last_seen_at ? new Date(item.last_seen_at).toLocaleString() : '';

            const json = JSON.stringify({
                slug,
                name: slug,
                version: item.latest_version || 'n/a',
                score,
                installations: installs,
                days_since_update: parseInt(item.latest_days_since_update || 0, 10) || 0,
                is_theme: theme,
                wp_org_link: link,
                trac_link: theme ? `https://themes.trac.wordpress.org/log/${slug}/` : `https://plugins.trac.wordpress.org/log/${slug}/`,
            });

            return `
                <tr class="history-row details-results-row" tabindex="0" onclick='openCatalogPlugin(${json}, ${sid})' onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();openCatalogPlugin(${json}, ${sid});}">
                    <td class="details-col-slug"><span class="details-slug">${escapeHtml(slug)}</span></td>
                    <td class="details-col-version"><span class="history-semgrep-pill">${escapeHtml(String(item.latest_version || 'n/a'))}</span></td>
                    <td class="details-col-score"><div class="history-risk-cell" title="Risk ${score} (latest ${latest}, max ${peak})"><span class="history-risk-pill ${sCls}">${score}</span><span class="history-risk-meter"><span class="history-risk-fill ${sCls}" style="width:${sPct}%;"></span></span></div></td>
                    <td class="details-col-updated"><span class="history-date-stamp">${escapeHtml(updated)}</span></td>
                    <td class="details-col-installs"><div class="history-found-cell" title="${installs.toLocaleString()} installs / last seen ${escapeHtml(seen)}"><span class="history-found-count">${escapeHtml(formatInstallCount(installs))}</span><span class="history-found-label">installs</span><span class="history-found-track"><span class="history-found-fill ${iLvl}" style="width:${iPct}%;"></span></span></div></td>
                    <td class="details-col-semgrep"><div class="history-semgrep-cell ${sTone}"><span class="history-semgrep-pill">${escapeHtml(String(sCount || '--'))}</span><span class="history-semgrep-meter"><span class="history-semgrep-fill" style="width:${sProg}%;"></span></span><span class="history-semgrep-state">${escapeHtml(sState)}</span></div></td>
                    <td class="details-col-actions"><div class="details-row-actions"><span class="history-mode-chip ${cls}">${escapeHtml(mode)}</span><a href="${escapeHtml(link)}" target="_blank" rel="noreferrer noopener" onclick="event.stopPropagation();" class="action-btn details-wp-btn" aria-label="Open on WordPress.org" title="Open on WordPress.org"><span class="wp-logo-icon" aria-hidden="true"></span></a><button onclick='event.stopPropagation(); openCatalogPlugin(${json}, ${sid})' class="action-btn details-open-btn">Details</button></div></td>
                </tr>
            `;
        }).join('');
    };

    window.applyCatalogFilters = function() {
        runtime.setCatalogCurrentPage(1);
        const filtered = filterCatalogPlugins(runtime.getCatalogPluginsCache(), getCatalogFilterState());
        window.renderCatalogDashboard(filtered);
        window.renderCatalogRows(filtered);
    };

    window.initializeCatalogFilters = function() {
        if (runtime.getCatalogFiltersInitialized()) return;
        const queryEl = document.getElementById('catalog-filter-query');
        const sortEl = document.getElementById('catalog-filter-sort');
        const typeEl = document.getElementById('catalog-filter-type');
        const orderEl = document.getElementById('catalog-filter-order');

        const controls = [queryEl, sortEl, typeEl, orderEl].filter(Boolean);
        if (controls.length === 0) return;

        controls.forEach((control) => {
            const eventName = control.tagName === 'SELECT' ? 'change' : 'input';
            control.addEventListener(eventName, window.applyCatalogFilters);
        });

        runtime.setCatalogFiltersInitialized(true);
    };

    window.loadCatalog = async function() {
        const list = document.getElementById('catalog-list');
        if (!list) return;
        window.renderCatalogDashboard([]);
        list.innerHTML = '<tr><td colspan="7" class="favorites-empty">Loading plugin store...</td></tr>';

        try {
            const pageSize = 1000;
            let offset = 0;
            let total = null;
            const mergedItems = [];

            while (total === null || mergedItems.length < total) {
                const response = await fetch(`/api/catalog/plugins?limit=${pageSize}&offset=${offset}&sort_by=last_seen&order=desc`);
                const data = await response.json();
                const items = data.items || [];

                if (total === null) total = parseInt(data.total || 0, 10) || 0;
                mergedItems.push(...items);

                if (items.length === 0) break;
                offset += items.length;
                if (offset > 200000) break;
            }

            runtime.setCatalogPluginsCache(mergedItems);
            window.initializeCatalogFilters();
            window.applyCatalogFilters();
        } catch (error) {
            console.error(error);
            window.renderCatalogDashboard([]);
            list.innerHTML = '<tr><td colspan="7" class="favorites-empty">Failed to load plugin store</td></tr>';
        }
    };

    window.openCatalogPlugin = function(plugin, sessionId = 0) {
        if (!plugin || !plugin.slug) return;
        if (sessionId) runtime.setCurrentScanId(sessionId);
        window.currentScanResults = [plugin];
        openPluginModal(0);
    };
})();
