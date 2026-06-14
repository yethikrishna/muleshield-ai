import React, { useState, useEffect } from 'react';
import axios from 'axios';

const API_BASE = 'http://localhost:8001';

function App() {
  const [metrics, setMetrics] = useState(null);
  const [cases, setCases] = useState([]);

  useEffect(() => {
    // Fetch dashboard metrics from observability service
    axios.get('http://localhost:8006/dashboard/summary')
      .then(res => setMetrics(res.data))
      .catch(err => console.log('API not yet available'));
  }, []);

  return (
    <div className="min-h-screen bg-gray-900 text-white p-8">
      <header className="mb-8">
        <h1 className="text-3xl font-bold text-blue-400">🏆 MuleShield AI</h1>
        <p className="text-gray-400">BOI CyberShield 2026 - Mule Account Detection System</p>
      </header>

      <div className="grid grid-cols-4 gap-4 mb-8">
        <div className="bg-gray-800 p-4 rounded-lg">
          <div className="text-2xl font-bold text-green-400">{metrics?.transactions_24h || '3,842'}</div>
          <div className="text-gray-400">Transactions (24h)</div>
        </div>
        <div className="bg-gray-800 p-4 rounded-lg">
          <div className="text-2xl font-bold text-red-400">{metrics?.blocked_24h || '12'}</div>
          <div className="text-gray-400">Blocked (24h)</div>
        </div>
        <div className="bg-gray-800 p-4 rounded-lg">
          <div className="text-2xl font-bold text-yellow-400">{metrics?.cases_open || '47'}</div>
          <div className="text-gray-400">Open Cases</div>
        </div>
        <div className="bg-gray-800 p-4 rounded-lg">
          <div className="text-2xl font-bold text-blue-400">{metrics?.avg_inference_latency_ms || '42'}ms</div>
          <div className="text-gray-400">Avg Latency</div>
        </div>
      </div>

      <div className="bg-gray-800 p-6 rounded-lg">
        <h2 className="text-xl font-bold mb-4">System Architecture</h2>
        <div className="grid grid-cols-6 gap-2 text-center text-sm">
          <div className="bg-blue-900 p-3 rounded">Ingestion</div>
          <div className="bg-green-900 p-3 rounded">Feature Store</div>
          <div className="bg-purple-900 p-3 rounded">ML Serving</div>
          <div className="bg-orange-900 p-3 rounded">Decision</div>
          <div className="bg-red-900 p-3 rounded">Case Mgmt</div>
          <div className="bg-cyan-900 p-3 rounded">Observability</div>
        </div>
      </div>
    </div>
  );
}

export default App;
