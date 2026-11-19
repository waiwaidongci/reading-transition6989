import json,random,logging
from sqlalchemy import select,func
from src.config.database import Base,engine,Session
from src.config.settings import CONFIG
from src.models.user import User
from src.models.source import Source
from src.models.record import Record
from src.models.run import Run
from src.models import note,audit
from src.utils.security import hash_password
from src.utils.serialization import now
from src.services.runs import queue
from src.services.domain_validation import validate_record

def seed_values(kind,index,batch,rng):
    if kind=='gaussian':
        cls=index%3;return {'rms':round(max(.1,rng.gauss([1.2,3.0,2.0][cls]+batch*.08,.35)),3),'centroid':round(max(100,rng.gauss([900,1600,2300][cls],170)),2),'kurtosis':round(max(.1,rng.gauss([2.8,5.2,3.9][cls],.45)),3),'label':['正常','轴承磨损','转子偏心'][cls]}
    if kind=='density':
        cls=index%3
        if index%19==0:return {'temperature':round(rng.uniform(12,42),2),'humidity':round(rng.uniform(12,92),2),'particles':round(rng.uniform(4,140),2)}
        return {'temperature':round(rng.gauss([19,26,32][cls]+batch*.3,.8),2),'humidity':round(rng.gauss([72,45,28][cls],2.5),2),'particles':round(max(.1,rng.gauss([22,48,85][cls],3)),2)}
    if kind=='transition':
        choices=[['序章','材料','工艺','案例'],['序章','案例','附录'],['材料','工艺','案例','附录'],['序章','材料','案例'],['序章']]
        path=choices[rng.randrange(len(choices))];return {'session':f'SY-{batch+1}-{index+1:04}','path':'>'.join(path)}
    if kind=='forest':
        moisture=rng.uniform(20,60);thickness=rng.uniform(1,8);temperature=rng.uniform(50,100);airflow=rng.uniform(1,5)
        minutes=12+1.6*moisture+8*thickness-.45*temperature-3*airflow+0.1*moisture*thickness+rng.gauss(0,3)
        return {'moisture':round(moisture,2),'thickness':round(thickness,2),'temperature':round(temperature,2),'airflow':round(airflow,2),'minutes':round(max(5,minutes),2)}
    if kind=='neighbors':
        uid=index//6;slot=index%6;exhibit=(uid%3*3+slot)%12
        return {'visitor':f'V{uid+1:03}','exhibit':f'E{exhibit+1:02}','rating':round(max(1,min(5,3+(1 if exhibit%3==uid%3 else -.4)+rng.gauss(0,.55))),1)}

def drill_paths(rng):
    """固定 seed 的编辑演练会话。

    按章族构造：5 个小环族 + 3 个大环族 + 1 个开放族（自然形成多条开放路线）
    + 1 个长尾散布族。每条会话最多 45 个章节（章节路径不超过后端 600 字符上限），
    合计约 50000 种实测接续，既有多条闭环、多条开放路线，也有大量榜外接续。
    """
    cap=45

    def family(fam,size,jumps,ring):
        nodes=[CONFIG['code']+f'-F{fam}-C{i:03d}' for i in range(size)]
        by_src={}
        for i in range(size):
            for j in range(1,jumps+1):
                target=(i+j)%size if ring else i+j
                if ring or target<size: by_src.setdefault(i,[]).append(target)
        for v in by_src: rng.shuffle(by_src[v])
        while any(by_src.values()):
            current=rng.choice([v for v in by_src if by_src[v]]);path=[current]
            while by_src.get(current):
                current=by_src[current].pop();path.append(current)
                if len(path)>=cap:break
            if len(path)>=2:paths.append([nodes[x] for x in path])
    paths=[]
    for fam,(size,jumps) in enumerate([(20,12),(15,12),(60,12),(30,12),(30,12)]):
        family(fam,size,jumps,True)
    for fam in (5,6,7):family(fam,1100,8,True)
    family(8,1100,6,False)
    sparse=[CONFIG['code']+f'-F9-C{i:03d}' for i in range(145)]
    for _ in range(1350):
        path=[sparse[rng.randrange(len(sparse))] for _ in range(21)]
        for step in range(1,len(path)):
            if path[step]==path[step-1]:path[step]=sparse[(sparse.index(path[step])+1)%len(sparse)]
        paths.append(path)
    return paths

def drill_values(index,path):
    return {'session':CONFIG['code']+'-DRILL-'+f'{index+1:05d}','path':'>'.join(path)}

def counts(db):
    return {cls.__tablename__:db.scalar(select(func.count()).select_from(cls)) for cls in (User,Source,Record,Run)}
def seed():
    Base.metadata.create_all(engine);rng=random.Random(42);queued=[]
    with Session() as db:
        for role in ('admin','analyst','viewer'):
            email=role+'@'+CONFIG['slug']+'.demo'
            if not db.scalar(select(User).where(User.email==email)):db.add(User(email=email,password_hash=hash_password('Research2026!'),role=role))
        for batch in range(3):
            key=CONFIG['code']+f'-202611-{batch+1:02}'
            source=db.scalar(select(Source).where(Source.key==key))
            if not source:
                source=Source(key=key,name=key+' '+['秋季常规组','复测对照组','工艺观察组'][batch],filename=CONFIG['slug']+f'-202611-{batch+1:02}.csv',description=CONFIG['scenario']);db.add(source);db.flush()
            for index in range(CONFIG['seed_count']):
                reference=key+f'-{index+1:04}'
                vals=seed_values(CONFIG['algorithm'],index,batch,rng)
                if not db.scalar(select(Record.id).where(Record.source_id==source.id,Record.reference==reference)):
                    db.add(Record(source_id=source.id,reference=reference,values=validate_record(vals)))
            db.flush()
            if batch==0 and not db.scalar(select(Run.id).where(Run.name=='首轮种子研究')):
                records=[{'id':r.id,'source_id':r.source_id,'reference':r.reference,'values':r.values} for r in db.scalars(select(Record).where(Record.source_id==source.id).order_by(Record.id))]
                run=Run(source_id=source.id,name='首轮种子研究',state='queued',parameters=CONFIG['default_parameters'],snapshot={'source':{'id':source.id,'name':source.name,'filename':source.filename},'records':records},created_at=now());db.add(run);db.flush();queued.append(run.id)
        drill_key=CONFIG['code']+'-DRILL-202611'
        drill_source=db.scalar(select(Source).where(Source.key==drill_key))
        if not drill_source:
            drill_source=Source(key=drill_key,name='十一月编辑演练组',filename=CONFIG['slug']+'-drill-202611.csv',
                                description='编辑演练专用：5000 条冻结会话，展开覆盖五万种实测接续（含榜外）。')
            db.add(drill_source);db.flush()
            paths=drill_paths(rng)
            for index,path in enumerate(paths):
                db.add(Record(source_id=drill_source.id,reference=drill_key+f'-{index+1:05d}',
                              values=validate_record(drill_values(index,path))))
        db.commit();print(json.dumps(counts(db),ensure_ascii=False))
    for id in queued:
        try:queue.rpush('analysis:queue',id)
        except Exception:logging.exception('seed queue unavailable')
if __name__=='__main__':seed()
