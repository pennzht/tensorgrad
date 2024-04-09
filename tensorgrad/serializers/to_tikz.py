from collections import defaultdict
from tensorgrad.tensor import Product, Zero, Copy, Variable, Sum, Function
import random
import re

# layout_style = "layered layout"
# layout_style = "spring layout"
layout_style = "tree layout"


def format_label(label):
    suffix = re.search("(_*)$", label).group(1)
    if len(suffix) > 0:
        label = label[: -len(suffix)] + "'" * len(suffix)

    def replacement(match):
        digits = match.group(0)
        return "_" + "{" + ",".join(filter(None, digits.split("_"))) + "}"

    if re.search(r"(_+\d+){2}$", label):
        print("before", label)
        label = re.sub(r"(_+\d+)+$", replacement, label)
        print("after", label)

    style = ""
    if "D_" in label:
        label = re.sub("D_[\d+]", "", label, count=1)
        style = "double"

    return label, style


# Sum(
#     [
#         Product(
#             [
#                 Variable(X, ["b", "x"], ["b_", "x_"]),
#                 Sum(
#                     [
#                         Product([Variable(W, ["x", "y"], ["x", "y_"]), Variable(X, ["b", "x"], ["b_", "x"])]),
#                         Variable(Y, ["b", "y"], ["b_", "y_"]),
#                     ],
#                     (1, -1),
#                 ),
#             ]
#         )
#     ],
#     (2,),
# )


class TikzGraph:
    def __init__(self):
        self.lines = []
        self.node_ids = set()

    def add_node(self, node_id, node_type, label=None):
        # print(f"adding node {node_id} of type {node_type} with label {label}")
        node_id = node_id.replace("_", "+")
        if node_id in self.node_ids:
            print("Warning: Node already exists. Ignoring")
            return
        self.node_ids.add(node_id)
        if label is not None:
            label, extra_style = format_label(label)
        else:
            label, extra_style = "", ""
        if node_type == "identity":
            self.lines.append(f"  {node_id}[identity,as=\\tiny{{\\textbullet}}];")
        elif node_type == "var":
            self.lines.append(f"  {node_id}[var,as=${label}$];")
        elif node_type == "zero":
            self.lines.append(f"  {node_id}[zero,as=0];")
        elif node_type == "function":
            self.lines.append(f"  {node_id}[function,as=${label}$,style={{{extra_style}}}];")
        elif node_type == "invisible":
            self.lines.append(f"  {node_id}[style={{}},as=];")
        else:
            self.lines.append(f"  {node_id}[as=${label}$];")

    def add_edge(self, id1, id2, label, directed=False):
        # print(f"adding edge ({id1}) -> ({id2}) with label {label}")
        id1 = id1.replace("_", "+")
        id2 = id2.replace("_", "+")
        if isinstance(label, str):
            label, _style = format_label(label)
        assert id1 in self.node_ids, f"Node {id1} does not exist in {self.node_ids}"
        assert id2 in self.node_ids, f"Node {id2} does not exist in {self.node_ids}"
        edge_type = " -> " if directed else " -- "
        self.lines.append(f'    ({id1}){edge_type}["${label}$"] ({id2}),')

    def add_subgraph(self, subgraph, definition: str, cluster_id: str):
        self.lines.append(f"{definition}{{")
        self.lines += subgraph.lines
        self.lines.append("},")
        self.node_ids |= subgraph.node_ids
        self.node_ids.add(cluster_id)

    def to_tikz(self):
        return "\n".join(self.lines)


def to_tikz(tensor):
    prefix = """
    \\documentclass[tikz]{standalone}
    \\usetikzlibrary{graphs, graphdrawing, quotes}
    \\usegdlibrary{trees, layered, force}
    \\begin{document}
    \\tikz[
        every node/.style={
            font=\\scriptsize,
            inner sep=2pt,
        },
        identity/.style={circle, draw=black, fill=white, inner sep=0pt, minimum size=4pt},
        var/.style={circle, draw=black, fill=white, inner sep=2pt},
        zero/.style={rectangle, draw=black, fill=white, inner sep=2pt},
        function/.style={circle, draw=black, fill=white, inner sep=2pt},
        subgraph nodes={draw=gray, rounded corners},
        subgraph text none,
    ]
    \\graph [
    """
    if layout_style == "tree layout":
        prefix += """\
            tree layout,
            fresh nodes,
            grow' = right,
            sibling sep=3em,
        """
    if layout_style == "layered layout":
        prefix += """\
            layered layout,
            fresh nodes,
            grow=right,
            components go down left aligned,
        """
    else:
        prefix += """\
            spring layout,
            node distance=1cm,
            node sep=1cm,
            spring constant=0.01,
            fresh nodes,
            nodes behind edges,
        """
    prefix += """] {"""

    tikz_code = [prefix]
    graph = TikzGraph()
    free_edges = _to_tikz(tensor, graph)
    # print("final free edges", free_edges)
    if not isinstance(tensor, Sum):
        # Sum handles free edges itself
        handle_free_edges(free_edges, graph)

    tikz_code.append(graph.to_tikz())
    tikz_code.append("};")
    tikz_code.append("\\end{document}")
    return "\n".join(tikz_code)


def count_components(con: Product):
    # Counts the individual components of a contraction,
    # that is, subgraphs that are not connected by an edge
    edges = defaultdict(list)
    for t in con.tensors:
        for e in t.edges:
            edges[e].append(t)
    colors = {}
    queue = list(con.tensors)
    while queue:
        t = queue.pop()
        if id(t) not in colors:
            colors[id(t)] = len(colors)
        for e in t.edges:
            for v in edges[e]:
                if id(v) not in colors:
                    colors[id(v)] = colors[id(t)]
                    queue.append(v)
    return max(colors.values()) + 1


def handle_free_edges(free_edges, graph):
    for e, node_id in free_edges.items():
        graph.add_node(f"{node_id}_{e}", "invisible")
        graph.add_edge(node_id, f"{node_id}_{e}", label=e)


def _to_tikz(tensor, graph):
    if isinstance(tensor, Copy):
        graph.add_node(node_id := str(id(tensor)), "identity")
        return {e: node_id for e in tensor.edges}

    if isinstance(tensor, Variable):
        # Not actually any reason to use node_id here.
        # In fact, we often want to use multiple nodes for the same variable,
        # as we'd otherwise end up combining tensors that should added.
        node_id = str(random.randrange(2**64))
        graph.add_node(node_id, "var", label=tensor.name)
        return {e: node_id for e in tensor.edges}

    if isinstance(tensor, Zero):
        graph.add_node(node_id := str(id(tensor)), "zero")
        return {e: node_id for e in tensor.edges}

    if isinstance(tensor, Function):
        node_id = str(id(tensor))
        subgraph = TikzGraph()

        subgraph.add_node(node_id, "function", label=tensor.name)

        free_edges = {}
        for t, *es in tensor.inputs:
            edges = _to_tikz(t, subgraph)
            for e in es:
                sub_id = edges.pop(e)
                subgraph.add_edge(sub_id, node_id, label=e, directed=True)
            # Add remaining edges to free edges.
            # Note: The Function should have made sure there is no edge overlap here
            assert not (edges.keys() & free_edges.keys())
            free_edges |= edges

        graph.add_subgraph(
            subgraph,
            f"cluster_{node_id} // [tree layout]",
            f"cluster_{node_id}",
        )

        # We propagate the free edges to the parent to handle
        return {e: node_id for e in tensor.edges} | free_edges

    if isinstance(tensor, Product):
        # subgraph = TikzGraph()

        sub_ids = defaultdict(list)  # edge -> [sub_id1, sub_id2]
        for t in tensor.tensors:
            for e, sub_id in _to_tikz(t, graph).items():
                sub_ids[e].append(sub_id)

        # Handle contractions (edges with multiple sub_ids)
        for e, ts in sub_ids.items():
            assert len(ts) <= 2, "Shouldn't happen"
            if len(ts) == 2:
                sub_id1, sub_id2 = ts
                graph.add_edge(sub_id1, sub_id2, label=e)

        # graph.add_subgraph(
        #     subgraph, f"{str(id(tensor))} / [inner sep=10pt] // [{layout_style}]", str(id(tensor))
        # )

        free = {e: ids[0] for e, ids in sub_ids.items() if len(ids) == 1}
        # print(f"{tensor=}")
        # print(f"{sub_ids=}")
        # print(f"{free=}")
        return free

    if isinstance(tensor, Sum):
        cluster_id = str(id(tensor))
        subgraph = TikzGraph()
        free_edges = {}
        for i, (w, t) in enumerate(zip(tensor.weights, tensor.tensors)):
            subsubgraph = TikzGraph()
            subgraph_edges = _to_tikz(t, subsubgraph)
            handle_free_edges(subgraph_edges, subsubgraph)
            free_edges |= subgraph_edges
            if isinstance(t, Product) and count_components(t) > 1:
                style = ""
            else:
                style = ", draw=none"
            subgraph.add_subgraph(
                subsubgraph,
                f"{cluster_id}+{i}/[label={{[anchor=east, scale=2]left:${format_weight(w)}$}} {style}] // [tree layout]",
                f"{cluster_id}+{i}",
            )

        graph.add_subgraph(subgraph, f"{cluster_id} / [inner sep=10pt] // [tree layout]", cluster_id)
        return {e: cluster_id for e in free_edges.keys()}

    assert False, "Unknown tensor type"


def format_weight(w):
    if w == 1:
        return "+"
    if w == -1:
        return "-"
    if w > 0:
        return f"+{w}"
    return str(w)