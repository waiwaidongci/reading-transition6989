from sqlalchemy import Column,Integer,String,JSON,Text,ForeignKey,Boolean
from ..config.database import Base
from ..config.settings import CONFIG
class Trail(Base):
    """一次编辑演练。frozen_catalog 是创建时冻结的接续目录，catalog_sha256 锁定它。"""
    __tablename__='reading_trails'
    id=Column(Integer,primary_key=True)
    source_id=Column(Integer,ForeignKey(CONFIG['source_table']+'.id'),nullable=False)
    title=Column(String(160),nullable=False)
    state=Column(String(20),default='collecting')
    error=Column(Text,default='')
    frozen_catalog=Column(JSON,nullable=True)
    catalog_sha256=Column(String(64),nullable=False)
    meta=Column(JSON,nullable=True)
    route_count=Column(Integer,nullable=True)
    total_steps=Column(Integer,nullable=True)
    closed_routes=Column(Integer,nullable=True)
    continuation_count=Column(Integer,nullable=True)
    off_board=Column(Integer,nullable=True)
    off_board_covered=Column(Integer,nullable=True)
    covered=Column(Integer,nullable=True)
    complete=Column(Boolean,default=False)
    memory_limit_mb=Column(Integer,default=192)
    intake_peak_mb=Column(Integer,nullable=True)
    solve_peak_mb=Column(Integer,nullable=True)
    created_at=Column(String(40),nullable=False)
    completed_at=Column(String(40),nullable=True)
