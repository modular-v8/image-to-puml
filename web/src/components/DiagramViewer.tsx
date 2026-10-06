import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { svgDataUrl } from "@/lib/svg";

// Zoom is an absolute scale of the image's natural size: 1 = 100%.
const ZOOM_STEP = 1.25;
const ZOOM_MIN = 0.1;
const ZOOM_MAX = 8;
const PERCENT = 100;

type DiagramViewerProps = {
  svg: string;
  onClose: () => void;
  onDownload: () => void;
};

type Anchor = { x: number; y: number; ratio: number };

function clamp(zoom: number): number {
  return Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, zoom));
}

// Full-window viewer on a native <dialog>: Esc, focus and backdrop for free.
// Mounted only while open, so closing it leaves the page exactly as it was.
export function DiagramViewer({ svg, onClose, onDownload }: DiagramViewerProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const areaRef = useRef<HTMLDivElement>(null);
  const natural = useRef({ w: 0, h: 0 });
  const anchor = useRef<Anchor | null>(null);
  const drag = useRef<{ x: number; y: number; left: number; top: number } | null>(null);

  const [zoom, setZoomState] = useState(1);
  // The latest zoom, so rapid events compose instead of reading a stale render.
  const zoomRef = useRef(1);
  const [fitMode, setFitMode] = useState(true);
  const [loaded, setLoaded] = useState(false);

  const setZoom = useCallback((next: number) => {
    zoomRef.current = next;
    setZoomState(next);
  }, []);

  // Largest scale that shows the whole diagram, never above 100%.
  const fitScale = useCallback((): number => {
    const area = areaRef.current;
    const { w, h } = natural.current;
    if (!area || !w || !h) return 1;
    return Math.min(1, area.clientWidth / w, area.clientHeight / h);
  }, []);

  const fit = useCallback(() => {
    setFitMode(true);
    setZoom(fitScale());
  }, [fitScale, setZoom]);

  // `at` is a point in the scroll area to keep still while zooming.
  const zoomTo = useCallback(
    (next: number, at?: { x: number; y: number }) => {
      const area = areaRef.current;
      const target = clamp(next);
      if (area) {
        const point = at ?? { x: area.clientWidth / 2, y: area.clientHeight / 2 };
        anchor.current = { ...point, ratio: target / zoomRef.current };
      }
      setFitMode(false);
      setZoom(target);
    },
    [setZoom],
  );

  useEffect(() => {
    dialogRef.current?.showModal();
  }, []);

  // After the image resizes, scroll so the anchored point stays under it.
  useLayoutEffect(() => {
    const area = areaRef.current;
    const a = anchor.current;
    if (!area || !a) return;
    area.scrollLeft = (area.scrollLeft + a.x) * a.ratio - a.x;
    area.scrollTop = (area.scrollTop + a.y) * a.ratio - a.y;
    anchor.current = null;
  }, [zoom]);

  // Keep fit-to-window fitted when the window changes size.
  useEffect(() => {
    const area = areaRef.current;
    if (!area || !fitMode) return;
    const observer = new ResizeObserver(() => setZoom(fitScale()));
    observer.observe(area);
    return () => observer.disconnect();
  }, [fitMode, fitScale, setZoom]);

  // Ctrl/Cmd + wheel zooms toward the pointer. Needs a non-passive native
  // listener: React's onWheel cannot cancel the browser's own page zoom.
  useEffect(() => {
    const area = areaRef.current;
    if (!area) return;
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey && !e.metaKey) return;
      e.preventDefault();
      const rect = area.getBoundingClientRect();
      const factor = e.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP;
      zoomTo(zoomRef.current * factor, { x: e.clientX - rect.left, y: e.clientY - rect.top });
    };
    area.addEventListener("wheel", onWheel, { passive: false });
    return () => area.removeEventListener("wheel", onWheel);
  }, [zoomTo]);

  function onLoad(e: React.SyntheticEvent<HTMLImageElement>) {
    natural.current = { w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight };
    setLoaded(true);
    fit();
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "+" || e.key === "=") zoomTo(zoomRef.current * ZOOM_STEP);
    if (e.key === "-") zoomTo(zoomRef.current / ZOOM_STEP);
    if (e.key === "0") fit();
  }

  function onPointerDown(e: React.PointerEvent<HTMLDivElement>) {
    const area = e.currentTarget;
    area.setPointerCapture(e.pointerId);
    drag.current = { x: e.clientX, y: e.clientY, left: area.scrollLeft, top: area.scrollTop };
  }

  function onPointerMove(e: React.PointerEvent<HTMLDivElement>) {
    const start = drag.current;
    if (!start) return;
    e.currentTarget.scrollLeft = start.left - (e.clientX - start.x);
    e.currentTarget.scrollTop = start.top - (e.clientY - start.y);
  }

  const width = natural.current.w * zoom;

  return (
    <dialog
      ref={dialogRef}
      onClose={onClose}
      // Esc: `cancel` fires synchronously, before the native close, so the
      // page does not depend on the later (and easily delayed) `close` event.
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onKeyDown={onKeyDown}
      aria-label="Rendered diagram, full size"
      className="m-auto h-[calc(100dvh-2*var(--viewer-inset))] max-h-none w-[calc(100vw-2*var(--viewer-inset))] max-w-none flex-col border border-ink-black bg-paper-white p-0 text-ink-black backdrop:bg-ink-black/50 open:flex"
    >
      <div className="flex shrink-0 flex-wrap items-center gap-(--spacing-8) border-b border-bone p-(--spacing-12)">
        <Button onClick={() => zoomTo(zoomRef.current / ZOOM_STEP)} aria-label="Zoom out">
          −
        </Button>
        <Button onClick={() => zoomTo(zoomRef.current * ZOOM_STEP)} aria-label="Zoom in">
          +
        </Button>
        <Button onClick={fit}>Fit</Button>
        <Button onClick={() => zoomTo(1)}>100%</Button>
        <span aria-live="polite" className="min-w-(--spacing-60) text-caption text-smoke">
          {Math.round(zoom * PERCENT)}%
        </span>
        <span className="ml-auto flex gap-(--spacing-8)">
          <Button onClick={onDownload}>Download .svg</Button>
          <Button variant="dark" onClick={onClose}>
            Close
          </Button>
        </span>
      </div>

      <div
        ref={areaRef}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={() => (drag.current = null)}
        onPointerCancel={() => (drag.current = null)}
        className="flex min-h-0 flex-1 cursor-grab overflow-auto bg-bone active:cursor-grabbing"
      >
        <img
          src={svgDataUrl(svg)}
          alt="Rendered diagram"
          draggable={false}
          onLoad={onLoad}
          style={loaded ? { width } : { visibility: "hidden" }}
          className="m-auto h-auto max-w-none shrink-0 select-none bg-paper-white"
        />
      </div>
    </dialog>
  );
}
