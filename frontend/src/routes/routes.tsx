import { Navigate, createBrowserRouter } from "react-router-dom";
import App from "@/App";
import HomePage from "@/pages/HomePage";
import NotFoundPage from "@/pages/NotFoundPage";
import StudyMaterialsPage from "@/pages/StudyMaterialsPage";

// Weitere Importe hier...

export const router = createBrowserRouter([
  {
    path: "/",
    element: <App />,
    errorElement: <NotFoundPage />,
    children: [
      {
        index: true,
        element: <HomePage />,
      },
      {
        path: "study-materials",
        element: <StudyMaterialsPage />,
      },
      // Weitere Routen hier...
      {
        path: "*",
        element: <Navigate to="/not-found" replace />,
      },
    ],
  },
]); 