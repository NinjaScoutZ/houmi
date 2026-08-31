import type { TextBlock, Page, Project } from '../stores/projectStore';

export interface MinimalProjectState {
  activeProject: Project | null;
  activePage: Page | null;
  selectedBlock: TextBlock | null;
  selectedBlocks: TextBlock[];
}

const blockMutationRevisions = new Map<string, number>();
const pageMutationRevisions = new Map<string, number>();

export function incrementMutationRevision(blockId: string): number {
  const rev = (blockMutationRevisions.get(blockId) || 0) + 1;
  blockMutationRevisions.set(blockId, rev);
  return rev;
}

export function getMutationRevision(blockId: string): number {
  return blockMutationRevisions.get(blockId) || 0;
}

export function shouldAcceptResponse(blockId: string, capturedRevision: number): boolean {
  return capturedRevision === getMutationRevision(blockId);
}

export function incrementPageMutationRevision(pageId: string): number {
  const revision = (pageMutationRevisions.get(pageId) || 0) + 1;
  pageMutationRevisions.set(pageId, revision);
  return revision;
}

export function getPageMutationRevision(pageId: string): number {
  return pageMutationRevisions.get(pageId) || 0;
}

export function shouldAcceptPageResponse(pageId: string, capturedRevision: number): boolean {
  return capturedRevision === getPageMutationRevision(pageId);
}

export function applyBlockResponse<T extends MinimalProjectState>(
  state: T,
  blockId: string,
  updatedBlock: TextBlock
): Partial<T> {
  const activeProj = state.activeProject;
  const activePage = state.activePage;
  
  let newProj: Project | null = null;
  let newActivePage: Page | null = activePage;
  
  if (activeProj) {
    const updatedPages = activeProj.pages.map((p) => {
      if (p.id === updatedBlock.page_id) {
        const updatedBlocks = p.text_blocks.map((b) =>
          b.id === blockId ? updatedBlock : b
        );
        const newP = { ...p, text_blocks: updatedBlocks };
        if (activePage && p.id === activePage.id) {
          newActivePage = newP;
        }
        return newP;
      }
      return p;
    });
    newProj = { ...activeProj, pages: updatedPages };
  } else if (activePage && activePage.id === updatedBlock.page_id) {
    const updatedBlocks = activePage.text_blocks.map((b) =>
      b.id === blockId ? updatedBlock : b
    );
    newActivePage = { ...activePage, text_blocks: updatedBlocks };
  }
  
  return {
    activePage: newActivePage,
    activeProject: newProj || state.activeProject,
    selectedBlock: state.selectedBlock?.id === blockId ? updatedBlock : state.selectedBlock,
    selectedBlocks: state.selectedBlocks.map((b) =>
      b.id === blockId ? updatedBlock : b
    ),
  } as unknown as Partial<T>;
}

export function clearAllMutationRevisions(): void {
  blockMutationRevisions.clear();
  pageMutationRevisions.clear();
}
