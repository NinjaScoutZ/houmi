/**
 * Small persistent outbox for mutations that are safe to retry.
 *
 * The desktop Local Engine is the source of truth for normal offline work
 * (SQLite lives in the local backend).  This outbox is deliberately kept at
 * the boundary so Cloud sync can be added without rewriting the editor.
 * Binary multipart uploads are not queued here; they need resumable asset
 * upload semantics and are handled by the Local Engine first.
 */

export type OfflineMutationStatus = 'pending' | 'failed';

export interface OfflineMutation {
  id: string;
  method: string;
  path: string;
  body: string;
  headers: Record<string, string>;
  createdAt: string;
  attempts: number;
  status: OfflineMutationStatus;
  idempotencyKey: string;
  lastError?: string;
}

const DATABASE_NAME = 'houmi-offline';
const DATABASE_VERSION = 1;
const MUTATIONS_STORE = 'mutations';

let databasePromise: Promise<IDBDatabase> | null = null;

function hasIndexedDb(): boolean {
  return typeof indexedDB !== 'undefined';
}

function openDatabase(): Promise<IDBDatabase> {
  if (!hasIndexedDb()) return Promise.reject(new Error('IndexedDB is unavailable'));
  if (databasePromise) return databasePromise;

  databasePromise = new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
    request.onerror = () => reject(request.error || new Error('Failed to open offline database'));
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(MUTATIONS_STORE)) {
        const store = db.createObjectStore(MUTATIONS_STORE, { keyPath: 'id' });
        store.createIndex('status_createdAt', ['status', 'createdAt'], { unique: false });
      }
    };
    request.onsuccess = () => resolve(request.result);
  });

  return databasePromise;
}

function transaction<T>(mode: IDBTransactionMode, action: (store: IDBObjectStore) => IDBRequest): Promise<T> {
  return openDatabase().then((db) => new Promise<T>((resolve, reject) => {
    const tx = db.transaction(MUTATIONS_STORE, mode);
    const request = action(tx.objectStore(MUTATIONS_STORE));
    request.onerror = () => reject(request.error || new Error('Offline database request failed'));
    request.onsuccess = () => resolve(request.result as T);
  }));
}

export function canQueueMutation(method: string, body: unknown): boolean {
  return ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method.toUpperCase())
    && typeof body === 'string'
    && body.length <= 1024 * 1024;
}

export async function enqueueMutation(input: Omit<OfflineMutation, 'id' | 'createdAt' | 'attempts' | 'status'>): Promise<OfflineMutation> {
  const mutation: OfflineMutation = {
    ...input,
    id: crypto.randomUUID(),
    createdAt: new Date().toISOString(),
    attempts: 0,
    status: 'pending',
  };
  await transaction<IDBValidKey>('readwrite', (store) => store.add(mutation));
  return mutation;
}

export async function listPendingMutations(): Promise<OfflineMutation[]> {
  const items = await transaction<OfflineMutation[]>('readonly', (store) => store.getAll());
  return items
    .filter((item) => item.status === 'pending' || item.status === 'failed')
    .sort((a, b) => a.createdAt.localeCompare(b.createdAt));
}

export async function removeMutation(id: string): Promise<void> {
  await transaction<undefined>('readwrite', (store) => store.delete(id));
}

export async function markMutationFailed(id: string, error: unknown): Promise<void> {
  const db = await openDatabase();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(MUTATIONS_STORE, 'readwrite');
    const store = tx.objectStore(MUTATIONS_STORE);
    const getRequest = store.get(id);
    getRequest.onerror = () => reject(getRequest.error || new Error('Failed to read mutation'));
    getRequest.onsuccess = () => {
      const current = getRequest.result as OfflineMutation | undefined;
      if (!current) {
        resolve();
        return;
      }
      current.status = 'failed';
      current.attempts += 1;
      current.lastError = error instanceof Error ? error.message : String(error);
      store.put(current);
    };
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error || new Error('Failed to update mutation'));
  });
}

export async function countPendingMutations(): Promise<number> {
  const items = await listPendingMutations();
  return items.length;
}

/** Test helper; production code never needs to clear the outbox wholesale. */
export function resetOfflineDatabaseForTests(): void {
  databasePromise = null;
}
