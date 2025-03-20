import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { toast } from 'sonner';

// API Endpunkt
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000';
const PAYMENT_API_URL = import.meta.env.VITE_PAYMENT_API_URL || 'http://localhost:5001';

interface Payment {
  id: string;
  amount: number;
  credits: number;
  status: string;
  created_at: string;
}

export default function PaymentHistory() {
  const [payments, setPayments] = useState<Payment[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    fetchPaymentHistory();
  }, []);

  const fetchPaymentHistory = async () => {
    setIsLoading(true);
    try {
      const token = localStorage.getItem('exammaster_token');
      if (!token) {
        setIsLoading(false);
        return;
      }

      const response = await axios.get(
        `${PAYMENT_API_URL}/api/payment/payment-history`,
        {
          withCredentials: true,
          headers: {
            Authorization: `Bearer ${token}`
          }
        }
      );

      if (response.data.history) {
        setPayments(response.data.history);
      }
    } catch (error) {
      console.error('Fehler beim Abrufen der Zahlungshistorie:', error);
      toast.error('Fehler beim Laden der Zahlungshistorie');
    } finally {
      setIsLoading(false);
    }
  };

  if (isLoading) {
    return <div className="text-center py-4">Zahlungshistorie wird geladen...</div>;
  }

  if (payments.length === 0) {
    return (
      <div className="text-center py-4 text-muted-foreground">
        Keine Zahlungen gefunden
      </div>
    );
  }

  // Hilfsfunktion zum Formatieren des Datums
  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return new Intl.DateTimeFormat('de-DE', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    }).format(date);
  };

  return (
    <div className="space-y-4">
      <h3 className="text-lg font-medium">Zahlungshistorie</h3>
      
      {payments.map((payment) => (
        <Card key={payment.id} className="bg-card">
          <CardHeader className="pb-2">
            <div className="flex justify-between items-center">
              <CardTitle className="text-base">{payment.credits} Credits</CardTitle>
              <CardDescription>
                {formatDate(payment.created_at)}
              </CardDescription>
            </div>
          </CardHeader>
          <CardContent>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Betrag:</span>
              <span className="font-medium">{payment.amount.toFixed(2)} CHF</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Status:</span>
              <span className={`font-medium ${
                payment.status === 'completed' ? 'text-green-600' : 'text-yellow-600'
              }`}>
                {payment.status === 'completed' ? 'Abgeschlossen' : payment.status}
              </span>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
