import { Pane } from "@/components/Pane";
import { Button } from "@/components/ui/button";

type CodePaneProps = {
  puml: string;
  running: boolean;
  rendering: boolean;
  onChange: (puml: string) => void;
  onRender: () => void;
  onDownload: () => void;
};

export function CodePane({ puml, running, rendering, onChange, onRender, onDownload }: CodePaneProps) {
  const empty = puml === "";

  return (
    <Pane
      title="PlantUML"
      actions={
        <>
          <Button onClick={onRender} disabled={empty || running || rendering}>
            {rendering ? "Rendering…" : "Re-render"}
          </Button>
          <Button onClick={onDownload} disabled={empty || running}>
            Download .puml
          </Button>
        </>
      }
    >
      {running ? (
        <p className="text-body-sm text-smoke">Extracting…</p>
      ) : (
        <textarea
          value={puml}
          onChange={(e) => onChange(e.target.value)}
          spellCheck={false}
          placeholder="PlantUML appears here."
          className="min-h-(--code-min-height) w-full flex-1 lg:min-h-0 resize-y rounded-(--radius-cards) border border-silver bg-paper-white p-(--spacing-12) font-mono text-caption text-ink-black placeholder:text-smoke"
        />
      )}
    </Pane>
  );
}
