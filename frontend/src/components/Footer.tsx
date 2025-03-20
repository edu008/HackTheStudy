import { GraduationCap } from 'lucide-react';
import { Link } from 'react-router-dom';

const Footer = () => {
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
              Revolutioniere deine Prüfungsvorbereitung mit KI-generierten Lernmaterialien basierend auf deinen alten Prüfungen.
            </p>
          </div>
          
          <div>
            <h3 className="font-semibold mb-4">Features</h3>
            <ul className="space-y-3">
              <li>
                <Link to="/" className="text-muted-foreground hover:text-foreground transition-colors duration-200">
                  Prüfungsanalyse
                </Link>
              </li>
              <li>
                <Link to="/" className="text-muted-foreground hover:text-foreground transition-colors duration-200">
                  Karteikarten
                </Link>
              </li>
              <li>
                <Link to="/" className="text-muted-foreground hover:text-foreground transition-colors duration-200">
                  Testsimulator
                </Link>
              </li>
              <li>
                <Link to="/" className="text-muted-foreground hover:text-foreground transition-colors duration-200">
                  KI-Lernassistent
                </Link>
              </li>
            </ul>
          </div>
          
          <div>
            <h3 className="font-semibold mb-4">Kontakt & Rechtliches</h3>
            <ul className="space-y-3">
              <li>
                <a href="mailto:info.eduanroci@gmail.ch" className="text-muted-foreground hover:text-foreground transition-colors duration-200">
                info.eduanroci@gmail.ch
                </a>
              </li>
              <li>
                <Link to="/impressum" className="text-muted-foreground hover:text-foreground transition-colors duration-200">
                  Impressum
                </Link>
              </li>
              <li>
                <Link to="/datenschutz" className="text-muted-foreground hover:text-foreground transition-colors duration-200">
                  Datenschutz
                </Link>
              </li>
              <li className="text-muted-foreground">
                © {new Date().getFullYear()} HackTheStudy
              </li>
              <li className="text-muted-foreground">
                Alle Rechte vorbehalten
              </li>
            </ul>
          </div>
        </div>
      </div>
    </footer>
  );
};

export default Footer;
