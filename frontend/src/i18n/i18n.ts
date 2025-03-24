import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

import deTranslation from './locales/de.json';
import enTranslation from './locales/en.json';

// Konfiguriere i18next
i18n
  // Automatische Spracherkennung
  .use(LanguageDetector)
  // Integration mit React
  .use(initReactI18next)
  // Initialisierung
  .init({
    resources: {
      de: {
        translation: deTranslation
      },
      en: {
        translation: enTranslation
      }
    },
    fallbackLng: 'de',  // Standardsprache ist Deutsch
    interpolation: {
      escapeValue: false  // React kümmert sich selbst um XSS-Schutz
    },
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
    }
  });

export default i18n; 