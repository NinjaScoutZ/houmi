import { useEffect } from 'react';

export interface ScanlationHotkeyActions {
  onPrevPage?: () => void;
  onNextPage?: () => void;
  onToggleMaskMode?: () => void;
  onToggleTypesetting?: () => void;
  onQuickInpaint?: () => void;
  onFitZoom?: () => void;
  onResetZoom?: () => void;
  isModalOpen?: boolean;
}

/**
 * Scanlation Power-User Ergonomic One-Handed Keyboard Shortcut Hook.
 * Automatically respects input focus, modal dialog open states, and standard modifier keys.
 */
export function useScanlationHotkeys({
  onPrevPage,
  onNextPage,
  onToggleMaskMode,
  onToggleTypesetting,
  onQuickInpaint,
  onFitZoom,
  onResetZoom,
  isModalOpen = false,
}: ScanlationHotkeyActions): void {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // 1. Guard against modal dialogs and active text editing
      if (isModalOpen) return;

      const activeEl = document.activeElement;
      const isInput =
        activeEl instanceof HTMLInputElement ||
        activeEl instanceof HTMLTextAreaElement ||
        (activeEl as HTMLElement)?.isContentEditable;

      if (isInput) return;

      // 2. Ignore shortcut if Ctrl, Meta, or Alt is held (let system/browser handle those)
      if (e.ctrlKey || e.metaKey || e.altKey) return;

      const key = e.key.toLowerCase();

      switch (key) {
        // One-handed navigation
        case 'q':
        case 'arrowleft':
          e.preventDefault();
          onPrevPage?.();
          break;
        case 'e':
        case 'arrowright':
          e.preventDefault();
          onNextPage?.();
          break;

        // Quick Mode Switching
        case 'm':
          e.preventDefault();
          onToggleMaskMode?.();
          break;
        case 't':
          e.preventDefault();
          onToggleTypesetting?.();
          break;
        case 'i':
          e.preventDefault();
          onQuickInpaint?.();
          break;

        // Viewport & Zoom
        case 'f':
          e.preventDefault();
          onFitZoom?.();
          break;
        case '0':
          e.preventDefault();
          onResetZoom?.();
          break;

        default:
          break;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [
    onPrevPage,
    onNextPage,
    onToggleMaskMode,
    onToggleTypesetting,
    onQuickInpaint,
    onFitZoom,
    onResetZoom,
    isModalOpen,
  ]);
}
