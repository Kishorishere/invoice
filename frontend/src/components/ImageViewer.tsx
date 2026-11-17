import { useEffect, useRef, useState } from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Minus, Plus, RotateCcw, X } from "lucide-react";

import { cn } from "@/lib/utils";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  src: string;
  alt?: string;
}

const MIN_ZOOM = 0.25;
const MAX_ZOOM = 6;
const STEP = 0.25;

export function ImageViewer({ open, onOpenChange, src, alt = "Invoice" }: Props) {
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const dragging = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => {
    if (open) {
      setZoom(1);
      setPan({ x: 0, y: 0 });
    }
  }, [open, src]);

  const clamp = (z: number) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z));
  const zoomIn = () => setZoom((z) => clamp(z + STEP));
  const zoomOut = () => setZoom((z) => clamp(z - STEP));
  const reset = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  };

  const onWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const dir = e.deltaY > 0 ? -1 : 1;
    setZoom((z) => clamp(z + dir * STEP));
  };

  const onPointerDown = (e: React.PointerEvent) => {
    if (zoom <= 1) return;
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    dragging.current = { x: e.clientX - pan.x, y: e.clientY - pan.y };
  };
  const onPointerMove = (e: React.PointerEvent) => {
    if (!dragging.current) return;
    setPan({ x: e.clientX - dragging.current.x, y: e.clientY - dragging.current.y });
  };
  const onPointerUp = () => {
    dragging.current = null;
  };

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm data-[state=open]:animate-fade-in" />
        <DialogPrimitive.Content
          className="fixed inset-0 z-50 flex items-center justify-center outline-none"
          onWheel={onWheel}
          aria-describedby={undefined}
        >
          <DialogPrimitive.Title className="sr-only">Invoice image</DialogPrimitive.Title>

          <div
            className="h-full w-full overflow-hidden"
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerUp}
          >
            <div
              className="flex h-full w-full items-center justify-center"
              style={{
                cursor: zoom > 1 ? (dragging.current ? "grabbing" : "grab") : "default",
              }}
            >
              <img
                src={src}
                alt={alt}
                draggable={false}
                className="max-h-[92vh] max-w-[92vw] select-none transition-transform duration-75 will-change-transform"
                style={{
                  transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
                }}
              />
            </div>
          </div>

          {/* Zoom controls */}
          <div className="fixed bottom-6 left-1/2 z-10 flex -translate-x-1/2 items-center gap-1 rounded-full border border-border bg-card/90 px-2 py-1.5 shadow-pop backdrop-blur">
            <ToolBtn label="Zoom out" onClick={zoomOut} disabled={zoom <= MIN_ZOOM}>
              <Minus className="h-4 w-4" />
            </ToolBtn>
            <span className="min-w-[3rem] text-center text-xs font-medium tabular-nums text-foreground">
              {Math.round(zoom * 100)}%
            </span>
            <ToolBtn label="Zoom in" onClick={zoomIn} disabled={zoom >= MAX_ZOOM}>
              <Plus className="h-4 w-4" />
            </ToolBtn>
            <span className="mx-1 h-5 w-px bg-border" />
            <ToolBtn label="Reset" onClick={reset}>
              <RotateCcw className="h-4 w-4" />
            </ToolBtn>
          </div>

          <DialogPrimitive.Close
            aria-label="Close"
            className="fixed right-6 top-6 z-10 inline-flex h-9 w-9 items-center justify-center rounded-full border border-border bg-card/90 text-foreground shadow-pop backdrop-blur transition-colors hover:bg-card ring-focus"
          >
            <X className="h-4 w-4" />
          </DialogPrimitive.Close>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

function ToolBtn({
  label,
  onClick,
  disabled,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      className={cn(
        "inline-flex h-7 w-7 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-foreground ring-focus",
        "disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent"
      )}
    >
      {children}
    </button>
  );
}
