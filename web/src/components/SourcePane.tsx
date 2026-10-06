import { Pane } from "@/components/Pane";

type SourcePaneProps = {
  url: string | null;
  name: string;
};

// In the top row the pane takes the upload card's height: from lg up
// the image is absolutely positioned inside the body, so it fills the space
// without adding to the row's height. Single column has no row height, so
// it uses the capped thumbnail instead.
export function SourcePane({ url, name }: SourcePaneProps) {
  return (
    <Pane title="Source" bodyClassName="lg:relative lg:min-h-0">
      {url ? (
        <img
          src={url}
          alt={name}
          className="h-(--thumb-max-height) w-full rounded-(--radius-images) bg-paper-white object-contain lg:absolute lg:inset-0 lg:h-full"
        />
      ) : (
        <p className="text-body-sm text-smoke">The source image appears here.</p>
      )}
    </Pane>
  );
}
