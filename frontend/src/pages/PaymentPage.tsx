
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import Navbar from '@/components/Navbar';
import Footer from '@/components/Footer';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { CheckCircle2, CreditCard, Euro } from 'lucide-react';
import { toast } from '@/components/ui/use-toast';

const paymentSchema = z.object({
  creditAmount: z.enum(['100', '250', '500', '1000']),
  paymentMethod: z.enum(['credit_card', 'paypal', 'bank_transfer']),
  cardNumber: z.string().optional(),
  cardName: z.string().optional(),
  expiryDate: z.string().optional(),
  cvv: z.string().optional(),
});

type PaymentFormValues = z.infer<typeof paymentSchema>;

const PaymentPage = () => {
  const { user, isLoading, addCredits } = useAuth();
  const navigate = useNavigate();
  const [isProcessing, setIsProcessing] = useState(false);

  const form = useForm<PaymentFormValues>({
    resolver: zodResolver(paymentSchema),
    defaultValues: {
      creditAmount: '100',
      paymentMethod: 'credit_card',
    },
  });

  useEffect(() => {
    if (!isLoading && !user) {
      navigate('/signin');
    }
  }, [user, isLoading, navigate]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center">
        <div className="animate-pulse text-lg">Loading...</div>
      </div>
    );
  }

  if (!user) {
    return null; // Redirect happens in useEffect
  }

  const onSubmit = (data: PaymentFormValues) => {
    setIsProcessing(true);
    
    // Simulate payment processing
    setTimeout(() => {
      const creditsToAdd = parseInt(data.creditAmount);
      addCredits(creditsToAdd);
      
      toast({
        title: "Payment Successful!",
        description: `You've added ${creditsToAdd} credits to your account.`,
      });
      
      setIsProcessing(false);
      navigate('/dashboard');
    }, 2000);
  };

  const creditOptions = [
    { value: '100', label: '100 Credits', price: '€9.99' },
    { value: '250', label: '250 Credits', price: '€19.99' },
    { value: '500', label: '500 Credits', price: '€34.99' },
    { value: '1000', label: '1000 Credits', price: '€59.99' },
  ];

  return (
    <div className="min-h-screen flex flex-col">
      <Navbar />
      <main className="flex-1 max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-24">
        <div className="mb-12 text-center">
          <h1 className="text-3xl font-bold">Add Credits to Your Account</h1>
          <p className="text-muted-foreground mt-2">Purchase credits to use all features of ExamMaster</p>
        </div>
        
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-8">
            <Card>
              <CardHeader>
                <CardTitle>Select Credit Package</CardTitle>
                <CardDescription>Choose how many credits you want to purchase</CardDescription>
              </CardHeader>
              <CardContent>
                <FormField
                  control={form.control}
                  name="creditAmount"
                  render={({ field }) => (
                    <FormItem className="space-y-3">
                      <FormControl>
                        <RadioGroup
                          onValueChange={field.onChange}
                          defaultValue={field.value}
                          className="grid grid-cols-1 md:grid-cols-2 gap-4"
                        >
                          {creditOptions.map((option) => (
                            <FormItem key={option.value} className="flex">
                              <FormControl>
                                <RadioGroupItem
                                  value={option.value}
                                  className="sr-only"
                                  id={`option-${option.value}`}
                                />
                              </FormControl>
                              <FormLabel
                                htmlFor={`option-${option.value}`}
                                className={`flex flex-1 cursor-pointer items-center justify-between rounded-md border-2 p-4 ${
                                  field.value === option.value 
                                    ? 'border-primary' 
                                    : 'border-muted'
                                }`}
                              >
                                <div className="flex flex-col gap-1">
                                  <span className="font-medium">{option.label}</span>
                                  <span className="text-muted-foreground">
                                    Best for moderate usage
                                  </span>
                                </div>
                                <div className="flex flex-col items-end gap-1">
                                  <span className="font-bold">{option.price}</span>
                                  {field.value === option.value && (
                                    <CheckCircle2 className="text-primary h-5 w-5" />
                                  )}
                                </div>
                              </FormLabel>
                            </FormItem>
                          ))}
                        </RadioGroup>
                      </FormControl>
                      <FormDescription>
                        Credits are used to analyze exams, generate flashcards, and run test simulations
                      </FormDescription>
                    </FormItem>
                  )}
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Payment Method</CardTitle>
                <CardDescription>Choose how you want to pay</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <FormField
                  control={form.control}
                  name="paymentMethod"
                  render={({ field }) => (
                    <FormItem className="space-y-3">
                      <FormControl>
                        <RadioGroup
                          onValueChange={field.onChange}
                          defaultValue={field.value}
                          className="flex flex-col space-y-2"
                        >
                          <FormItem className="flex items-center space-x-3 space-y-0">
                            <FormControl>
                              <RadioGroupItem value="credit_card" />
                            </FormControl>
                            <FormLabel className="font-normal flex items-center">
                              <CreditCard className="mr-2 h-4 w-4" />
                              Credit Card
                            </FormLabel>
                          </FormItem>
                          <FormItem className="flex items-center space-x-3 space-y-0">
                            <FormControl>
                              <RadioGroupItem value="paypal" />
                            </FormControl>
                            <FormLabel className="font-normal">
                              PayPal
                            </FormLabel>
                          </FormItem>
                          <FormItem className="flex items-center space-x-3 space-y-0">
                            <FormControl>
                              <RadioGroupItem value="bank_transfer" />
                            </FormControl>
                            <FormLabel className="font-normal flex items-center">
                              <Euro className="mr-2 h-4 w-4" />
                              Bank Transfer
                            </FormLabel>
                          </FormItem>
                        </RadioGroup>
                      </FormControl>
                    </FormItem>
                  )}
                />

                {form.watch('paymentMethod') === 'credit_card' && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="col-span-2">
                      <FormField
                        control={form.control}
                        name="cardNumber"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>Card Number</FormLabel>
                            <FormControl>
                              <Input placeholder="4242 4242 4242 4242" {...field} />
                            </FormControl>
                          </FormItem>
                        )}
                      />
                    </div>
                    <FormField
                      control={form.control}
                      name="cardName"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Name on Card</FormLabel>
                          <FormControl>
                            <Input placeholder="John Doe" {...field} />
                          </FormControl>
                        </FormItem>
                      )}
                    />
                    <div className="grid grid-cols-2 gap-4">
                      <FormField
                        control={form.control}
                        name="expiryDate"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>Expiry Date</FormLabel>
                            <FormControl>
                              <Input placeholder="MM/YY" {...field} />
                            </FormControl>
                          </FormItem>
                        )}
                      />
                      <FormField
                        control={form.control}
                        name="cvv"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>CVV</FormLabel>
                            <FormControl>
                              <Input placeholder="123" {...field} />
                            </FormControl>
                          </FormItem>
                        )}
                      />
                    </div>
                  </div>
                )}
              </CardContent>
              <CardFooter className="flex justify-between">
                <Button variant="outline" onClick={() => navigate('/dashboard')}>
                  Cancel
                </Button>
                <Button type="submit" disabled={isProcessing}>
                  {isProcessing ? 'Processing...' : 'Complete Purchase'}
                </Button>
              </CardFooter>
            </Card>
          </form>
        </Form>
      </main>
      <Footer />
    </div>
  );
};

export default PaymentPage;
