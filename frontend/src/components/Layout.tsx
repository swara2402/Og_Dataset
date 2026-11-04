import { Outlet, NavLink } from 'react-router-dom';
import { 
  FileText, 
  Home, 
  BarChart3, 
  Settings, 
  Activity,
  XCircle
} from 'lucide-react';
import { useAPI } from '../contexts/APIContext';
import { useEffect } from 'react';

export default function Layout() {
  const { healthCheck, isConnected, isCheckingConnection, lastConnectionStatus } = useAPI();

  useEffect(() => {
    healthCheck();
    // Check connection status every 30 seconds
    const interval = setInterval(healthCheck, 30000);
    return () => clearInterval(interval);
  }, [healthCheck]);

  const navItems = [
    { to: '/', label: 'Dashboard', icon: Home },
    { to: '/document', label: 'Document Workspace', icon: FileText },
    { to: '/analysis', label: 'Analysis', icon: BarChart3 },
    { to: '/settings', label: 'Settings', icon: Settings },
  ];

  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="w-64 bg-white dark:bg-neutral-800 border-r border-neutral-200 dark:border-neutral-700 flex flex-col">
        <div className="p-6 border-b border-neutral-200 dark:border-neutral-700">
          <h1 className="text-xl font-bold text-primary-600 dark:text-primary-400">Your Helper</h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">Document Refinement Platform</p>
        </div>
        
        <nav className="flex-1 p-4">
          <ul className="space-y-2">
            {navItems.map(({ to, label, icon: Icon }) => (
              <li key={to}>
                <NavLink
                  to={to}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                      isActive
                        ? 'bg-primary-50 dark:bg-primary-900/20 text-primary-700 dark:text-primary-400'
                        : 'text-neutral-600 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-700'
                    }`
                  }
                >
                  <Icon size={20} />
                  <span>{label}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>

        {/* Connection status */}
        <div className="p-4 border-t border-neutral-200 dark:border-neutral-700">
          <div className="flex items-center gap-3">
            {isCheckingConnection ? (
              <Activity size={18} className="text-yellow-500 animate-pulse" />
            ) : isConnected ? (
              <Activity size={18} className="text-green-500" />
            ) : (
              <XCircle size={18} className="text-red-500" />
            )}
            <div>
              <p className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
                {isCheckingConnection ? 'Checking connection...' : isConnected ? 'All systems online' : 'Connection issues'}
              </p>
              {lastConnectionStatus && (
                <p className="text-xs text-neutral-500 dark:text-neutral-400">
                  Rule Engine: {lastConnectionStatus.services.rule_engine}
                </p>
              )}
            </div>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <div className="p-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}