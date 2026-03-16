/* === FlyCal — Toast Notification System === */

const Toast = {
    _container: null,

    _ensureContainer() {
        if (this._container) return this._container;
        this._container = document.createElement('div');
        this._container.id = 'toastContainer';
        this._container.className = 'toast-container';
        document.body.appendChild(this._container);
        return this._container;
    },

    /**
     * Show a toast notification
     * @param {string} message - Text to display
     * @param {string} type - 'success' | 'error' | 'info' | 'warning'
     * @param {number} duration - Auto-dismiss in ms (0 = sticky)
     */
    show(message, type = 'info', duration = 4000) {
        const container = this._ensureContainer();
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;

        const icons = { success: '✓', error: '✕', warning: '⚠', info: 'ℹ' };
        toast.innerHTML = `
            <span class="toast-icon">${icons[type] || icons.info}</span>
            <span class="toast-msg">${message}</span>
            <button class="toast-close" onclick="Toast.dismiss(this.parentElement)">✕</button>
        `;

        container.appendChild(toast);
        // Trigger animation
        requestAnimationFrame(() => toast.classList.add('toast-visible'));

        if (duration > 0) {
            setTimeout(() => this.dismiss(toast), duration);
        }
        return toast;
    },

    success(message, duration = 4000) { return this.show(message, 'success', duration); },
    error(message, duration = 6000) { return this.show(message, 'error', duration); },
    warning(message, duration = 5000) { return this.show(message, 'warning', duration); },
    info(message, duration = 4000) { return this.show(message, 'info', duration); },

    dismiss(toast) {
        if (!toast || toast._dismissing) return;
        toast._dismissing = true;
        toast.classList.remove('toast-visible');
        toast.classList.add('toast-exit');
        setTimeout(() => toast.remove(), 300);
    },

    /**
     * Show confirmation toast with Yes/No buttons
     * @param {string} message
     * @param {Function} onConfirm
     * @param {Function} onCancel
     */
    confirm(message, onConfirm, onCancel) {
        const container = this._ensureContainer();
        const toast = document.createElement('div');
        toast.className = 'toast toast-warning';

        toast.innerHTML = `
            <span class="toast-icon">⚠</span>
            <span class="toast-msg">${message}</span>
            <div class="toast-actions">
                <button class="toast-btn toast-btn-confirm">Yes</button>
                <button class="toast-btn toast-btn-cancel">No</button>
            </div>
        `;

        toast.querySelector('.toast-btn-confirm').onclick = () => {
            this.dismiss(toast);
            if (onConfirm) onConfirm();
        };
        toast.querySelector('.toast-btn-cancel').onclick = () => {
            this.dismiss(toast);
            if (onCancel) onCancel();
        };

        container.appendChild(toast);
        requestAnimationFrame(() => toast.classList.add('toast-visible'));
        return toast;
    },
};
