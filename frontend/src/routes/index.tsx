import React from 'react';
import { Routes, Route } from 'react-router-dom';
import Index from '@/pages/Index';
import Dashboard from '@/pages/Dashboard';
import PaymentPage from '@/pages/PaymentPage';
import NotFound from '@/pages/NotFound';
import AuthCallback from '@/pages/AuthCallback';
import TaskPage from '@/pages/TaskPage';

const AppRoutes: React.FC = () => {
  return (
    <Routes>
      <Route path="/" element={<Index />} />
      <Route path="/dashboard" element={<Dashboard />} />
      <Route path="/payment" element={<PaymentPage />} />
      <Route path="/auth-callback" element={<AuthCallback />} />
      <Route path="/tasks" element={<TaskPage />} />
      {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
};

export default AppRoutes; 