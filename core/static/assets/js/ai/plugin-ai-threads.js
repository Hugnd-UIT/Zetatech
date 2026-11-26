(function() {
    function stopSync() {
        const state = window.getPluginAiState();
        if (state.threadSyncPollTimer) {
            window.clearTimeout(state.threadSyncPollTimer);
            state.threadSyncPollTimer = null;
        }
        state.threadSyncPollKey = null;
    }

    function startSync(opts = {}) {
        const state = window.getPluginAiState();
        const slug = String(opts.slug || state.plugin || '').trim();
        const tid = Number(opts.threadId || state.threadId || 0);
        const token = opts.viewToken ?? state.viewToken;
        if (!slug || !tid) return;

        const key = `${slug}::${tid}::${token}`;
        if (state.threadSyncPollKey === key && state.threadSyncPollTimer) return;

        stopSync();
        state.threadSyncPollKey = key;

        let ticks = 0;
        const poll = async () => {
            const live = window.getPluginAiState();
            if (!window.isPluginAiViewCurrent(slug, token) || Number(live.threadId || 0) !== tid) {
                stopSync();
                return;
            }
            if (live.loading) {
                live.threadSyncPollTimer = window.setTimeout(poll, 600);
                return;
            }

            await loadMsgs({ slug, threadId: tid, viewToken: token, silent: true });
            ticks += 1;
            const delay = ticks <= 4 ? 500 : 1500;
            live.threadSyncPollTimer = window.setTimeout(poll, delay);
        };

        state.threadSyncPollTimer = window.setTimeout(poll, 120);
    }

    function stopPoll() {
        const state = window.getPluginAiState();
        if (state.pendingRunPollTimer) {
            window.clearTimeout(state.pendingRunPollTimer);
            state.pendingRunPollTimer = null;
        }
        state.pendingRunPollKey = null;
    }

    function startPoll(opts = {}) {
        const state = window.getPluginAiState();
        const slug = String(opts.slug || state.plugin || '').trim();
        const tid = Number(opts.threadId || state.threadId || 0);
        const token = opts.viewToken ?? state.viewToken;
        if (!slug || !tid) return;

        const key = `${slug}::${tid}::${token}`;
        if (state.pendingRunPollKey === key && state.pendingRunPollTimer) {
            return;
        }

        stopPoll();
        stopSync();
        state.pendingRunPollKey = key;

        const poll = async () => {
            if (!window.isPluginAiViewCurrent(slug, token) || Number(window.getPluginAiState().threadId || 0) !== tid) {
                stopPoll();
                return;
            }

            const res = await loadMsgs({ slug, threadId: tid, viewToken: token });
            if (!res?.hasPendingRun) {
                stopPoll();
                if (window.isPluginAiViewCurrent(slug, token) && Number(window.getPluginAiState().threadId || 0) === tid) {
                    state.sending = false;
                    window.setPluginAiBadge(window.buildPluginAiThreadBadge());
                    window.updatePluginAiComposerState(true);
                    window.setPluginAiResponseReceivedStatus();
                }
                return;
            }

            state.pendingRunPollTimer = window.setTimeout(poll, 800);
        };

        state.pendingRunPollTimer = window.setTimeout(poll, 180);
    }

    async function loadThreads(plugin, opts = {}) {
        const state = window.getPluginAiState();
        const slug = String(plugin?.slug || state.plugin || '').trim();
        const theme = opts.isTheme ?? !!plugin?.is_theme ?? state.isTheme;
        const token = opts.viewToken ?? state.viewToken;
        if (!slug) return [];

        const res = await fetch(`/api/ai/threads/plugin?plugin_slug=${encodeURIComponent(slug)}&is_theme=${theme ? 'true' : 'false'}&_ts=${Date.now()}`, {
            cache: 'no-store',
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            throw new Error(data.detail || `HTTP ${res.status}`);
        }
        if (!window.isPluginAiViewCurrent(slug, token)) {
            return [];
        }
        const threads = Array.isArray(data.threads) ? data.threads : [];
        window.rememberPluginAiThreads(threads);
        window.renderPluginAiSessions(threads, state.threadId);
        return threads;
    }

    async function loadMsgs(opts = {}) {
        const state = window.getPluginAiState();
        const slug = String(opts.slug || state.plugin || '').trim();
        const token = opts.viewToken ?? state.viewToken;
        const tid = opts.threadId ?? state.threadId;
        const silent = !!opts.silent;

        if (tid && typeof window.hydratePluginAiThreadUiSnapshot === 'function') {
            const snap = window.hydratePluginAiThreadUiSnapshot(slug, tid, !!state.isTheme);
            if (snap && !silent) {
                window.refreshPluginAiRenderedState();
                if (snap.badgeText) {
                    window.setPluginAiBadge(snap.badgeText);
                }
                if (snap.statusText) {
                    window.setPluginAiStatus(snap.statusText);
                }
                if (snap.sending && snap.runStartedAt) {
                    if (state.runningIndicatorTimer) {
                        window.clearInterval(state.runningIndicatorTimer);
                    }
                    state.runningIndicatorTimer = window.setInterval(() => {
                        if (typeof window.refreshPluginAiRunningIndicators === 'function') {
                            window.refreshPluginAiRunningIndicators();
                        }
                    }, 1000);
                }
                window.updatePluginAiComposerState(!snap.sending && !!tid);
            }
        }

        if (!tid) {
            if (!slug || window.isPluginAiViewCurrent(slug, token)) {
                window.setPluginAiMessagesEmptyView();
                window.setPluginAiActivityEmptyView();
            }
            return { hasPendingRun: false, messages: [] };
        }

        try {
            const params = new URLSearchParams({
                plugin_slug: slug,
                is_theme: String(!!state.isTheme),
            });
            params.set('_ts', String(Date.now()));
            const res = await fetch(`/api/ai/threads/${tid}/messages?${params.toString()}`, {
                cache: 'no-store',
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                throw new Error(data.detail || `HTTP ${res.status}`);
            }
            if (slug && !window.isPluginAiViewCurrent(slug, token)) {
                return { hasPendingRun: false, messages: [] };
            }
            const msgs = window.extractPluginAiMessages(data);
            const items = Array.isArray(msgs) ? [...msgs] : [];
            const hasPending = !!data.has_pending_run;
            const pending = typeof window.getPluginAiPendingSnapshot === 'function'
                ? window.getPluginAiPendingSnapshot(slug, tid, !!state.isTheme)
                : null;
            const draft = String(pending?.content || '').trim();
            const hasUser = !!draft && items.some((item) => {
                const role = String(item?.role || '').trim();
                const content = String(item?.content || '').trim();
                return role === 'user' && content === draft;
            });
            const active = !!state.sending
                && Number(state.streamThreadId || 0) === Number(tid || 0)
                && !!String(state.streamRequestId || '').trim();
            const preserve = !hasPending && !!draft && !hasUser;
            if (hasUser && typeof window.clearPluginAiPendingSnapshot === 'function') {
                window.clearPluginAiPendingSnapshot(slug, tid, !!state.isTheme);
            }
            if (draft && !hasUser) {
                items.push({
                    id: `pending-user-${tid}`,
                    thread_id: tid,
                    role: 'user',
                    content: draft,
                    created_at: pending.createdAt || new Date().toISOString(),
                    tool_calls: [],
                    tool_results: [],
                });
            }
            if (hasPending || preserve || active) {
                if (!items.some((item) => item?.is_pending_assistant)) {
                    items.push({
                        id: `pending-refresh-${tid}`,
                        thread_id: tid,
                        role: 'assistant',
                        content: '',
                        created_at: new Date().toISOString(),
                        tool_calls: [],
                        tool_results: [],
                        is_pending_assistant: true,
                    });
                }
                if (!String(state.runStartedAt || '').trim()) {
                    state.runStartedAt = String(pending?.createdAt || new Date().toISOString());
                }
                state.sending = true;
                window.setPluginAiRunningBadge();
                if (!silent) {
                    window.setPluginAiStatus(window.buildPluginAiRunningStatusText(state.runStartedAt));
                }
                if (typeof window.startPluginAiPendingRunPoll === 'function') {
                    window.startPluginAiPendingRunPoll({ slug, threadId: tid, viewToken: token });
                }
            } else {
                state.sending = false;
                state.runStartedAt = '';
                if (state.runningIndicatorTimer) {
                    window.clearInterval(state.runningIndicatorTimer);
                    state.runningIndicatorTimer = null;
                }
                state.pendingSnapshotRetryInFlight = false;
                if (typeof window.clearPluginAiPendingSnapshot === 'function') {
                    window.clearPluginAiPendingSnapshot(slug, tid, !!state.isTheme);
                }
                if (typeof window.stopPluginAiPendingRunPoll === 'function') {
                    window.stopPluginAiPendingRunPoll();
                }
            }
            const cur = Array.isArray(state.messages) ? state.messages : [];
            const merged = preserve || active
                ? window.mergePluginAiMessages(cur, items)
                : window.mergePluginAiMessages([], items);
            window.capturePluginAiMessages(merged);
            state.pendingApproval = data.pending_approval && typeof data.pending_approval === 'object'
                ? data.pending_approval
                : null;
            const evts = Array.isArray(data.team_events) ? data.team_events : [];
            if (evts.length) {
                state.events = evts;
                state.liveActivity = state.events;
                if (typeof window.rememberPluginAiEventsSnapshot === 'function') {
                    window.rememberPluginAiEventsSnapshot({
                        plugin: slug,
                        threadId: tid,
                        isTheme: !!state.isTheme,
                        events: state.liveActivity,
                        createdAt: new Date().toISOString(),
                    });
                }
            } else {
                const snap = typeof window.getPluginAiEventsSnapshot === 'function'
                    ? window.getPluginAiEventsSnapshot(slug, tid, !!state.isTheme)
                    : null;
                const cached = Array.isArray(snap?.events) ? snap.events : [];
                if (cached.length) {
                    state.events = cached;
                    state.liveActivity = cached;
                } else {
                    window.capturePluginAiToolAudit(msgs);
                    state.liveActivity = state.events;
                }
            }
            window.refreshPluginAiRenderedState();
            if (typeof window.syncCurrentPluginAiThreadSnapshot === 'function') {
                window.syncCurrentPluginAiThreadSnapshot({
                    threadId: tid,
                    messages: state.messages,
                    events: state.events,
                    liveActivity: state.liveActivity,
                    sending: hasPending,
                    pendingApproval: state.pendingApproval,
                });
            }
            if (!hasPending) {
                window.notePluginAiMessagesLoaded(msgs);
            }
            return { hasPendingRun: hasPending, messages: msgs };
        } catch (err) {
            if (slug && !window.isPluginAiViewCurrent(slug, token)) {
                return { hasPendingRun: false, messages: [] };
            }
            if (!silent) {
                window.setPluginAiActivityEmptyView();
                window.setPluginAiStatus(`Unable to load AI messages: ${err.message}`);
            }
            return { hasPendingRun: false, messages: [] };
        }
    }

    async function switchThread(tid) {
        const state = window.getPluginAiState();
        const slug = String(state.plugin || '').trim();
        if (!tid || !slug) return;
        stopPoll();
        state.threadId = tid;
        if (typeof window.rememberPluginAiSelectedThread === 'function') {
            window.rememberPluginAiSelectedThread(slug, tid, !!state.isTheme);
        }
        if (typeof window.hydratePluginAiThreadUiSnapshot === 'function') {
            const snap = window.hydratePluginAiThreadUiSnapshot(slug, tid, !!state.isTheme);
            if (snap) {
                window.refreshPluginAiRenderedState();
                window.setPluginAiBadge(snap.badgeText || (snap.sending ? 'Running' : window.buildPluginAiThreadBadge()));
                window.setPluginAiStatus(snap.statusText || (snap.sending ? 'Restoring running chat…' : 'Restoring chat…'));
            } else {
                window.setPluginAiThreadLoadingBadge();
                window.setPluginAiStatus('Loading chat messages...');
            }
        } else {
            window.setPluginAiThreadLoadingBadge();
            window.setPluginAiStatus('Loading chat messages...');
        }
        window.updatePluginAiSessionUi();
        const res = await loadMsgs({ slug, threadId: tid, viewToken: state.viewToken });
        if (window.getPluginAiState().threadId === tid) {
            const active = !!state.sending
                && Number(state.streamThreadId || 0) === Number(tid || 0)
                && !!String(state.streamRequestId || '').trim();
            window.setPluginAiBadge(active ? 'Running' : window.buildPluginAiThreadBadge());
            window.updatePluginAiComposerState(!active);
            if (res?.hasPendingRun) {
                startPoll({ slug, threadId: tid, viewToken: state.viewToken });
            } else {
                startSync({ slug, threadId: tid, viewToken: state.viewToken });
            }
        }
    }

    async function createThread() {
        const state = window.getPluginAiState();
        const slug = String(state.plugin || '').trim();
        if (!slug || state.loading) return;

        try {
            state.pendingSnapshotRetryInFlight = false;
            if (typeof window.stopPluginAiPendingRunPoll === 'function') {
                window.stopPluginAiPendingRunPoll();
            }
            window.setPluginAiStatus('Creating new chat...');
            const res = await fetch('/api/ai/threads/plugin/new', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(window.buildPluginThreadRequest({ slug, is_theme: state.isTheme })),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                throw new Error(data.detail || `HTTP ${res.status}`);
            }
            await loadThreads({ slug, is_theme: state.isTheme }, { viewToken: state.viewToken });
            stopSync();
            window.rememberPluginAiThread(data);
            window.clearPluginAiTransientState(state);
            window.refreshPluginAiRenderedState();
            window.updatePluginAiSessionUi();
            window.setPluginAiBadge(window.buildPluginAiThreadBadge());
            window.setPluginAiStatus('New chat ready.');
        } catch (err) {
            window.setPluginAiErrorBadge();
            window.setPluginAiStatus(`Unable to create new chat: ${err.message}`);
        }
    }

    async function ensureThread(plugin) {
        const slug = String(plugin?.slug || '').trim();
        if (!slug) return null;

        if (typeof window.stopPluginAiPendingRunPoll === 'function') {
            window.stopPluginAiPendingRunPoll();
        }

        const state = window.getPluginAiState();
        if (window.currentPluginMatchesState(plugin, state) && state.threadId) {
            return state.threadId;
        }

        const prevId = Number(state.threadId || 0) || null;
        const prevSnap = typeof window.getPluginAiThreadUiSnapshot === 'function'
            ? window.getPluginAiThreadUiSnapshot(slug, prevId, !!plugin?.is_theme)
            : null;
        const token = window.startPluginAiView(plugin);
        state.loading = true;
        if (!(prevSnap && Array.isArray(prevSnap.messages) && prevSnap.messages.length)) {
            window.setPluginAiMessagesEmptyView();
            window.setPluginAiActivityEmptyView();
        }
        window.setPluginAiThreadLoadingBadge();
        window.setPluginAiThreadStatusLoading(plugin);
        window.updatePluginAiComposerState(false);

        try {
            let threads = await loadThreads(plugin, { viewToken: token, isTheme: !!plugin?.is_theme });
            if (!window.isPluginAiViewCurrent(slug, token)) {
                return null;
            }

            const savedId = typeof window.getPluginAiSelectedThread === 'function'
                ? window.getPluginAiSelectedThread(slug, !!plugin?.is_theme)
                : null;
            let tid = Array.isArray(threads)
                ? (threads.find((item) => Number(item?.id || 0) === Number(savedId || 0))?.id || null)
                : null;
            if (!tid) {
                tid = window.resolvePreferredPluginAiThreadId(threads);
            }
            if (!tid) {
                const res = await fetch('/api/ai/threads/plugin', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(window.buildPluginThreadRequest(plugin)),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    throw new Error(data.detail || `HTTP ${res.status}`);
                }
                threads = [data];
                window.rememberPluginAiThreads(threads);
                window.renderPluginAiSessions(threads, data.id);
                window.rememberPluginAiThread(data);
                tid = data.id;
            } else {
                const active = Array.isArray(threads) ? threads.find((item) => Number(item?.id || 0) === Number(tid || 0)) : null;
                window.rememberPluginAiThread(active || { id: tid, is_theme: !!plugin?.is_theme });
            }

            if (!tid || !window.isPluginAiViewCurrent(slug, token)) {
                return null;
            }

            window.updatePluginAiSessionUi();
            window.setPluginAiBadge(window.buildPluginAiThreadBadge());
            window.setPluginAiThreadReadyStatus();
            const res = await loadMsgs({ slug, threadId: tid, viewToken: token });
            if (!window.isPluginAiViewCurrent(slug, token)) {
                return null;
            }
            if (res?.hasPendingRun) {
                startPoll({ slug, threadId: tid, viewToken: token });
                window.updatePluginAiComposerState(false);
            } else {
                stopPoll();
                startSync({ slug, threadId: tid, viewToken: token });
                window.updatePluginAiComposerState(true);
            }
            return tid;
        } catch (err) {
            if (!window.isPluginAiViewCurrent(slug, token)) {
                return null;
            }
            window.setPluginAiErrorBadge();
            window.setPluginAiStatus(`Unable to load AI chat: ${err.message}`);
            window.setPluginAiMessagesEmptyView();
            window.updatePluginAiComposerState(!!state.threadId);
            return null;
        } finally {
            if (window.isPluginAiViewCurrent(slug, token)) {
                state.loading = false;
            }
        }
    }

    window.stopPluginAiThreadSyncPoll = stopSync;
    window.startPluginAiThreadSyncPoll = startSync;
    window.stopPluginAiPendingRunPoll = stopPoll;
    window.startPluginAiPendingRunPoll = startPoll;
    window.loadPluginAiThreads = loadThreads;
    window.loadPluginAiMessages = loadMsgs;
    window.switchPluginAiThread = switchThread;
    window.createNewPluginAiThread = createThread;
    window.ensurePluginAiThread = ensureThread;
})();
