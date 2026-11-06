import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, homePathFor, useAuth } from "./lib/auth";
import { CandidateLayout, HRLayout, RequireRole, Spinner } from "./components/layout";
import Login from "./pages/auth/Login";
import Register from "./pages/auth/Register";
import CandidateDashboard from "./pages/candidate/Dashboard";
import CandidateProfilePage from "./pages/candidate/Profile";
import JobDiscovery from "./pages/candidate/Jobs";
import JobDetailPage from "./pages/candidate/JobDetail";
import JobCompatibilityPage from "./pages/candidate/JobCompatibility";
import RecommendationsPage from "./pages/candidate/Recommendations";
import MyCvPage from "./pages/candidate/MyCV";
import ReviewExtractionPage from "./pages/candidate/ReviewExtraction";
import CvSkillsPage from "./pages/candidate/CvSkills";
import HrDashboard from "./pages/hr/Dashboard";
import CompanyPage from "./pages/hr/Company";
import HrJobsPage from "./pages/hr/Jobs";
import JobForm from "./pages/hr/JobForm";
import HrJobDetailPage from "./pages/hr/JobDetail";

function RootRedirect() {
  const { user, initializing } = useAuth();
  if (initializing) return <Spinner />;
  return <Navigate to={user ? homePathFor(user.role) : "/login"} replace />;
}

function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3">
      <p className="text-4xl font-bold text-slate-300">404</p>
      <p className="text-sm text-slate-500">Halaman tidak ditemukan.</p>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
        <Route path="/" element={<RootRedirect />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />

        <Route
          path="/app"
          element={
            <RequireRole role="candidate">
              <CandidateLayout />
            </RequireRole>
          }
        >
          <Route index element={<CandidateDashboard />} />
          <Route path="profile" element={<CandidateProfilePage />} />
          <Route path="jobs" element={<JobDiscovery />} />
          <Route path="jobs/:id" element={<JobDetailPage />} />
          <Route path="jobs/:id/compatibility" element={<JobCompatibilityPage />} />
          <Route path="recommendations" element={<RecommendationsPage />} />
          <Route path="cv" element={<MyCvPage />} />
          <Route path="cv/:id/review" element={<ReviewExtractionPage />} />
          <Route path="cv/:id/skills" element={<CvSkillsPage />} />
        </Route>

        <Route
          path="/hr"
          element={
            <RequireRole role="hr">
              <HRLayout />
            </RequireRole>
          }
        >
          <Route index element={<HrDashboard />} />
          <Route path="company" element={<CompanyPage />} />
          <Route path="jobs" element={<HrJobsPage />} />
          <Route path="jobs/new" element={<JobForm />} />
          <Route path="jobs/:id" element={<HrJobDetailPage />} />
          <Route path="jobs/:id/edit" element={<JobForm />} />
        </Route>

        <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
