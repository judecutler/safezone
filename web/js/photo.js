const MAX_SIDE = 1600;
const QUALITY = 0.88;

async function decode(file) {
  try {
    return await createImageBitmap(file, { imageOrientation: 'from-image' });
  } catch {
    // Older Safari lacks the options bag; an <img> applies EXIF orientation itself.
    const url = URL.createObjectURL(file);
    try {
      const img = new Image();
      img.src = url;
      await img.decode();
      return img;
    } finally {
      URL.revokeObjectURL(url);
    }
  }
}

export async function toUploadJpeg(file) {
  const src = await decode(file);
  const sw = src.naturalWidth ?? src.width, sh = src.naturalHeight ?? src.height;
  const k = Math.min(1, MAX_SIDE / Math.max(sw, sh));
  const width = Math.round(sw * k), height = Math.round(sh * k);
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  canvas.getContext('2d').drawImage(src, 0, 0, width, height);
  src.close?.();
  const blob = await new Promise((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('encode_failed'))), 'image/jpeg', QUALITY));
  return { blob, width, height };
}
