# rtl_fingerprint/rmmg/builder.py

from __future__ import annotations
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ..uhdm_compat import get_uhdm

uhdm, util = get_uhdm()

from .graph import RmmgGraph, RmmgNode

ASSIGN_TYPES = []
_KNOWN_WIDTHS: Dict[str, int] = {}
_SOURCE_CACHE: Dict[str, List[str]] = {}

# vpiAssignment 通常一定有

if hasattr(uhdm, "vpiAssignment"):
    ASSIGN_TYPES.append(uhdm.vpiAssignment)

for _name in ("vpiBlockingAssign", "vpiNonBlockingAssign"):
    _val = getattr(uhdm, _name, None)
    if _val is not None:
        ASSIGN_TYPES.append(_val)

def build_rmmg_from_design(design,
                           arch_visible_rules: Optional[List[Dict[str, str]]] = None
                           ) -> RmmgGraph:
    """
    给定 UHDM design，对整个设计构建一张“单图版” RMMG。
    - 精确恢复 width/kind
    - 组合 + 时序边
    - 节点附带 module_path / signal_name
    - 用简单规则打 is_arch_visible / is_micro_state
    """
    g = RmmgGraph()

    # 1) 遍历所有 module 实例
    module_count = 0
    for top in util.vpi_iterate_gen(uhdm.uhdmallModules, design):
        module_count += 1
        _build_instance_recursive(g, top)
    print(f"[RMMG]:visited {module_count} modules")
    # 2) 语义标注：micro_state / arch_visible
    _annotate_micro_state(g)
    if arch_visible_rules:
        _annotate_arch_visible(g, arch_visible_rules)

    return g

def _build_instance_recursive(g: RmmgGraph, inst) -> None:
    """
    inst: 某个 module 实例（带层次路径的那个对象）
    """
    _build_module_into_graph(g, inst)  # 这里的 mod 就是实例，不是 definition

    # 对该实例内部再递归处理下一级实例
    for child_inst in util.vpi_iterate_gen(uhdm.vpiModule, inst):
        _build_instance_recursive(g, child_inst)

# ==== Module 内构图逻辑 =====================================================

def _build_module_into_graph(g: RmmgGraph, mod) -> None:
    """把一个 module_inst 全部对象和依赖关系加到同一张图里。"""
    # 1) 端口
    for port in util.vpi_iterate_gen(uhdm.vpiPort, mod):
        _ensure_port_node(g, port)

    # 2) 内部 net / reg / memory
    for net in util.vpi_iterate_gen(uhdm.vpiNet, mod):
        _ensure_signal_node(g, net)
    for reg in util.vpi_iterate_gen(uhdm.vpiReg, mod):
        _ensure_signal_node(g, reg)
    for logic_var in util.vpi_iterate_gen(uhdm.vpiLogicVar, mod):
        _ensure_signal_node(g, logic_var)
    for mem in util.vpi_iterate_gen(uhdm.vpiMemory, mod):
        _ensure_signal_node(g, mem, kind_override="memory")

    # 3) 端口连接：把父模块 net 与子模块内部 net 通过 port 连起来
    _connect_port_bindings(g, mod)

    # 4) 连续赋值：组合依赖
    for ca in util.vpi_iterate_gen(uhdm.vpiContAssign, mod):
        _handle_cont_assign(g, ca)

    # 5) 过程赋值：组合 / 时序依赖
    for proc in util.vpi_iterate_gen(uhdm.vpiProcess, mod):
        _handle_process(g, proc)
    for alw in util.vpi_iterate_gen(uhdm.vpiAlways, mod):
        _handle_process(g, alw)

def _connect_port_bindings(g: RmmgGraph, mod) -> None:
    """
    对一个 module_inst，把它的 vpiPort 的 HighConn / LowConn 转成图边。
    这样可以把父模块信号和子模块内部信号桥接起来。
    """
    for port in util.vpi_iterate_gen(uhdm.vpiPort, mod):
        # 端口自己是一个节点
        port_name = _get_full_name(port)
        port_id = g.get_node_id(port_name)
        if port_id is None:
            port_id = _ensure_port_node(g, port)

        # HighConn: 父模块中的实际连接
        high = uhdm.vpi_handle(uhdm.vpiHighConn, port)
        high_id = None
        if high is not None:
            high_name = _get_full_name(high)
            if high_name:
                high_id = g.get_node_id(high_name)
                if high_id is None:
                    high_id = _ensure_signal_node(g, high)

        # LowConn: 子模块内部连到的 net（formal）
        low = uhdm.vpi_handle(uhdm.vpiLowConn, port)
        low_id = None
        if low is not None:
            low_name = _get_full_name(low)
            if low_name:
                low_id = g.get_node_id(low_name)
                if low_id is None:
                    low_id = _ensure_signal_node(g, low)

        # 根据方向加边
        dir_val = uhdm.vpi_get(uhdm.vpiDirection, port)

        # input: parent -> port -> child
        if dir_val == uhdm.vpiInput:
            if high_id is not None:
                g.add_edge(high_id, port_id, is_seq=False, cond=None, src_loc=None)
            if low_id is not None:
                g.add_edge(port_id, low_id, is_seq=False, cond=None, src_loc=None)

        # output: child -> port -> parent
        elif dir_val == uhdm.vpiOutput:
            if low_id is not None:
                g.add_edge(low_id, port_id, is_seq=False, cond=None, src_loc=None)
            if high_id is not None:
                g.add_edge(port_id, high_id, is_seq=False, cond=None, src_loc=None)

        # inout: 先双向全连，后续如果需要再精细化方向
        else:
            if high_id is not None:
                g.add_edge(high_id, port_id, is_seq=False, cond=None, src_loc=None)
                if low_id is not None:
                    g.add_edge(high_id, low_id, is_seq=False, cond=None, src_loc=None)
            if low_id is not None:
                g.add_edge(low_id, port_id, is_seq=False, cond=None, src_loc=None)
                if high_id is not None:
                    g.add_edge(low_id, high_id, is_seq=False, cond=None, src_loc=None)


# ==== 节点构建辅助 =========================================================

def _ensure_port_node(g: RmmgGraph, port) -> int:
    full_name = _get_full_name(port)
    if not full_name:
        high_conn = uhdm.vpi_handle(uhdm.vpiHighConn, port)
        full_name = _get_full_name(high_conn) or f"port@{id(port)}"

    dir_val = uhdm.vpi_get(uhdm.vpiDirection, port)
    if dir_val == uhdm.vpiInput:
        kind = "input"
    elif dir_val == uhdm.vpiOutput:
        kind = "output"
    else:
        kind = "inout"

    width = _get_width(port)
    if full_name:
        _KNOWN_WIDTHS[full_name] = width
    node_id = g.add_node(full_name, kind, width, uhdm_obj=port)

    # 在 builder 里拆 module_path / signal_name
    node = g.nodes[node_id]
    module_path, sig_name = _split_module_path(node.hier_name)
    node.attrs["module_path"] = module_path
    node.attrs["signal_name"] = sig_name

    return node_id

def _ensure_signal_node(g: RmmgGraph, obj, kind_override: Optional[str] = None) -> int:
    full_name = _get_full_name(obj)
    if not full_name:
        full_name = f"sig@{id(obj)}"

    if kind_override is not None:
        kind = kind_override
    else:
        t = uhdm.vpi_get(uhdm.vpiType, obj)
        if t == uhdm.vpiNet:
            if _has_unpacked_dims(obj):
                kind = "memory"
            else:
                kind = "logic" if _is_logic_decl(obj) else "net"
        elif t == uhdm.vpiReg:
            kind = "reg"
        elif t == uhdm.vpiLogicVar:
            kind = "logic"
        elif t == uhdm.vpiMemory:
            kind = "memory"
        else:
            kind = "internal"

    width = _get_width(obj)
    if full_name in _KNOWN_WIDTHS and (_KNOWN_WIDTHS[full_name] or 0) > max(width, 0):
        width = _KNOWN_WIDTHS[full_name]
    node_id = g.add_node(full_name, kind, width, uhdm_obj=obj)

    # 这里同样拆 module_path / signal_name
    node = g.nodes[node_id]
    module_path, sig_name = _split_module_path(node.hier_name)
    node.attrs["module_path"] = module_path
    node.attrs["signal_name"] = sig_name

    return node_id

def _get_full_name(obj) -> str:
    if obj is None:
        return ""
    try:
        name = uhdm.vpi_get_str(uhdm.vpiFullName, obj)
        if name:
            return name
    except Exception:
        pass
    try:
        name = uhdm.vpi_get_str(uhdm.vpiName, obj)
        return name or ""
    except Exception:
        return ""


def _split_module_path(hier_name: str) -> Tuple[str, str]:
    """把 work@ALUExeUnit.io_req_bits_addr 割成 (work@ALUExeUnit, io_req_bits_addr)。"""
    if not hier_name:
        return "", ""
    parts = hier_name.split(".")
    if len(parts) == 1:
        return "", hier_name
    return ".".join(parts[:-1]), parts[-1]

################# get width #########################


def _literal_to_int(value: str | None) -> int | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return int(text, 0)
    except ValueError:
        if "'" in text:
            _, encoded = text.split("'", 1)
            if not encoded:
                return None
            base_char = encoded[0].lower()
            digits = encoded[1:].replace("_", "")
            base_map = {"h": 16, "d": 10, "b": 2, "o": 8}
            base = base_map.get(base_char, 10)
            try:
                return int(digits or "0", base)
            except ValueError:
                return None
        return None


def _range_dim(r) -> int | None:
    if r is None:
        return None
    left = uhdm.vpi_handle(uhdm.vpiLeftRange, r)
    right = uhdm.vpi_handle(uhdm.vpiRightRange, r)
    lval = _literal_to_int(uhdm.vpi_get_str(uhdm.vpiDecompile, left))
    rval = _literal_to_int(uhdm.vpi_get_str(uhdm.vpiDecompile, right))
    if lval is None or rval is None:
        return None
    return abs(lval - rval) + 1


def _resolve_actual_typespec(ts):
    ref_type = getattr(uhdm, "vpiRefTypespec", None)
    actual_tag = getattr(uhdm, "vpiActualTypespec", None)
    seen: Set[int] = set()
    while ts is not None and ref_type is not None and \
            uhdm.vpi_get(uhdm.vpiType, ts) == ref_type and id(ts) not in seen:
        seen.add(id(ts))
        next_ts = uhdm.vpi_handle(uhdm.vpiActual, ts)
        if next_ts is None and actual_tag is not None:
            next_ts = uhdm.vpi_handle(actual_tag, ts)
        if next_ts is None:
            break
        ts = next_ts
    return ts


def _width_from_typespec(ts) -> int | None:
    """
    从 vpiTypespec 树计算拍扁后的 bit 宽度。
    覆盖常见几类：
      - logic_typespec
      - array_typespec（packed/unpacked 一视同仁，全部拍扁）
      - struct_typespec（字段宽度相加）
      - enum_typespec（看 base_typespec）
    拿不到就返回 None，由上层兜底。
    """
    if ts is None:
        return None

    ts = _resolve_actual_typespec(ts) or ts
    if ts is None:
        return None

    ttype = uhdm.vpi_get(uhdm.vpiType, ts)

    # 1) logic_typespec: 最常见的 scalar / vector
    if ttype == uhdm.vpiLogicTypespec:
        # 逻辑：如果有 range，就把所有维度相乘；没有 range 就认为是 1bit
        total = 1
        has_range = False
        for r in util.vpi_iterate_gen(uhdm.vpiRange, ts):
            has_range = True
            dim = _range_dim(r)
            if dim is None:
                return None
            total *= dim
        return total if has_range else 1

    # 2) array_typespec: packed/unpacked array
    if ttype == uhdm.vpiArrayTypespec:
        elem_ts = uhdm.vpi_handle(uhdm.vpiElemTypespec, ts)
        elem_w = _width_from_typespec(elem_ts) or 1

        total = elem_w
        for r in util.vpi_iterate_gen(uhdm.vpiRange, ts):
            dim = _range_dim(r)
            if dim is None:
                return None
            total *= dim
        return total

    # 3) struct_typespec: 所有字段宽度之和
    if ttype == uhdm.vpiStructTypespec:
        total = 0
        for member in util.vpi_iterate_gen(uhdm.vpiTypespecMember, ts):
            f_ts = uhdm.vpi_handle(uhdm.vpiTypespec, member)
            fw = _width_from_typespec(f_ts) or 0
            total += fw
        return total or None

    # 4) enum_typespec: 用 base_typespec 的宽度
    if ttype == uhdm.vpiEnumTypespec:
        base_ts = uhdm.vpi_handle(uhdm.vpiBaseTypespec, ts)
        return _width_from_typespec(base_ts)

    # 5) 其它类型：尝试用 vpiSize 兜底
    size = uhdm.vpi_get(uhdm.vpiSize, ts)
    if size not in (None, 0, -1):
        return int(size)

    return None

def _width_net_like(obj) -> int:
    """
    vpiNet / vpiReg / vpiLogicVar / vpiMemory 的宽度。
    优先使用 vpiTypespec，再用对象自己的 vpiRange/vpiSize 补充。
    """
    if obj is None:
        return 1

    # 某些连接是 reference，对应 actual 节点才带真正的宽度。
    actual = uhdm.vpi_handle(uhdm.vpiActual, obj)
    if actual is not None:
        return _width_net_like(actual)

    # 0) typespec 优先（解决 typedef/packed array/struct 等）
    ts = uhdm.vpi_handle(uhdm.vpiTypespec, obj)
    w = _width_from_typespec(ts)
    if w is not None and w > 0:
        return w

    obj_type = uhdm.vpi_get(uhdm.vpiType, obj)

    # 1) memory：看 element 类型的宽度
    if obj_type == uhdm.vpiMemory:
        elem = uhdm.vpi_handle(uhdm.vpiElement, obj)
        if elem is not None:
            return _width_net_like(elem)
        return 1

    # 2) 自己挂的 range（简单 logic [31:0] a; 之类）
    total = 1
    has_range = False
    for r in util.vpi_iterate_gen(uhdm.vpiRange, obj):
        has_range = True
        dim = _range_dim(r)
        if dim is None:
            has_range = False
            break
        total *= dim
    if has_range and total > 0:
        return total

    # 3) vpiSize 兜底
    size = uhdm.vpi_get(uhdm.vpiSize, obj)
    if size not in (None, 0, -1):
        return int(size)

    # 4) 源码兜底（ANSI 端口声明最常见）
    src_width = _width_from_source(obj)
    if src_width is not None and src_width > 0:
        return src_width

    # 5) 尝试通过 port 反推（input/output 没挂 typespec 的情况）
    via_port = _width_via_parent_port(obj)
    if via_port is not None and via_port > 0:
        return via_port

    # 6) 实在没有，当 1bit
    return 1


def _width_via_parent_port(obj) -> int | None:
    parent = uhdm.vpi_handle(uhdm.vpiParent, obj)
    if parent is None:
        return None

    target_name = _get_full_name(obj)
    for port in util.vpi_iterate_gen(uhdm.vpiPort, parent):
        for tag in (uhdm.vpiLowConn, uhdm.vpiHighConn):
            conn = uhdm.vpi_handle(tag, port)
            if conn is None:
                continue
            if conn is obj:
                return _width_port(port)
            conn_name = _get_full_name(conn)
            if target_name and conn_name == target_name:
                return _width_port(port)
            actual = uhdm.vpi_handle(uhdm.vpiActual, conn)
            if actual is obj:
                return _width_port(port)
            if target_name and actual is not None:
                actual_name = _get_full_name(actual)
                if actual_name == target_name:
                    return _width_port(port)
    return None


def _width_from_source(obj) -> int | None:
    text = _get_decl_line(obj)
    if text is None:
        return None

    # 尝试匹配 packed array 的 [msb:lsb]
    for match in re.finditer(r"\[(?P<msb>[^:\]]+):(?P<lsb>[^\]]+)\]", text):
        msb = _literal_to_int(match.group("msb"))
        lsb = _literal_to_int(match.group("lsb"))
        if msb is None or lsb is None:
            continue
        return abs(msb - lsb) + 1
    return None


def _get_decl_line(obj) -> Optional[str]:
    loc = _get_src_loc(obj)
    if loc is None:
        return None
    fname, line = loc
    try:
        lines = _SOURCE_CACHE.get(fname)
        if lines is None:
            lines = Path(fname).read_text().splitlines()
            _SOURCE_CACHE[fname] = lines
        if not (1 <= line <= len(lines)):
            return None
        return lines[line - 1]
    except Exception:
        return None


def _is_logic_decl(obj) -> bool:
    ts = uhdm.vpi_handle(uhdm.vpiTypespec, obj)
    ts = _resolve_actual_typespec(ts)
    if ts is None:
        return False
    return uhdm.vpi_get(uhdm.vpiType, ts) == getattr(uhdm, "vpiLogicTypespec", None)


def _has_unpacked_dims(obj) -> bool:
    text = _get_decl_line(obj)
    if text is None:
        return False
    brackets = list(re.finditer(r"\[[^\]]+\]", text))
    return len(brackets) >= 2


_PORT_RESOLVE_GUARD: Set[int] = set()


def _guard_key(obj) -> int:
    name = _get_full_name(obj)
    if name:
        return hash(name)
    try:
        uid = uhdm.vpi_get(getattr(uhdm, "vpiUniqueId", 0), obj)
        if uid not in (None, 0):
            return int(uid)
    except Exception:
        pass
    return id(obj)


def _width_port(port) -> int:
    """
    端口位宽计算优先级：
      1) port 自己的 typespec
      2) lowConn / highConn 指向的 net/reg/port
      3) port 自己的 range/size
      4) fallback = 1
    """
    if port is None:
        return 1

    key = _guard_key(port)
    if key in _PORT_RESOLVE_GUARD:
        return 1

    _PORT_RESOLVE_GUARD.add(key)
    try:
        # 1) 端口自身的 typespec（标准 1800-2017 推荐的写法）
        ts = uhdm.vpi_handle(uhdm.vpiTypespec, port)
        w_ts = _width_from_typespec(ts)
        if w_ts is not None and w_ts > 0:
            return w_ts

        src_width = _width_from_source(port)
        if src_width is not None and src_width > 0:
            return src_width

        # 2) lowConn / highConn（连接到内部 net/reg 或上级信号）
        for tag in (uhdm.vpiLowConn, uhdm.vpiHighConn):
            conn = uhdm.vpi_handle(tag, port)
            if conn is None:
                continue
            c_type = uhdm.vpi_get(uhdm.vpiType, conn)
            if c_type == uhdm.vpiPort:
                cw = _width_port(conn)
            else:
                cw = _width_net_like(conn)
            if cw is not None and cw > 0:
                return cw

        # 3) port 自身的 range/size
        total = 1
        has_range = False
        for r in util.vpi_iterate_gen(uhdm.vpiRange, port):
            has_range = True
            dim = _range_dim(r)
            if dim is None:
                has_range = False
                break
            total *= dim
        if has_range and total > 0:
            return total

        size = uhdm.vpi_get(uhdm.vpiSize, port)
        if size not in (None, 0, -1):
            return int(size)

        src_width = _width_from_source(port)
        if src_width is not None and src_width > 0:
            return src_width

        # 4) 全部失败，当 scalar
        return 1
    finally:
        _PORT_RESOLVE_GUARD.discard(key)

def _get_width(obj) -> int:
    """
    RMMG 中统一的“对象宽度”查询接口。
    - vpiPort              -> _width_port
    - vpiNet/Reg/Logic/Mem -> _width_net_like
    - 其它                 -> 1bit 兜底
    """
    if obj is None:
        return 1

    obj_type = uhdm.vpi_get(uhdm.vpiType, obj)

    if obj_type == uhdm.vpiPort:
        return _width_port(obj)

    if obj_type in (uhdm.vpiNet, uhdm.vpiReg, uhdm.vpiLogicVar, uhdm.vpiMemory):
        return _width_net_like(obj)

    return 1



# ==== 连续赋值（组合边） ====================================================

def _handle_cont_assign(g: RmmgGraph, ca) -> None:
    lhs = uhdm.vpi_handle(uhdm.vpiLhs, ca)
    rhs = uhdm.vpi_handle(uhdm.vpiRhs, ca)
    if lhs is None or rhs is None:
        return

    dst_name = _get_full_name(lhs)
    dst_id = g.get_node_id(dst_name)
    if dst_id is None:
        dst_id = _ensure_signal_node(g, lhs)

    # 遍历 RHS 表达式叶子，建 src → dst 的组合边
    for src_obj in _iter_expr_leaves(rhs):
        src_name = _get_full_name(src_obj)
        src_id = g.get_node_id(src_name)
        if src_id is None:
            src_id = _ensure_signal_node(g, src_obj)
        g.add_edge(src_id, dst_id, is_seq=False, cond=None,
                   src_loc=_get_src_loc(ca))


# ==== 过程赋值（组合 / 时序边） ============================================

def _handle_process(g: RmmgGraph, proc) -> None:
    """
    对 vpiProcess / vpiAlways：
    - 判定是否 clocked（时序过程）
    - 遍历内部 stmt 树，找赋值语句，建 is_seq = True/False 的边
    """
    is_seq, clock_name = _is_clocked_process(proc)

    stmt = uhdm.vpi_handle(uhdm.vpiStmt, proc)
    if stmt is None:
        return
    _traverse_stmt_for_assign(g, stmt, is_seq=is_seq, clock_name=clock_name)


def _is_clocked_process(proc) -> Tuple[bool, Optional[str]]:
    """
    基于 surelog.dump 结构：
    vpiProcess
      |_ vpiStmt = _event_control
           |_ vpiCondition = _operation (opType: posedge/negedge)
                |_ vpiOperand = ref clock
    """
    stmt = uhdm.vpi_handle(uhdm.vpiStmt, proc)
    if stmt is None:
        return False, None

    if uhdm.vpi_get(uhdm.vpiType, stmt) != uhdm.vpiEventControl:
        return False, None

    cond = uhdm.vpi_handle(uhdm.vpiCondition, stmt)
    if cond is None or uhdm.vpi_get(uhdm.vpiType, cond) != uhdm.vpiOperation:
        return False, None

    op_type = uhdm.vpi_get(uhdm.vpiOpType, cond)
    # 有的 binding 可能没有 vpiPosedgeOp 枚举，可以直接比数字（在 surelog.dump 中查到）
    try:
        is_edge = op_type in (uhdm.vpiPosedgeOp, uhdm.vpiNegedgeOp)
    except AttributeError:
        # 兜底写法：在 surelog.dump 中查到 posedge 的 opType 是 39，就这么写
        is_edge = (op_type == 39)

    if not is_edge:
        return False, None

    clock_ref = uhdm.vpi_handle(uhdm.vpiOperand, cond)
    clock_name = _get_full_name(clock_ref)
    return True, clock_name or None


def _traverse_stmt_for_assign(g: RmmgGraph,
                              stmt,
                              is_seq: bool,
                              clock_name: Optional[str]) -> None:
    """
    在 stmt 树中找赋值语句（blocking/non-blocking），生成边。
    只关注数据依赖，不展开条件逻辑（condition 可以以后再加到 edge 上）。
    """
    if stmt is None:
        return

    t = uhdm.vpi_get(uhdm.vpiType, stmt)

    # assignment
    if t in ASSIGN_TYPES:
        lhs = uhdm.vpi_handle(uhdm.vpiLhs, stmt)
        rhs = uhdm.vpi_handle(uhdm.vpiRhs, stmt)
        if lhs is None or rhs is None:
            return

        dst_name = _get_full_name(lhs)
        dst_id = g.get_node_id(dst_name)
        if dst_id is None:
            dst_id = _ensure_signal_node(g, lhs)

        # 时序过程里的 LHS，标记为 micro_state 候选
        if is_seq:
            node = g.nodes[dst_id]
            node.attrs["seq"] = True
            if clock_name:
                node.attrs["clock"] = clock_name

        for src_obj in _iter_expr_leaves(rhs):
            src_name = _get_full_name(src_obj)
            src_id = g.get_node_id(src_name)
            if src_id is None:
                src_id = _ensure_signal_node(g, src_obj)
            g.add_edge(src_id, dst_id, is_seq=is_seq,
                       cond=None,  # TODO: 以后加 if/case 条件
                       src_loc=_get_src_loc(stmt))
        return

    # 容器语句：begin / if / case / for / while 等，递归子 stmt
    for child in _iter_stmt_children(stmt):
        _traverse_stmt_for_assign(g, child, is_seq=is_seq, clock_name=clock_name)


def _iter_stmt_children(stmt) -> Iterable:
    """根据 surelog.dump 的典型结构，枚举子语句。这里只覆盖最常见的几种，够用即可。"""
    t = uhdm.vpi_get(uhdm.vpiType, stmt)

    # begin / block
    if t == uhdm.vpiBegin:
        it = uhdm.vpi_iterate(uhdm.vpiStmt, stmt)
        while True:
            s = uhdm.vpi_scan(it)
            if s is None:
                break
            yield s
        return

    # if
    if t == uhdm.vpiIf:
        then_stmt = uhdm.vpi_handle(uhdm.vpiStmt, stmt)
        else_stmt = uhdm.vpi_handle(uhdm.vpiElseStmt, stmt)
        if then_stmt is not None:
            yield then_stmt
        if else_stmt is not None:
            yield else_stmt
        return

    # case（多分支）
    if t == uhdm.vpiCase:
        for ci in util.vpi_iterate_gen(uhdm.vpiCaseItem, stmt):
            cs = uhdm.vpi_handle(uhdm.vpiStmt, ci)
            if cs is not None:
                yield cs
        return

    # 其他 stmt 类型可以按需后续补充
    return


# ==== 表达式叶子遍历 =======================================================

def _iter_expr_leaves(expr) -> Iterable:
    """
    遍历 RHS 表达式树的“叶子对象”：
    - constant
    - ref_obj / bit-select / part-select / var-select
    这里采用保守策略：bit-select/part-select 本身也当作一个 leaf，
    其 fullName 一般包含索引信息（方便后续做 index/mapping 分析）。
    """
    if expr is None:
        return

    t = uhdm.vpi_get(uhdm.vpiType, expr)

    # 常量
    if t == uhdm.vpiConstant:
        yield expr
        return

    # 对象引用 / 选择
    if t in (uhdm.vpiRefObj,
             uhdm.vpiNetBit,
             uhdm.vpiRegBit,
             uhdm.vpiBitSelect,
             uhdm.vpiPartSelect,
             uhdm.vpiVarSelect):
        yield expr
        return

    # 运算表达式：递归 operands
    if t == uhdm.vpiOperation:
        for opnd in util.vpi_iterate_gen(uhdm.vpiOperand, expr):
            for leaf in _iter_expr_leaves(opnd):
                yield leaf
        return

    # 其他类型：保守起见，当成 leaf（至少不会丢依赖），以后再精细化
    yield expr


def _get_src_loc(obj) -> Optional[Tuple[str, int]]:
    """从 UHDM 对象上提取 (file, line) 源位置，用于 debug / 消融。"""
    if obj is None:
        return None
    try:
        fname = uhdm.vpi_get_str(uhdm.vpiFile, obj)
        line = uhdm.vpi_get(uhdm.vpiLineNo, obj)
        if fname:
            return (fname, int(line or 0))
    except Exception:
        return None
    return None


# ==== 语义标注：micro_state / arch_visible =================================

def _annotate_micro_state(g: RmmgGraph) -> None:
    """
    粗粒度 micro_state 标记：
    - 写入于时序过程的 reg/memory 节点
    - 排除 clock/reset 等明显不是状态的信号
    """
    for node in g.nodes.values():
        # 默认 False
        node.attrs.setdefault("is_micro_state", False)

    for node in g.nodes.values():
        if node.kind in ("reg", "memory", "logic"):
            # 使用刚才在 process 中记录的 seq 标记
            if node.attrs.get("seq", False) and node.width != 1:
                name_l = node.hier_name.lower()
                if not any(x in name_l for x in ("clock", "clk", "reset", "rst")):
                    node.attrs["is_micro_state"] = True


def _annotate_arch_visible(g: RmmgGraph,
                           rules: List[Dict[str, str]]) -> None:
    """
    简单的 rule-based arch_visible 标记。
    rules 例子：
      - {"type": "prefix", "value": "DigitalTop.tile_prci_domain.boom_tile.core.io_commit"}
      - {"type": "regex",  "value": ".*io_dmem_.*"}
    """
    import re

    compiled = []
    for r in rules:
        if r["type"] == "prefix":
            compiled.append(("prefix", r["value"]))
        elif r["type"] == "regex":
            compiled.append(("regex", re.compile(r["value"])))
        else:
            continue

    for node in g.nodes.values():
        name = node.hier_name
        is_vis = False
        for t, val in compiled:
            if t == "prefix" and name.startswith(val):
                is_vis = True
                break
            if t == "regex" and val.match(name):
                is_vis = True
                break
        node.attrs["is_arch_visible"] = is_vis
