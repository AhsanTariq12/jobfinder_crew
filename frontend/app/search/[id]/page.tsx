"use client";

import { useEffect, useState, useRef } from "react";
import { useRouter, useParams } from "next/navigation";

const STAGES = [
  { key: "queued",    label: "Waiting to start"           },
  { key: "running",   label: "Searching & analyzing jobs" },
  { key: "complete",  label: "Results ready"              },
];

const MESSAGES: Record<string, string[]> = {
  queued: [
    "Getting ready...",
    "Preparing your search...",
  ],
  running: [
    "Searching job boards...",
    "Analyzing job descriptions...",
    "Identifying required skills...",
    "Building your prep roadmap...",
    "Almost there...",
    "Wrapping up analysis...",
  ],
};

export default function ProgressPage() {
  const params = useParams();
  const id     = params.id as string;
  const router = useRouter();

  const [status,       setStatus]       = useState("queued");
  const [messageIndex, setMessageIndex] = useState(0);
  const [error,        setError]        = useState<string | null>(null);
  const [elapsed,      setElapsed]      = useState(0);

  const statusRef      = useRef("queued");
  const intervalRef    = useRef<NodeJS.Timeout | null>(null);
  const msgIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const elapsedRef     = useRef<NodeJS.Timeout | null>(null);
  const notFoundCount  = useRef(0); // track consecutive not_found

  useEffect(() => {
    if (!id || id === "undefined") return;

    const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

    const cleanup = () => {
      if (intervalRef.current)    clearInterval(intervalRef.current);
      if (msgIntervalRef.current) clearInterval(msgIntervalRef.current);
      if (elapsedRef.current)     clearInterval(elapsedRef.current);
    };

    const poll = async () => {
      try {
        const res  = await fetch(`${API_URL}/api/status/${id}`);
        const data = await res.json();

        if (data.status === "not_found") {
          // Keep polling — worker might not have inserted the row yet
          // Only error out after 10 consecutive not_found (~30 seconds)
          notFoundCount.current += 1;
          if (notFoundCount.current > 10) {
            cleanup();
            setError("Search could not be found. Please try again.");
          }
          return;
        }

        // Reset counter once we find the row
        notFoundCount.current = 0;

        setStatus(data.status);
        statusRef.current = data.status;

        if (data.status === "complete") {
          cleanup();
          setTimeout(() => router.push(`/results/${id}`), 1000);
        }

        if (data.status === "error") {
          cleanup();
          setError("Something went wrong. Please try again.");
        }

      } catch (e) {
        console.error("Poll error:", e);
      }
    };

    const rotateMessages = () => {
      setMessageIndex(i => {
        const messages = MESSAGES[statusRef.current] || MESSAGES.running;
        return (i + 1) % messages.length;
      });
    };

    const tickElapsed = () => setElapsed(s => s + 1);

    poll();
    intervalRef.current    = setInterval(poll,           3000);
    msgIntervalRef.current = setInterval(rotateMessages, 8000);
    elapsedRef.current     = setInterval(tickElapsed,    1000);

    return cleanup;
  }, [id]);

  const currentMessages = MESSAGES[status] || MESSAGES.running;
  const currentMessage  = currentMessages[messageIndex % currentMessages.length];

  const formatElapsed = (s: number) => {
    const m   = Math.floor(s / 60);
    const sec = s % 60;
    return m > 0 ? `${m}m ${sec}s` : `${sec}s`;
  };

  return (
    <main className="min-h-screen flex flex-col items-center justify-center p-8">
      <h2 className="text-2xl font-semibold mb-2">Finding your opportunities...</h2>
      <p className="text-gray-400 text-sm mb-10">
        This usually takes 2–5 minutes
      </p>

      {error ? (
        <div className="text-center space-y-4">
          <p className="text-red-500">{error}</p>
          <button
            onClick={() => router.push("/")}
            className="text-blue-600 underline text-sm"
          >
            Try again
          </button>
        </div>
      ) : (
        <div className="w-full max-w-sm space-y-6">

          <div className="space-y-4">
            {STAGES.map((stage, i) => {
              const stageIndex = STAGES.findIndex(s => s.key === status);
              const isComplete = i < stageIndex;
              const isCurrent  = stage.key === status;

              return (
                <div key={stage.key} className="flex items-center gap-3">
                  <div className={`w-7 h-7 rounded-full flex items-center justify-center text-sm font-medium shrink-0
                    ${isComplete ? "bg-green-500 text-white" :
                      isCurrent  ? "bg-blue-500 text-white animate-pulse" :
                                   "bg-gray-100 text-gray-400"}`}>
                    {isComplete ? "✓" : i + 1}
                  </div>
                  <span className={
                    isComplete ? "text-gray-400 line-through text-sm" :
                    isCurrent  ? "font-medium text-blue-500 text-sm" :
                                 "text-gray-400 text-sm"
                  }>
                    {stage.label}
                  </span>
                </div>
              );
            })}
          </div>

          <div className="text-center pt-2">
            <p className="text-sm text-gray-500 animate-pulse">
              {currentMessage}
            </p>
            <p className="text-xs text-gray-300 mt-2">
              {formatElapsed(elapsed)} elapsed
            </p>
          </div>

        </div>
      )}
    </main>
  );
}