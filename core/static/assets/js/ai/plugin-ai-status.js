(function() {
    function setStatus(msg) {
        const text = String(msg || '');
        const el = document.getElementById('plugin-ai-status');
        if (el) el.textContent = text;
        const state = typeof window.getPluginAiState === 'function' ? window.getPluginAiState() : null;
        if (state && typeof state === 'object') {
            state.statusText = text;
        }
        if (typeof window.syncCurrentPluginAiThreadSnapshot === 'function') {
            window.syncCurrentPluginAiThreadSnapshot({ statusText: text });
        }
    }

    function setBadge(msg) {
        const text = String(msg || '');
        const el = document.getElementById('plugin-ai-thread-badge');
        if (el) el.textContent = text;
        const state = typeof window.getPluginAiState === 'function' ? window.getPluginAiState() : null;
        if (state && typeof state === 'object') {
            state.badgeText = text;
        }
        if (typeof window.syncCurrentPluginAiThreadSnapshot === 'function') {
            window.syncCurrentPluginAiThreadSnapshot({ badgeText: text });
        }
    }

    function setComposer(enabled) {
        const input = document.getElementById('plugin-ai-input');
        const btn = document.getElementById('plugin-ai-send');
        const sel = document.getElementById('plugin-ai-profile-model-select');
        if (input) input.disabled = !enabled;
        if (btn) btn.disabled = !enabled;
        if (sel) sel.disabled = !enabled;
    }

    function fmtDuration(startedAt) {
        const raw = String(startedAt || '').trim();
        if (!raw) return '0m 00s';
        const ms = new Date(raw).getTime();
        if (!Number.isFinite(ms)) return '0m 00s';
        const diff = Math.max(0, Math.floor((Date.now() - ms) / 1000));
        const mins = Math.floor(diff / 60);
        const secs = diff % 60;
        return `${mins}m ${String(secs).padStart(2, '0')}s`;
    }

    function runBadge(startedAt) {
        return `Running • ${fmtDuration(startedAt)}`;
    }

    function runStatus(startedAt) {
        return `AI is running • ${fmtDuration(startedAt)}`;
    }

    function refreshIndicators() {
        const state = typeof window.getPluginAiState === 'function' ? window.getPluginAiState() : null;
        if (!state || !state.sending || !String(state.runStartedAt || '').trim()) return;
        const badge = document.getElementById('plugin-ai-thread-badge');
        const status = document.getElementById('plugin-ai-status');
        if (badge) badge.textContent = runBadge(state.runStartedAt);
        if (status && String(state.statusText || '').includes('AI is running')) {
            status.textContent = runStatus(state.runStartedAt);
        }
        if (typeof window.updatePluginAiSessionUi === 'function') {
            window.updatePluginAiSessionUi();
        }
    }

    function updateComposer(enabled) {
        setComposer(enabled);
    }

    function keyPlaceholder(cfg = {}) {
        const masked = String(cfg.api_key_masked || '').trim();
        return masked || 'Enter a new API key';
    }

    function requireKey(cfg = {}) {
        return !String(cfg.api_key_masked || '').trim();
    }

    function updateKeyHint(cfg = {}) {
        const input = document.getElementById('plugin-ai-api-key');
        if (!input) return;
        input.placeholder = keyPlaceholder(cfg);
        input.required = requireKey(cfg);
    }

    function threadBadge() {
        return 'Ready';
    }

    function loadingBadge() {
        setBadge('Loading');
    }

    function runningBadge() {
        const state = typeof window.getPluginAiState === 'function' ? window.getPluginAiState() : null;
        setBadge(runBadge(state?.runStartedAt));
    }

    function errorBadge() {
        setBadge('Error');
    }

    function pluginLabel(plugin) {
        return plugin?.is_theme ? 'theme' : 'plugin';
    }

    function threadStatus(plugin) {
        return `Loading AI thread for ${pluginLabel(plugin)} ${String(plugin?.slug || '').trim()}...`;
    }

    function setThreadLoading(plugin) {
        setStatus(threadStatus(plugin));
    }

    function setThreadReady() {
        setStatus('AI thread ready. Loading existing messages...');
    }

    function setResponseReceived() {
        setStatus('AI response received.');
    }

    function setSettingsLoading() {
        setStatus('Loading AI settings...');
    }

    function loadedStatus(msgs = []) {
        return msgs.length ? 'AI messages loaded.' : 'Thread ready.';
    }

    function noteLoaded(msgs = []) {
        setStatus(loadedStatus(msgs));
    }

    function errStatus(err) {
        return `AI request failed: ${err.message}`;
    }

    function settingsStatus(cfg) {
        const label = cfg?.display_name || cfg?.model || cfg?.provider;
        return label ? `Loaded AI profile ${label}.` : 'No AI profile configured yet.';
    }

    function savedStatus(provider) {
        return `Saved AI profile for ${provider}.`;
    }

    function setFailure(err) {
        setStatus(errStatus(err));
    }

    function setCfgStatus(cfg) {
        setStatus(settingsStatus(cfg));
    }

    function setSaved(provider) {
        setStatus(savedStatus(provider));
    }

    function toastSaved() {
        showToast('AI settings saved.', 'success');
    }

    function toastNoMsg() {
        showToast('Enter a message for AI first.', 'warn');
    }

    function noScanMsg(plugin) {
        return `Open this ${pluginLabel(plugin)} from a scan result before starting AI chat.`;
    }

    function toastNoScan(plugin) {
        showToast(noScanMsg(plugin), 'warn');
    }

    function toastSaveErr(err) {
        showToast(`Failed to save AI settings: ${err.message}`, 'error');
    }

    function toastLoadErr(err) {
        showToast(`Failed to load AI settings: ${err.message}`, 'error');
    }

    function toastReqErr(err) {
        showToast(errStatus(err), 'error');
    }

    window.setPluginAiStatus = setStatus;
    window.setPluginAiBadge = setBadge;
    window.setPluginAiComposerEnabled = setComposer;
    window.updatePluginAiComposerState = updateComposer;
    window.formatPluginAiRunDuration = fmtDuration;
    window.buildPluginAiRunningBadgeLabel = runBadge;
    window.buildPluginAiRunningStatusText = runStatus;
    window.refreshPluginAiRunningIndicators = refreshIndicators;
    window.getMaskedApiKeyPlaceholder = keyPlaceholder;
    window.shouldRequireApiKeyInput = requireKey;
    window.updatePluginAiApiKeyHint = updateKeyHint;
    window.buildPluginAiThreadBadge = threadBadge;
    window.setPluginAiThreadLoadingBadge = loadingBadge;
    window.setPluginAiRunningBadge = runningBadge;
    window.setPluginAiErrorBadge = errorBadge;
    window.currentPluginAiLabel = pluginLabel;
    window.buildPluginAiThreadStatus = threadStatus;
    window.setPluginAiThreadStatusLoading = setThreadLoading;
    window.setPluginAiThreadReadyStatus = setThreadReady;
    window.setPluginAiResponseReceivedStatus = setResponseReceived;
    window.setPluginAiSettingsLoadingStatus = setSettingsLoading;
    window.buildPluginAiLoadedStatus = loadedStatus;
    window.notePluginAiMessagesLoaded = noteLoaded;
    window.buildPluginAiRequestFailureStatus = errStatus;
    window.buildPluginAiSettingsLoadedStatus = settingsStatus;
    window.buildPluginAiSettingsSavedStatus = savedStatus;
    window.setPluginAiRequestFailure = setFailure;
    window.setPluginAiSettingsStatus = setCfgStatus;
    window.setPluginAiSavedStatus = setSaved;
    window.setPluginAiSettingsSavedToast = toastSaved;
    window.setPluginAiNoMessageWarning = toastNoMsg;
    window.buildPluginAiNoScanWarning = noScanMsg;
    window.setPluginAiNoScanWarningForPlugin = toastNoScan;
    window.setPluginAiSettingsErrorToast = toastSaveErr;
    window.setPluginAiLoadSettingsErrorToast = toastLoadErr;
    window.setPluginAiRequestErrorToast = toastReqErr;
})();
