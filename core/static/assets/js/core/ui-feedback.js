(function() {

window.showConfirm = function(message) {
    return new Promise((resolve) => {
        const modal = document.getElementById('confirm-modal');
        const msg = document.getElementById('confirm-message');
        const yes = document.getElementById('btn-confirm-yes');
        const cancel = document.getElementById('btn-confirm-cancel');

        if (!modal || !msg || !yes || !cancel) {
            resolve(window.confirm(message));
            return;
        }

        msg.textContent = message;
        modal.classList.add('active');

        function onYes() {
            cleanup();
            resolve(true);
        }

        function onCancel() {
            cleanup();
            resolve(false);
        }

        function onKey(event) {
            if (event.key === 'Escape') {
                event.preventDefault();
                onCancel();
            }
        }

        function cleanup() {
            modal.classList.remove('active');
            yes.removeEventListener('click', onYes);
            cancel.removeEventListener('click', onCancel);
            modal.removeEventListener('click', onOverlay);
            document.removeEventListener('keydown', onKey);
        }

        function onOverlay(event) {
            if (event.target === modal) {
                onCancel();
            }
        }

        yes.addEventListener('click', onYes);
        cancel.addEventListener('click', onCancel);
        modal.addEventListener('click', onOverlay);
        document.addEventListener('keydown', onKey);
    });
};

window.showPrompt = function({ title = 'Enter text', message = '', defaultValue = '', confirmText = 'Save', cancelText = 'Cancel' } = {}) {
    return new Promise((resolve) => {
        const modal = document.getElementById('prompt-modal');
        const titleEl = document.getElementById('prompt-title');
        const msg = document.getElementById('prompt-message');
        const input = document.getElementById('prompt-input');
        const yes = document.getElementById('btn-prompt-yes');
        const cancel = document.getElementById('btn-prompt-cancel');

        if (!modal || !titleEl || !msg || !input || !yes || !cancel) {
            resolve(window.prompt(message || title, defaultValue));
            return;
        }

        titleEl.textContent = title;
        msg.textContent = message;
        input.value = String(defaultValue ?? '');
        yes.textContent = confirmText;
        cancel.textContent = cancelText;
        modal.classList.add('active');

        function onConfirm() {
            const val = String(input.value || '');
            cleanup();
            resolve(val);
        }

        function onCancel() {
            cleanup();
            resolve(null);
        }

        function onKey(event) {
            if (event.key === 'Escape') {
                event.preventDefault();
                onCancel();
            } else if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                onConfirm();
            }
        }

        function onOverlay(event) {
            if (event.target === modal) {
                onCancel();
            }
        }

        function cleanup() {
            modal.classList.remove('active');
            btnYes.removeEventListener('click', handleConfirm);
            btnCancel.removeEventListener('click', handleCancel);
            modal.removeEventListener('click', handleOverlayClick);
            document.removeEventListener('keydown', handleKeydown);
            inputEl.removeEventListener('keydown', handleKeydown);
        }

        btnYes.addEventListener('click', handleConfirm);
        btnCancel.addEventListener('click', handleCancel);
        modal.addEventListener('click', handleOverlayClick);
        document.addEventListener('keydown', handleKeydown);
        inputEl.addEventListener('keydown', handleKeydown);

        requestAnimationFrame(() => {
            inputEl.focus();
            inputEl.select();
        });
    });
};


window.showToast = function(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');


    let bg = '#141416';
    let color = '#fff';
    let border = '#333';

    if (type === 'success') { bg = 'rgba(0, 255, 157, 0.1)'; color = '#00FF9D'; border = 'rgba(0, 255, 157, 0.3)'; }
    if (type === 'error') { bg = 'rgba(255, 0, 85, 0.1)'; color = '#FF0055'; border = 'rgba(255, 0, 85, 0.3)'; }
    if (type === 'warn') { bg = 'rgba(255, 189, 46, 0.1)'; color = '#FFBD2E'; border = 'rgba(255, 189, 46, 0.3)'; }
    if (type === 'info') { bg = 'rgba(0, 243, 255, 0.1)'; color = '#00F3FF'; border = 'rgba(0, 243, 255, 0.3)'; }

    toast.style.cssText = `
        background: ${bg};
        color: ${color};
        border: 1px solid ${border};
        padding: 12px 15px;
        border-radius: 4px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 12px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.5);
        min-width: 250px;
        max-width: 400px;
        animation: slideIn 0.3s ease-out forwards;
        display: flex;
        align-items: center;
        gap: 12px;
        backdrop-filter: blur(5px);
    `;

    let icon = 'ℹ';
    if (type === 'success') icon = '✓';
    if (type === 'error') icon = '✕';
    if (type === 'warn') icon = '⚠';

    toast.innerHTML = `<span style="font-weight: bold; font-size: 14px;">${icon}</span> <span style="line-height: 1.4;">${escapeHtml(message)}</span>`;

    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(20px)';
        toast.style.transition = 'all 0.3s ease-in';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}


if (!document.getElementById('toast-style')) {
    const style = document.createElement('style');
    style.id = 'toast-style';
    style.innerHTML = `
        @keyframes slideIn {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
    `;
    document.head.appendChild(style);
}


})();
