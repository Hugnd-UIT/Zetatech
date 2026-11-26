(function() {
    const runtime = window.zetatechRuntime;

    window.changeDetailsPage = function(delta) {
        const total = Math.max(1, Math.ceil((runtime.getDetailsResultsCache().length || 0) / runtime.getDetailsPageSize()));
        runtime.setDetailsCurrentPage(Math.min(Math.max(1, runtime.getDetailsCurrentPage() + delta), total));
        window.renderDetailsRows(runtime.getDetailsResultsCache());
    };

    function setRunLabel(btn, label) {
        btn.innerHTML = `<span class="semgrep-logo-icon" aria-hidden="true"></span><span class="semgrep-btn-label">${escapeHtml(label)}</span>`;
    }

    window.setDetailsBulkControls = function(state, meta = {}) {
        const runBtn = document.getElementById('details-bulk-run');
        const stopBtn = document.getElementById('details-bulk-stop');
        if (!runBtn || !stopBtn) return;

        if (state === 'running') {
            const scanned = Number(meta.scanned || 0);
            const total = Number(meta.total || 0);
            const slug = String(meta.currentSlug || '').trim();
            runBtn.disabled = true;
            setRunLabel(runBtn, 'Scanning...');
            runBtn.title = slug ? `Scanning ${scanned}/${total}: ${slug}` : `Scanning ${scanned}/${total}`;
            stopBtn.style.display = 'inline-flex';
            stopBtn.disabled = false;
            return;
        }

        if (state === 'paused') {
            runBtn.disabled = false;
            setRunLabel(runBtn, 'Resume Scan All');
            runBtn.title = 'Bulk Semgrep paused';
            stopBtn.style.display = 'none';
            return;
        }

        if (state === 'completed') {
            runBtn.disabled = false;
            setRunLabel(runBtn, 'Scan All (Semgrep)');
            const findings = Number(meta.findings || 0);
            runBtn.title = `Completed${Number.isFinite(findings) ? `: ${findings} findings` : ''}`;
            stopBtn.style.display = 'none';
            return;
        }

        runBtn.disabled = false;
        setRunLabel(runBtn, 'Scan All (Semgrep)');
        runBtn.title = '';
        stopBtn.style.display = 'none';
    };

    function filterState() {
        const qEl = document.getElementById('details-filter-query');
        const iEl = document.getElementById('details-filter-installs');
        const sEl = document.getElementById('details-filter-sort');
        const uEl = document.getElementById('details-filter-updated-sort');

        return {
            query: String(qEl ? qEl.value : '').trim().toLowerCase(),
            installs: String(iEl ? iEl.value : 'default').toLowerCase(),
            sort: String(sEl ? sEl.value : 'default').toLowerCase(),
            updatedSort: String(uEl ? uEl.value : 'default').toLowerCase()
        };
    }

    function semgrepState(res) {
        const sem = res && res.semgrep ? res.semgrep : null;
        if (!sem) return 'wait';

        const status = String(sem.status || '').toLowerCase();
        if (status === 'running' || status === 'pending') return 'run';
        if (status === 'failed') return 'fail';
        if (status === 'completed') {
            const count = parseInt(sem.findings_count || 0, 10) || 0;
            return count > 0 ? 'issue' : 'clean';
        }
        return 'wait';
    }

    function issueCount(res) {
        if (!res || !res.semgrep) return 0;
        const status = String(res.semgrep.status || '').toLowerCase();
        if (status !== 'completed') return 0;
        return parseInt(res.semgrep.findings_count || 0, 10) || 0;
    }

    function updatedDays(res) {
        const days = parseDaysSinceUpdate(res && res.days_since_update);
        return days == null ? Number.POSITIVE_INFINITY : days;
    }

    window.renderDetailsDashboard = function(results) {
        const dash = document.getElementById('details-dashboard');
        if (!dash) return;

        const rows = Array.isArray(results) ? results : [];
        const total = rows.length;
        if (total === 0) {
            dash.innerHTML = '';
            return;
        }

        const high = rows.filter(r => (parseInt(r && r.score || 0, 10) || 0) >= 40).length;
        const mid = rows.filter(r => {
            const score = parseInt(r && r.score || 0, 10) || 0;
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
        const pct = (val, sum) => {
            if (!sum || sum <= 0) return 0;
            return Math.max(0, Math.min(100, Math.round((val / sum) * 100)));
        };

        dash.innerHTML = `
            <div class="details-stat-card details-stat-card-total"><div class="details-stat-label">Scan inventory</div><div class="details-stat-value">${total}</div><div class="details-stat-sub">Total plugins/themes in this scan</div><div class="details-stat-track"><span class="details-stat-fill details-fill-blue" style="width:100%"></span></div></div>
            <div class="details-stat-card details-stat-card-progress"><div class="details-stat-label">Semgrep progress</div><div class="details-stat-value">${scanned} / ${total}</div><div class="details-stat-sub">Processed / Total • ${left} remaining</div><div class="details-stat-track"><span class="details-stat-fill details-fill-primary" style="width:${pct(scanned, total)}%"></span><span class="details-stat-fill details-fill-wait" style="width:${pct(left, total)}%"></span></div></div>
            <div class="details-stat-card"><div class="details-stat-label">Risk split</div><div class="details-stat-value">${high} / ${mid} / ${low}</div><div class="details-stat-sub">High / Medium / Low</div><div class="details-stat-track"><span class="details-stat-fill details-fill-high" style="width:${pct(high, total)}%"></span><span class="details-stat-fill details-fill-mid" style="width:${pct(mid, total)}%"></span><span class="details-stat-fill details-fill-low" style="width:${pct(low, total)}%"></span></div></div>
            <div class="details-stat-card"><div class="details-stat-label">Semgrep</div><div class="details-stat-value">${issue} / ${clean} / ${run}</div><div class="details-stat-sub">Issue / Clean / Running</div><div class="details-stat-track"><span class="details-stat-fill details-fill-issue" style="width:${pct(issue, total)}%"></span><span class="details-stat-fill details-fill-clean" style="width:${pct(clean, total)}%"></span><span class="details-stat-fill details-fill-wait" style="width:${pct(wait, total)}%"></span><span class="details-stat-fill details-fill-fail" style="width:${pct(fail, total)}%"></span></div></div>
        `;
    };

    function sortResults(results, sort) {
        const list = Array.isArray(results) ? [...results] : [];
        const state = sort || {};
        const cmps = [];

        if (state.sort === 'semgrep_desc') {
            cmps.push((a, b) => issueCount(b) - issueCount(a));
            cmps.push((a, b) => (parseInt(b && b.score || 0, 10) || 0) - (parseInt(a && a.score || 0, 10) || 0));
        } else if (state.sort === 'semgrep_asc') {
            cmps.push((a, b) => issueCount(a) - issueCount(b));
            cmps.push((a, b) => (parseInt(b && b.score || 0, 10) || 0) - (parseInt(a && a.score || 0, 10) || 0));
        } else if (state.sort === 'score_desc') {
            cmps.push((a, b) => (parseInt(b && b.score || 0, 10) || 0) - (parseInt(a && a.score || 0, 10) || 0));
        } else if (state.sort === 'score_asc') {
            cmps.push((a, b) => (parseInt(a && a.score || 0, 10) || 0) - (parseInt(b && b.score || 0, 10) || 0));
        }

        if (state.installs === 'installs_desc') {
            cmps.push((a, b) => (parseInt(b && b.installations || 0, 10) || 0) - (parseInt(a && a.installations || 0, 10) || 0));
        } else if (state.installs === 'installs_asc') {
            cmps.push((a, b) => (parseInt(a && a.installations || 0, 10) || 0) - (parseInt(b && b.installations || 0, 10) || 0));
        }

        if (state.updatedSort === 'updated_newest') {
            cmps.push((a, b) => updatedDays(a) - updatedDays(b));
        } else if (state.updatedSort === 'updated_oldest') {
            cmps.push((a, b) => updatedDays(b) - updatedDays(a));
        }

        if (cmps.length === 0) return list;

        list.sort((a, b) => {
            for (const cmp of cmps) {
                const diff = cmp(a, b);
                if (diff !== 0) return diff;
            }
            return 0;
        });

        return list;
    }

    function filterResults(results, fState) {
        const state = fState || filterState();

        const kept = (results || []).filter((res) => {
            const slug = String((res && res.slug) || '').toLowerCase();
            const ver = String((res && res.version) || '').toLowerCase();
            const sem = semgrepState(res);
            const issues = issueCount(res);
            const risk = getRiskClassForResult(parseInt((res && res.score) || 0, 10) || 0);
            const installs = parseInt((res && res.installations) || 0, 10) || 0;
            const days = updatedDays(res);

            if (state.query) {
                const text = `${slug} ${ver} ${sem} ${risk} ${issues} ${installs} ${days}`;
                if (!text.includes(state.query)) return false;
            }

            return true;
        });

        return sortResults(kept, state);
    }

    window.applyDetailsFilters = function() {
        runtime.setDetailsCurrentPage(1);
        const filtered = filterResults(runtime.getDetailsSourceCache(), filterState());
        window.renderDetailsRows(filtered);
    };

    window.renderDetailsRows = function(results) {
        const list = document.getElementById('details-list');
        if (!list) return;

        const rows = results || [];
        runtime.setDetailsResultsCache(rows);

        const totalPages = Math.max(1, Math.ceil(rows.length / runtime.getDetailsPageSize()));
        runtime.setDetailsCurrentPage(Math.min(Math.max(1, runtime.getDetailsCurrentPage()), totalPages));
        const start = (runtime.getDetailsCurrentPage() - 1) * runtime.getDetailsPageSize();
        const paged = rows.slice(start, start + runtime.getDetailsPageSize());

        window.updateTablePagination('details', rows.length, runtime.getDetailsCurrentPage(), runtime.getDetailsPageSize());

        if (rows.length === 0) {
            list.innerHTML = '<tr><td colspan="7" class="favorites-empty">No plugins match the current filters</td></tr>';
            return;
        }

        const maxInstalls = rows.reduce((max, item) => {
            const installs = parseInt(item.installations || 0, 10) || 0;
            return Math.max(max, installs);
        }, 1);

        list.innerHTML = paged.map((res) => rowHtml(res, maxInstalls)).join('');
    };

    function installsMeta(res, max) {
        const installs = parseInt(res.installations || 0, 10) || 0;
        const ratio = max > 0 ? Math.min(100, Math.round((installs / max) * 100)) : 0;
        const level = ratio >= 70 ? 'high' : (ratio >= 35 ? 'medium' : 'low');
        return { installs, ratio, level };
    }

    function semgrepMeta(res, slug) {
        let tone = 'empty';
        let count = '--';
        let state = 'WAIT';
        let pct = 0;
        let title = 'Semgrep has not run for this plugin yet.';

        if (res.semgrep) {
            if (res.semgrep.status === 'completed') {
                const issues = parseInt(res.semgrep.findings_count || 0, 10) || 0;
                tone = issues > 0 ? 'alert' : 'complete';
                count = String(issues);
                state = issues > 0 ? 'ISSUE' : 'CLEAN';
                pct = 100;
                title = issues > 0 ? `${issues} finding(s) detected for ${slug}.` : `No findings detected for ${slug}.`;
            } else if (res.semgrep.status === 'running' || res.semgrep.status === 'pending') {
                tone = 'running';
                count = '--';
                state = 'SCANNING';
                pct = 35;
                title = `Semgrep scan is running for ${slug}.`;
            } else if (res.semgrep.status === 'failed') {
                tone = 'alert';
                count = 'ERR';
                state = 'FAIL';
                pct = 100;
                title = `Semgrep scan failed for ${slug}.`;
            }
        }

        return { tone, count, state, pct, title };
    }

    function rowHtml(res, max) {
        const idx = window.currentScanResults.indexOf(res);
        const slug = String(res.slug || 'unknown-plugin');
        const arg = JSON.stringify(slug);
        const score = parseInt(res.score || 0, 10) || 0;
        const sPct = Math.max(0, Math.min(100, score));
        const rCls = getRiskClassForResult(score);
        const { installs, ratio, level } = installsMeta(res, max);
        const mCls = res.is_theme ? 'theme' : 'plugin';
        const mLbl = mCls.toUpperCase();
        const { tone, count, state, pct, title } = semgrepMeta(res, slug);
        const days = parseDaysSinceUpdate(res.days_since_update);
        const uLbl = getUpdatedLabel(days);
        const fav = isFavoriteSlug(slug);
        const link = res.wp_org_link || (res.is_theme ? `https://wordpress.org/themes/${slug}/` : `https://wordpress.org/plugins/${slug}/`);

        return `
            <tr class="history-row details-results-row" tabindex="0" onclick="openPluginModal(${idx})" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();openPluginModal(${idx});}">
                <td class="details-col-slug"><span class="details-slug">${escapeHtml(slug)}</span>${res.is_duplicate ? '<span class="details-dup-chip">Seen Before · DB</span>' : ''}</td>
                <td class="details-col-version"><span class="history-semgrep-pill">${escapeHtml(String(res.version || 'n/a'))}</span></td>
                <td class="details-col-score"><div class="history-risk-cell" title="Risk score ${score}"><span class="history-risk-pill ${rCls}">${score}</span><span class="history-risk-meter"><span class="history-risk-fill ${rCls}" style="width:${sPct}%;"></span></span></div></td>
                <td class="details-col-updated"><span class="history-date-stamp">${escapeHtml(uLbl)}</span></td>
                <td class="details-col-installs"><div class="history-found-cell" title="${installs.toLocaleString()} installs"><span class="history-found-count">${escapeHtml(formatInstallCount(installs))}</span><span class="history-found-label">installs</span><span class="history-found-track"><span class="history-found-fill ${level}" style="width: ${ratio}%;"></span></span></div></td>
                <td class="details-col-semgrep"><div class="history-semgrep-cell ${tone}" title="${escapeHtml(title)}"><span class="history-semgrep-pill">${escapeHtml(count)}</span><span class="history-semgrep-meter"><span class="history-semgrep-fill" style="width: ${pct}%;"></span></span><span class="history-semgrep-state">${escapeHtml(state)}</span></div></td>
                <td class="details-col-actions"><div class="details-row-actions"><span class="history-mode-chip ${mCls}">${escapeHtml(mLbl)}</span><button onclick='event.stopPropagation(); toggleFavorite(${arg})' class="action-btn details-fav-btn${fav ? ' active' : ''}" title="${fav ? 'In Favorites' : 'Add to Favorites'}" aria-label="Toggle favorite ${escapeHtml(slug)}"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path></svg></button><a href="${escapeHtml(link)}" target="_blank" rel="noreferrer noopener" onclick="event.stopPropagation();" class="action-btn details-wp-btn" aria-label="Open on WordPress.org" title="Open on WordPress.org"><span class="wp-logo-icon" aria-hidden="true"></span></a><button onclick="event.stopPropagation(); openPluginModal(${idx})" class="action-btn details-open-btn">Details</button></div></td>
            </tr>
        `;
    }

    function refreshRows() {
        const filtered = filterResults(runtime.getDetailsSourceCache(), filterState());
        const total = Math.max(1, Math.ceil((filtered.length || 0) / runtime.getDetailsPageSize()));
        runtime.setDetailsCurrentPage(Math.min(Math.max(1, runtime.getDetailsCurrentPage()), total));
        window.renderDetailsRows(filtered);
    }

    function advancePage() {
        const total = Math.max(1, Math.ceil((runtime.getDetailsResultsCache().length || 0) / runtime.getDetailsPageSize()));
        if (runtime.getDetailsCurrentPage() >= total) return;

        const start = (runtime.getDetailsCurrentPage() - 1) * runtime.getDetailsPageSize();
        const rows = (runtime.getDetailsResultsCache() || []).slice(start, start + runtime.getDetailsPageSize());
        if (rows.length === 0) return;

        const wait = rows.some((r) => !r.semgrep || !r.semgrep.status || ['pending'].includes(String(r.semgrep.status).toLowerCase()));
        const run = rows.some((r) => r.semgrep && ['running'].includes(String(r.semgrep.status).toLowerCase()));

        if (!wait && !run) {
            runtime.setDetailsCurrentPage(Math.min(runtime.getDetailsCurrentPage() + 1, total));
            window.renderDetailsRows(runtime.getDetailsResultsCache());
        }
    }

    function bulkState(stats, slug) {
        const running = Number(stats.running_count || 0);
        const pending = Number(stats.pending_count || 0);
        const total = Number(stats.total_plugins || 0);
        const scanned = Number(stats.scanned_count || 0);
        const findings = stats.total_findings || 0;

        if (stats.is_running) {
            return {
                state: 'running',
                meta: { scanned, total, currentSlug: slug },
                shouldAutoAdvance: true,
            };
        }
        if (running === 0 && pending === 0 && scanned > 0) {
            return { state: 'completed', meta: { findings }, shouldAutoAdvance: false };
        }
        if ((running > 0 || pending > 0) && scanned > 0) {
            return { state: 'paused', meta: {}, shouldAutoAdvance: false };
        }
        if (total > 0 && scanned >= total) {
            return { state: 'completed', meta: { findings }, shouldAutoAdvance: false };
        }
        return { state: 'idle', meta: {}, shouldAutoAdvance: false };
    }

    window.refreshDetailsBulkStatus = async function(sid) {
        const statsRes = await fetch(`/api/semgrep/bulk/${sid}/stats`);
        const stats = await statsRes.json();

        const res = await fetch(apiNoCacheUrl(`/api/scans/${sid}/results?limit=500`));
        const data = await res.json();
        window.currentScanResults = data.results || [];
        runtime.setDetailsSourceCache(window.currentScanResults);

        let slug = '';
        const item = window.currentScanResults.find((r) => r.semgrep && ['running', 'pending'].includes(String(r.semgrep.status || '').toLowerCase()));
        if (item) slug = String(item.slug || '');

        window.renderDetailsDashboard(window.currentScanResults);
        refreshRows();

        const bulk = bulkState(stats, slug);
        window.setDetailsBulkControls(bulk.state, bulk.meta);
        if (bulk.shouldAutoAdvance) {
            advancePage();
        }

        return stats;
    };

    window.startDetailsBulkSemgrep = async function() {
        if (!runtime.getCurrentScanId()) return;

        try {
            const res = await fetch('/api/semgrep/rules');
            const data = await res.json();
            const sets = (data.rulesets || []).filter(r => r.enabled).length;
            const custom = (data.custom_rules || []).filter(r => r.enabled).length;
            if (sets === 0 && custom === 0) {
                showToast('Semgrep is disabled. Enable at least one ruleset first.', 'warn');
                switchTab('semgrep');
                return;
            }
        } catch (err) {
            showToast('Failed to check Semgrep configuration.', 'error');
            return;
        }

        const ok = await showConfirm('Start Semgrep scan for all plugins in this scan?');
        if (!ok) return;

        try {
            const res = await fetch(`/api/semgrep/bulk/${runtime.getCurrentScanId()}`, { method: 'POST' });
            const data = await res.json();
            if (!data.success) {
                showToast('Failed to start bulk scan: ' + (data.detail || 'Unknown error'), 'error');
                return;
            }

            window.setDetailsBulkControls('running', { scanned: 0, total: data.count || 0 });

            const prev = runtime.getDetailsBulkPollingInterval();
            if (prev) clearInterval(prev);
            const timer = setInterval(async () => {
                try {
                    const stats = await window.refreshDetailsBulkStatus(runtime.getCurrentScanId());
                    if (!stats.is_running) {
                        clearInterval(timer);
                        runtime.setDetailsBulkPollingInterval(null);
                    }
                } catch (err) {
                    console.error('Details bulk polling error', err);
                }
            }, 1500);
            runtime.setDetailsBulkPollingInterval(timer);
        } catch (err) {
            showToast('Error: ' + err.message, 'error');
        }
    };

    window.stopDetailsBulkSemgrep = async function() {
        if (!runtime.getCurrentScanId()) return;
        const ok = await showConfirm('Stop bulk Semgrep scan?');
        if (!ok) return;

        try {
            const res = await fetch(`/api/semgrep/bulk/${runtime.getCurrentScanId()}/stop`, { method: 'POST' });
            const data = await res.json();
            if (data.success) {
                window.setDetailsBulkControls('paused');
            }
        } catch (err) {
            showToast('Error: ' + err.message, 'error');
        }
    };

    window.initializeDetailsFilters = function() {
        if (runtime.getDetailsFiltersInitialized()) return;
        const qEl = document.getElementById('details-filter-query');
        const iEl = document.getElementById('details-filter-installs');
        const sEl = document.getElementById('details-filter-sort');
        const uEl = document.getElementById('details-filter-updated-sort');

        const ctrls = [qEl, iEl, sEl, uEl].filter(Boolean);
        if (ctrls.length === 0) return;

        ctrls.forEach((ctrl) => {
            const evt = ctrl.tagName === 'SELECT' ? 'change' : 'input';
            ctrl.addEventListener(evt, window.applyDetailsFilters);
        });

        runtime.setDetailsFiltersInitialized(true);
    };
})();
