// ============================================
// PlaySchool Hub - Main JS
// ============================================

// Sidebar toggle for mobile
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('overlay');
    if (sidebar) {
        sidebar.classList.toggle('open');
        overlay.classList.toggle('open');
    }
}

// Auto-dismiss flash messages
document.addEventListener('DOMContentLoaded', function() {
    const flashes = document.querySelectorAll('.flash');
    flashes.forEach(flash => {
        setTimeout(() => {
            flash.style.opacity = '0';
            flash.style.transform = 'translateY(-8px)';
            flash.style.transition = 'all .4s ease';
            setTimeout(() => flash.remove(), 400);
        }, 4000);
    });

    // Animate progress bars
    setTimeout(() => {
        document.querySelectorAll('[style*="width:"]').forEach(el => {
            const width = el.style.width;
            el.style.width = '0%';
            requestAnimationFrame(() => {
                setTimeout(() => { el.style.width = width; }, 100);
            });
        });
    }, 300);

    // --- Theme Toggling ---
    const themeBtn = document.getElementById('themeToggle');
    const themeBtnMobile = document.getElementById('themeToggleMobile');
    
    function applyTheme(theme) {
        if(theme === 'dark') {
            document.documentElement.setAttribute('data-theme', 'dark');
            if(themeBtn) themeBtn.innerHTML = '🌙 <span data-i18n="Theme">Theme</span>';
            if(themeBtnMobile) themeBtnMobile.innerHTML = '🌙';
        } else {
            document.documentElement.removeAttribute('data-theme');
            if(themeBtn) themeBtn.innerHTML = '☀️ <span data-i18n="Theme">Theme</span>';
            if(themeBtnMobile) themeBtnMobile.innerHTML = '☀️';
        }
    }
    
    let currentTheme = localStorage.getItem('theme') || 'light';
    applyTheme(currentTheme);

    function toggleTheme() {
        currentTheme = currentTheme === 'light' ? 'dark' : 'light';
        localStorage.setItem('theme', currentTheme);
        applyTheme(currentTheme);
    }

    if(themeBtn) themeBtn.addEventListener('click', toggleTheme);
    if(themeBtnMobile) themeBtnMobile.addEventListener('click', toggleTheme);

    // --- Google Translate integration ---
    const langBtn = document.getElementById('langToggle');
    const langBtnMobile = document.getElementById('langToggleMobile');
    
    // Add required div for Google API
    const translateDiv = document.createElement('div');
    translateDiv.id = 'google_translate_element';
    // Keep the widget off-screen instead of display:none; Google Translate
    // does not reliably initialize a hidden select element.
    translateDiv.style.position = 'fixed';
    translateDiv.style.left = '-10000px';
    translateDiv.style.top = '-10000px';
    translateDiv.style.width = '1px';
    translateDiv.style.height = '1px';
    translateDiv.style.overflow = 'hidden';
    document.body.appendChild(translateDiv);

    // Add custom CSS to HIDE the Google Translate Top Bar toolbar but keep text changed
    const translateStyle = document.createElement('style');
    translateStyle.innerHTML = `
        .goog-te-banner-frame.skiptranslate, .goog-te-gadget-icon { display: none !important; }
        body { top: 0px !important; }
        .goog-logo-link { display: none !important; }
        .goog-te-gadget { color: transparent !important; }
        .goog-te-gadget .goog-te-combo { padding: 4px; border-radius: 4px; }
    `;
    document.head.appendChild(translateStyle);

    window.googleTranslateElementInit = function() {
        new google.translate.TranslateElement({
            pageLanguage: 'en', 
            includedLanguages: 'hi,en', 
            autoDisplay: false
        }, 'google_translate_element');
    }

    // Dynamically load Google Script once.
    const translateScript = document.createElement('script');
    translateScript.src = "//translate.google.com/translate_a/element.js?cb=googleTranslateElementInit";
    document.body.appendChild(translateScript);

    const supportedLanguages = new Set(['en', 'hi']);

    // Google reads this cookie on the next page load. Do not set a domain
    // cookie: it conflicts on localhost/IP hosts and can leave two cookies
    // with different values on the production hostname.
    function setTranslateCookie(lang) {
        if (!supportedLanguages.has(lang)) return;
        const cookieVal = `/en/${lang}`;
        document.cookie = `googtrans=${cookieVal}; path=/; SameSite=Lax`;
        localStorage.setItem('lang', lang);
    }

    function updateLangBtnLabels(lang) {
        if(langBtn) langBtn.innerHTML = lang === 'en' ? 'अ <span data-i18n="Lang">Translate to Hindi</span>' : 'A <span data-i18n="Lang">English में बदलें</span>';
        if(langBtnMobile) langBtnMobile.innerText = lang === 'en' ? 'अ' : 'A';
    }

    function applyGoogleLanguage(langCode) {
        const select = document.querySelector('.goog-te-combo');
        if (select) {
            select.value = langCode;
            select.dispatchEvent(new Event('change'));
            sessionStorage.removeItem('translate-reload');
            updateLangBtnLabels(langCode);
            return true;
        }
        return false;
    }

    let currentLang = localStorage.getItem('lang') || 'en';

    function handleLangClick() {
        currentLang = currentLang === 'en' ? 'hi' : 'en';
        setTranslateCookie(currentLang);
        updateLangBtnLabels(currentLang);
        if (!applyGoogleLanguage(currentLang)) {
            // One reload lets Google consume the cookie. The session guard
            // prevents an endless reload loop if the external script fails.
            const reloadKey = `translate-reload:${currentLang}`;
            if (sessionStorage.getItem('translate-reload') !== reloadKey) {
                sessionStorage.setItem('translate-reload', reloadKey);
                window.location.reload();
            }
        }
    }

    if(langBtn) langBtn.addEventListener('click', handleLangClick);
    if(langBtnMobile) langBtnMobile.addEventListener('click', handleLangClick);

    // Restore the selected language after the widget has had time to load.
    updateLangBtnLabels(currentLang);
    if (currentLang === 'hi') {
        setTimeout(() => applyGoogleLanguage('hi'), 1000);
    }
});
