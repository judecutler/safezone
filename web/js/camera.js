// The rear camera, and the photo picker when there is no camera. The permissions screen asks first;
// its stream is handed to the capture screen so the phone does not ask twice.

const CONSTRAINTS = {
  audio: false,
  video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1080 } },
};
const HANDOFF_MS = 15000;

let handoff = null;
// 'unknown' until the person answers on the permissions screen; 'declined' after "Not now", so the
// capture screen does not raise a prompt the person just turned down.
let choice = 'unknown';

const hasCamera = () => Boolean(navigator.mediaDevices?.getUserMedia);
const problem = (e) => (e?.name === 'NotAllowedError' || e?.name === 'SecurityError' ? 'denied' : 'unavailable');
const live = (stream) => stream?.getVideoTracks().some((t) => t.readyState === 'live');
const stopStream = (stream) => stream?.getTracks().forEach((t) => t.stop());

function takeHandoff() {
  if (!handoff) return null;
  clearTimeout(handoff.timer);
  const { stream } = handoff;
  handoff = null;
  return live(stream) ? stream : null;
}

export const cameraDeclined = () => choice === 'declined';
export function declineCamera() {
  choice = 'declined';
  stopStream(takeHandoff());
}

// Asks for the camera now. Resolves to 'granted' | 'denied' | 'unavailable'.
export async function requestCamera() {
  if (!hasCamera()) return 'unavailable';
  try {
    const stream = await navigator.mediaDevices.getUserMedia(CONSTRAINTS);
    stopStream(takeHandoff());
    handoff = { stream, timer: setTimeout(() => stopStream(takeHandoff()), HANDOFF_MS) };
    choice = 'granted';
    return 'granted';
  } catch (e) {
    return problem(e);
  }
}

// Shows the rear camera in `videoEl`. Rejects with an error whose `code` is 'denied',
// 'unavailable' or 'declined'; the caller then offers pickPhoto().
export async function openCamera(videoEl) {
  let stream = takeHandoff();
  if (!stream) {
    if (choice === 'declined') throw Object.assign(new Error('camera'), { code: 'declined' });
    if (!hasCamera()) throw Object.assign(new Error('camera'), { code: 'unavailable' });
    try {
      stream = await navigator.mediaDevices.getUserMedia(CONSTRAINTS);
      choice = 'granted';
    } catch (e) {
      throw Object.assign(new Error('camera'), { code: problem(e) });
    }
  }
  Object.assign(videoEl, { muted: true, playsInline: true, autoplay: true, srcObject: stream });
  await videoEl.play().catch(() => {});
  return {
    stop() {
      stopStream(stream);
      if (videoEl.srcObject === stream) videoEl.srcObject = null;
    },
    capture() {
      const canvas = document.createElement('canvas');
      canvas.width = videoEl.videoWidth;
      canvas.height = videoEl.videoHeight;
      canvas.getContext('2d').drawImage(videoEl, 0, 0);
      return new Promise((resolve, reject) =>
        canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('encode_failed'))), 'image/jpeg', 0.92));
    },
  };
}

// The fallback: the system photo picker, which on phones also offers the camera app. Call it from
// a tap. Resolves to the chosen File, or null when the person cancels.
export function pickPhoto() {
  return new Promise((resolve) => {
    const input = Object.assign(document.createElement('input'), { type: 'file', accept: 'image/*' });
    input.addEventListener('change', () => resolve(input.files?.[0] ?? null), { once: true });
    input.addEventListener('cancel', () => resolve(null), { once: true });
    input.click();
  });
}
