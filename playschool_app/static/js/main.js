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

    // --- HIGH PERFORMANCE AUTO TRANSLATION (Google Translate Integration) ---
    const langBtn = document.getElementById('langToggle');
    const langBtnMobile = document.getElementById('langToggleMobile');
    
    // Add required div for Google API
    const translateDiv = document.createElement('div');
    translateDiv.id = 'google_translate_element';
    translateDiv.style.display = 'none';
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

    // Dynamically Load Google Script
    const translateScript = document.createElement('script');
    translateScript.src = "//translate.google.com/translate_a/element.js?cb=googleTranslateElementInit";
    document.body.appendChild(translateScript);

    // Bulletproof Enterprise Translation using Cookie Logic
    function setTranslateCookie(lang) {
        const domain = window.location.hostname;
        // Construct path based value e.g. /en/hi
        const cookieVal = "/en/" + lang; 
        
        // Clear old ones first to prevent clash
        document.cookie = "googtrans=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
        document.cookie = "googtrans=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/; domain=" + domain;
        
        // Set primary cookie
        document.cookie = "googtrans=" + cookieVal + "; path=/;";
        document.cookie = "googtrans=" + cookieVal + "; path=/; domain=" + domain;
        
        localStorage.setItem('lang', lang);
    }

    function changeLanguage(langCode) {
        setTranslateCookie(langCode);
        // Standard Google DOM Trigger fallback
        const select = document.querySelector('.goog-te-combo');
        if (select) {
            select.value = langCode;
            select.dispatchEvent(new Event('change'));
            setTimeout(() => { updateLangBtnLabels(langCode); }, 200);
        } else {
            // Force reload to pick up cookie if DOM node missing
            window.location.reload();
        }
    }

    function updateLangBtnLabels(lang) {
        if(langBtn) langBtn.innerHTML = lang === 'en' ? 'अ <span data-i18n="Lang">Translate to Hindi</span>' : 'A <span data-i18n="Lang">English में बदलें</span>';
        if(langBtnMobile) langBtnMobile.innerText = lang === 'en' ? 'अ' : 'A';
    }

    let currentLang = localStorage.getItem('lang') || 'en';
    
    function handleLangClick() {
        currentLang = currentLang === 'en' ? 'hi' : 'en';
        // Set it and reload is most secure for full page
        setTranslateCookie(currentLang);
        window.location.reload();
    }

    if(langBtn) langBtn.addEventListener('click', handleLangClick);
    if(langBtnMobile) langBtnMobile.addEventListener('click', handleLangClick);

    // Auto restore language on init
    setTimeout(() => {
        if(currentLang === 'hi') changeLanguage('hi');
        else updateLangBtnLabels('en');
    }, 1000);
});
