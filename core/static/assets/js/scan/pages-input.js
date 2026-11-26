(function() {
    const MIN = 1;
    const MAX = 50;
    const ATTR = 'data-pages-fixed';

    function pagesInput() {
        return document.querySelector('#configForm input[name="pages"]');
    }

    function randInt(min, max) {
        return Math.floor(Math.random() * (max - min + 1)) + min;
    }

    function clampPages(val) {
        if (!Number.isFinite(val)) return randInt(MIN, MAX);
        return Math.max(MIN, Math.min(MAX, val));
    }

    function isFixed() {
        const el = pagesInput();
        return !!el && el.getAttribute(ATTR) === '1';
    }

    function setRandom(force = false) {
        const el = pagesInput();
        if (!el) return;
        if (!force && isFixed()) return;
        el.value = String(randInt(MIN, MAX));
        if (!isFixed()) {
            el.setAttribute(ATTR, '0');
        }
    }

    function initPages() {
        const el = pagesInput();
        if (!el) return;

        el.setAttribute(ATTR, '0');
        el.min = String(MIN);
        el.max = String(MAX);

        const onBlur = () => {
            const raw = String(el.value || '').trim();
            if (!raw) {
                el.setAttribute(ATTR, '0');
                setRandom(true);
                return;
            }

            const num = Number.parseInt(raw, 10);
            if (!Number.isFinite(num)) {
                el.setAttribute(ATTR, '0');
                setRandom(true);
                return;
            }

            el.value = String(clampPages(num));
            el.setAttribute(ATTR, '1');
        };

        el.addEventListener('input', () => {
            const raw = String(el.value || '').trim();
            if (!raw) {
                el.setAttribute(ATTR, '0');
                return;
            }
            const num = Number.parseInt(raw, 10);
            if (Number.isFinite(num)) {
                el.setAttribute(ATTR, '1');
            }
        });

        el.addEventListener('blur', onBlur);
        setRandom(true);
    }

    function prepPages() {
        const el = pagesInput();
        if (!el) return randInt(MIN, MAX);
        if (!isFixed()) {
            setRandom(true);
        }
        const num = Number.parseInt(String(el.value || ''), 10);
        const val = clampPages(num);
        el.value = String(val);
        return val;
    }

    window.initializePagesAutoRandom = initPages;
    window.preparePagesValueBeforeScan = prepPages;
})();
