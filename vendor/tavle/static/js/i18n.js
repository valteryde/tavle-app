/**
 * Internationalization (i18n) Module
 * Supports multiple languages with localStorage persistence
 */

const translations = {
    en: {
        // App name
        appName: 'Collaborative Whiteboard',
        
        // Tools
        tools: {
            draw: 'Draw',
            erase: 'Eraser',
            select: 'Select',
            pan: 'Pan',
        },
        
        // Tool tooltips
        tooltips: {
            draw: 'Draw (D)',
            erase: 'Eraser (E)',
            select: 'Select (V)',
            pan: 'Pan (H)',
            strokeColor: 'Stroke Color',
            backgroundColor: 'Background Color',
            toggleGrid: 'Toggle Grid (G)',
            zoomIn: 'Zoom In',
            zoomOut: 'Zoom Out',
            resetZoom: 'Reset Zoom',
            clear: 'Clear Canvas',
            uploadImage: 'Add Image (Ctrl+V to paste)',
            export: 'Export as PNG',
            undo: 'Undo',
            redo: 'Redo',
        },
        
        // Toolbar labels
        toolbar: {
            strokeColor: 'Stroke Color',
            background: 'Background',
            customColor: 'Custom color',
            strokeWidth: 'Stroke Width',
            eraserSize: 'Eraser Size',
            extraThin: 'Extra thin',
            thin: 'Thin',
            medium: 'Medium',
            thick: 'Thick',
            extraThick: 'Extra thick',
            small: 'Small',
            large: 'Large',
            extraLarge: 'Extra large',
            more: 'More tools',
            groupCanvas: 'Canvas',
            groupZoom: 'Zoom',
            groupActions: 'Actions',
        },
        
        // User panel
        userPanel: {
            you: 'You',
            users: 'Users',
            editName: 'Edit name',
            jumpToUser: 'Jump to user',
            online: 'online',
            noUsers: 'No other users online',
        },
        
        // Connection status
        connection: {
            connected: 'Connected',
            disconnected: 'Disconnected',
            connecting: 'Connecting...',
            rateLimited: 'Rate Limited',
            rateLimitedHint: 'Too many refreshes - please wait',
        },
        
        // Name picker modal
        namePicker: {
            welcomeLine1: 'Welcome to',
            welcomeLine2: 'the Whiteboard',
            subtitle: 'Enter your name to collaborate',
            yourName: 'Your Name',
            placeholder: 'Type here...',
            suggestions: 'Or pick a fun name',
            join: 'Join Whiteboard',
            nameRequired: 'Please enter a name',
        },
        
        // Suggested rare animal names
        animalNames: {
            axolotl: 'Axolotl',
            quokka: 'Quokka',
            pangolin: 'Pangolin',
            okapi: 'Okapi',
            narwhal: 'Narwhal',
            kakapo: 'Kakapo',
            fossa: 'Fossa',
            dugong: 'Dugong',
            saola: 'Saola',
            tarsier: 'Tarsier',
        },
        
        // Loading
        loading: {
            text: 'Loading whiteboard...',
            preparing: 'Preparing your canvas',
        },
        
        // Confirmations
        confirm: {
            clearCanvas: 'Clear the entire canvas?',
        },
        
        // Settings
        settings: {
            language: 'Language',
            english: 'English',
            danish: 'Danish',
        },
        
        // Landing page
        landing: {
            title: 'Collaborative Whiteboard',
            subtitle: 'Real-time collaboration',
            feature1Title: 'Real-time Collaboration',
            feature1Desc: 'See everyone\'s cursors and strokes live',
            feature2Title: 'Image Support',
            feature2Desc: 'Paste or upload images directly',
            feature3Title: 'Private Boards',
            feature3Desc: 'Secure access with unique tokens',
            needBoard: 'Need a board?',
            contactAdmin: 'Contact your administrator to create one.',
            footer: 'Built with Flask, Socket.IO, and ❤️',
            apiDocs: 'API Documentation',
        },
        
        // Setup page
        setup: {
            title: 'Welcome to Whiteboard',
            subtitle: 'First-time setup',
            setupComplete: 'Setup Complete!',
            setupCompleteDesc: 'Your whiteboard server is now configured and ready to use.',
            adminToken: 'Admin API Token',
            tokenHint: 'Save this token securely. You\'ll need it to create boards and manage the API.',
            securityNotice: 'Security Notice',
            securityPoint1: 'This token grants full admin access',
            securityPoint2: 'Store it in a password manager',
            securityPoint3: 'This screen will only appear once',
            quickStart: 'Quick Start: Create a Board',
            confirmSaved: 'I have securely saved my admin token and understand this page will not be shown again.',
            continueBtn: 'Complete Setup →',
            cliHint: 'Or use CLI:',
            configSaved: 'Configuration saved to',
            copy: 'Copy',
            copied: 'Copied!',
        },

        // Error pages
        errors: {
            // 400 Bad Request
            badRequest: 'Bad Request',
            badRequestDesc: 'The request could not be understood. Please check your input and try again.',
            badRequestHint: 'Double-check the URL or form data you submitted.',
            
            // 403 Forbidden
            forbidden: 'Access Denied',
            forbiddenDesc: 'You don\'t have permission to access this resource.',
            forbiddenHint: 'If you believe this is an error, please contact the administrator.',
            
            // 404 Not Found
            notFound: 'Page Not Found',
            notFoundDesc: 'The page you\'re looking for doesn\'t exist or has been moved.',
            
            // 429 Too Many Requests
            tooManyRequests: 'Too Many Requests',
            tooManyRequestsDesc: 'You\'ve made too many requests. Please wait a moment and try again.',
            tooManyRequestsHint: 'Rate limiting helps protect our service. Please wait before retrying.',
            
            // 500 Server Error
            serverError: 'Server Error',
            serverErrorDesc: 'Something went wrong on our end. We\'re working to fix it.',
            serverErrorHint: 'Try refreshing the page or come back later.',
            
            // Common actions
            backHome: 'Back to Home',
            goBack: 'Go Back',
            refresh: 'Refresh Page',
            tryAgain: 'Try Again',

            // Image upload
            imageTooLarge: 'Image is too large. Try a smaller file.',
            imageUploadFailed: 'Could not add image. Please try again.',
            imageBoardFull: 'Board image limit reached. Remove an image first.',
        },
    },
    
    da: {
        // App name
        appName: 'Samarbejds Whiteboard',
        
        // Tools
        tools: {
            draw: 'Tegn',
            erase: 'Viskelæder',
            select: 'Vælg',
            pan: 'Panorer',
        },
        
        // Tool tooltips
        tooltips: {
            draw: 'Tegn (D)',
            erase: 'Viskelæder (E)',
            select: 'Vælg (V)',
            pan: 'Panorer (H)',
            strokeColor: 'Penfarve',
            backgroundColor: 'Baggrundsfarve',
            toggleGrid: 'Vis/skjul gitter (G)',
            zoomIn: 'Zoom ind',
            zoomOut: 'Zoom ud',
            resetZoom: 'Nulstil zoom',
            clear: 'Ryd tavle',
            uploadImage: 'Tilføj billede (Ctrl+V for at indsætte)',
            export: 'Eksporter som PNG',
            undo: 'Fortryd',
            redo: 'Gentag',
        },
        
        // Toolbar labels
        toolbar: {
            strokeColor: 'Penfarve',
            background: 'Baggrund',
            customColor: 'Brugerdefineret farve',
            strokeWidth: 'Pentykkelse',
            eraserSize: 'Viskelæder størrelse',
            extraThin: 'Ekstra tynd',
            thin: 'Tynd',
            medium: 'Medium',
            thick: 'Tyk',
            extraThick: 'Ekstra tyk',
            small: 'Lille',
            large: 'Stor',
            extraLarge: 'Ekstra stor',
            more: 'Flere værktøjer',
            groupCanvas: 'Tavle',
            groupZoom: 'Zoom',
            groupActions: 'Handlinger',
        },
        
        // User panel
        userPanel: {
            you: 'Dig',
            users: 'Brugere',
            editName: 'Rediger navn',
            jumpToUser: 'Gå til bruger',
            online: 'online',
            noUsers: 'Ingen andre brugere online',
        },
        
        // Connection status
        connection: {
            connected: 'Forbundet',
            disconnected: 'Afbrudt',
            connecting: 'Forbinder...',
            rateLimited: 'Begrænset',
            rateLimitedHint: 'For mange genindlæsninger - vent venligst',
        },
        
        // Name picker modal
        namePicker: {
            welcomeLine1: 'Velkommen til',
            welcomeLine2: 'Whiteboard',
            subtitle: 'Indtast dit navn for at samarbejde',
            yourName: 'Dit Navn',
            placeholder: 'Skriv her...',
            suggestions: 'Eller vælg et sjovt navn',
            join: 'Deltag',
            nameRequired: 'Indtast venligst et navn',
        },
        
        // Suggested rare animal names
        animalNames: {
            axolotl: 'Axolotl',
            quokka: 'Quokka',
            pangolin: 'Skældyr',
            okapi: 'Okapi',
            narwhal: 'Narhval',
            kakapo: 'Kakapo',
            fossa: 'Fossa',
            dugong: 'Dugong',
            saola: 'Saola',
            tarsier: 'Spøgelsesabe',
        },
        
        // Loading
        loading: {
            text: 'Indlæser whiteboard...',
            preparing: 'Forbereder dit lærred',
        },
        
        // Confirmations
        confirm: {
            clearCanvas: 'Ryd hele tavlen?',
        },
        
        // Settings
        settings: {
            language: 'Sprog',
            english: 'Engelsk',
            danish: 'Dansk',
        },
        
        // Landing page
        landing: {
            title: 'Samarbejds Whiteboard',
            subtitle: 'Samarbejde i realtid',
            feature1Title: 'Realtids Samarbejde',
            feature1Desc: 'Se alles markører og streger live',
            feature2Title: 'Billed Support',
            feature2Desc: 'Indsæt eller upload billeder direkte',
            feature3Title: 'Private Tavler',
            feature3Desc: 'Sikker adgang med unikke tokens',
            needBoard: 'Har du brug for en tavle?',
            contactAdmin: 'Kontakt din administrator for at oprette en.',
            footer: 'Bygget med Flask, Socket.IO og ❤️',
            apiDocs: 'API Dokumentation',
        },
        
        // Setup page
        setup: {
            title: 'Velkommen til Whiteboard',
            subtitle: 'Førstegangs opsætning',
            setupComplete: 'Opsætning fuldført!',
            setupCompleteDesc: 'Din whiteboard server er nu konfigureret og klar til brug.',
            adminToken: 'Admin API Token',
            tokenHint: 'Gem denne token sikkert. Du skal bruge den til at oprette tavler og administrere API\'et.',
            securityNotice: 'Sikkerhedsmeddelelse',
            securityPoint1: 'Denne token giver fuld administratoradgang',
            securityPoint2: 'Gem den i en password manager',
            securityPoint3: 'Denne skærm vises kun én gang',
            quickStart: 'Hurtigstart: Opret en Tavle',
            confirmSaved: 'Jeg har gemt min admin token sikkert og forstår at denne side ikke vises igen.',
            continueBtn: 'Fuldfør opsætning →',
            cliHint: 'Eller brug CLI:',
            configSaved: 'Konfiguration gemt i',
            copy: 'Kopiér',
            copied: 'Kopieret!',
        },

        // Error pages
        errors: {
            // 400 Bad Request
            badRequest: 'Ugyldig Anmodning',
            badRequestDesc: 'Anmodningen kunne ikke forstås. Tjek venligst dine data og prøv igen.',
            badRequestHint: 'Dobbelttjek URL\'en eller de data du har indsendt.',
            
            // 403 Forbidden
            forbidden: 'Adgang Nægtet',
            forbiddenDesc: 'Du har ikke tilladelse til at tilgå denne ressource.',
            forbiddenHint: 'Hvis du mener dette er en fejl, kontakt venligst administratoren.',
            
            // 404 Not Found
            notFound: 'Side Ikke Fundet',
            notFoundDesc: 'Siden du leder efter findes ikke eller er blevet flyttet.',
            
            // 429 Too Many Requests
            tooManyRequests: 'For Mange Anmodninger',
            tooManyRequestsDesc: 'Du har lavet for mange anmodninger. Vent venligst et øjeblik og prøv igen.',
            tooManyRequestsHint: 'Hastighedsbegrænsning hjælper med at beskytte vores service. Vent venligst før du prøver igen.',
            
            // 500 Server Error
            serverError: 'Serverfejl',
            serverErrorDesc: 'Noget gik galt på vores side. Vi arbejder på at løse det.',
            serverErrorHint: 'Prøv at genindlæse siden eller kom tilbage senere.',
            
            // Common actions
            backHome: 'Tilbage til Forsiden',
            goBack: 'Gå Tilbage',
            refresh: 'Genindlæs Side',
            tryAgain: 'Prøv Igen',

            // Image upload
            imageTooLarge: 'Billedet er for stort. Prøv en mindre fil.',
            imageUploadFailed: 'Kunne ikke tilføje billede. Prøv igen.',
            imageBoardFull: 'Billedgrænsen er nået. Fjern et billede først.',
        },
    },
};

// Available languages
const availableLanguages = [
    { code: 'en', name: 'English', nativeName: 'English' },
    { code: 'da', name: 'Danish', nativeName: 'Dansk' },
];

// Current language
let currentLanguage = 'en';

/**
 * Initialize i18n - load language from localStorage or detect from browser
 */
function initI18n() {
    // Try to load from localStorage
    const stored = localStorage.getItem('whiteboardLanguage');
    if (stored && translations[stored]) {
        currentLanguage = stored;
    } else {
        // Try to detect from browser
        const browserLang = navigator.language?.split('-')[0];
        if (browserLang && translations[browserLang]) {
            currentLanguage = browserLang;
        }
    }
    return currentLanguage;
}

/**
 * Get current language code
 */
function getLanguage() {
    return currentLanguage;
}

/**
 * Set language and save to localStorage
 */
function setLanguage(langCode) {
    if (translations[langCode]) {
        currentLanguage = langCode;
        localStorage.setItem('whiteboardLanguage', langCode);
        // Dispatch event for reactive updates
        window.dispatchEvent(new CustomEvent('languageChanged', { detail: langCode }));
        return true;
    }
    return false;
}

/**
 * Get translation by key path (e.g., 'namePicker.welcome')
 */
function t(keyPath, fallback = '') {
    const keys = keyPath.split('.');
    let value = translations[currentLanguage];
    
    for (const key of keys) {
        if (value && typeof value === 'object' && key in value) {
            value = value[key];
        } else {
            // Fallback to English
            value = translations['en'];
            for (const k of keys) {
                if (value && typeof value === 'object' && k in value) {
                    value = value[k];
                } else {
                    return fallback || keyPath;
                }
            }
            break;
        }
    }
    
    return value || fallback || keyPath;
}

/**
 * Get all translations for current language
 */
function getTranslations() {
    return translations[currentLanguage] || translations['en'];
}

/**
 * Get available languages
 */
function getAvailableLanguages() {
    return availableLanguages;
}

// Export for use in modules and global scope
window.i18n = {
    init: initI18n,
    t,
    getLanguage,
    setLanguage,
    getTranslations,
    getAvailableLanguages,
    translations,
};

// Auto-initialize
initI18n();
