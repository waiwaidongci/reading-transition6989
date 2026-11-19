from fastapi import APIRouter,Depends
from ..config.database import db_session
from ..schemas.trail import TrailInput,BatchInput,SolveInput
from ..services.auth import current_user,writer
from ..services import drills
router=APIRouter()
@router.get('/trails')
def trails(db=Depends(db_session),u=Depends(current_user)):return drills.list_trails(db)
@router.post('/trails')
def create(data:TrailInput,db=Depends(db_session),u=Depends(writer)):return drills.create_trail(db,u,data)
@router.get('/trails/{id}')
def detail(id:int,db=Depends(db_session),u=Depends(current_user)):return drills.get_trail(db,id)
@router.get('/trails/{id}/routes')
def trail_route_rows(id:int,limit:int=500,offset:int=0,db=Depends(db_session),u=Depends(current_user)):return drills.trail_routes(db,id,min(limit,500),max(offset,0))
@router.get('/trails/{id}/catalog')
def catalog_page(id:int,limit:int=500,offset:int=0,db=Depends(db_session),u=Depends(current_user)):return drills.frozen_catalog_page(db,id,min(limit,500),max(offset,0))
@router.post('/trails/{id}/batches')
def batch(id:int,data:BatchInput,db=Depends(db_session),u=Depends(writer)):return drills.accept_batch(db,u,id,data)
@router.get('/trails/{id}/coverage')
def coverage(id:int,limit:int=500,offset:int=0,missing:bool=False,db=Depends(db_session),u=Depends(current_user)):return drills.coverage_report(db,id,min(limit,500),max(offset,0),missing)
@router.post('/trails/{id}/solve')
def solve(id:int,data:SolveInput,db=Depends(db_session),u=Depends(writer)):return drills.solve_trail(db,u,id,override=data.override_frozen)
