(function() {
    const MENU_GAP = 6;
    const VIEWPORT_PAD = 8;
    let activeController = null;
    let valueHookInstalled = false;

    function installNativeValueHook() {
        if (valueHookInstalled) {
            return;
        }
        valueHookInstalled = true;

        const valueDesc = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value');
        if (valueDesc && valueDesc.set && valueDesc.get) {
            Object.defineProperty(HTMLSelectElement.prototype, 'value', {
                configurable: true,
                enumerable: valueDesc.enumerable,
                get: function() {
                    return valueDesc.get.call(this);
                },
                set: function(nextValue) {
                    valueDesc.set.call(this, nextValue);
                    this.dispatchEvent(new CustomEvent('zt-select:sync'));
                }
            });
        }

        const indexDesc = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'selectedIndex');
        if (indexDesc && indexDesc.set && indexDesc.get) {
            Object.defineProperty(HTMLSelectElement.prototype, 'selectedIndex', {
                configurable: true,
                enumerable: indexDesc.enumerable,
                get: function() {
                    return indexDesc.get.call(this);
                },
                set: function(nextIndex) {
                    indexDesc.set.call(this, nextIndex);
                    this.dispatchEvent(new CustomEvent('zt-select:sync'));
                }
            });
        }
    }

    function closeActiveMenu(restoreFocus) {
        if (!activeController) {
            return;
        }
        activeController.close(Boolean(restoreFocus));
    }

    function createChevronSvg() {
        return '<svg width="12" height="12" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg">'
            + '<path d="M2.5 4.25L6 7.75L9.5 4.25" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>'
            + '</svg>';
    }

    function enhanceSelect(selectEl) {
        if (!selectEl || selectEl.multiple || selectEl.dataset.ztSelectReady === '1') {
            return;
        }
        selectEl.dataset.ztSelectReady = '1';

        const container = document.createElement('div');
        container.className = 'zt-select';
        if (selectEl.className) {
            selectEl.className.split(/\s+/).filter(Boolean).forEach((cls) => {
                if (cls !== 'zt-select-native') {
                    container.classList.add(cls);
                }
            });
        }

        const trigger = document.createElement('button');
        trigger.type = 'button';
        trigger.className = 'zt-select-trigger';
        trigger.setAttribute('aria-haspopup', 'listbox');
        trigger.setAttribute('aria-expanded', 'false');
        const ariaLabel = selectEl.getAttribute('aria-label');
        if (ariaLabel) {
            trigger.setAttribute('aria-label', ariaLabel);
        }

        const labelSpan = document.createElement('span');
        labelSpan.className = 'zt-select-label';

        const arrowSpan = document.createElement('span');
        arrowSpan.className = 'zt-select-arrow';
        arrowSpan.setAttribute('aria-hidden', 'true');
        arrowSpan.innerHTML = createChevronSvg();

        trigger.appendChild(labelSpan);
        trigger.appendChild(arrowSpan);
        container.appendChild(trigger);

        const menu = document.createElement('div');
        menu.className = 'zt-select-menu';
        menu.setAttribute('role', 'listbox');
        menu.hidden = true;
        document.body.appendChild(menu);

        selectEl.classList.add('zt-select-native');
        selectEl.tabIndex = -1;
        selectEl.setAttribute('aria-hidden', 'true');
        selectEl.insertAdjacentElement('afterend', container);

        let isOpen = false;
        let highlightedIndex = -1;
        let optionItems = [];

        function getSelectedOption() {
            const idx = selectEl.selectedIndex;
            if (idx >= 0 && selectEl.options[idx]) {
                return selectEl.options[idx];
            }
            return selectEl.options[0] || null;
        }

        function syncTriggerState() {
            const selected = getSelectedOption();
            labelSpan.textContent = selected ? selected.textContent.trim() : '';
            const isDisabled = Boolean(selectEl.disabled);
            trigger.disabled = isDisabled;
            container.classList.toggle('is-disabled', isDisabled);

            if (isOpen) {
                renderMenuOptions();
                positionMenu();
            }
        }

        function setHighlighted(nextIdx) {
            if (!optionItems.length) {
                highlightedIndex = -1;
                return;
            }
            highlightedIndex = nextIdx;
            optionItems.forEach((item, i) => {
                item.classList.toggle('is-highlighted', i === highlightedIndex);
            });
            if (highlightedIndex >= 0 && optionItems[highlightedIndex]) {
                optionItems[highlightedIndex].scrollIntoView({ block: 'nearest' });
            }
        }

        function moveHighlight(delta) {
            if (!optionItems.length) {
                return;
            }
            let idx = highlightedIndex;
            for (let step = 0; step < optionItems.length; step++) {
                idx = (idx + delta + optionItems.length) % optionItems.length;
                if (!optionItems[idx].classList.contains('is-disabled')) {
                    setHighlighted(idx);
                    return;
                }
            }
        }

        function selectOptionAt(optionIndex) {
            const opt = selectEl.options[optionIndex];
            if (!opt || opt.disabled) {
                return;
            }
            const changed = selectEl.selectedIndex !== optionIndex;
            selectEl.selectedIndex = optionIndex;
            syncTriggerState();
            close(true);
            if (changed) {
                selectEl.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }

        function renderMenuOptions() {
            menu.innerHTML = '';
            optionItems = [];
            const selectedIdx = selectEl.selectedIndex;
            let activeHighlight = -1;

            Array.from(selectEl.options).forEach((opt, idx) => {
                const item = document.createElement('button');
                item.type = 'button';
                item.className = 'zt-select-option';
                item.setAttribute('role', 'option');
                item.dataset.index = String(idx);

                const isSelected = idx === selectedIdx;
                const isDisabled = Boolean(opt.disabled);
                item.setAttribute('aria-selected', isSelected ? 'true' : 'false');
                if (isSelected) {
                    item.classList.add('is-selected');
                    activeHighlight = idx;
                }
                if (isDisabled) {
                    item.classList.add('is-disabled');
                    item.disabled = true;
                }

                const textSpan = document.createElement('span');
                textSpan.className = 'zt-select-option-text';
                textSpan.textContent = opt.textContent.trim();
                item.appendChild(textSpan);

                if (isSelected) {
                    const checkSpan = document.createElement('span');
                    checkSpan.className = 'zt-select-option-check';
                    checkSpan.textContent = '✓';
                    item.appendChild(checkSpan);
                }

                item.addEventListener('mouseenter', () => {
                    if (!isDisabled) {
                        setHighlighted(idx);
                    }
                });
                item.addEventListener('mousedown', (e) => {
                    e.preventDefault();
                });
                item.addEventListener('click', () => {
                    selectOptionAt(idx);
                });

                menu.appendChild(item);
                optionItems.push(item);
            });

            if (activeHighlight >= 0) {
                setHighlighted(activeHighlight);
            } else {
                const firstEnabled = optionItems.findIndex((el) => !el.classList.contains('is-disabled'));
                setHighlighted(firstEnabled);
            }
        }

        function positionMenu() {
            const rect = trigger.getBoundingClientRect();
            const viewportH = window.innerHeight;
            const viewportW = window.innerWidth;
            const spaceBelow = viewportH - rect.bottom - VIEWPORT_PAD;
            const spaceAbove = rect.top - VIEWPORT_PAD;

            menu.style.minWidth = `${Math.max(rect.width, 140)}px`;
            menu.style.maxWidth = `${Math.min(viewportW - VIEWPORT_PAD * 2, Math.max(rect.width * 1.5, 320))}px`;

            const menuHeight = Math.min(menu.scrollHeight || 220, 260);
            const openUp = spaceBelow < Math.min(menuHeight, 160) && spaceAbove > spaceBelow;
            const maxH = Math.max(110, Math.min(260, openUp ? spaceAbove - MENU_GAP : spaceBelow - MENU_GAP));

            menu.style.maxHeight = `${maxH}px`;

            let left = rect.left;
            const menuWidth = Math.max(rect.width, menu.offsetWidth || rect.width);
            if (left + menuWidth > viewportW - VIEWPORT_PAD) {
                left = Math.max(VIEWPORT_PAD, viewportW - VIEWPORT_PAD - menuWidth);
            }
            menu.style.left = `${left}px`;

            if (openUp) {
                const top = Math.max(VIEWPORT_PAD, rect.top - MENU_GAP - Math.min(menuHeight, maxH));
                menu.style.top = `${top}px`;
                menu.classList.add('is-open-up');
            } else {
                const top = Math.min(viewportH - VIEWPORT_PAD - 60, rect.bottom + MENU_GAP);
                menu.style.top = `${top}px`;
                menu.classList.remove('is-open-up');
            }
        }

        function open() {
            if (selectEl.disabled || isOpen) {
                return;
            }
            closeActiveMenu(false);
            isOpen = true;
            activeController = controller;
            renderMenuOptions();
            menu.hidden = false;
            container.classList.add('is-open');
            trigger.setAttribute('aria-expanded', 'true');
            positionMenu();
        }

        function close(restoreFocus) {
            if (!isOpen) {
                return;
            }
            isOpen = false;
            menu.hidden = true;
            container.classList.remove('is-open');
            trigger.setAttribute('aria-expanded', 'false');
            if (activeController === controller) {
                activeController = null;
            }
            if (restoreFocus) {
                trigger.focus();
            }
        }

        const controller = {
            close,
            menu,
            container
        };

        trigger.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (isOpen) {
                close(false);
            } else {
                open();
            }
        });

        trigger.addEventListener('keydown', (e) => {
            if (selectEl.disabled) {
                return;
            }
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                if (!isOpen) {
                    open();
                } else {
                    moveHighlight(1);
                }
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                if (!isOpen) {
                    open();
                } else {
                    moveHighlight(-1);
                }
            } else if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                if (!isOpen) {
                    open();
                } else if (highlightedIndex >= 0) {
                    selectOptionAt(highlightedIndex);
                }
            } else if (e.key === 'Escape' && isOpen) {
                e.preventDefault();
                close(true);
            } else if (e.key === 'Tab' && isOpen) {
                close(false);
            }
        });

        selectEl.addEventListener('change', syncTriggerState);
        selectEl.addEventListener('zt-select:sync', syncTriggerState);

        const observer = new MutationObserver(() => {
            syncTriggerState();
        });
        observer.observe(selectEl, {
            childList: true,
            subtree: true,
            attributes: true,
            attributeFilter: ['disabled', 'selected', 'label']
        });

        syncTriggerState();
    }

    function bindGlobalDismiss() {
        if (document.body.dataset.ztSelectGlobalBound === '1') {
            return;
        }
        document.body.dataset.ztSelectGlobalBound = '1';

        document.addEventListener('mousedown', (e) => {
            if (!activeController) {
                return;
            }
            const target = e.target;
            if (activeController.container.contains(target) || activeController.menu.contains(target)) {
                return;
            }
            closeActiveMenu(false);
        });

        window.addEventListener('resize', () => closeActiveMenu(false));
        window.addEventListener('scroll', (e) => {
            if (!activeController) {
                return;
            }
            if (e.target === activeController.menu || activeController.menu.contains(e.target)) {
                return;
            }
            closeActiveMenu(false);
        }, true);
    }

    function initializeCustomSelects(root = document) {
        installNativeValueHook();
        bindGlobalDismiss();
        const selects = root.querySelectorAll('select');
        selects.forEach(enhanceSelect);
    }

    window.initializeCustomSelects = initializeCustomSelects;
})();
