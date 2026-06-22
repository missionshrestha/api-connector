// frontend/src/App.tsx
import { Navigate, Route, Routes } from "react-router-dom";
import { TooltipProvider } from "@/shared/components/ui/tooltip";
import { ProfileListPage, ProfileFormPage } from "@/features/connection-profile";

export default function App() {
  return (
    <TooltipProvider>
      <Routes>
        <Route path="/" element={<Navigate to="/profiles" replace />} />
        <Route path="/profiles" element={<ProfileListPage />} />
        <Route path="/profiles/new" element={<ProfileFormPage />} />
        <Route path="/profiles/:id/edit" element={<ProfileFormPage />} />
      </Routes>
    </TooltipProvider>
  );
}