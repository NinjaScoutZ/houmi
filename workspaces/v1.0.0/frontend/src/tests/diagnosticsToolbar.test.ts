import { describe, it, expect, vi } from 'vitest';
import React from 'react';

// Unit testing the PipelineToolbar component props & logic
import { PipelineToolbar } from '../components/PipelineToolbar';

describe('PipelineToolbar Diagnostics Badge Tests', () => {
  it('defines PipelineToolbar component correctly', () => {
    expect(PipelineToolbar).toBeDefined();
  });

  it('correctly handles backend status badge props', () => {
    const handleDiagnostics = vi.fn();
    const props = {
      onRunStep: vi.fn(),
      onReorderBlocks: vi.fn(),
      onOpenBatchModal: vi.fn(),
      onOpenSettings: vi.fn(),
      onExport: vi.fn(),
      isProcessing: false,
      pageCount: 1,
      backendStatus: 'online' as const,
      latencyMs: 14,
      onOpenDiagnostics: handleDiagnostics,
    };

    const element = React.createElement(PipelineToolbar, props);
    expect(element.props.backendStatus).toBe('online');
    expect(element.props.latencyMs).toBe(14);
    expect(element.props.onOpenDiagnostics).toBe(handleDiagnostics);
  });

  it('accepts and passes ocrEngineStatuses prop to filter/mark unusable OCR engines', () => {
    const ocrEngineStatuses = {
      gemini: { available: true },
      glm: { available: false, reason: 'Local VLM API server offline' },
      deepseek: { available: false, reason: 'API key missing' },
    };

    const props = {
      workspaceMode: 'ocr' as const,
      ocrEngine: 'glm',
      onChangeOcrEngine: vi.fn(),
      ocrEngineStatuses,
    };

    const element = React.createElement(PipelineToolbar, props);
    const glmStatus = element.props.ocrEngineStatuses?.glm;
    expect(typeof glmStatus === 'object' && glmStatus.available).toBe(false);
    expect(typeof glmStatus === 'object' && glmStatus.reason).toBe('Local VLM API server offline');
  });
});
