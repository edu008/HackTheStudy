
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useEffect } from "react";
import { AuthProvider } from "./contexts/AuthContext";
import Index from "./pages/Index";
import NotFound from "./pages/NotFound";
import Dashboard from "./pages/Dashboard";
import SignIn from "./pages/SignIn";
import PaymentPage from "./pages/PaymentPage";
import AuthCallback from "./pages/AuthCallback";
import { useAuth } from "./contexts/AuthContext";

// Wrapper components for protected routes
const FlashcardsPage = () => {
  const { user } = useAuth();
  
  if (!user) {
    return <Navigate to="/signin" />;
  }
  
  // Use useEffect to handle the navigation with window.location
  useEffect(() => {
    window.location.href = '/#flashcards';
  }, []);
  
  // Return null while the navigation is happening
  return null;
};

const TestSimulatorPage = () => {
  const { user } = useAuth();
  
  if (!user) {
    return <Navigate to="/signin" />;
  }
  
  // Use useEffect to handle the navigation with window.location
  useEffect(() => {
    window.location.href = '/#test-simulator';
  }, []);
  
  // Return null while the navigation is happening
  return null;
};

const queryClient = new QueryClient();

const App = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <Toaster />
        <Sonner />
        <BrowserRouter>
          <AuthProvider>
            <Routes>
              <Route path="/" element={<Index />} />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/signin" element={<SignIn />} />
              <Route path="/payment" element={<PaymentPage />} />
              <Route path="/auth-callback" element={<AuthCallback />} />
              
              {/* New routes for Flashcards and Test Simulator */}
              <Route path="/flashcards" element={<FlashcardsPage />} />
              <Route path="/test-simulator" element={<TestSimulatorPage />} />
              
              {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
              <Route path="*" element={<NotFound />} />
            </Routes>
          </AuthProvider>
        </BrowserRouter>
      </TooltipProvider>
    </QueryClientProvider>
  );
};

export default App;
