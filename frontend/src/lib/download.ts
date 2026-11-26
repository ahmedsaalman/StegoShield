/** Save a blob or text as a file through the browser's normal download flow. */
export function saveFile(contents: Blob | string, filename: string, mimeType = "application/octet-stream"): void {
  const blob = typeof contents === "string" ? new Blob([contents], { type: mimeType }) : contents;
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.rel = "noopener";
  document.body.append(link);
  link.click();
  link.remove();
  // Revoke after the click has been handled, or some browsers cancel the download.
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
