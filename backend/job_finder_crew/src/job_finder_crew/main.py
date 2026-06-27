#!/usr/bin/env python
import sys
import warnings
import asyncio
from datetime import datetime
from pydantic import BaseModel
from crewai.flow.flow import Flow, listen, start, router
from job_finder_crew.crew import JobFinderCrew

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

# 1. Define the state of your application
class JobFinderState(BaseModel):
    job_role: str = "Full Stack Website Developer"
    location: str = "Ireland"
    job_type: str = "Remote"
    company: str = "Not Provided"
    
    jobs_list: list = []
    analysis_report: str = ""
    skills_report: str = ""
    prep_guide: str = ""

# 2. Define the flow controller
class JobFinderFlow(Flow[JobFinderState]):
    def __init__(self, progress_callback=None):
        super().__init__()
        self._progress = progress_callback or (lambda msg: None)
    @start()
    def initialize_and_search(self):
        self._progress({"stage": "searching", "message": "Searching for jobs..."})
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting job search crew...")
        
        # Kick off the search crew
        crew_output = JobFinderCrew().search_crew().kickoff(inputs={
            "job_role": self.state.job_role,
            "location": self.state.location,
            "job_type": self.state.job_type,
            "company": self.state.company
        })
        
        # Save search output to state
        if crew_output and hasattr(crew_output, "pydantic") and crew_output.pydantic:
            self.state.jobs_list = crew_output.pydantic.jobs
        else:
            self.state.jobs_list = []
            
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Found {len(self.state.jobs_list)} jobs.")
        return self.state.jobs_list

    @router(initialize_and_search)
    def check_jobs_found(self):
        if not self.state.jobs_list:
            return "no_jobs_found"
        return "jobs_exist"

    @listen("no_jobs_found")
    def handle_empty_results(self):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] No jobs found. Ending flow.")
        self.state.prep_guide = "No jobs found matching your criteria, so no roadmap could be generated."
        return self.state.prep_guide

    @listen("jobs_exist")
    async def analyze_jobs_parallel(self):
        self._progress({
            "stage": "analyzing",
            "message": f"Analyzing {len(self.state.jobs_list)} jobs in parallel..."
        })
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting parallel analysis for {len(self.state.jobs_list)} jobs...")
        
        async def analyze_single_job(job, index):
            job_title = getattr(job, "job_title", "Unknown Title")
            company_name = getattr(job, "company_name", "Unknown Company")
            job_location = getattr(job, "company_location", "Unknown Location")
            job_url = getattr(job, "job_url", "")
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Launching analysis task for Job #{index}: {job_title} at {company_name}")
            
            # Run the analyst crew asynchronously
            result = await JobFinderCrew().analysis_crew().kickoff_async(inputs={
                "job_title": job_title,
                "company_name": company_name,
                "job_location": job_location,
                "job_url": job_url
            })
            return f"### Job #{index}: {job_title} at {company_name}\n{result.raw}\n"

        # Create tasks for all jobs
        tasks = [analyze_single_job(job, idx) for idx, job in enumerate(self.state.jobs_list, 1)]
        
        # Execute in parallel
        reports = await asyncio.gather(*tasks)
        
        # Consolidate reports
        self.state.analysis_report = "\n\n".join(reports)
        
        # Save consolidated report to file
        import os
        os.makedirs("output", exist_ok=True)
        with open("output/jobs_analysis_report.md", "w", encoding="utf-8") as f:
            f.write(self.state.analysis_report)
            
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Consolidated analysis report generated.")
        return self.state.analysis_report

    @listen(analyze_jobs_parallel)
    def identify_skills_and_plan(self):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Identifying required skills...")
        self._progress({"stage": "skills", "message": "Identifying required skills..."})
        # Kick off skills crew using the consolidated report
        skills_output = JobFinderCrew().skills_crew().kickoff(inputs={
            "job_analysis_report": self.state.analysis_report
        })
        self.state.skills_report = skills_output.raw
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Generating roadmap & preparation plan...")
        # Kick off prep planner crew using both reports
        self._progress({"stage": "planning", "message": "Building your prep roadmap..."})
        prep_output = JobFinderCrew().prep_crew().kickoff(inputs={
            "skills_list": self.state.skills_report,
            "job_analysis_report": self.state.analysis_report
        })
        self.state.prep_guide = prep_output.raw
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Flow processing complete.")
        return self.state.prep_guide


def run():
    """
    Run the Job Finder Flow.
    """
    inputs = {
        'job_role': 'Full Stack Website Developer',
        'location': 'Ireland',
        'company': 'Not Provided',
        'job_type': 'Remote'
    }
    
    try:
        flow = JobFinderFlow()
        # Execute the flow asynchronously since it contains parallel async steps
        result = asyncio.run(flow.kickoff_async(inputs=inputs))
        print("\n==================================================")
        print("FINAL INTERVIEW PREPARATION PLAN:")
        print("==================================================")
        print(result)
    except Exception as e:
        raise Exception(f"An error occurred while running the flow: {e}")


if __name__ == "__main__":
    run()
