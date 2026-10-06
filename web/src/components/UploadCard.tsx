import { FileImage } from "lucide-react";

import { FileUpload } from "@/components/extend/file-upload";
import { Button } from "@/components/ui/button";

const ACCEPT = ".png,.jpg,.jpeg,image/png,image/jpeg";
const ACCEPTED_TYPES = [{ label: "Image", icon: FileImage }];

type UploadCardProps = {
  fileName: string | null;
  running: boolean;
  onFile: (file: File) => void;
  onRegenerate: () => void;
};

export function UploadCard({ fileName, running, onFile, onRegenerate }: UploadCardProps) {
  return (
    <section className="tilda-upload flex flex-col gap-(--spacing-12) rounded-(--radius-cards) bg-bone p-(--spacing-16)">
      <FileUpload
        accept={ACCEPT}
        acceptedFileTypes={ACCEPTED_TYPES}
        multiple={false}
        showBorderBeam={false}
        showFileList={false}
        title="Drop a class diagram"
        description="PNG or JPG"
        onFilesAccepted={(files) => onFile(files[0])}
      />
      <p className="min-w-0 truncate text-body-sm text-carbon">{fileName ?? "No image selected."}</p>
      <Button variant="cta" className="w-full" onClick={onRegenerate} disabled={!fileName || running}>
        {running ? "Regenerating…" : "Regenerate"}
      </Button>
    </section>
  );
}
