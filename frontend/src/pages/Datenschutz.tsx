import React from 'react';
import Navbar from '@/components/Navbar';
import Footer from '@/components/Footer';

const Datenschutz = () => {
  return (
    <div className="min-h-screen flex flex-col bg-[#f0f7ff]">
      <Navbar />
      <main className="flex-1 container mx-auto px-4 py-12 mt-20">
        <div className="max-w-4xl mx-auto">
          <div className="bg-white p-8 rounded-lg shadow-md border border-blue-100">
            <h1 className="text-3xl font-bold mb-8 text-gray-800 text-center">Datenschutzerklärung</h1>
            
            <div className="space-y-8">
              <section>
                <h2 className="text-xl font-semibold mb-4 text-gray-800">1. Verantwortliche Stelle 📝</h2>
                <p className="text-gray-600">
                  Verantwortlich für die Datenverarbeitung auf dieser Website ist der Betreiber von HackTheStudy.
                  Kontaktdetails finden Sie im Impressum.
                </p>
              </section>

              <section>
                <h2 className="text-xl font-semibold mb-4 text-gray-800">2. Erhobene und verarbeitete Daten 📊</h2>
                <ul className="list-disc pl-6 text-gray-600 space-y-2">
                  <li>Registrierungsdaten (Name, E-Mail, Passwort)</li>
                  <li>Hochgeladene Dokumente und erstellte Inhalte</li>
                  <li>Nutzungsdaten (z. B. Lernfortschritte, Sitzungsinformationen)</li>
                  <li>Technische Daten (IP-Adresse, Gerätetyp, Browserinformationen)</li>
                  <li>Bei kostenpflichtigen Services: Zahlungsinformationen</li>
                </ul>
              </section>

              <section>
                <h2 className="text-xl font-semibold mb-4 text-gray-800">3. Verwendungszwecke 🎯</h2>
                <p className="text-gray-600">
                  Wir verwenden die erfassten Daten zur:
                </p>
                <ul className="list-disc pl-6 text-gray-600 space-y-2">
                  <li>Bereitstellung der Plattform und Funktionen</li>
                  <li>Optimierung der Lerninhalte und -angebote</li>
                  <li>Ermöglichung von Premium-Diensten</li>
                  <li>Erfüllung gesetzlicher Pflichten</li>
                </ul>
              </section>

              <section>
                <h2 className="text-xl font-semibold mb-4 text-gray-800">4. Rechtliche Grundlagen ⚖️</h2>
                <p className="text-gray-600">
                  Die Datenverarbeitung erfolgt im Einklang mit dem schweizerischen Datenschutzgesetz (DSG), insbesondere:
                </p>
                <ul className="list-disc pl-6 text-gray-600 space-y-2">
                  <li>Zur Erfüllung vertraglicher Verpflichtungen</li>
                  <li>Auf Basis berechtigter Interessen</li>
                  <li>Auf Basis Ihrer Einwilligung</li>
                </ul>
              </section>

              <section>
                <h2 className="text-xl font-semibold mb-4 text-gray-800">5. Cookies und Tracking 🍪</h2>
                <p className="text-gray-600">
                  Unsere Plattform nutzt Cookies und Tracking-Technologien zur Verbesserung der Benutzererfahrung.
                  Sie können Cookies in den Browsereinstellungen verwalten oder deaktivieren.
                </p>
              </section>

              <section>
                <h2 className="text-xl font-semibold mb-4 text-gray-800">6. API-Nutzung und Datenverarbeitung 🌐</h2>
                <p className="text-gray-600">
                  Wir nutzen APIs zur Datenverarbeitung und zur Bereitstellung personalisierter Lerninhalte.
                  Dabei achten wir auf Datenschutz und Sicherheit.
                </p>
              </section>

              <section>
                <h2 className="text-xl font-semibold mb-4 text-gray-800">7. Zahlungsdaten 💳</h2>
                <p className="text-gray-600">
                  Bei der Nutzung kostenpflichtiger Funktionen werden Zahlungsdaten über sichere Zahlungsanbieter verarbeitet.
                  Wir speichern keine vollständigen Kreditkartendaten auf unseren Servern.
                </p>
              </section>

              <section>
                <h2 className="text-xl font-semibold mb-4 text-gray-800">8. Ihre Rechte 📋</h2>
                <ul className="list-disc pl-6 text-gray-600 space-y-2">
                  <li>Recht auf Auskunft über gespeicherte Daten</li>
                  <li>Recht auf Berichtigung unrichtiger Daten</li>
                  <li>Recht auf Löschung Ihrer Daten</li>
                  <li>Recht auf Widerspruch gegen die Verarbeitung</li>
                </ul>
                <p className="text-gray-600">
                  Zur Ausübung Ihrer Rechte kontaktieren Sie uns bitte über die im Impressum angegebene E-Mail-Adresse.
                </p>
              </section>

              <section>
                <h2 className="text-xl font-semibold mb-4 text-gray-800">9. Datensicherheit 🔒</h2>
                <p className="text-gray-600">
                  Wir setzen technische und organisatorische Massnahmen ein, um Ihre Daten zu schützen.
                  Alle Datenübertragungen erfolgen verschlüsselt über HTTPS.
                </p>
              </section>

              <section>
                <h2 className="text-xl font-semibold mb-4 text-gray-800">10. Speicherdauer 🕒</h2>
                <p className="text-gray-600">
                  Daten werden nur so lange gespeichert, wie es für die Bereitstellung unserer Dienste notwendig oder gesetzlich vorgeschrieben ist.
                  Sie können Ihre Daten jederzeit löschen lassen.
                </p>
              </section>
            </div>
          </div>
        </div>
      </main>
      <Footer />
    </div>
  );
};

export default Datenschutz;