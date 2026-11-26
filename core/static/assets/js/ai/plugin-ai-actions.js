(function() {
    async function renameThread(id) {
        const state = window.getPluginAiState();
        const thread = Array.isArray(state.threads) ? state.threads.find((item) => Number(item.id || 0) === Number(id || 0)) : null;
        const idx = Math.max(0, Array.isArray(state.threads) ? state.threads.findIndex((item) => Number(item.id || 0) === Number(id || 0)) : 0);
        const cur = String(thread?.title || '').trim() || `Chat ${idx + 1}`;
        const raw = await window.showPrompt({
            title: 'Rename chat',
            message: 'Enter a new name for this chat.',
            defaultValue: cur,
            confirmText: 'Save',
            cancelText: 'Cancel',
        });
        if (raw == null) return;
        const title = String(raw || '').trim();
        if (!title) {
            window.showToast('Chat name cannot be empty.', 'warn');
            return;
        }

        const res = await fetch(`/api/ai/threads/${id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                plugin_slug: String(state.plugin || '').trim(),
                is_theme: !!state.isTheme,
                title,
            }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            throw new Error(data.detail || `HTTP ${res.status}`);
        }
        window.replacePluginAiThreadInState(data);
        window.showToast('Chat name updated.', 'success');
    }

    async function deleteThread(id) {
        const state = window.getPluginAiState();
        const ok = await window.showConfirm('Delete this chat? This action cannot be undone.');
        if (!ok) return;

        const res = await fetch(`/api/ai/threads/${id}`, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                plugin_slug: String(state.plugin || '').trim(),
                is_theme: !!state.isTheme,
            }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            throw new Error(data.detail || `HTTP ${res.status}`);
        }

        window.removePluginAiThreadFromState(id);
        if (Number(state.threadId || 0) === Number(id || 0)) {
            const next = Array.isArray(state.threads) && state.threads.length ? state.threads[0] : null;
            if (next?.id) {
                state.threadId = Number(next.id);
                await window.switchPluginAiThread(state.threadId);
            } else {
                state.threadId = null;
                state.messages = [];
                state.events = [];
                window.refreshPluginAiRenderedState();
                window.updatePluginAiComposerState(false);
            }
        }
    }

    async function prepSource() {
        const state = window.getPluginAiState();
        const id = Number(state.threadId || 0);
        const slug = String(state.plugin || '').trim();
        if (!id || !slug || state.sourcePreparing) return;

        state.sourcePreparing = true;
        if (typeof window.refreshPluginAiRenderedState === 'function') {
            window.refreshPluginAiRenderedState();
        }
        window.setPluginAiStatus('Preparing source...');

        try {
            const res = await fetch(`/api/ai/threads/${id}/source`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    plugin_slug: slug,
                    is_theme: !!state.isTheme,
                    last_scan_session_id: typeof window.getCurrentScanId === 'function' ? window.getCurrentScanId() || null : null,
                }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                throw new Error(data.detail || `HTTP ${res.status}`);
            }
            if (data.thread && typeof window.replacePluginAiThreadInState === 'function') {
                window.replacePluginAiThreadInState(data.thread);
            }
            if (data.thread && typeof window.rememberPluginAiThread === 'function') {
                window.rememberPluginAiThread(data.thread);
            }
            window.setPluginAiStatus('Source ready.');
        } catch (err) {
            window.setPluginAiStatus(`Source prepare failed: ${err.message}`);
        } finally {
            state.sourcePreparing = false;
            if (typeof window.refreshPluginAiRenderedState === 'function') {
                window.refreshPluginAiRenderedState();
            }
        }
    }

    function bindSession() {
        const box = document.getElementById('plugin-ai-sessions');
        if (box && !box.dataset.bound) {
            box.addEventListener('click', async (event) => {
                const renBtn = event.target.closest('[data-thread-rename]');
                if (renBtn) {
                    event.preventDefault();
                    event.stopPropagation();
                    const id = Number(renBtn.getAttribute('data-thread-rename') || 0);
                    if (id > 0) {
                        try {
                            await renameThread(id);
                        } catch (err) {
                            window.setPluginAiStatus(`Failed to rename chat: ${err.message}`);
                        }
                    }
                    return;
                }

                const delBtn = event.target.closest('[data-thread-delete]');
                if (delBtn) {
                    event.preventDefault();
                    event.stopPropagation();
                    const id = Number(delBtn.getAttribute('data-thread-delete') || 0);
                    if (id > 0) {
                        try {
                            await deleteThread(id);
                        } catch (err) {
                            window.setPluginAiStatus(`Failed to delete chat: ${err.message}`);
                        }
                    }
                    return;
                }

                const btn = event.target.closest('[data-thread-id]');
                if (!btn) return;
                const id = Number(btn.getAttribute('data-thread-id') || 0);
                if (id > 0) {
                    await window.switchPluginAiThread(id);
                }
            });
            box.dataset.bound = '1';
        }

        const newBtn = document.getElementById('plugin-ai-new-chat-btn');
        if (newBtn && !newBtn.dataset.bound) {
            newBtn.addEventListener('click', async () => {
                await window.createNewPluginAiThread();
            });
            newBtn.dataset.bound = '1';
        }

        const srcBtn = document.getElementById('plugin-ai-source-download-btn');
        if (srcBtn && !srcBtn.dataset.bound) {
            srcBtn.addEventListener('click', async () => {
                await prepSource();
            });
            srcBtn.dataset.bound = '1';
        }
    }

    function initHelpers() {
        bindSession();
        window.updatePluginAiSessionUi();
        if (typeof window.bindPluginAiLayoutEvents === 'function') {
            window.bindPluginAiLayoutEvents();
        }
        if (typeof window.bindAiSettingsEvents === 'function') {
            window.bindAiSettingsEvents();
        }
    }

    function initModal() {
        initHelpers();
        if (typeof window.setPluginAiExpanded === 'function') {
            window.setPluginAiExpanded(false);
        }
    }

    function appendEvents({ slug, threadId: id, isTheme: theme, events = [] }) {
        if (typeof window.getPluginAiEventsSnapshot !== 'function' || typeof window.rememberPluginAiEventsSnapshot !== 'function') {
            return;
        }
        const snap = window.getPluginAiEventsSnapshot(slug, id, !!theme);
        const cur = Array.isArray(snap?.events) ? snap.events : [];
        const next = Array.isArray(events) ? events.filter(Boolean) : [];
        if (!next.length) return;
        const merged = [...cur, ...next].slice(-120);
        window.rememberPluginAiEventsSnapshot({
            plugin: slug,
            threadId: id,
            isTheme: !!theme,
            events: merged,
            createdAt: new Date().toISOString(),
        });
        if (typeof window.rememberPluginAiThreadUiSnapshot === 'function') {
            const uiSnap = typeof window.getPluginAiThreadUiSnapshot === 'function'
                ? window.getPluginAiThreadUiSnapshot(slug, id, !!theme)
                : null;
            window.rememberPluginAiThreadUiSnapshot({
                plugin: slug,
                threadId: id,
                isTheme: !!theme,
                messages: Array.isArray(uiSnap?.messages) ? uiSnap.messages : [],
                events: merged,
                liveActivity: merged,
                sending: true,
                runStartedAt: String(uiSnap?.runStartedAt || ''),
                badgeText: String(uiSnap?.badgeText || window.buildPluginAiRunningBadgeLabel(uiSnap?.runStartedAt)),
                statusText: String(uiSnap?.statusText || window.buildPluginAiRunningStatusText(uiSnap?.runStartedAt)),
                sourceStatus: uiSnap?.sourceStatus || {},
            });
        }
    }

    async function sendMsg(prompt = '') {
        const state = window.getPluginAiState();
        const input = document.getElementById('plugin-ai-input');
        if (!state.threadId || !input) return;
        const streaming = !!state.sending
            && Number(state.streamThreadId || 0) === Number(state.threadId || 0)
            && !!String(state.streamRequestId || '').trim();
        if (streaming) return;

        const slug = String(state.plugin || '').trim();
        const id = state.threadId;
        const tok = state.viewToken;
        const text = window.normalizePluginAiInput(prompt, input.value);
        if (!text) {
            window.setPluginAiNoMessageWarning();
            return;
        }

        if (!window.getCurrentScanId || !window.getCurrentScanId()) {
            window.setPluginAiStatus('No active scan context. AI will use a trusted local source if available, otherwise stored metadata only.');
        }

        state.sending = true;
        state.runStartedAt = new Date().toISOString();
        state.sourcePreparing = false;
        if (typeof window.stopPluginAiPendingRunPoll === 'function') {
            window.stopPluginAiPendingRunPoll();
        }
        if (typeof window.stopPluginAiThreadSyncPoll === 'function') {
            window.stopPluginAiThreadSyncPoll();
        }
        const reqId = window.beginPluginAiStreamRequest(id);
        const hasHistory = Array.isArray(state.messages) && state.messages.some((item) => String(item?.role || '') === 'assistant' && !item?.is_pending_assistant);
        const thread = Array.isArray(state.threads) ? state.threads.find((item) => Number(item?.id || 0) === Number(id || 0)) : null;
        const root = String(thread?.workspace_path || state.workspacePath || '').trim();
        window.setPluginAiLiveActivityOptions({ showSource: !hasHistory, workspaceRoot: root });
        state.liveActivity = [];
        window.updatePluginAiComposerState(false);
        window.setPluginAiRunningBadge();
        window.setPluginAiStatus(window.buildPluginAiRunningStatusText(state.runStartedAt));
        if (state.runningIndicatorTimer) {
            window.clearInterval(state.runningIndicatorTimer);
        }
        state.runningIndicatorTimer = window.setInterval(() => {
            if (typeof window.refreshPluginAiRunningIndicators === 'function') {
                window.refreshPluginAiRunningIndicators();
            }
        }, 1000);

        const userMsg = {
            id: `tmp-user-${Date.now()}`,
            thread_id: id,
            role: 'user',
            content: text,
            created_at: new Date().toISOString(),
            tool_calls: [],
            tool_results: [],
        };
        const botMsg = {
            id: `tmp-assistant-${Date.now()}`,
            thread_id: id,
            role: 'assistant',
            content: '',
            created_at: new Date().toISOString(),
            tool_calls: [],
            tool_results: [],
            is_pending_assistant: true,
        };
        window.pushPluginAiMessage(userMsg);
        window.pushPluginAiMessage(botMsg);
        if (typeof window.syncCurrentPluginAiThreadSnapshot === 'function') {
            window.syncCurrentPluginAiThreadSnapshot({
                threadId: id,
                messages: state.messages,
                liveActivity: state.liveActivity,
                events: state.events,
                sending: true,
                runStartedAt: state.runStartedAt,
                badgeText: window.buildPluginAiRunningBadgeLabel(state.runStartedAt),
                statusText: window.buildPluginAiRunningStatusText(state.runStartedAt),
            });
        }
        if (typeof window.rememberPluginAiPendingSnapshot === 'function') {
            window.rememberPluginAiPendingSnapshot({
                plugin: slug,
                threadId: id,
                isTheme: !!state.isTheme,
                content: text,
                createdAt: userMsg.created_at,
            });
        }
        window.refreshPluginAiRenderedState();
        input.value = '';

        try {
            let body;
            try {
                body = window.buildPluginAiMessagePayload({ threadId: id, content: text });
            } catch (payloadErr) {
                state.sending = false;
                window.updatePluginAiComposerState(false);
                window.setPluginAiStatus(payloadErr.message || 'Invalid AI runtime options.');
                window.showToast(payloadErr.message || 'Invalid AI runtime options.', 'warn');
                return;
            }
            const res = await fetch('/api/ai/messages/stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                throw new Error(data.detail || `HTTP ${res.status}`);
            }
            if (!res.body) {
                throw new Error('Streaming response body is not available.');
            }

            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buf = '';
            let final = null;

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buf += decoder.decode(value, { stream: true });
                const lines = buf.split('\n');
                buf = lines.pop() || '';

                for (const raw of lines) {
                    const line = String(raw || '').trim();
                    if (!line) continue;
                    let chunk = {};
                    try {
                        chunk = JSON.parse(line);
                    } catch (_) {
                        continue;
                    }
                    if (!window.isCurrentPluginAiStreamRequest(reqId)) {
                        return;
                    }
                    if (window.shouldIgnorePluginAiResponse(slug, tok, id)) {
                        if (chunk.type === 'bridge_event' || chunk.type === 'runtime_event') {
                            appendEvents({
                                slug,
                                threadId: id,
                                isTheme: !!state.isTheme,
                                events: [chunk.data],
                            });
                        }
                        if (chunk.type === 'final' && chunk.data && typeof chunk.data === 'object') {
                            const evts = Array.isArray(chunk.data.team_events) ? chunk.data.team_events : [];
                            if (evts.length) {
                                appendEvents({
                                    slug,
                                    threadId: id,
                                    isTheme: !!state.isTheme,
                                    events: evts,
                                });
                            }
                            if (typeof window.clearPluginAiPendingSnapshot === 'function') {
                                window.clearPluginAiPendingSnapshot(slug, id, !!state.isTheme);
                            }
                        }
                        continue;
                    }
                    if (chunk.type === 'error') {
                        throw new Error(chunk?.data?.detail || 'AI stream failed.');
                    }
                    window.applyPluginAiStreamChunk(chunk);
                    if (chunk.type === 'final') {
                        final = chunk.data || null;
                    }
                    window.refreshPluginAiRenderedState();
                }
            }

            if (buf.trim()) {
                try {
                    const chunk = JSON.parse(buf.trim());
                    if (window.shouldIgnorePluginAiResponse(slug, tok, id)) {
                        if (chunk.type === 'bridge_event' || chunk.type === 'runtime_event') {
                            appendEvents({
                                slug,
                                threadId: id,
                                isTheme: !!state.isTheme,
                                events: [chunk.data],
                            });
                        }
                        if (chunk.type === 'final' && chunk.data && typeof chunk.data === 'object') {
                            const evts = Array.isArray(chunk.data.team_events) ? chunk.data.team_events : [];
                            if (evts.length) {
                                appendEvents({
                                    slug,
                                    threadId: id,
                                    isTheme: !!state.isTheme,
                                    events: evts,
                                });
                            }
                            if (typeof window.clearPluginAiPendingSnapshot === 'function') {
                                window.clearPluginAiPendingSnapshot(slug, id, !!state.isTheme);
                            }
                        }
                    } else {
                        if (chunk.type === 'error') {
                            throw new Error(chunk?.data?.detail || 'AI stream failed.');
                        }
                        window.applyPluginAiStreamChunk(chunk);
                        if (chunk.type === 'final') {
                            final = chunk.data || null;
                        }
                    }
                } catch (_) {
                    if (!final) {
                        throw new Error('AI stream ended with malformed output.');
                    }
                }
            }

            if (window.shouldIgnorePluginAiResponse(slug, tok, id)) {
                return;
            }

            if (!final && state.sending && typeof window.startPluginAiPendingRunPoll === 'function') {
                window.startPluginAiPendingRunPoll({ slug, threadId: id, viewToken: tok });
            }

            if (typeof window.clearPluginAiPendingSnapshot === 'function') {
                window.clearPluginAiPendingSnapshot(slug, id, !!state.isTheme);
            }
            if (final && typeof final === 'object') {
                state.events = Array.isArray(final.team_events) ? final.team_events : [];
                state.liveActivity = state.events.length ? state.events : (state.liveActivity || []);
                state.pendingApproval = final.pending_approval && typeof final.pending_approval === 'object'
                    ? final.pending_approval
                    : null;
                if (final.assistant_message && final.agents && Array.isArray(final.agents)) {
                    const struct = final.agents.find((agent) => agent && typeof agent === 'object' && agent.structured)?.structured;
                    if (struct && Array.isArray(state.messages) && state.messages.length) {
                        const last = state.messages.length - 1;
                        state.messages[last] = {
                            ...state.messages[last],
                            structured: struct,
                        };
                    }
                }
                if (state.runningIndicatorTimer) {
                    window.clearInterval(state.runningIndicatorTimer);
                    state.runningIndicatorTimer = null;
                }
                if (typeof window.syncCurrentPluginAiThreadSnapshot === 'function') {
                    window.syncCurrentPluginAiThreadSnapshot({
                        threadId: id,
                        messages: state.messages,
                        events: state.events,
                        liveActivity: state.liveActivity,
                        sending: false,
                        runStartedAt: '',
                        badgeText: 'Ready',
                        statusText: 'AI response received.',
                        pendingApproval: state.pendingApproval,
                    });
                }
                window.refreshPluginAiRenderedState();
            } else {
                window.removePendingAssistantMessage();
                state.liveActivity = [];
                window.refreshPluginAiRenderedState();
            }
            window.updatePluginAiThreadsAfterMessage(id);
            window.setPluginAiBadge(window.buildPluginAiThreadBadge());
            window.setPluginAiResponseReceivedStatus();
        } catch (err) {
            if (window.shouldIgnorePluginAiResponse(slug, tok, id)) {
                return;
            }
            if (typeof window.clearPluginAiPendingSnapshot === 'function') {
                window.clearPluginAiPendingSnapshot(slug, id, !!state.isTheme);
            }
            window.removePendingAssistantMessage();
            state.liveActivity = [];
            if (state.runningIndicatorTimer) {
                window.clearInterval(state.runningIndicatorTimer);
                state.runningIndicatorTimer = null;
            }
            if (typeof window.syncCurrentPluginAiThreadSnapshot === 'function') {
                window.syncCurrentPluginAiThreadSnapshot({
                    threadId: id,
                    messages: state.messages,
                    events: state.events,
                    liveActivity: state.liveActivity,
                    sending: false,
                    runStartedAt: '',
                    badgeText: 'Error',
                    statusText: `AI request failed: ${err.message}`,
                });
            }
            window.refreshPluginAiRenderedState();
            window.setPluginAiErrorBadge();
            window.setPluginAiRequestFailure(err);
            window.setPluginAiRequestErrorToast(err);
        } finally {
            const latest = window.getPluginAiState();
            const owns = window.isCurrentPluginAiStreamRequest(reqId)
                || Number(latest.streamThreadId || 0) === Number(id || 0);
            if (owns) {
                window.endPluginAiStreamRequest(reqId);
                latest.sending = false;
                latest.pendingSnapshotRetryInFlight = false;
            }
            const active = Number(latest.threadId || 0) === Number(id || 0);
            if (typeof window.syncCurrentPluginAiThreadSnapshot === 'function') {
                window.syncCurrentPluginAiThreadSnapshot({
                    threadId: id,
                    messages: latest.messages,
                    events: latest.events,
                    liveActivity: latest.liveActivity,
                    sending: latest.sending,
                });
            }
            const compose = !!latest.threadId && !latest.loading && (!latest.sending || !active);
            window.updatePluginAiComposerState(compose);
            if (window.isPluginAiViewCurrent(slug, tok) && active && !latest.sending) {
                window.setPluginAiBadge(window.buildPluginAiThreadBadge());
                if (typeof window.startPluginAiThreadSyncPoll === 'function') {
                    window.startPluginAiThreadSyncPoll({ slug, threadId: id, viewToken: tok });
                }
            }
        }
    }

    async function decideApproval(decision) {
        const state = window.getPluginAiState();
        const approval = state.pendingApproval && typeof state.pendingApproval === 'object' ? state.pendingApproval : null;
        const id = Number(state.threadId || 0);
        const slug = String(state.plugin || '').trim();
        if (!approval || !id || !slug) return;
        const res = await fetch(`/api/ai/runs/${encodeURIComponent(approval.run_id)}/approval`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                plugin_slug: slug,
                is_theme: !!state.isTheme,
                decision,
            }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            throw new Error(data.detail || `HTTP ${res.status}`);
        }
        state.pendingApproval = null;
        if (typeof window.syncCurrentPluginAiThreadSnapshot === 'function') {
            window.syncCurrentPluginAiThreadSnapshot({ pendingApproval: null, sending: true });
        }
        window.setPluginAiStatus(decision === 'approved' ? 'Approval granted. Continuing run...' : 'Approval rejected. Finishing run...');
        if (typeof window.startPluginAiPendingRunPoll === 'function') {
            window.startPluginAiPendingRunPoll({ slug, threadId: id, viewToken: state.viewToken });
        }
        window.refreshPluginAiRenderedState();
        return data;
    }

    function bindUi() {
        initModal();
        if (typeof window.fetchCurrentAiSettings === 'function') {
            window.fetchCurrentAiSettings().catch(() => null);
        }

        const form = document.getElementById('plugin-ai-form');
        if (form && !form.dataset.bound) {
            form.addEventListener('submit', (event) => {
                event.preventDefault();
                sendMsg();
            });
            form.dataset.bound = '1';
        }

        const input = document.getElementById('plugin-ai-input');
        if (input && !input.dataset.bound) {
            input.addEventListener('keydown', (event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    sendMsg();
                }
            });
            input.dataset.bound = '1';
        }

        const panel = document.getElementById('plugin-ai-messages');
        if (panel && !panel.dataset.approvalBound) {
            panel.addEventListener('click', async (event) => {
                const target = event.target instanceof HTMLElement ? event.target : null;
                if (!target) return;
                if (target.id === 'plugin-ai-approve-run') {
                    event.preventDefault();
                    try {
                        await decideApproval('approved');
                    } catch (err) {
                        window.showToast(err.message || 'Failed to approve run.', 'warn');
                    }
                }
                if (target.id === 'plugin-ai-reject-run') {
                    event.preventDefault();
                    try {
                        await decideApproval('rejected');
                    } catch (err) {
                        window.showToast(err.message || 'Failed to reject run.', 'warn');
                    }
                }
            });
            panel.dataset.approvalBound = '1';
        }

        const select = document.getElementById('plugin-ai-profile-model-select');
        if (select && !select.dataset.bound) {
            select.addEventListener('change', (event) => {
                const raw = String(event.target.value || '').trim();
                const [profileKey, model] = raw.split('::');
                window.updatePluginAiComposerSelections({
                    selectedProfileKey: String(profileKey || '').trim() || null,
                    selectedModel: String(model || '').trim() || null,
                });
            });
            select.dataset.bound = '1';
        }

        if (typeof window.renderPluginAiComposerProfiles === 'function') {
            window.renderPluginAiComposerProfiles();
        }
    }

    window.bindPluginAiSessionEvents = bindSession;
    window.initializePluginAiHelpers = initHelpers;
    window.initializePluginAiModal = initModal;
    window.submitPluginAiMessage = sendMsg;
    window.bindPluginAiUiEvents = bindUi;
})();
