// What the export menu (in the header) needs from the canvas (a React Flow tree further down): the drawing that is on screen.
import { create } from 'zustand';
import type { Composed } from './compose';

export const useDiagram = create<{ composed: Composed | null }>(() => ({ composed: null }));
