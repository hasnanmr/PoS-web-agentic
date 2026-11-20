// Shrinks a picked photo in the browser before upload (O5 "Foto *"), so Storage holds a file
// sized for the screens that show it (at most a 112 px tile in O5 and a card in S1) instead of
// a multi-megabyte phone photo. Output is JPEG; transparent areas become white.

const MAX_SIDE = 800
const JPEG_QUALITY = 0.82

/**
 * The photo scaled down so its longest side is at most 800 px, as JPEG. Returns the original
 * file when the browser cannot decode or encode it (the server still checks type and size), or
 * when the re-encoded file would not be smaller.
 */
export async function resizeImage(file: Blob): Promise<Blob> {
  if (typeof createImageBitmap !== 'function') return file
  let bitmap: ImageBitmap
  try {
    bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
  } catch {
    return file
  }
  try {
    const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height))
    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.round(bitmap.width * scale))
    canvas.height = Math.max(1, Math.round(bitmap.height * scale))
    const ctx = canvas.getContext('2d')
    if (!ctx) return file
    ctx.fillStyle = '#FFFFFF'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', JPEG_QUALITY))
    return blob && blob.type === 'image/jpeg' && blob.size < file.size ? blob : file
  } finally {
    bitmap.close()
  }
}
