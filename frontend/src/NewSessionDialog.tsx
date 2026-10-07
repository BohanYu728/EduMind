import { useEffect, useRef, useState } from "react";

export default function NewSessionDialog({
  onCreate,
  onClose,
  initialName = "",
  editing = false,
}: {
  onCreate: (name: string) => void;
  onClose: () => void;
  initialName?: string;
  editing?: boolean;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [name, setName] = useState(initialName);
  useEffect(() => {
    const dialog = dialogRef.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);

  return (
    <dialog
      ref={dialogRef}
      className="new-session-dialog"
      aria-labelledby="new-session-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (name.trim()) onCreate(name.trim());
        }}
      >
        <h2 id="new-session-title">{editing ? "重命名备课" : "新建备课"}</h2>
        <p>
          {editing
            ? "修改名称，已有对话和资料会保留。"
            : "给这次备课取个名字，方便以后查找。"}
        </p>
        <label htmlFor="session-name">会话名称</label>
        <input
          id="session-name"
          autoFocus
          required
          maxLength={40}
          placeholder="例如：七年级 · 一元一次方程"
          value={name}
          onFocus={(event) => event.currentTarget.select()}
          onChange={(event) => setName(event.target.value)}
        />
        <div className="new-session-actions">
          <button type="button" onClick={onClose}>
            取消
          </button>
          <button type="submit" disabled={!name.trim()}>
            {editing ? "保存名称" : "创建会话"}
          </button>
        </div>
      </form>
    </dialog>
  );
}
