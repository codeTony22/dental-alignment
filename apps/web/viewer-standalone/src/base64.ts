/**
 * Pure, framework-free base64 -> ArrayBuffer decoding for the standalone viewer.
 * The emitter inlines each STL as a base64 string in window.__CASE__.parts[].b64; this turns
 * that back into the ArrayBuffer STLLoader.parse() expects. Uses atob (available in every
 * browser this file:// viewer targets) rather than Buffer, which is not guaranteed in a
 * browser context.
 */
export function base64ToArrayBuffer(b64: string): ArrayBuffer {
  const binaryString = atob(b64);
  const length = binaryString.length;
  const bytes = new Uint8Array(length);
  for (let i = 0; i < length; i += 1) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  return bytes.buffer;
}
