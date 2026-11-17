import { useCallback, useEffect, useState } from "react";
import { useDropzone, type FileRejection } from "react-dropzone";
import { motion } from "framer-motion";
import { Download, FileImage, Folder, Plus, UploadCloud, X } from "lucide-react";
import { toast } from "sonner";

import { ProviderPicker } from "@/components/ProviderPicker";
import { Button } from "@/components/ui/button";
import { useLimits } from "@/lib/limitsContext";
import { cn } from "@/lib/utils";

interface Props {
  busy: boolean;
  files: File[];
  onFilesChange: (next: File[]) => void;
  model: string | null;
  onModelChange: (m: string) => void;
}

const ACCEPT = {
  "image/jpeg": [".jpg", ".jpeg"],
  "image/png": [".png"],
  "image/webp": [".webp"],
  "application/pdf": [".pdf"],
};
const MAX_SIZE = 10 * 1024 * 1024;

export function Uploader({
  busy,
  files,
  onFilesChange,
  model,
  onModelChange,
}: Props) {
  const { status: limits } = useLimits();
  const maxFiles = limits?.limits.max_files_per_upload ?? 1;

  const remainingSlots = Math.max(0, maxFiles - files.length);

  const onDrop = useCallback(
    (accepted: File[], rejected: FileRejection[]) => {
      if (rejected.length) {
        const code = rejected[0]?.errors[0]?.code;
        if (code === "file-too-large") toast.error("A file is larger than 10MB.");
        else if (code === "file-invalid-type") toast.error("Use JPG, PNG, WEBP or PDF.");
        else if (code === "too-many-files") toast.error(`Max ${maxFiles} per upload.`);
        else toast.error("Couldn't accept that file.");
        // still fall through so any accepted ones in the same drop are kept
      }
      if (!accepted.length) return;

      const trimmed = accepted.slice(0, remainingSlots);
      if (accepted.length > trimmed.length) {
        toast.message(`Only ${maxFiles} per upload — kept the first ${trimmed.length}.`);
      }
      const merged = dedupe([...files, ...trimmed]).slice(0, maxFiles);
      onFilesChange(merged);
    },
    [files, maxFiles, remainingSlots, onFilesChange]
  );

  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    onDrop,
    accept: ACCEPT,
    maxFiles: Math.max(1, remainingSlots || maxFiles),
    maxSize: MAX_SIZE,
    noClick: true,
    noKeyboard: true,
    disabled: busy,
  });

  // When the queue is non-empty, render the staged-files list.
  if (files.length > 0) {
    return (
      <StagedList
        files={files}
        maxFiles={maxFiles}
        remainingSlots={remainingSlots}
        busy={busy}
        onFilesChange={onFilesChange}
        onAddClick={open}
        inputProps={getInputProps()}
        model={model}
        onModelChange={onModelChange}
      />
    );
  }

  return (
    <div
      {...getRootProps()}
      className={cn(
        "relative rounded-3xl border-2 border-dashed p-6 transition-all duration-200",
        "sm:p-8",
        "bg-card shadow-soft",
        isDragActive
          ? "border-foreground/40 scale-[1.005]"
          : "border-border hover:border-foreground/25"
      )}
    >
      <input {...getInputProps()} />

      <div className="flex items-center justify-end">
        <ProviderPicker
          model={model}
          onModelChange={onModelChange}
          disabled={busy}
        />
      </div>

      <div className="flex flex-col items-center justify-center text-center py-10 sm:py-14">
        <motion.div
          initial={{ y: 4, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          className="mb-6 flex h-16 w-16 items-center justify-center text-foreground/55"
        >
          <UploadCloud className="h-14 w-14" strokeWidth={1.25} />
        </motion.div>
        <p className="font-display text-2xl text-foreground sm:text-3xl">Drop your invoices here</p>
        <p className="mt-1 text-sm text-muted-foreground">
          PDF, PNG, JPG &middot; up to {maxFiles} {maxFiles === 1 ? "file" : "files"} &middot; Max 10 MB each
        </p>

        <Button
          type="button"
          onClick={open}
          size="lg"
          className="mt-7 h-12 rounded-full px-7 text-sm shadow-soft hover:shadow-pop"
        >
          <Folder className="h-4 w-4" />
          Choose {maxFiles === 1 ? "file" : "files"}
        </Button>
      </div>

      <div className="flex items-center justify-between">
        <a
          href="/invoice.png"
          download="sample-invoice.png"
          onClick={(e) => e.stopPropagation()}
          className="inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-xs text-muted-foreground hover:text-foreground ring-focus"
        >
          <Download className="h-3.5 w-3.5" />
          Download sample
        </a>
        <span className="text-[11px] text-muted-foreground/70">Drag anywhere in this card</span>
      </div>
    </div>
  );
}

function StagedList({
  files,
  maxFiles,
  remainingSlots,
  busy,
  onFilesChange,
  onAddClick,
  inputProps,
  model,
  onModelChange,
}: {
  files: File[];
  maxFiles: number;
  remainingSlots: number;
  busy: boolean;
  onFilesChange: (next: File[]) => void;
  onAddClick: () => void;
  inputProps: React.HTMLAttributes<HTMLInputElement>;
  model: string | null;
  onModelChange: (m: string) => void;
}) {
  const multi = files.length > 1;
  return (
    <div className="rounded-3xl border border-border bg-card/70 p-5 shadow-soft">
      <div className="mb-4 flex items-center justify-between gap-3">
        {multi ? (
          <div className="text-sm text-muted-foreground">
            <span className="font-medium text-foreground">{files.length}</span> of {maxFiles} queued
          </div>
        ) : (
          <span />
        )}
        <ProviderPicker
          model={model}
          onModelChange={onModelChange}
          disabled={busy}
        />
      </div>

      {multi ? (
        <ul className="space-y-2">
          {files.map((f, i) => (
            <StagedRow
              key={`${f.name}-${f.size}-${i}`}
              file={f}
              disabled={busy}
              onRemove={() => onFilesChange(files.filter((_, idx) => idx !== i))}
            />
          ))}
        </ul>
      ) : (
        <SingleStagedPreview
          file={files[0]}
          disabled={busy}
          onRemove={() => onFilesChange([])}
        />
      )}

      <input {...inputProps} />
      {multi && (
        <div className="mt-4 flex items-center justify-between">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onAddClick}
            disabled={busy || remainingSlots <= 0}
            className="rounded-full"
          >
            <Plus className="h-3.5 w-3.5" />
            Add more {remainingSlots > 0 ? `(${remainingSlots} left)` : "(full)"}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => onFilesChange([])}
            disabled={busy}
          >
            Clear all
          </Button>
        </div>
      )}
    </div>
  );
}

function SingleStagedPreview({
  file,
  disabled,
  onRemove,
}: {
  file: File;
  disabled: boolean;
  onRemove: () => void;
}) {
  const url = useObjectUrl(file);
  const isImage = file.type.startsWith("image/");
  return (
    <div className="relative overflow-hidden rounded-2xl border border-border bg-background/60">
      <div className="flex min-h-[20rem] items-center justify-center bg-muted/40 p-4 sm:min-h-[26rem]">
        {isImage && url ? (
          <img
            src={url}
            alt={file.name}
            className="max-h-[22rem] max-w-full object-contain sm:max-h-[28rem]"
          />
        ) : (
          <div className="flex flex-col items-center gap-2 text-muted-foreground">
            <FileImage className="h-10 w-10" />
            <span className="text-xs">No preview available</span>
          </div>
        )}
      </div>
      <div className="flex items-center justify-between gap-3 border-t border-border bg-card/70 px-4 py-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-foreground">{file.name}</p>
          <p className="text-xs text-muted-foreground">
            {(file.size / 1024).toFixed(0)} KB
            {file.type ? ` · ${file.type}` : ""}
          </p>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={onRemove}
          disabled={disabled}
          className="rounded-full"
        >
          <X className="h-4 w-4" />
          Remove
        </Button>
      </div>
    </div>
  );
}

function StagedRow({
  file,
  disabled,
  onRemove,
}: {
  file: File;
  disabled: boolean;
  onRemove: () => void;
}) {
  const url = useObjectUrl(file);
  const isImage = file.type.startsWith("image/");
  return (
    <li className="flex items-center gap-3 rounded-2xl border border-border/60 bg-background/60 p-2">
      <div className="h-12 w-12 shrink-0 overflow-hidden rounded-xl border border-border bg-muted">
        {isImage && url ? (
          <img src={url} alt="" className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-muted-foreground">
            <FileImage className="h-5 w-5" />
          </div>
        )}
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-foreground">{file.name}</p>
        <p className="text-xs text-muted-foreground">
          {(file.size / 1024).toFixed(0)} KB
          {file.type ? ` · ${file.type}` : ""}
        </p>
      </div>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        onClick={onRemove}
        aria-label={`Remove ${file.name}`}
        disabled={disabled}
      >
        <X className="h-4 w-4" />
      </Button>
    </li>
  );
}

function useObjectUrl(file: File): string | null {
  // Create the URL inside the effect so StrictMode's double-invoke cleans up
  // the stale URL and sets up a fresh one, instead of leaving the component
  // pointing at a revoked blob.
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!file.type.startsWith("image/")) {
      setUrl(null);
      return;
    }
    const u = URL.createObjectURL(file);
    setUrl(u);
    return () => URL.revokeObjectURL(u);
  }, [file]);
  return url;
}

function dedupe(list: File[]): File[] {
  const seen = new Set<string>();
  const out: File[] = [];
  for (const f of list) {
    const key = `${f.name}:${f.size}:${f.lastModified}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(f);
  }
  return out;
}

