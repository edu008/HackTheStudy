import React, { useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { Button } from './ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from './ui/card';
import { toast } from 'sonner';
import { loadStripe } from '@stripe/stripe-js';

// API Endpunkte für Zahlungen
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000';
const PAYMENT_API_URL = import.meta.env.VITE_PAYMENT_API_URL || 'http://localhost:5001';
const STRIPE_PUBLIC_KEY = import.meta.env.VITE_STRIPE_PUBLIC_KEY;

// Stripe-Instance initialisieren
const stripePromise = loadStripe(STRIPE_PUBLIC_KEY);

// Preis-Stufen mit Schweizer Franken (CHF)
const priceTiers = [
  { id: 'tier1', price: 5, credits: 250, label: '5 CHF für 250 Credits' },
  { id: 'tier2', price: 10, credits: 500, label: '10 CHF für 500 Credits' },
  { id: 'tier3', price: 25, credits: 1250, label: '25 CHF für 1250 Credits' },
  { id: 'tier4', price: 50, credits: 2500, label: '50 CHF für 2500 Credits' },
];

export default function PaymentPage() {
  const [isLoading, setIsLoading] = useState(false);
  const [selectedTier, setSelectedTier] = useState<string | null>(null);
  const navigate = useNavigate();

  const handleSelectTier = (tierId: string) => {
    setSelectedTier(tierId);
  };

  const handleCheckout = async () => {
    if (!selectedTier) {
      toast.error('Bitte wählen Sie eine Preisstufe aus');
      return;
    }

    setIsLoading(true);

    try {
      const token = localStorage.getItem('exammaster_token');
      if (!token) {
        toast.error('Sie müssen eingeloggt sein, um Credits zu kaufen');
        navigate('/signin');
        return;
      }

      // Stripe Checkout-Session erstellen
      const response = await axios.post(
        `${PAYMENT_API_URL}/api/payment/create-checkout-session`,
        { tier: selectedTier },
        { 
          withCredentials: true,
          headers: {
            Authorization: `Bearer ${token}`
          }
        }
      );

      // Zu Stripe Checkout weiterleiten
      if (response.data && response.data.url) {
        window.location.href = response.data.url;
      } else {
        toast.error('Es ist ein Fehler bei der Zahlungsabwicklung aufgetreten');
      }
    } catch (error) {
      console.error('Fehler beim Erstellen der Checkout-Session:', error);
      toast.error('Es ist ein Fehler aufgetreten. Bitte versuchen Sie es später erneut.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="container mx-auto py-8 px-4">
      <h1 className="text-3xl font-bold mb-8 text-center">Credits kaufen</h1>
      <p className="text-center mb-8">
        Wählen Sie ein Paket aus, um Credits für API-Anfragen zu erwerben.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        {priceTiers.map((tier) => (
          <Card 
            key={tier.id}
            className={`cursor-pointer hover:shadow-lg transition-shadow ${
              selectedTier === tier.id ? 'border-2 border-primary' : ''
            }`}
            onClick={() => handleSelectTier(tier.id)}
          >
            <CardHeader>
              <CardTitle className="text-2xl">{tier.price} CHF</CardTitle>
              <CardDescription>{tier.credits} Credits</CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-muted-foreground">
                Nutzen Sie diese Credits für API-Abfragen in unserer Anwendung.
              </p>
            </CardContent>
            <CardFooter>
              <Button 
                variant="outline" 
                className="w-full"
                onClick={(e) => {
                  e.stopPropagation();
                  setSelectedTier(tier.id);
                }}
              >
                {selectedTier === tier.id ? 'Ausgewählt' : 'Auswählen'}
              </Button>
            </CardFooter>
          </Card>
        ))}
      </div>

      <div className="flex justify-center">
        <Button 
          onClick={handleCheckout} 
          disabled={!selectedTier || isLoading}
          className="px-8 py-6 text-lg"
        >
          {isLoading ? 'Wird bearbeitet...' : 'Jetzt kaufen'}
        </Button>
      </div>
    </div>
  );
} 