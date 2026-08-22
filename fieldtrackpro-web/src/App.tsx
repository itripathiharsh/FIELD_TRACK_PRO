import React from 'react';
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
import { FormsPage } from './pages/FormsPage';
import { FormBuilderPage } from './pages/FormBuilderPage';
import { FormPreviewPage } from './pages/FormPreviewPage';
import { FormSubmissionsPage } from './pages/FormSubmissionsPage';
import { FormSubmissionDetailPage } from './pages/FormSubmissionDetailPage';
import { FormFillPage } from './pages/FormFillPage';
import { ReportsPage } from './pages/ReportsPage';
import { SettingsPage } from './pages/SettingsPage';
import { ProfilePage } from './pages/ProfilePage';
import { MapPage } from './pages/MapPage';
import { EmployeeDetailPage } from './pages/EmployeeDetailPage';
import { CustomerDetailPage } from './pages/CustomerDetailPage';
import { UserDetailPage } from './pages/UserDetailPage';
import { TerritoryDetailPage } from './pages/TerritoryDetailPage';
import { PaymentReviewPage } from './pages/PaymentReviewPage';
import { ImportWizardPage } from './pages/ImportWizardPage';
import { ImportHistoryPage } from './pages/ImportHistoryPage';

const AuthLoadingFallback: React.FC = () => (
  <div className="min-h-screen bg-background flex flex-col items-center justify-center text-on-surface">
    <div className="w-10 h-10 border-4 border-primary-container border-t-secondary-container rounded-full animate-spin" />
    <p className="mt-space-4 font-caption text-caption text-on-surface-variant">
      Initializing FieldTrack Pro Subsystem...
    </p>
  </div>
);

const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated, isLoading } = useAuth();
  if (isLoading) return <AuthLoadingFallback />;
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <>{children}</>;
};

const AdminRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, isAuthenticated, isLoading } = useAuth();
  if (isLoading) return <AuthLoadingFallback />;
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (user?.role === 'EMPLOYEE') return <Navigate to="/" replace />;
  return <>{children}</>;
};

export function AppContent() {
  // FT-057: an `apiStatus` state was computed here, passed to Layout, and then
  // discarded without ever being rendered - a duplicate of the health check
  // the Header already performs and displays. Removed.
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route
        path="/*"
        element={
          <ProtectedRoute>
            <Layout>
              <Routes>
                <Route path="/" element={<DashboardPage />} />
                <Route path="/employees" element={<AdminRoute><EmployeesPage /></AdminRoute>} />
                <Route path="/territories" element={<AdminRoute><TerritoriesPage /></AdminRoute>} />
                <Route path="/territories/:id" element={<AdminRoute><TerritoryDetailPage /></AdminRoute>} />
                <Route path="/customers" element={<AdminRoute><CustomersPage /></AdminRoute>} />
                <Route path="/visits" element={<VisitsPage />} />
                <Route path="/visits/:id" element={<VisitDetailsPage />} />
                <Route path="/geo-logs" element={<AdminRoute><GeoLogsPage /></AdminRoute>} />
                <Route path="/map" element={<AdminRoute><MapPage /></AdminRoute>} />
                <Route path="/employees/:id" element={<AdminRoute><EmployeeDetailPage /></AdminRoute>} />
                <Route path="/customers/:id" element={<AdminRoute><CustomerDetailPage /></AdminRoute>} />
                <Route path="/users/:id" element={<AdminRoute><UserDetailPage /></AdminRoute>} />
                {/* P2-E: standalone Media Vault removed - media now lives only where it
                    was created (Visit → Media/Orders, Payment → Proof, Form → Attachments).
                    An old bookmark to /media falls through to the wildcard route below. */}
                <Route path="/forms" element={<AdminRoute><FormsPage /></AdminRoute>} />
                <Route path="/forms/new" element={<AdminRoute><FormBuilderPage /></AdminRoute>} />
                <Route path="/forms/:id/edit" element={<AdminRoute><FormBuilderPage /></AdminRoute>} />
                <Route path="/forms/:id/preview" element={<AdminRoute><FormPreviewPage /></AdminRoute>} />
                <Route path="/forms/:id/submissions" element={<AdminRoute><FormSubmissionsPage /></AdminRoute>} />
                <Route path="/forms/:id/submissions/:submissionId" element={<AdminRoute><FormSubmissionDetailPage /></AdminRoute>} />
                <Route path="/visits/:visitId/forms/:formId" element={<FormFillPage />} />
                <Route path="/reports" element={<AdminRoute><ReportsPage /></AdminRoute>} />
                <Route path="/collections" element={<Navigate to="/reports?tab=collections_workbench" replace />} />
                <Route path="/payments" element={<AdminRoute><PaymentReviewPage /></AdminRoute>} />
                <Route path="/imports" element={<AdminRoute><ImportHistoryPage /></AdminRoute>} />
                <Route path="/imports/new" element={<AdminRoute><ImportWizardPage /></AdminRoute>} />
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

