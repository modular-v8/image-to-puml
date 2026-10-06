import { useEffect, useState } from "react";

import { getInfo, regenerate, renderPuml, type Info, type RegenerateResult } from "@/api";
import { CodePane } from "@/components/CodePane";
import { DiagramPane } from "@/components/DiagramPane";
import { Header } from "@/components/Header";
import { ReviewStrip } from "@/components/ReviewStrip";
import { SourcePane } from "@/components/SourcePane";
import { UploadCard } from "@/components/UploadCard";

const MIME_PUML = "text/plain;charset=utf-8";
const MIME_SVG = "image/svg+xml;charset=utf-8";

function stem(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot > 0 ? name.slice(0, dot) : name;
}

function download(filename: string, text: string, mime: string) {
  const url = URL.createObjectURL(new Blob([text], { type: mime }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export default function App() {
  const [info, setInfo] = useState<Info | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [sourceUrl, setSourceUrl] = useState<string | null>(null);
  const [result, setResult] = useState<RegenerateResult | null>(null);
  const [puml, setPuml] = useState("");
  const [svg, setSvg] = useState<string | null>(null);
  const [diagramError, setDiagramError] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [rendering, setRendering] = useState(false);

  useEffect(() => {
    getInfo()
      .then(setInfo)
      .catch((e: Error) => setFailure(e.message));
  }, []);

  useEffect(() => {
    return () => {
      if (sourceUrl) URL.revokeObjectURL(sourceUrl);
    };
  }, [sourceUrl]);

  function clearResults() {
    setResult(null);
    setPuml("");
    setSvg(null);
    setDiagramError(null);
    setFailure(null);
  }

  function pick(next: File) {
    setFile(next);
    setSourceUrl(URL.createObjectURL(next));
    clearResults();
  }

  async function run() {
    if (!file || running) return;
    setRunning(true);
    clearResults();

    try {
      const next = await regenerate(file);
      setResult(next);
      setPuml(next.puml);
      setSvg(next.svg);
      setDiagramError(next.render_error);
    } catch (e) {
      setFailure((e as Error).message);
    } finally {
      setRunning(false);
    }
  }

  // Free: renders the edited text only, no model call. On failure the
  // previous diagram and the user's edits stay.
  async function rerender() {
    setRendering(true);
    try {
      setSvg(await renderPuml(puml));
      setDiagramError(null);
    } catch (e) {
      setDiagramError((e as Error).message);
    } finally {
      setRendering(false);
    }
  }

  const name = file ? stem(file.name) : "diagram";

  return (
    <div className="flex flex-col lg:h-dvh lg:min-h-(--shell-min-height)">
      <Header info={info} />
      {/* From lg up the app is one screen: the input row keeps its height, the
          code and diagram panes share what is left and scroll inside
          themselves. Same grid before and after an image is chosen, so
          nothing jumps. DOM order is the single-column order below lg. */}
      <main className="mx-auto flex w-full max-w-(--page-max-width) flex-col gap-(--spacing-20) px-(--spacing-16) py-(--spacing-16) md:px-(--spacing-32) lg:min-h-0 lg:flex-1">
        <div className="grid shrink-0 grid-cols-1 gap-(--spacing-20) lg:grid-cols-2">
          <UploadCard fileName={file?.name ?? null} running={running} onFile={pick} onRegenerate={run} />
          <SourcePane url={sourceUrl} name={file?.name ?? ""} />
        </div>

        {failure ? (
          <p role="alert" className="shrink-0 whitespace-pre-wrap border border-ink-black p-(--spacing-12) text-body-sm">
            {failure}
          </p>
        ) : null}

        <div className="grid grid-cols-1 gap-(--spacing-20) lg:min-h-0 lg:flex-1 lg:grid-cols-[minmax(0,var(--code-fr))_minmax(0,var(--diagram-fr))] lg:grid-rows-[minmax(0,1fr)]">
          <CodePane
            puml={puml}
            running={running}
            rendering={rendering}
            onChange={setPuml}
            onRender={rerender}
            onDownload={() => download(`${name}.puml`, puml, MIME_PUML)}
          />
          <DiagramPane
            svg={svg}
            error={diagramError}
            running={running}
            onDownload={() => svg && download(`${name}.svg`, svg, MIME_SVG)}
          />
        </div>

        {result ? <ReviewStrip result={result} /> : null}
      </main>
    </div>
  );
}
