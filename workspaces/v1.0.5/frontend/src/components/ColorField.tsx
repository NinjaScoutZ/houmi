import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  hexToRgb,
  hsbToRgb,
  normalizeHex,
  normalizeStoredHex,
  rgbToHex,
  rgbToHsb,
  type HSBColor,
  type RGBColor,
} from '../utils/color';

interface ColorFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  compact?: boolean;
  mixed?: boolean;
}

interface PickerPosition {
  left: number;
  top: number;
}

const PICKER_WIDTH = 328;
const PICKER_HEIGHT = 476;

const clamp = (value: number, minimum: number, maximum: number) =>
  Math.min(maximum, Math.max(minimum, Number.isFinite(value) ? value : minimum));

const checkerboardStyle = {
  backgroundColor: '#27272a',
  backgroundImage: 'conic-gradient(#52525b 25%, #27272a 0 50%, #52525b 0 75%, #27272a 0)',
  backgroundPosition: '0 0',
  backgroundSize: '10px 10px',
};

function pickerPosition(trigger: DOMRect, popoverElement?: HTMLDivElement | null): PickerPosition {
  const viewportWidth = window.innerWidth;
  const viewportHeight = window.innerHeight;
  const popoverHeight = popoverElement?.offsetHeight || PICKER_HEIGHT;
  const popoverWidth = popoverElement?.offsetWidth || PICKER_WIDTH;

  const width = Math.min(popoverWidth, viewportWidth - 16);
  const height = Math.min(popoverHeight, viewportHeight - 16);

  let left = trigger.left;
  if (left + width > viewportWidth - 12) {
    left = Math.max(12, trigger.right - width);
  }
  left = clamp(left, 12, Math.max(12, viewportWidth - width - 12));

  const spaceBelow = viewportHeight - trigger.bottom - 12;
  const spaceAbove = trigger.top - 12;

  let top: number;
  if (spaceBelow >= height) {
    top = trigger.bottom + 6;
  } else if (spaceAbove >= height) {
    top = trigger.top - height - 6;
  } else {
    top = spaceAbove > spaceBelow ? trigger.top - height - 6 : trigger.bottom + 6;
  }

  // Absolute hard bounds safety check: Guarantee top and bottom never spill off viewport
  top = Math.max(8, Math.min(top, Math.max(8, viewportHeight - height - 8)));

  return { left, top };
}

function channelValue(value: number): number {
  return Math.round(value);
}

interface ChannelInputProps {
  label: string;
  value: number;
  maximum: number;
  onChange: (value: number) => void;
}

function ChannelInput({ label, value, maximum, onChange }: ChannelInputProps) {
  return (
    <label className="grid grid-cols-[18px_minmax(0,1fr)] items-center gap-1.5 text-[10px] text-zinc-400">
      <span className="font-semibold text-zinc-300">{label}</span>
      <input
        type="number"
        min={0}
        max={maximum}
        step={1}
        value={channelValue(value)}
        onChange={(event) => onChange(clamp(Number(event.target.value), 0, maximum))}
        onFocus={(event) => event.currentTarget.select()}
        className="h-7 min-w-0 border border-zinc-700 bg-zinc-900 px-2 text-right font-mono text-[10px] text-zinc-100 outline-none focus:border-amber-400"
      />
    </label>
  );
}

export function ColorField({ label, value, onChange, compact = false, mixed = false }: ColorFieldProps) {
  const safeValue = normalizeStoredHex(value) || '#000000';
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const saturationRef = useRef<HTMLDivElement>(null);
  const saturationDraggingRef = useRef(false);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<PickerPosition>({ left: 8, top: 8 });
  const [startingHex, setStartingHex] = useState(safeValue);
  const [startingMixed, setStartingMixed] = useState(mixed);
  const [stagedHsb, setStagedHsb] = useState<HSBColor>(() => rgbToHsb(hexToRgb(safeValue) || { r: 0, g: 0, b: 0 }));
  const [pickerHexDraft, setPickerHexDraft] = useState(safeValue.slice(1).toUpperCase());

  const stagedRgb = hsbToRgb(stagedHsb);
  const stagedHex = rgbToHex(stagedRgb);
  const pickerHexValid = normalizeHex(pickerHexDraft) !== null;
  const huePosition = stagedHsb.h === 360 ? 100 : (((stagedHsb.h % 360) + 360) % 360) / 3.6;

  const updateStage = (next: HSBColor) => {
    const normalized = {
      h: clamp(next.h, 0, 360),
      s: clamp(next.s, 0, 100),
      b: clamp(next.b, 0, 100),
    };
    setStagedHsb(normalized);
    setPickerHexDraft(rgbToHex(hsbToRgb(normalized)).slice(1).toUpperCase());
  };

  const openPicker = () => {
    const initialRgb = hexToRgb(safeValue) || { r: 0, g: 0, b: 0 };
    setStartingHex(safeValue);
    setStartingMixed(mixed);
    setStagedHsb(rgbToHsb(initialRgb));
    setPickerHexDraft(safeValue.slice(1).toUpperCase());
    if (triggerRef.current) setPosition(pickerPosition(triggerRef.current.getBoundingClientRect(), popoverRef.current));
    setOpen(true);
  };

  const closePicker = (restoreFocus = false) => {
    setOpen(false);
    if (restoreFocus) window.requestAnimationFrame(() => triggerRef.current?.focus());
  };

  useEffect(() => {
    if (!open) return;

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!popoverRef.current?.contains(target) && !triggerRef.current?.contains(target)) {
        if (pickerHexValid && stagedHex !== startingHex) {
          onChange(stagedHex);
        }
        closePicker();
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      closePicker(true);
    };
    const handleViewportChange = () => {
      if (triggerRef.current) setPosition(pickerPosition(triggerRef.current.getBoundingClientRect(), popoverRef.current));
    };

    handleViewportChange();
    document.addEventListener('pointerdown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    window.addEventListener('resize', handleViewportChange);
    window.addEventListener('scroll', handleViewportChange, true);
    const focusFrame = window.requestAnimationFrame(() => {
      handleViewportChange();
      saturationRef.current?.focus();
    });
    return () => {
      window.cancelAnimationFrame(focusFrame);
      document.removeEventListener('pointerdown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('resize', handleViewportChange);
      window.removeEventListener('scroll', handleViewportChange, true);
    };
  }, [open]);

  const updateSaturation = (clientX: number, clientY: number) => {
    const bounds = saturationRef.current?.getBoundingClientRect();
    if (!bounds) return;
    updateStage({
      ...stagedHsb,
      s: ((clientX - bounds.left) / bounds.width) * 100,
      b: (1 - (clientY - bounds.top) / bounds.height) * 100,
    });
  };

  const updateRgbChannel = (channel: keyof RGBColor, channelValue: number) => {
    const nextRgb = { ...stagedRgb, [channel]: channelValue };
    const nextHsb = rgbToHsb(nextRgb);
    if (nextHsb.s === 0) nextHsb.h = stagedHsb.h;
    updateStage(nextHsb);
  };

  const popover = open && typeof document !== 'undefined' ? createPortal(
    <div
      ref={popoverRef}
      role="dialog"
      tabIndex={-1}
      aria-label={`${label} color picker`}
      className="fixed z-[100000] max-h-[calc(100vh-24px)] w-[min(328px,calc(100vw-16px))] overflow-y-auto border border-zinc-700/80 rounded-xl bg-zinc-950/95 text-zinc-200 shadow-2xl backdrop-blur-md"
      style={{ left: position.left, top: position.top }}
      onPointerDown={(event) => event.stopPropagation()}
    >
      <div className="flex h-9 items-center justify-between border-b border-zinc-700 bg-zinc-900 px-3">
        <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-200">Color Picker</span>
        <button
          type="button"
          onClick={() => closePicker(true)}
          className="grid size-7 place-items-center text-lg leading-none text-zinc-500 hover:bg-zinc-800 hover:text-white focus-visible:outline focus-visible:outline-1 focus-visible:outline-amber-400"
          aria-label="Close color picker"
          title="Close"
        >
          &times;
        </button>
      </div>

      <div className="space-y-3 p-3">
        <div
          ref={saturationRef}
          role="slider"
          aria-label="Saturation and brightness"
          aria-valuetext={`${channelValue(stagedHsb.s)}% saturation, ${channelValue(stagedHsb.b)}% brightness`}
          tabIndex={0}
          className="relative h-36 cursor-crosshair touch-none overflow-hidden border border-zinc-600 outline-none focus-visible:ring-1 focus-visible:ring-amber-400"
          style={{ backgroundColor: `hsl(${stagedHsb.h} 100% 50%)` }}
          onPointerDown={(event) => {
            saturationDraggingRef.current = true;
            event.currentTarget.setPointerCapture(event.pointerId);
            updateSaturation(event.clientX, event.clientY);
          }}
          onPointerMove={(event) => {
            if (saturationDraggingRef.current) updateSaturation(event.clientX, event.clientY);
          }}
          onPointerUp={(event) => {
            saturationDraggingRef.current = false;
            event.currentTarget.releasePointerCapture(event.pointerId);
          }}
          onPointerCancel={() => { saturationDraggingRef.current = false; }}
          onKeyDown={(event) => {
            const step = event.shiftKey ? 10 : 1;
            if (event.key === 'ArrowLeft') updateStage({ ...stagedHsb, s: stagedHsb.s - step });
            else if (event.key === 'ArrowRight') updateStage({ ...stagedHsb, s: stagedHsb.s + step });
            else if (event.key === 'ArrowUp') updateStage({ ...stagedHsb, b: stagedHsb.b + step });
            else if (event.key === 'ArrowDown') updateStage({ ...stagedHsb, b: stagedHsb.b - step });
            else return;
            event.preventDefault();
          }}
        >
          <div className="absolute inset-0 bg-gradient-to-r from-white to-transparent" />
          <div className="absolute inset-0 bg-gradient-to-b from-transparent to-black" />
          <span
            className="pointer-events-none absolute size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white shadow-[0_0_0_1px_rgba(0,0,0,0.85)]"
            style={{ left: `${stagedHsb.s}%`, top: `${100 - stagedHsb.b}%` }}
          />
        </div>

        <div className="space-y-1.5">
          <div className="flex items-center justify-between text-[9px] font-bold uppercase tracking-wider text-zinc-500">
            <span>Hue</span>
            <span className="font-mono text-zinc-300">{channelValue(stagedHsb.h)}&deg;</span>
          </div>
          <div className="relative h-4 border border-zinc-600 bg-[linear-gradient(to_right,#f00,#ff0,#0f0,#0ff,#00f,#f0f,#f00)] focus-within:ring-1 focus-within:ring-amber-400">
            <span
              className="pointer-events-none absolute -top-1 h-5 w-1 -translate-x-1/2 border border-black bg-white shadow-sm"
              style={{ left: `${huePosition}%` }}
            />
            <input
              type="range"
              min={0}
              max={360}
              step={1}
              value={channelValue(stagedHsb.h)}
              onChange={(event) => updateStage({ ...stagedHsb, h: Number(event.target.value) })}
              className="absolute inset-0 h-full w-full cursor-ew-resize opacity-0"
              aria-label="Hue"
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2 border-y border-zinc-800 py-2">
          <div className="grid grid-cols-[40px_minmax(0,1fr)] items-center gap-2">
            <span
              className="h-8 border border-zinc-600"
              style={startingMixed ? checkerboardStyle : { backgroundColor: startingHex }}
            />
            <span className="min-w-0">
              <span className="block text-[8px] font-bold uppercase tracking-wider text-zinc-500">Current</span>
              <span className="block truncate font-mono text-[9px] text-zinc-300">{startingMixed ? 'MIXED' : startingHex.toUpperCase()}</span>
            </span>
          </div>
          <div className="grid grid-cols-[40px_minmax(0,1fr)] items-center gap-2">
            <span className="h-8 border border-zinc-600" style={{ backgroundColor: stagedHex }} />
            <span className="min-w-0">
              <span className="block text-[8px] font-bold uppercase tracking-wider text-zinc-500">New</span>
              <span className="block truncate font-mono text-[9px] text-zinc-300">{stagedHex.toUpperCase()}</span>
            </span>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <fieldset className="space-y-1.5">
            <legend className="mb-1 text-[8px] font-bold uppercase tracking-wider text-zinc-500">HSB</legend>
            <ChannelInput label="H" value={stagedHsb.h} maximum={360} onChange={(h) => updateStage({ ...stagedHsb, h })} />
            <ChannelInput label="S" value={stagedHsb.s} maximum={100} onChange={(s) => updateStage({ ...stagedHsb, s })} />
            <ChannelInput label="B" value={stagedHsb.b} maximum={100} onChange={(b) => updateStage({ ...stagedHsb, b })} />
          </fieldset>
          <fieldset className="space-y-1.5">
            <legend className="mb-1 text-[8px] font-bold uppercase tracking-wider text-zinc-500">RGB</legend>
            <ChannelInput label="R" value={stagedRgb.r} maximum={255} onChange={(r) => updateRgbChannel('r', r)} />
            <ChannelInput label="G" value={stagedRgb.g} maximum={255} onChange={(g) => updateRgbChannel('g', g)} />
            <ChannelInput label="B" value={stagedRgb.b} maximum={255} onChange={(b) => updateRgbChannel('b', b)} />
          </fieldset>
        </div>

        <label className="block text-[8px] font-bold uppercase tracking-wider text-zinc-500">
          HEX
          <span className={`mt-1 flex h-8 items-center border bg-zinc-900 ${pickerHexValid ? 'border-zinc-700 focus-within:border-amber-400' : 'border-red-500'}`}>
            <span className="pl-2 font-mono text-[10px] text-zinc-500">#</span>
            <input
              value={pickerHexDraft}
              onChange={(event) => {
                const next = event.target.value.replace(/[^0-9a-f]/gi, '').slice(0, 6).toUpperCase();
                setPickerHexDraft(next);
                const normalized = normalizeHex(next);
                const rgb = normalized ? hexToRgb(normalized) : null;
                if (rgb) setStagedHsb(rgbToHsb(rgb));
              }}
              onBlur={() => {
                if (!pickerHexValid) setPickerHexDraft(stagedHex.slice(1).toUpperCase());
              }}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && pickerHexValid) {
                  event.preventDefault();
                  onChange(stagedHex);
                  closePicker(true);
                }
              }}
              className="min-w-0 flex-1 bg-transparent px-1.5 font-mono text-[10px] uppercase text-zinc-100 outline-none"
              spellCheck={false}
              aria-invalid={!pickerHexValid}
            />
          </span>
        </label>

        <div className="flex justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={() => closePicker(true)}
            className="h-8 min-w-20 border border-zinc-600 bg-zinc-900 px-3 text-[9px] font-bold uppercase tracking-wider text-zinc-300 hover:bg-zinc-800 focus-visible:outline focus-visible:outline-1 focus-visible:outline-amber-400"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!pickerHexValid}
            onClick={() => {
              onChange(stagedHex);
              closePicker(true);
            }}
            className="h-8 min-w-20 border border-amber-400 bg-amber-400 px-3 text-[9px] font-bold uppercase tracking-wider text-zinc-950 hover:bg-amber-300 focus-visible:outline focus-visible:outline-1 focus-visible:outline-white disabled:cursor-not-allowed disabled:border-zinc-700 disabled:bg-zinc-800 disabled:text-zinc-500"
          >
            OK
          </button>
        </div>
      </div>
    </div>,
    document.body,
  ) : null;

  return (
    <div className="block min-w-0 text-[8px] font-bold uppercase tracking-wider text-slate-500">
      <span>{label}</span>
      <span className={`mt-1 flex items-center border border-zinc-700 bg-zinc-950 focus-within:border-amber-400 ${compact ? 'h-8' : 'h-9'}`}>
        <button
          ref={triggerRef}
          type="button"
          onClick={() => open ? closePicker() : openPicker()}
          className="relative h-full w-10 shrink-0 border-r border-zinc-700 outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-amber-400"
          style={mixed ? checkerboardStyle : { backgroundColor: safeValue }}
          aria-label={`Choose ${label.toLowerCase()}`}
          aria-haspopup="dialog"
          aria-expanded={open}
          title={`Choose ${label.toLowerCase()}`}
        />
        <span className="pl-2 text-[10px] text-slate-600">#</span>
        <input
          key={`${mixed ? 'mixed' : 'color'}-${safeValue}`}
          defaultValue={mixed ? '' : safeValue.slice(1).toUpperCase()}
          placeholder={mixed ? 'MIXED' : undefined}
          onChange={(event) => {
            const next = event.target.value.replace(/[^0-9a-f]/gi, '').slice(0, 6).toUpperCase();
            event.target.value = next;
            const normalized = normalizeHex(next);
            if (normalized) onChange(normalized);
          }}
          onBlur={(event) => {
            if (!normalizeHex(event.currentTarget.value)) {
              event.currentTarget.value = mixed ? '' : safeValue.slice(1).toUpperCase();
            }
          }}
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              event.currentTarget.value = mixed ? '' : safeValue.slice(1).toUpperCase();
              event.currentTarget.blur();
            }
          }}
          className="min-w-0 flex-1 bg-transparent px-1.5 font-mono text-[10px] uppercase text-slate-200 outline-none placeholder:text-zinc-500"
          spellCheck={false}
          aria-label={`${label} hex value`}
        />
      </span>
      {popover}
    </div>
  );
}
