(function() {
    function mergeCfg(prev = {}, next = {}) {
        return {
            ...prev,
            ...next,
            api_key: null,
        };
    }

    function syncCfg(cfg = {}) {
        window.currentAiConfig = mergeCfg(window.currentAiConfig || {}, cfg || {});
        return window.currentAiConfig;
    }

    async function fetchCfg() {
        const res = await fetch('/api/ai/settings');
        const data = await res.json().catch(() => null);
        if (!res.ok) {
            throw new Error((data && data.detail) || `HTTP ${res.status}`);
        }
        window.currentAiConfig = data?.active_profile || null;
        if (typeof window.updatePluginAiComposerSelections === 'function') {
            window.updatePluginAiComposerSelections({
                profiles: Array.isArray(data?.profiles) ? data.profiles : [],
                selectedProfileKey: data?.active_profile?.profile_key || null,
                selectedModel: data?.active_profile?.model || null,
            });
        }
        return data;
    }

    window.mergeAiSettingsConfig = mergeCfg;
    window.syncPluginAiSettingsState = syncCfg;
    window.fetchCurrentAiSettings = fetchCfg;
})();
