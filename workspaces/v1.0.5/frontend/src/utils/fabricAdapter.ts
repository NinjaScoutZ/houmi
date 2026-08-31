import * as fabric from 'fabric';

export interface Fabric7TextLinesInfo {
  lines: string[];
  graphemeLines: string[][];
  _unwrappedLines: string[][];
  graphemeText: string[];
}

interface CustomTextbox {
  __originalSplitTextIntoLines?: (text: string) => Fabric7TextLinesInfo;
  _splitTextIntoLines?(text: string): Fabric7TextLinesInfo;
  isEditing: boolean;
}

interface FabricUtilString {
  string?: {
    graphemeSplit?: (s: string) => string[];
  };
}

export function applyExplicitLineAdapter(
  textbox: fabric.Textbox,
  explicitLines: string[]
): void {
  const customTextbox = textbox as unknown as CustomTextbox;
  
  if (!customTextbox.__originalSplitTextIntoLines && customTextbox._splitTextIntoLines) {
    customTextbox.__originalSplitTextIntoLines = customTextbox._splitTextIntoLines;
  }
  
  const proto = fabric.Textbox.prototype as unknown as {
    _splitTextIntoLines(text: string): Fabric7TextLinesInfo;
  };
  
  const originalSplit = customTextbox.__originalSplitTextIntoLines || proto._splitTextIntoLines;
  
  customTextbox._splitTextIntoLines = function(this: CustomTextbox, text: string): Fabric7TextLinesInfo {
    if (this.isEditing) {
      return originalSplit.call(this, text);
    }
    
    const utilString = (fabric.util as unknown as FabricUtilString);
    const splitFn = utilString.string?.graphemeSplit || ((s: string) => s.split(''));
    
    const graphemeLines = explicitLines.map((line) => splitFn(line));
    
    const graphemeText: string[] = [];
    for (let i = 0; i < graphemeLines.length; i++) {
      graphemeText.push(...graphemeLines[i]);
      if (i < graphemeLines.length - 1) {
        graphemeText.push('\n');
      }
    }
    
    return {
      lines: explicitLines,
      graphemeLines,
      _unwrappedLines: graphemeLines,
      graphemeText,
    };
  };
}

export function removeExplicitLineAdapter(textbox: fabric.Textbox): void {
  const customTextbox = textbox as CustomTextbox;
  if (customTextbox.__originalSplitTextIntoLines) {
    customTextbox._splitTextIntoLines = customTextbox.__originalSplitTextIntoLines;
    delete customTextbox.__originalSplitTextIntoLines;
  }
}

export function isExplicitLineAdapterApplied(textbox: fabric.Textbox): boolean {
  const customTextbox = textbox as CustomTextbox;
  return !!customTextbox.__originalSplitTextIntoLines;
}
