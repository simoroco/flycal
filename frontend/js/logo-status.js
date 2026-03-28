/* Polls the running search status and animates the logo on any page */
(function () {
    let _logoInterval = null;

    function setLogoSearching(active) {
        document.querySelectorAll('.logo-img').forEach(el => {
            if (active) el.classList.add('logo-searching');
            else el.classList.remove('logo-searching');
        });
    }

    async function checkRunning() {
        try {
            const res = await fetch('/api/flights/running');
            if (!res.ok) return;
            const data = await res.json();
            setLogoSearching(data && data.running);
        } catch (e) { /* ignore */ }
    }

    document.addEventListener('DOMContentLoaded', () => {
        checkRunning();
        _logoInterval = setInterval(checkRunning, 4000);
    });
})();
