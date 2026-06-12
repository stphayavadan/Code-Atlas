// Narration voice via the browser's Web Speech API (free, no key).
// Picks a pleasant English voice when available and exposes simple controls.
import { useCallback, useEffect, useRef, useState } from "react";

// Voices we prefer, in order, when present on the system.
const PREFERRED = [
  "Google UK English Female",
  "Microsoft Aria Online",
  "Microsoft Jenny",
  "Samantha",
  "Google US English",
];

// Character span of the word currently being spoken (for karaoke highlight).
export interface SpeakMark { start: number; end: number; }

export function useSpeech() {
  const [enabled, setEnabled] = useState(true);
  const [speaking, setSpeaking] = useState(false);
  // Which word is being spoken right now, as a [start, end) char range in the
  // utterance text. null when not speaking.
  const [mark, setMark] = useState<SpeakMark | null>(null);
  const voiceRef = useRef<SpeechSynthesisVoice | null>(null);

  useEffect(() => {
    const synth = window.speechSynthesis;
    if (!synth) return;
    const pick = () => {
      const voices = synth.getVoices();
      if (!voices.length) return;
      for (const name of PREFERRED) {
        const v = voices.find((x) => x.name === name);
        if (v) {
          voiceRef.current = v;
          return;
        }
      }
      voiceRef.current =
        voices.find((v) => v.lang.startsWith("en") && /female|aria|jenny|samantha/i.test(v.name)) ??
        voices.find((v) => v.lang.startsWith("en")) ??
        voices[0];
    };
    pick();
    synth.onvoiceschanged = pick;
    return () => {
      synth.onvoiceschanged = null;
    };
  }, []);

  const stop = useCallback(() => {
    window.speechSynthesis?.cancel();
    setSpeaking(false);
    setMark(null);
  }, []);

  const speak = useCallback(
    (text: string, onEnd?: () => void) => {
      const synth = window.speechSynthesis;
      if (!synth || !enabled || !text) {
        onEnd?.();
        return;
      }
      synth.cancel();
      const u = new SpeechSynthesisUtterance(text);
      if (voiceRef.current) u.voice = voiceRef.current;
      u.rate = 1.0;
      u.pitch = 1.0;
      u.onstart = () => { setSpeaking(true); setMark(null); };
      // Fired at each word boundary: highlight the word at charIndex.
      u.onboundary = (e: SpeechSynthesisEvent) => {
        if (e.name && e.name !== "word") return;
        const start = e.charIndex ?? 0;
        // charLength is unreliable across engines; derive the word end ourselves.
        let end = start + (e.charLength ?? 0);
        if (!e.charLength) {
          const m = /\S+/.exec(text.slice(start));
          end = m ? start + m[0].length : start;
        }
        setMark({ start, end });
      };
      u.onend = () => {
        setSpeaking(false);
        setMark(null);
        onEnd?.();
      };
      u.onerror = () => {
        setSpeaking(false);
        setMark(null);
        onEnd?.();
      };
      synth.speak(u);
    },
    [enabled]
  );

  const toggleEnabled = useCallback(() => {
    setEnabled((e) => {
      if (e) window.speechSynthesis?.cancel();
      return !e;
    });
  }, []);

  return { speak, stop, speaking, mark, enabled, toggleEnabled };
}
