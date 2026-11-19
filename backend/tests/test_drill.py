"""编辑演练：算法最优性与接口不变量测试。

算法部分用暴力搜索做对照（小图穷举/随机图），接口部分用 FastAPI TestClient
覆盖分批受理、并发追加冻结、覆盖核对与权限。
"""
import itertools
import random
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.services import drill_algorithm, drill_validation  # noqa: E402


def brute_force(edges):
    """(路线数, 总步数) 的暴力字典序最优解：状态=(已走边集合, 当前章节)。"""
    edges = sorted(set(edges))
    if not edges:
        return (0, 0)
    nodes = sorted({x for edge in edges for x in edge})
    outgoing = {v: [] for v in nodes}
    for index, (a, b) in enumerate(edges):
        outgoing[a].append((b, index))
    full = (1 << len(edges)) - 1
    best = {(0, v): (1, 0) for v in nodes}
    heap = [(1, 0, 0, v) for v in nodes]
    import heapq
    while heap:
        routes, steps, mask, node = heapq.heappop(heap)
        if best.get((mask, node)) != (routes, steps):
            continue
        if mask == full:
            return (routes, steps)
        for target, edge_index in outgoing[node]:
            new_mask = mask | (1 << edge_index)
            cost = (routes, steps + 1)
            if (new_mask, target) not in best or cost < best[(new_mask, target)]:
                best[(new_mask, target)] = cost
                heapq.heappush(heap, (routes, steps + 1, new_mask, target))
        for start in nodes:
            cost = (routes + 1, steps)
            if (mask, start) not in best or cost < best[(mask, start)]:
                best[(mask, start)] = cost
                heapq.heappush(heap, (routes + 1, steps, mask, start))


def run_solver(edges):
    catalog = [{'from': a, 'to': b, 'count': 1} for a, b in sorted(set(edges))]
    result = drill_algorithm.solve(catalog)
    measured = {(a, b) for a, b in edges}
    walked = set()
    for route in result['routes']:
        assert len(route['nodes']) - 1 == len(route['steps'])
        assert route['closed'] == (route['nodes'][0] == route['nodes'][-1])
        for index, step in enumerate(route['steps']):
            assert route['nodes'][index] == step['from']
            assert route['nodes'][index + 1] == step['to']
            assert (step['from'], step['to']) in measured
            walked.add((step['from'], step['to']))
    assert walked == measured
    assert result['summary']['complete'] is True
    return result['summary']['routes'], result['summary']['total_steps']


def test_matches_brute_force_small_graphs():
    all_edges = [(a, b) for a in range(3) for b in range(3) if a != b]
    for size in range(1, len(all_edges) + 1):
        for combination in itertools.combinations(all_edges, size):
            assert run_solver(list(combination)) == brute_force(list(combination))


def test_matches_brute_force_random_graphs():
    rng = random.Random(20261119)
    all_edges = [(a, b) for a in range(4) for b in range(4)]
    for _ in range(600):
        edges = rng.sample(all_edges, rng.randint(1, 7))
        assert run_solver(edges) == brute_force(edges)


def test_self_loops_and_closed_loop_are_single_route():
    assert run_solver([('A', 'A'), ('A', 'B')]) == (1, 2)
    assert run_solver([('A', 'B'), ('B', 'C'), ('C', 'A')]) == (1, 3)


def test_off_board_flagged_and_covered():
    catalog = [{'from': 'A', 'to': 'B', 'count': 9}, {'from': 'B', 'to': 'C', 'count': 1}]
    result = drill_algorithm.solve(catalog, min_count=3, top_n=1)
    coverage = {(row['from'], row['to']): row for row in result['coverage']}
    assert coverage[('A', 'B')]['on_board'] is True
    assert coverage[('B', 'C')]['on_board'] is False
    assert all(row['covered'] for row in coverage.values())
    assert result['summary']['off_board_covered'] == 1


def test_validation_rejects_duplicate_sessions_and_unknown_fields():
    with pytest.raises(ValueError):
        drill_validation.normalize_sessions([{'session': 'S', 'path': 'A>B'},
                                             {'session': 'S', 'path': 'B>C'}])
    with pytest.raises(ValueError):
        drill_validation.normalize_catalog([{'from': 'A', 'to': 'B', 'count': 1, 'x': 2}])
    with pytest.raises(ValueError):
        drill_validation.normalize_catalog([{'from': 'A', 'to': 'B', 'count': 0}])


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(tmp_path / 'test.db'))
    monkeypatch.setenv('ARTIFACT_DIR', str(tmp_path / 'artifacts'))
    monkeypatch.setenv('SEED_DEMO', 'false')
    (tmp_path / 'artifacts').mkdir()
    for module in list(sys.modules):
        if module.startswith('src.'):
            del sys.modules[module]
    from src.config.database import Base, engine, Session
    from src.models.user import User
    from src.utils.security import hash_password
    import src.services.runs as runs_service
    from src.main import app

    class FakeQueue:
        def rpush(self, *args):
            return None

        def ping(self):
            return True

    runs_service.queue = FakeQueue()
    Base.metadata.create_all(engine)
    with Session() as db:
        for role in ('admin', 'analyst', 'viewer'):
            db.add(User(email=role + '@reading-transition.demo',
                        password_hash=hash_password('Research2026!'), role=role))
        db.commit()
    with TestClient(app) as test_client:
        yield test_client


def login(client, role='analyst'):
    response = client.post('/auth/login', json={'email': role + '@reading-transition.demo',
                                                'password': 'Research2026!'})
    return {'Authorization': 'Bearer ' + response.json()['token']}


def build_source(client, headers, paths, name='演练来源'):
    source = client.post('/sources', json={'name': name, 'filename': 'drill-source.csv',
                                           'description': 'test'}, headers=headers).json()
    records = [{'reference': f'R{i:05d}', 'values': {'session': f'S{i:05d}', 'path': path}}
               for i, path in enumerate(paths)]
    response = client.post(f"/sources/{source['id']}/records", json={'records': records}, headers=headers)
    assert response.status_code == 200, response.text
    return source


def test_api_batches_freeze_and_coverage(client):
    analyst = login(client)
    source = build_source(client, analyst, ['A>B>C', 'B>C>D', 'C>D>A'])
    trail = client.post('/trails', json={'source_id': source['id'], 'title': '十一月编辑演练',
                                         'parameters': {}}, headers=analyst).json()
    catalog = drill_validation.normalize_sessions([{'session': 'S00000', 'path': 'A>B>C'},
                                                   {'session': 'S00001', 'path': 'B>C>D'},
                                                   {'session': 'S00002', 'path': 'C>D>A'}])
    first, second = catalog[:2], catalog[2:]
    assert client.post(f"/trails/{trail['id']}/batches", json={'continuations': first},
                       headers=analyst).status_code == 200
    assert client.post(f"/trails/{trail['id']}/batches", json={'continuations': second},
                       headers=analyst).status_code == 200
    solved = client.post(f"/trails/{trail['id']}/solve", json={}, headers=analyst)
    assert solved.status_code == 200, solved.text
    body = solved.json()
    assert body['complete'] is True
    assert body['route_count'] == 1 and body['closed_routes'] == 1
    coverage = client.get(f"/trails/{trail['id']}/coverage", headers=analyst).json()
    assert coverage['covered'] == coverage['total'] == 4


def test_concurrent_append_does_not_change_frozen_drill(client):
    analyst = login(client)
    source = build_source(client, analyst, ['A>B>C', 'B>C>D'])
    trail = client.post('/trails', json={'source_id': source['id'], 'title': '冻结快照演练',
                                         'parameters': {}}, headers=analyst).json()
    client.post(f"/sources/{source['id']}/records",
                json={'records': [{'reference': 'R999', 'values': {'session': 'S999', 'path': 'A>Z'}}]},
                headers=analyst)
    changed = drill_validation.normalize_sessions([
        {'session': 'S00000', 'path': 'A>B>C'}, {'session': 'S00001', 'path': 'B>C>D'},
        {'session': 'S999', 'path': 'A>Z'}])
    client.post(f"/trails/{trail['id']}/batches", json={'continuations': changed}, headers=analyst)
    response = client.post(f"/trails/{trail['id']}/solve", json={}, headers=analyst)
    assert response.status_code == 422
    assert '冻结' in response.json()['detail']


def test_role_and_batch_guards(client):
    analyst, viewer = login(client), login(client, 'viewer')
    source = build_source(client, analyst, ['A>B>C'])
    trail = client.post('/trails', json={'source_id': source['id'], 'title': '权限演练',
                                         'parameters': {}}, headers=analyst).json()
    assert client.post('/trails', json={'source_id': source['id'], 'title': '越权演练',
                                        'parameters': {}}, headers=viewer).status_code == 403
    assert client.post(f"/trails/{trail['id']}/batches",
                       json={'continuations': [{'from': 'A', 'to': 'B', 'count': 1}]},
                       headers=viewer).status_code == 403
    assert client.get('/trails').status_code == 401
    oversize = [{'from': f'X{i}', 'to': f'Y{i}', 'count': 1} for i in range(5001)]
    response = client.post(f"/trails/{trail['id']}/batches", json={'continuations': oversize},
                           headers=analyst)
    assert response.status_code == 422
