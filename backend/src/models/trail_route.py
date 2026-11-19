from sqlalchemy import Column,Integer,String,JSON,ForeignKey,Boolean
from ..config.database import Base
class TrailRoute(Base):
    __tablename__='trail_routes'
    id=Column(Integer,primary_key=True)
    trail_id=Column(Integer,ForeignKey('reading_trails.id'),nullable=False)
    route_index=Column(Integer,nullable=False)
    closed=Column(Boolean,default=False)
    step_count=Column(Integer,nullable=False)
    nodes=Column(JSON,nullable=False)
    steps=Column(JSON,nullable=False)
