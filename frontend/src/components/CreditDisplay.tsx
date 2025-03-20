import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Button } from './ui/button';
import { useNavigate } from 'react-router-dom';
import { Wallet } from 'lucide-react';
import { toast } from 'sonner';

// API Endpunkte
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000';
const PAYMENT_API_URL = import.meta.env.VITE_PAYMENT_API_URL || 'http://localhost:5001';

export default function CreditDisplay() {
  const [credits, setCredits] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    fetchCredits();
  }, []);

  const fetchCredits = async () => {
    setIsLoading(true);
    try {
      const token = localStorage.getItem('exammaster_token');
      if (!token) {
        setCredits(0);
        setIsLoading(false);
        return;
      }
      
      const response = await axios.get(
        `${PAYMENT_API_URL}/api/payment/get-credits`,
        { 
          withCredentials: true,
          headers: { 
            Authorization: `Bearer ${token}`
          }
        }
      );
      setCredits(response.data.credits);
    } catch (error) {
      console.error('Fehler beim Abrufen der Credits:', error);
      toast.error('Fehler beim Laden der Credits');
    } finally {
      setIsLoading(false);
    }
  };

  const handleNavigateToPayment = () => {
    navigate('/payment');
  };

  return (
    <div className="flex items-center gap-2 px-3 py-2">
      <div className="flex items-center gap-1">
        <Wallet className="h-4 w-4 text-primary" />
        <span className="font-medium">
          {isLoading ? '...' : credits !== null ? credits : '0'} Credits
        </span>
      </div>
      <Button
        variant="outline"
        size="sm"
        onClick={handleNavigateToPayment}
        className="h-7 text-xs"
      >
        Aufladen
      </Button>
    </div>
  );
} 