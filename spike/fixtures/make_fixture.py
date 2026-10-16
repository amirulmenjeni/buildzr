"""Writes the HAND-WRITTEN fixture aws-mini.scene.json (no ELK involved).

A trimmed AWS deployment view (region ap-southeast-1 only): 4 levels of nesting,
3 edges, 2 of them crossing boundaries, one with a bend. Geometry was placed by
hand so that the viewer (worker B) can start before the ELK pipeline exists.
Run: python3 -I spike/fixtures/make_fixture.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
from scene_io import rnd, write  # noqa: E402

AWS = "live/amazon-web-services"
REG = AWS + "/ap-southeast-1"
ASG = REG + "/autoscaling-group"
EC2 = ASG + "/amazon-ec2-ubuntu-server"
RDS = REG + "/amazon-rds"
SQL = RDS + "/mysql"

BOUNDARY_STYLE = {"fill": "#ffffff", "stroke": "#888888", "color": "#000000", "fontSize": 13, "dash": [6, 4]}
INFRA_STYLE = {"fill": "#dddddd", "stroke": "#9a9a9a", "color": "#000000", "fontSize": 14}
CONTAINER_STYLE = {"fill": "#ffffff", "stroke": "#9a9a9a", "color": "#000000", "fontSize": 14}


def boundary(id_, model_id, parent, name, tech, tags, x, y, w, h):
    return {
        "id": id_, "modelId": model_id, "role": "boundary", "type": "DeploymentNode", "parent": parent,
        "x": rnd(x), "y": rnd(y), "w": rnd(w), "h": rnd(h), "shape": "Box", "style": BOUNDARY_STYLE,
        "label": {"anchor": "bottom-left", "lines": [
            {"text": name, "weight": "bold"},
            {"text": f"[Deployment Node{': ' + tech if tech else ''}]", "size": 11}]},
        "tags": ["Element", "Deployment Node", *tags], "name": name,
    }


def element(id_, model_id, parent, type_, kind, name, tech, desc, tags, shape, style, x, y, w, h, desc_lines=()):
    n = {
        "id": id_, "modelId": model_id, "role": "element", "type": type_, "parent": parent,
        "x": rnd(x), "y": rnd(y), "w": rnd(w), "h": rnd(h), "shape": shape, "style": style,
        "label": {"anchor": "center", "lines": [
            {"text": name, "weight": "bold"},
            {"text": f"[{kind}{': ' + tech if tech else ''}]", "size": 12},
            *({"text": t, "size": 12} for t in desc_lines)]},
        "tags": tags, "name": name, "lod": {"detail": ["name", "type", "description"]},
    }
    if tech:
        n["technology"] = tech
    if desc:
        n["description"] = desc
    return n


nodes = [
    boundary(AWS, "11", None, "Amazon Web Services", "", ["Amazon Web Services - Cloud"], 12, 12, 1176, 520),
    boundary(REG, "12", AWS, "ap-southeast-1", "", ["Amazon Web Services - Region"], 32, 32, 1136, 470),
    boundary(RDS, "19", REG, "Amazon RDS", "", ["Amazon Web Services - RDS Instance"], 872, 52, 276, 250),
    boundary(SQL, "20", RDS, "MySQL", "", ["Amazon Web Services - RDS MySQL instance"], 892, 72, 236, 200),
    element(SQL + "/database-schema", "21", SQL, "ContainerInstance", "Container", "Database Schema", "", "",
            ["Container Instance"], "Cylinder", CONTAINER_STYLE, 900, 102, 220, 120),
    boundary(ASG, "16", REG, "Autoscaling Group", "", ["Amazon Web Services - Autoscaling Group"], 332, 52, 360, 250),
    boundary(EC2, "17", ASG, "Amazon EC2 - Ubuntu Server", "", ["Amazon Web Services - EC2 Instance"], 352, 72, 320, 200),
    element(EC2 + "/web-application", "18", EC2, "ContainerInstance", "Container", "Web Application",
            "Java and Spring boot", "", ["Container Instance"], "Box", CONTAINER_STYLE, 402, 102, 220, 120),
    element(REG + "/dns-router", "13", REG, "InfrastructureNode", "Infrastructure Node", "DNS Router", "Route 53",
            "Routes incoming requests based upon domain name.",
            ["Element", "Infrastructure Node", "Amazon Web Services - Route 53"], "Box", INFRA_STYLE, 62, 72, 220, 120,
            desc_lines=("Routes incoming requests based", "upon domain name.")),
    element(REG + "/load-balancer", "14", REG, "InfrastructureNode", "Infrastructure Node", "Load Balancer",
            "Elastic Load Balancer", "Automatically distributes incoming application traffic.",
            ["Element", "Infrastructure Node", "Amazon Web Services - Elastic Load Balancer"], "Box", INFRA_STYLE,
            62, 332, 220, 120, desc_lines=("Automatically distributes", "incoming application traffic.")),
]

EDGE_STYLE = {"stroke": "#707070", "arrow": "end", "dash": [5, 5]}


def edge(src, dst, model_id, desc, tech, points, lx, ly, lw, lh):
    lines = [{"text": desc, "size": 12}]
    if tech:
        lines.append({"text": f"[{tech}]", "size": 11})
    e = {
        "id": f"{src}->{dst}", "modelId": model_id, "source": src, "target": dst,
        "points": [[rnd(x), rnd(y)] for x, y in points],
        "label": {"lines": lines, "x": rnd(lx), "y": rnd(ly), "w": rnd(lw), "h": rnd(lh)},
        "style": EDGE_STYLE, "tags": ["Relationship"], "description": desc, "order": None,
    }
    if tech:
        e["technology"] = tech
    return e


edges = sorted([
    edge(REG + "/dns-router", REG + "/load-balancer", "15", "Fowards requests to", "HTTP",
         [(172, 192), (172, 332)], 180, 246, 130, 32),
    edge(REG + "/load-balancer", EC2 + "/web-application", "22", "Forwards requests to", "",
         [(282, 392), (307, 392), (307, 162), (402, 162)], 290, 310, 130, 18),
    edge(EC2 + "/web-application", SQL + "/database-schema", "23", "Reads from and writes to", "",
         [(622, 162), (900, 162)], 702, 138, 160, 18),
], key=lambda e: e["id"])

scene = {
    "schema": "buildzr.scene/1", "view": "aws-mini", "kind": "deployment",
    "title": "AWS deployment (hand-written fixture)",
    "description": "Hand-placed fixture for viewer development; not produced by ELK.",
    "modelHash": "sha256:unknown",
    "layout": {"engine": "hand", "version": "0", "inputHash": "sha256:unknown", "direction": "RIGHT"},
    "bounds": [0, 0, 1200, 544],
    "nodes": nodes, "edges": edges,
}

if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aws-mini.scene.json")
    write(out, scene)
    print(out)
