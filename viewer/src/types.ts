// Types for buildzr.model/2, buildzr.scene/2 and buildzr.index/2 (see buildzr/site/schema/*.json).

/** build.json next to index.html (buildzr/site/schema/build.schema.json); only what the viewer reads. */
export interface BuildInfo {
  status?: 'ok' | 'broken'; stage?: 'model' | 'layout' | 'check'; errors?: string[];
  workspace?: string; name?: string; input?: { file?: string };
}

export interface FileRef { file: string; hash: string }
export interface IndexJson { schema: 'buildzr.index/2'; modelHash: string; model: FileRef; scenes: Record<string, FileRef> }

export interface Element {
  id: string; modelId: string; type: string; parent: string | null; children: string[];
  name: string; description: string | null; technology: string | null; tags: string[];
  properties: Record<string, string>; url: string | null; group: string | null; views: string[];
  // deployment elements only
  environment?: string; instanceOf?: string; instances?: string;
  // custom elements (type Element) only, when they have metadata
  metadata?: string;
  healthChecks?: { name: string; url: string; interval: number | null; timeout: number | null }[];
}
export interface Environment { key: string; name: string; id: string; nodes: string[]; views: string[] }
export interface Relationship {
  id: string; modelId: string; source: string; destination: string;
  description: string | null; technology: string | null; tags: string[]; properties: Record<string, string>;
}
export interface ViewDef { key: string; viewKey?: string; kind: string; title: string; description?: string | null; scope: string | null; scene: string; environment?: string }
export interface ModelJson {
  schema: 'buildzr.model/2'; modelHash: string; workspace: { name: string; description?: string | null };
  elements: Element[]; relationships: Relationship[]; views: ViewDef[]; deployment: { environments: Environment[] };
}

export interface LabelLine { text: string; tier: 0 | 1 | 2; weight?: 'normal' | 'bold'; size?: number; italic?: boolean }
export interface Frame { scene: string; scale: number; children: number; childType?: string }
export interface NodeStyle { fill: string; stroke: string; color: string; fontSize: number; strokeWidth?: number; dash?: number[]; opacity?: number }
export interface SceneNode {
  id: string; modelId?: string; role: 'element' | 'boundary'; type: string; parent: string | null;
  x: number; y: number; w: number; h: number; shape: string; style: NodeStyle;
  label: { lines: LabelLine[]; anchor: 'center' | 'top' | 'bottom-left' | 'top-left' };
  tags: string[]; name: string; frame?: Frame; instances?: string;
}
export type Endpoint = string | { port: string };
export interface SceneEdge {
  id: string; source: Endpoint; target: Endpoint; points: [number, number][]; count: number; rels: string[];
  label?: { lines: LabelLine[]; x: number; y: number; w: number; h: number };
  style: { stroke: string; color?: string; width?: number; dash?: number[]; arrow: 'end' | 'start' | 'both' | 'none'; fontSize?: number; opacity?: number };
  order?: string | null;
}
export interface ScenePort { id: string; x: number; y: number; side: 'N' | 'E' | 'S' | 'W' }
export interface Scene {
  schema: 'buildzr.scene/2'; key: string; level: { kind: 'landscape' | 'element' | 'view'; scope: string | null };
  title: string; modelHash: string; bounds: [number, number, number, number]; ports: ScenePort[]; nodes: SceneNode[]; edges: SceneEdge[];
}
