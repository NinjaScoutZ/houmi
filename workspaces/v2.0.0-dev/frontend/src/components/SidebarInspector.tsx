import React from 'react';
import { useProjectStore, type TextBlock } from '../stores/projectStore';
import { FontSelector } from './FontSelector';
import { ColorField } from './ColorField';
import { Sparkles, AlignLeft, AlignCenter, AlignRight, X } from 'lucide-react';
import { DEFAULT_TEXT_TEMPLATES, type TextTemplate } from '../utils/textTemplates';

import { isFontAvailable, type FontFamilyMeta } from '../utils/fontLoader';

export interface SidebarInspectorProps {
  onClose?: () => void;
  systemFonts?: string[];
  availableFamilies?: Record<string, FontFamilyMeta>;
  onFontUploaded?: () => void;
  onRescanFonts?: (rescan?: boolean) => void | Promise<void>;
  stylePresets?: Record<string, TextTemplate>;
  onApplyTemplate?: (template: TextTemplate) => void;
  onOpenTemplateSettings?: () => void;
  onRecomputeSmartBalloons?: () => void;
}

export const SidebarInspector: React.FC<SidebarInspectorProps> = ({
  systemFonts = [],
  availableFamilies,
  onFontUploaded,
  onRescanFonts,
  stylePresets = DEFAULT_TEXT_TEMPLATES,
  onApplyTemplate,
  onOpenTemplateSettings,
  onClose,
}) => {
  const activePage = useProjectStore((state) => state.activePage);
  const selectedBlock = useProjectStore((state) => state.selectedBlock);
  const selectedBlocks = useProjectStore((state) => state.selectedBlocks);
  const updateBlock = useProjectStore((state) => state.updateBlock);
  const updateBlocksBulk = useProjectStore((state) => state.updateBlocksBulk);

  const targets = selectedBlocks.length > 0 ? selectedBlocks : selectedBlock ? [selectedBlock] : [];
  const isMulti = targets.length > 1;

  if (!activePage || targets.length === 0) {
    return (
      <div className="p-4 text-xs text-slate-400 text-center flex flex-col items-center justify-center h-full space-y-2 select-none font-sans">
        <span className="text-2xl">🔍</span>
        <p className="font-medium text-slate-300">No Block Selected</p>
        <p className="text-[11px] text-slate-500 max-w-[180px]">
          Click on any speech balloon in the workspace canvas to edit typography and translation.
        </p>
      </div>
    );
  }

  const primaryBlock = targets[0];

  const handleFieldChange = (patch: Partial<TextBlock>) => {
    if (isMulti) {
      updateBlocksBulk(targets.map((b) => ({ blockId: b.id, data: patch })));
    } else if (primaryBlock) {
      updateBlock(primaryBlock.id, patch);
    }
  };

  const handleMetadataChange = (metadataPatch: Record<string, any>) => {
    if (isMulti) {
      updateBlocksBulk(
        targets.map((b) => ({
          blockId: b.id,
          data: { extra_metadata: { ...(b.extra_metadata || {}), ...metadataPatch } },
        }))
      );
    } else if (primaryBlock) {
      updateBlock(primaryBlock.id, {
        extra_metadata: { ...(primaryBlock.extra_metadata || {}), ...metadataPatch },
      });
    }
  };

  const currentFont = primaryBlock.font_family || 'FC Sukhumvit';
  const currentSize = primaryBlock.font_size || 18;
  const isAutoFontSize =
    primaryBlock.extra_metadata?.manual_font_size == null &&
    primaryBlock.extra_metadata?.font_size_mode !== 'manual';

  const currentLeading = primaryBlock.extra_metadata?.line_height_ratio ?? 1.2;
  const currentTracking =
    primaryBlock.extra_metadata?.letter_spacing ?? primaryBlock.extra_metadata?.tracking ?? 0;
  const [isStyleAlignExpanded, setIsStyleAlignExpanded] = React.useState(false);

  return (
    <div className="flex flex-col h-full bg-zinc-950 text-slate-200 border-l border-zinc-900 font-sans select-none overflow-y-auto w-full p-3.5 space-y-4">
      {/* HEADER */}
      <div className="flex items-center justify-between border-b border-zinc-900 pb-2">
        <div className="flex items-center gap-2">
          <span className="text-amber-500 font-bold text-xs">
            {isMulti ? `Selected (${targets.length})` : `#${primaryBlock.block_index + 1}`}
          </span>
          <span className="text-[10px] text-slate-400 font-mono">
            {primaryBlock.balloon_type.toUpperCase()}
          </span>
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="p-1 hover:bg-zinc-900 text-slate-400 hover:text-slate-200 rounded transition-colors"
          >
            <X size={14} />
          </button>
        )}
      </div>

      {/* 1. STYLE TEMPLATES */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-[9px] font-bold uppercase tracking-wider text-slate-400">
            🎨 Text Templates
          </span>
          {onOpenTemplateSettings && (
            <button
              type="button"
              onClick={onOpenTemplateSettings}
              className="text-[9px] text-amber-500 hover:text-amber-400 underline font-medium"
            >
              Manage
            </button>
          )}
        </div>

        {/* Current Role Indicator */}
        <div className="bg-cyan-500/10 border border-cyan-500/30 rounded-lg p-2 flex items-center justify-between">
          <div className="truncate">
            <span className="text-[10px] text-cyan-400 font-bold block truncate">
              {primaryBlock.balloon_type || 'Default'}
            </span>
            <span className="text-[9px] text-cyan-500/80 font-mono block truncate">
              {currentFont} · {currentSize}px
            </span>
          </div>
          <span className="text-cyan-400 font-mono text-[9px] bg-cyan-500/20 px-1.5 py-0.5 rounded shrink-0">
            ACTIVE
          </span>
        </div>

        {/* Template Quick Selection Grid */}
        <div className="grid grid-cols-2 gap-1.5 max-h-40 overflow-y-auto pr-1">
          {Object.entries(stylePresets).map(([key, template]) => {
            const isMatch = primaryBlock.font_family === template.font_stack[0] && primaryBlock.font_size === template.font_size;
            const templateFont = template.font_stack[0];
            const isTemplateFontMissing = !isFontAvailable(templateFont, availableFamilies, systemFonts);
            return (
              <button
                key={key}
                type="button"
                onClick={() => {
                  if (onApplyTemplate) {
                    onApplyTemplate(template);
                  } else {
                    handleFieldChange({
                      font_family: template.font_stack[0],
                      font_size: template.font_size,
                      bold: template.bold,
                      italic: template.italic,
                      color_hex: template.color_hex,
                      text_align: template.text_align,
                    });
                  }
                }}
                className={`p-2 rounded-lg border text-left transition-all ${
                  isMatch
                    ? 'border-amber-500 bg-amber-500/10 text-amber-300 shadow-[0_0_10px_rgba(245,158,11,0.15)]'
                    : 'border-zinc-900 bg-zinc-900/50 text-slate-300 hover:border-zinc-800 hover:bg-zinc-900'
                }`}
                title={`${template.font_stack[0]} · ${template.font_size}px`}
              >
                <span className="block truncate font-bold text-[11px]">{template.semantic_tag || template.name || key}</span>
                <span className="block truncate pt-0.5 text-[9px] font-mono text-slate-400 flex items-center gap-1">
                  <span className="truncate">{templateFont} · {template.font_size}px</span>
                  {isTemplateFontMissing && (
                    <span className="text-amber-400 font-bold shrink-0" title={`ไม่พบไฟล์ฟอนต์ ${templateFont} ในเครื่อง (ใช้ Tahoma ชั่วคราว)`}>
                      ⚠️
                    </span>
                  )}
                </span>
              </button>
            );
            })}
          </div>
        </div>

        <div className="h-px bg-zinc-900" />

        {/* 2. CUSTOM TEXT STYLE SECTION */}
        <div className="space-y-3">
          <span className="text-[9px] font-bold uppercase tracking-wider text-slate-400 block">
            🔤 Custom Text Style
          </span>

          {/* Font Family (Full Width) */}
          <div>
            <label className="text-[9px] font-bold uppercase tracking-wider text-slate-400 block mb-1">
              Font Family
            </label>
            <FontSelector
              value={currentFont}
              availableFonts={systemFonts.length > 0 ? systemFonts : undefined}
              availableFamilies={availableFamilies}
              onFontUploaded={onFontUploaded}
              onRescanFonts={onRescanFonts}
              onChange={(font) => handleFieldChange({ font_family: font })}
              className="w-full bg-zinc-900 border border-zinc-800 focus:border-amber-500/60 text-slate-100"
            />
          </div>

        {/* Font Size (px) Row */}
        <div>
          <label className="text-[9px] font-bold uppercase tracking-wider text-slate-400 block mb-1">
            Font Size (px)
          </label>
          <div className="flex items-center gap-2">
            <input
              type="number"
              min="6"
              max="150"
              step="0.5"
              value={currentSize}
              onChange={(e) => handleFieldChange({ font_size: Number(e.target.value) || 12 })}
              className="flex-1 bg-zinc-900 border border-zinc-800 focus:border-amber-500/60 rounded-lg p-2 text-xs text-amber-400 font-mono focus:outline-none font-bold"
            />
            <button
              type="button"
              onClick={() => handleMetadataChange({ manual_font_size: null, font_size_mode: 'auto' })}
              className={`py-2 px-3 rounded-lg border text-[10px] font-bold transition-all flex items-center justify-center gap-1 cursor-pointer shrink-0 ${
                isAutoFontSize
                  ? 'border-emerald-500/50 bg-emerald-500/15 text-emerald-300 shadow-[0_0_8px_rgba(16,185,129,0.2)]'
                  : 'border-zinc-800 bg-zinc-900 text-slate-400 hover:text-amber-300 hover:border-amber-500/40'
              }`}
              title="Auto fit font size to balloon bounds"
            >
              <Sparkles size={11} className={isAutoFontSize ? 'text-emerald-400 animate-pulse' : ''} />
              <span>Fit</span>
            </button>
          </div>
        </div>

        {/* Collapsible Font Style & Alignment Disclosure */}
        <div className="pt-0.5">
          <button
            type="button"
            onClick={() => setIsStyleAlignExpanded(!isStyleAlignExpanded)}
            className="w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg bg-zinc-900/70 hover:bg-zinc-850 border border-zinc-800 text-[10px] text-slate-300 transition-colors cursor-pointer"
          >
            <span className="flex items-center gap-1.5 font-bold">
              <span>📐</span>
              <span>Font Style & Alignment</span>
              {(primaryBlock.bold || primaryBlock.italic || primaryBlock.text_align !== 'center') && (
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
              )}
            </span>
            <span className="text-slate-400 text-[9px] font-mono">{isStyleAlignExpanded ? '▲ ซ่อน' : '▼ ขยาย'}</span>
          </button>

          {isStyleAlignExpanded && (
            <div className="mt-2 p-2.5 bg-zinc-900/40 border border-zinc-800 rounded-lg grid grid-cols-2 gap-2 animate-fade-in">
              <div>
                <label className="text-[9px] font-bold uppercase tracking-wider text-slate-400 block mb-1">
                  Font Style
                </label>
                <div className="flex items-center gap-1 bg-zinc-950 p-1 border border-zinc-800 rounded-lg">
                  <button
                    type="button"
                    onClick={() => handleFieldChange({ bold: !primaryBlock.bold })}
                    className={`flex-1 py-1 rounded-md font-bold text-xs transition-colors cursor-pointer ${
                      primaryBlock.bold
                        ? 'bg-amber-500 text-black font-bold'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    B
                  </button>
                  <button
                    type="button"
                    onClick={() => handleFieldChange({ italic: !primaryBlock.italic })}
                    className={`flex-1 py-1 rounded-md italic text-xs transition-colors cursor-pointer ${
                      primaryBlock.italic
                        ? 'bg-amber-500 text-black font-bold'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    I
                  </button>
                </div>
              </div>

              <div>
                <label className="text-[9px] font-bold uppercase tracking-wider text-slate-400 block mb-1">
                  Alignment
                </label>
                <div className="grid grid-cols-3 border border-zinc-800 bg-zinc-950 rounded-lg p-1 gap-0.5">
                  {(['left', 'center', 'right'] as const).map((align) => {
                    const isActive = primaryBlock.text_align === align;
                    return (
                      <button
                        key={align}
                        type="button"
                        onClick={() => handleFieldChange({ text_align: align })}
                        className={`py-1 flex items-center justify-center rounded transition-all cursor-pointer ${
                          isActive
                            ? 'bg-amber-500 text-black font-bold shadow'
                            : 'text-slate-400 hover:text-slate-200'
                        }`}
                        title={`${align} align`}
                      >
                        {align === 'left' && <AlignLeft size={12} />}
                        {align === 'center' && <AlignCenter size={12} />}
                        {align === 'right' && <AlignRight size={12} />}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Text Color */}
        <div>
          <ColorField
            label="Text Color"
            value={primaryBlock.color_hex || '#ffffff'}
            onChange={(color) => handleFieldChange({ color_hex: color })}
            compact
          />
        </div>

        {/* Leading & Tracking */}
        <div className="grid grid-cols-2 gap-2 pt-1 border-t border-zinc-800/80">
          <div>
            <label className="text-[9px] font-bold uppercase tracking-wider text-slate-400 block mb-1">
              Leading (Line)
            </label>
            <input
              type="number"
              min="0.8"
              max="3"
              step="0.05"
              value={currentLeading}
              onChange={(e) => handleMetadataChange({ line_height_ratio: Number(e.target.value) || 1.2 })}
              className="w-full bg-zinc-900 border border-zinc-800 focus:border-amber-500/60 rounded-lg p-1.5 text-xs text-slate-100 font-mono focus:outline-none"
            />
          </div>

          <div>
            <label className="text-[9px] font-bold uppercase tracking-wider text-slate-400 block mb-1">
              Tracking (Spacing)
            </label>
            <input
              type="number"
              min="-200"
              max="500"
              step="10"
              value={currentTracking}
              onChange={(e) => {
                const tracking = Number(e.target.value) || 0;
                handleMetadataChange({ tracking, letter_spacing: tracking });
              }}
              className="w-full bg-zinc-900 border border-zinc-800 focus:border-amber-500/60 rounded-lg p-1.5 text-xs text-slate-100 font-mono focus:outline-none"
            />
          </div>
        </div>
      </div>

      {/* Manage Templates Button */}
      {onOpenTemplateSettings && (
        <button
          type="button"
          onClick={onOpenTemplateSettings}
          className="w-full mt-3 border border-zinc-800 bg-zinc-900 hover:border-amber-500/50 hover:text-amber-300 p-2 text-center rounded-lg text-[10px] font-bold uppercase tracking-wider transition-colors cursor-pointer"
        >
          MANAGE TEMPLATES
        </button>
      )}
    </div>
  );
};

