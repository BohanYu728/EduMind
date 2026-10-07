import { useEffect, useRef, useState } from "react";
import type { Granularity } from "./types";
import { MODE_DESCRIPTIONS, MODES } from "./modeOptions";

export default function ModeSelector({
  value,
  disabled,
  onChange,
}: {
  value: Granularity;
  disabled: boolean;
  onChange: (mode: Granularity) => void;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const options = useRef<(HTMLButtonElement | null)[]>([]);
  useEffect(() => {
    if (!open) return;
    function dismiss(event: PointerEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("pointerdown", dismiss);
    return () => document.removeEventListener("pointerdown", dismiss);
  }, [open]);
  function show() {
    if (disabled) return;
    setOpen(true);
    requestAnimationFrame(() => options.current[MODES.indexOf(value)]?.focus());
  }
  return (
    <div
      className="mode-selector"
      ref={root}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
      }}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          setOpen(false);
          trigger.current?.focus();
          event.stopPropagation();
        }
      }}
    >
      <button
        type="button"
        className="mode-trigger"
        ref={trigger}
        disabled={disabled}
        aria-label={`备课模式：${value}`}
        aria-expanded={open}
        aria-haspopup="menu"
        title="选择备课模式"
        onClick={() => (open ? setOpen(false) : show())}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            show();
          }
        }}
      >
        {value}
        <span aria-hidden="true">⌄</span>
      </button>
      {open && (
        <div className="mode-menu" role="menu" aria-label="选择备课模式">
          <span className="mode-menu-heading">备课模式</span>
          {MODES.map((mode, index) => (
            <button
              type="button"
              key={mode}
              className={`mode-option${value === mode ? " selected" : ""}`}
              role="menuitemradio"
              aria-checked={value === mode}
              aria-label={mode}
              disabled={disabled}
              ref={(element) => {
                options.current[index] = element;
              }}
              onClick={() => {
                onChange(mode);
                setOpen(false);
                trigger.current?.focus();
              }}
              onKeyDown={(event) => {
                let next = index;
                if (event.key === "ArrowDown")
                  next = (index + 1) % MODES.length;
                else if (event.key === "ArrowUp")
                  next = (index + MODES.length - 1) % MODES.length;
                else if (event.key === "Home") next = 0;
                else if (event.key === "End") next = MODES.length - 1;
                else return;
                event.preventDefault();
                options.current[next]?.focus();
              }}
            >
              <span className="mode-option-title">
                {mode}
                <span aria-hidden="true">{value === mode ? "✓" : ""}</span>
              </span>
              <small>{MODE_DESCRIPTIONS[mode]}</small>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
