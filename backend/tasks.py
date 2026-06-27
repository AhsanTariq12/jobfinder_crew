# backend/tasks.py

import asyncio
import json
import os
import sys
import redis
import psycopg2
from worker import celery_app

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "./job_finder_crew/src"))
from job_finder_crew.main import JobFinderFlow
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.Redis.from_url(REDIS_URL)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://jobfinder:jobfinder123@localhost:5432/jobfinder")

# Railway gives postgres:// but psycopg2 needs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

def publish_progress(job_id: str, data: dict):
    data["job_id"] = job_id
    redis_client.publish(f"progress:{job_id}", json.dumps(data))

def create_search_record(job_id: str, job_role: str, location: str,
                         job_type: str, company: str):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO searches (id, job_role, location, job_type, company, status)
            VALUES (%s, %s, %s, %s, %s, 'queued')
            """,
            (job_id, job_role, location, job_type, company)
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()
def save_result_to_db(job_id: str, result: dict):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    try:
        # Save result to results table
        cur.execute(
            """
            INSERT INTO results (search_id, jobs_list, analysis_report, skills_report, prep_guide)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                job_id,
                json.dumps(result.get("jobs_list", [])),
                result.get("analysis_report", ""),
                result.get("skills_report", ""),
                result.get("prep_guide", ""),
            )
        )

        # Update search status to complete
        cur.execute(
            "UPDATE searches SET status = 'complete' WHERE id = %s",
            (job_id,)
        )

        conn.commit()

    except Exception as e:
        conn.rollback()
        raise e

    finally:
        cur.close()
        conn.close()


def update_search_status(job_id: str, status: str):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE searches SET status = %s WHERE id = %s",
            (status, job_id)
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


@celery_app.task(bind=True)
def run_job_search(self, job_id: str, job_role: str, location: str,
                   job_type: str, company: str):

    def progress_callback(data: dict):
        publish_progress(job_id, data)

    try:
        create_search_record(job_id, job_role, location, job_type, company)
        publish_progress(job_id, {"stage": "started", "message": "Starting your job search..."})
        update_search_status(job_id, "running")

        flow = JobFinderFlow(progress_callback=progress_callback)

        asyncio.run(flow.kickoff_async(inputs={
            "job_role": job_role,
            "location": location,
            "job_type": job_type,
            "company": company,
        }))

        save_result_to_db(job_id, {
            "jobs_list": [j.dict() for j in flow.state.jobs_list],
            "analysis_report": flow.state.analysis_report,
            "skills_report": flow.state.skills_report,
            "prep_guide": flow.state.prep_guide,
        })

        publish_progress(job_id, {
            "stage": "complete",
            "message": "Done! Your results are ready."
        })

    except Exception as e:
        update_search_status(job_id, "error")
        publish_progress(job_id, {
            "stage": "error",
            "message": f"Something went wrong: {str(e)}"
        })
        raise