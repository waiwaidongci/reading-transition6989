"""接受的编辑演练请求只有两种冻结输入：catalog（全部实测接续）或 sessions（全部会话原文）。"""
import math
def _text(value,label):
    if not isinstance(value,str) or not value.strip() or len(value.strip())>600:
        raise ValueError(label+'不能为空且最多600字符')
    return value.strip()
def _finite(value,label):
    if isinstance(value,bool):
        raise ValueError(label+'必须为有限数值')
    try:number=float(value)
    except (TypeError,ValueError):
        raise ValueError(label+'必须为有限数值')
    if not math.isfinite(number):raise ValueError(label+'必须为有限数值')
    return number
def normalize_catalog(rows):
    """五万种接续逐个受理：逐行校验，重复边合并计数，from==to 只允许作为实测自环保留。"""
    if not isinstance(rows,list) or not rows:
        raise ValueError('接续目录不能为空')
    merged={}
    for index,row in enumerate(rows):
        if not isinstance(row,dict):
            raise ValueError(f'第 {index+1} 条接续格式错误')
        unknown=set(row)-{'from','to','count'}
        if unknown:
            raise ValueError(f'第 {index+1} 条接续包含未知字段：'+','.join(sorted(unknown)))
        src=_text(row.get('from'),'当前章节')
        dst=_text(row.get('to'),'下一章节')
        count=_finite(row.get('count',1),'接续次数')
        if count<=0 or count!=int(count):
            raise ValueError('接续次数必须为正整数')
        if count>10**9:
            raise ValueError('接续次数过大')
        key=(src,dst)
        merged[key]=merged.get(key,0)+int(count)
        if len(merged)>50000:
            raise ValueError('接续种类超过 50000，请分批提交')
    if not merged:
        raise ValueError('接续目录不能为空')
    return [{'from':k[0],'to':k[1],'count':merged[k]} for k in sorted(merged)]
def parse_session_path(path):
    if not isinstance(path,str):
        raise ValueError('章节路径必须为文本')
    parts=[part.strip() for part in path.split('>')]
    if any(not part for part in parts) or len(parts)>80:
        raise ValueError('章节路径需1–80个非空章节，用>分隔')
    return parts
def normalize_sessions(rows):
    """把冻结会话逐条展开成相邻接续；同一会话内的相邻才计数，不跨会话拼接。"""
    if not isinstance(rows,list) or not rows:
        raise ValueError('会话不能为空')
    seen=set();merged={}
    for index,row in enumerate(rows):
        if not isinstance(row,dict):
            raise ValueError(f'第 {index+1} 条会话格式错误')
        unknown=set(row)-{'session','path'}
        if unknown:
            raise ValueError(f'第 {index+1} 条会话包含未知字段：'+','.join(sorted(unknown)))
        session=_text(row.get('session'),'匿名会话编号')
        if session in seen:raise ValueError('会话编号重复，请将一个完整会话保存在同一行')
        seen.add(session)
        path=parse_session_path(row.get('path'))
        for a,b in zip(path,path[1:]):
            merged[(a,b)]=merged.get((a,b),0)+1
    if not merged:
        raise ValueError('没有相邻章节转移；单章会话不形成接续边')
    if len(merged)>50000:
        raise ValueError('会话展开后的接续种类超过 50000，请分批提交')
    return [{'from':k[0],'to':k[1],'count':merged[k]} for k in sorted(merged)]
def fingerprint(edges):
    """目录指纹：排序后的实测接续与次数，用于覆盖核对与并发追加检测。"""
    import hashlib,json
    canonical=[{'from':edge['from'],'to':edge['to'],'count':edge['count']} for edge in sorted(edges,key=lambda e:(e['from'],e['to']))]
    return hashlib.sha256(json.dumps(canonical,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')).hexdigest()
