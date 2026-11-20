import React, { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { AccountantScope, AdminRoute, AuthLoadingFallback, FinanceRoute, ProtectedRoute } from './components/auth/RouteGuards';
import { ReconnectingScreen } from './components/auth/ReconnectingScreen';
import { useAuth } from './context/AuthContext';
import { Layout } from './components/layout/Layout';
import { LoginPage } from './pages/LoginPage';
import { RouteFallback } from './components/ui/RouteFallback';
import { ChunkErrorBoundary } from './components/ui/ChunkErrorBoundary';

// Every page except Login is code-split; the app shell (Layout) stays in the main bundle.
// The public landing page is its own chunk so signed-in users never download it.
const LandingPage = lazy(() => import('./pages/LandingPage').then((m) => ({ default: m.LandingPage })));
const DashboardPage = lazy(() => import('./pages/DashboardPage').then((m) => ({ default: m.DashboardPage })));
const EmployeesPage = lazy(() => import('./pages/EmployeesPage').then((m) => ({ default: m.EmployeesPage })));
const TerritoriesPage = lazy(() => import('./pages/TerritoriesPage').then((m) => ({ default: m.TerritoriesPage })));
const CustomersPage = lazy(() => import('./pages/CustomersPage').then((m) => ({ default: m.CustomersPage })));
const VisitsPage = lazy(() => import('./pages/VisitsPage').then((m) => ({ default: m.VisitsPage })));
const VisitDetailsPage = lazy(() => import('./pages/VisitDetailsPage').then((m) => ({ default: m.VisitDetailsPage })));
const AdhocReviewPage = lazy(() => import('./pages/AdhocReviewPage').then((m) => ({ default: m.AdhocReviewPage })));
const MonthlyVisitPlanningPage = lazy(() => import('./pages/MonthlyVisitPlanningPage').then((m) => ({ default: m.MonthlyVisitPlanningPage })));
const AdminVisitPlanningPage = lazy(() => import('./pages/AdminVisitPlanningPage').then((m) => ({ default: m.AdminVisitPlanningPage })));
const FormsPage = lazy(() => import('./pages/FormsPage').then((m) => ({ default: m.FormsPage })));
const FormBuilderPage = lazy(() => import('./pages/FormBuilderPage').then((m) => ({ default: m.FormBuilderPage })));
const FormPreviewPage = lazy(() => import('./pages/FormPreviewPage').then((m) => ({ default: m.FormPreviewPage })));
const FormSubmissionsPage = lazy(() => import('./pages/FormSubmissionsPage').then((m) => ({ default: m.FormSubmissionsPage })));
const FormSubmissionDetailPage = lazy(() => import('./pages/FormSubmissionDetailPage').then((m) => ({ default: m.FormSubmissionDetailPage })));
const FormFillPage = lazy(() => import('./pages/FormFillPage').then((m) => ({ default: m.FormFillPage })));
const ReportsPage = lazy(() => import('./pages/ReportsPage').then((m) => ({ default: m.ReportsPage })));
const SettingsPage = lazy(() => import('./pages/SettingsPage').then((m) => ({ default: m.SettingsPage })));
const ProfilePage = lazy(() => import('./pages/ProfilePage').then((m) => ({ default: m.ProfilePage })));
const MapPage = lazy(() => import('./pages/MapPage').then((m) => ({ default: m.MapPage })));
const EmployeeDetailPage = lazy(() => import('./pages/EmployeeDetailPage').then((m) => ({ default: m.EmployeeDetailPage })));
const CustomerDetailPage = lazy(() => import('./pages/CustomerDetailPage').then((m) => ({ default: m.CustomerDetailPage })));
const UserDetailPage = lazy(() => import('./pages/UserDetailPage').then((m) => ({ default: m.UserDetailPage })));
const TerritoryDetailPage = lazy(() => import('./pages/TerritoryDetailPage').then((m) => ({ default: m.TerritoryDetailPage })));
const PaymentReviewPage = lazy(() => import('./pages/PaymentReviewPage').then((m) => ({ default: m.PaymentReviewPage })));
const RequirementsPage = lazy(() => import('./pages/RequirementsPage').then((m) => ({ default: m.RequirementsPage })));
const EmployeeDailyLogsPage = lazy(() => import('./pages/EmployeeDailyLogsPage').then((m) => ({ default: m.EmployeeDailyLogsPage })));
const OutletMappingPage = lazy(() => import('./pages/OutletMappingPage').then((m) => ({ default: m.OutletMappingPage })));
const OutletVerificationPage = lazy(() => import('./pages/OutletVerificationPage').then((m) => ({ default: m.OutletVerificationPage })));

/** Suspense + chunk-failure boundary for lazy routes; a navigation clears a previous failure. */
function LazyRoutes({ children }: { children: React.ReactNode }) {
  const { pathname } = useLocation();
  return (
    <ChunkErrorBoundary resetKey={pathname}>
      <Suspense fallback={<RouteFallback />}>{children}</Suspense>
    </ChunkErrorBoundary>
  );
}

/** Signed-in application shell with every protected route. */
function ProtectedApp() {
  return (
    <ProtectedRoute>
      <AccountantScope>
      <Layout>
        <LazyRoutes>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/employees" element={<AdminRoute><EmployeesPage /></AdminRoute>} />
          <Route path="/daily-logs" element={<AdminRoute><EmployeeDailyLogsPage /></AdminRoute>} />
          <Route path="/employee-daily-logs" element={<AdminRoute><EmployeeDailyLogsPage /></AdminRoute>} />
          <Route path="/territories" element={<AdminRoute><TerritoriesPage /></AdminRoute>} />
          <Route path="/territories/:id" element={<AdminRoute><TerritoryDetailPage /></AdminRoute>} />
          <Route path="/customers" element={<AdminRoute><CustomersPage /></AdminRoute>} />
          <Route path="/customers/outlet-verification" element={<AdminRoute><OutletVerificationPage /></AdminRoute>} />
          <Route path="/customers/outlet-mapping" element={<AdminRoute><OutletMappingPage /></AdminRoute>} />
          <Route path="/visit-planning" element={<MonthlyVisitPlanningPage />} />
          <Route path="/admin/visit-planning" element={<AdminRoute><AdminVisitPlanningPage /></AdminRoute>} />
          <Route path="/visits" element={<VisitsPage />} />
          <Route path="/visits/adhoc-review" element={<AdminRoute><AdhocReviewPage /></AdminRoute>} />
          <Route path="/visits/:id" element={<VisitDetailsPage />} />
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
          <Route path="/reports" element={<FinanceRoute><ReportsPage /></FinanceRoute>} />
          <Route path="/collections" element={<Navigate to="/reports?tab=collections_workbench" replace />} />
          <Route path="/payments" element={<AdminRoute><PaymentReviewPage /></AdminRoute>} />
          <Route path="/requirements" element={<AdminRoute><RequirementsPage /></AdminRoute>} />
          <Route path="/settings" element={<AdminRoute><SettingsPage /></AdminRoute>} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </LazyRoutes>
      </Layout>
      </AccountantScope>
    </ProtectedRoute>
  );
}

function PublicLanding() {
  return (
    <Suspense fallback={<AuthLoadingFallback />}>
      <LandingPage />
    </Suspense>
  );
}

/**
 * "/" is the public entry route: signed-out visitors see the landing page (with links
 * to the web login and the Android APK); signed-in users get the dashboard as before.
 * Every other path is the protected app. An expired session still goes to login.
 */
function RootEntry() {
  const { pathname } = useLocation();
  const { isAuthenticated, isLoading, sessionExpired, reconnecting } = useAuth();
  if (pathname !== '/') return <ProtectedApp />;
  if (reconnecting && !isAuthenticated) return <ReconnectingScreen />;
  if (isLoading) return <AuthLoadingFallback />;
  if (!isAuthenticated) {
    if (sessionExpired) return <Navigate to="/login" replace state={{ reason: 'session_expired' }} />;
    return <PublicLanding />;
  }
  return <ProtectedApp />;
}

export function AppContent() {
  // FT-057: an `apiStatus` state was computed here, passed to Layout, and then
  // discarded without ever being rendered - a duplicate of the health check
  // the Header already performs and displays. Removed.
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/welcome" element={<PublicLanding />} />
      <Route path="/*" element={<RootEntry />} />
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

