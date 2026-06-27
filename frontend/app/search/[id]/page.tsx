"use client";

import { useEffect, useState, useRef } from "react";
import { useRouter, useParams } from "next/navigation";

const STAGES = [
  { key: "started",   label: "Connecting to search engine"  },
  { key: "searching", label: "Searching job boards"         },
  { key: "analyzing", label: "Analyzing job descriptions"   },
  { key: "skills",    label: "Identifying required skills"  },
  { key: "planning",  label: "Building preparation plan"    },
  { key: "complete",  label: "Results ready"                },
];

export default function ProgressPage() {
  const params = useParams();
  const id = params.id as string;
  const router = useRouter();

  const [currentStage, setCurrentStage] = useState("started");
  const [message, setMessage]           = useState("Connecting...");
  const [error, setError]               = useState<string | null>(null);

  // Ref tracks stage without closure staleness
  const stageRef = useRef("started");

  useEffect(() => {
    const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const es = new EventSource(`${API_URL}/api/stream/${id}`);

    es.onmessage = (event) => {
      const data = JSON.parse(event.data);

      setCurrentStage(data.stage);
      setMessage(data.message);
      stageRef.current = data.stage;   // keep ref in sync

   // In ProgressPage, update the complete handler
if (data.stage === "complete") {
  es.close();
  if (id && id !== "undefined") {
    setTimeout(() => router.push(`/results/${id}`), 1500);
  } else {
    setError("Invalid search ID. Please try again.");
  }
}
      if (data.stage === "error" || data.stage === "no_jobs_found") {
        es.close();
        setError(data.message);
      }
    };

    es.onerror = () => {
      es.close();
      // Only show error if we never completed successfully
      if (stageRef.current !== "complete") {
        setError("Connection lost. Please check if the server is running.");
      }
    };

    return () => es.close();
  }, [id]);

  const completedIndex = STAGES.findIndex(s => s.key === currentStage);

  return (
    <main className="min-h-screen flex flex-col items-center justify-center p-8">
      <h2 className="text-2xl font-semibold mb-8">Finding your opportunities...</h2>

      {error ? (
        <div className="text-center">
          <p className="text-red-500 mb-4">{error}</p>
          <button
            onClick={() => router.push("/")}
            className="text-blue-600 underline"
          >
            Try again
          </button>
        </div>
      ) : (
        <div className="w-full max-w-sm space-y-4">
          {STAGES.map((stage, i) => (
            <div key={stage.key} className="flex items-center gap-3">
              <div className={`w-6 h-6 rounded-full flex items-center justify-center text-sm font-medium
                ${i < completedIndex  ? "bg-green-500 text-white" :
                  i === completedIndex ? "bg-blue-500 text-white animate-pulse" :
                                         "bg-gray-200 text-gray-400"}`}>
                {i < completedIndex ? "✓" : i + 1}
              </div>
              <span className={
                i < completedIndex  ? "text-gray-400 line-through" :
                i === completedIndex ? "font-medium text-blue-500" :
                                       "text-gray-400"
              }>
                {stage.label}
              </span>
            </div>
          ))}
          <p className="text-sm text-gray-400 mt-6 text-center">{message}</p>
        </div>
      )}
    </main>
  );
}