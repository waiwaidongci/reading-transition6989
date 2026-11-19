from sqlalchemy import Column,Integer,String,JSON,ForeignKey
from ..config.database import Base
class TrailBatch(Base):
    __tablename__='trail_batches'
    id=Column(Integer,primary_key=True)
    trail_id=Column(Integer,ForeignKey('reading_trails.id'),nullable=False)
    index=Column(Integer,nullable=False)
    state=Column(String(20),default='accepted')
    continuations=Column(Integer,nullable=False)
    sha256=Column(String(64),nullable=False)
    bytes=Column(Integer,default=0)
    receipt=Column(JSON,nullable=True)
    created_at=Column(String(40),nullable=False)
