/* === FlyCal — Toast Notification System === */

const Toast = {
    _container: null,
    _audioCtx: null,

    _ensureContainer() {
        if (this._container) return this._container;
        this._container = document.createElement('div');
        this._container.id = 'toastContainer';
        this._container.className = 'toast-container';
        document.body.appendChild(this._container);
        return this._container;
    },

    /** Play a short synthesized beep via Web Audio API */
    _playSound(type = 'info') {
        try {
            if (!this._audioCtx) {
                this._audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            }
            const ctx = this._audioCtx;
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain);
            gain.connect(ctx.destination);

            // Different tones per type
            const tones = {
                success: { freq: 880, dur: 0.15, freq2: 1100 },
                error:   { freq: 300, dur: 0.25, freq2: 200 },
                warning: { freq: 600, dur: 0.2,  freq2: 500 },
                info:    { freq: 700, dur: 0.12, freq2: 900 },
            };
            const t = tones[type] || tones.info;

            osc.type = 'sine';
            osc.frequency.setValueAtTime(t.freq, ctx.currentTime);
            osc.frequency.linearRampToValueAtTime(t.freq2, ctx.currentTime + t.dur);
            gain.gain.setValueAtTime(0.15, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + t.dur + 0.05);

            osc.start(ctx.currentTime);
            osc.stop(ctx.currentTime + t.dur + 0.1);
        } catch (e) {
            // Audio not available — silently ignore
        }
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

        // Play sound
        this._playSound(type);

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
        this._playSound('warning');
        return toast;
    },
};
