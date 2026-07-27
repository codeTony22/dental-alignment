import { describe, expect, it } from "vitest";
import { base64ToArrayBuffer } from "./base64";

function toBytes(buffer: ArrayBuffer): number[] {
  return Array.from(new Uint8Array(buffer));
}

describe("base64ToArrayBuffer", () => {
  it("decodes a simple ASCII payload", () => {
    // "hello" -> base64
    const b64 = Buffer.from("hello", "utf-8").toString("base64");
    const buffer = base64ToArrayBuffer(b64);
    expect(new TextDecoder().decode(buffer)).toBe("hello");
  });

  it("decodes an empty string to an empty ArrayBuffer", () => {
    const buffer = base64ToArrayBuffer("");
    expect(buffer.byteLength).toBe(0);
  });

  it("round-trips arbitrary binary bytes (0-255), including nulls and high bytes", () => {
    const original = new Uint8Array(256);
    for (let i = 0; i < 256; i += 1) original[i] = i;
    const b64 = Buffer.from(original).toString("base64");

    const buffer = base64ToArrayBuffer(b64);
    expect(toBytes(buffer)).toEqual(Array.from(original));
  });

  it("produces a fresh ArrayBuffer of the expected byte length", () => {
    const b64 = Buffer.from([1, 2, 3, 4, 5]).toString("base64");
    const buffer = base64ToArrayBuffer(b64);
    expect(buffer.byteLength).toBe(5);
    expect(buffer).toBeInstanceOf(ArrayBuffer);
  });

  it("decodes STL-magic-like binary header bytes correctly (sanity check for the real use case)", () => {
    // A binary STL starts with an 80-byte header, then a uint32 triangle count. Simulate the
    // triangle-count prefix (little-endian) to make sure byte order survives the round-trip.
    const header = new Uint8Array(80).fill(0);
    const countBytes = new Uint8Array(4);
    new DataView(countBytes.buffer).setUint32(0, 42, true);
    const payload = new Uint8Array([...header, ...countBytes]);
    const b64 = Buffer.from(payload).toString("base64");

    const buffer = base64ToArrayBuffer(b64);
    const view = new DataView(buffer);
    expect(view.getUint32(80, true)).toBe(42);
  });
});
