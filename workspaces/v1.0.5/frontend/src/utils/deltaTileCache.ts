/**
 * Houmi Studio - Sparse Virtual Tile Cache (SVTC) Manager
 * Controls GPU VRAM allocation with a fixed 256 physical slot pool for 600 DPI non-destructive canvas.
 */

export interface TileCoordinate {
  layerId: number; // 0..5 (0: RawScan, 1: InpaintDelta, 2: UserRedraw, 3: VectorBalloon, 4: Text, 5: SFX)
  tileX: number;
  tileY: number;
  lod: number;
}

export interface TileSlot {
  slotIndex: number;
  key: string;
  lastUsedFrame: number;
}

export class DeltaTileCacheManager {
  private readonly maxSlots: number;
  private currentFrame: number = 0;
  private readonly slotMap: Map<string, TileSlot> = new Map();
  private readonly freeSlots: number[] = [];

  constructor(maxSlots: number = 256) {
    this.maxSlots = maxSlots;
    for (let i = 0; i < maxSlots; i++) {
      this.freeSlots.push(i);
    }
  }

  public getSlot(coord: TileCoordinate): number | null {
    const key = `${coord.layerId}_${coord.tileX}_${coord.tileY}_${coord.lod}`;
    const slot = this.slotMap.get(key);
    if (slot) {
      slot.lastUsedFrame = this.currentFrame;
      return slot.slotIndex;
    }
    return null;
  }

  public allocateSlot(coord: TileCoordinate): number {
    this.currentFrame++;
    const key = `${coord.layerId}_${coord.tileX}_${coord.tileY}_${coord.lod}`;

    if (this.slotMap.has(key)) {
      const slot = this.slotMap.get(key)!;
      slot.lastUsedFrame = this.currentFrame;
      return slot.slotIndex;
    }

    if (this.freeSlots.length > 0) {
      const slotIndex = this.freeSlots.pop()!;
      this.slotMap.set(key, { slotIndex, key, lastUsedFrame: this.currentFrame });
      return slotIndex;
    }

    // LRU eviction
    let oldestKey = '';
    let oldestFrame = Infinity;
    for (const [k, slot] of this.slotMap.entries()) {
      if (slot.lastUsedFrame < oldestFrame) {
        oldestFrame = slot.lastUsedFrame;
        oldestKey = k;
      }
    }

    const evictedSlot = this.slotMap.get(oldestKey)!;
    this.slotMap.delete(oldestKey);
    this.slotMap.set(key, { slotIndex: evictedSlot.slotIndex, key, lastUsedFrame: this.currentFrame });
    return evictedSlot.slotIndex;
  }

  public invalidateLayer(layerId: number): void {
    const prefix = `${layerId}_`;
    for (const [key, slot] of this.slotMap.entries()) {
      if (key.startsWith(prefix)) {
        this.freeSlots.push(slot.slotIndex);
        this.slotMap.delete(key);
      }
    }
  }

  public getActiveSlotCount(): number {
    return this.slotMap.size;
  }
}
