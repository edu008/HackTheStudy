import React, { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Button } from './ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from './ui/card';
import { Check, RefreshCcw } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/contexts/AuthContext';

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

  useEffect(() => {
    if (verified) return;
    
    const verifyPayment = async () => {
      const searchParams = new URLSearchParams(location.search);
      const sessionId = searchParams.get('session_id');
      
      if (!sessionId) {
        toast.error('Keine Zahlungsinformationen gefunden');
        setPaymentStatus('error');
        setIsLoading(false);
        setVerified(true);
        return;
      }
      
      try {
        const token = localStorage.getItem('exammaster_token');
        if (!token) {
          toast.error('Bitte melden Sie sich an, um die Zahlung zu verifizieren');
          navigate('/signin');
          setVerified(true);
          return;
        }
        
        const response = await axios.get(
          `${PAYMENT_API_URL}/api/payment/payment-success?session_id=${sessionId}`,
          { 
            withCredentials: true,
            headers: {
              Authorization: `Bearer ${token}`
            }
          }
        );
        
        if (response.data.status === 'success') {
          setPaymentStatus('success');
          setCredits(Number(response.data.credits));
          toast.success('Zahlung erfolgreich!');
          
          await refreshUserCredits();
        } else {
          setPaymentStatus('pending');
          toast.info('Zahlung wird bearbeitet');
        }
      } catch (error) {
        console.error('Fehler beim Überprüfen der Zahlung:', error);
        setPaymentStatus('error');
        toast.error('Fehler beim Überprüfen der Zahlung');
      } finally {
        setIsLoading(false);
        setVerified(true);
      }
    };
    
    verifyPayment();
  }, [location.search, refreshUserCredits, navigate, verified]);

  return (
    <div className="container mx-auto py-12 px-4 max-w-lg">
      <Card className="w-full">
        <CardHeader>
          <CardTitle className="text-2xl text-center">
            {isLoading
              ? 'Zahlung wird überprüft...'
              : paymentStatus === 'success'
              ? 'Zahlung erfolgreich!'
              : paymentStatus === 'pending'
              ? 'Zahlung wird bearbeitet'
              : 'Fehler bei der Zahlung'}
          </CardTitle>
          <CardDescription className="text-center">
            {isLoading
              ? 'Bitte warten Sie, während wir Ihre Zahlung überprüfen'
              : paymentStatus === 'success'
              ? `${credits} Credits wurden Ihrem Konto gutgeschrieben`
              : paymentStatus === 'pending'
              ? 'Ihre Zahlung wird noch bearbeitet'
              : 'Es gab ein Problem mit Ihrer Zahlung'}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex justify-center py-6">
          {isLoading ? (
            <RefreshCcw className="h-16 w-16 animate-spin text-primary" />
          ) : paymentStatus === 'success' ? (
            <div className="rounded-full bg-green-100 p-3">
              <Check className="h-16 w-16 text-green-600" />
            </div>
          ) : (
            <div className="text-center">
              <p className="text-muted-foreground">
                {paymentStatus === 'pending'
                  ? 'Die Verarbeitung der Zahlung kann einen Moment dauern.'
                  : 'Bitte kontaktieren Sie den Support, wenn das Problem weiterhin besteht.'}
              </p>
            </div>
          )}
        </CardContent>
        <CardFooter className="flex justify-center">
          <Button
            onClick={() => navigate('/dashboard')}
            disabled={isLoading}
            className="px-8"
          >
            Zum Dashboard
          </Button>
        </CardFooter>
      </Card>
    </div>
  );
} 