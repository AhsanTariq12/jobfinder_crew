from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as aioredis
import json
import asyncio
from uuid import uuid4
from tasks import run_job_search
from models import SearchRequest, SearchResponse
import json
import psycopg2
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://jobfinder:jobfinder123@localhost:5432/jobfinder")
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

                    # Decode bytes to string if needed
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")

                    yield f"data: {data}\n\n"

                    parsed = json.loads(data)
                    if parsed.get("stage") in ("complete", "error", "no_jobs_found"):
                        await asyncio.sleep(0.5)
                        break
        finally:
            await pubsub.unsubscribe(f"progress:{job_id}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )

@app.get("/api/results/{job_id}")
async def get_results(job_id: str):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT r.jobs_list, r.analysis_report, r.skills_report, r.prep_guide
            FROM results r
            WHERE r.search_id = %s
            """,
            (job_id,)
        )
        row = cur.fetchone()

        if not row:
            return {"status": "not_found"}

        jobs_list, analysis_report, skills_report, prep_guide = row

        # jobs_list comes back as string from psycopg2, parse it
        if isinstance(jobs_list, str):
            jobs_list = json.loads(jobs_list)
        if isinstance(jobs_list, bytes):
            jobs_list = json.loads(jobs_list.decode("utf-8"))

        return {
            "status": "complete",
            "jobs_list": jobs_list,
            "analysis_report": analysis_report,
            "skills_report": skills_report,
            "prep_guide": prep_guide,
        }

    finally:
        cur.close()
        conn.close()