import React, { useEffect } from 'react';
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { AuthProvider } from "./contexts/AuthContext";
import { setupAxiosInterceptors, cleanupStorageData } from '@/lib/api/authService';
import AppRoutes from '@/routes';

const queryClient = new QueryClient();

const App: React.FC = () => {
  useEffect(() => {
    // Lösche alle Testdaten aus dem localStorage
    cleanupStorageData();
    
    // Initialisiere Axios-Interceptors für automatische Token-Erneuerung
    setupAxiosInterceptors();
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <TooltipProvider>
          <Toaster />
          <Sonner />
          <BrowserRouter>
            <AppRoutes />
          </BrowserRouter>
        </TooltipProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
};

export default App;
