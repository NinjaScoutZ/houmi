import { afterEach, describe, expect, test, vi } from 'vitest';
import {
  autoFitTextboxFontSize,
  shouldSplitCanvasTextByGrapheme,
  suppressTextboxDecorationsForCapture,
} from '../components/Canvas';
import { useProjectStore, type TextBlock } from '../stores/projectStore';

const block: TextBlock = {
  id: 'fit-block',
  page_id: 'fit-page',
  block_index: 0,
  x: 0,
  y: 0,
  width: 120,
  height: 40,
  rotation_deg: 0,
  source_text: '',
  translation: 'A long line that must shrink inside a fixed balloon',
  font_family: 'Tahoma',
  font_size: 36,
  color_hex: '#000000',
  bold: false,
  italic: false,
  text_direction: 'horizontal',
  text_align: 'center',
  balloon_type: 'narrative',
  confidence: 1,
  extra_metadata: {
    font_size_mode: 'auto',
    min_font_size: 6,
    max_font_size: 96,
    typesetting_spec: { font_size: 36, line_height: 43.2 },
  },
};

describe('Canvas auto fit', () => {
  const originalUpdateBlock = useProjectStore.getState().updateBlock;

  afterEach(() => {
    useProjectStore.setState({ updateBlock: originalUpdateBlock });
  });

  test('syncs the fitted size locally without persisting when backend updates are skipped', () => {
    const page = {
      id: 'fit-page', project_id: 'fit-project', page_number: 1, name: 'Fit',
      width: 1000, height: 1000, source_image_path: '', status: 'ready', text_blocks: [block],
    };
    const updateBlock = vi.fn();
    useProjectStore.setState({
      activePage: page,
      activeProject: {
        id: 'fit-project', name: 'Fit', source_lang: 'en', target_lang: 'th',
        created_at: '', updated_at: '', settings: {}, pages: [page],
      },
      selectedBlock: block,
      selectedBlocks: [block],
      updateBlock: updateBlock as any,
    });

    const textbox: any = {
      text: block.translation,
      width: 120,
      height: 40,
      fontSize: 36,
      lineHeight: 1.2,
      data: { blockId: block.id, balloonType: 'narrative', minFontSize: 6, maxFontSize: 96 },
      set(values: Record<string, unknown>) { Object.assign(this, values); },
      _splitText() {
        const charsPerLine = Math.max(1, Math.floor(this.width / (this.fontSize * 0.55)));
        const count = Math.max(1, Math.ceil(this.text.length / charsPerLine));
        this._textLines = Array.from({ length: count }, () => ['x']);
      },
      getHeightOfLineImpl() { return this.fontSize; },
      getHeightOfLine() { return this.fontSize * this.lineHeight; },
      getLineWidth() { return Math.min(this.width * 0.9, this.text.length * this.fontSize * 0.55); },
    };
    textbox._splitText();

    autoFitTextboxFontSize(textbox, null, 1, true);

    const fitted = useProjectStore.getState().selectedBlock!;
    expect(fitted.font_size).toBeLessThan(36);
    expect(fitted.extra_metadata.typesetting_spec.font_size).toBe(fitted.font_size);
    expect(textbox.height).toBe(40);
    expect(updateBlock).not.toHaveBeenCalled();
  });

  test('treats a configured 50pt minimum as soft in Auto mode', () => {
    const highMinimumBlock = {
      ...block,
      font_size: 50,
      extra_metadata: {
        ...block.extra_metadata,
        min_font_size: 50,
        typesetting_spec: { font_size: 50, line_height: 60 },
      },
    };
    const page = {
      id: 'fit-page', project_id: 'fit-project', page_number: 1, name: 'Fit',
      width: 1000, height: 1000, source_image_path: '', status: 'ready', text_blocks: [highMinimumBlock],
    };
    useProjectStore.setState({
      activePage: page,
      activeProject: {
        id: 'fit-project', name: 'Fit', source_lang: 'en', target_lang: 'th',
        created_at: '', updated_at: '', settings: {}, pages: [page],
      },
      selectedBlock: highMinimumBlock,
      selectedBlocks: [highMinimumBlock],
    });
    const textbox: any = {
      text: highMinimumBlock.translation.repeat(4),
      width: 120,
      height: 40,
      fontSize: 50,
      lineHeight: 1.2,
      data: { blockId: block.id, balloonType: 'narrative', minFontSize: 50, maxFontSize: 96 },
      set(values: Record<string, unknown>) { Object.assign(this, values); },
      _splitText() {
        const charsPerLine = Math.max(1, Math.floor(this.width / (this.fontSize * 0.55)));
        const count = Math.max(1, Math.ceil(this.text.length / charsPerLine));
        this._textLines = Array.from({ length: count }, () => ['x']);
      },
      getHeightOfLineImpl() { return this.fontSize; },
      getHeightOfLine() { return this.fontSize * this.lineHeight; },
      getLineWidth() { return Math.min(this.width * 0.9, this.text.length * this.fontSize * 0.55); },
    };
    textbox._splitText();

    autoFitTextboxFontSize(textbox, null, 1, true);

    expect(useProjectStore.getState().selectedBlock?.font_size).toBeLessThan(50);
    expect(useProjectStore.getState().selectedBlock?.font_size).toBeGreaterThanOrEqual(6);
    expect(textbox.height).toBe(40);
  });

  test('grows the font when the fixed balloon is enlarged', () => {
    const roomyBlock = {
      ...block,
      translation: 'Short text',
      font_size: 24,
      extra_metadata: {
        ...block.extra_metadata,
        typesetting_spec: { font_size: 24, line_height: 28.8 },
      },
    };
    const page = {
      id: 'fit-page', project_id: 'fit-project', page_number: 1, name: 'Fit',
      width: 1000, height: 1000, source_image_path: '', status: 'ready', text_blocks: [roomyBlock],
    };
    useProjectStore.setState({ activePage: page, selectedBlock: roomyBlock, selectedBlocks: [roomyBlock] });
    const textbox: any = {
      text: roomyBlock.translation,
      width: 300,
      height: 120,
      fontSize: 24,
      lineHeight: 1.2,
      data: { blockId: roomyBlock.id, balloonType: 'narrative', minFontSize: 6, maxFontSize: 96 },
      set(values: Record<string, unknown>) { Object.assign(this, values); },
      _splitText() { this._textLines = [['x']]; },
      getHeightOfLineImpl() { return this.fontSize; },
      getHeightOfLine() { return this.fontSize * this.lineHeight; },
      getLineWidth() { return this.text.length * this.fontSize * 0.55; },
    };
    textbox._splitText();

    autoFitTextboxFontSize(textbox, null, 1, true);

    expect(textbox.fontSize).toBeGreaterThan(24);
    expect(useProjectStore.getState().selectedBlock?.font_size).toBe(textbox.fontSize);
  });

  test('commits Thai wrapping immediately instead of waiting for layer selection', () => {
    const initDimensions = vi.fn();
    const setCoords = vi.fn();
    const requestRenderAll = vi.fn();
    const textbox: any = {
      text: 'แค่ได้ยินเสียงหายใจก็รู้สึกลามกแล้ว',
      width: 120,
      height: 40,
      fontSize: 36,
      lineHeight: 1.2,
      data: { balloonType: 'bubble', minFontSize: 6, maxFontSize: 96 },
      set(values: Record<string, unknown>) { Object.assign(this, values); },
      _splitText() { this._textLines = [['x'], ['x']]; },
      getHeightOfLineImpl() { return this.fontSize; },
      getHeightOfLine() { return this.fontSize * this.lineHeight; },
      getLineWidth() { return this.width * 0.8; },
      initDimensions,
      setCoords,
    };

    autoFitTextboxFontSize(textbox, { requestRenderAll }, 1, true);

    expect(shouldSplitCanvasTextByGrapheme(textbox.text)).toBe(false);
    expect(textbox.splitByGrapheme).toBe(false);
    expect(initDimensions).toHaveBeenCalledOnce();
    expect(setCoords).toHaveBeenCalledOnce();
    expect(requestRenderAll).toHaveBeenCalledOnce();
    expect(textbox.dirty).toBe(true);
  });

  test('enables splitByGrapheme for CJK text but disables it for Thai text', () => {
    expect(shouldSplitCanvasTextByGrapheme('这是中文文本')).toBe(true);
    expect(shouldSplitCanvasTextByGrapheme('日本語のテキスト')).toBe(true);
    expect(shouldSplitCanvasTextByGrapheme('ข้อความภาษาไทย')).toBe(false);
    expect(shouldSplitCanvasTextByGrapheme('English text')).toBe(false);
  });
});

describe('Canvas export capture', () => {
  test('removes textbox editor decorations during capture and restores them afterward', () => {
    const decoratedRender = vi.fn();
    const textbox: any = {
      _render: decoratedRender,
      hasBorders: true,
      hasControls: true,
      set(values: Record<string, unknown>) { Object.assign(this, values); },
    };

    const restore = suppressTextboxDecorationsForCapture([textbox]);

    expect(textbox._render).not.toBe(decoratedRender);
    expect(textbox.hasBorders).toBe(false);
    expect(textbox.hasControls).toBe(false);

    restore();

    expect(textbox._render).toBe(decoratedRender);
    expect(textbox.hasBorders).toBe(true);
    expect(textbox.hasControls).toBe(true);
  });
});
