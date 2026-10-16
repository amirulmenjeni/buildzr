export interface LabelLine { text: string; weight?: 'normal' | 'bold'; size?: number; italic?: boolean }
export interface SceneNode {
  id: string; modelId: string; role: 'element' | 'boundary'; type: string; parent: string | null;
  x: number; y: number; w: number; h: number; shape: string; name: string;
  style: { fill: string; stroke: string; color: string; fontSize: number; strokeWidth?: number; dash?: number[]; opacity?: number };
  label: { lines: LabelLine[]; anchor: 'center' | 'bottom-left' | 'top-left' };
  tags: string[]; technology?: string; description?: string;
}
export interface SceneEdge {
  id: string; source: string; target: string; points: [number, number][];
  label?: { lines: LabelLine[]; x: number; y: number; w: number; h: number };
  style: { stroke: string; color?: string; width?: number; dash?: number[]; arrow: 'end' | 'start' | 'both' | 'none'; fontSize?: number; opacity?: number };
  tags: string[]; description?: string; technology?: string;
}
export interface Scene {
  view: string; kind: string; title: string; bounds: [number, number, number, number];
  nodes: SceneNode[]; edges: SceneEdge[];
}
export interface IndexEntry { view: string; title: string; kind: string; file: string }
