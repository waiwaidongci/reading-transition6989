"""编辑演练服务：冻结会话 → 分批受理接续 → 合齐后统一求解 → 逐条路线与覆盖。

* 冻结：创建时把来源当前全部会话展开成接续目录并记录 SHA256；之后并发追加
  会话不会改变本次演练（目录不一致时求解明确拒绝）。
* 受理：每批最多 5000 条，逐批校验写盘，合计不超过 50000 种接续。
* 求解：从分批文件流式合齐目录，统一规划；路线与覆盖逐行落库，页面分页读取。
* 内存：受理与求解各自记录峰值，超过 192MB 预算即把演练标为失败而不继续。
"""
import os
from fastapi import HTTPException
from sqlalchemy import select, func, delete
from ..models.trail import Trail
from ..models.trail_batch import TrailBatch
from ..models.trail_route import TrailRoute
from ..models.trail_coverage import TrailCoverage
from ..utils.serialization import row, now
from .sources import source_or_404, list_records
from .domain_validation import validate_parameters
from .audit import log
from . import drill_validation, drill_algorithm, drill_store

ARTIFACT_ROOT = os.getenv('ARTIFACT_DIR', '/tmp/artifacts')
_PAGE = 500


def _session_rows(records):
    return [{'session': item['values']['session'], 'path': item['values']['path']} for item in records]


def _trail_or_404(db, id):
    trail = db.get(Trail, id)
    if not trail:
        raise HTTPException(404, '未找到编辑演练')
    return trail


def create_trail(db, user, data):
    source = source_or_404(db, data.source_id)
    records = list_records(db, source.id)
    if not records:
        raise HTTPException(422, '至少录入 1 个完整阅读会话后才能演练')
    try:
        catalog = drill_validation.normalize_sessions(_session_rows(records))
        params = validate_parameters(data.parameters or {})
    except ValueError as error:
        raise HTTPException(422, str(error))
    board = drill_algorithm.leaderboard(catalog, params['min_count'], params['top_n'])
    trail = Trail(source_id=source.id, title=data.title, state='collecting',
                  frozen_catalog=catalog, catalog_sha256=drill_validation.fingerprint(catalog),
                  meta={'frozen_sessions': len(records), 'min_count': params['min_count'],
                        'top_n': params['top_n'], 'leaderboard': sorted([list(x) for x in board])},
                  continuation_count=len(catalog), off_board=len(catalog) - len(board),
                  memory_limit_mb=drill_store.MEMORY_BUDGET_MB, created_at=now())
    db.add(trail)
    db.flush()
    log(db, user, 'trail.created', trail.id,
        f'{source.name} · {len(records)} 会话 · {len(catalog)} 种接续 · 目录 {trail.catalog_sha256[:12]}')
    db.commit()
    return _summary(trail, db)


def _summary(trail, db):
    item = row(trail)
    item.pop('frozen_catalog', None)
    item['batch_count'] = db.scalar(select(func.count()).select_from(TrailBatch).where(TrailBatch.trail_id == trail.id))
    return item


def get_trail(db, id):
    return _summary(_trail_or_404(db, id), db)


def list_trails(db):
    return [_summary(trail, db) for trail in db.scalars(select(Trail).order_by(Trail.id.desc()))]


def accept_batch(db, user, trail_id, payload):
    trail = _trail_or_404(db, trail_id)
    if trail.state != 'collecting':
        raise HTTPException(409, '本次演练已合齐求解，不再受理新批次')
    started = drill_store.memory_mb()
    try:
        if payload.sessions is not None:
            rows = drill_validation.normalize_sessions(payload.sessions)
        else:
            rows = drill_validation.normalize_catalog(payload.continuations)
    except ValueError as error:
        raise HTTPException(422, str(error))
    if len(rows) > drill_store.MAX_BATCH:
        raise HTTPException(422, f'单个批次最多 {drill_store.MAX_BATCH} 条接续，请分批提交')
    used = db.scalar(select(func.coalesce(func.sum(TrailBatch.continuations), 0))
                     .where(TrailBatch.trail_id == trail.id))
    if used + len(rows) > drill_store.MAX_CONTINUATIONS:
        raise HTTPException(422, '接续批次合计超过 50000 条，请检查是否重复提交')
    index = payload.batch_index
    if index is None:
        index = db.scalar(select(func.coalesce(func.max(TrailBatch.index), -1))
                          .where(TrailBatch.trail_id == trail.id)) + 1
    if db.scalar(select(TrailBatch.id).where(TrailBatch.trail_id == trail.id, TrailBatch.index == index)):
        raise HTTPException(409, f'批次编号 {index} 已存在')
    receipt = drill_store.write_batch(ARTIFACT_ROOT, trail.id, index, rows)
    db.add(TrailBatch(trail_id=trail.id, index=index, state='accepted', continuations=len(rows),
                      sha256=receipt['sha256'], bytes=receipt['bytes'],
                      receipt={'kinds': len({(r['from'], r['to']) for r in rows})}, created_at=now()))
    peak = int(drill_store.memory_mb(started))
    trail.intake_peak_mb = max(trail.intake_peak_mb or 0, peak)
    if trail.intake_peak_mb > trail.memory_limit_mb:
        trail.state = 'failed'
        trail.error = f'受理内存峰值 {trail.intake_peak_mb}MB 超过 {trail.memory_limit_mb}MB 预算'
    log(db, user, 'trail.batch', trail.id, f'批次 {index} · {len(rows)} 条 · {receipt["sha256"][:12]}')
    db.commit()
    return {'index': index, 'accepted': len(rows), 'sha256': receipt['sha256'],
            'distinct': len({(r['from'], r['to']) for r in rows}),
            'intake_peak_mb': trail.intake_peak_mb}


def solve_trail(db, user, trail_id, override=False):
    trail = _trail_or_404(db, trail_id)
    if trail.state == 'solving':
        raise HTTPException(409, '本次演练正在求解')
    if trail.state == 'completed':
        raise HTTPException(409, '本次演练已完成；如需重算请新建演练以保持口径')
    batches = list(db.scalars(select(TrailBatch).where(TrailBatch.trail_id == trail.id)
                              .order_by(TrailBatch.index)))
    if not batches:
        raise HTTPException(409, '尚未受理任何接续批次')
    trail.state = 'solving'
    trail.error = ''
    db.commit()
    started = drill_store.memory_mb()
    succeeded = False
    try:
        catalog = drill_store.merge_batches(ARTIFACT_ROOT, trail.id, [b.index for b in batches])
        if not override and drill_validation.fingerprint(catalog) != trail.catalog_sha256:
            raise ValueError('受理的接续与创建时冻结的会话目录不一致；本次演练不改变冻结快照')
        meta = trail.meta or {}
        result = drill_algorithm.solve(catalog, min_count=meta.get('min_count', 3),
                                       top_n=meta.get('top_n', 20))
        peak = int(drill_store.memory_mb(started))
        if peak > trail.memory_limit_mb:
            raise ValueError(f'求解内存峰值 {peak}MB 超过 {trail.memory_limit_mb}MB 预算')
        db.execute(delete(TrailRoute).where(TrailRoute.trail_id == trail.id))
        db.execute(delete(TrailCoverage).where(TrailCoverage.trail_id == trail.id))
        for chunk_start in range(0, len(result['routes']), _PAGE):
            db.add_all([TrailRoute(trail_id=trail.id, route_index=route['index'], closed=route['closed'],
                                   step_count=route['step_count'], nodes=route['nodes'], steps=route['steps'])
                        for route in result['routes'][chunk_start:chunk_start + _PAGE]])
            db.flush()
        for chunk_start in range(0, len(result['coverage']), _PAGE):
            db.add_all([TrailCoverage(trail_id=trail.id, from_chapter=item['from'], to_chapter=item['to'],
                                      measured=item['count'], walked=item['walked'],
                                      covered=item['covered'], on_board=item['on_board'])
                        for item in result['coverage'][chunk_start:chunk_start + _PAGE]])
            db.flush()
        summary = result['summary']
        trail.route_count = summary['routes']
        trail.total_steps = summary['total_steps']
        trail.closed_routes = summary['closed_routes']
        trail.continuation_count = summary['continuations']
        trail.off_board = summary['off_board']
        trail.off_board_covered = summary['off_board_covered']
        trail.covered = summary['continuations'] if summary['complete'] else None
        trail.complete = summary['complete']
        trail.solve_peak_mb = peak
        trail.state = 'completed'
        trail.completed_at = now()
        succeeded = True
        log(db, user, 'trail.completed', trail.id,
            f'{trail.route_count} 条路线 · {trail.total_steps} 步 · 覆盖 {summary["continuations"]} 条接续')
        db.commit()
    except ValueError as error:
        db.rollback()
        trail = _trail_or_404(db, trail_id)
        trail.state = 'failed'
        trail.error = str(error)
        log(db, user, 'trail.failed', trail.id, str(error))
        db.commit()
        raise HTTPException(422, str(error))
    except Exception as error:  # noqa: BLE001 - 保留失败态供重新合齐
        db.rollback()
        trail = _trail_or_404(db, trail_id)
        trail.state = 'failed'
        trail.error = str(error)[:2000]
        log(db, user, 'trail.failed', trail.id, trail.error)
        db.commit()
        raise HTTPException(500, '求解失败，已保留批次文件，可重新合齐')
    finally:
        # 失败时保留分批文件，便于补齐批次后重新合齐；只有成功完成才清理。
        if succeeded:
            drill_store.delete_chunks(ARTIFACT_ROOT, trail.id)
    return get_trail(db, trail.id)


def coverage_report(db, trail_id, limit=_PAGE, offset=0, missing_only=False):
    trail = _trail_or_404(db, trail_id)
    query = select(TrailCoverage).where(TrailCoverage.trail_id == trail.id)
    if missing_only:
        query = query.where(TrailCoverage.covered.is_(False))
    total = db.scalar(select(func.count()).select_from(TrailCoverage).where(TrailCoverage.trail_id == trail.id))
    covered = db.scalar(select(func.count()).select_from(TrailCoverage)
                        .where(TrailCoverage.trail_id == trail.id, TrailCoverage.covered.is_(True)))
    off_board = db.scalar(select(func.count()).select_from(TrailCoverage)
                          .where(TrailCoverage.trail_id == trail.id, TrailCoverage.on_board.is_(False)))
    rows = [{'from': item.from_chapter, 'to': item.to_chapter, 'count': item.measured,
             'walked': item.walked, 'covered': item.covered, 'on_board': item.on_board}
            for item in db.scalars(query.order_by(TrailCoverage.id).offset(offset).limit(limit))]
    return {'state': trail.state, 'complete': bool(trail.complete),
            'total': total or 0, 'covered': covered or 0, 'off_board': off_board or 0,
            'off_board_covered': trail.off_board_covered or 0,
            'offset': offset, 'limit': limit, 'rows': rows,
            'catalog_sha256': trail.catalog_sha256}


def frozen_catalog_page(db, trail_id, limit=_PAGE, offset=0):
    """从冻结会话展开出的全部相邻接续（含榜外），分页供页面自动分批受理。"""
    trail = _trail_or_404(db, trail_id)
    catalog = trail.frozen_catalog or []
    return {'total': len(catalog), 'offset': offset, 'limit': limit,
            'rows': catalog[offset:offset + limit],
            'catalog_sha256': trail.catalog_sha256}


def trail_routes(db, trail_id, limit=_PAGE, offset=0):
    trail = _trail_or_404(db, trail_id)
    rows = [{'index': item.route_index, 'closed': item.closed, 'step_count': item.step_count,
             'nodes': item.nodes, 'steps': item.steps}
            for item in db.scalars(select(TrailRoute).where(TrailRoute.trail_id == trail.id)
                                   .order_by(TrailRoute.route_index).offset(offset).limit(limit))]
    return {'state': trail.state, 'offset': offset, 'limit': limit, 'rows': rows}
