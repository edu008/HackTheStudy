import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { CreditCard, CheckCircle, XCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';

const PaymentHistory = () => {
  const { user, payments, fetchPayments } = useAuth();
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    const loadPayments = async () => {
      if (user) {
        setIsLoading(true);
        await fetchPayments();
        setIsLoading(false);
      }
    };
    
    loadPayments();
  }, [user, fetchPayments]);

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return new Intl.DateTimeFormat('de-DE', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    }).format(date);
  };

  const formatAmount = (amount: number) => {
    return new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: 'EUR'
    }).format(amount);
  };

  const getPaymentMethodIcon = (method: string) => {
    return <CreditCard className="h-5 w-5 text-blue-500" />;
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return (
          <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200">
            <CheckCircle className="h-3 w-3 mr-1" /> Completed
          </Badge>
        );
      case 'pending':
        return (
          <Badge variant="outline" className="bg-yellow-50 text-yellow-700 border-yellow-200">
            Processing
          </Badge>
        );
      case 'failed':
        return (
          <Badge variant="outline" className="bg-red-50 text-red-700 border-red-200">
            <XCircle className="h-3 w-3 mr-1" /> Failed
          </Badge>
        );
      default:
        return (
          <Badge variant="outline">
            {status}
          </Badge>
        );
    }
  };

  const handleRefresh = async () => {
    setIsLoading(true);
    await fetchPayments();
    setIsLoading(false);
  };

  return (
    <div className="py-6">
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-medium">Payment History</h3>
        <Button 
          variant="outline" 
          size="sm" 
          onClick={handleRefresh}
          disabled={isLoading}
        >
          Refresh
        </Button>
      </div>
      
      {!user ? (
        <div className="text-center py-10 text-muted-foreground">
          Please sign in to view your payment history
        </div>
      ) : isLoading ? (
        <div className="space-y-6 pr-4">
          {Array(3).fill(0).map((_, i) => (
            <div key={i} className="space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <Skeleton className="h-5 w-5 rounded-full" />
                  <div className="space-y-1">
                    <Skeleton className="h-4 w-40" />
                    <Skeleton className="h-3 w-24" />
                  </div>
                </div>
                <Skeleton className="h-6 w-20" />
              </div>
              <Separator />
            </div>
          ))}
        </div>
      ) : payments.length === 0 ? (
        <div className="text-center py-10 text-muted-foreground">
          No payment history available yet
        </div>
      ) : (
        <ScrollArea className="h-[400px]">
          <div className="space-y-6 pr-4">
            {payments.map((payment) => (
              <div key={payment.id} className="space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-3">
                    {getPaymentMethodIcon(payment.payment_method)}
                    <div>
                      <h4 className="text-sm font-medium">
                        {payment.credits} Credits ({formatAmount(payment.amount)})
                      </h4>
                      <p className="text-xs text-muted-foreground">
                        {formatDate(payment.created_at)}
                      </p>
                    </div>
                  </div>
                  <div>
                    {getStatusBadge(payment.status)}
                  </div>
                </div>
                <Separator />
              </div>
            ))}
          </div>
        </ScrollArea>
      )}
    </div>
  );
};

export default PaymentHistory;
