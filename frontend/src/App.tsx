import { Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { DetectPage } from "./pages/DetectPage";
import { HidePage } from "./pages/HidePage";
import { HomePage } from "./pages/HomePage";
import { KeysPage } from "./pages/KeysPage";
import { LabPage } from "./pages/LabPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { PreflightPage } from "./pages/PreflightPage";
import { RevealPage } from "./pages/RevealPage";

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<HomePage />} />
        <Route path="hide" element={<HidePage />} />
        <Route path="reveal" element={<RevealPage />} />
        <Route path="preflight" element={<PreflightPage />} />
        <Route path="detect" element={<DetectPage />} />
        <Route path="keys" element={<KeysPage />} />
        <Route path="lab" element={<LabPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
