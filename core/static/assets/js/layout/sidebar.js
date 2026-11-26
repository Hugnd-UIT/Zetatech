(function() {
const SIDEBAR_PREF_KEY = 'zetatech-sidebar-collapsed';
const STAR_STRIP_PREF_KEY = 'zetatech-star-strip-hidden';

function applySidebarState(collapsed) {
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
        applySidebarState(false);
        localStorage.setItem(SIDEBAR_PREF_KEY, '0');
        return;
    }

    const collapse = !layout.classList.contains('sidebar-collapsed');
    applySidebarState(collapse);
    localStorage.setItem(SIDEBAR_PREF_KEY, collapse ? '1' : '0');
};

function initializeSidebarToggle() {
    const btn = document.getElementById('sidebar-toggle');
    if (!btn) return;

    btn.addEventListener('click', window.toggleSidebarCollapse);

    const saved = localStorage.getItem(SIDEBAR_PREF_KEY) === '1';
    applySidebarState(saved);

    window.addEventListener('resize', () => {
        const collapse = window.matchMedia('(max-width: 800px)').matches
            ? false
            : localStorage.getItem(SIDEBAR_PREF_KEY) === '1';
        applySidebarState(collapse);
    });
}

function initializeStarStripDismiss() {
    const strip = document.querySelector('.star-strip');
    const close = document.getElementById('star-strip-close');
    if (!strip || !close) return;

    const setHidden = (hidden) => {
        strip.classList.toggle('is-hidden', hidden);
        document.body.classList.toggle('star-strip-hidden', hidden);
    };

    const hidden = localStorage.getItem(STAR_STRIP_PREF_KEY) === '1';
    setHidden(hidden);

    close.addEventListener('click', () => {
        setHidden(true);
        localStorage.setItem(STAR_STRIP_PREF_KEY, '1');
    });
}


const _nativeFetch = window.fetch.bind(window);
window.fetch = function(resource, options = {}) {
    const isApiCall = typeof resource === 'string' && resource.startsWith('/api/');
    if (!isApiCall) return _nativeFetch(resource, options);

    const headers = { ...(options.headers || {}) };
    if (!headers['Cache-Control']) headers['Cache-Control'] = 'no-cache';
    if (!headers['Pragma']) headers['Pragma'] = 'no-cache';

    return _nativeFetch(resource, {
        ...options,
        cache: 'no-store',
        headers
    });
};

function isDetailsViewActive() {
    const detailsView = document.getElementById('scan-details-view');
    return !!detailsView && detailsView.style.display !== 'none';
}

function apiNoCacheUrl(path) {
    const sep = path.includes('?') ? '&' : '?';
    return `${path}${sep}_ts=${Date.now()}`;
}


    window.initializeSidebarToggle = initializeSidebarToggle;
    window.initializeStarStripDismiss = initializeStarStripDismiss;
    window.isDetailsViewActive = isDetailsViewActive;
    window.apiNoCacheUrl = apiNoCacheUrl;
})();
