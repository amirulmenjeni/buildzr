import { createRoot } from 'react-dom/client';
import '@xyflow/react/dist/style.css';
import './app.css';
import { App } from './App';
import { installTheme } from './store';

installTheme();
createRoot(document.getElementById('root')!).render(<App />);
