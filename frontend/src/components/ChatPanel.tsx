// Left-side Q&A chat panel. Each assistant answer can carry a navigation target;
// clicking it re-flies the camera. The actual fly-to is triggered by the parent
// when an answer arrives.
import { useEffect, useRef, useState } from "react";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  navNodeId?: string | null;
  navLabel?: string | null;
}

interface Props {
  visible: boolean;
  messages: ChatMessage[];
  thinking: boolean;
  onSend: (q: string) => void;
  onNavClick: (nodeId: string) => void;
  onClose: () => void;
}

export function ChatPanel({ visible, messages, thinking, onSend, onNavClick, onClose }: Props) {
  const [input, setInput] = useState("");
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, thinking]);

  if (!visible) return null;

  const submit = () => {
    const q = input.trim();
    if (!q || thinking) return;
    onSend(q);
    setInput("");
  };

  return (
    <div className="chat panel">
      <div className="chat-head">
        <span className="glow-dot" />
        <div>
          <div className="chat-head-title">Ask the guide</div>
          <div className="chat-head-sub">I’ll fly you to the answer</div>
        </div>
        <button className="btn icon" style={{ marginLeft: "auto" }} onClick={onClose}>✕</button>
      </div>

      <div className="chat-log" ref={logRef}>
        {messages.length === 0 && (
          <div className="msg assistant">
            <div className="msg-bubble">
              Ask me anything about this codebase — “how does X work?”, “where is Y handled?” —
              and I’ll glide the map to the exact spot and explain it.
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <div className="msg-bubble">{m.content}</div>
            {m.role === "assistant" && m.navNodeId && (
              <span className="msg-nav" onClick={() => onNavClick(m.navNodeId!)}>
                ↳ fly to {m.navLabel}
              </span>
            )}
          </div>
        ))}
        {thinking && (
          <div className="msg assistant">
            <div className="msg-bubble">
              <div className="thinking"><span /><span /><span /></div>
            </div>
          </div>
        )}
      </div>

      <div className="chat-input-row">
        <input
          className="chat-input"
          placeholder="Ask about this codebase…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
        />
        <button className="btn primary icon" onClick={submit} disabled={thinking}>➤</button>
      </div>
    </div>
  );
}
