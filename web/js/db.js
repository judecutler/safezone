// IndexedDB is the only store the emergency screens read. Keys in `kv`: 'saved' and 'guidance'.
// `images` holds each room's JPEG blob by room id; the server never keeps images.
const DB_NAME = 'safezone';

let opening;
function open() {
  opening ??= new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      req.result.createObjectStore('kv');
      req.result.createObjectStore('images');
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  return opening;
}

async function run(store, mode, fn) {
  const db = await open();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, mode);
    const req = fn(tx.objectStore(store));
    tx.oncomplete = () => resolve(req?.result);
    tx.onerror = () => reject(tx.error);
  });
}

export const getKV = (key) => run('kv', 'readonly', (s) => s.get(key));
export const putKV = (key, value) => run('kv', 'readwrite', (s) => s.put(value, key));
export const getImage = (id) => run('images', 'readonly', (s) => s.get(id));
export const putImage = (id, blob) => run('images', 'readwrite', (s) => s.put(blob, id));
export const deleteImage = (id) => run('images', 'readwrite', (s) => s.delete(id));

export async function clearAll() {
  await run('kv', 'readwrite', (s) => s.clear());
  await run('images', 'readwrite', (s) => s.clear());
}

export async function loadImageUrls(roomIds) {
  const urls = {};
  for (const id of roomIds) {
    const blob = await getImage(id);
    if (blob) urls[id] = URL.createObjectURL(blob);
  }
  return urls;
}
