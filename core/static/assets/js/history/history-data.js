(function() {
    const runtime = window.zetatechRuntime;
    const cache = new Map();

    function semgrepState(stats, theme = false) {
        if (theme) {
            return {
                cls: 'na',
                state: 'N/A',
                count: '--',
                progress: 0,
                title: 'Semgrep is not available for theme sessions.'
            };
        }

        if (!stats) {
            return {
                cls: 'empty',
                state: 'WAIT',
                count: '--/--',
                progress: 0,
                title: 'Semgrep data is not available for this session yet.'
            };
        }

        const scanned = parseInt(stats.scanned_count || 0, 10) || 0;
        const total = parseInt(stats.total_plugins || 0, 10) || 0;
        const findings = parseInt(stats.total_findings || 0, 10) || 0;
        const pct = Math.max(0, Math.min(100, parseInt(stats.progress || 0, 10) || 0));
        const safe = total > 0 ? total : Math.max(scanned, 0);
        const pair = safe > 0 ? `${scanned}/${safe}` : '--/--';

        if (stats.is_running) {
            return {
                cls: 'running',
                state: 'RUN',
                count: pair,
                progress: pct,
                title: `Semgrep scanning in progress (${pct}% - ${pair}).`
            };
        }

        if (scanned === 0) {
            return {
                cls: 'empty',
                state: 'WAIT',
                count: safe > 0 ? `0/${safe}` : '0/0',
                progress: 0,
                title: 'Semgrep has not run for this session yet.'
            };
        }

        if (pct >= 100 || (safe > 0 && scanned >= safe)) {
            if (findings > 0) {
                return {
                    cls: 'alert',
                    state: 'ISSUE',
                    count: String(findings),
                    progress: 100,
                    title: `${findings} findings detected (${pair} analyzed).`
                };
            }
            return {
                cls: 'complete',
                state: 'CLEAN',
                count: pair,
                progress: 100,
                title: `Semgrep completed clean (${pair} analyzed).`
            };
        }

        return {
            cls: 'partial',
            state: 'PART',
            count: pair,
            progress: pct,
            title: `Partial semgrep progress (${pair}, ${findings} findings).`
        };
    }

    function setBadge(sid, stats, theme = false) {
        const cell = document.getElementById(`history-semgrep-${sid}`);
        const stateEl = document.getElementById(`history-semgrep-state-${sid}`);
        const countEl = document.getElementById(`history-semgrep-count-${sid}`);
        const fillEl = document.getElementById(`history-semgrep-fill-${sid}`);
        if (!cell || !stateEl || !countEl || !fillEl) return;

        const state = semgrepState(stats, theme);
        cell.className = `history-semgrep-cell ${state.cls}`;
        cell.title = state.title;
        stateEl.textContent = state.state;
        countEl.textContent = state.count;
        fillEl.style.width = `${state.progress}%`;
    }

    window.hydrateHistorySemgrepBadges = async function(sessions) {
        const pending = (sessions || []).map(async (session) => {
            const sid = parseInt(session.id, 10);
            if (!Number.isFinite(sid) || sid <= 0) return;

            const cfg = session.config || {};
            const theme = Boolean(cfg.themes);
            if (theme) {
                setBadge(sid, null, true);
                return;
            }

            const hit = cache.get(sid);
            if (hit) {
                setBadge(sid, hit, false);
                return;
            }

            try {
                const res = await fetch(apiNoCacheUrl(`/api/semgrep/bulk/${sid}/stats`));
                if (!res.ok) {
                    setBadge(sid, null, false);
                    return;
                }
                const stats = await res.json();
                cache.set(sid, stats);
                setBadge(sid, stats, false);
            } catch (_) {
                setBadge(sid, null, false);
            }
        });

        await Promise.allSettled(pending);
    };

    window.loadHistory = async function() {
        try {
            cache.clear();
            const res = await fetch(apiNoCacheUrl('/api/scans'));
            const data = await res.json();
            const sessions = (data.sessions || []).sort((a, b) => new Date(b.created_at || b.start_time) - new Date(a.created_at || a.start_time));
            runtime.setHistorySessionsCache(sessions);
            refreshScanDashboard(sessions);
            initializeHistoryFilters();
            applyHistoryFilters();
        } catch (_) {
            const list = document.getElementById('history-list');
            runtime.setHistorySessionsCache([]);
            if (list) list.innerHTML = '<tr><td colspan="8">Error loading history</td></tr>';
            refreshScanDashboard([]);
        }
    };

    window.deleteScan = async function(id) {
        const ok = await showConfirm('Are you sure you want to delete this scan session? This will remove all associated results from the database.');
        if (!ok) return;
        try {
            const res = await fetch(`/api/scans/${id}`, { method: 'DELETE' });
            if (res.ok) {
                loadHistory();
            } else {
                const err = await res.json();
                showToast('Failed to delete scan: ' + (err.detail || 'Unknown error'), 'error');
            }
        } catch (err) {
            showToast('Error deleting scan: ' + err.message, 'error');
        }
    };
})();
