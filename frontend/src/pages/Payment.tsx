import React, { useState } from 'react';
import axios from 'axios';
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "sonner";
import { useAuth } from '@/contexts/AuthContext';

// API-Endpunkte
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000';
const PAYMENT_API_URL = import.meta.env.VITE_PAYMENT_API_URL || 'http://localhost:5001';

// Preistabelle
const PRICE_TIERS = [
  { id: 'tier1', credits: 250, price: '5 CHF', description: 'Grundpaket' },
  { id: 'tier2', credits: 500, price: '10 CHF', description: 'Standardpaket' },
  { id: 'tier3', credits: 1250, price: '25 CHF', description: 'Premiumpaket' },
  { id: 'tier4', credits: 2500, price: '50 CHF', description: 'Profipaket' },
];

const Payment = () => {
  const [isLoading, setIsLoading] = useState(false);
  const { user, refreshUserCredits } = useAuth();

  const handlePurchase = async (tier: string) => {
    try {
      setIsLoading(true);
      const token = localStorage.getItem('exammaster_token');
      
      // Request an den neuen Payment-Service senden
      const response = await axios.post(
        `${PAYMENT_API_URL}/api/payment/create-checkout-session`,
        { tier },
        { 
          withCredentials: true,
          headers: {
            Authorization: `Bearer ${token}`
          }
        }
      );
      
      // Weiterleitung zur Stripe Checkout-Seite
      if (response.data.url) {
        window.location.href = response.data.url;
      } else {
        toast.error('Fehler beim Erstellen der Checkout-Session');
      }
    } catch (error) {
      console.error('Fehler beim Erstellen der Checkout-Session:', error);
      toast.error('Zahlung konnte nicht initiiert werden');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="container mx-auto py-12">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold">Credits kaufen</h1>
          <p className="text-muted-foreground mt-2">
            Wählen Sie ein Paket, um mehr Credits zu erhalten
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {PRICE_TIERS.map((tier) => (
            <Card key={tier.id} className="border border-border">
              <CardHeader>
                <CardTitle>{tier.credits} Credits</CardTitle>
                <CardDescription>{tier.description}</CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-3xl font-bold">{tier.price}</p>
                <p className="text-muted-foreground">
                  {tier.credits / parseInt(tier.price)} Credits pro CHF
                </p>
              </CardContent>
              <CardFooter>
                <Button 
                  className="w-full" 
                  onClick={() => handlePurchase(tier.id)}
                  disabled={isLoading}
                >
                  {isLoading ? 'Wird verarbeitet...' : 'Jetzt kaufen'}
                </Button>
              </CardFooter>
            </Card>
          ))}
        </div>

        <div className="mt-12 text-center text-muted-foreground">
          <p>Sie haben derzeit {user?.credits || 0} Credits</p>
          <p className="text-sm mt-2">
            Nach einer erfolgreichen Zahlung werden die Credits automatisch Ihrem Konto gutgeschrieben
          </p>
        </div>
      </div>
    </div>
  );
};

export default Payment; 