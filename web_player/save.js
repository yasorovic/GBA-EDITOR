// Le moteur précédent stockait les .sav dans le volume IndexedDB /data d'Emscripten.
const SAVE_DATABASE = "/data";
const SAVE_VERSION = 21;
const SAVE_STORE = "FILE_DATA";

function readRequest(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export async function openCartridgeSave(romName) {
  const key = `/data/saves/${romName.replace(/\.[^.]*$/, "")}.sav`;
  const request = indexedDB.open(SAVE_DATABASE, SAVE_VERSION);
  request.onupgradeneeded = () => {
    const db = request.result;
    const store = db.objectStoreNames.contains(SAVE_STORE)
      ? request.transaction.objectStore(SAVE_STORE)
      : db.createObjectStore(SAVE_STORE);
    if (!store.indexNames.contains("timestamp")) store.createIndex("timestamp", "timestamp");
  };
  const db = await readRequest(request);
  db.onversionchange = () => db.close();

  try {
    const entry = await readRequest(db.transaction(SAVE_STORE).objectStore(SAVE_STORE).get(key));
    const contents = entry?.contents;
    let lastSave = contents;
    return {
      contents,
      close() { db.close(); },
      write(bytes) {
        if (!bytes?.length || (lastSave?.length === bytes.length &&
            bytes.every((byte, index) => byte === lastSave[index]))) return;
        const transaction = db.transaction(SAVE_STORE, "readwrite");
        // Emscripten attend un fichier normal, avec les permissions 0666.
        transaction.objectStore(SAVE_STORE).put({
          timestamp: new Date(), mode: 0o100666, contents: bytes,
        }, key);
        lastSave = bytes;
        transaction.onabort = () => {
          if (lastSave === bytes) lastSave = null;
          console.warn("Could not save the cartridge.", transaction.error);
        };
      },
    };
  } catch (error) {
    db.close();
    throw error;
  }
}
