import { Keyboard, X } from "lucide-react";

export function ShortcutsModal({ onClose }: { onClose: () => void }) {
  const shortcuts = [
    { key: "Space", description: "Play or pause the preview video" },
    { key: "1 – 6", description: "Jump directly to tab (Overview, Story, Cast, Shots, Episodes, Export)" },
    { key: "[ and ]", description: "Previous or next episode in a series" },
    { key: "Arrow keys", description: "Navigate between tabs or controls" },
    { key: "?", description: "Toggle this keyboard shortcuts guide" },
    { key: "Esc", description: "Close this window" },
  ];

  return (
    <div
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="shortcuts-heading"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal-content shortcuts-modal">
        <div className="modal-header">
          <div className="modal-title-row">
            <Keyboard size={20} />
            <h2 id="shortcuts-heading">Keyboard Shortcuts</h2>
          </div>
          <button
            className="icon-button"
            onClick={onClose}
            aria-label="Close keyboard shortcuts"
          >
            <X size={18} />
          </button>
        </div>

        <p className="muted">
          Fast, accessible navigation for creative filmmaking. Shortcuts are active
          whenever you are not typing in a text field.
        </p>

        <ul className="shortcuts-list" role="list">
          {shortcuts.map(({ key, description }) => (
            <li key={key} className="shortcut-row">
              <kbd className="shortcut-key">{key}</kbd>
              <span className="shortcut-desc">{description}</span>
            </li>
          ))}
        </ul>

        <div className="modal-footer">
          <button className="primary" onClick={onClose}>
            Got it
          </button>
        </div>
      </div>
    </div>
  );
}
