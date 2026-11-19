import { Mic, Volume2, VolumeX } from "lucide-react";
import type { PointerEvent } from "react";

import { cn } from "@/lib/utils";
import { Button } from "@/ui/button";

import { PUSH_TO_TALK, type useVoice } from "./useVoice";

type Voice = ReturnType<typeof useVoice>;

/**
 * Push-to-talk: press and hold (mouse, touch or pen), release to send. Only shown when
 * this device can recognise speech on its own (decision 0015).
 */
export function MicButton({ voice, disabled }: { voice: Voice; disabled: boolean }) {
  if (voice.mic !== "available") return null;
  function down(event: PointerEvent<HTMLButtonElement>) {
    if (event.button !== 0 || disabled) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture?.(event.pointerId);
    voice.start();
  }
  function up() {
    void voice.release();
  }
  return (
    <Button
      type="button"
      variant={voice.listening ? "default" : "outline"}
      size="icon"
      disabled={disabled && !voice.listening}
      aria-pressed={voice.listening}
      aria-keyshortcuts="Space"
      {...{ [PUSH_TO_TALK]: "" }}
      onPointerDown={down}
      onPointerUp={up}
      onPointerCancel={up}
      onContextMenu={(event) => event.preventDefault()}
      className={cn("touch-none select-none", voice.listening && "ring-ring/40 ring-4")}
    >
      <Mic aria-hidden />
      <span className="sr-only">Hold to talk (or hold Space)</span>
    </Button>
  );
}

/**
 * Above the input: "Listening…" with the words so far, voice set-up or why there's no
 * voice, and the Read aloud toggle.
 */
export function VoiceStatus({ voice }: { voice: Voice }) {
  return (
    <>
      {voice.listening && (
        <p role="status" className="text-fg flex items-baseline gap-2 px-2 pt-1 text-sm">
          <span className="text-link shrink-0 font-medium">Listening…</span>
          <span className="text-muted min-w-0 truncate">
            {voice.interim || "release to send, Esc to cancel"}
          </span>
        </p>
      )}
      {voice.error && !voice.listening && (
        <p role="alert" className="text-danger px-2 pt-1 text-xs">
          {voice.error}
        </p>
      )}
      <div className="text-muted flex flex-wrap items-center gap-x-3 gap-y-1 px-2 text-xs">
        <MicNote voice={voice} />
        {voice.canSpeak ? (
          <>
            <button
              type="button"
              role="switch"
              aria-checked={voice.readAloud}
              onClick={() => voice.setReadAloud(!voice.readAloud)}
              className="hover:text-fg inline-flex min-h-7 cursor-pointer items-center gap-1.5 rounded-md"
            >
              {voice.readAloud ? (
                <Volume2 aria-hidden className="text-link size-3.5" />
              ) : (
                <VolumeX aria-hidden className="size-3.5" />
              )}
              Read aloud {voice.readAloud ? "on" : "off"}
            </button>
            {voice.speaking && (
              <button
                type="button"
                onClick={voice.stopSpeaking}
                className="text-link inline-flex min-h-7 cursor-pointer items-center rounded-md font-medium"
              >
                Stop reading
              </button>
            )}
          </>
        ) : (
          voice.voicesChecked && <span>This device has no voice of its own to read answers.</span>
        )}
      </div>
    </>
  );
}

function MicNote({ voice }: { voice: Voice }) {
  switch (voice.mic) {
    case "available":
      return <span>Hold the mic (or Space) to ask by voice.</span>;
    case "downloadable":
      return (
        <Button variant="quiet" size="sm" onClick={() => void voice.install()}>
          <Mic aria-hidden />
          Set up voice (downloads a speech pack to this device)
        </Button>
      );
    case "installing":
      return (
        <span role="status" aria-busy="true" className="inline-flex items-center gap-2">
          <span aria-hidden className="answer-caret" />
          Downloading the speech pack to this device…
        </span>
      );
    case "install-failed":
      return (
        <span role="alert" className="inline-flex flex-wrap items-center gap-2">
          <span className="text-danger">The speech pack didn't download.</span>
          <Button variant="quiet" size="sm" onClick={() => void voice.install()}>
            Try again
          </Button>
        </span>
      );
    case "unavailable":
      return (
        <span>
          This browser can't recognise speech on the device, so voice is off. Typing works.
        </span>
      );
    default:
      return null;
  }
}
