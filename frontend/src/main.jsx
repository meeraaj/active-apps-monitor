import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'

console.log("Main.jsx is running");

try {
  const rootElement = document.getElementById('root');
  if (!rootElement) throw new Error("Root element not found");
  
  ReactDOM.createRoot(rootElement).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  )
  console.log("React render called");
} catch (e) {
  console.error("React Mount Error:", e);
  document.body.innerHTML += `<div style="color:red">React Mount Error: ${e.message}</div>`;
}
