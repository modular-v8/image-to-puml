// An <img> with a data URL: scripts inside the SVG cannot execute. Never
// open an SVG as a document (new tab, <object>, <iframe>): it would run
// its scripts on this app's origin.
export function svgDataUrl(svg: string): string {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}
