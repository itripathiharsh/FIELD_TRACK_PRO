import React, { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { Layout } from './components/layout/Layout';
import { LoginPage } from './pages/LoginPage';
import { DashboardPage } from './pages/DashboardPage';
import { EmployeesPage } from './pages/EmployeesPage';
import { TerritoriesPage } from './pages/TerritoriesPage';
import { CustomersPage } from './pages/CustomersPage';
import { VisitsPage } from './pages/VisitsPage';
import { VisitDetailsPage } from './pages/VisitDetailsPage';
import { GeoLogsPage } from './pages/GeoLogsPage';
import { MediaViewerPage } from './pages/MediaViewerPage';
import { FormsPage } from './pages/FormsPage';
import { ReportsPage } from './pages/ReportsPage';
import { SettingsPage } from './pages/SettingsPage';
import { ProfilePage } from './pages/ProfilePage';
import { apiClient } from './api/client';

const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated, isLoading } = useAuth();
  if (isLoading) return null;
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <>{children}</>;
};

const AdminRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, isAuthenticated, isLoading } = useAuth();
  if (isLoading) return null;
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (user?.role === 'EMPLOYEE') return <Navigate to="/" replace />;
  return <>{children}</>;
};

export function AppContent() {
  const [apiStatus, setApiStatus] = useState<'checking' | 'connected' | 'error'>('checking');

  useEffect(() => {
    apiClient.getHealth()
      .then(() => setApiStatus('connected'))
      .catch(() => setApiStatus('error'));
  }, []);

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route
        path="/*"
        element={
          <ProtectedRoute>
            <Layout apiStatus={apiStatus}>
              <Routes>
                <Route path="/" element={<DashboardPage />} />
                <Route path="/employees" element={<AdminRoute><EmployeesPage /></AdminRoute>} />
                <Route path="/territories" element={<AdminRoute><TerritoriesPage /></AdminRoute>} />
                <Route path="/customers" element={<AdminRoute><CustomersPage /></AdminRoute>} />
                <Route path="/visits" element={<VisitsPage />} />
                <Route path="/visits/:id" element={<VisitDetailsPage />} />
                <Route path="/geo-logs" element={<AdminRoute><GeoLogsPage /></AdminRoute>} />
                <Route path="/media" element={<AdminRoute><MediaViewerPage /></AdminRoute>} />
                <Route path="/forms" element={<FormsPage />} />
                <Route path="/reports" element={<AdminRoute><ReportsPage /></AdminRoute>} />
                <Route path="/settings" element={<AdminRoute><SettingsPage /></AdminRoute>} />
                <Route path="/profile" element={<ProfilePage />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </Layout>
          </ProtectedRoute>
        }
      />
    </Routes>
  );
}


export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppContent />
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
