import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { ProtectedRoute, PublicOnlyRoute } from "./auth/ProtectedRoute";
import { DashboardPage } from "./pages/DashboardPage";
import { FoodPage } from "./pages/FoodPage";
import { FreshnessDetailPage } from "./pages/FreshnessDetailPage";
import { FreshnessHistoryPage } from "./pages/FreshnessHistoryPage";
import { FreshnessPage } from "./pages/FreshnessPage";
import { HistoryPage } from "./pages/HistoryPage";
import { LoginPage } from "./pages/LoginPage";
import { MealDetailPage, MealEditPage } from "./pages/MealDetailPage";
import { MealsPage } from "./pages/MealsPage";
import { MediaPage } from "./pages/MediaPage";
import { ModuleDetailPage, ModulesPage } from "./pages/ModulesPage";
import { RegisterPage } from "./pages/RegisterPage";
import { SettingsPage } from "./pages/SettingsPage";

export function App() {
  return (
    <Routes>
      <Route element={<PublicOnlyRoute />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
      </Route>
      <Route element={<ProtectedRoute />}>
        <Route element={<Layout />}>
          <Route index element={<DashboardPage />} />
          <Route path="/modules" element={<ModulesPage />} />
          <Route path="/modules/:key" element={<ModuleDetailPage />} />
          <Route path="/food" element={<FoodPage />} />
          <Route path="/freshness" element={<FreshnessPage />} />
          <Route path="/freshness/history" element={<FreshnessHistoryPage />} />
          <Route path="/freshness/:id" element={<FreshnessDetailPage />} />
          <Route path="/meals" element={<MealsPage />} />
          <Route path="/meals/:id" element={<MealDetailPage />} />
          <Route path="/meals/:id/edit" element={<MealEditPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/media" element={<MediaPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/preferences" element={<Navigate to="/settings" replace />} />
        </Route>
      </Route>
      <Route path="*" element={<p className="center-note">Page not found.</p>} />
    </Routes>
  );
}
