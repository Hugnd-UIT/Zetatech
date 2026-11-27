(function() {
    const runtime = window.zetatechRuntime;

    function runMarkup() {
        return '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg><span>RUN SCAN</span>';
    }

    function resetRun(btn) {
        if (!btn) return;
        btn.disabled = false;
        btn.innerHTML = runMarkup();
    }

    function scanReq(form) {
        const pages = preparePagesValueBeforeScan();
        const fd = new FormData(form);

        return {
            pages,
            limit: parseInt(fd.get('limit'), 10) || 0,
            min_installs: parseInt(fd.get('min_installs'), 10) || 0,
            max_installs: parseInt(fd.get('max_installs'), 10) || 0,
            sort: fd.get('sort') || 'updated',
            smart: fd.get('smart') === 'on',
            abandoned: fd.get('abandoned') === 'on',
            user_facing: fd.get('user_facing') === 'on',
            themes: fd.get('themes') === 'on',
            min_days: parseInt(fd.get('min_days'), 10) || 0,
            max_days: parseInt(fd.get('max_days'), 10) || 0,
        };
    }

    function startRun(btn) {
        if (!btn) return;
        btn.disabled = true;
        btn.innerHTML = '<span>STARTING...</span>';
    }

    function setStatus(label, tone) {
        const el = document.getElementById('scan-status');
        if (!el) return;
        el.textContent = label;
        el.className = `metric-value info-value ${tone}`;
    }

    function markRun() {
        setStatus('RUNNING', 'running');
    }

    function markDone() {
        setStatus('COMPLETED', 'completed');
    }

    function markCancel() {
        setStatus('CANCELLED', 'cancelled');
    }

    function markFail() {
        setStatus('FAILED', 'failed');
    }

    function markMerge() {
        setStatus('MERGED', 'completed');
    }

    function startPoll(sid) {
        stopPoll();
        const timer = setInterval(() => {
            if (runtime.getCurrentScanId() === sid) {
                window.viewScan(sid);
                return;
            }
            clearInterval(timer);
            runtime.setDetailsPollingInterval(null);
        }, 3000);
        runtime.setDetailsPollingInterval(timer);
    }

    function stopPoll() {
        const timer = runtime.getDetailsPollingInterval();
        if (timer) {
            clearInterval(timer);
            runtime.setDetailsPollingInterval(null);
        }
    }

    function closeSock() {
        const sock = runtime.getSocket();
        if (sock) sock.close();
    }

    function setResults(res) {
        window.currentScanResults = Array.isArray(res) ? res : [];
    }

    function getResults() {
        return Array.isArray(window.currentScanResults) ? window.currentScanResults : [];
    }

    window.refreshAfterScanEvent = function(sid) {
        loadHistory();
        const view = document.getElementById('catalog-view');
        if (view && view.style.display !== 'none') {
            loadCatalog();
        }
        if (!sid) return;

        if (isDetailsViewActive() && runtime.getCurrentScanId() === sid) {
            setTimeout(() => {
                if (runtime.getCurrentScanId() === sid) window.viewScan(sid);
            }, 250);
            setTimeout(() => {
                if (runtime.getCurrentScanId() === sid) window.viewScan(sid);
            }, 1200);
        }
    };

    window.syncFinalScanResults = async function(sid, total = 0) {
        if (!sid || !isDetailsViewActive()) return;
        const target = parseInt(total || 0, 10);
        for (let i = 0; i < 6; i += 1) {
            if (runtime.getCurrentScanId() !== sid) return;
            await window.viewScan(sid);
            const cur = getResults().length;
            if (target <= 0 || cur >= target) return;
            await new Promise((resolve) => setTimeout(resolve, 350 * (i + 1)));
        }
    };

    window.setScanProgressState = function(pct, stage, detail) {
        const fill = document.getElementById('scan-progress-fill');
        const track = document.getElementById('scan-progress-track');
        const pctEl = document.getElementById('scan-progress-percent');
        const stageEl = document.getElementById('scan-stage-text');
        const detailEl = document.getElementById('scan-stage-subtext');

        if (!fill || !track) return;

        const curPct = Number(fill.dataset.percent || '0');
        const val = pct == null ? curPct : Math.max(0, Math.min(100, Number(pct)));

        fill.style.width = `${val}%`;
        fill.dataset.percent = String(val);
        track.setAttribute('aria-valuenow', String(Math.round(val)));

        if (pctEl) pctEl.textContent = `${Math.round(val)}%`;
        if (stageEl && stage) stageEl.textContent = stage;
        if (detailEl && detail) detailEl.textContent = detail;
    };

    window.setProgressDetailsButton = function(visible) {
        const btn = document.getElementById('scan-progress-details-btn');
        if (!btn) return;
        const sid = runtime.getCurrentScanId();
        if (visible && sid) {
            btn.dataset.scanId = String(sid);
        } else if (!visible) {
            delete btn.dataset.scanId;
        }
        const show = Boolean(visible) && Boolean(sid || btn.dataset.scanId);
        btn.style.display = show ? 'inline-flex' : 'none';
    };

    window.openProgressScanDetails = function() {
        const btn = document.getElementById('scan-progress-details-btn');
        const sid = runtime.getCurrentScanId() || parseInt(btn?.dataset.scanId || '0', 10);
        if (!sid) return;
        window.viewScan(sid);
    };

    window.logTerminal = function(text, type = 'info') {
        const map = {
            error: 'Failed',
            'high-risk': 'Warning',
            success: 'Completed',
            warn: 'Notice',
            info: 'Running'
        };
        const stage = map[type] || 'Running';
        window.setScanProgressState(null, stage, text);
    };

    window.clearTerminal = function() {
        window.setScanProgressState(0, 'Initializing', 'Preparing scan session...');
        window.setProgressDetailsButton(false);
    };

    window.connectWebSocket = function(sid) {
        const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${proto}//${window.location.host}/ws/scans/${sid}`;
        closeSock();

        const ws = new WebSocket(url);
        runtime.setSocket(ws);

        ws.onopen = () => {
            if (runtime.getSocket() !== ws) return;
            window.logTerminal('WebSocket connected', 'info');
            window.setScanProgressState(10, 'Running', 'Realtime channel connected');
        };
        ws.onmessage = (event) => {
            if (runtime.getSocket() !== ws) return;
            const payload = JSON.parse(event.data);
            window.handleMessage(payload, sid);
        };
        ws.onclose = () => {
            if (runtime.getSocket() !== ws) return;
            window.logTerminal('WebSocket connection closed', 'info');
            window.reconcileScanStatus(sid);
        };
        ws.onerror = () => {
            if (runtime.getSocket() !== ws) return;
            window.logTerminal('WebSocket error', 'error');
            window.reconcileScanStatus(sid);
        };
    };

    window.reconcileScanStatus = async function(sid) {
        if (!sid) return;
        if (runtime.getCurrentScanId() !== sid) return;

        const btn = document.getElementById('runBtn');
        try {
            const res = await fetch(apiNoCacheUrl(`/api/scans/${sid}`));
            if (!res.ok) return;
            const session = await res.json();
            const status = String(session.status || '').toLowerCase();
            const found = Number(session.total_found || 0);
            const high = Number(session.high_risk_count || 0);

            if (status === 'completed') {
                markDone();
                window.setScanProgressState(100, 'Completed', `Found ${found} total / ${high} high risk`);
                window.setProgressDetailsButton(true);
                window.refreshAfterScanEvent(sid);
            } else if (status === 'cancelled') {
                markCancel();
                window.setScanProgressState(100, 'Cancelled', `Found ${found} total / ${high} high risk`);
                window.setProgressDetailsButton(true);
                window.refreshAfterScanEvent(sid);
            } else if (status === 'failed') {
                markFail();
                window.setScanProgressState(100, 'Failed', 'Scan terminated with an error');
                window.setProgressDetailsButton(false);
                window.refreshAfterScanEvent(sid);
            }
        } catch (err) {
            console.error('Failed to reconcile scan status:', err);
        } finally {
            resetRun(btn);
        }
    };

    window.handleMessage = function(msg, sourceSid = null) {
        const btn = document.getElementById('runBtn');
        const curId = runtime.getCurrentScanId();

        if (sourceSid && curId && Number(sourceSid) !== Number(curId)) return;
        if (msg && msg.session_id && curId && Number(msg.session_id) !== Number(curId)) return;

        switch (msg.type) {
            case 'start':
                window.logTerminal('Scan execution started...', 'info');
                window.setScanProgressState(12, 'Running', 'Execution started');
                window.setProgressDetailsButton(false);
                break;
            case 'progress': {
                const pct = Number(msg.percent || 0);
                const cur = Number(msg.current || 0);
                const total = Number(msg.total || 0);
                const val = Math.max(0, Math.min(100, Math.round(pct)));
                const detail = total > 0 ? `Processed ${cur}/${total} targets` : `Processed ${cur} targets`;
                window.setScanProgressState(val, 'Running', detail);
                break;
            }
            case 'result':
                window.logTerminal(`${msg.data.score >= 40 ? '[HIGH RISK]' : '[INFO]'} Found: ${msg.data.slug} (Score: ${msg.data.score})`, msg.data.score >= 40 ? 'high-risk' : 'low-risk');
                document.getElementById('scan-found').textContent = msg.found_count;
                appendTrendPoint(msg.found_count);
                window.setScanProgressState(null, 'Running', `Detected ${msg.found_count} findings`);
                break;
            case 'deduplicated':
                window.logTerminal(`Scan identical to Session #${msg.original_session_id}. Merging...`, 'warn');
                window.logTerminal('Session merged. History updated.', 'success');
                runtime.setCurrentScanId(msg.original_session_id);
                markMerge();
                resetRun(btn);
                window.setScanProgressState(100, 'Merged', `Merged into Session #${msg.original_session_id}`);
                window.setProgressDetailsButton(true);
                window.refreshAfterScanEvent(runtime.getCurrentScanId());
                break;
            case 'cancelled':
                window.logTerminal(`Scan cancelled. Found: ${msg.total_found || 0}, High Risk: ${msg.high_risk_count || 0}`, 'warn');
                markCancel();
                resetRun(btn);
                window.setScanProgressState(100, 'Cancelled', `Found ${msg.total_found || 0} total / ${msg.high_risk_count || 0} high risk`);
                window.setProgressDetailsButton(true);
                window.refreshAfterScanEvent(runtime.getCurrentScanId());
                stopPoll();
                break;
            case 'complete':
                window.logTerminal(`Scan completed. Found: ${msg.total_found}, High Risk: ${msg.high_risk_count}`, 'success');
                markDone();
                resetRun(btn);
                window.setScanProgressState(100, 'Completed', `Found ${msg.total_found} total / ${msg.high_risk_count} high risk`);
                window.setProgressDetailsButton(true);
                window.refreshAfterScanEvent(runtime.getCurrentScanId());
                if (runtime.getCurrentScanId() && isDetailsViewActive()) {
                    window.syncFinalScanResults(runtime.getCurrentScanId(), msg.total_found);
                }
                stopPoll();
                break;
            case 'error':
                window.logTerminal(`Error: ${msg.message}`, 'error');
                markFail();
                resetRun(btn);
                window.setScanProgressState(100, 'Failed', msg.message || 'Scan terminated with an error');
                window.setProgressDetailsButton(false);
                window.refreshAfterScanEvent(runtime.getCurrentScanId());
                stopPoll();
                break;
            default:
                break;
        }
    };

    window.runScan = async function() {
        const form = document.getElementById('configForm');
        const btn = document.getElementById('runBtn');
        const req = scanReq(form);

        startRun(btn);
        window.setProgressDetailsButton(false);
        window.clearTerminal();
        window.logTerminal('Initializing scan...', 'info');
        window.setScanProgressState(5, 'Starting', 'Submitting scan request');

        try {
            const res = await fetch('/api/scans', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(req)
            });
            const data = await res.json();

            if (!data.session_id) {
                window.logTerminal('Failed to start scan', 'error');
                window.setScanProgressState(100, 'Failed', 'Scan session could not be started');
                window.setProgressDetailsButton(false);
                resetRun(btn);
                return;
            }

            runtime.setCurrentScanId(data.session_id);
            window.logTerminal(`Scan session started: ID ${runtime.getCurrentScanId()}`, 'success');
            window.setScanProgressState(8, 'Starting', `Session #${runtime.getCurrentScanId()} created`);
            window.connectWebSocket(runtime.getCurrentScanId());
            markRun();
        } catch (err) {
            window.logTerminal(`Error: ${err.message}`, 'error');
            window.setScanProgressState(100, 'Failed', err.message || 'Unknown error');
            window.setProgressDetailsButton(false);
            resetRun(btn);
        }
    };

    function setScanBtn(state) {
        const btn = document.getElementById('btn-deep-scan');
        if (!btn) return;

        const setLabel = (label) => {
            btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg><span>${label}</span>`;
        };

        if (state === 'scanning') {
            btn.disabled = true;
            setLabel('SCANNING...');
            return;
        }

        if (state === 'rescan') {
            btn.disabled = false;
            setLabel('RE-SCAN');
            btn.style.borderColor = 'var(--accent-primary)';
            btn.style.color = 'var(--accent-primary)';
            btn.style.opacity = '1';
            btn.title = 'Run Semgrep scan again';
            return;
        }

        btn.disabled = false;
        setLabel('RE-SCAN');
        btn.style.borderColor = 'var(--accent-blue)';
        btn.style.color = 'var(--accent-blue)';
        btn.style.opacity = '1';
        btn.title = '';
    }

    function returnHash(urlState) {
        if (urlState.view && urlState.view !== 'plugin-detail') {
            if (urlState.view === 'details' && urlState.scanId) {
                return `details/${urlState.scanId}`;
            }
            return urlState.view;
        }

        const hash = runtime.getModalReturnHash();
        if (!hash || String(hash).startsWith('plugin/')) {
            return runtime.getCurrentScanId() ? `details/${runtime.getCurrentScanId()}` : 'history';
        }

        return hash;
    }

    function initAiPanel(plugin) {
        bindPluginAiUiEvents();
        const state = typeof window.getPluginAiState === 'function' ? window.getPluginAiState() : {};
        const same = String(state.plugin || '').trim() === String(plugin.slug || '').trim() && !!state.isTheme === !!plugin.is_theme;

        if (!same) {
            beginPluginAiView(plugin.slug, !!plugin.is_theme);
            renderPluginAiMessages([]);
            renderPluginAiActivity([]);
            setPluginAiBadge('Idle');
            setPluginAiStatus(`Preparing AI context for ${plugin.slug || plugin.name || 'plugin'}...`);
            setPluginAiComposerEnabled(false);
            return;
        }

        refreshPluginAiRenderedState();
        setPluginAiBadge(state.sending ? 'Running' : (typeof window.buildPluginAiThreadBadge === 'function' ? window.buildPluginAiThreadBadge() : 'Ready'));
        setPluginAiStatus(state.sending
            ? 'Restoring AI chat…'
            : `Restoring AI context for ${plugin.slug || plugin.name || 'plugin'}...`);
        setPluginAiComposerEnabled(!state.sending && !!state.threadId);
    }

    function tagsHtml(plugin) {
        let html = '';
        if (plugin.is_user_facing) html += '<span class="tag warn">USER FACING</span>';
        if (plugin.is_risky_category) html += '<span class="tag risk">RISKY CATEGORY</span>';
        if (plugin.author_trusted) html += '<span class="tag safe">TRUSTED AUTHOR</span>';
        if (plugin.is_duplicate) html += '<span class="tag" style="background: #333;">PREVIOUSLY FOUND</span>';
        return html || '<span class="tag">NO TAGS</span>';
    }

    function modalVm(plugin) {
        const type = plugin.is_theme ? 'theme' : 'plugin';
        const ver = plugin.version || 'latest';
        const url = plugin.download_link || `https://downloads.wordpress.org/${type}/${plugin.slug}.${ver}.zip`;
        const slug = String(plugin.slug || '');
        const score = parseInt(plugin.score || 0, 10) || 0;

        return {
            pluginSlug: slug,
            pluginSlugJs: JSON.stringify(slug),
            downloadUrl: url,
            downloadUrlJs: JSON.stringify(String(url || '')),
            tagsHtml: tagsHtml(plugin),
            isFav: isFavoriteSlug(plugin.slug),
            pluginScore: score,
            pluginScoreColor: getRiskColorForScore(score),
            semgrepFindings: String((plugin.semgrep && plugin.semgrep.findings_count) || plugin.latest_semgrep_findings || 0),
        };
    }

    function renderModal(plugin, box) {
        if (!box) return null;
        const vm = modalVm(plugin);

        box.innerHTML = `
            <section class="plugin-hero">
                <div class="plugin-metrics-grid">
                    <article class="plugin-metric-card"><span class="plugin-metric-label">Risk Score</span><span class="plugin-metric-value" style="color:${vm.pluginScoreColor}">${vm.pluginScore}/100</span><span class="plugin-metric-sub">Current plugin risk level</span></article>
                    <article class="plugin-metric-card"><span class="plugin-metric-label">Installs</span><span class="plugin-metric-value">${escapeHtml(String(plugin.installations || 0))}+</span><span class="plugin-metric-sub">Active install footprint</span></article>
                    <article class="plugin-metric-card"><span class="plugin-metric-label">Updated</span><span class="plugin-metric-value">${escapeHtml(String(plugin.days_since_update || 0))}d</span><span class="plugin-metric-sub">Days since last update</span></article>
                    <article class="plugin-metric-card"><span class="plugin-metric-label">Semgrep</span><span class="plugin-metric-value">${escapeHtml(vm.semgrepFindings)}</span><span class="plugin-metric-sub">Known findings count</span></article>
                </div>
            </section>

            <section class="plugin-toolbar">
                <div class="plugin-toolbar-tags">${vm.tagsHtml}</div>
                <div class="plugin-toolbar-actions">
                    <button id="plugin-fav-btn" onclick='toggleFavorite(${vm.pluginSlugJs})' class="action-btn details-fav-btn plugin-fav-inline${vm.isFav ? ' active' : ''}" title="${vm.isFav ? 'In Favorites' : 'Add to Favorites'}" aria-label="${vm.isFav ? 'Remove from' : 'Add to'} favorites">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path></svg>
                    </button>
                    <a href="${escapeHtml(vm.downloadUrl)}" target="_blank" rel="noreferrer noopener" class="action-btn plugin-action-download"><span>DOWNLOAD ZIP</span></a>
                    <button id="btn-deep-scan" onclick='runPluginSemgrep(${vm.pluginSlugJs}, ${vm.downloadUrlJs})' class="action-btn plugin-action-secondary">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>
                        <span>RE-SCAN</span>
                    </button>
                </div>
            </section>

            <section class="plugin-section">
                <div class="section-title">Semgrep Analysis</div>
                <div id="semgrep-results-container"><div class="plugin-semgrep-empty">No Semgrep analysis yet. Click <strong>RE-SCAN</strong> to run deep static analysis for this plugin.</div></div>
            </section>
        `;

        return vm;
    }

    function loadSemgrep(slug) {
        fetch(`/api/semgrep/scan/${slug}`)
            .then((res) => res.json())
            .then((data) => {
                if (data.status === 'completed') {
                    renderSemgrep(data);
                } else if (data.status === 'running' || data.status === 'pending') {
                    document.getElementById('semgrep-results-container').innerHTML = '<div class="plugin-semgrep-empty">Semgrep scan in progress...</div>';
                    setScanBtn('scanning');
                    pollSemgrep(slug);
                }
            })
            .catch(() => {});
    }

    function checkSemgrep() {
        fetch('/api/semgrep/rules')
            .then((res) => res.json())
            .then((rules) => {
                const sets = (rules.rulesets || []).filter((r) => r.enabled).length;
                const custom = (rules.custom_rules || []).filter((r) => r.enabled).length;
                const btn = document.getElementById('btn-deep-scan');

                if (btn && sets === 0 && custom === 0) {
                    btn.disabled = true;
                    btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right: 5px;"><path d="M12 15v.01M12 12v.01M12 9v.01M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg> DISABLED';
                    btn.title = 'Enable rulesets in Semgrep Settings to use this feature';
                    btn.style.opacity = '0.6';
                }
            })
            .catch(() => {});
    }

    function renderSemgrep(scan) {
        const box = document.getElementById('semgrep-results-container');
        if (!box) return;

        const findings = Array.isArray(scan && scan.findings) ? scan.findings : null;
        const sum = (scan && scan.summary && typeof scan.summary === 'object') ? scan.summary : {};
        const total = Number(sum.total_findings || 0);
        const doneAt = scan && scan.completed_at ? String(scan.completed_at) : '';
        const done = String((scan && scan.status) || '').toLowerCase() === 'completed';
        const errs = Array.isArray(sum.errors) ? sum.errors.filter(Boolean) : [];

        if (!scan || !done || findings === null) {
            box.innerHTML = '<div class="plugin-semgrep-empty">Semgrep result is incomplete or unavailable right now. Please retry the scan or refresh this plugin view.</div>';
            setScanBtn('rescan');
            return;
        }

        if (findings.length === 0 && total === 0) {
            const label = doneAt ? ` Last completed: <strong>${escapeHtml(doneAt)}</strong>.` : '';
            const warn = errs.length
                ? `<div class="plugin-semgrep-summary" style="border-left-color: var(--warn); margin-bottom: 12px;">Scan completed with parser/runtime warnings:<br>${errs.slice(0, 5).map((err) => `• ${escapeHtml(String(err))}`).join('<br>')}</div>`
                : '';
            box.innerHTML = `${warn}<div class="plugin-semgrep-empty">No issues were reported by the latest completed Semgrep scan.${label}</div>`;
            setScanBtn('rescan');
            return;
        }

        const counts = (sum && sum.breakdown) ? sum.breakdown : {};
        const warn = errs.length
            ? `<div class="plugin-semgrep-summary" style="border-left-color: var(--warn); margin-bottom: 12px;">Scan completed with parser/runtime warnings:<br>${errs.slice(0, 5).map((err) => `• ${escapeHtml(String(err))}`).join('<br>')}</div>`
            : '';

        let html = `${warn}<div class="plugin-semgrep-summary">Found <strong>${findings.length}</strong> issues (ERROR: <span class="sev-error">${counts.ERROR || 0}</span>, WARNING: <span class="sev-warning">${counts.WARNING || 0}</span>)</div>`;

        html += findings.map((f) => {
            const sev = String(f.severity || 'INFO').toUpperCase();
            const cls = sev === 'ERROR' ? 'error' : (sev === 'WARNING' ? 'warning' : 'info');
            const path = `${escapeHtml(String(f.file_path || ''))}${f.line_number ? `:${f.line_number}` : ''}`;
            return `
                <article class="plugin-semgrep-item ${cls}">
                    <header class="plugin-semgrep-item-head">
                        <span class="plugin-semgrep-rule">${escapeHtml(sev)}: ${escapeHtml(String(f.rule_id || 'unknown-rule'))}</span>
                        <span class="plugin-semgrep-file">${path}</span>
                    </header>
                    <p class="plugin-semgrep-message">${escapeHtml(String(f.message || 'No description provided.'))}</p>
                    ${f.code_snippet ? `<pre class="plugin-semgrep-code"><code>${escapeHtml(String(f.code_snippet || ''))}</code></pre>` : ''}
                </article>
            `;
        }).join('');

        box.innerHTML = html;
        setScanBtn('rescan');
    }

    async function pollSemgrep(slug) {
        const timer = setInterval(async () => {
            try {
                const res = await fetch(`/api/semgrep/scan/${slug}`);
                const data = await res.json();

                if (data.status === 'completed') {
                    clearInterval(timer);
                    renderSemgrep(data);
                    const errs = Array.isArray(data && data.summary && data.summary.errors) ? data.summary.errors.filter(Boolean) : [];
                    if (errs.length) {
                        showToast(`Semgrep scan completed with ${errs.length} warning(s). Findings were preserved.`, 'warn');
                    }
                } else if (data.status === 'failed') {
                    clearInterval(timer);
                    showToast('Semgrep scan failed: ' + (data.error_message || 'Unknown error'), 'error');
                    setScanBtn('rescan');
                }
            } catch (_) {
                clearInterval(timer);
            }
        }, 3000);
    }

    window.runPluginSemgrep = async function(slug, url) {
        try {
            const res = await fetch('/api/semgrep/rules');
            const data = await res.json();
            const sets = (data.rulesets || []).filter((r) => r.enabled).length;
            const custom = (data.custom_rules || []).filter((r) => r.enabled).length;

            if (sets === 0 && custom === 0) {
                showToast('Semgrep is disabled. Please enable at least one ruleset in Semgrep Settings.', 'warn');
                switchTab('semgrep');
                return;
            }
        } catch (_) {
            showToast('Failed to check Semgrep configuration.', 'error');
            return;
        }

        const ok = await showConfirm(`Run deep Semgrep analysis on ${slug}? This may take a few minutes.`);
        if (!ok) return;

        setScanBtn('scanning');

        try {
            const res = await fetch('/api/semgrep/scan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ slug, download_url: url })
            });

            const data = await res.json();
            if (data.success) {
                showToast('Semgrep scan started in background. Check back in a few minutes.', 'success');
                pollSemgrep(slug);
            } else {
                showToast('Failed to start scan', 'error');
                setScanBtn('rescan');
            }
        } catch (err) {
            showToast('Error: ' + err.message, 'error');
            setScanBtn('rescan');
        }
    };

    window.viewScan = async function(id, opts = {}) {
        const { syncUrl = true } = opts;
        switchTab('details', { syncUrl: false });
        runtime.setCurrentScanId(id);
        if (syncUrl) {
            setUrlState({ view: 'details', scanId: id, plugin: '' }, { replace: false });
        }

        const list = document.getElementById('details-list');
        const title = document.getElementById('details-view-title');
        const desc = document.getElementById('details-view-desc');

        if (title) title.textContent = `SCAN #${id} DETAILS`;
        if (desc) desc.textContent = `Inspect plugins found in scan #${id} and review risk context.`;
        if (list) list.innerHTML = '<tr><td colspan="7" class="favorites-empty">Loading results...</td></tr>';

        try {
            const sRes = await fetch(apiNoCacheUrl(`/api/scans/${id}`));
            const session = await sRes.json();

            const rRes = await fetch(apiNoCacheUrl(`/api/scans/${id}/results?limit=500`));
            const rData = await rRes.json();
            setResults(rData.results || []);
            runtime.setDetailsSourceCache(getResults());
            await refreshFavoriteSlugs();

            initializeDetailsFilters();
            runtime.setDetailsCurrentPage(1);
            window.renderDetailsDashboard(getResults());
            applyDetailsFilters();

            const prev = runtime.getDetailsBulkPollingInterval();
            if (prev) {
                clearInterval(prev);
                runtime.setDetailsBulkPollingInterval(null);
            }
            const bulk = await window.refreshDetailsBulkStatus(id);
            if (bulk && bulk.is_running) {
                const timer = setInterval(async () => {
                    try {
                        const stats = await window.refreshDetailsBulkStatus(id);
                        if (!stats.is_running) {
                            clearInterval(timer);
                            runtime.setDetailsBulkPollingInterval(null);
                        }
                    } catch (err) {
                        console.error('Details bulk polling error', err);
                    }
                }, 1500);
                runtime.setDetailsBulkPollingInterval(timer);
            }

            if ((session.status || '').toUpperCase() === 'RUNNING') {
                startPoll(id);
            } else {
                stopPoll();
            }
        } catch (_) {
            window.setDetailsBulkControls('idle');
            window.renderDetailsDashboard([]);
            if (list) list.innerHTML = '<tr><td colspan="7" class="favorites-empty">Failed to load scan details</td></tr>';
        }
    };

    window.openPluginModal = function(idx, opts = {}) {
        const { syncUrl = true } = opts;
        const plugin = getResults()[idx];
        if (!plugin) return;

        const url = getUrlState();
        runtime.setModalReturnHash(returnHash(url));

        if (syncUrl) {
            setUrlState({
                view: 'plugin-detail',
                scanId: runtime.getCurrentScanId() || url.scanId || null,
                plugin: plugin.slug,
            }, { replace: false });
        }

        switchTab('plugin-detail', { syncUrl: false });

        const title = document.getElementById('plugin-page-title');
        const desc = document.getElementById('plugin-page-desc');
        const box = document.getElementById('plugin-page-content');

        if (title) title.textContent = String(plugin.slug || plugin.name || 'PLUGIN').toUpperCase();
        if (desc) desc.textContent = `Inspect metadata and Semgrep findings for ${plugin.slug || plugin.name || 'the selected plugin'}.`;

        initAiPanel(plugin);
        if (!box) return;

        renderModal(plugin, box);
        setScanBtn('default');
        ensurePluginAiThread(plugin);
        loadSemgrep(plugin.slug);
        checkSemgrep();
    };

    window.closeModal = function() {
        const fb = runtime.getCurrentScanId() ? `details/${runtime.getCurrentScanId()}` : 'history';
        const cur = runtime.getModalReturnHash();
        const target = cur && !String(cur).startsWith('plugin/') ? cur : fb;

        if (String(target).startsWith('details/')) {
            const sid = parseInt(String(target).split('/')[1], 10);
            const resolved = Number.isFinite(sid) ? sid : (runtime.getCurrentScanId() || null);
            if (resolved) {
                setUrlState({ view: 'details', scanId: resolved, plugin: '' }, { replace: false });
                window.viewScan(resolved, { syncUrl: false });
                return;
            }
        }

        const tab = runtime.getViewToTab()[String(target)] || 'history';
        setUrlState({ view: runtime.getTabToView()[tab] || 'history', scanId: null, plugin: '' }, { replace: false });
        switchTab(tab, { syncUrl: false });
    };
})();
