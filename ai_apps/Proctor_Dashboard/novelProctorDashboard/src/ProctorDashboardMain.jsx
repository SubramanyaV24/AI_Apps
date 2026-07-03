import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import ProctorDashboard from './ProctorDashboard.jsx';
import './index.css';
import './proctorDashboardIndex.css';


export const BASE_PATH = import.meta.env.PROD ? '/novel-proctor-dashboard' : '';

document.documentElement.classList.add('dark');

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <Router
      basename={BASE_PATH}
      future={{
        v7_startTransition: true,
        v7_relativeSplatPath: true,
      }}
    >
      <Routes>
        <Route path="/" element={<ProctorDashboard />} />
      </Routes>
    </Router>
  </React.StrictMode>,
);
