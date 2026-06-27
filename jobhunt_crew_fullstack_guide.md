# JobHunt Crew — Full-Stack Web App Development Guide

> Production-grade architecture for wrapping your CrewAI multi-agent pipeline in a Next.js web application.

---

## Quick orientation

Your CrewAI project runs a 4-crew pipeline:

1. **SearchCrew** — `job_researcher` agent uses SerperDev + ScrapeWebsite to find 5 jobs → returns `Job_Search_List` (Pydantic)
2. **AnalysisCrew** — `job_analyst` runs *in parallel* across all 5 jobs via `asyncio.gather`
3. **SkillsCrew** — `skills_advisor` reads the consolidated analysis report → outputs a categorized skills list
4. **PrepCrew** — `preparation_planner` reads both reports → outputs the final interview guide

The full pipeline takes **2–8 minutes** to complete (LLM calls, web scraping). This has major architectural implications — the web app *cannot* behave like a normal request/response API. You need a job queue.

---

## Part 1 — Choosing your tech stack

### On Next.js for the frontend

Your instinct is correct. Next.js is an excellent choice — not just because it looks modern, but for concrete reasons:

- **React Server Components** let you stream AI output to the browser as it arrives, with zero extra effort.
- **App Router** gives you file-based API routes so your backend lives in the same repo.
- **TypeScript-first** — catches bugs before they cost you debugging time.
- **Vercel deployment** is near-zero config for Next.js apps.

The "modern look" you mentioned comes from the ecosystem around it: shadcn/ui components, Tailwind CSS, and Framer Motion — these are the actual tools that produce the aesthetic, not Next.js itself. But Next.js is the right foundation.

### Recommended full stack

| Layer | Technology | Why |
|---|---|---|
| Frontend | Next.js 14+ (App Router) | SSR, streaming, file-based routing |
| Styling | Tailwind CSS + shadcn/ui | Fast, consistent, professional |
| Backend API | FastAPI (Python) | Async-native, perfect for CrewAI |
| Job Queue | Redis + Celery (or RQ) | Handles 2–8 min long-running tasks |
| Database | PostgreSQL + Prisma | Stores job results, user history |
| Real-time updates | Server-Sent Events (SSE) | Streams progress to frontend |
| Auth | NextAuth.js | GitHub/Google login in minutes |
| Deployment | Vercel (frontend) + Railway/Render (backend) | Free tier friendly |

### Why FastAPI, not Next.js API routes, for the AI backend?

Your CrewAI code is Python. You cannot run Python inside Next.js API routes. You have two choices:

1. **FastAPI microservice** (recommended) — Python backend that Next.js calls. Clean separation.
2. **Next.js → subprocess** — spawning Python from Node.js. Messy, hard to scale.

Always go with option 1.

---

## Part 2 — System architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     USER'S BROWSER                          │
│  Next.js App (Vercel)                                       │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐   │
│  │  Search Form │  │ Progress UI  │  │  Results Page   │   │
│  └──────┬───────┘  └──────┬───────┘  └────────┬────────┘   │
└─────────┼─────────────────┼───────────────────┼────────────┘
          │ POST /search     │ SSE /stream/{id}  │ GET /results/{id}
          ▼                  ▼                   ▼
┌─────────────────────────────────────────────────────────────┐
│                  FastAPI Backend (Railway)                   │
│                                                             │
│  /api/search  →  enqueue task  →  return { job_id }        │
│  /api/stream/{id}  →  SSE endpoint reading Redis pub/sub   │
│  /api/results/{id}  →  fetch from PostgreSQL               │
└─────────────┬───────────────────────────────┬──────────────┘
              │                               │
              ▼                               ▼
┌─────────────────────┐           ┌───────────────────────┐
│  Redis              │           │  PostgreSQL            │
│  - Task queue       │           │  - searches table      │
│  - Progress pub/sub │           │  - results table       │
│  - Cached results   │           │  - users table         │
└──────────┬──────────┘           └───────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────┐
│                   Celery Worker Process                     │
│                                                             │
│  Picks up task → runs JobFinderFlow → publishes progress   │
│  via Redis → saves final result to PostgreSQL              │
└─────────────────────────────────────────────────────────────┘
```

### The critical design decision — async job processing

When a user submits a search:

1. Frontend sends `POST /api/search` with `{ job_role, location, job_type, company }`
2. FastAPI creates a task in Redis and immediately returns `{ job_id: "abc123" }`
3. Frontend opens an SSE connection to `/api/stream/abc123`
4. A Celery worker picks up the task and runs your `JobFinderFlow`
5. As each crew completes, the worker publishes progress events to Redis
6. The SSE endpoint reads those events and forwards them to the browser in real-time
7. When done, results are saved to PostgreSQL and a final event is sent
8. Frontend navigates to `/results/abc123` to display the full output

This pattern is called the **polling with SSE** pattern, and it's the standard way to handle long-running AI tasks in production.

---

## Part 3 — Project structure

```
jobhunt-crew/
│
├── frontend/                        # Next.js app
│   ├── app/
│   │   ├── page.tsx                 # Landing page with search form
│   │   ├── search/[id]/
│   │   │   └── page.tsx             # Progress tracking page
│   │   ├── results/[id]/
│   │   │   └── page.tsx             # Final results display
│   │   └── api/
│   │       └── proxy/               # Optional: proxy to FastAPI
│   ├── components/
│   │   ├── SearchForm.tsx
│   │   ├── ProgressTracker.tsx
│   │   ├── JobCard.tsx
│   │   ├── SkillsReport.tsx
│   │   └── PrepGuide.tsx
│   ├── lib/
│   │   └── api.ts                   # API client functions
│   └── package.json
│
├── backend/                         # FastAPI + Celery
│   ├── main.py                      # FastAPI app
│   ├── tasks.py                     # Celery task definitions
│   ├── models.py                    # SQLAlchemy/Pydantic models
│   ├── database.py                  # DB connection
│   ├── worker.py                    # Celery worker entry point
│   └── requirements.txt
│
├── crew/                            # Your existing CrewAI code
│   └── src/
│       └── job_finder_crew/
│           ├── main.py              # Modified to accept callbacks
│           ├── crew.py
│           └── config/
│
└── docker-compose.yml               # Redis + Postgres for local dev
```

---

## Part 4 — Backend implementation

### Step 4.1 — Modify your flow to emit progress events

Add a `progress_callback` to `JobFinderFlow` so the Celery worker can forward updates to Redis:

```python
# crew/src/job_finder_crew/main.py

class JobFinderFlow(Flow[JobFinderState]):

    def __init__(self, progress_callback=None):
        super().__init__()
        self._progress = progress_callback or (lambda msg: None)

    @start()
    def initialize_and_search(self):
        self._progress({"stage": "searching", "message": "Searching for jobs..."})
        # ... rest of your existing code unchanged

    @listen("jobs_exist")
    async def analyze_jobs_parallel(self):
        self._progress({
            "stage": "analyzing",
            "message": f"Analyzing {len(self.state.jobs_list)} jobs in parallel..."
        })
        # ... rest of your existing code unchanged

    @listen(analyze_jobs_parallel)
    def identify_skills_and_plan(self):
        self._progress({"stage": "skills", "message": "Identifying required skills..."})
        # ...
        self._progress({"stage": "planning", "message": "Building your prep roadmap..."})
        # ... rest of your existing code unchanged
```

### Step 4.2 — FastAPI application

```python
# backend/main.py

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as aioredis
import json
import asyncio
from uuid import uuid4
from .tasks import run_job_search
from .models import SearchRequest, SearchResponse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://yourapp.vercel.app"],
    allow_methods=["*"],
    allow_headers=["*"],
)

redis_client = aioredis.from_url("redis://localhost:6379")

@app.post("/api/search", response_model=SearchResponse)
async def create_search(request: SearchRequest):
    job_id = str(uuid4())

    # Enqueue the Celery task
    run_job_search.apply_async(
        kwargs={
            "job_id": job_id,
            "job_role": request.job_role,
            "location": request.location,
            "job_type": request.job_type,
            "company": request.company or "Not Provided",
        },
        task_id=job_id
    )

    return {"job_id": job_id, "status": "queued"}


@app.get("/api/stream/{job_id}")
async def stream_progress(job_id: str):
    async def event_generator():
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(f"progress:{job_id}")

        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = message["data"]
                    yield f"data: {data}\n\n"

                    parsed = json.loads(data)
                    if parsed.get("stage") in ("complete", "error", "no_jobs_found"):
                        break
        finally:
            await pubsub.unsubscribe(f"progress:{job_id}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@app.get("/api/results/{job_id}")
async def get_results(job_id: str):
    # Fetch from PostgreSQL (implement with SQLAlchemy)
    result = await fetch_result_from_db(job_id)
    if not result:
        return {"status": "not_found"}
    return result
```

### Step 4.3 — Celery task

```python
# backend/tasks.py

from celery import Celery
import redis
import json
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../crew/src"))
from job_finder_crew.main import JobFinderFlow, JobFinderState

celery_app = Celery("jobhunt", broker="redis://localhost:6379/0")
redis_client = redis.Redis(host="localhost", port=6379, db=0)

@celery_app.task(bind=True)
def run_job_search(self, job_id: str, job_role: str, location: str,
                   job_type: str, company: str):

    def publish_progress(data: dict):
        data["job_id"] = job_id
        redis_client.publish(f"progress:{job_id}", json.dumps(data))

    try:
        publish_progress({"stage": "started", "message": "Starting your job search..."})

        flow = JobFinderFlow(progress_callback=publish_progress)

        result = asyncio.run(flow.kickoff_async(inputs={
            "job_role": job_role,
            "location": location,
            "job_type": job_type,
            "company": company,
        }))

        # Save to PostgreSQL here
        save_result_to_db(job_id, {
            "jobs_list": [j.dict() for j in flow.state.jobs_list],
            "analysis_report": flow.state.analysis_report,
            "skills_report": flow.state.skills_report,
            "prep_guide": flow.state.prep_guide,
        })

        publish_progress({
            "stage": "complete",
            "message": "Done! Your results are ready.",
        })

    except Exception as e:
        publish_progress({
            "stage": "error",
            "message": f"Something went wrong: {str(e)}"
        })
        raise
```

---

## Part 5 — Frontend implementation

### Step 5.1 — Search form (Landing page)

```tsx
// frontend/app/page.tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function HomePage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    job_role: "",
    location: "United States of America",
    job_type: "Remote",
    company: "",
  });

  async function handleSubmit() {
    setLoading(true);
    const res = await fetch("http://localhost:8000/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(form),
    });
    const data = await res.json();
    router.push(`/search/${data.job_id}`);
  }

  return (
    <main className="min-h-screen flex flex-col items-center justify-center p-8">
      <h1 className="text-4xl font-bold mb-2">JobHunt Crew</h1>
      <p className="text-gray-500 mb-8">AI-powered job research & interview prep</p>

      <div className="w-full max-w-md space-y-4">
        <input
          className="w-full border rounded-lg p-3"
          placeholder="Job role (e.g. Full Stack Developer)"
          value={form.job_role}
          onChange={e => setForm(f => ({ ...f, job_role: e.target.value }))}
        />
        <input
          className="w-full border rounded-lg p-3"
          placeholder="Location"
          value={form.location}
          onChange={e => setForm(f => ({ ...f, location: e.target.value }))}
        />
        <select
          className="w-full border rounded-lg p-3"
          value={form.job_type}
          onChange={e => setForm(f => ({ ...f, job_type: e.target.value }))}
        >
          <option>Remote</option>
          <option>Hybrid</option>
          <option>On-site</option>
        </select>
        <input
          className="w-full border rounded-lg p-3"
          placeholder="Company (optional)"
          value={form.company}
          onChange={e => setForm(f => ({ ...f, company: e.target.value }))}
        />
        <button
          onClick={handleSubmit}
          disabled={!form.job_role || loading}
          className="w-full bg-blue-600 text-white rounded-lg p-3 font-medium
                     hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? "Starting search..." : "Find Jobs & Prepare"}
        </button>
      </div>
    </main>
  );
}
```

### Step 5.2 — Progress tracking page (SSE consumer)

```tsx
// frontend/app/search/[id]/page.tsx
"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";

const STAGES = [
  { key: "searching",  label: "Searching job boards"        },
  { key: "analyzing",  label: "Analyzing job descriptions"  },
  { key: "skills",     label: "Identifying required skills" },
  { key: "planning",   label: "Building preparation plan"   },
  { key: "complete",   label: "Results ready"               },
];

export default function ProgressPage() {
  const { id } = useParams();
  const router = useRouter();
  const [currentStage, setCurrentStage] = useState("searching");
  const [message, setMessage] = useState("Connecting...");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const es = new EventSource(`http://localhost:8000/api/stream/${id}`);

    es.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setCurrentStage(data.stage);
      setMessage(data.message);

      if (data.stage === "complete") {
        es.close();
        router.push(`/results/${id}`);
      }
      if (data.stage === "error") {
        es.close();
        setError(data.message);
      }
    };

    es.onerror = () => {
      setError("Connection lost. Please try again.");
      es.close();
    };

    return () => es.close();
  }, [id]);

  const completedIndex = STAGES.findIndex(s => s.key === currentStage);

  return (
    <main className="min-h-screen flex flex-col items-center justify-center p-8">
      <h2 className="text-2xl font-semibold mb-8">Finding your opportunities...</h2>

      {error ? (
        <p className="text-red-500">{error}</p>
      ) : (
        <div className="w-full max-w-sm space-y-4">
          {STAGES.map((stage, i) => (
            <div key={stage.key} className="flex items-center gap-3">
              <div className={`w-6 h-6 rounded-full flex items-center justify-center text-sm
                ${i < completedIndex  ? "bg-green-500 text-white" :
                  i === completedIndex ? "bg-blue-500 text-white animate-pulse" :
                                         "bg-gray-200 text-gray-400"}`}>
                {i < completedIndex ? "✓" : i + 1}
              </div>
              <span className={i === completedIndex ? "font-medium" : "text-gray-500"}>
                {stage.label}
              </span>
            </div>
          ))}
          <p className="text-sm text-gray-400 mt-4 text-center">{message}</p>
        </div>
      )}
    </main>
  );
}
```

### Step 5.3 — Results page

```tsx
// frontend/app/results/[id]/page.tsx

import ReactMarkdown from "react-markdown";

async function getResults(id: string) {
  const res = await fetch(`http://localhost:8000/api/results/${id}`, {
    cache: "no-store"
  });
  return res.json();
}

export default async function ResultsPage({ params }: { params: { id: string } }) {
  const data = await getResults(params.id);

  return (
    <main className="max-w-4xl mx-auto p-8 space-y-10">
      <h1 className="text-3xl font-bold">Your Job Search Results</h1>

      {/* Jobs found */}
      <section>
        <h2 className="text-xl font-semibold mb-4">Jobs Found</h2>
        <div className="grid gap-4">
          {data.jobs_list?.map((job: any, i: number) => (
            <div key={i} className="border rounded-lg p-4">
              <h3 className="font-semibold">{job.job_title}</h3>
              <p className="text-gray-600">{job.company_name} · {job.company_location}</p>
              <a href={job.job_url} target="_blank"
                 className="text-blue-600 text-sm hover:underline">
                View posting →
              </a>
            </div>
          ))}
        </div>
      </section>

      {/* Skills report */}
      <section>
        <h2 className="text-xl font-semibold mb-4">Skills Required</h2>
        <div className="prose prose-sm max-w-none">
          <ReactMarkdown>{data.skills_report}</ReactMarkdown>
        </div>
      </section>

      {/* Prep guide */}
      <section>
        <h2 className="text-xl font-semibold mb-4">Your Preparation Roadmap</h2>
        <div className="prose prose-sm max-w-none">
          <ReactMarkdown>{data.prep_guide}</ReactMarkdown>
        </div>
      </section>
    </main>
  );
}
```

---

## Part 6 — Database schema

```sql
-- PostgreSQL schema

CREATE TABLE searches (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID REFERENCES users(id),   -- nullable for anonymous
  job_role    TEXT NOT NULL,
  location    TEXT NOT NULL,
  job_type    TEXT NOT NULL,
  company     TEXT,
  status      TEXT DEFAULT 'queued',       -- queued | running | complete | error
  created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE results (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  search_id       UUID REFERENCES searches(id),
  jobs_list       JSONB,
  analysis_report TEXT,
  skills_report   TEXT,
  prep_guide      TEXT,
  created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE users (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email       TEXT UNIQUE NOT NULL,
  name        TEXT,
  created_at  TIMESTAMPTZ DEFAULT now()
);
```

---

## Part 7 — Local development setup

### docker-compose.yml

```yaml
version: "3.9"
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: jobhunt
      POSTGRES_PASSWORD: jobhunt
      POSTGRES_DB: jobhunt
    ports:
      - "5432:5432"
    volumes:
      - pg_data:/var/lib/postgresql/data

volumes:
  pg_data:
```

### Running everything locally

```bash
# 1. Start Redis + Postgres
docker-compose up -d

# 2. Start FastAPI backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# 3. Start Celery worker (new terminal)
cd backend
celery -A worker worker --loglevel=info

# 4. Start Next.js frontend (new terminal)
cd frontend
npm install
npm run dev
```

### Environment variables

```bash
# backend/.env
REDIS_URL=redis://localhost:6379
DATABASE_URL=postgresql://jobhunt:jobhunt@localhost:5432/jobhunt
OPENAI_API_KEY=sk-...
SERPER_API_KEY=...

# frontend/.env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Part 8 — Deployment

### Frontend → Vercel

```bash
cd frontend
vercel deploy
# Set NEXT_PUBLIC_API_URL to your Railway backend URL
```

### Backend → Railway

Railway handles Python apps natively. Create a new project, connect your GitHub repo, and point it to the `backend/` directory.

Add a `Procfile` in the backend folder:

```
web: uvicorn main:app --host 0.0.0.0 --port $PORT
worker: celery -A worker worker --loglevel=info
```

Railway will run both processes. Add Redis and PostgreSQL as Railway plugins — they provision automatically.

### Environment variables on Railway

Set the same variables from your `.env` file in the Railway dashboard. Railway auto-injects `DATABASE_URL` and `REDIS_URL` when you add those plugins.

---

## Part 9 — Production hardening checklist

These are things to add after the MVP works, before you share it publicly:

- [ ] **Rate limiting** — add `slowapi` to FastAPI to prevent abuse (e.g. 5 searches/hour per IP)
- [ ] **Result caching** — if the same `job_role + location + job_type` was searched in the last 6 hours, return the cached result instead of running the crew again (saves LLM costs)
- [ ] **Error retries** — configure Celery to retry failed tasks up to 2 times
- [ ] **Result expiry** — delete results from PostgreSQL after 7 days (add a Celery beat scheduled task)
- [ ] **Auth** — add NextAuth.js with Google provider; tie searches to user accounts so users can view their history
- [ ] **Cost monitoring** — log token usage from OpenAI API calls per search; estimate cost per run
- [ ] **Input validation** — validate `job_role` length (max 100 chars), reject empty strings
- [ ] **HTTPS** — Vercel and Railway handle this automatically in production; verify it works
- [ ] **Loading states** — if the SSE connection drops mid-search, poll `/api/results/{id}` as a fallback

---

## Part 10 — Recommended build order

Build in this sequence to avoid rework:

1. **Week 1** — Backend foundation: FastAPI + Celery + Redis working locally. Verify the flow runs as a Celery task and publishes events to Redis.
2. **Week 2** — Frontend shell: Next.js app with the three pages (search form, progress tracker, results). Wire up SSE from the progress page.
3. **Week 3** — Database: Add PostgreSQL, save results, fetch them on the results page. Test the full end-to-end flow.
4. **Week 4** — Polish: Tailwind styling, shadcn/ui components, mobile responsiveness, error handling.
5. **Week 5** — Deployment: Vercel + Railway. Test in production with real API keys.
6. **Week 6** — Hardening: Rate limiting, caching, auth.

A working MVP — ugly but functional — by end of week 3 is more valuable than a beautifully designed app that doesn't work yet.

---

## Common mistakes to avoid

**Do not use Next.js API routes as the AI backend.** They run in Node.js (or Edge runtime), cannot import CrewAI, and have a 10-second timeout on Vercel — your pipeline takes minutes.

**Do not run the CrewAI flow synchronously in the HTTP request.** The request will time out after 30 seconds. Always use a job queue.

**Do not store large markdown results in Redis.** Use PostgreSQL for the actual results; use Redis only for the progress events and task queue.

**Do not poll `/api/results/{id}` repeatedly from the frontend.** Use SSE (Server-Sent Events) for real-time progress. SSE is simpler than WebSockets and works perfectly for one-way server → client updates.
