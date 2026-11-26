(function() {
    async function initializeApp() {
        initializeSidebarToggle();
        initializeStarStripDismiss();
        initializeDashboardChartInteractions();
        initializePagesAutoRandom();
        bindPluginAiUiEvents();
        setPluginAiComposerEnabled(false);

        await refreshFavoriteSlugs();
        loadHistory();
        restoreViewFromUrl();
        window.addEventListener('popstate', restoreViewFromUrl);

        const btn = document.getElementById('update-action-btn');
        if (btn) {
            btn.addEventListener('click', initiateSystemUpdate);
        }

        startSystemStatusPolling();
    }

    document.addEventListener('DOMContentLoaded', () => {
        initializeApp().catch((error) => {
            console.error('App bootstrap failed:', error);
        });
    });
})();
