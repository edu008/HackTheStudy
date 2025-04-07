import { GraduationCap } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

const Footer = () => {
  const { t } = useTranslation();
  
  return (
    <footer className="border-t border-border/50 bg-secondary/30">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
          <div className="md:col-span-2">
            <Link to="/" className="flex items-center space-x-2 text-xl font-semibold">
              <GraduationCap className="h-6 w-6 text-primary" />
              <span>HackTheStudy</span>
            </Link>
            
            <p className="mt-4 text-muted-foreground max-w-md">
              {t('footer.description')}
            </p>
          </div>
          
          <div>
            <h3 className="font-semibold mb-4">{t('footer.featuresTitle')}</h3>
            <ul className="space-y-3">
              <li>
                <Link to="/" className="text-muted-foreground hover:text-foreground transition-colors duration-200">
                  {t('footer.examAnalysis')}
                </Link>
              </li>
              <li>
                <Link to="/" className="text-muted-foreground hover:text-foreground transition-colors duration-200">
                  {t('footer.flashcards')}
                </Link>
              </li>
              <li>
                <Link to="/" className="text-muted-foreground hover:text-foreground transition-colors duration-200">
                  {t('footer.testSimulator')}
                </Link>
              </li>
              <li>
                <Link to="/" className="text-muted-foreground hover:text-foreground transition-colors duration-200">
                  {t('footer.aiAssistant')}
                </Link>
              </li>
            </ul>
          </div>
          
          <div>
            <h3 className="font-semibold mb-4">{t('footer.contactLegalTitle')}</h3>
            <ul className="space-y-3">
              <li>
                <a href="mailto:info.eduanroci@gmail.ch" className="text-muted-foreground hover:text-foreground transition-colors duration-200">
                info.eduanroci@gmail.ch
                </a>
              </li>
              <li>
                <Link to="/impressum" className="text-muted-foreground hover:text-foreground transition-colors duration-200">
                  {t('legal.impressum.title')}
                </Link>
              </li>
              <li>
                <Link to="/datenschutz" className="text-muted-foreground hover:text-foreground transition-colors duration-200">
                  {t('legal.privacy.title')}
                </Link>
              </li>
              <li className="text-muted-foreground">
                © {new Date().getFullYear()} HackTheStudy
              </li>
              <li className="text-muted-foreground">
                {t('footer.allRightsReserved')}
              </li>
            </ul>
          </div>
        </div>
      </div>
    </footer>
  );
};

export default Footer;
