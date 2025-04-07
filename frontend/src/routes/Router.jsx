import { Routes, Route, Navigate } from 'react-router-dom';
import { useEffect } from 'react';

// Import der Komponenten
import LoginPage from '../pages/LoginPage';
import RegisterPage from '../pages/RegisterPage';
import HomePage from '../pages/HomePage';
import StudyMaterialsPage from '../pages/StudyMaterialsPage';
import ProfilePage from '../pages/ProfilePage';
import AuthCallbackPage from '../pages/AuthCallbackPage';

// Geschützte Route-Komponente
const ProtectedRoute = ({ isAuthenticated, children, sessionId }) => {
  if (!isAuthenticated) {
    // Umleitung zur Login-Seite, wenn nicht authentifiziert
    return <Navigate to="/login" replace />;
  }
  
  // Kinder-Komponenten mit der sessionId rendern
  return children;
};

// Authentifizierungsroute-Komponente (umgekehrte Logik)
const AuthRoute = ({ isAuthenticated, children }) => {
  if (isAuthenticated) {
    // Umleitung zur Hauptseite, wenn bereits authentifiziert
    return <Navigate to="/" replace />;
  }
  
  // Kinder-Komponenten rendern
  return children;
};

const Router = ({ isAuthenticated, sessionId, user }) => {
  // Effekt, um beim Routing-Wechsel die Session zu aktualisieren
  useEffect(() => {
    console.log('Router initialized with session:', sessionId);
    console.log('Authentication status:', isAuthenticated);
  }, [sessionId, isAuthenticated]);

  return (
    <Routes>
      {/* Öffentliche Routen */}
      <Route 
        path="/login" 
        element={
          <AuthRoute isAuthenticated={isAuthenticated}>
            <LoginPage />
          </AuthRoute>
        } 
      />
      <Route 
        path="/register" 
        element={
          <AuthRoute isAuthenticated={isAuthenticated}>
            <RegisterPage />
          </AuthRoute>
        } 
      />
      <Route path="/auth-callback" element={<AuthCallbackPage />} />
      
      {/* Geschützte Routen */}
      <Route 
        path="/" 
        element={
          isAuthenticated ? (
            <HomePage sessionId={sessionId} user={user} />
          ) : (
            <LoginPage />
          )
        } 
      />
      <Route 
        path="/study-materials" 
        element={
          <ProtectedRoute isAuthenticated={isAuthenticated} sessionId={sessionId}>
            <StudyMaterialsPage sessionId={sessionId} />
          </ProtectedRoute>
        } 
      />
      <Route 
        path="/profile" 
        element={
          <ProtectedRoute isAuthenticated={isAuthenticated}>
            <ProfilePage user={user} />
          </ProtectedRoute>
        } 
      />
      
      {/* 404 Fallback */}
      <Route 
        path="*" 
        element={<Navigate to="/" replace />} 
      />
    </Routes>
  );
};

export default Router; 