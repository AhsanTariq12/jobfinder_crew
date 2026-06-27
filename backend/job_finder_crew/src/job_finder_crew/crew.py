from typing import List
from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai_tools import SerperDevTool
from crewai_tools import ScrapeWebsiteTool

from pydantic import BaseModel, Field

class Job(BaseModel):
    """Details of top 5 searched companies"""
    job_title: str = Field(description="Job Title")
    company_name: str = Field(description="Company Name")
    company_location: str = Field(description="Company Location")
    job_url: str = Field(description="Job URL")
    job_posting_date: str = Field(description="Job Posting Date")
    job_source: str = Field(description="Job Source")
   
class Job_Search_List(BaseModel):
    """List of top 5 searched jobs"""
    
    jobs: List[Job] = Field(
        description="Array containing top 5 job listings"
    )


@CrewBase
class JobFinderCrew():
    """JobFinderCrew crew"""
    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"
    agents: list[BaseAgent]
    tasks: list[Task]

    @agent
    def job_researcher(self) -> Agent:
        return Agent(
            config=self.agents_config['job_researcher'], # type: ignore[index]
            verbose=True,
            tools = [SerperDevTool(), ScrapeWebsiteTool()]
        )

    @agent
    def job_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config['job_analyst'], # type: ignore[index]
            verbose=True,
            tools = [SerperDevTool(), ScrapeWebsiteTool()]
        )

    @agent
    def skills_advisor(self) -> Agent:
        return Agent(
            config=self.agents_config['skills_advisor'], # type: ignore[index]
            verbose=True,
        )

    @agent
    def preparation_planner(self) -> Agent:
        return Agent(
            config=self.agents_config['preparation_planner'], # type: ignore[index]
            verbose=True,
        )

    @task
    def search_jobs(self) -> Task:
        return Task(
            config=self.tasks_config['search_jobs'], # type: ignore[index]
            output_pydantic = Job_Search_List
        )

    @task
    def analyze_jobs(self) -> Task:
        return Task(
            config=self.tasks_config['analyze_jobs'], # type: ignore[index]
        )

    @task
    def identify_skills(self) -> Task:
        return Task(
            config=self.tasks_config['identify_skills'], # type: ignore[index]
        )

    @task
    def prepare_for_interview(self) -> Task:
        return Task(
            config=self.tasks_config['prepare_for_interview'], # type: ignore[index]
        )

    def search_crew(self) -> Crew:
        """Creates a Crew specifically for searching jobs"""
        return Crew(
            agents=[self.job_researcher()],
            tasks=[self.search_jobs()],
            process=Process.sequential,
            verbose=True,
        )

    def analysis_crew(self) -> Crew:
        """Creates a Crew specifically for analyzing jobs"""
        return Crew(
            agents=[self.job_analyst()],
            tasks=[self.analyze_jobs()],
            process=Process.sequential,
            verbose=True,
        )

    def skills_crew(self) -> Crew:
        """Creates a Crew specifically for identifying skills"""
        return Crew(
            agents=[self.skills_advisor()],
            tasks=[self.identify_skills()],
            process=Process.sequential,
            verbose=True,
        )

    def prep_crew(self) -> Crew:
        """Creates a Crew specifically for interview preparation planning"""
        return Crew(
            agents=[self.preparation_planner()],
            tasks=[self.prepare_for_interview()],
            process=Process.sequential,
            verbose=True,
        )

    @crew
    def crew(self) -> Crew:
        """Creates the full sequential JobFinderCrew crew"""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
