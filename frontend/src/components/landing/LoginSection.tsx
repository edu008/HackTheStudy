import React from 'react';
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { FcGoogle } from "react-icons/fc";
import { Github, ArrowUp } from "lucide-react";
import { useTranslation } from 'react-i18next';

interface LoginSectionProps {
  onBackClick: () => void;
  onSignIn: (provider: string) => void;
}

const LoginSection = ({ onBackClick, onSignIn }: LoginSectionProps) => {
  const { t } = useTranslation();
  
  return (
    <div className="container mx-auto px-6">
      <div className="max-w-md mx-auto transform transition-all duration-500">
        <Card className="shadow-lg border-blue-100 bg-white">
          <CardHeader className="text-center">
            <CardTitle className="text-gray-800">{t('landing.login.title', 'Anmelden')}</CardTitle>
            <CardDescription className="text-gray-600">
              {t('landing.login.description', 'Wähle eine Anmeldemethode')}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Button 
              variant="outline" 
              className="w-full transform transition-all duration-200 hover:scale-102 hover:shadow-md border-blue-100" 
              onClick={() => onSignIn('google')}
            >
              <FcGoogle className="mr-2 h-4 w-4" />
              {t('landing.login.googleButton', 'Mit Google anmelden')}
            </Button>
            <Button 
              variant="outline" 
              className="w-full transform transition-all duration-200 hover:scale-102 hover:shadow-md border-blue-100" 
              onClick={() => onSignIn('github')}
            >
              <Github className="mr-2 h-4 w-4" />
              {t('landing.login.githubButton', 'Mit GitHub anmelden')}
            </Button>
            
            <p className="text-xs text-center text-gray-500 mt-4">
              {t('landing.login.note', 'Durch die Anmeldung stimmst du unseren Nutzungsbedingungen zu')}
            </p>
          </CardContent>
          <CardFooter className="flex justify-center">
            <Button 
              variant="ghost" 
              onClick={onBackClick}
              className="flex items-center text-blue-600 hover:bg-blue-50 gap-2"
            >
              <ArrowUp className="h-4 w-4" />
              {t('landing.login.backButton', 'Zurück')}
            </Button>
          </CardFooter>
        </Card>
      </div>
    </div>
  );
};

export default LoginSection;
