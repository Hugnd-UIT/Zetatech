(function() {
    const SIDEBAR_KEY = 'zetatech-sidebar-collapsed';
    const STRIP_KEY = 'zetatech-star-strip-hidden';

    function applyState(collapsed) {
        const layout = document.querySelector('.layout');
        const btn = document.getElementById('sidebar-toggle');
        const mobile = window.matchMedia('(max-width: 800px)').matches;
        if (!layout || !btn) return;

        if (mobile) {
            layout.classList.remove('sidebar-collapsed');
            btn.setAttribute('aria-expanded', 'true');
            btn.setAttribute('aria-label', 'Collapse sidebar');
            btn.title = 'Collapse sidebar';
            return;
        }

        layout.classList.toggle('sidebar-collapsed', collapsed);
        btn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
        btn.setAttribute('aria-label', collapsed ? 'Expand sidebar' : 'Collapse sidebar');
        btn.title = collapsed ? 'Expand sidebar' : 'Collapse sidebar';
    }

    window.toggleSidebarCollapse = function() {
        const layout = document.querySelector('.layout');
        if (!layout) return;

        const mobile = window.matchMedia('(max-width: 800px)').matches;
        if (mobile) {
            applyState(false);
            localStorage.setItem(SIDEBAR_KEY, '0');
            return;
        }

        const collapsed = !layout.classList.contains('sidebar-collapsed');
        applyState(collapsed);
        localStorage.setItem(SIDEBAR_KEY, collapsed ? '1' : '0');
    };

    function initToggle() {
        const btn = document.getElementById('sidebar-toggle');
        if (!btn) return;

        btn.addEventListener('click', window.toggleSidebarCollapse);

        const saved = localStorage.getItem(SIDEBAR_KEY) === '1';
        applyState(saved);

        window.addEventListener('resize', () => {
            const collapsed = window.matchMedia('(max-width: 800px)').matches
                ? false
                : localStorage.getItem(SIDEBAR_KEY) === '1';
            applyState(collapsed);
        });
    }

    function initStrip() {
        const strip = document.querySelector('.star-strip');
        const close = document.getElementById('star-strip-close');
        if (!strip || !close) return;

        const setHidden = (hidden) => {
            strip.classList.toggle('is-hidden', hidden);
            document.body.classList.toggle('star-strip-hidden', hidden);
        };

        const hidden = localStorage.getItem(STRIP_KEY) === '1';
        setHidden(hidden);

        close.addEventListener('click', () => {
            setHidden(true);
            localStorage.setItem(STRIP_KEY, '1');
        });
    }

    const nativeFetch = window.fetch.bind(window);
    window.fetch = function(res, opts = {}) {
        const isApi = typeof res === 'string' && res.startsWith('/api/');
        if (!isApi) return nativeFetch(res, opts);

        const headers = { ...(opts.headers || {}) };
        if (!headers['Cache-Control']) headers['Cache-Control'] = 'no-cache';
        if (!headers['Pragma']) headers['Pragma'] = 'no-cache';

        return nativeFetch(res, {
            ...opts,
            cache: 'no-store',
            headers
        });
    };

    function isDetailsActive() {
        const view = document.getElementById('scan-details-view');
        return !!view && view.style.display !== 'none';
    }

    function noCacheUrl(path) {
        const sep = path.includes('?') ? '&' : '?';
        return `${path}${sep}_ts=${Date.now()}`;
    }

    window.initializeSidebarToggle = initToggle;
    window.initializeStarStripDismiss = initStrip;
    window.isDetailsViewActive = isDetailsActive;
    window.apiNoCacheUrl = noCacheUrl;
})();
