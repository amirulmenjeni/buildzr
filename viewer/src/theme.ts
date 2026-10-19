// Light and dark theme: the resolved theme. The embed's parent page can force it (embed.ts).
import type { ThemeChoice } from './protocol';

export type Theme = 'light' | 'dark';

export const resolveTheme = (choice: ThemeChoice, prefersDark: boolean): Theme =>
  choice === 'system' ? (prefersDark ? 'dark' : 'light') : choice;
