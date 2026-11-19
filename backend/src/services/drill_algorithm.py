"""编辑演练路线规划：会话内一阶接续的实测边，只照走、不造边。

输入
----
catalog: ``[{'from': 章节, 'to': 章节, 'count': 实测次数}, ...]``
         按 (from, to) 去重后的**全部**相邻接续（含未进入榜单的榜外接续）。

目标（严格字典序）
------------------
1. 路线数最少；
2. 路线数相同时总步数最少。

一条路线是章节序列，相邻两步必须是目录中实测到的接续；同一条接续允许重复
走（重复步同样是实测证据）。闭环（首尾相接）算一条路线。

图论依据
--------
* 弱连通分量独立规划：跨分量没有实测衔接，不能强行并成一条路线。
* 分量内不平衡度 ``P = sum(max(0, out-in))``：P=0 存在欧拉回路（1 条闭环）；
  P>0 至少 P 条开放路线。
* 一条路线的终点可以用一条实测路径接到另一条路线的起点，从而把两条并成一条；
  每个分量最多合并 P-1 次。合并问题化为最小费用最大流：亏空点供流、盈余点收流、
  每条实测边费用 1。先最大流（路线最少），再最小费用（重复步最少）。
* 增广后的多重图用 Hierholzer 欧拉分解拆成路线；非平衡分量补虚拟节点 X 并
  在虚拟边处切成 P-flow 条开放路线。

实现采用“Dijkstra 势函数 + Dinic 阻塞流”的最小费用最大流，避免按单位逐次
增广；流分解与欧拉分解均为线性，整体在 5 万条接续、192MB 约束内可运行。
"""
from collections import defaultdict
import heapq

_INF = 1 << 60


class _Edge:
    __slots__ = ('to', 'rev', 'cap', 'cost')

    def __init__(self, to, rev, cap, cost):
        self.to = to
        self.rev = rev
        self.cap = cap
        self.cost = cost


class _MinCostMaxFlow:
    """Dijkstra 势函数求最短路 + Dinic 阻塞流一次推进多条最短路。"""

    def __init__(self, size):
        self.graph = [[] for _ in range(size)]

    def add(self, u, v, cap, cost):
        iu, iv = len(self.graph[u]), len(self.graph[v])
        if u == v:
            self.graph[u].append(_Edge(v, iu + 1, cap, cost))
            self.graph[u].append(_Edge(u, iu, 0, -cost))
            return self.graph[u][iu]
        forward = _Edge(v, iv, cap, cost)
        backward = _Edge(u, iu, 0, -cost)
        self.graph[u].append(forward)
        self.graph[v].append(backward)
        return forward

    def _blocking_flow(self, source, sink, limit, potential):
        """在零约化费用（admissible）子图上跑 Dinic，返回本次推进的流量。"""
        graph = self.graph
        size = len(graph)
        total = 0
        while total < limit:
            level = [-1] * size
            level[source] = 0
            queue = [source]
            head = 0
            while head < len(queue):
                u = queue[head]
                head += 1
                pu = potential[u]
                for edge in graph[u]:
                    if edge.cap > 0 and level[edge.to] < 0 and edge.cost + pu - potential[edge.to] == 0:
                        level[edge.to] = level[u] + 1
                        queue.append(edge.to)
            if level[sink] < 0:
                break
            cursor = [0] * size

            def push(u, amount):
                if u == sink:
                    return amount
                graph_u = graph[u]
                pu = potential[u]
                while cursor[u] < len(graph_u):
                    edge = graph_u[cursor[u]]
                    if edge.cap > 0 and level[edge.to] == level[u] + 1 and edge.cost + pu - potential[edge.to] == 0:
                        got = push(edge.to, amount if amount < edge.cap else edge.cap)
                        if got:
                            edge.cap -= got
                            graph[edge.to][edge.rev].cap += got
                            return got
                    cursor[u] += 1
                return 0

            while total < limit:
                pushed = push(source, limit - total)
                if not pushed:
                    break
                total += pushed
        return total

    def run(self, source, sink, limit):
        size = len(self.graph)
        potential = [0] * size
        flow = 0
        cost = 0
        while flow < limit:
            dist = [_INF] * size
            dist[source] = 0
            heap = [(0, source)]
            while heap:
                d, u = heapq.heappop(heap)
                if d != dist[u]:
                    continue
                pu = potential[u]
                for edge in self.graph[u]:
                    if edge.cap > 0:
                        nd = d + edge.cost + pu - potential[edge.to]
                        if nd < dist[edge.to]:
                            dist[edge.to] = nd
                            heapq.heappush(heap, (nd, edge.to))
            if dist[sink] >= _INF:
                break
            for v in range(size):
                if dist[v] < _INF:
                    potential[v] += dist[v]
                else:
                    potential[v] += dist[sink]
            pushed = self._blocking_flow(source, sink, limit - flow, potential)
            if not pushed:
                break
            flow += pushed
            cost += pushed * potential[sink]
        return flow, cost


def _find(parent, x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def _components(node_count, arcs):
    parent = list(range(node_count))

    def union(a, b):
        ra, rb = _find(parent, a), _find(parent, b)
        if ra != rb:
            parent[rb] = ra

    for a, b in arcs:
        union(a, b)
    groups = defaultdict(list)
    for v in range(node_count):
        groups[_find(parent, v)].append(v)
    return list(groups.values()), [_find(parent, v) for v in range(node_count)]


def _hierholzer(start, adjacency, arc_src, arc_dst):
    """消耗式 Hierholzer；返回欧拉回路（或欧拉路径）的边编号序列。"""
    pointer = {v: 0 for v in adjacency}
    stack = [(start, -1)]
    circuit = []
    while stack:
        v, used = stack[-1]
        edges = adjacency.get(v)
        position = pointer.get(v, 0)
        if edges is not None and position < len(edges):
            edge_id = edges[position]
            pointer[v] = position + 1
            stack.append((arc_dst[edge_id], edge_id))
        else:
            stack.pop()
            if used != -1:
                circuit.append(used)
    circuit.reverse()
    return circuit


def _split_component(members, adjacency, arc_src, arc_dst):
    """把一个分量的多重图拆成路线（节点编号, 边编号序列, 是否闭环）。"""
    local_edges = [eid for v in members for eid in adjacency.get(v, [])]
    if not local_edges:
        return []
    out_balance = defaultdict(int)
    in_balance = defaultdict(int)
    for eid in local_edges:
        out_balance[arc_src[eid]] += 1
        in_balance[arc_dst[eid]] += 1
    imbalance = {v: out_balance[v] - in_balance[v] for v in members if out_balance[v] != in_balance[v]}
    if not imbalance:
        start = min(members)
        circuit = _hierholzer(start, adjacency, arc_src, arc_dst)
        if not circuit:
            return []
        nodes = [arc_src[circuit[0]]]
        for eid in circuit:
            nodes.append(arc_dst[eid])
        return [(nodes, circuit, nodes[0] == nodes[-1])]
    # 虚拟节点 -1：盈余点补 X->v，亏空点补 v->X，从 X 跑欧拉回路后按 X 切段。
    virtual_src = []
    virtual_dst = []
    extended_src = list(arc_src)
    extended_dst = list(arc_dst)
    counter = len(arc_src)
    combined = defaultdict(list)
    for v in members:
        if adjacency.get(v):
            combined[v].extend(adjacency[v])
    for v, balance in imbalance.items():
        for _ in range(balance):
            extended_src.append(-1)
            extended_dst.append(v)
            combined[-1].append(counter)
            counter += 1
        for _ in range(-balance):
            extended_src.append(v)
            extended_dst.append(-1)
            combined[v].append(counter)
            counter += 1
    circuit = _hierholzer(-1, combined, extended_src, extended_dst)
    routes = []
    nodes = None
    steps = []
    for eid in circuit:
        if eid >= len(arc_src):
            if extended_src[eid] == -1:
                if nodes is not None and steps:
                    routes.append((nodes, steps, False))
                nodes = [extended_dst[eid]]
                steps = []
            else:
                if nodes is not None and steps:
                    routes.append((nodes, steps, False))
                nodes = None
                steps = []
        else:
            if nodes is None:
                nodes = [arc_src[eid]]
            nodes.append(arc_dst[eid])
            steps.append(eid)
    if nodes is not None and steps:
        routes.append((nodes, steps, False))
    return routes


def leaderboard(edges, min_count, top_n):
    """复刻后端 transition 榜单口径，用于标注榜内/榜外接续。"""
    total = sum(row['count'] for row in edges)
    outgoing = defaultdict(int)
    incoming = defaultdict(int)
    for row in edges:
        outgoing[row['from']] += row['count']
        incoming[row['to']] += row['count']
    scored = []
    for row in edges:
        if row['count'] < min_count:
            continue
        probability = row['count'] / outgoing[row['from']]
        base = incoming[row['to']] / total
        scored.append((-(probability / base), -row['count'], row['from'], row['to']))
    scored.sort()
    return {(a, b) for _, _, a, b in scored[:top_n]}


def _decompose_flow(node_count, arcs, used, supply, demand):
    """把亏空点到盈余点的净流拆成实测路径（边编号序列）。O(边数 + 路径数)。"""
    outgoing = [[] for _ in range(node_count)]
    for edge_id, amount in enumerate(used):
        if amount:
            outgoing[arcs[edge_id][0]].append(edge_id)
    cursor = [0] * node_count
    remaining_supply = [v for v, amount in supply.items() if amount]
    remaining_supply.sort()
    paths = []
    while remaining_supply:
        start = remaining_supply.pop()
        path = []
        v = start
        while True:
            if demand.get(v, 0) > 0:
                demand[v] -= 1
                break
            edges = outgoing[v]
            position = cursor[v]
            while position < len(edges) and used[edges[position]] <= 0:
                position += 1
            cursor[v] = position
            if position >= len(edges):
                raise RuntimeError('衔接路径分解失败：流量不守恒')
            edge_id = edges[position]
            used[edge_id] -= 1
            path.append(edge_id)
            v = arcs[edge_id][1]
        paths.append(path)
        supply[start] -= 1
        if supply[start] > 0:
            remaining_supply.append(start)
    return paths


def solve(catalog, min_count=None, top_n=None):
    """catalog 已按 (from,to) 去重。返回路线、逐条覆盖核对与汇总。"""
    edges = [{'from': row['from'], 'to': row['to'], 'count': row['count']} for row in catalog]
    if not edges:
        raise ValueError('接续目录为空，无法规划演练路线')
    names = sorted({row['from'] for row in edges} | {row['to'] for row in edges})
    index = {name: i for i, name in enumerate(names)}
    node_count = len(names)
    arcs = [(index[row['from']], index[row['to']]) for row in edges]

    outdeg = [0] * node_count
    indeg = [0] * node_count
    for a, b in arcs:
        outdeg[a] += 1
        indeg[b] += 1
    groups, comp_of = _components(node_count, arcs)

    edges_of = defaultdict(list)
    for edge_id, node in enumerate(a for a, _ in arcs):
        edges_of[comp_of[node]].append(edge_id)
    comps = []
    for members in groups:
        root = comp_of[members[0]]
        local_edges = edges_of.get(root, [])
        if not local_edges:
            continue
        surplus = {v: outdeg[v] - indeg[v] for v in members if outdeg[v] > indeg[v]}
        deficit = {v: indeg[v] - outdeg[v] for v in members if indeg[v] > outdeg[v]}
        comps.append({'members': members, 'edges': local_edges,
                      'surplus': surplus, 'deficit': deficit,
                      'P': sum(surplus.values())})

    merge_target = sum(max(0, comp['P'] - 1) for comp in comps)
    base = node_count
    for position, comp in enumerate(comps):
        comp['src'] = base + 2 * position
        comp['snk'] = base + 2 * position + 1
    source = base + 2 * len(comps)
    sink = source + 1
    network = _MinCostMaxFlow(sink + 1)
    real_edges = []
    terminals = []
    for comp in comps:
        if comp['P'] < 2:
            continue
        cap = comp['P'] - 1
        network.add(source, comp['src'], cap, 0)
        network.add(comp['snk'], sink, cap, 0)
        for v, amount in comp['deficit'].items():
            terminals.append(('deficit', v, network.add(comp['src'], v, amount, 0)))
        for v, amount in comp['surplus'].items():
            terminals.append(('surplus', v, network.add(v, comp['snk'], amount, 0)))
        for edge_id in comp['edges']:
            a, b = arcs[edge_id]
            if a != b:
                real_edges.append((edge_id, network.add(a, b, cap, 1)))
    flow, _ = network.run(source, sink, merge_target) if merge_target else (0, 0)

    used = [0] * len(arcs)
    for edge_id, reference in real_edges:
        used[edge_id] = network.graph[reference.to][reference.rev].cap
    supply = {}
    demand = {}
    for kind, v, reference in terminals:
        amount = network.graph[reference.to][reference.rev].cap
        if kind == 'deficit':
            supply[v] = amount
        else:
            demand[v] = amount
    supply = {v: a for v, a in supply.items() if a}
    demand = {v: a for v, a in demand.items() if a}
    deadheads = _decompose_flow(node_count, arcs, used, supply, demand)

    multiplicity = [1] * len(arcs)
    for path in deadheads:
        for edge_id in path:
            multiplicity[edge_id] += 1
    mult_adj = defaultdict(list)
    for edge_id, copies in enumerate(multiplicity):
        node = arcs[edge_id][0]
        for _ in range(copies):
            mult_adj[node].append(edge_id)

    routes = []
    for comp in comps:
        for nodes, steps, closed in _split_component(comp['members'], mult_adj, [a for a, _ in arcs], [b for _, b in arcs]):
            routes.append({'nodes': nodes, 'steps': steps, 'closed': closed})
    name_list = names
    routes.sort(key=lambda route: (name_list[route['nodes'][0]], len(route['steps']),
                                  [name_list[n] for n in route['nodes']]))

    walked = [0] * len(arcs)
    for route in routes:
        for edge_id in route['steps']:
            walked[edge_id] += 1
    board = set()
    if min_count is not None and top_n is not None:
        board = leaderboard(edges, min_count, top_n)
    coverage = []
    for edge_id, row in enumerate(edges):
        a, b = arcs[edge_id]
        coverage.append({'from': names[a], 'to': names[b], 'count': row['count'],
                         'walked': walked[edge_id], 'covered': walked[edge_id] > 0,
                         'on_board': (names[a], names[b]) in board})
    complete = all(item['covered'] for item in coverage)

    total_steps = sum(len(route['steps']) for route in routes)
    if total_steps != len(arcs) + sum(len(path) for path in deadheads):
        raise RuntimeError('路线步数与规划不一致')
    if flow > merge_target or flow < 0:
        raise RuntimeError('合并流量越界')

    result_routes = []
    for position, route in enumerate(routes, start=1):
        seen = set()
        steps_out = []
        for edge_id in route['steps']:
            a, b = arcs[edge_id]
            steps_out.append({'from': names[a], 'to': names[b],
                              'count': edges[edge_id]['count'],
                              'repeat': edge_id in seen})
            seen.add(edge_id)
        result_routes.append({'index': position,
                              'nodes': [names[n] for n in route['nodes']],
                              'steps': steps_out,
                              'closed': route['closed'],
                              'step_count': len(steps_out)})
    if not complete:
        raise RuntimeError('覆盖核对失败：存在未走到的实测接续')

    return {
        'routes': result_routes,
        'coverage': coverage,
        'summary': {
            'continuations': len(arcs),
            'routes': len(result_routes),
            'closed_routes': sum(1 for route in result_routes if route['closed']),
            'total_steps': total_steps,
            'unique_steps': len(arcs),
            'repeated_steps': total_steps - len(arcs),
            'merged': flow,
            'off_board_covered': sum(1 for item in coverage if not item['on_board'] and item['covered']),
            'off_board': sum(1 for item in coverage if not item['on_board']),
            'complete': complete,
        },
    }
