import "@testing-library/jest-dom";

// Polyfills required for Radix UI components (e.g. Select, Dialog, DropdownMenu)
// jsdom does not implement these methods used internally by Radix UI primitives.
Element.prototype.hasPointerCapture = () => false;
Element.prototype.setPointerCapture = () => undefined;
Element.prototype.releasePointerCapture = () => undefined;
Element.prototype.scrollIntoView = () => undefined;
// ResizeObserver polyfill for components using it
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "../locales/en/common.json";

i18n.use(initReactI18next).init({
  resources: { en: { common: en } },
  lng: "en",
  fallbackLng: "en",
  defaultNS: "common",
  interpolation: { escapeValue: false },
  initImmediate: false,
});
