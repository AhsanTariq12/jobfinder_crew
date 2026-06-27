
from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import datetime


class SearchRequest(BaseModel):
    job_role: str
    location: str = "United States of America"
    job_type: str = "Remote"
    company: Optional[str] = None


class SearchResponse(BaseModel):
    job_id: str
    status: str