import { Navigate, Route, Routes } from "react-router-dom";

import { RequireAdmin, RequireAuth } from "@/lib/auth";
import { AdminLimits } from "@/pages/AdminLimits";
import { Dashboard } from "@/pages/Dashboard";
import { Detail } from "@/pages/Detail";
import { History } from "@/pages/History";
import { Login } from "@/pages/Login";
import { Users } from "@/pages/Users";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <Dashboard />
          </RequireAuth>
        }
      />
      <Route
        path="/history"
        element={
          <RequireAuth>
            <History />
          </RequireAuth>
        }
      />
      <Route
        path="/invoice/:id"
        element={
          <RequireAuth>
            <Detail />
          </RequireAuth>
        }
      />
      <Route
        path="/admin/users"
        element={
          <RequireAdmin>
            <Users />
          </RequireAdmin>
        }
      />
      <Route
        path="/admin/limits"
        element={
          <RequireAdmin>
            <AdminLimits />
          </RequireAdmin>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
