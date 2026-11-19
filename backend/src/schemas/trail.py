from pydantic import BaseModel,Field
from typing import Optional,List,Dict,Any
class TrailInput(BaseModel):
    source_id:int
    title:str=Field(min_length=2,max_length=160)
    parameters:Dict[str,Any]=Field(default_factory=dict)
class BatchInput(BaseModel):
    batch_index:Optional[int]=Field(default=None,ge=0,le=100000)
    continuations:Optional[List[Dict[str,Any]]]=None
    sessions:Optional[List[Dict[str,Any]]]=None
class SolveInput(BaseModel):
    override_frozen:bool=False
