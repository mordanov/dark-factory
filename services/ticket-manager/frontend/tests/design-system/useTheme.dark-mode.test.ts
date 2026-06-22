/**
 * Tests for T009: useTheme must toggle `.dark` CSS class on <html>
 * alongside the existing `data-theme` attribute.
 * Dark themes: "dark", "oceanic", "high-contrast"
 * Light themes: "light", "solarized", "warm"
 */
import { describe, it, expect, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useTheme } from "../../src/hooks/useTheme";

const html = document.documentElement;

beforeEach(() => {
  localStorage.clear();
  html.removeAttribute("data-theme");
  html.classList.remove("dark");
});

describe("useTheme — .dark class toggle (T009)", () => {
  it('adds .dark class when switching to "dark" theme', () => {
    const { result } = renderHook(() => useTheme());
    act(() => result.current.setTheme("dark"));
    expect(html.classList.contains("dark")).toBe(true);
    expect(html.dataset.theme).toBe("dark");
  });

  it('adds .dark class when switching to "oceanic" theme', () => {
    const { result } = renderHook(() => useTheme());
    act(() => result.current.setTheme("oceanic"));
    expect(html.classList.contains("dark")).toBe(true);
  });

  it('adds .dark class when switching to "high-contrast" theme', () => {
    const { result } = renderHook(() => useTheme());
    act(() => result.current.setTheme("high-contrast"));
    expect(html.classList.contains("dark")).toBe(true);
  });

  it('removes .dark class when switching to "light" theme', () => {
    html.classList.add("dark");
    localStorage.setItem("theme", "dark");
    const { result } = renderHook(() => useTheme());
    act(() => result.current.setTheme("light"));
    expect(html.classList.contains("dark")).toBe(false);
    expect(html.dataset.theme).toBe("light");
  });

  it('removes .dark class when switching to "solarized" theme', () => {
    html.classList.add("dark");
    const { result } = renderHook(() => useTheme());
    act(() => result.current.setTheme("solarized"));
    expect(html.classList.contains("dark")).toBe(false);
  });

  it('removes .dark class when switching to "warm" theme', () => {
    html.classList.add("dark");
    const { result } = renderHook(() => useTheme());
    act(() => result.current.setTheme("warm"));
    expect(html.classList.contains("dark")).toBe(false);
  });

  it("applies .dark class on initial mount when dark theme is in localStorage", async () => {
    localStorage.setItem("theme", "dark");
    const { result } = renderHook(() => useTheme());
    // useEffect fires synchronously in act during renderHook
    expect(result.current.theme).toBe("dark");
    expect(html.classList.contains("dark")).toBe(true);
  });

  it("does not add .dark class on initial mount when light theme is in localStorage", () => {
    localStorage.setItem("theme", "light");
    renderHook(() => useTheme());
    expect(html.classList.contains("dark")).toBe(false);
  });

  it("does not add .dark class on initial mount when no theme is stored", () => {
    renderHook(() => useTheme());
    expect(html.classList.contains("dark")).toBe(false);
  });

  it("persists theme key to localStorage when setTheme is called", () => {
    const { result } = renderHook(() => useTheme());
    act(() => result.current.setTheme("oceanic"));
    expect(localStorage.getItem("theme")).toBe("oceanic");
  });
});
