import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  conversationKey,
  createConversation,
  streamAnswer,
  useSessionConversation,
  type Conversation,
  type DoneEvent,
  type StreamSource,
  type TutorMode,
} from "./api";
import { liveSources, turnsFromMessages, type AnswerStatus, type Turn } from "./turns";

/** The turn being asked right now, shown until the stored copy comes back from the API. */
type Live = {
  question: string;
  mode: TutorMode;
  /** How many stored messages there were when it was sent. */
  base: number;
  sources: StreamSource[];
  text: string;
  status: AnswerStatus;
  done: DoneEvent | null;
  error: string | null;
  retryAt: string | null;
};

const LOST = "The connection to the tutor was lost before the answer finished.";

/**
 * The tutor for one study session: its conversation (created on the first question, and
 * found again after a reload), the turns so far, and the answer streaming now.
 */
export function useTutor({
  moduleId,
  sessionId,
  topicId,
}: {
  moduleId: string;
  /** The study session's server ID; null until the session has reached the server. */
  sessionId: string | null;
  topicId: string | null;
}) {
  const queryClient = useQueryClient();
  const key = conversationKey(moduleId, sessionId);
  const conversation = useSessionConversation(moduleId, sessionId);
  const [live, setLive] = useState<Live | null>(null);
  const abort = useRef<AbortController | null>(null);
  const stored = conversation.data?.messages ?? [];

  // Once the API has stored both the question and its answer, the stored copy shows. A
  // failed answer stays as it was seen, with its reason and retry time (the stored copy
  // only knows it failed), until the next question.
  const shown =
    live && (isActive(live.status) || live.status === "failed" || stored.length < live.base + 2)
      ? live
      : null;

  // Leaving the session (or the page) stops an answer still streaming.
  useEffect(() => () => abort.current?.abort(), []);

  const refetch = useCallback(
    () => queryClient.invalidateQueries({ queryKey: key }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [queryClient, moduleId, sessionId],
  );

  const send = useCallback(
    async (question: string, mode: TutorMode = "answer") => {
      const text = question.trim();
      if (!text || sessionId === null || (live && isActive(live.status))) return;
      const controller = new AbortController();
      abort.current = controller;
      const base = conversation.data?.messages.length ?? 0;
      const update = (change: Partial<Live>) =>
        setLive((now) => (now ? { ...now, ...change } : now));
      setLive({
        question: text,
        mode,
        base,
        sources: [],
        text: "",
        status: "waiting",
        done: null,
        error: null,
        retryAt: null,
      });
      let answer = "";
      let ended = false;
      try {
        let current: Conversation | null = conversation.data ?? null;
        if (current === null) {
          current = await createConversation(moduleId, {
            study_session_id: sessionId,
            topic_id: topicId,
          });
          queryClient.setQueryData(key, current);
        }
        for await (const event of streamAnswer(
          current.id,
          { question: text, mode },
          controller.signal,
        )) {
          if (event.type === "sources") update({ sources: event.sources });
          else if (event.type === "delta") {
            answer += event.text;
            update({ text: answer, status: "streaming" });
          } else if (event.type === "done") {
            ended = true;
            update({ status: event.done.status, done: event.done });
          } else {
            ended = true;
            update({
              status: "failed",
              error: event.error.message,
              retryAt: event.error.retry_at ?? null,
            });
          }
        }
        if (!ended) update({ status: "failed", error: LOST });
      } catch (error) {
        if (controller.signal.aborted) update({ status: "stopped" });
        else update({ status: "failed", error: (error as Error).message || LOST });
      } finally {
        abort.current = null;
        await refetch();
        if (controller.signal.aborted) {
          // The API stores a stopped answer once it notices the client left: look again.
          setTimeout(() => void refetch(), 1500);
        }
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [conversation.data, live, moduleId, sessionId, topicId, queryClient, refetch],
  );

  const stop = useCallback(() => abort.current?.abort(), []);

  const turns: Turn[] = turnsFromMessages(shown ? stored.slice(0, shown.base) : stored);
  if (shown) {
    const live = shown;
    turns.push({
      key: "live",
      question: live.question,
      mode: live.mode,
      answer: {
        text: live.text,
        status: live.status,
        sources: liveSources(live.sources, live.text, live.done?.cited),
        model: live.done?.model ?? null,
        firstTokenMs: live.done?.first_token_ms ?? null,
        error: live.error,
        retryAt: live.retryAt,
      },
    });
  }

  return {
    turns,
    /** Loading the session's earlier conversation (after a reload). */
    restoring: conversation.isPending && sessionId !== null,
    loadError: conversation.isError ? conversation.error.message : null,
    busy: live !== null && isActive(live.status),
    ready: sessionId !== null,
    send,
    stop,
  };
}

function isActive(status: AnswerStatus) {
  return status === "waiting" || status === "streaming";
}
