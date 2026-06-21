import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import en from "./locales/en/common.json";
import ru from "./locales/ru/common.json";
import es from "./locales/es/common.json";

const savedLang = localStorage.getItem("lang") ?? "en";

i18n
  .use(initReactI18next)
  .init({
    resources: {
      en: { common: en },
      ru: { common: ru },
      es: { common: es },
    },
    lng: savedLang,
    fallbackLng: "en",
    defaultNS: "common",
    interpolation: { escapeValue: false },
  });

export default i18n;
