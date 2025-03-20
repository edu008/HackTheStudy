import React from 'react';
import Navbar from '@/components/Navbar';
import Footer from '@/components/Footer';

const Impressum = () => {
  return (
    <div className="min-h-screen flex flex-col bg-[#f0f7ff]">
      <Navbar />
      <main className="flex-1 container mx-auto px-4 py-12 mt-20">
        <div className="max-w-3xl mx-auto">
          <div className="bg-white p-8 rounded-lg shadow-md border border-blue-100">
            <h1 className="text-3xl font-bold mb-8 text-gray-800 text-center">Impressum</h1>
            
            <div className="space-y-8">
              <section>
                <h2 className="text-xl font-semibold mb-4 text-gray-800">Angaben gemäss schweizerischem Recht</h2>
                <p className="text-gray-600">
                  HackTheStudy<br />
                </p>
              </section>

              <section>
                <h2 className="text-xl font-semibold mb-4 text-gray-800">Kontakt</h2>
                <p className="text-gray-600">
                  E-Mail: info.eduanroci@gmail.ch<br />
                </p>
              </section>


              <section>
                <h2 className="text-xl font-semibold mb-4 text-gray-800">Verantwortlich für den Inhalt</h2>
                <p className="text-gray-600">
                  Eduan Roci<br />
                  Schweiz
                </p>
              </section>

              <section>
                <h2 className="text-xl font-semibold mb-4 text-gray-800">Haftungsausschluss</h2>
                <h3 className="text-lg font-medium mb-2 text-gray-700">Haftung für Inhalte</h3>
                <p className="text-gray-600 mb-4">
                  Die Inhalte dieser Website wurden mit grösster Sorgfalt erstellt. Dennoch können wir keine Gewähr für die Richtigkeit, Vollständigkeit und Aktualität der Inhalte übernehmen. Als Diensteanbieter sind wir für eigene Inhalte auf diesen Seiten nach den allgemeinen Gesetzen der Schweiz verantwortlich.
                </p>
                
                <h3 className="text-lg font-medium mb-2 text-gray-700">Haftung für Links</h3>
                <p className="text-gray-600">
                  Diese Website enthält Links zu externen Webseiten Dritter, auf deren Inhalte wir keinen Einfluss haben. Deshalb können wir für diese fremden Inhalte auch keine Gewähr übernehmen. Für die Inhalte der verlinkten Seiten ist stets der jeweilige Anbieter oder Betreiber der Seiten verantwortlich. Bei Bekanntwerden von Rechtsverletzungen werden wir derartige Links umgehend entfernen.
                </p>
              </section>

              <section>
                <h2 className="text-xl font-semibold mb-4 text-gray-800">Urheberrechte</h2>
                <p className="text-gray-600">
                  Die durch die Seitenbetreiber erstellten Inhalte und Werke auf dieser Website unterliegen dem schweizerischen Urheberrecht. Die Vervielfältigung, Bearbeitung, Verbreitung und jede Art der Verwertung ausserhalb der Grenzen des Urheberrechts bedürfen der schriftlichen Zustimmung des jeweiligen Autors bzw. Erstellers.
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

export default Impressum;
