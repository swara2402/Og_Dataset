import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import DocumentWorkspace from './pages/DocumentWorkspace'
import AnalysisPage from './pages/AnalysisPage'
import Settings from './pages/Settings'
import { APIProvider } from './contexts/APIContext'

function App() {
  return (
    <APIProvider>
      <div className="min-h-screen">
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/document/:jobId?" element={<DocumentWorkspace />} />
            <Route path="/analysis" element={<AnalysisPage />} />
            <Route path="/analysis/:jobId" element={<AnalysisPage />} />
            <Route path="/settings" element={<Settings />} />
          </Route>
        </Routes>
      </div>
    </APIProvider>
  )
}

export default App