import { createRoot } from 'react-dom/client';
import '@fontsource/inter/latin-400.css';
import '@fontsource/inter/latin-700.css';
import '@xyflow/react/dist/style.css';
import './app.css';
import { App } from './App';

createRoot(document.getElementById('root')!).render(<App />);
