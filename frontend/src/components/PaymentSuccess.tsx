import React, { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Button } from './ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from './ui/card';
import { Check, RefreshCcw } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/contexts/AuthContext';
import { useTranslation } from 'react-i18next';

// API Endpunkt
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000';
const PAYMENT_API_URL = import.meta.env.VITE_PAYMENT_API_URL || 'http://localhost:5001';

export default function PaymentSuccess() {
  const [isLoading, setIsLoading] = useState(true);
  const [paymentStatus, setPaymentStatus] = useState<'success' | 'pending' | 'error'>('pending');
  const [credits, setCredits] = useState<number | null>(null);
  const [verified, setVerified] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const { refreshUserCredits } = useAuth();
  const { t } = useTranslation();

  useEffect(() => {
    if (verified) return;
    
    const verifyPayment = async () => {
      const searchParams = new URLSearchParams(location.search);
      const sessionId = searchParams.get('session_id');
      
      if (!sessionId) {
        toast.error(t('payment.success.noInformation'));
        setPaymentStatus('error');
        setIsLoading(false);
        setVerified(true);
        return;
      }
      
      try {
        const token = localStorage.getItem('exammaster_token');
        if (!token) {
          toast.error(t('payment.success.loginRequired'));
          navigate('/');
          setVerified(true);
          return;
        }
        
        setIsLoading(true);
        
        // Backend-Aufruf um Zahlung zu bestätigen und Guthaben gutzuschreiben
        const response = await axios.get(
          `${API_URL}/api/v1/payment/payment-success?session_id=${sessionId}`,
          {
            headers: {
              Authorization: `Bearer ${token}`
            },
            withCredentials: true
          }
        );
        
        if (response.data.success) {
          setPaymentStatus('success');
          setCredits(response.data.credits || 0);
          
          // Aktualisiere die Benutzer-Credits im Auth-Kontext
          await refreshUserCredits();
          
          toast.success(t('payment.success.confirmed'));
        } else {
          setPaymentStatus('error');
          toast.error(response.data.message || t('payment.success.verificationFailed'));
        }
      } catch (error) {
        console.error('Fehler bei der Zahlungsverifizierung:', error);
        setPaymentStatus('error');
        toast.error(t('payment.success.processingError'));
      } finally {
        setIsLoading(false);
        setVerified(true);
      }
    };
    
    verifyPayment();
  }, [location.search, navigate, refreshUserCredits, verified, t]);

  const getStatusText = () => {
    switch (paymentStatus) {
      case 'success':
        return t('payment.success.successMessage');
      case 'pending':
        return t('payment.success.pendingMessage');
      case 'error':
        return t('payment.success.errorMessage');
    }
  };

  return (
    <div className="container mx-auto px-4 max-w-4xl">
      <div className="pt-12 pb-8 text-center">
        <h1 className="text-3xl font-bold mb-2">{t('payment.success.title')}</h1>
        <p className="text-muted-foreground max-w-2xl mx-auto">
          {t('payment.success.statusCheck')}
        </p>
      </div>

      <Card className="mb-8 border-blue-100 overflow-hidden">
        <div className={`w-full h-2 ${
          paymentStatus === 'success' ? 'bg-green-500' : 
          paymentStatus === 'error' ? 'bg-red-500' : 'bg-blue-500'
        }`}></div>
        <CardHeader>
          <CardTitle>{t('payment.success.paymentStatus')}</CardTitle>
          <CardDescription>{getStatusText()}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col items-center justify-center py-10">
            {isLoading ? (
              <div className="flex flex-col items-center">
                <RefreshCcw className="h-12 w-12 animate-spin text-blue-500 mb-4" />
                <p className="text-muted-foreground">{t('payment.success.verifying')}</p>
              </div>
            ) : (
              <div className="text-center flex flex-col items-center">
                {paymentStatus === 'success' && (
                  <>
                    <div className="h-20 w-20 rounded-full bg-green-100 flex items-center justify-center mb-4">
                      <Check className="h-10 w-10 text-green-600" />
                    </div>
                    <h3 className="text-xl font-semibold mb-1">{t('payment.success.thankyou')}</h3>
                    <p className="mb-6">{t('payment.success.accountCredited')}</p>
                    <div className="mb-4 bg-blue-50 py-3 px-6 rounded-md">
                      <p className="text-sm text-gray-600">{t('payment.success.newBalance')}</p>
                      <p className="text-2xl font-bold text-blue-600">{credits?.toLocaleString('de-CH') || 0} Credits</p>
                    </div>
                  </>
                )}
                
                {paymentStatus === 'error' && (
                  <>
                    <div className="h-20 w-20 rounded-full bg-red-100 flex items-center justify-center mb-4">
                      <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-red-600">
                        <circle cx="12" cy="12" r="10"></circle>
                        <line x1="15" y1="9" x2="9" y2="15"></line>
                        <line x1="9" y1="9" x2="15" y2="15"></line>
                      </svg>
                    </div>
                    <h3 className="text-xl font-semibold mb-2">{t('payment.success.verificationFailed')}</h3>
                    <p className="text-muted-foreground mb-6 max-w-md">{t('payment.success.contactSupport')}</p>
                  </>
                )}
              </div>
            )}
          </div>
        </CardContent>
        <CardFooter className="flex justify-center">
          <Button onClick={() => navigate('/dashboard')}>
            {t('payment.success.backToDashboard')}
          </Button>
        </CardFooter>
      </Card>
    </div>
  );
} 