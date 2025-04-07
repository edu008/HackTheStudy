import React from 'react';
import { Link } from 'react-router-dom';
import { Github } from 'lucide-react';

const Footer = () => {
  const currentYear = new Date().getFullYear();

  return (
    <footer className="bg-background border-t mt-auto py-6">
      <div className="container mx-auto px-4">
        <div className="flex flex-col md:flex-row justify-between items-center">
          <div className="mb-4 md:mb-0">
            <p className="text-sm text-muted-foreground">
              &copy; {currentYear} HackTheStudy. Alle Rechte vorbehalten.
            </p>
          </div>
          
          <div className="flex items-center space-x-4">
            <Link to="/privacy" className="text-sm text-muted-foreground hover:text-foreground transition">
              Datenschutz
            </Link>
            <Link to="/terms" className="text-sm text-muted-foreground hover:text-foreground transition">
              AGB
            </Link>
            <Link to="/contact" className="text-sm text-muted-foreground hover:text-foreground transition">
              Kontakt
            </Link>
            <a 
              href="https://github.com/username/hackthestudy" 
              target="_blank" 
              rel="noopener noreferrer" 
              className="text-sm text-muted-foreground hover:text-foreground transition"
            >
              <Github className="h-4 w-4" />
            </a>
          </div>
        </div>
      </div>
    </footer>
  );
};

export default Footer;
