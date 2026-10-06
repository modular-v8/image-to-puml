import { useState } from "react";

import { DiagramViewer } from "@/components/DiagramViewer";
import { Pane } from "@/components/Pane";
import { Button } from "@/components/ui/button";
import { svgDataUrl } from "@/lib/svg";

type DiagramPaneProps = {
  svg: string | null;
  error: string | null;
  running: boolean;
  onDownload: () => void;
};

export function DiagramPane({ svg, error, running, onDownload }: DiagramPaneProps) {
  const [viewing, setViewing] = useState(false);
  const showImage = !running && svg;
  const showPlaceholder = !running && !svg && !error;

  return (
    <Pane
      title="Rendered"
      className="min-h-(--diagram-min-height) lg:min-h-0"
      // From lg the image is absolutely positioned so the whole diagram fits the
      // pane; states without an image sit in the middle.
      bodyClassName={showImage ? "lg:relative" : "items-center justify-center"}
      actions={
        <>
          <Button onClick={() => setViewing(true)} disabled={!svg || running}>
            Open full size
          </Button>
          <Button onClick={onDownload} disabled={!svg || running}>
            Download .svg
          </Button>
        </>
      }
    >
      {running ? <p className="text-body-sm text-smoke">Waiting for the model…</p> : null}
      {showImage ? (
        <img
          src={svgDataUrl(svg)}
          alt="Rendered diagram"
          title="Double-click to open full size"
          onDoubleClick={() => setViewing(true)}
          className="h-auto w-full cursor-zoom-in rounded-(--radius-images) bg-paper-white object-contain lg:absolute lg:inset-0 lg:h-full"
        />
      ) : null}
      {showPlaceholder ? <p className="text-body-sm text-smoke">The diagram appears here.</p> : null}
      {!running && error ? (
        <pre className="w-full whitespace-pre-wrap break-words border border-ink-black bg-paper-white p-(--spacing-12) font-mono text-caption text-ink-black">
          {error}
        </pre>
      ) : null}
      {viewing && svg ? <DiagramViewer svg={svg} onClose={() => setViewing(false)} onDownload={onDownload} /> : null}
    </Pane>
  );
}
