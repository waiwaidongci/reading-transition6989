from sqlalchemy import Column,Integer,String,ForeignKey,Boolean
from ..config.database import Base
class TrailCoverage(Base):
    __tablename__='trail_coverage'
    id=Column(Integer,primary_key=True)
    trail_id=Column(Integer,ForeignKey('reading_trails.id'),nullable=False)
    from_chapter=Column(String(600),nullable=False)
    to_chapter=Column(String(600),nullable=False)
    measured=Column(Integer,nullable=False)
    walked=Column(Integer,nullable=False)
    covered=Column(Boolean,nullable=False)
    on_board=Column(Boolean,nullable=False)
