import React, { useState, useMemo } from 'react';
import axios from 'axios';
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "sonner";
import { useAuth } from '@/contexts/AuthContext';
import { Check, CreditCard, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useTranslation } from 'react-i18next';

// API-Endpunkte
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000';
const PAYMENT_API_URL = import.meta.env.VITE_PAYMENT_API_URL || 'http://localhost:5001';

const Payment = () => {
  const [isLoading, setIsLoading] = useState(false);
  const [selectedTier, setSelectedTier] = useState<string>('tier2'); // Standardpaket als Standard
  const { user, refreshUserCredits } = useAuth();
  const { t, i18n } = useTranslation();
  
  // Lokale für die Zahlenformatierung basierend auf der aktuellen Sprache
  const currentLocale = i18n.language === 'de' ? 'de-CH' : 'en-US';
  
  // Preisstufen als useMemo, damit sie bei Sprachänderung neu berechnet werden
  const PRICE_TIERS = useMemo(() => [
    { 
      id: 'tier1', 
      credits: 5000, 
      price: '5 CHF', 
      priceValue: 5,
      description: t('payment.tiers.basic'), 
      features: [
        t('payment.tiers.credits', { count: 5000 }), 
        t('payment.tiers.inputTokens', { count: 33000 }), 
        t('payment.tiers.outputTokens', { count: 16600 })
      ],
      highlighted: false
    },
    { 
      id: 'tier2', 
      credits: 10000, 
      price: '10 CHF', 
      priceValue: 10,
      description: t('payment.tiers.standard'), 
      features: [
        t('payment.tiers.credits', { count: 10000 }), 
        t('payment.tiers.inputTokens', { count: 66000 }), 
        t('payment.tiers.outputTokens', { count: 33300 })
      ],
      highlighted: true
    },
    { 
      id: 'tier3', 
      credits: 25000, 
      price: '25 CHF', 
      priceValue: 25,
      description: t('payment.tiers.premium'), 
      features: [
        t('payment.tiers.credits', { count: 25000 }), 
        t('payment.tiers.inputTokens', { count: 166000 }), 
        t('payment.tiers.outputTokens', { count: 83300 })
      ],
      highlighted: false
    },
    { 
      id: 'tier4', 
      credits: 50000, 
      price: '50 CHF', 
      priceValue: 50,
      description: t('payment.tiers.professional'), 
      features: [
        t('payment.tiers.credits', { count: 50000 }), 
        t('payment.tiers.inputTokens', { count: 333000 }), 
        t('payment.tiers.outputTokens', { count: 166600 })
      ],
      highlighted: false
    },
  ], [t]); // Abhängigkeit von t, damit bei Sprachänderung neu berechnet wird

  const handlePurchase = async (tier: string) => {
    try {
      setIsLoading(true);
      const token = localStorage.getItem('exammaster_token');
      
      // Request an den neuen Payment-Service senden
      const response = await axios.post(
        `${API_URL}/api/v1/payment/create-checkout-session`,
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
        toast.error(t('payment.errors.checkoutSession'));
      }
    } catch (error) {
      console.error('Fehler beim Erstellen der Checkout-Session:', error);
      toast.error(t('payment.errors.initiate'));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="container mx-auto py-12">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-10">
          <h1 className="text-3xl font-bold mb-2">{t('payment.title')}</h1>
          <p className="text-muted-foreground max-w-2xl mx-auto">
            {t('payment.description')}
          </p>
        </div>

        <div className="bg-muted/40 p-4 rounded-lg mb-8">
          <h2 className="text-lg font-medium mb-2">{t('payment.tokenModel.title')}</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-background rounded-md p-3 shadow-sm">
              <p className="font-medium">{t('payment.tokenModel.inputTitle')}:</p>
              <p className="text-muted-foreground text-sm">{t('payment.tokenModel.inputRate')}</p>
              <p className="text-xs text-muted-foreground mt-1">{t('payment.tokenModel.inputDescription')}</p>
            </div>
            <div className="bg-background rounded-md p-3 shadow-sm">
              <p className="font-medium">{t('payment.tokenModel.outputTitle')}:</p>
              <p className="text-muted-foreground text-sm">{t('payment.tokenModel.outputRate')}</p>
              <p className="text-xs text-muted-foreground mt-1">{t('payment.tokenModel.outputDescription')}</p>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {PRICE_TIERS.map((tier) => (
            <Card 
              key={tier.id} 
              className={cn(
                "border transition-all",
                tier.highlighted ? "border-primary shadow-md scale-105" : "border-border hover:border-muted-foreground/20"
              )}
            >
              <CardHeader>
                <CardTitle>{tier.credits.toLocaleString(currentLocale)} Credits</CardTitle>
                <CardDescription>{tier.description}</CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-3xl font-bold mb-2">{tier.price}</p>
                <p className="text-sm text-muted-foreground mb-4">
                  {(tier.credits / tier.priceValue).toLocaleString(currentLocale)} {t('payment.creditsPerCHF')}
                </p>
                <ul className="space-y-2 mt-4">
                  {tier.features.map((feature, index) => (
                    <li key={index} className="flex items-start">
                      <Check className="h-4 w-4 text-primary mr-2 mt-1 flex-shrink-0" />
                      <span className="text-sm">{feature}</span>
                    </li>
                  ))}
                </ul>
              </CardContent>
              <CardFooter>
                <Button 
                  className="w-full" 
                  onClick={() => handlePurchase(tier.id)}
                  disabled={isLoading}
                  variant={tier.highlighted ? "default" : "outline"}
                >
                  {isLoading ? t('common.loading') : t('payment.buyNow')}
                </Button>
              </CardFooter>
            </Card>
          ))}
        </div>

        <div className="mt-12 text-center">
          <div className="bg-muted/30 rounded-lg p-6 max-w-md mx-auto">
            <p className="text-lg font-medium mb-2">
              {t('payment.currentBalance')}: <span className="font-bold">{user?.credits?.toLocaleString(currentLocale) || 0} Credits</span>
            </p>
            <p className="text-sm text-muted-foreground mt-2">
              {t('payment.securePayment')}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Payment; 